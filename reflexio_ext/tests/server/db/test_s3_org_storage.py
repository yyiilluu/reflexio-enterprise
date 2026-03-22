"""Tests for S3-based organization storage module."""

import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from reflexio_ext.server.db import db_models
from reflexio_ext.server.db.s3_org_storage import (
    OrganizationsStore,
    S3OrganizationStorage,
    get_s3_org_storage,
    is_s3_org_storage_ready,
    reset_s3_org_storage,
)

TEST_BUCKET = "test-org-bucket"
TEST_REGION = "us-east-1"
TEST_ACCESS_KEY = "test_access_key"
TEST_SECRET_KEY = "test_secret_key"  # noqa: S105
ORG_FILE_KEY = "auth/organizations.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(email: str = "test@example.com", hashed_password: str = "hashed") -> db_models.Organization:
    """Create a minimal Organization model for testing."""
    org = db_models.Organization()
    org.email = email  # type: ignore[reportAttributeAccessIssue]
    org.hashed_password = hashed_password  # type: ignore[reportAttributeAccessIssue]
    return org


def _seed_s3_data(s3_client, data: dict) -> None:
    """Upload organization JSON data to mock S3."""
    s3_client.put_object(
        Bucket=TEST_BUCKET,
        Key=ORG_FILE_KEY,
        Body=json.dumps(data),
        ContentType="application/json",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the singleton between every test so state never leaks."""
    reset_s3_org_storage()
    yield
    reset_s3_org_storage()


@pytest.fixture
def mock_s3():
    """Provide a moto-mocked S3 bucket and raw boto3 client."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=TEST_REGION)
        s3.create_bucket(Bucket=TEST_BUCKET)
        yield s3


@pytest.fixture
def storage(mock_s3):
    """Create an S3OrganizationStorage instance backed by mock S3."""
    with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", ""):
        inst = S3OrganizationStorage(
            s3_path=TEST_BUCKET,
            s3_region=TEST_REGION,
            s3_access_key=TEST_ACCESS_KEY,
            s3_secret_key=TEST_SECRET_KEY,
        )
    return inst


@pytest.fixture
def seeded_storage(mock_s3):
    """Create storage pre-seeded with two organizations and one API token."""
    data = {
        "organizations": [
            {
                "id": 1,
                "created_at": 1700000000,
                "email": "alice@example.com",
                "hashed_password": "hash_alice",
                "is_active": True,
                "is_verified": True,
                "interaction_count": 5,
                "configuration_json": '{"theme":"dark"}',
                "is_self_managed": False,
                "auth_provider": "email",
            },
            {
                "id": 2,
                "created_at": 1700000001,
                "email": "bob@example.com",
                "hashed_password": "hash_bob",
                "is_active": True,
                "is_verified": True,
                "interaction_count": 0,
                "configuration_json": "",
                "is_self_managed": True,
                "auth_provider": "google",
            },
        ],
        "next_id": 3,
        "api_tokens": [
            {
                "id": 1,
                "org_id": 1,
                "token": "tok_alice_1",
                "name": "Alice Token",
                "created_at": 1700000010,
                "last_used_at": None,
            },
        ],
        "next_token_id": 2,
    }
    _seed_s3_data(mock_s3, data)

    with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", ""):
        inst = S3OrganizationStorage(
            s3_path=TEST_BUCKET,
            s3_region=TEST_REGION,
            s3_access_key=TEST_ACCESS_KEY,
            s3_secret_key=TEST_SECRET_KEY,
        )
    return inst


# ===========================================================================
# OrganizationsStore
# ===========================================================================


class TestOrganizationsStore:
    """Tests for the in-memory OrganizationsStore data container."""

    def test_default_init(self):
        """New store starts with empty lists and next_id = 1."""
        store = OrganizationsStore()
        assert store.organizations == []
        assert store.next_id == 1
        assert store.api_tokens == []
        assert store.next_token_id == 1

    def test_to_dict(self):
        """to_dict round-trips correctly."""
        store = OrganizationsStore()
        store.organizations = [{"id": 1, "email": "a@b.com"}]
        store.next_id = 2
        store.api_tokens = [{"id": 1, "token": "tok"}]
        store.next_token_id = 2

        d = store.to_dict()
        assert d["organizations"] == [{"id": 1, "email": "a@b.com"}]
        assert d["next_id"] == 2
        assert d["api_tokens"] == [{"id": 1, "token": "tok"}]
        assert d["next_token_id"] == 2

    def test_from_dict(self):
        """from_dict populates all fields."""
        data = {
            "organizations": [{"id": 10}],
            "next_id": 11,
            "api_tokens": [{"id": 5}],
            "next_token_id": 6,
        }
        store = OrganizationsStore.from_dict(data)
        assert store.organizations == [{"id": 10}]
        assert store.next_id == 11
        assert store.api_tokens == [{"id": 5}]
        assert store.next_token_id == 6

    def test_from_dict_defaults(self):
        """from_dict handles missing keys gracefully."""
        store = OrganizationsStore.from_dict({})
        assert store.organizations == []
        assert store.next_id == 1
        assert store.api_tokens == []
        assert store.next_token_id == 1

    def test_round_trip(self):
        """to_dict -> from_dict preserves data."""
        store = OrganizationsStore()
        store.organizations = [{"id": 1}]
        store.next_id = 99
        store.api_tokens = [{"id": 7, "token": "abc"}]
        store.next_token_id = 8

        restored = OrganizationsStore.from_dict(store.to_dict())
        assert restored.organizations == store.organizations
        assert restored.next_id == store.next_id
        assert restored.api_tokens == store.api_tokens
        assert restored.next_token_id == store.next_token_id


# ===========================================================================
# is_s3_org_storage_ready
# ===========================================================================


class TestIsS3OrgStorageReady:
    """Tests for the is_s3_org_storage_ready helper."""

    def test_ready_when_all_set(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="bucket",
            CONFIG_S3_REGION="us-east-1",
            CONFIG_S3_ACCESS_KEY="ak",
            CONFIG_S3_SECRET_KEY="sk",
        ):
            assert is_s3_org_storage_ready() is True

    def test_not_ready_missing_path(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="",
            CONFIG_S3_REGION="us-east-1",
            CONFIG_S3_ACCESS_KEY="ak",
            CONFIG_S3_SECRET_KEY="sk",
        ):
            assert is_s3_org_storage_ready() is False

    def test_not_ready_missing_region(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="bucket",
            CONFIG_S3_REGION="",
            CONFIG_S3_ACCESS_KEY="ak",
            CONFIG_S3_SECRET_KEY="sk",
        ):
            assert is_s3_org_storage_ready() is False

    def test_not_ready_missing_access_key(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="bucket",
            CONFIG_S3_REGION="us-east-1",
            CONFIG_S3_ACCESS_KEY="",
            CONFIG_S3_SECRET_KEY="sk",
        ):
            assert is_s3_org_storage_ready() is False

    def test_not_ready_missing_secret_key(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="bucket",
            CONFIG_S3_REGION="us-east-1",
            CONFIG_S3_ACCESS_KEY="ak",
            CONFIG_S3_SECRET_KEY="",
        ):
            assert is_s3_org_storage_ready() is False

    def test_not_ready_all_empty(self):
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH="",
            CONFIG_S3_REGION="",
            CONFIG_S3_ACCESS_KEY="",
            CONFIG_S3_SECRET_KEY="",
        ):
            assert is_s3_org_storage_ready() is False


