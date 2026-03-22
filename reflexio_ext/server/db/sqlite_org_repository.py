"""SQLite (SQLAlchemy) adapter for the OrgRepository port.

Implements organization, API token, and invitation code storage using a local
SQLite database via SQLAlchemy ORM.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from reflexio_ext.server.db import db_models

logger = logging.getLogger(__name__)


class SQLiteOrgRepository:
    """SQLite-backed organization repository.

    Args:
        session_factory: A SQLAlchemy ``sessionmaker`` bound to an engine.
            Pass ``None`` only when the SQLite backend is not configured.
        session: An optional pre-existing session to use instead of creating
            new sessions from the factory.  Used for backward compatibility
            with code that passes sessions from FastAPI ``Depends()``.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None,
        session: Session | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._session = session

    def _get_session(self) -> Session:
        """Return the pre-existing session or create one from the factory.

        Returns:
            Session: An active SQLAlchemy session.

        Raises:
            RuntimeError: If neither a session nor a factory was provided.
        """
        if self._session is not None:
            return self._session
        if self._session_factory is None:
            raise RuntimeError(
                "SQLiteOrgRepository requires a sessionmaker or session but neither was provided"
            )
        return self._session_factory()

    # ------------------------------------------------------------------
    # Organization CRUD
    # ------------------------------------------------------------------

    def get_organization_by_email(self, email: str) -> db_models.Organization | None:
        """Look up an organization by email address.

        Args:
            email (str): Email address to search for.

        Returns:
            db_models.Organization | None: Organization if found, None otherwise.
        """
        session = self._get_session()
        return (
            session.query(db_models.Organization)
            .filter(db_models.Organization.email == email)
            .first()
        )

    def get_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> list[db_models.Organization]:
        """Get a paginated list of organizations.

        Args:
            skip (int): Number of records to skip.
            limit (int): Maximum number of records to return.

        Returns:
            list[db_models.Organization]: List of Organization objects.
        """
        session = self._get_session()
        return session.query(db_models.Organization).offset(skip).limit(limit).all()

    def create_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Create a new organization.

        Args:
            organization (db_models.Organization): Organization object to create.

        Returns:
            db_models.Organization: Created Organization with ID populated.
        """
        session = self._get_session()
        session.add(organization)
        session.commit()
        session.refresh(organization)
        return organization

    def update_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Update an existing organization.

        Args:
            organization (db_models.Organization): Organization object with updated fields.

        Returns:
            db_models.Organization: Updated Organization object.
        """
        session = self._get_session()
        session.commit()
        session.refresh(organization)
        return organization

    def delete_organization(self, org_id: int) -> bool:
        """Delete an organization by ID.

        Args:
            org_id (int): Organization ID to delete.

        Returns:
            bool: True if deleted, False if not found.
        """
        session = self._get_session()
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

    # ------------------------------------------------------------------
    # API Token operations
    # ------------------------------------------------------------------

    def create_api_token(
        self, org_id: int, token_value: str, name: str = "Default"
    ) -> db_models.ApiToken:
        """Create a new API token for an organization.

        Args:
            org_id (int): Organization ID.
            token_value (str): The token string (e.g. rflx-...).
            name (str): Human-readable name for the token.

        Returns:
            db_models.ApiToken: Created ApiToken object.
        """
        session = self._get_session()
        created_at = int(datetime.now(UTC).timestamp())
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

    def get_api_tokens_by_org_id(self, org_id: int) -> list[db_models.ApiToken]:
        """Get all API tokens for an organization.

        Args:
            org_id (int): Organization ID.

        Returns:
            list[db_models.ApiToken]: List of ApiToken objects ordered by creation time.
        """
        session = self._get_session()
        return (
            session.query(db_models.ApiToken)
            .filter(db_models.ApiToken.org_id == org_id)
            .order_by(db_models.ApiToken.created_at)
            .all()
        )

    def get_org_by_api_token(self, token_value: str) -> db_models.Organization | None:
        """Look up an organization by API token value.

        Args:
            token_value (str): The token string to look up.

        Returns:
            db_models.Organization | None: Organization if found, None otherwise.
        """
        session = self._get_session()
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

    def delete_api_token(self, token_id: int, org_id: int) -> bool:
        """Delete an API token, ensuring it belongs to the given organization.

        Args:
            token_id (int): Token ID to delete.
            org_id (int): Organization ID (ownership check).

        Returns:
            bool: True if deleted, False if not found.
        """
        session = self._get_session()
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

    def delete_all_api_tokens_for_org(self, org_id: int) -> int:
        """Delete all API tokens for an organization.

        Args:
            org_id (int): Organization ID.

        Returns:
            int: Number of tokens deleted.
        """
        session = self._get_session()
        count = (
            session.query(db_models.ApiToken)
            .filter(db_models.ApiToken.org_id == org_id)
            .delete()
        )
        session.commit()
        return count

    # ------------------------------------------------------------------
    # Invitation Code operations
    # ------------------------------------------------------------------

    def get_invitation_code(self, code: str) -> db_models.InvitationCode | None:
        """Look up an invitation code.

        Args:
            code (str): The invitation code string.

        Returns:
            db_models.InvitationCode | None: InvitationCode if found, None otherwise.
        """
        session = self._get_session()
        return (
            session.query(db_models.InvitationCode)
            .filter(db_models.InvitationCode.code == code)
            .first()
        )

    def claim_invitation_code(
        self, code: str, email: str
    ) -> db_models.InvitationCode | None:
        """Atomically claim an invitation code.

        Validates that the code is unused and not expired, then marks it as used.
        Uses SELECT ... FOR UPDATE to prevent concurrent claims.

        Args:
            code (str): The invitation code string.
            email (str): Email of the user claiming the code.

        Returns:
            db_models.InvitationCode | None: The claimed InvitationCode if successful,
                None if the code was already used, expired, or does not exist.
        """
        session = self._get_session()
        now = int(datetime.now(UTC).timestamp())
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

    def release_invitation_code(self, code: str) -> None:
        """Release a previously claimed invitation code.

        Used to roll back a claim when a subsequent operation fails.

        Args:
            code (str): The invitation code string to release.
        """
        session = self._get_session()
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
        self, code: str, expires_at: int | None = None
    ) -> db_models.InvitationCode:
        """Create a new invitation code.

        Args:
            code (str): The invitation code string.
            expires_at (int | None): Optional Unix timestamp for expiration.

        Returns:
            db_models.InvitationCode: Created InvitationCode object.
        """
        session = self._get_session()
        created_at = int(datetime.now(UTC).timestamp())
        inv = db_models.InvitationCode(
            code=code,
            created_at=created_at,
            expires_at=expires_at,
        )
        session.add(inv)
        session.commit()
        session.refresh(inv)
        return inv
