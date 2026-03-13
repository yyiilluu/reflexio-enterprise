"""
Database operations for organization/login data.

Supports three backends:
1. S3 storage (in self-host mode) - when SELF_HOST=true and CONFIG_S3_* vars are set
2. Cloud Supabase (via Supabase Python client) - when LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY are set
3. SQLite (via SQLAlchemy) - fallback for local development
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from reflexio.server.db import db_models
from reflexio.server.db.database import SessionLocal, ensure_sqlite_tables
from reflexio.server.db.login_supabase_client import (
    get_login_supabase_client,
    is_using_login_supabase,
)
from reflexio.server.db.s3_org_storage import (
    get_s3_org_storage,
    is_s3_org_storage_ready,
)

logger = logging.getLogger(__name__)

# Ensure SQLite tables exist (no-op for Supabase/S3 modes)
ensure_sqlite_tables()

# Check if in self-host mode
SELF_HOST_MODE = os.getenv("SELF_HOST", "false").lower() == "true"


def _is_self_host_s3_mode() -> bool:
    """Check if we're in self-host mode with S3 storage."""
    return SELF_HOST_MODE and is_s3_org_storage_ready()


def _supabase_row_to_organization(row: dict) -> db_models.Organization:
    """
    Convert a Supabase row dict to an Organization model instance.

    Args:
        row: Dictionary from Supabase query result

    Returns:
        Organization model instance (detached, not bound to SQLAlchemy session)
    """
    org = db_models.Organization()
    org.id = row.get("id")  # type: ignore[reportAttributeAccessIssue]
    org.created_at = row.get("created_at")  # type: ignore[reportAttributeAccessIssue]
    org.email = row.get("email")  # type: ignore[reportAttributeAccessIssue]
    org.hashed_password = row.get("hashed_password")  # type: ignore[reportAttributeAccessIssue]
    org.is_active = row.get("is_active", True)
    org.is_verified = row.get("is_verified", False)
    org.interaction_count = row.get("interaction_count", 0)
    org.configuration_json = row.get("configuration_json", "")
    org.auth_provider = row.get("auth_provider", "email")
    return org


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(
        "Retrying get_organization_by_email (attempt %s): %s",
        retry_state.attempt_number,
        retry_state.outcome.exception(),  # type: ignore[reportOptionalMemberAccess]
    ),
    reraise=True,
)
def get_organization_by_email(
    session: Session, email: str
) -> db_models.Organization | None:
    """
    Get an organization by email.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        email: Email address

    Returns:
        Organization or None
    """
    # Check S3 storage first (self-host mode)
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.get_organization_by_email(email)

    client = get_login_supabase_client()
    if client:
        response = (
            client.table("organizations").select("*").eq("email", email).execute()
        )
        if response.data:
            return _supabase_row_to_organization(response.data[0])
        return None
    if session is None:
        logger.error("No session available and Supabase client not configured")
        return None
    return (
        session.query(db_models.Organization)
        .filter(db_models.Organization.email == email)
        .first()
    )


def get_organizations(
    session: Session, skip: int = 0, limit: int = 100
) -> list[db_models.Organization]:
    """
    Get a list of organizations with pagination.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of Organization objects
    """
    # Check S3 storage first (self-host mode)
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.get_organizations(skip=skip, limit=limit)

    client = get_login_supabase_client()
    if client:
        response = (
            client.table("organizations")
            .select("*")
            .range(skip, skip + limit - 1)
            .execute()
        )
        return [_supabase_row_to_organization(row) for row in response.data]
    if session is None:
        logger.error("No session available and Supabase client not configured")
        return []
    return session.query(db_models.Organization).offset(skip).limit(limit).all()


def create_organization(
    session: Session, organization: db_models.Organization
) -> db_models.Organization:
    """
    Create a new organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        organization: Organization object to create

    Returns:
        Created Organization object with ID populated
    """
    # Check S3 storage first (self-host mode)
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.create_organization(organization)

    client = get_login_supabase_client()
    if client:
        data = {
            "created_at": organization.created_at
            or int(datetime.now(timezone.utc).timestamp()),
            "email": organization.email,
            "hashed_password": organization.hashed_password,
            "is_active": organization.is_active
            if organization.is_active is not None
            else True,
            "is_verified": organization.is_verified
            if organization.is_verified is not None
            else False,
            "interaction_count": organization.interaction_count
            if organization.interaction_count is not None
            else 0,
            "configuration_json": organization.configuration_json or "",
            "auth_provider": organization.auth_provider or "email",
        }
        response = client.table("organizations").insert(data).execute()
        if response.data:
            return _supabase_row_to_organization(response.data[0])  # type: ignore[reportArgumentType]
        raise Exception("Failed to create organization in Supabase")
    if session is None:
        raise Exception("No session available and Supabase client not configured")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return organization