# ===========================================================================
# S3OrganizationStorage -- initialization and singleton
# ===========================================================================


class TestStorageInit:
    """Tests for S3OrganizationStorage initialization and singleton behaviour."""

    def test_singleton_returns_same_instance(self, mock_s3):
        """Two calls to __new__ return the exact same object."""
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", ""):
            a = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
            b = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert a is b

    def test_init_with_empty_bucket(self, storage):
        """Starting with no S3 file gives an empty store."""
        assert storage.store.organizations == []
        assert storage.store.next_id == 1

    def test_init_loads_existing_data(self, seeded_storage):
        """Starting with existing S3 data loads it into memory."""
        assert len(seeded_storage.store.organizations) == 2
        assert seeded_storage.store.next_id == 3
        assert len(seeded_storage.store.api_tokens) == 1
        assert seeded_storage.store.next_token_id == 2

    def test_init_without_encryption(self, storage):
        """Without FERNET_KEYS, encrypt_manager is None."""
        assert storage.encrypt_manager is None

    def test_init_with_encryption(self, mock_s3):
        """With FERNET_KEYS, encrypt_manager is set up."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert inst.encrypt_manager is not None


# ===========================================================================
# S3OrganizationStorage -- load / save
# ===========================================================================


class TestLoadSave:
    """Tests for internal _load_from_s3 and _save_to_s3."""

    def test_load_empty_content(self, mock_s3):
        """Loading an empty file returns an empty store."""
        mock_s3.put_object(
            Bucket=TEST_BUCKET, Key=ORG_FILE_KEY, Body="", ContentType="application/json"
        )
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", ""):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert inst.store.organizations == []

    def test_load_invalid_json_returns_empty_store(self, mock_s3):
        """Loading corrupted JSON returns an empty store instead of crashing."""
        mock_s3.put_object(
            Bucket=TEST_BUCKET, Key=ORG_FILE_KEY, Body="NOT VALID JSON"
        )
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", ""):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert inst.store.organizations == []

    def test_save_persists_data(self, storage, mock_s3):
        """_save_to_s3 writes store content to the expected key."""
        storage.store.organizations = [{"id": 1, "email": "x@y.com"}]
        assert storage._save_to_s3() is True

        raw = mock_s3.get_object(Bucket=TEST_BUCKET, Key=ORG_FILE_KEY)["Body"].read().decode()
        data = json.loads(raw)
        assert data["organizations"] == [{"id": 1, "email": "x@y.com"}]

    def test_save_with_encryption(self, mock_s3):
        """With encryption enabled, saved content is encrypted and can be loaded back."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )

        # Create an org to force save
        org = _make_org(email="enc@test.com")
        inst.create_organization(org)

        # Raw S3 content should NOT be plain JSON
        raw = mock_s3.get_object(Bucket=TEST_BUCKET, Key=ORG_FILE_KEY)["Body"].read().decode()
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)

        # Reset and reload -- data should survive round-trip
        reset_s3_org_storage()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key):
            inst2 = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert len(inst2.store.organizations) == 1
        assert inst2.store.organizations[0]["email"] == "enc@test.com"

    def test_load_with_failed_decryption_returns_empty(self, mock_s3):
        """If decryption fails, an empty store is returned."""
        from cryptography.fernet import Fernet

        # Write with one key, try to load with a different key
        key1 = Fernet.generate_key().decode()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key1):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        inst.create_organization(_make_org("x@y.com"))

        reset_s3_org_storage()
        key2 = Fernet.generate_key().decode()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key2):
            inst2 = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )
        assert inst2.store.organizations == []

    def test_save_failure_returns_false(self, storage):
        """_save_to_s3 returns False when S3 write fails."""
        storage.s3_utils.s3_client.put_object = MagicMock(side_effect=Exception("boom"))
        assert storage._save_to_s3() is False


