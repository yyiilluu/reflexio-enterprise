"""S3 organization repository adapter for self-host mode.

Wraps :class:`S3OrganizationStorage` to satisfy the :class:`OrgRepository`
protocol.  All organization and API-token operations delegate directly to the
underlying storage; invitation-code operations raise ``NotImplementedError``
because invitation codes are not used in S3 self-host deployments.
"""

from __future__ import annotations

from reflexio_ext.server.db import db_models
from reflexio_ext.server.db.s3_org_storage import S3OrganizationStorage

_INVITATION_CODE_MSG = "Invitation codes are not supported in S3 self-host mode"


class S3OrgRepository:
    """OrgRepository adapter backed by S3OrganizationStorage.

    This is a thin delegation wrapper -- it forwards every org / API-token
    call to the storage instance and raises ``NotImplementedError`` for
    invitation-code methods that do not apply in self-host mode.

    Args:
        storage (S3OrganizationStorage): The underlying S3 storage instance.
    """

    def __init__(self, storage: S3OrganizationStorage) -> None:
        self._storage = storage

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
        return self._storage.get_organization_by_email(email)

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
        return self._storage.get_organizations(skip=skip, limit=limit)

    def create_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Create a new organization.

        Args:
            organization (db_models.Organization): Organization object to create.

        Returns:
            db_models.Organization: Created Organization with ID populated.
        """
        return self._storage.create_organization(organization)

    def update_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Update an existing organization.

        Args:
            organization (db_models.Organization): Organization object with updated fields.

        Returns:
            db_models.Organization: Updated Organization object.
        """
        return self._storage.update_organization(organization)

    def delete_organization(self, org_id: int) -> bool:
        """Delete an organization by ID.

        Args:
            org_id (int): Organization ID to delete.

        Returns:
            bool: True if deleted, False if not found.
        """
        return self._storage.delete_organization(org_id)

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
        return self._storage.create_api_token(org_id, token_value, name)

    def get_api_tokens_by_org_id(self, org_id: int) -> list[db_models.ApiToken]:
        """Get all API tokens for an organization.

        Args:
            org_id (int): Organization ID.

        Returns:
            list[db_models.ApiToken]: List of ApiToken objects.
        """
        return self._storage.get_api_tokens_by_org_id(org_id)

    def get_org_by_api_token(self, token_value: str) -> db_models.Organization | None:
        """Look up an organization by API token value.

        Args:
            token_value (str): The token string to look up.

        Returns:
            db_models.Organization | None: Organization if found, None otherwise.
        """
        return self._storage.get_org_by_api_token(token_value)

    def delete_api_token(self, token_id: int, org_id: int) -> bool:
        """Delete an API token, ensuring it belongs to the given organization.

        Args:
            token_id (int): Token ID to delete.
            org_id (int): Organization ID (ownership check).

        Returns:
            bool: True if deleted, False if not found.
        """
        return self._storage.delete_api_token(token_id, org_id)

    def delete_all_api_tokens_for_org(self, org_id: int) -> int:
        """Delete all API tokens for an organization.

        Args:
            org_id (int): Organization ID.

        Returns:
            int: Number of tokens deleted.
        """
        return self._storage.delete_all_api_tokens_for_org(org_id)

    # ------------------------------------------------------------------
    # Invitation Code operations (not supported in self-host mode)
    # ------------------------------------------------------------------

    def get_invitation_code(self, code: str) -> db_models.InvitationCode | None:
        """Not supported in S3 self-host mode.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(_INVITATION_CODE_MSG)

    def claim_invitation_code(
        self, code: str, email: str
    ) -> db_models.InvitationCode | None:
        """Not supported in S3 self-host mode.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(_INVITATION_CODE_MSG)

    def release_invitation_code(self, code: str) -> None:
        """Not supported in S3 self-host mode.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(_INVITATION_CODE_MSG)

    def create_invitation_code(
        self, code: str, expires_at: int | None = None
    ) -> db_models.InvitationCode:
        """Not supported in S3 self-host mode.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(_INVITATION_CODE_MSG)
