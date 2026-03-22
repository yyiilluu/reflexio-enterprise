"""Tests for SupabaseConfigStorage."""

from unittest.mock import MagicMock, patch

from reflexio_commons.config_schema import Config

_MOD = "reflexio_ext.server.services.configurator.supabase_config_storage"


def _make_storage(org_id: str = "org-1"):
    """Create a SupabaseConfigStorage with mocked EncryptManager."""
    with (
        patch(f"{_MOD}.FERNET_KEYS", "fake-key"),
        patch(f"{_MOD}.EncryptManager") as mock_encrypt_cls,
    ):
        mock_em = MagicMock()
        mock_encrypt_cls.return_value = mock_em
        from reflexio_ext.server.services.configurator.supabase_config_storage import (
            SupabaseConfigStorage,
        )

        storage = SupabaseConfigStorage(org_id=org_id)
    return storage, mock_em


# ---------------------------------------------------------------------------
# get_default_config
# ---------------------------------------------------------------------------


class TestGetDefaultConfig:
    def test_returns_config_with_no_storage(self):
        storage, _ = _make_storage()
        cfg = storage.get_default_config()
        assert isinstance(cfg, Config)
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_no_client_returns_default(self, mock_get_client):
        mock_get_client.return_value = None
        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(f"{_MOD}.get_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_no_config_returns_default(self, mock_get_client, mock_get_org_cfg):
        mock_get_client.return_value = MagicMock()
        mock_get_org_cfg.return_value = None
        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(f"{_MOD}.get_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_success_decrypts_and_returns(self, mock_get_client, mock_get_org_cfg):
        mock_get_client.return_value = MagicMock()
        raw_cfg = Config(storage_config=None)
        encrypted = "encrypted-blob"
        mock_get_org_cfg.return_value = encrypted

        storage, mock_em = _make_storage()
        mock_em.decrypt.return_value = raw_cfg.model_dump_json()

        cfg = storage.load_config()
        mock_em.decrypt.assert_called_once_with(encrypted_value=encrypted)
        assert isinstance(cfg, Config)

    @patch(f"{_MOD}.get_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_exception_returns_default(self, mock_get_client, mock_get_org_cfg):
        mock_get_client.return_value = MagicMock()
        mock_get_org_cfg.side_effect = RuntimeError("boom")

        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_no_client_returns_early(self, mock_get_client):
        mock_get_client.return_value = None
        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        # No error raised

    @patch(f"{_MOD}.set_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_encrypt_failure_returns_early(self, mock_get_client, mock_set_cfg):
        mock_get_client.return_value = MagicMock()
        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = None
        storage.save_config(Config(storage_config=None))
        mock_set_cfg.assert_not_called()

    @patch(f"{_MOD}.set_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_set_org_config_failure(self, mock_get_client, mock_set_cfg):
        mock_get_client.return_value = MagicMock()
        mock_set_cfg.return_value = False
        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted"
        storage.save_config(Config(storage_config=None))
        mock_set_cfg.assert_called_once()

    @patch(f"{_MOD}.set_organization_config")
    @patch(f"{_MOD}.get_login_supabase_client")
    def test_success(self, mock_get_client, mock_set_cfg):
        client_mock = MagicMock()
        mock_get_client.return_value = client_mock
        mock_set_cfg.return_value = True

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted-cfg"

        cfg = Config(storage_config=None)
        storage.save_config(cfg)

        mock_em.encrypt.assert_called_once()
        mock_set_cfg.assert_called_once_with(client_mock, "org-1", "encrypted-cfg")

    @patch(f"{_MOD}.get_login_supabase_client")
    def test_exception_logged(self, mock_get_client):
        mock_get_client.side_effect = RuntimeError("connection lost")
        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        # No exception propagated
