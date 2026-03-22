"""Tests for S3ConfigStorage."""

from unittest.mock import MagicMock, patch

from reflexio_commons.config_schema import Config


# Patch module-level constants before importing the class
_PATCHES = {
    "reflexio_ext.server.services.configurator.s3_config_storage.CONFIG_S3_PATH": "test-bucket",
    "reflexio_ext.server.services.configurator.s3_config_storage.CONFIG_S3_REGION": "us-west-2",
    "reflexio_ext.server.services.configurator.s3_config_storage.CONFIG_S3_ACCESS_KEY": "AKIA-FAKE",
    "reflexio_ext.server.services.configurator.s3_config_storage.CONFIG_S3_SECRET_KEY": "secret",
    "reflexio_ext.server.services.configurator.s3_config_storage.FERNET_KEYS": "",
}


def _make_storage(org_id: str = "org-42", fernet_keys: str = ""):
    """Create an S3ConfigStorage with mocked S3Utils and optional EncryptManager."""
    patches = {**_PATCHES, "reflexio_ext.server.services.configurator.s3_config_storage.FERNET_KEYS": fernet_keys}
    ctx_managers = [patch(k, v) for k, v in patches.items()]
    for cm in ctx_managers:
        cm.start()

    with patch(
        "reflexio_ext.server.services.configurator.s3_config_storage.S3Utils"
    ) as MockS3, patch(
        "reflexio_ext.server.services.configurator.s3_config_storage.EncryptManager"
    ) as MockEncrypt:
        mock_s3 = MagicMock()
        MockS3.return_value = mock_s3

        mock_em = MagicMock()
        MockEncrypt.return_value = mock_em

        from reflexio_ext.server.services.configurator.s3_config_storage import (
            S3ConfigStorage,
        )

        storage = S3ConfigStorage(org_id=org_id)

    for cm in ctx_managers:
        cm.stop()

    return storage, mock_s3, mock_em


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_config_file_key(self):
        storage, _, _ = _make_storage(org_id="my-org")
        assert storage.config_file_key == "configs/config_my-org.json"

    def test_no_fernet_keys_means_no_encrypt_manager(self):
        storage, _, _ = _make_storage(fernet_keys="")
        assert storage.encrypt_manager is None

    def test_fernet_keys_creates_encrypt_manager(self):
        storage, _, mock_em = _make_storage(fernet_keys="some-fernet-key")
        assert storage.encrypt_manager is not None


# ---------------------------------------------------------------------------
# get_default_config
# ---------------------------------------------------------------------------

class TestGetDefaultConfig:
    def test_returns_config_with_none_storage(self):
        storage, _, _ = _make_storage()
        cfg = storage.get_default_config()
        assert isinstance(cfg, Config)
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_file_not_exists_returns_default(self):
        storage, mock_s3, _ = _make_storage()
        mock_s3.file_exists.return_value = False
        cfg = storage.load_config()
        assert cfg.storage_config is None
        mock_s3.file_exists.assert_called_once_with(storage.config_file_key)

    def test_empty_body_returns_default(self):
        storage, mock_s3, _ = _make_storage()
        mock_s3.file_exists.return_value = True
        body = MagicMock()
        body.read.return_value = b""
        mock_s3.s3_client.get_object.return_value = {"Body": body}
        cfg = storage.load_config()
        assert cfg.storage_config is None

    def test_load_without_encryption(self):
        raw_cfg = Config(storage_config=None)
        storage, mock_s3, _ = _make_storage()
        storage.encrypt_manager = None
        mock_s3.file_exists.return_value = True
        body = MagicMock()
        body.read.return_value = raw_cfg.model_dump_json().encode("utf-8")
        mock_s3.s3_client.get_object.return_value = {"Body": body}

        cfg = storage.load_config()
        assert isinstance(cfg, Config)

    def test_load_with_encryption(self):
        raw_cfg = Config(storage_config=None)
        storage, mock_s3, mock_em = _make_storage(fernet_keys="key")
        mock_s3.file_exists.return_value = True
        body = MagicMock()
        body.read.return_value = b"encrypted-blob"
        mock_s3.s3_client.get_object.return_value = {"Body": body}
        mock_em.decrypt.return_value = raw_cfg.model_dump_json()

        cfg = storage.load_config()
        mock_em.decrypt.assert_called_once_with(encrypted_value="encrypted-blob")
        assert isinstance(cfg, Config)

    def test_exception_returns_default(self):
        storage, mock_s3, _ = _make_storage()
        mock_s3.file_exists.side_effect = RuntimeError("network")
        cfg = storage.load_config()
        assert cfg.storage_config is None


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------

class TestSaveConfig:
    def test_save_without_encryption(self):
        storage, mock_s3, _ = _make_storage()
        storage.encrypt_manager = None
        cfg = Config(storage_config=None)

        storage.save_config(cfg)
        mock_s3.s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3.s3_client.put_object.call_args
        assert call_kwargs.kwargs.get("Key") or call_kwargs[1].get("Key") == storage.config_file_key

    def test_save_with_encryption(self):
        storage, mock_s3, mock_em = _make_storage(fernet_keys="key")
        mock_em.encrypt.return_value = "encrypted-out"
        cfg = Config(storage_config=None)

        storage.save_config(cfg)
        mock_em.encrypt.assert_called_once()
        mock_s3.s3_client.put_object.assert_called_once()

    def test_save_exception_does_not_propagate(self):
        storage, mock_s3, _ = _make_storage()
        storage.encrypt_manager = None
        mock_s3.s3_client.put_object.side_effect = RuntimeError("write fail")
        storage.save_config(Config(storage_config=None))
