"""
Organization repository port (interface) for the Ports & Adapters pattern.

Defines the contract that all organization storage backends must implement.
Concrete adapters (SQLite, Supabase, S3) live alongside this file.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reflexio_ext.server.db import db_models


@runtime_checkable
class OrgRepository(Protocol):
    """Port for organization data access.

    Each adapter manages its own connection/client internally.
    Callers never pass a session or client — the adapter owns that concern.
    """

    # ------------------------------------------------------------------
    # Organization CRUD
    # ------------------------------------------------------------------

    def get_organization_by_email(self, email: str) -> db_models.Organization | None:
        """Look up an organization by email address.

        Args:
            email: Email address to search for

        Returns:
            Organization if found, None otherwise
        """
        ...

    def get_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> list[db_models.Organization]:
        """Get a paginated list of organizations.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Organization objects
        """
        ...

    def create_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Create a new organization.

        Args:
            organization: Organization object to create

        Returns:
            Created Organization with ID populated
        """
        ...

    def update_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Update an existing organization.

        Args:
            organization: Organization object with updated fields

        Returns:
            Updated Organization object
        """
        ...

    def delete_organization(self, org_id: int) -> bool:
        """Delete an organization by ID.

        Args:
            org_id: Organization ID to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    # ------------------------------------------------------------------
    # API Token operations
    # ------------------------------------------------------------------

    def create_api_token(
        self, org_id: int, token_value: str, name: str = "Default"
    ) -> db_models.ApiToken:
        """Create a new API token for an organization.

        Args:
            org_id: Organization ID
            token_value: The token string (e.g. rflx-...)
            name: Human-readable name for the token

        Returns:
            Created ApiToken object
        """
        ...

    def get_api_tokens_by_org_id(self, org_id: int) -> list[db_models.ApiToken]:
        """Get all API tokens for an organization.

        Args:
            org_id: Organization ID

        Returns:
            List of ApiToken objects
        """
        ...

    def get_org_by_api_token(self, token_value: str) -> db_models.Organization | None:
        """Look up an organization by API token value.

        Args:
            token_value: The token string to look up

        Returns:
            Organization if found, None otherwise
        """
        ...

    def delete_api_token(self, token_id: int, org_id: int) -> bool:
        """Delete an API token, ensuring it belongs to the given organization.

        Args:
            token_id: Token ID to delete
            org_id: Organization ID (ownership check)

        Returns:
            True if deleted, False if not found
        """
        ...

    def delete_all_api_tokens_for_org(self, org_id: int) -> int:
        """Delete all API tokens for an organization.

        Args:
            org_id: Organization ID

        Returns:
            Number of tokens deleted
        """
        ...

    # ------------------------------------------------------------------
    # Invitation Code operations
    # ------------------------------------------------------------------

    def get_invitation_code(self, code: str) -> db_models.InvitationCode | None:
        """Look up an invitation code.

        Args:
            code: The invitation code string

        Returns:
            InvitationCode if found, None otherwise
        """
        ...

    def claim_invitation_code(
        self, code: str, email: str
    ) -> db_models.InvitationCode | None:
        """Atomically claim an invitation code.

        Validates that the code is unused and not expired, then marks it as used.

        Args:
            code: The invitation code string
            email: Email of the user claiming the code

        Returns:
            The claimed InvitationCode if successful, None otherwise
        """
        ...

    def release_invitation_code(self, code: str) -> None:
        """Release a previously claimed invitation code.

        Used to roll back a claim when a subsequent operation fails.

        Args:
            code: The invitation code string to release
        """
        ...

    def create_invitation_code(
        self, code: str, expires_at: int | None = None
    ) -> db_models.InvitationCode:
        """Create a new invitation code.

        Args:
            code: The invitation code string
            expires_at: Optional Unix timestamp for expiration

        Returns:
            Created InvitationCode object
        """
        ...