# ===========================================================================
# Organization CRUD
# ===========================================================================


class TestOrganizationCRUD:
    """Tests for organization create / read / update / delete."""

    # -- create --

    def test_create_organization(self, storage):
        """Creating an org assigns an ID and persists to S3."""
        org = _make_org(email="new@example.com")
        result = storage.create_organization(org)

        assert result.id == 1
        assert result.email == "new@example.com"
        assert result.is_verified is True
        assert result.created_at is not None
        assert len(storage.store.organizations) == 1

    def test_create_sets_defaults(self, storage):
        """Created orgs get is_verified defaulted and created_at populated."""
        org = _make_org()
        result = storage.create_organization(org)

        # is_verified is explicitly defaulted by create_organization
        assert result.is_verified is True
        assert result.created_at is not None

        # The stored dict applies defaults for None fields via _organization_to_dict
        stored = storage.store.organizations[0]
        assert stored["is_active"] is True
        assert stored["interaction_count"] == 0

    def test_create_increments_id(self, storage):
        """Sequential creates get incrementing IDs."""
        storage.create_organization(_make_org("a@b.com"))
        storage.create_organization(_make_org("c@d.com"))
        assert storage.store.next_id == 3

    def test_create_duplicate_email_raises(self, storage):
        """Creating an org with a duplicate email raises ValueError."""
        storage.create_organization(_make_org("dup@x.com"))
        with pytest.raises(ValueError, match="already exists"):
            storage.create_organization(_make_org("dup@x.com"))

    def test_create_rollback_on_save_failure(self, storage):
        """If S3 save fails, the in-memory store is rolled back."""
        storage.create_organization(_make_org("ok@x.com"))

        storage.s3_utils.s3_client.put_object = MagicMock(side_effect=Exception("boom"))
        with pytest.raises(Exception, match="Failed to save"):
            storage.create_organization(_make_org("fail@x.com"))

        # Only the first org should remain
        assert len(storage.store.organizations) == 1
        assert storage.store.next_id == 2

    # -- read --

    def test_get_by_email_found(self, seeded_storage):
        """get_organization_by_email returns the matching org."""
        org = seeded_storage.get_organization_by_email("alice@example.com")
        assert org is not None
        assert org.id == 1
        assert org.email == "alice@example.com"
        assert org.interaction_count == 5

    def test_get_by_email_not_found(self, seeded_storage):
        """get_organization_by_email returns None for unknown email."""
        assert seeded_storage.get_organization_by_email("nope@x.com") is None

    def test_get_by_id_found(self, seeded_storage):
        """get_organization_by_id returns the matching org."""
        org = seeded_storage.get_organization_by_id(2)
        assert org is not None
        assert org.email == "bob@example.com"
        assert org.is_self_managed is True
        assert org.auth_provider == "google"

    def test_get_by_id_not_found(self, seeded_storage):
        """get_organization_by_id returns None for unknown id."""
        assert seeded_storage.get_organization_by_id(999) is None

    def test_get_organizations_default(self, seeded_storage):
        """get_organizations returns all orgs with default pagination."""
        orgs = seeded_storage.get_organizations()
        assert len(orgs) == 2

    def test_get_organizations_with_skip(self, seeded_storage):
        """get_organizations respects skip parameter."""
        orgs = seeded_storage.get_organizations(skip=1)
        assert len(orgs) == 1
        assert orgs[0].email == "bob@example.com"

    def test_get_organizations_with_limit(self, seeded_storage):
        """get_organizations respects limit parameter."""
        orgs = seeded_storage.get_organizations(limit=1)
        assert len(orgs) == 1
        assert orgs[0].email == "alice@example.com"

    def test_get_organizations_skip_beyond_range(self, seeded_storage):
        """Skipping beyond available orgs returns empty list."""
        assert seeded_storage.get_organizations(skip=100) == []

    # -- update --

    def test_update_organization(self, seeded_storage):
        """Updating an org persists changes."""
        org = seeded_storage.get_organization_by_id(1)
        assert org is not None
        org.configuration_json = '{"theme":"light"}'  # type: ignore[reportAttributeAccessIssue]
        org.interaction_count = 10  # type: ignore[reportAttributeAccessIssue]

        updated = seeded_storage.update_organization(org)
        assert updated.configuration_json == '{"theme":"light"}'

        # Verify in-memory state
        reloaded = seeded_storage.get_organization_by_id(1)
        assert reloaded is not None
        assert reloaded.interaction_count == 10

    def test_update_nonexistent_raises(self, storage):
        """Updating a non-existent org raises ValueError."""
        org = _make_org()
        org.id = 999  # type: ignore[reportAttributeAccessIssue]
        with pytest.raises(ValueError, match="not found"):
            storage.update_organization(org)

    def test_update_rollback_on_save_failure(self, seeded_storage):
        """If S3 save fails during update, the old data is preserved."""
        org = seeded_storage.get_organization_by_id(1)
        assert org is not None
        original_config = org.configuration_json

        org.configuration_json = "CHANGED"  # type: ignore[reportAttributeAccessIssue]
        seeded_storage.s3_utils.s3_client.put_object = MagicMock(side_effect=Exception("boom"))

        with pytest.raises(Exception, match="Failed to save"):
            seeded_storage.update_organization(org)

        # Verify rollback
        restored = seeded_storage.get_organization_by_id(1)
        assert restored is not None
        assert restored.configuration_json == original_config

    # -- delete --

    def test_delete_organization(self, seeded_storage):
        """Deleting an existing org returns True and removes it."""
        assert seeded_storage.delete_organization(1) is True
        assert seeded_storage.get_organization_by_id(1) is None
        assert len(seeded_storage.store.organizations) == 1

    def test_delete_nonexistent_returns_false(self, seeded_storage):
        """Deleting a non-existent org returns False."""
        assert seeded_storage.delete_organization(999) is False

    def test_delete_rollback_on_save_failure(self, seeded_storage):
        """If S3 save fails during delete, the org is restored."""
        seeded_storage.s3_utils.s3_client.put_object = MagicMock(
            side_effect=Exception("boom")
        )
        with pytest.raises(Exception, match="Failed to save"):
            seeded_storage.delete_organization(1)

        assert seeded_storage.get_organization_by_id(1) is not None