def update_organization(
    session: Session, organization: db_models.Organization
) -> db_models.Organization:
    """
    Update an existing organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        organization: Organization object with updated fields

    Returns:
        Updated Organization object
    """
    # Check S3 storage first (self-host mode)
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.update_organization(organization)

    client = get_login_supabase_client()
    if client:
        data = {
            "email": organization.email,
            "hashed_password": organization.hashed_password,
            "is_active": organization.is_active,
            "is_verified": organization.is_verified,
            "interaction_count": organization.interaction_count,
            "configuration_json": organization.configuration_json or "",
            "auth_provider": organization.auth_provider or "email",
        }
        response = (
            client.table("organizations")
            .update(data)
            .eq("id", organization.id)
            .execute()
        )
        if response.data:
            return _supabase_row_to_organization(response.data[0])
        raise Exception("Failed to update organization in Supabase")
    if session is None:
        raise Exception("No session available and Supabase client not configured")
    session.commit()
    session.refresh(organization)
    return organization


# Dependency
def get_db_session() -> Generator[Session | None, None, None]:
    """
    FastAPI dependency that yields a database session.

    For Supabase mode, SessionLocal is None, so we yield None.
    The actual database operations check for Supabase client first.
    """
    if SessionLocal is None:
        # Supabase mode - yield None, operations will use Supabase client
        yield None
    else:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()


def _row_to_invitation_code(row: dict) -> db_models.InvitationCode:
    """
    Convert a Supabase row dict to an InvitationCode ORM object.

    Args:
        row: Dictionary from Supabase response

    Returns:
        InvitationCode object
    """
    inv = db_models.InvitationCode()
    inv.id = row.get("id")  # type: ignore[reportAttributeAccessIssue]
    inv.code = row.get("code")  # type: ignore[reportAttributeAccessIssue]
    inv.is_used = row.get("is_used", False)
    inv.used_by_email = row.get("used_by_email")  # type: ignore[reportAttributeAccessIssue]
    inv.used_at = row.get("used_at")  # type: ignore[reportAttributeAccessIssue]
    inv.created_at = row.get("created_at")  # type: ignore[reportAttributeAccessIssue]
    inv.expires_at = row.get("expires_at")  # type: ignore[reportAttributeAccessIssue]
    return inv


def get_invitation_code(session: Session, code: str) -> db_models.InvitationCode | None:
    """
    Look up an invitation code by its code string.

    Args:
        session: SQLAlchemy session (ignored if using Supabase)
        code: The invitation code string

    Returns:
        InvitationCode or None
    """
    client = get_login_supabase_client()
    if client:
        response = (
            client.table("invitation_codes").select("*").eq("code", code).execute()
        )
        if response.data:
            return _row_to_invitation_code(response.data[0])
        return None
    if session is None:
        logger.error("No session available and Supabase client not configured")
        return None
    return (
        session.query(db_models.InvitationCode)
        .filter(db_models.InvitationCode.code == code)
        .first()
    )


