"""
This script is used to reset the password for an organization.
It is only available for test environment.

Usage:
python reset_password_script.py --email <email> --password <password>
"""

import argparse

from sqlalchemy.orm import Session

from reflexio.server.api_endpoints.login import get_password_hash
from reflexio.server.db.db_operations import get_db_session, get_organization_by_email


def reset_password(org_email: str, new_password: str, session: Session) -> bool:
    """Reset password for an organization.

    Args:
        org_email: Email of the organization
        new_password: New password to set
        session: Database session

    Returns:
        bool: True if password was reset successfully, False otherwise
    """
    # Get the organization
    org = get_organization_by_email(session=session, email=org_email)
    if not org:
        print(f"Organization with email {org_email} not found")
        return False

    try:
        # Hash the new password
        hashed_password = get_password_hash(new_password)

        # Update the password
        org.hashed_password = hashed_password
        session.commit()
        print(f"Successfully reset password for organization: {org_email}")
        return True
    except Exception as e:
        print(f"Error resetting password: {e}")
        session.rollback()
        return False


def main():
    parser = argparse.ArgumentParser(description="Reset password for an organization")
    parser.add_argument("--email", required=True, help="Organization email")
    parser.add_argument("--password", required=True, help="New password")

    args = parser.parse_args()

    # Get database session
    session = next(get_db_session())

    # Reset the password
    success = reset_password(args.email, args.password, session)

    if not success:
        exit(1)


if __name__ == "__main__":
    main()