# ===========================================================================
# Dict <-> Model conversion
# ===========================================================================


class TestDictConversion:
    """Tests for _dict_to_organization and _organization_to_dict."""

    def test_dict_to_organization_full(self, storage):
        """All fields are mapped correctly from dict to model."""
        d = {
            "id": 42,
            "created_at": 1700000000,
            "email": "conv@test.com",
            "hashed_password": "pw",
            "is_active": False,
            "is_verified": False,
            "interaction_count": 99,
            "configuration_json": '{"k":"v"}',
            "is_self_managed": True,
            "auth_provider": "saml",
        }
        org = storage._dict_to_organization(d)
        assert org.id == 42
        assert org.created_at == 1700000000
        assert org.email == "conv@test.com"
        assert org.hashed_password == "pw"
        assert org.is_active is False
        assert org.is_verified is False
        assert org.interaction_count == 99
        assert org.configuration_json == '{"k":"v"}'
        assert org.is_self_managed is True
        assert org.auth_provider == "saml"

    def test_dict_to_organization_defaults(self, storage):
        """Missing fields in dict fall back to defaults."""
        org = storage._dict_to_organization({})
        assert org.is_active is True
        assert org.is_verified is True
        assert org.interaction_count == 0
        assert org.configuration_json == ""
        assert org.is_self_managed is False
        assert org.auth_provider == "email"

    def test_organization_to_dict(self, storage):
        """Model to dict includes all expected keys."""
        org = db_models.Organization()
        org.id = 10  # type: ignore[reportAttributeAccessIssue]
        org.created_at = 100  # type: ignore[reportAttributeAccessIssue]
        org.email = "e@f.com"  # type: ignore[reportAttributeAccessIssue]
        org.hashed_password = "hp"  # type: ignore[reportAttributeAccessIssue]
        org.is_active = True  # type: ignore[reportAttributeAccessIssue]
        org.is_verified = False  # type: ignore[reportAttributeAccessIssue]
        org.interaction_count = 7  # type: ignore[reportAttributeAccessIssue]
        org.configuration_json = "{}"  # type: ignore[reportAttributeAccessIssue]
        org.is_self_managed = True  # type: ignore[reportAttributeAccessIssue]
        org.auth_provider = "oidc"  # type: ignore[reportAttributeAccessIssue]

        d = storage._organization_to_dict(org)
        assert d["id"] == 10
        assert d["email"] == "e@f.com"
        assert d["is_active"] is True
        assert d["is_verified"] is False
        assert d["auth_provider"] == "oidc"

    def test_organization_to_dict_none_defaults(self, storage):
        """Nones in the model fall back to safe defaults in the dict."""
        org = db_models.Organization()
        d = storage._organization_to_dict(org)
        assert d["is_active"] is True
        assert d["is_verified"] is True
        assert d["interaction_count"] == 0
        assert d["configuration_json"] == ""
        assert d["is_self_managed"] is False
        assert d["auth_provider"] == "email"

    def test_round_trip_dict_org_dict(self, storage):
        """dict -> org -> dict preserves all values."""
        original = {
            "id": 7,
            "created_at": 1234567890,
            "email": "rt@test.com",
            "hashed_password": "hash",
            "is_active": True,
            "is_verified": True,
            "interaction_count": 3,
            "configuration_json": '{"a":1}',
            "is_self_managed": False,
            "auth_provider": "email",
        }
        org = storage._dict_to_organization(original)
        result = storage._organization_to_dict(org)
        assert result == original