def claim_invitation_code(
    session: Session, code: str, email: str
) -> db_models.InvitationCode | None:
    """
    Atomically claim an invitation code — validates it is unused and not expired,
    then marks it as used in a single operation to prevent race conditions.

    Args:
        session: SQLAlchemy session (ignored if using Supabase)
        code: The invitation code string
        email: Email of the user claiming the code

    Returns:
        The claimed InvitationCode if successful, or None if the code was
        already used, expired, or does not exist.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    client = get_login_supabase_client()
    if client:
        # Atomic update: only update if code exists, is unused, and not expired.
        # The expiration filter uses an OR to allow codes with no expiration (NULL).
        response = (
            client.table("invitation_codes")
            .update({"is_used": True, "used_by_email": email, "used_at": now})
            .eq("code", code)
            .eq("is_used", False)
            .or_(f"expires_at.is.null,expires_at.gte.{now}")
            .execute()
        )
        if not response.data:
            return None
        return _row_to_invitation_code(response.data[0])
    if session is None:
        logger.error("No session available and Supabase client not configured")
        return None
    # Use SELECT ... FOR UPDATE to lock the row and prevent concurrent claims
    inv = (
        session.query(db_models.InvitationCode)
        .filter(db_models.InvitationCode.code == code)
        .with_for_update()
        .first()
    )
    if inv is None or inv.is_used:  # type: ignore[reportGeneralTypeIssues]
        return None
    if inv.expires_at and inv.expires_at < now:  # type: ignore[reportGeneralTypeIssues]
        return None
    inv.is_used = True  # type: ignore[reportAttributeAccessIssue]
    inv.used_by_email = email  # type: ignore[reportAttributeAccessIssue]
    inv.used_at = now  # type: ignore[reportAttributeAccessIssue]
    session.flush()
    return inv


def release_invitation_code(session: Session, code: str) -> None:
    """
    Release a previously claimed invitation code, marking it as unused again.

    Used to roll back a claim when a subsequent operation (e.g., registration) fails.

    Args:
        session: SQLAlchemy session (ignored if using Supabase)
        code: The invitation code string to release
    """
    client = get_login_supabase_client()
    if client:
        client.table("invitation_codes").update(
            {"is_used": False, "used_by_email": None, "used_at": None}
        ).eq("code", code).execute()
    else:
        if session is None:
            logger.error("No session available and Supabase client not configured")
            return
        inv = (
            session.query(db_models.InvitationCode)
            .filter(db_models.InvitationCode.code == code)
            .first()
        )
        if inv:
            inv.is_used = False  # type: ignore[reportAttributeAccessIssue]
            inv.used_by_email = None  # type: ignore[reportAttributeAccessIssue]
            inv.used_at = None  # type: ignore[reportAttributeAccessIssue]
            session.flush()


def create_invitation_code(
    session: Session, code: str, expires_at: int | None = None
) -> db_models.InvitationCode:
    """
    Insert a new invitation code into the database.

    Args:
        session: SQLAlchemy session (ignored if using Supabase)
        code: The invitation code string
        expires_at: Optional Unix timestamp for code expiration

    Returns:
        Created InvitationCode object
    """
    created_at = int(datetime.now(timezone.utc).timestamp())
    client = get_login_supabase_client()
    if client:
        data = {
            "code": code,
            "is_used": False,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        response = client.table("invitation_codes").insert(data).execute()
        if response.data:
            return _row_to_invitation_code(response.data[0])  # type: ignore[reportArgumentType]
        raise Exception("Failed to create invitation code in Supabase")
    if session is None:
        raise Exception("No session available and Supabase client not configured")
    inv = db_models.InvitationCode(
        code=code,
        created_at=created_at,
        expires_at=expires_at,
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


def _row_to_api_token(row: dict) -> db_models.ApiToken:
    """
    Convert a Supabase/dict row to an ApiToken model instance.

    Args:
        row: Dictionary from query result

    Returns:
        ApiToken model instance
    """
    token = db_models.ApiToken()
    token.id = row.get("id")  # type: ignore[reportAttributeAccessIssue]
    token.org_id = row.get("org_id")  # type: ignore[reportAttributeAccessIssue]
    token.token = row.get("token")  # type: ignore[reportAttributeAccessIssue]
    token.name = row.get("name", "Default")
    token.created_at = row.get("created_at")  # type: ignore[reportAttributeAccessIssue]
    token.last_used_at = row.get("last_used_at")  # type: ignore[reportAttributeAccessIssue]
    return token


def create_api_token(
    session: Session, org_id: int, token_value: str, name: str = "Default"
) -> db_models.ApiToken:
    """
    Create a new API token for an organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        org_id: Organization ID
        token_value: The token string (rflx-...)
        name: Human-readable name for the token

    Returns:
        Created ApiToken object
    """
    created_at = int(datetime.now(timezone.utc).timestamp())

    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.create_api_token(org_id, token_value, name)

    client = get_login_supabase_client()
    if client:
        data = {
            "org_id": org_id,
            "token": token_value,
            "name": name,
            "created_at": created_at,
        }
        response = client.table("api_tokens").insert(data).execute()
        if response.data:
            return _row_to_api_token(response.data[0])  # type: ignore[reportArgumentType]
        raise Exception("Failed to create API token in Supabase")
    if session is None:
        raise Exception("No session available and Supabase client not configured")
    api_token = db_models.ApiToken(
        org_id=org_id,
        token=token_value,
        name=name,
        created_at=created_at,
    )
    session.add(api_token)
    session.commit()
    session.refresh(api_token)
    return api_token


def get_api_tokens_by_org_id(session: Session, org_id: int) -> list[db_models.ApiToken]:
    """
    Get all API tokens for an organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        org_id: Organization ID

    Returns:
        List of ApiToken objects
    """
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.get_api_tokens_by_org_id(org_id)

    client = get_login_supabase_client()
    if client:
        response = (
            client.table("api_tokens")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at")
            .execute()
        )
        return [_row_to_api_token(row) for row in response.data]
    if session is None:
        return []
    return (
        session.query(db_models.ApiToken)
        .filter(db_models.ApiToken.org_id == org_id)
        .order_by(db_models.ApiToken.created_at)
        .all()
    )


def get_org_by_api_token(
    session: Session, token_value: str
) -> db_models.Organization | None:
    """
    Look up an organization by API token value.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        token_value: The token string to look up

    Returns:
        Organization or None
    """
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.get_org_by_api_token(token_value)

    client = get_login_supabase_client()
    if client:
        response = (
            client.table("api_tokens")
            .select("org_id")
            .eq("token", token_value)
            .execute()
        )
        if not response.data:
            return None
        org_id = response.data[0]["org_id"]
        # Now get the organization
        org_response = (
            client.table("organizations").select("*").eq("id", org_id).execute()
        )
        if org_response.data:
            return _supabase_row_to_organization(org_response.data[0])
        return None
    if session is None:
        return None
    api_token = (
        session.query(db_models.ApiToken)
        .filter(db_models.ApiToken.token == token_value)
        .first()
    )
    if api_token is None:
        return None
    return (
        session.query(db_models.Organization)
        .filter(db_models.Organization.id == api_token.org_id)
        .first()
    )


def delete_api_token(session: Session, token_id: int, org_id: int) -> bool:
    """
    Delete an API token, ensuring it belongs to the given organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        token_id: Token ID to delete
        org_id: Organization ID (for ownership check)

    Returns:
        True if deleted, False if not found
    """
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.delete_api_token(token_id, org_id)

    client = get_login_supabase_client()
    if client:
        response = (
            client.table("api_tokens")
            .delete()
            .eq("id", token_id)
            .eq("org_id", org_id)
            .execute()
        )
        return len(response.data) > 0
    if session is None:
        return False
    result = (
        session.query(db_models.ApiToken)
        .filter(
            db_models.ApiToken.id == token_id,
            db_models.ApiToken.org_id == org_id,
        )
        .first()
    )
    if result is None:
        return False
    session.delete(result)
    session.commit()
    return True


def delete_all_api_tokens_for_org(session: Session, org_id: int) -> int:
    """
    Delete all API tokens for an organization.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        org_id: Organization ID

    Returns:
        int: Number of tokens deleted
    """
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.delete_all_api_tokens_for_org(org_id)

    client = get_login_supabase_client()
    if client:
        response = client.table("api_tokens").delete().eq("org_id", org_id).execute()
        return len(response.data)
    if session is None:
        return 0
    count = (
        session.query(db_models.ApiToken)
        .filter(db_models.ApiToken.org_id == org_id)
        .delete()
    )
    session.commit()
    return count


def delete_organization(session: Session, org_id: int) -> bool:
    """
    Delete an organization record by ID.

    Args:
        session: SQLAlchemy session (ignored if using Supabase or S3)
        org_id: Organization ID to delete

    Returns:
        bool: True if deleted, False if not found
    """
    if _is_self_host_s3_mode():
        s3_storage = get_s3_org_storage()
        return s3_storage.delete_organization(org_id)

    client = get_login_supabase_client()
    if client:
        response = client.table("organizations").delete().eq("id", org_id).execute()
        return len(response.data) > 0
    if session is None:
        return False
    result = (
        session.query(db_models.Organization)
        .filter(db_models.Organization.id == org_id)
        .first()
    )
    if result is None:
        return False
    session.delete(result)
    session.commit()
    return True


def add_db_model(session: Session, db_model: db_models.Base) -> db_models.Base:  # type: ignore[reportInvalidTypeForm]
    """
    Add a generic database model (SQLAlchemy only, for backward compatibility).

    Args:
        session: SQLAlchemy session
        db_model: Model to add

    Returns:
        Added model
    """
    if session is None:
        raise Exception("Cannot add model: no SQLAlchemy session available")
    session.add(db_model)
    session.commit()
    session.refresh(db_model)
    return db_model


@contextmanager
def db_session_context() -> Generator[Session | None, None, None]:
    """
    Context manager for database sessions.

    Yields a SQLAlchemy session that auto-closes on exit, or None if using Supabase.
    """
    if SessionLocal is None:
        # Supabase mode - yield None
        yield None
    else:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()


if __name__ == "__main__":
    if is_using_login_supabase():
        print("Using cloud Supabase for login database")
        # Test with Supabase
        with db_session_context() as s:
            orgs = get_organizations(s, limit=5)  # type: ignore[reportArgumentType]
            for org in orgs:
                print(f"  - {org.email}")
    else:
        print("Using local SQLite for login database")
        if SessionLocal is not None:
            with SessionLocal() as s:
                org = s.query(db_models.Organization).first()
                if org:
                    print(f"First org: {org.email}")
        else:
            print("No SessionLocal available")
