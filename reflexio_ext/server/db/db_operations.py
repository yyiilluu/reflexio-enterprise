"""
Database operations for organization/login data.

Uses the Ports & Adapters pattern: a factory function selects the appropriate
OrgRepository adapter based on environment configuration. All public functions
delegate to the repository instance.

Supports three backends:
1. S3 storage (in self-host mode) - when SELF_HOST=true and CONFIG_S3_* vars are set
2. Cloud Supabase (via Supabase Python client) - when LOGIN_SUPABASE_URL and LOGIN_SUPABASE_KEY are set
3. SQLite (via SQLAlchemy) - fallback for local development
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from postgrest import APIResponse
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from reflexio_ext.server.db import db_models
from reflexio_ext.server.db.database import SessionLocal, ensure_sqlite_tables
from reflexio_ext.server.db.login_supabase_client import (
    get_login_supabase_client,
    is_using_login_supabase,
)
from reflexio_ext.server.db.org_repository import OrgRepository
from reflexio_ext.server.db.s3_org_storage import (
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


# ---------------------------------------------------------------------------
# Repository factory
# ---------------------------------------------------------------------------


def create_org_repository(
    session: Session | None = None,
) -> OrgRepository:
    """Create the appropriate OrgRepository adapter based on environment.

    Selection priority:
    1. S3 (self-host mode with S3 config)
    2. Supabase (cloud login database)
    3. SQLite (local fallback)

    Args:
        session: Optional pre-existing SQLAlchemy session for the SQLite adapter.
            Passed through from the backward-compatible wrapper functions.

    Returns:
        OrgRepository: The configured repository adapter
    """
    if _is_self_host_s3_mode():
        from reflexio_ext.server.db.s3_org_repository import S3OrgRepository

        return S3OrgRepository(storage=get_s3_org_storage())

    client = get_login_supabase_client()
    if client:
        from reflexio_ext.server.db.supabase_org_repository import (
            SupabaseOrgRepository,
        )

        return SupabaseOrgRepository(client=client)

    from reflexio_ext.server.db.sqlite_org_repository import SQLiteOrgRepository

    return SQLiteOrgRepository(session_factory=SessionLocal, session=session)


def _get_repo(session: Session | None = None) -> OrgRepository:
    """Create an OrgRepository for the current environment.

    Not cached — the factory checks env vars on each call so that tests
    can patch ``_is_self_host_s3_mode`` and ``get_login_supabase_client``
    between test cases (matching the old per-call backend selection).

    Args:
        session: Optional pre-existing SQLAlchemy session for backward compat.
    """
    return create_org_repository(session=session)


# ---------------------------------------------------------------------------
# Backward-compatible public functions
#
# These keep the same (session, ...) signatures so that existing callers
# (login.py, oauth.py, manage_invitation_codes.py, tests) continue to work
# without changes.  The session parameter is ignored — the repository owns
# its own connection.
# ---------------------------------------------------------------------------


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
    """Get an organization by email.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        email: Email address

    Returns:
        Organization or None
    """
    return _get_repo(session).get_organization_by_email(email)


def get_organizations(
    session: Session, skip: int = 0, limit: int = 100
) -> list[db_models.Organization]:
    """Get a list of organizations with pagination.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of Organization objects
    """
    return _get_repo(session).get_organizations(skip=skip, limit=limit)


def create_organization(
    session: Session, organization: db_models.Organization
) -> db_models.Organization:
    """Create a new organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        organization: Organization object to create

    Returns:
        Created Organization object with ID populated
    """
    return _get_repo(session).create_organization(organization)


def update_organization(
    session: Session, organization: db_models.Organization
) -> db_models.Organization:
    """Update an existing organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        organization: Organization object with updated fields

    Returns:
        Updated Organization object
    """
    return _get_repo(session).update_organization(organization)


def delete_organization(session: Session, org_id: int) -> bool:
    """Delete an organization record by ID.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        org_id: Organization ID to delete

    Returns:
        bool: True if deleted, False if not found
    """
    return _get_repo(session).delete_organization(org_id)


# ---------------------------------------------------------------------------
# API Token operations
# ---------------------------------------------------------------------------


def create_api_token(
    session: Session, org_id: int, token_value: str, name: str = "Default"
) -> db_models.ApiToken:
    """Create a new API token for an organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        org_id: Organization ID
        token_value: The token string (rflx-...)
        name: Human-readable name for the token

    Returns:
        Created ApiToken object
    """
    return _get_repo(session).create_api_token(org_id, token_value, name)


def get_api_tokens_by_org_id(session: Session, org_id: int) -> list[db_models.ApiToken]:
    """Get all API tokens for an organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        org_id: Organization ID

    Returns:
        List of ApiToken objects
    """
    return _get_repo(session).get_api_tokens_by_org_id(org_id)


def get_org_by_api_token(
    session: Session, token_value: str
) -> db_models.Organization | None:
    """Look up an organization by API token value.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        token_value: The token string to look up

    Returns:
        Organization or None
    """
    return _get_repo(session).get_org_by_api_token(token_value)


def delete_api_token(session: Session, token_id: int, org_id: int) -> bool:
    """Delete an API token, ensuring it belongs to the given organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        token_id: Token ID to delete
        org_id: Organization ID (for ownership check)

    Returns:
        True if deleted, False if not found
    """
    return _get_repo(session).delete_api_token(token_id, org_id)


def delete_all_api_tokens_for_org(session: Session, org_id: int) -> int:
    """Delete all API tokens for an organization.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        org_id: Organization ID

    Returns:
        int: Number of tokens deleted
    """
    return _get_repo(session).delete_all_api_tokens_for_org(org_id)


# ---------------------------------------------------------------------------
# Invitation Code operations
# ---------------------------------------------------------------------------


def get_invitation_code(session: Session, code: str) -> db_models.InvitationCode | None:
    """Look up an invitation code by its code string.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        code: The invitation code string

    Returns:
        InvitationCode or None
    """
    return _get_repo(session).get_invitation_code(code)


def claim_invitation_code(
    session: Session, code: str, email: str
) -> db_models.InvitationCode | None:
    """Atomically claim an invitation code.

    Validates it is unused and not expired, then marks it as used.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        code: The invitation code string
        email: Email of the user claiming the code

    Returns:
        The claimed InvitationCode if successful, None otherwise
    """
    return _get_repo(session).claim_invitation_code(code, email)


def release_invitation_code(session: Session, code: str) -> None:
    """Release a previously claimed invitation code.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        code: The invitation code string to release
    """
    _get_repo(session).release_invitation_code(code)


def create_invitation_code(
    session: Session, code: str, expires_at: int | None = None
) -> db_models.InvitationCode:
    """Insert a new invitation code into the database.

    Args:
        session: SQLAlchemy session (ignored — kept for backward compatibility)
        code: The invitation code string
        expires_at: Optional Unix timestamp for code expiration

    Returns:
        Created InvitationCode object
    """
    return _get_repo(session).create_invitation_code(code, expires_at)


# ---------------------------------------------------------------------------
# Session management (not part of the repository pattern)
# ---------------------------------------------------------------------------


def get_db_session() -> Generator[Session | None]:
    """FastAPI dependency that yields a database session.

    For Supabase mode, SessionLocal is None, so we yield None.
    """
    if SessionLocal is None:
        yield None
    else:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()


@contextmanager
def db_session_context() -> Generator[Session | None]:
    """Context manager for database sessions.

    Yields a SQLAlchemy session that auto-closes on exit, or None if using Supabase.
    """
    if SessionLocal is None:
        yield None
    else:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()


def add_db_model(session: Session, db_model: db_models.Base) -> db_models.Base:  # type: ignore[reportInvalidTypeForm]
    """Add a generic database model (SQLAlchemy only, for backward compatibility).

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


# ---------------------------------------------------------------------------
# Internal helpers re-exported for backward compatibility (used by tests)
# ---------------------------------------------------------------------------


def _rows(response: APIResponse) -> list[dict[str, Any]]:
    """Narrow postgrest's List[JSON] to the list[dict] that table queries actually return."""
    return cast(list[dict[str, Any]], response.data)


def _supabase_row_to_organization(row: dict) -> db_models.Organization:
    """Convert a Supabase row dict to an Organization model instance.

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


def _row_to_invitation_code(row: dict) -> db_models.InvitationCode:
    """Convert a Supabase row dict to an InvitationCode ORM object.

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


def _row_to_api_token(row: dict) -> db_models.ApiToken:
    """Convert a Supabase/dict row to an ApiToken model instance.

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


if __name__ == "__main__":
    repo = _get_repo()
    if is_using_login_supabase():
        print("Using cloud Supabase for login database")
        orgs = repo.get_organizations(limit=5)
        for org in orgs:
            print(f"  - {org.email}")
    else:
        print("Using local SQLite for login database")
        orgs = repo.get_organizations(limit=5)
        for org in orgs:
            print(f"  - {org.email}")
