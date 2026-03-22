"""Tests for RdsConfigStorage (Supabase/RDS-backed config storage)."""

from unittest.mock import MagicMock, patch

from reflexio_commons.config_schema import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(org_id: str = "org-1"):
    """Create an RdsConfigStorage with mocked EncryptManager."""
    with patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.FERNET_KEYS",
        "fake-key",
    ), patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.EncryptManager"
    ) as MockEncrypt:
        mock_em = MagicMock()
        MockEncrypt.return_value = mock_em
        from reflexio_ext.server.services.configurator.rds_config_storage import (
            RdsConfigStorage,
        )

        storage = RdsConfigStorage(org_id=org_id)
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
# load_config  -- Supabase path (SessionLocal is None)
# ---------------------------------------------------------------------------

class TestLoadConfigSupabase:
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_no_client_returns_default(self, mock_get_client):
        mock_get_client.return_value = None
        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_no_config_returns_default(self, mock_get_client, mock_get_org_cfg):
        mock_get_client.return_value = MagicMock()
        mock_get_org_cfg.return_value = None
        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
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

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_exception_returns_default(self, mock_get_client, mock_get_org_cfg):
        mock_get_client.return_value = MagicMock()
        mock_get_org_cfg.side_effect = RuntimeError("boom")

        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# load_config  -- SessionLocal path
# ---------------------------------------------------------------------------

class TestLoadConfigSession:
    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_org_not_found_returns_default(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_org_found_with_config(self, mock_session_cls):
        raw_cfg = Config(storage_config=None)
        encrypted = "enc-data"

        mock_org = MagicMock()
        mock_org.configuration_json = encrypted

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        mock_em.decrypt.return_value = raw_cfg.model_dump_json()

        cfg = storage.load_config()
        mock_em.decrypt.assert_called_once_with(encrypted_value=encrypted)
        assert isinstance(cfg, Config)

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_org_config_is_none(self, mock_session_cls):
        mock_org = MagicMock()
        mock_org.configuration_json = None

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        # When config_raw_encrypted is None, decrypt is not called;
        # json.loads(str(None)) raises ValueError -> returns default
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_json_decode_error_returns_default(self, mock_session_cls):
        mock_org = MagicMock()
        mock_org.configuration_json = "not-json"

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        mock_em.decrypt.return_value = "not-valid-json"

        cfg = storage.load_config()
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# save_config  -- Supabase path
# ---------------------------------------------------------------------------

class TestSaveConfigSupabase:
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_no_client_returns_early(self, mock_get_client):
        mock_get_client.return_value = None
        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        # No error raised

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.set_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_encrypt_failure_returns_early(self, mock_get_client, mock_set_cfg):
        mock_get_client.return_value = MagicMock()
        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = None
        storage.save_config(Config(storage_config=None))
        mock_set_cfg.assert_not_called()

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.set_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_set_org_config_failure(self, mock_get_client, mock_set_cfg):
        mock_get_client.return_value = MagicMock()
        mock_set_cfg.return_value = False
        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted"
        storage.save_config(Config(storage_config=None))
        mock_set_cfg.assert_called_once()

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.set_organization_config"
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
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

    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal",
        None,
    )
    @patch(
        "reflexio_ext.server.services.configurator.rds_config_storage.get_login_supabase_client"
    )
    def test_exception_logged(self, mock_get_client):
        mock_get_client.side_effect = RuntimeError("connection lost")
        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        # No exception propagated


# ---------------------------------------------------------------------------
# save_config  -- Session path
# ---------------------------------------------------------------------------

class TestSaveConfigSession:
    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_org_not_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_not_called()

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_encrypt_returns_none(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = None
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_not_called()

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_success_commits(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted-data"
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_called_once()
        assert mock_org.configuration_json == "encrypted-data"

    @patch("reflexio_ext.server.services.configurator.rds_config_storage.SessionLocal")
    def test_exception_during_commit(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("db down")
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_org

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted-data"
        # Should not propagate the exception
        storage.save_config(Config(storage_config=None))
