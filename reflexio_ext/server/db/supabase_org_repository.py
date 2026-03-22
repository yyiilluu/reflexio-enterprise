"""
Supabase adapter for the OrgRepository port.

Implements organization, API-token, and invitation-code persistence
using the Supabase PostgREST API via the official Python client.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from postgrest import APIResponse

from reflexio_ext.server.db import db_models
from supabase import Client

logger = logging.getLogger(__name__)


def _rows(response: APIResponse) -> list[dict[str, Any]]:
    """Narrow PostgREST's response data to the list[dict] that table queries return.

    Args:
        response (APIResponse): Raw PostgREST API response

    Returns:
        list[dict[str, Any]]: List of row dictionaries
    """
    return cast(list[dict[str, Any]], response.data)


class SupabaseOrgRepository:
    """Supabase-backed adapter for organization data access.

    Uses the PostgREST API exposed by ``supabase.Client.table()`` for all
    CRUD operations on organizations, API tokens, and invitation codes.

    Args:
        client (Client): An initialised Supabase client instance
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Row-to-model helpers (private)
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_organization(row: dict[str, Any]) -> db_models.Organization:
        """Convert a Supabase row dict to an Organization model instance.

        Args:
            row (dict[str, Any]): Dictionary from Supabase query result

        Returns:
            db_models.Organization: Detached Organization model instance
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

    @staticmethod
    def _row_to_invitation_code(row: dict[str, Any]) -> db_models.InvitationCode:
        """Convert a Supabase row dict to an InvitationCode model instance.

        Args:
            row (dict[str, Any]): Dictionary from Supabase query result

        Returns:
            db_models.InvitationCode: Detached InvitationCode model instance
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

    @staticmethod
    def _row_to_api_token(row: dict[str, Any]) -> db_models.ApiToken:
        """Convert a Supabase row dict to an ApiToken model instance.

        Args:
            row (dict[str, Any]): Dictionary from Supabase query result

        Returns:
            db_models.ApiToken: Detached ApiToken model instance
        """
        token = db_models.ApiToken()
        token.id = row.get("id")  # type: ignore[reportAttributeAccessIssue]
        token.org_id = row.get("org_id")  # type: ignore[reportAttributeAccessIssue]
        token.token = row.get("token")  # type: ignore[reportAttributeAccessIssue]
        token.name = row.get("name", "Default")
        token.created_at = row.get("created_at")  # type: ignore[reportAttributeAccessIssue]
        token.last_used_at = row.get("last_used_at")  # type: ignore[reportAttributeAccessIssue]
        return token

    # ------------------------------------------------------------------
    # Organization CRUD
    # ------------------------------------------------------------------

    def get_organization_by_email(self, email: str) -> db_models.Organization | None:
        """Look up an organization by email address.

        Args:
            email (str): Email address to search for

        Returns:
            db_models.Organization | None: Organization if found, None otherwise
        """
        response = (
            self._client.table("organizations").select("*").eq("email", email).execute()
        )
        if rows := _rows(response):
            return self._row_to_organization(rows[0])
        return None

    def get_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> list[db_models.Organization]:
        """Get a paginated list of organizations.

        Args:
            skip (int): Number of records to skip
            limit (int): Maximum number of records to return

        Returns:
            list[db_models.Organization]: List of Organization objects
        """
        response = (
            self._client.table("organizations")
            .select("*")
            .range(skip, skip + limit - 1)
            .execute()
        )
        return [self._row_to_organization(row) for row in _rows(response)]

    def create_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Create a new organization.

        Args:
            organization (db_models.Organization): Organization object to create

        Returns:
            db_models.Organization: Created Organization with ID populated

        Raises:
            Exception: If the Supabase insert fails to return a row
        """
        data = {
            "created_at": organization.created_at or int(datetime.now(UTC).timestamp()),
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
        response = self._client.table("organizations").insert(data).execute()
        if rows := _rows(response):
            return self._row_to_organization(rows[0])
        raise Exception("Failed to create organization in Supabase")

    def update_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """Update an existing organization.

        Args:
            organization (db_models.Organization): Organization object with updated fields

        Returns:
            db_models.Organization: Updated Organization object

        Raises:
            Exception: If the Supabase update fails to return a row
        """
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
            self._client.table("organizations")
            .update(data)
            .eq("id", organization.id)
            .execute()
        )
        if rows := _rows(response):
            return self._row_to_organization(rows[0])
        raise Exception("Failed to update organization in Supabase")

    def delete_organization(self, org_id: int) -> bool:
        """Delete an organization by ID.

        Args:
            org_id (int): Organization ID to delete

        Returns:
            bool: True if deleted, False if not found
        """
        response = (
            self._client.table("organizations").delete().eq("id", org_id).execute()
        )
        return bool(_rows(response))

    # ------------------------------------------------------------------
    # API Token operations
    # ------------------------------------------------------------------

    def create_api_token(
        self, org_id: int, token_value: str, name: str = "Default"
    ) -> db_models.ApiToken:
        """Create a new API token for an organization.

        Args:
            org_id (int): Organization ID
            token_value (str): The token string (e.g. rflx-...)
            name (str): Human-readable name for the token

        Returns:
            db_models.ApiToken: Created ApiToken object

        Raises:
            Exception: If the Supabase insert fails to return a row
        """
        created_at = int(datetime.now(UTC).timestamp())
        data = {
            "org_id": org_id,
            "token": token_value,
            "name": name,
            "created_at": created_at,
        }
        response = self._client.table("api_tokens").insert(data).execute()
        if rows := _rows(response):
            return self._row_to_api_token(rows[0])
        raise Exception("Failed to create API token in Supabase")

    def get_api_tokens_by_org_id(self, org_id: int) -> list[db_models.ApiToken]:
        """Get all API tokens for an organization.

        Args:
            org_id (int): Organization ID

        Returns:
            list[db_models.ApiToken]: List of ApiToken objects ordered by creation time
        """
        response = (
            self._client.table("api_tokens")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at")
            .execute()
        )
        return [self._row_to_api_token(row) for row in _rows(response)]

    def get_org_by_api_token(self, token_value: str) -> db_models.Organization | None:
        """Look up an organization by API token value.

        Args:
            token_value (str): The token string to look up

        Returns:
            db_models.Organization | None: Organization if found, None otherwise
        """
        response = (
            self._client.table("api_tokens")
            .select("org_id")
            .eq("token", token_value)
            .execute()
        )
        rows = _rows(response)
        if not rows:
            return None

        org_id = rows[0]["org_id"]
        org_response = (
            self._client.table("organizations").select("*").eq("id", org_id).execute()
        )
        if org_rows := _rows(org_response):
            return self._row_to_organization(org_rows[0])
        return None

    def delete_api_token(self, token_id: int, org_id: int) -> bool:
        """Delete an API token, ensuring it belongs to the given organization.

        Args:
            token_id (int): Token ID to delete
            org_id (int): Organization ID (ownership check)

        Returns:
            bool: True if deleted, False if not found
        """
        response = (
            self._client.table("api_tokens")
            .delete()
            .eq("id", token_id)
            .eq("org_id", org_id)
            .execute()
        )
        return bool(_rows(response))

    def delete_all_api_tokens_for_org(self, org_id: int) -> int:
        """Delete all API tokens for an organization.

        Args:
            org_id (int): Organization ID

        Returns:
            int: Number of tokens deleted
        """
        response = (
            self._client.table("api_tokens").delete().eq("org_id", org_id).execute()
        )
        return len(_rows(response))

    # ------------------------------------------------------------------
    # Invitation Code operations
    # ------------------------------------------------------------------

    def get_invitation_code(self, code: str) -> db_models.InvitationCode | None:
        """Look up an invitation code.

        Args:
            code (str): The invitation code string

        Returns:
            db_models.InvitationCode | None: InvitationCode if found, None otherwise
        """
        response = (
            self._client.table("invitation_codes")
            .select("*")
            .eq("code", code)
            .execute()
        )
        if rows := _rows(response):
            return self._row_to_invitation_code(rows[0])
        return None

    def claim_invitation_code(
        self, code: str, email: str
    ) -> db_models.InvitationCode | None:
        """Atomically claim an invitation code.

        Validates that the code is unused and not expired, then marks it as
        used in a single update to prevent race conditions.

        Args:
            code (str): The invitation code string
            email (str): Email of the user claiming the code

        Returns:
            db_models.InvitationCode | None: The claimed InvitationCode if
                successful, None otherwise
        """
        now = int(datetime.now(UTC).timestamp())
        response = (
            self._client.table("invitation_codes")
            .update({"is_used": True, "used_by_email": email, "used_at": now})
            .eq("code", code)
            .eq("is_used", False)
            .or_(f"expires_at.is.null,expires_at.gte.{now}")
            .execute()
        )
        if rows := _rows(response):
            return self._row_to_invitation_code(rows[0])
        return None

    def release_invitation_code(self, code: str) -> None:
        """Release a previously claimed invitation code.

        Used to roll back a claim when a subsequent operation fails.

        Args:
            code (str): The invitation code string to release
        """
        self._client.table("invitation_codes").update(
            {"is_used": False, "used_by_email": None, "used_at": None}
        ).eq("code", code).execute()

    def create_invitation_code(
        self, code: str, expires_at: int | None = None
    ) -> db_models.InvitationCode:
        """Create a new invitation code.

        Args:
            code (str): The invitation code string
            expires_at (int | None): Optional Unix timestamp for expiration

        Returns:
            db_models.InvitationCode: Created InvitationCode object

        Raises:
            Exception: If the Supabase insert fails to return a row
        """
        created_at = int(datetime.now(UTC).timestamp())
        data = {
            "code": code,
            "is_used": False,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        response = self._client.table("invitation_codes").insert(data).execute()
        if rows := _rows(response):
            return self._row_to_invitation_code(rows[0])
        raise Exception("Failed to create invitation code in Supabase")
