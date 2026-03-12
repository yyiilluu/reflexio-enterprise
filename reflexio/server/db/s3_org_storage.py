"""
S3-based organization storage for self-host mode.

This module provides a singleton storage class that stores organization/login data
in S3 instead of using Supabase. Organizations are loaded once at startup and
cached in memory for fast reads, with writes persisted to S3.

The S3 file structure:
- auth/organizations.json - contains all organization data
"""

import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional

from reflexio.server import (
    CONFIG_S3_ACCESS_KEY,
    CONFIG_S3_SECRET_KEY,
    CONFIG_S3_REGION,
    CONFIG_S3_PATH,
    FERNET_KEYS,
)
from reflexio.server.db import db_models
from reflexio.utils.encrypt_manager import EncryptManager
from reflexio.utils.s3_utils import S3Utils

logger = logging.getLogger(__name__)


def is_s3_org_storage_ready() -> bool:
    """
    Check if all required S3 config storage parameters are set.

    Returns:
        bool: True if all CONFIG_S3_* env vars are set, False otherwise
    """
    return all(
        [CONFIG_S3_PATH, CONFIG_S3_REGION, CONFIG_S3_ACCESS_KEY, CONFIG_S3_SECRET_KEY]
    )


class OrganizationsStore:
    """
    In-memory store for organizations data.
    Thread-safe container for organization data loaded from S3.
    """

    def __init__(self):
        self.organizations: list[dict] = []
        self.next_id: int = 1
        self.api_tokens: list[dict] = []
        self.next_token_id: int = 1

    def to_dict(self) -> dict:
        """
        Convert store to dictionary for JSON serialization.

        Returns:
            dict: Store data as dictionary
        """
        return {
            "organizations": self.organizations,
            "next_id": self.next_id,
            "api_tokens": self.api_tokens,
            "next_token_id": self.next_token_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrganizationsStore":
        """
        Create store from dictionary.

        Args:
            data: Dictionary with organizations and next_id

        Returns:
            OrganizationsStore: Populated store
        """
        store = cls()
        store.organizations = data.get("organizations", [])
        store.next_id = data.get("next_id", 1)
        store.api_tokens = data.get("api_tokens", [])
        store.next_token_id = data.get("next_token_id", 1)
        return store


class S3OrganizationStorage:
    """
    S3-based organization storage implementation (singleton).
    Stores organization/login data in S3 with optional encryption.

    The storage is loaded once at initialization and kept in memory.
    Write operations update both memory and S3.
    """

    _instance: Optional["S3OrganizationStorage"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        s3_path: Optional[str] = None,
        s3_region: Optional[str] = None,
        s3_access_key: Optional[str] = None,
        s3_secret_key: Optional[str] = None,
    ):
        """
        Initialize S3 organization storage.

        Args:
            s3_path: S3 bucket path, falls back to CONFIG_S3_PATH env var
            s3_region: AWS region, falls back to CONFIG_S3_REGION env var
            s3_access_key: AWS access key, falls back to CONFIG_S3_ACCESS_KEY env var
            s3_secret_key: AWS secret key, falls back to CONFIG_S3_SECRET_KEY env var
        """
        # Only initialize once (singleton pattern)
        if self._initialized:
            return

        # Use provided params or fall back to env vars
        self.s3_path = s3_path or CONFIG_S3_PATH
        self.s3_region = s3_region or CONFIG_S3_REGION
        self.s3_access_key = s3_access_key or CONFIG_S3_ACCESS_KEY
        self.s3_secret_key = s3_secret_key or CONFIG_S3_SECRET_KEY

        # S3 file key for organizations
        self.org_file_key = "auth/organizations.json"

        # Initialize S3 utils
        self.s3_utils = S3Utils(
            s3_path=self.s3_path,
            aws_region=self.s3_region,
            aws_access_key=self.s3_access_key,
            aws_secret_key=self.s3_secret_key,
        )

        # Thread lock for write operations
        self._write_lock = threading.Lock()

        # Initialize encryption manager if FERNET_KEYS is set
        self.encrypt_manager: Optional[EncryptManager] = None
        if FERNET_KEYS:
            self.encrypt_manager = EncryptManager(fernet_keys=FERNET_KEYS)

        # Load organizations from S3 at startup
        self.store = self._load_from_s3()

        logger.info(
            f"S3OrganizationStorage initialized with {len(self.store.organizations)} organizations"
        )
        print(
            f"S3OrganizationStorage initialized from {self.s3_path}/{self.org_file_key}"
        )

        self._initialized = True

    def _load_from_s3(self) -> OrganizationsStore:
        """
        Load organizations from S3.

        Returns:
            OrganizationsStore: Loaded store or empty store if not found
        """
        try:
            if not self.s3_utils.file_exists(self.org_file_key):
                logger.info("Organizations file not found in S3, creating empty store")
                return OrganizationsStore()

            # Read raw content from S3
            response = self.s3_utils.s3_client.get_object(
                Bucket=self.s3_path, Key=self.org_file_key
            )
            raw_content = response["Body"].read().decode("utf-8")

            if not raw_content:
                return OrganizationsStore()

            # Decrypt if encryption is enabled
            if self.encrypt_manager:
                content = self.encrypt_manager.decrypt(encrypted_value=raw_content)
                if content is None:
                    logger.error("Failed to decrypt organizations file")
                    return OrganizationsStore()
            else:
                content = raw_content

            data = json.loads(content)
            return OrganizationsStore.from_dict(data)

        except Exception as e:
            logger.error(f"Error loading organizations from S3: {str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
            return OrganizationsStore()

    def _save_to_s3(self) -> bool:
        """
        Save organizations to S3.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            content = json.dumps(self.store.to_dict())

            # Encrypt if encryption is enabled
            if self.encrypt_manager:
                content = self.encrypt_manager.encrypt(value=content)
                if content is None:
                    logger.error("Failed to encrypt organizations data")
                    return False

            # Write to S3
            self.s3_utils.s3_client.put_object(
                Bucket=self.s3_path,
                Key=self.org_file_key,
                Body=content,
                ContentType="application/json",
            )
            return True

        except Exception as e:
            logger.error(f"Error saving organizations to S3: {str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
            return False

    def _dict_to_organization(self, org_dict: dict) -> db_models.Organization:
        """
        Convert a dictionary to an Organization model instance.

        Args:
            org_dict: Dictionary from store

        Returns:
            Organization model instance (detached, not bound to SQLAlchemy session)
        """
        org = db_models.Organization()
        org.id = org_dict.get("id")
        org.created_at = org_dict.get("created_at")
        org.email = org_dict.get("email")
        org.hashed_password = org_dict.get("hashed_password")
        org.is_active = org_dict.get("is_active", True)
        org.is_verified = org_dict.get("is_verified", True)  # Auto-verify in self-host
        org.interaction_count = org_dict.get("interaction_count", 0)
        org.configuration_json = org_dict.get("configuration_json", "")
        org.api_key = org_dict.get("api_key", "")
        org.is_self_managed = org_dict.get("is_self_managed", False)
        return org

    def _organization_to_dict(self, org: db_models.Organization) -> dict:
        """
        Convert an Organization model to dictionary.

        Args:
            org: Organization model instance

        Returns:
            Dictionary representation
        """
        return {
            "id": org.id,
            "created_at": org.created_at,
            "email": org.email,
            "hashed_password": org.hashed_password,
            "is_active": org.is_active if org.is_active is not None else True,
            "is_verified": org.is_verified if org.is_verified is not None else True,
            "interaction_count": org.interaction_count
            if org.interaction_count is not None
            else 0,
            "configuration_json": org.configuration_json or "",
            "api_key": org.api_key or "",
            "is_self_managed": org.is_self_managed
            if org.is_self_managed is not None
            else False,
        }

    def get_organization_by_email(self, email: str) -> Optional[db_models.Organization]:
        """
        Get an organization by email.

        Args:
            email: Email address

        Returns:
            Organization or None
        """
        for org_dict in self.store.organizations:
            if org_dict.get("email") == email:
                return self._dict_to_organization(org_dict)
        return None

    def get_organization_by_id(self, org_id: int) -> Optional[db_models.Organization]:
        """
        Get an organization by ID.

        Args:
            org_id: Organization ID

        Returns:
            Organization or None
        """
        for org_dict in self.store.organizations:
            if org_dict.get("id") == org_id:
                return self._dict_to_organization(org_dict)
        return None

    def create_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """
        Create a new organization.

        Args:
            organization: Organization object to create

        Returns:
            Created Organization object with ID populated

        Raises:
            ValueError: If email already exists
        """
        with self._write_lock:
            # Check if email already exists
            if self.get_organization_by_email(organization.email):
                raise ValueError(
                    f"Organization with email {organization.email} already exists"
                )

            # Assign new ID
            organization.id = self.store.next_id
            self.store.next_id += 1

            # Set created_at if not set
            if not organization.created_at:
                organization.created_at = int(datetime.now(timezone.utc).timestamp())

            # Auto-verify in self-host mode
            if organization.is_verified is None:
                organization.is_verified = True

            # Add to store
            org_dict = self._organization_to_dict(organization)
            self.store.organizations.append(org_dict)

            # Persist to S3
            if not self._save_to_s3():
                # Rollback on failure
                self.store.organizations.pop()
                self.store.next_id -= 1
                raise Exception("Failed to save organization to S3")

            return organization

    def update_organization(
        self, organization: db_models.Organization
    ) -> db_models.Organization:
        """
        Update an existing organization.

        Args:
            organization: Organization object with updated fields

        Returns:
            Updated Organization object

        Raises:
            ValueError: If organization not found
        """
        with self._write_lock:
            # Find and update organization
            for i, org_dict in enumerate(self.store.organizations):
                if org_dict.get("id") == organization.id:
                    old_org = self.store.organizations[i]
                    self.store.organizations[i] = self._organization_to_dict(
                        organization
                    )

                    # Persist to S3
                    if not self._save_to_s3():
                        # Rollback on failure
                        self.store.organizations[i] = old_org
                        raise Exception("Failed to save organization to S3")

                    return organization

            raise ValueError(f"Organization with ID {organization.id} not found")

    def get_organizations(
        self, skip: int = 0, limit: int = 100
    ) -> list[db_models.Organization]:
        """
        Get a list of organizations with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Organization objects
        """
        orgs = self.store.organizations[skip : skip + limit]
        return [self._dict_to_organization(org_dict) for org_dict in orgs]

    def _dict_to_api_token(self, token_dict: dict) -> db_models.ApiToken:
        """
        Convert a dictionary to an ApiToken model instance.

        Args:
            token_dict: Dictionary from store

        Returns:
            ApiToken model instance
        """
        token = db_models.ApiToken()
        token.id = token_dict.get("id")
        token.org_id = token_dict.get("org_id")
        token.token = token_dict.get("token")
        token.name = token_dict.get("name", "Default")
        token.created_at = token_dict.get("created_at")
        token.last_used_at = token_dict.get("last_used_at")
        return token

    def create_api_token(
        self, org_id: int, token_value: str, name: str = "Default"
    ) -> db_models.ApiToken:
        """
        Create a new API token in S3 storage.

        Args:
            org_id: Organization ID
            token_value: The token string
            name: Human-readable name

        Returns:
            Created ApiToken object
        """
        with self._write_lock:
            token_dict = {
                "id": self.store.next_token_id,
                "org_id": org_id,
                "token": token_value,
                "name": name,
                "created_at": int(datetime.now(timezone.utc).timestamp()),
                "last_used_at": None,
            }
            self.store.next_token_id += 1
            self.store.api_tokens.append(token_dict)

            if not self._save_to_s3():
                self.store.api_tokens.pop()
                self.store.next_token_id -= 1
                raise Exception("Failed to save API token to S3")

            return self._dict_to_api_token(token_dict)

    def get_api_tokens_by_org_id(self, org_id: int) -> list[db_models.ApiToken]:
        """
        Get all API tokens for an organization from S3 storage.

        Args:
            org_id: Organization ID

        Returns:
            List of ApiToken objects
        """
        return [
            self._dict_to_api_token(t)
            for t in self.store.api_tokens
            if t.get("org_id") == org_id
        ]

    def get_org_by_api_token(
        self, token_value: str
    ) -> Optional[db_models.Organization]:
        """
        Look up an organization by API token value in S3 storage.

        Args:
            token_value: The token string

        Returns:
            Organization or None
        """
        for t in self.store.api_tokens:
            if t.get("token") == token_value:
                return self.get_organization_by_id(t["org_id"])
        return None

    def delete_api_token(self, token_id: int, org_id: int) -> bool:
        """
        Delete an API token from S3 storage.

        Args:
            token_id: Token ID
            org_id: Organization ID (ownership check)

        Returns:
            True if deleted, False if not found
        """
        with self._write_lock:
            for i, t in enumerate(self.store.api_tokens):
                if t.get("id") == token_id and t.get("org_id") == org_id:
                    old_token = self.store.api_tokens.pop(i)
                    if not self._save_to_s3():
                        self.store.api_tokens.insert(i, old_token)
                        raise Exception("Failed to save to S3")
                    return True
            return False


# Singleton getter
_s3_org_storage_instance: Optional[S3OrganizationStorage] = None


def get_s3_org_storage() -> S3OrganizationStorage:
    """
    Get the singleton S3OrganizationStorage instance.

    Returns:
        S3OrganizationStorage: The singleton instance
    """
    global _s3_org_storage_instance
    if _s3_org_storage_instance is None:
        _s3_org_storage_instance = S3OrganizationStorage()
    return _s3_org_storage_instance


def reset_s3_org_storage() -> None:
    """
    Reset the singleton S3OrganizationStorage instance.
    Useful for testing.
    """
    global _s3_org_storage_instance
    _s3_org_storage_instance = None
    S3OrganizationStorage._instance = None
