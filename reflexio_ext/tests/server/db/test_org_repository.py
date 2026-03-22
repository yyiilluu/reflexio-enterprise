"""Protocol compliance tests for OrgRepository adapters and ConfigStorage implementations.

Verifies that each adapter satisfies its port interface using ``isinstance()``
checks against the ``@runtime_checkable`` Protocol / ABC.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reflexio.server.services.configurator.config_storage import ConfigStorage

from reflexio_ext.server.db.org_repository import OrgRepository
from reflexio_ext.server.db.s3_org_repository import S3OrgRepository
from reflexio_ext.server.db.sqlite_org_repository import SQLiteOrgRepository
from reflexio_ext.server.db.supabase_org_repository import SupabaseOrgRepository

# ---------------------------------------------------------------------------
# OrgRepository Protocol compliance
# ---------------------------------------------------------------------------


class TestOrgRepositoryProtocolCompliance:
    """Every OrgRepository adapter must satisfy the Protocol at runtime."""

    def test_sqlite_adapter_satisfies_protocol(self):
        repo = SQLiteOrgRepository(session_factory=None, session=MagicMock())
        assert isinstance(repo, OrgRepository)

    def test_supabase_adapter_satisfies_protocol(self):
        repo = SupabaseOrgRepository(client=MagicMock())
        assert isinstance(repo, OrgRepository)

    def test_s3_adapter_satisfies_protocol(self):
        repo = S3OrgRepository(storage=MagicMock())
        assert isinstance(repo, OrgRepository)


# ---------------------------------------------------------------------------
# ConfigStorage ABC compliance
# ---------------------------------------------------------------------------


class TestConfigStorageCompliance:
    """Every ConfigStorage adapter must be a subclass of the ABC."""

    @patch(
        "reflexio_ext.server.services.configurator.supabase_config_storage.FERNET_KEYS",
        "fake-key",
    )
    @patch(
        "reflexio_ext.server.services.configurator.supabase_config_storage.EncryptManager"
    )
    def test_supabase_config_is_config_storage(self, _mock_em):
        from reflexio_ext.server.services.configurator.supabase_config_storage import (
            SupabaseConfigStorage,
        )

        storage = SupabaseConfigStorage(org_id="test-org")
        assert isinstance(storage, ConfigStorage)

    @patch(
        "reflexio_ext.server.services.configurator.sqlite_config_storage.FERNET_KEYS",
        "fake-key",
    )
    @patch(
        "reflexio_ext.server.services.configurator.sqlite_config_storage.EncryptManager"
    )
    def test_sqlite_config_is_config_storage(self, _mock_em):
        from reflexio_ext.server.services.configurator.sqlite_config_storage import (
            SqliteConfigStorage,
        )

        storage = SqliteConfigStorage(org_id="test-org")
        assert isinstance(storage, ConfigStorage)
