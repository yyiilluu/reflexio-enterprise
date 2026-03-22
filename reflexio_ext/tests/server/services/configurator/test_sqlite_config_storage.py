"""Tests for SqliteConfigStorage."""

from unittest.mock import MagicMock, patch

from reflexio_commons.config_schema import Config

_MOD = "reflexio_ext.server.services.configurator.sqlite_config_storage"


def _make_storage(org_id: str = "org-1"):
    """Create a SqliteConfigStorage with mocked EncryptManager."""
    with (
        patch(f"{_MOD}.FERNET_KEYS", "fake-key"),
        patch(f"{_MOD}.EncryptManager") as mock_encrypt_cls,
    ):
        mock_em = MagicMock()
        mock_encrypt_cls.return_value = mock_em
        from reflexio_ext.server.services.configurator.sqlite_config_storage import (
            SqliteConfigStorage,
        )

        storage = SqliteConfigStorage(org_id=org_id)
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
    @patch(f"{_MOD}.SessionLocal")
    def test_org_not_found_returns_default(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        storage, _ = _make_storage()
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(f"{_MOD}.SessionLocal")
    def test_org_found_with_config(self, mock_session_cls):
        raw_cfg = Config(storage_config=None)
        encrypted = "enc-data"

        mock_org = MagicMock()
        mock_org.configuration_json = encrypted

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        mock_em.decrypt.return_value = raw_cfg.model_dump_json()

        cfg = storage.load_config()
        mock_em.decrypt.assert_called_once_with(encrypted_value=encrypted)
        assert isinstance(cfg, Config)

    @patch(f"{_MOD}.SessionLocal")
    def test_org_config_is_none(self, mock_session_cls):
        mock_org = MagicMock()
        mock_org.configuration_json = None

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        # When config_raw_encrypted is None, decrypt is not called;
        # json.loads(str(None)) raises ValueError -> returns default
        cfg = storage.load_config()
        assert cfg.storage_config is None

    @patch(f"{_MOD}.SessionLocal")
    def test_json_decode_error_returns_default(self, mock_session_cls):
        mock_org = MagicMock()
        mock_org.configuration_json = "not-json"

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        mock_em.decrypt.return_value = "not-valid-json"

        cfg = storage.load_config()
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    @patch(f"{_MOD}.SessionLocal")
    def test_org_not_found(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        storage, _ = _make_storage()
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_not_called()

    @patch(f"{_MOD}.SessionLocal")
    def test_encrypt_returns_none(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = None
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_not_called()

    @patch(f"{_MOD}.SessionLocal")
    def test_success_commits(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted-data"
        storage.save_config(Config(storage_config=None))
        mock_session.commit.assert_called_once()
        assert mock_org.configuration_json == "encrypted-data"

    @patch(f"{_MOD}.SessionLocal")
    def test_exception_during_commit(self, mock_session_cls):
        mock_org = MagicMock()
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("db down")
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_org
        )

        storage, mock_em = _make_storage()
        mock_em.encrypt.return_value = "encrypted-data"
        # Should not propagate the exception
        storage.save_config(Config(storage_config=None))
