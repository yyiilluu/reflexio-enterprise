"""
CLI script to generate and manage invitation codes.

Usage:
    python -m reflexio.server.scripts.manage_invitation_codes generate --count 5
    python -m reflexio.server.scripts.manage_invitation_codes generate --count 3 --expires-in-days 30
    python -m reflexio.server.scripts.manage_invitation_codes list
"""

import argparse
import secrets
import string
from datetime import datetime, timezone

from reflexio.server.db.database import Base, engine
from reflexio.server.db.db_operations import (
    create_invitation_code,
    db_session_context,
    get_login_supabase_client,
)


def _ensure_tables() -> None:
    """Create tables in local SQLite if they don't exist yet."""
    if engine is not None:
        Base.metadata.create_all(bind=engine)


def _generate_code() -> str:
    """
    Generate a random invitation code in REFLEXIO-XXXX-XXXX format.

    Returns:
        str: A unique invitation code
    """
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"REFLEXIO-{part1}-{part2}"


def generate_codes(count: int, expires_in_days: int | None = None) -> list[str]:
    """
    Generate and insert invitation codes into the database.

    Args:
        count: Number of codes to generate
        expires_in_days: Optional number of days until codes expire

    Returns:
        List of generated code strings
    """
    expires_at = None
    if expires_in_days is not None:
        expires_at = int(datetime.now(timezone.utc).timestamp()) + (
            expires_in_days * 86400
        )

    codes = []
    with db_session_context() as session:
        for _ in range(count):
            code = _generate_code()
            create_invitation_code(session=session, code=code, expires_at=expires_at)  # type: ignore[reportArgumentType]
            codes.append(code)

    return codes


def list_codes(show_used: bool = False) -> None:
    """
    List invitation codes from the database.

    Args:
        show_used: If True, include used codes in the output
    """
    client = get_login_supabase_client()
    if client:
        query = (
            client.table("invitation_codes").select("*").order("created_at", desc=True)
        )
        if not show_used:
            query = query.eq("is_used", False)
        response = query.execute()
        rows = response.data
    else:
        from reflexio.server.db.database import SessionLocal
        from reflexio.server.db.db_models import InvitationCode

        if SessionLocal is None:
            print("No database available")
            return
        session = SessionLocal()
        try:
            query = session.query(InvitationCode)
            if not show_used:
                query = query.filter(InvitationCode.is_used == False)  # noqa: E712
            query = query.order_by(InvitationCode.created_at.desc())
            rows = [
                {
                    "code": inv.code,
                    "is_used": inv.is_used,
                    "used_by_email": inv.used_by_email,
                    "created_at": inv.created_at,
                    "expires_at": inv.expires_at,
                }
                for inv in query.all()
            ]
        finally:
            session.close()

    if not rows:
        print("No invitation codes found.")
        return

    print(f"{'Code':<25} {'Used':<8} {'Used By':<30} {'Expires'}")
    print("-" * 90)
    for row in rows:
        code = row.get("code", row.get("code"))
        is_used = row.get("is_used", False)
        used_by = row.get("used_by_email") or ""
        expires_at = row.get("expires_at")
        expires_str = (
            datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M"
            )
            if expires_at
            else "Never"
        )
        print(f"{code:<25} {'Yes' if is_used else 'No':<8} {used_by:<30} {expires_str}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage invitation codes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate invitation codes")
    gen_parser.add_argument(
        "--count", type=int, default=1, help="Number of codes to generate"
    )
    gen_parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="Number of days until codes expire",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List invitation codes")
    list_parser.add_argument(
        "--show-used", action="store_true", help="Include used codes"
    )

    args = parser.parse_args()
    _ensure_tables()

    if args.command == "generate":
        codes = generate_codes(count=args.count, expires_in_days=args.expires_in_days)
        print(f"Generated {len(codes)} invitation code(s):")
        for code in codes:
            print(f"  {code}")

    elif args.command == "list":
        list_codes(show_used=args.show_used)


if __name__ == "__main__":
    main()