# ===========================================================================
# API token CRUD
# ===========================================================================


class TestApiTokenCRUD:
    """Tests for API token create / read / lookup / delete."""

    def test_create_api_token(self, storage):
        """Creating an org first, then a token, assigns correct IDs."""
        storage.create_organization(_make_org("org@t.com"))
        token = storage.create_api_token(org_id=1, token_value="tok_123", name="My Token")

        assert token.id == 1
        assert token.org_id == 1
        assert token.token == "tok_123"
        assert token.name == "My Token"
        assert token.created_at is not None
        assert token.last_used_at is None

    def test_create_api_token_default_name(self, storage):
        """Token name defaults to 'Default'."""
        storage.create_organization(_make_org("org@t.com"))
        token = storage.create_api_token(org_id=1, token_value="tok_456")
        assert token.name == "Default"

    def test_create_token_increments_id(self, storage):
        """Sequential token creates get incrementing IDs."""
        storage.create_organization(_make_org("org@t.com"))
        storage.create_api_token(org_id=1, token_value="t1")
        storage.create_api_token(org_id=1, token_value="t2")
        assert storage.store.next_token_id == 3

    def test_create_token_rollback_on_save_failure(self, storage):
        """If S3 save fails during token create, the token is rolled back."""
        storage.create_organization(_make_org("org@t.com"))
        # Break S3 writes
        storage.s3_utils.s3_client.put_object = MagicMock(side_effect=Exception("boom"))
        with pytest.raises(Exception, match="Failed to save"):
            storage.create_api_token(org_id=1, token_value="bad_tok")

        assert len(storage.store.api_tokens) == 0
        assert storage.store.next_token_id == 1

    def test_get_api_tokens_by_org_id(self, seeded_storage):
        """Retrieves tokens for the specified org only."""
        tokens = seeded_storage.get_api_tokens_by_org_id(1)
        assert len(tokens) == 1
        assert tokens[0].token == "tok_alice_1"

    def test_get_api_tokens_empty_for_unknown_org(self, seeded_storage):
        """Returns empty list for an org with no tokens."""
        assert seeded_storage.get_api_tokens_by_org_id(999) == []

    def test_get_org_by_api_token(self, seeded_storage):
        """Looks up org by token value."""
        org = seeded_storage.get_org_by_api_token("tok_alice_1")
        assert org is not None
        assert org.id == 1
        assert org.email == "alice@example.com"

    def test_get_org_by_api_token_not_found(self, seeded_storage):
        """Returns None for unknown token value."""
        assert seeded_storage.get_org_by_api_token("nonexistent_token") is None

    def test_delete_api_token(self, seeded_storage):
        """Deleting an existing token returns True."""
        assert seeded_storage.delete_api_token(token_id=1, org_id=1) is True
        assert seeded_storage.get_api_tokens_by_org_id(1) == []

    def test_delete_api_token_wrong_org(self, seeded_storage):
        """Cannot delete a token belonging to another org."""
        assert seeded_storage.delete_api_token(token_id=1, org_id=2) is False
        # Token still exists
        assert len(seeded_storage.get_api_tokens_by_org_id(1)) == 1

    def test_delete_api_token_nonexistent(self, seeded_storage):
        """Deleting a non-existent token returns False."""
        assert seeded_storage.delete_api_token(token_id=999, org_id=1) is False

    def test_delete_token_rollback_on_save_failure(self, seeded_storage):
        """If S3 save fails during token delete, the token is restored."""
        seeded_storage.s3_utils.s3_client.put_object = MagicMock(
            side_effect=Exception("boom")
        )
        with pytest.raises(Exception, match="Failed to save"):
            seeded_storage.delete_api_token(token_id=1, org_id=1)

        assert len(seeded_storage.store.api_tokens) == 1

    def test_delete_all_api_tokens_for_org(self, storage):
        """delete_all_api_tokens_for_org removes all tokens for an org."""
        storage.create_organization(_make_org("org@t.com"))
        storage.create_api_token(org_id=1, token_value="t1")
        storage.create_api_token(org_id=1, token_value="t2")
        storage.create_api_token(org_id=1, token_value="t3")

        count = storage.delete_all_api_tokens_for_org(1)
        assert count == 3
        assert storage.get_api_tokens_by_org_id(1) == []

    def test_delete_all_tokens_no_tokens(self, storage):
        """delete_all_api_tokens_for_org returns 0 for org with no tokens."""
        assert storage.delete_all_api_tokens_for_org(999) == 0

    def test_delete_all_tokens_preserves_other_orgs(self, storage):
        """delete_all_api_tokens_for_org only removes tokens for specified org."""
        storage.create_organization(_make_org("a@t.com"))
        storage.create_organization(_make_org("b@t.com"))
        storage.create_api_token(org_id=1, token_value="t_a")
        storage.create_api_token(org_id=2, token_value="t_b")

        storage.delete_all_api_tokens_for_org(1)
        assert storage.get_api_tokens_by_org_id(1) == []
        assert len(storage.get_api_tokens_by_org_id(2)) == 1

    def test_delete_all_tokens_rollback_on_save_failure(self, storage):
        """If S3 save fails during bulk delete, all tokens are restored."""
        storage.create_organization(_make_org("org@t.com"))
        storage.create_api_token(org_id=1, token_value="t1")
        storage.create_api_token(org_id=1, token_value="t2")

        storage.s3_utils.s3_client.put_object = MagicMock(side_effect=Exception("boom"))
        with pytest.raises(Exception, match="Failed to save"):
            storage.delete_all_api_tokens_for_org(1)

        assert len(storage.store.api_tokens) == 2


