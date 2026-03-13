#!/usr/bin/env python3
"""
Run Supabase migrations for all organizations at deployment time.

This script runs before FastAPI starts to ensure all organizations have the latest
database schema. It supports two modes:

1. Self-host mode (SELF_HOST=true): Loads local config and runs a single migration
2. Cloud mode: Connects to login Supabase, fetches all orgs, decrypts configs, and migrates each

Usage:
    # Dry run (lists orgs without migrating)
    python -m reflexio.scripts.run_all_migrations --dry-run

    # Single org test
    python -m reflexio.scripts.run_all_migrations --org-id "test-org"

    # Full run with error tolerance
    python -m reflexio.scripts.run_all_migrations --continue-on-error

Required env vars:
    - RUN_MIGRATION: Must be "true" to run migrations (otherwise script exits early)

Required env vars (cloud mode):
    - LOGIN_SUPABASE_URL: Login database URL
    - LOGIN_SUPABASE_KEY: Login database service key
    - FERNET_KEYS: Config decryption keys
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Add parent directories to path for imports
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from reflexio.server.services.storage.supabase_storage_utils import (
    extract_db_url_from_config_json,
    is_localhost_url,
)


@dataclass
class MigrationResult:
    """Result of a migration operation for an organization."""

    org_id: str
    success: bool
    message: str
    skipped: bool = False


def get_self_host_mode() -> bool:
    """Check if running in self-host mode."""
    return os.getenv("SELF_HOST", "false").lower() == "true"


def get_local_config_db_url(org_id: str = "self-host-org") -> str | None:
    """
    Load local config and extract db_url for self-host mode.

    Args:
        org_id: Organization ID (default: self-host-org)

    Returns:
        str | None: The db_url from storage config, or None if not found/applicable
    """
    from reflexio import data

    config_dir = Path(data.__file__).parent / "configs"
    config_file = config_dir / f"config_{org_id}.json"

    if not config_file.exists():
        logger.warning(f"Config file not found: {config_file}")
        return None

    try:
        # Get FERNET_KEYS for decryption
        fernet_keys = os.environ.get("FERNET_KEYS", "").strip()

        with config_file.open(encoding="utf-8") as f:
            config_raw = f.read()

        # Decrypt if encryption is configured
        if fernet_keys:
            from reflexio.utils.encrypt_manager import EncryptManager

            encrypt_manager = EncryptManager(fernet_keys=fernet_keys)
            config_content = encrypt_manager.decrypt(encrypted_value=config_raw)
            if config_content is None:
                # Decryption failed, try reading as plain text
                config_content = config_raw
        else:
            config_content = config_raw

        config_data = json.loads(str(config_content))
        storage_config = config_data.get("storage_config")

        if storage_config and "db_url" in storage_config:
            return storage_config["db_url"]

        logger.info(f"No db_url in storage config for {org_id} (using local storage)")
        return None

    except Exception as e:
        logger.error(f"Error loading config for {org_id}: {e}")
        return None


def get_all_organizations_with_db_url() -> list[tuple[str, str]]:
    """
    Fetch all organizations from login Supabase and extract their db_urls.

    Returns:
        list[tuple[str, str]]: List of (org_id, db_url) tuples
    """
    from reflexio.server import FERNET_KEYS, LOGIN_SUPABASE_KEY, LOGIN_SUPABASE_URL

    if not LOGIN_SUPABASE_URL or not LOGIN_SUPABASE_KEY:
        logger.error("LOGIN_SUPABASE_URL or LOGIN_SUPABASE_KEY not configured")
        return []

    try:
        from supabase import create_client

        client = create_client(LOGIN_SUPABASE_URL, LOGIN_SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return []

    # Initialize encryption manager
    encrypt_manager = None
    if FERNET_KEYS:
        from reflexio.utils.encrypt_manager import EncryptManager

        encrypt_manager = EncryptManager(fernet_keys=FERNET_KEYS)

    organizations_with_db_url = []

    try:
        # Fetch all organizations in batches
        batch_size = 100
        offset = 0

        while True:
            response = (
                client.table("organizations")
                .select("id, configuration_json, is_self_managed")
                .range(offset, offset + batch_size - 1)
                .execute()
            )

            if not response.data:
                break

            for org in response.data:
                org_id = org.get("id")
                config_json_encrypted = org.get("configuration_json")
                is_self_managed = org.get("is_self_managed", False)

                if not org_id:
                    continue

                if is_self_managed:
                    logger.info(f"Skipping self-managed org: {org_id}")
                    continue

                if not config_json_encrypted:
                    logger.debug(f"Org {org_id} has no configuration_json")
                    continue

                try:
                    # Decrypt the configuration
                    config_json_str = config_json_encrypted
                    if encrypt_manager:
                        decrypted = encrypt_manager.decrypt(
                            encrypted_value=str(config_json_encrypted)
                        )
                        if decrypted:
                            config_json_str = decrypted
                        else:
                            logger.warning(
                                f"Failed to decrypt config for org {org_id}, skipping"
                            )
                            continue

                    db_url = extract_db_url_from_config_json(config_json_str)
                    if db_url:
                        organizations_with_db_url.append((org_id, db_url))
                    else:
                        logger.debug(
                            f"Org {org_id} has no db_url in storage_config (likely local storage)"
                        )

                except Exception as e:
                    logger.warning(f"Error processing org {org_id}: {e}")

            if len(response.data) < batch_size:
                break

            offset += batch_size

    except Exception as e:
        logger.error(f"Error fetching organizations: {e}")

    return organizations_with_db_url


def run_migration_for_org(
    org_id: str, db_url: str, dry_run: bool = False
) -> MigrationResult:
    """
    Run migration for a single organization.

    Args:
        org_id: Organization ID
        db_url: Database connection URL
        dry_run: If True, skip actual migration

    Returns:
        MigrationResult: Result of the migration
    """
    # Skip localhost URLs
    if is_localhost_url(db_url):
        logger.info(f"Skipping localhost database for org {org_id}")
        return MigrationResult(
            org_id=org_id,
            success=True,
            message="Skipped localhost database",
            skipped=True,
        )

    if dry_run:
        return MigrationResult(
            org_id=org_id,
            success=True,
            message="Dry run - would migrate",
            skipped=True,
        )

    try:
        from reflexio.server.services.storage.supabase_storage_utils import (
            execute_migration,
        )

        success, message = execute_migration(db_url)
        if not success:
            logger.error(f"Migration failed - org_id: {org_id}, url: {db_url}")
        return MigrationResult(
            org_id=org_id,
            success=success,
            message=message,
        )
    except Exception as e:
        logger.error(f"Migration exception - org_id: {org_id}, url: {db_url}")
        return MigrationResult(
            org_id=org_id,
            success=False,
            message=f"Exception: {str(e)}",
        )


def run_self_host_migration(dry_run: bool = False) -> list[MigrationResult]:
    """
    Run migration for self-host mode (single organization).

    Args:
        dry_run: If True, skip actual migration

    Returns:
        list[MigrationResult]: Results (single item)
    """
    org_id = "self-host-org"
    logger.info(f"Self-host mode: Processing org '{org_id}'")

    db_url = get_local_config_db_url(org_id)

    if not db_url:
        logger.info(
            "No Supabase db_url configured (using local storage), nothing to migrate"
        )
        return [
            MigrationResult(
                org_id=org_id,
                success=True,
                message="No Supabase db_url configured (local storage mode)",
                skipped=True,
            )
        ]

    result = run_migration_for_org(org_id, db_url, dry_run)
    return [result]


def run_cloud_migrations(
    dry_run: bool = False,
    continue_on_error: bool = False,
    target_org_id: str | None = None,
) -> list[MigrationResult]:
    """
    Run migrations for all organizations in cloud mode.

    Args:
        dry_run: If True, skip actual migrations
        continue_on_error: If True, continue even if some migrations fail
        target_org_id: If set, only migrate this specific org

    Returns:
        list[MigrationResult]: Results for all organizations
    """
    results = []

    organizations = get_all_organizations_with_db_url()

    if not organizations:
        logger.warning("No organizations found with Supabase db_url configured")
        return results

    # Filter to specific org if requested
    if target_org_id:
        # Compare as strings to handle both string and integer org IDs
        organizations = [
            (oid, url) for oid, url in organizations if str(oid) == str(target_org_id)
        ]
        if not organizations:
            logger.error(f"Organization '{target_org_id}' not found or has no db_url")
            return [
                MigrationResult(
                    org_id=target_org_id,
                    success=False,
                    message="Organization not found or has no db_url",
                )
            ]

    logger.info(f"Found {len(organizations)} organizations with Supabase storage")

    for org_id, db_url in organizations:
        logger.info(f"Processing org: {org_id}")

        result = run_migration_for_org(org_id, db_url, dry_run)
        results.append(result)

        if result.success:
            logger.info(f"  ✓ {org_id}: {result.message}")
        else:
            logger.error(f"  ✗ {org_id}: {result.message}")
            if not continue_on_error:
                logger.error(
                    "Stopping due to migration failure (use --continue-on-error to proceed)"
                )
                break

    return results


def print_summary(results: list[MigrationResult]) -> None:
    """Print a summary of migration results."""
    total = len(results)
    successful = sum(1 for r in results if r.success and not r.skipped)
    failed = sum(1 for r in results if not r.success)
    skipped = sum(1 for r in results if r.skipped)

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total organizations: {total}")
    print(f"Successful migrations: {successful}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")

    if failed > 0:
        print("\nFailed organizations:")
        for r in results:
            if not r.success:
                print(f"  - {r.org_id}: {r.message}")

    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run database migrations for all organizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List organizations without running migrations",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue migrating remaining orgs even if some fail",
    )
    parser.add_argument(
        "--org-id",
        help="Migrate only a specific organization",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check if migrations are enabled via RUN_MIGRATION env variable
    run_migration = os.getenv("RUN_MIGRATION", "false").lower() == "true"
    if not run_migration:
        logger.info("RUN_MIGRATION is not set to 'true', skipping migrations")
        return 0

    logger.info("Starting migration runner...")

    self_host_mode = get_self_host_mode()
    logger.info(f"Mode: {'Self-host' if self_host_mode else 'Cloud'}")

    if self_host_mode:
        results = run_self_host_migration(dry_run=args.dry_run)
    else:
        results = run_cloud_migrations(
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            target_org_id=args.org_id,
        )

    print_summary(results)

    # Determine exit code
    # With --continue-on-error, always exit 0 to not block deployment
    # Otherwise, exit 1 if any migration failed
    failed_count = sum(1 for r in results if not r.success)

    if args.continue_on_error:
        if failed_count > 0:
            logger.warning(
                f"{failed_count} migration(s) failed, but continuing (--continue-on-error)"
            )
        return 0
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
