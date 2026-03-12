#!/usr/bin/env python3
"""
Local Supabase snapshot manager — create, restore, and list data snapshots.

Allows you to save all local Supabase table data and later restore it,
even after a `supabase db reset` that drops and re-creates the schema.
Only public-schema data is captured; the supabase_migrations schema is
managed by the Supabase CLI and left untouched.

Usage:
    python -m reflexio.scripts.snapshot_manager create [--name NAME]
    python -m reflexio.scripts.snapshot_manager restore <name>
    python -m reflexio.scripts.snapshot_manager list
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:54322/postgres"
SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "data" / "snapshots"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_applied_migrations(db_url: str) -> list[str]:
    """
    Query supabase_migrations.schema_migrations for all applied migration versions.

    Args:
        db_url (str): PostgreSQL connection URL

    Returns:
        list[str]: Sorted list of migration version strings
    """
    conn = psycopg2.connect(db_url)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT version FROM supabase_migrations.schema_migrations ORDER BY version"
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def _public_tables_are_empty(db_url: str) -> tuple[bool, list[str]]:
    """
    Check whether all public-schema tables are empty.

    Args:
        db_url (str): PostgreSQL connection URL

    Returns:
        tuple[bool, list[str]]: (all_empty, list_of_non_empty_table_names)
    """
    conn = psycopg2.connect(db_url)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = [row[0] for row in cursor.fetchall()]

        non_empty: list[str] = []
        for table in tables:
            cursor.execute(
                f'SELECT EXISTS (SELECT 1 FROM public."{table}" LIMIT 1)'
            )  # noqa: S608
            if cursor.fetchone()[0]:
                non_empty.append(table)

        return len(non_empty) == 0, non_empty
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_create(args: argparse.Namespace) -> int:
    """
    Create a snapshot of local Supabase data.

    Dumps all public-schema table data using pg_dump (custom format) and
    writes a metadata.json alongside it with the current applied migrations.

    Args:
        args: Parsed CLI arguments (name, db_url)

    Returns:
        int: 0 on success, 1 on failure
    """
    db_url = args.db_url
    name = args.name or "snapshot"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_dir = SNAPSHOTS_DIR / f"{name}_{timestamp}"

    logger.info("Creating snapshot '%s' ...", snapshot_dir.name)

    # 1. Get applied migrations
    try:
        migrations = _get_applied_migrations(db_url)
    except Exception as e:
        logger.error("Failed to read migrations: %s", e)
        return 1

    logger.info("Found %d applied migrations", len(migrations))

    # 2. Create snapshot directory
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # 3. pg_dump --data-only for public schema
    dump_file = snapshot_dir / "data.dump"

    # Parse connection details from URL for pg_dump CLI flags
    from urllib.parse import urlparse

    parsed = urlparse(db_url)
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 54322)
    user = parsed.username or "postgres"
    dbname = parsed.path.lstrip("/") or "postgres"

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or "postgres"

    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "--data-only",
        "--schema=public",
        "-Fc",  # custom format
        "-f",
        str(dump_file),
    ]

    logger.info("Running pg_dump ...")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("pg_dump failed:\n%s", result.stderr)
        return 1

    # 4. Write metadata
    metadata = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applied_migrations": migrations,
    }
    metadata_file = snapshot_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2))

    dump_size_mb = dump_file.stat().st_size / (1024 * 1024)
    logger.info(
        "Snapshot created: %s (%.1f MB dump, %d migrations recorded)",
        snapshot_dir,
        dump_size_mb,
        len(migrations),
    )
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """
    Restore a snapshot into the local Supabase database.

    Expects the database to have been reset via `supabase db reset` first
    (schema applied, tables empty). Restores public-schema data with
    pg_restore, then runs any DATA_MIGRATIONS added after the snapshot.

    Args:
        args: Parsed CLI arguments (name, db_url, force)

    Returns:
        int: 0 on success, 1 on failure
    """
    db_url = args.db_url
    snapshot_path = SNAPSHOTS_DIR / args.name

    if not snapshot_path.is_dir():
        logger.error("Snapshot not found: %s", snapshot_path)
        logger.info("Available snapshots:")
        if SNAPSHOTS_DIR.exists():
            for d in sorted(SNAPSHOTS_DIR.iterdir()):
                if d.is_dir():
                    logger.info("  %s", d.name)
        return 1

    dump_file = snapshot_path / "data.dump"
    metadata_file = snapshot_path / "metadata.json"

    if not dump_file.exists() or not metadata_file.exists():
        logger.error("Invalid snapshot — missing data.dump or metadata.json")
        return 1

    # 1. Safety check: tables should be empty (post supabase db reset)
    try:
        all_empty, non_empty = _public_tables_are_empty(db_url)
    except Exception as e:
        logger.error("Failed to check table state: %s", e)
        return 1

    if not all_empty and not args.force:
        logger.error(
            "Tables are not empty: %s\n"
            "Run `supabase db reset` first, or use --force to skip this check.",
            ", ".join(non_empty),
        )
        return 1
    elif not all_empty:
        logger.warning(
            "Tables not empty (--force): %s. Truncating before restore.",
            ", ".join(non_empty),
        )
        conn = psycopg2.connect(db_url)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            table_list = ", ".join(f'public."{t}"' for t in tables)
            cursor.execute(f"TRUNCATE {table_list} CASCADE")  # noqa: S608
            conn.commit()
            logger.info("Truncated all public tables")
        except Exception as e:
            conn.rollback()
            logger.error("Failed to truncate tables: %s", e)
            return 1
        finally:
            conn.close()

    # 2. Restore data via plain SQL (avoids --disable-triggers permission issues)
    from urllib.parse import urlparse

    parsed = urlparse(db_url)
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 54322)
    user = parsed.username or "postgres"
    dbname = parsed.path.lstrip("/") or "postgres"

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or "postgres"

    # 2a. Convert custom-format dump to plain SQL
    logger.info("Converting dump to plain SQL ...")
    convert_cmd = [
        "pg_restore",
        "-f",
        "-",  # output to stdout
        str(dump_file),
    ]
    convert_result = subprocess.run(
        convert_cmd, env=env, capture_output=True, text=True
    )
    if convert_result.returncode != 0 and not convert_result.stdout:
        logger.error("pg_restore conversion failed:\n%s", convert_result.stderr)
        return 1

    # 2b. Filter out unsupported SET commands and wrap with session_replication_role
    #     to bypass foreign-key checks without needing superuser trigger control.
    lines = convert_result.stdout.splitlines(keepends=True)
    filtered_sql = "".join(
        line for line in lines if not line.strip().startswith("SET transaction_timeout")
    )

    # Filter out COPY blocks for excluded tables and rename columns
    exclude_tables = set(getattr(args, "exclude_tables", []) or [])
    # Parse --rename-columns: "table.old_col=new_col" entries
    rename_columns: dict[str, dict[str, str]] = {}
    for entry in getattr(args, "rename_columns", []) or []:
        # Format: table.old_col=new_col
        left, new_col = entry.split("=", 1)
        table, old_col = left.rsplit(".", 1)
        rename_columns.setdefault(table, {})[old_col] = new_col

    # Auto-detect columns in snapshot that don't exist in current DB schema
    drop_columns: dict[str, set[str]] = {}
    conn_check = psycopg2.connect(db_url)
    try:
        cursor_check = conn_check.cursor()
        for line in filtered_sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("COPY public."):
                table_name = stripped.split(".", 1)[1].split(" ", 1)[0].strip('"')
                # Extract column list from COPY statement
                col_start = stripped.index("(") + 1
                col_end = stripped.index(")")
                snapshot_cols = [
                    c.strip() for c in stripped[col_start:col_end].split(",")
                ]
                # Get current DB columns
                cursor_check.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table_name,),
                )
                db_cols = {row[0] for row in cursor_check.fetchall()}
                missing = {c for c in snapshot_cols if c not in db_cols}
                if missing:
                    drop_columns[table_name] = missing
                    logger.info(
                        "Table '%s': dropping columns not in current schema: %s",
                        table_name,
                        ", ".join(sorted(missing)),
                    )
    finally:
        conn_check.close()

    if exclude_tables or rename_columns or drop_columns:
        if exclude_tables:
            logger.info("Excluding tables from restore: %s", ", ".join(exclude_tables))
        if rename_columns:
            logger.info("Renaming columns during restore: %s", rename_columns)
        result_lines = []
        skipping = False
        # Track column indices to drop for current COPY block
        current_drop_indices: set[int] = set()
        in_copy_data = False
        for line in filtered_sql.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("COPY public."):
                # COPY public."table_name" (col1, col2, ...) FROM stdin;
                table_name = stripped.split(".", 1)[1].split(" ", 1)[0].strip('"')
                if table_name in exclude_tables:
                    skipping = True
                    continue
                if table_name in rename_columns:
                    for old_col, new_col in rename_columns[table_name].items():
                        line = line.replace(old_col, new_col)
                # Handle dropping columns
                current_drop_indices = set()
                if table_name in drop_columns:
                    col_start = stripped.index("(") + 1
                    col_end = stripped.index(")")
                    cols = [c.strip() for c in stripped[col_start:col_end].split(",")]
                    current_drop_indices = {
                        i for i, c in enumerate(cols) if c in drop_columns[table_name]
                    }
                    kept_cols = [
                        c for i, c in enumerate(cols) if i not in current_drop_indices
                    ]
                    # Rebuild the COPY line
                    prefix = line[: line.index("(") + 1]
                    suffix = line[line.index(")") :]
                    line = prefix + ", ".join(kept_cols) + suffix
                in_copy_data = True
                result_lines.append(line)
                continue
            if skipping:
                if stripped == "\\.":
                    skipping = False
                continue
            if in_copy_data:
                if stripped == "\\.":
                    in_copy_data = False
                    current_drop_indices = set()
                    result_lines.append(line)
                elif current_drop_indices:
                    # Drop columns from tab-separated data row
                    fields = line.rstrip("\n").split("\t")
                    kept_fields = [
                        f for i, f in enumerate(fields) if i not in current_drop_indices
                    ]
                    result_lines.append("\t".join(kept_fields) + "\n")
                else:
                    result_lines.append(line)
            else:
                result_lines.append(line)
        filtered_sql = "".join(result_lines)

    restore_sql = (
        "SET session_replication_role = 'replica';\n"
        + filtered_sql
        + "\nSET session_replication_role = 'origin';\n"
    )

    # 2c. Execute via psql
    logger.info("Restoring data via psql ...")
    psql_cmd = [
        "psql",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "-v",
        "ON_ERROR_STOP=1",
    ]
    result = subprocess.run(
        psql_cmd, env=env, input=restore_sql, capture_output=True, text=True
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.error("psql restore failed:\n%s", stderr)
        return 1

    logger.info("Data restored successfully")

    # 3. Run data migrations added after the snapshot
    metadata = json.loads(metadata_file.read_text())
    snapshot_migrations = set(metadata.get("applied_migrations", []))

    from reflexio.server.services.storage.supabase_migrations import DATA_MIGRATIONS

    new_versions = sorted(v for v in DATA_MIGRATIONS if v not in snapshot_migrations)

    if new_versions:
        logger.info(
            "Running %d new data migration(s): %s",
            len(new_versions),
            ", ".join(new_versions),
        )
        conn = psycopg2.connect(db_url)
        try:
            cursor = conn.cursor()
            for version in new_versions:
                logger.info("  Running data migration %s ...", version)
                DATA_MIGRATIONS[version](conn, cursor)
            conn.commit()
            logger.info("Data migrations completed")
        except Exception as e:
            conn.rollback()
            logger.error("Data migration failed: %s", e)
            return 1
        finally:
            conn.close()
    else:
        logger.info("No new data migrations to run")

    logger.info("Restore complete")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """
    List available snapshots with their metadata.

    Args:
        args: Parsed CLI arguments (unused)

    Returns:
        int: Always 0
    """
    if not SNAPSHOTS_DIR.exists():
        print("No snapshots directory found.")
        return 0

    snapshot_dirs = sorted(
        [d for d in SNAPSHOTS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    if not snapshot_dirs:
        print("No snapshots found.")
        return 0

    print(f"\nAvailable snapshots ({len(snapshot_dirs)}):")
    print("-" * 70)

    for snap_dir in snapshot_dirs:
        metadata_file = snap_dir / "metadata.json"
        dump_file = snap_dir / "data.dump"

        if not metadata_file.exists():
            print(f"  {snap_dir.name}  (missing metadata.json)")
            continue

        metadata = json.loads(metadata_file.read_text())
        name = metadata.get("name", "?")
        created_at = metadata.get("created_at", "?")
        migrations = metadata.get("applied_migrations", [])
        latest_migration = migrations[-1] if migrations else "none"

        dump_size = ""
        if dump_file.exists():
            size_mb = dump_file.stat().st_size / (1024 * 1024)
            dump_size = f"{size_mb:.1f} MB"

        print(f"  {snap_dir.name}")
        print(f"    Name: {name}")
        print(f"    Created: {created_at}")
        print(f"    Migrations: {len(migrations)} (latest: {latest_migration})")
        if dump_size:
            print(f"    Size: {dump_size}")
        print()

    print("-" * 70)
    print(f"Restore with: python -m reflexio.scripts.snapshot_manager restore <name>")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local Supabase snapshot manager — create, restore, and list data snapshots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m reflexio.scripts.snapshot_manager create --name before_reset\n"
            "  python -m reflexio.scripts.snapshot_manager list\n"
            "  python -m reflexio.scripts.snapshot_manager restore before_reset_20260207_120000\n"
        ),
    )

    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        help=f"PostgreSQL connection URL (default: {DEFAULT_DB_URL})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Create a new snapshot")
    create_parser.add_argument(
        "--name",
        default="snapshot",
        help="Name prefix for the snapshot directory (default: snapshot)",
    )

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore a snapshot")
    restore_parser.add_argument(
        "name",
        help="Name of the snapshot to restore (e.g. demo_with_login_20260214_020834)",
    )
    restore_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip empty-tables safety check",
    )
    restore_parser.add_argument(
        "--exclude-tables",
        nargs="+",
        default=[],
        metavar="TABLE",
        help="Tables to skip during restore (e.g. agent_success_evaluation_result)",
    )
    restore_parser.add_argument(
        "--rename-columns",
        nargs="+",
        default=[],
        metavar="TABLE.OLD=NEW",
        help="Rename columns in COPY headers (e.g. requests.request_group=session_id)",
    )

    # list
    subparsers.add_parser("list", help="List available snapshots")

    args = parser.parse_args()

    if args.command == "create":
        return cmd_create(args)
    elif args.command == "restore":
        return cmd_restore(args)
    elif args.command == "list":
        return cmd_list(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