# ===========================================================================
# Dict to ApiToken conversion
# ===========================================================================


class TestApiTokenConversion:
    """Tests for _dict_to_api_token."""

    def test_dict_to_api_token_full(self, storage):
        """All fields mapped from dict."""
        d = {
            "id": 5,
            "org_id": 2,
            "token": "tok_val",
            "name": "Custom Name",
            "created_at": 1700000000,
            "last_used_at": 1700000099,
        }
        token = storage._dict_to_api_token(d)
        assert token.id == 5
        assert token.org_id == 2
        assert token.token == "tok_val"
        assert token.name == "Custom Name"
        assert token.created_at == 1700000000
        assert token.last_used_at == 1700000099

    def test_dict_to_api_token_defaults(self, storage):
        """Missing name defaults to 'Default'."""
        token = storage._dict_to_api_token({})
        assert token.name == "Default"
        assert token.last_used_at is None


# ===========================================================================
# Singleton helpers
# ===========================================================================


class TestSingletonHelpers:
    """Tests for get_s3_org_storage and reset_s3_org_storage."""

    def test_get_creates_instance(self, mock_s3):
        """get_s3_org_storage creates an instance on first call."""
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH=TEST_BUCKET,
            CONFIG_S3_REGION=TEST_REGION,
            CONFIG_S3_ACCESS_KEY=TEST_ACCESS_KEY,
            CONFIG_S3_SECRET_KEY=TEST_SECRET_KEY,
            FERNET_KEYS="",
        ):
            inst = get_s3_org_storage()
            assert inst is not None
            assert isinstance(inst, S3OrganizationStorage)

    def test_get_returns_same_instance(self, mock_s3):
        """get_s3_org_storage returns the same instance on repeated calls."""
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH=TEST_BUCKET,
            CONFIG_S3_REGION=TEST_REGION,
            CONFIG_S3_ACCESS_KEY=TEST_ACCESS_KEY,
            CONFIG_S3_SECRET_KEY=TEST_SECRET_KEY,
            FERNET_KEYS="",
        ):
            a = get_s3_org_storage()
            b = get_s3_org_storage()
            assert a is b

    def test_reset_clears_instance(self, mock_s3):
        """reset_s3_org_storage clears both module-level and class-level singletons."""
        with patch.multiple(
            "reflexio_ext.server.db.s3_org_storage",
            CONFIG_S3_PATH=TEST_BUCKET,
            CONFIG_S3_REGION=TEST_REGION,
            CONFIG_S3_ACCESS_KEY=TEST_ACCESS_KEY,
            CONFIG_S3_SECRET_KEY=TEST_SECRET_KEY,
            FERNET_KEYS="",
        ):
            first = get_s3_org_storage()
            reset_s3_org_storage()
            second = get_s3_org_storage()
            assert first is not second


# ===========================================================================
# Encryption edge cases
# ===========================================================================


class TestEncryptionEdgeCases:
    """Tests for encryption failure paths in save/load."""

    def test_save_encrypt_failure_returns_false(self, mock_s3):
        """If encryption fails during save, _save_to_s3 returns False."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with patch("reflexio_ext.server.db.s3_org_storage.FERNET_KEYS", key):
            inst = S3OrganizationStorage(
                s3_path=TEST_BUCKET,
                s3_region=TEST_REGION,
                s3_access_key=TEST_ACCESS_KEY,
                s3_secret_key=TEST_SECRET_KEY,
            )

        # Force encrypt to return None
        inst.encrypt_manager.encrypt = MagicMock(return_value=None)  # type: ignore[union-attr]
        assert inst._save_to_s3() is False
