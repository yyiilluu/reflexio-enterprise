"""Tests for LocalJsonConfigStorage load/save and encryption."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from reflexio.server.services.configurator.local_json_config_storage import (
    LocalJsonConfigStorage,
)
from reflexio_commons.config_schema import Config, StorageConfigLocal


@pytest.fixture
def storage(tmp_path):
    """Create a LocalJsonConfigStorage with a temp directory and no encryption."""
    with patch(
        "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
        "",
    ):
        return LocalJsonConfigStorage(org_id="test_org", base_dir=str(tmp_path))


@pytest.fixture
def storage_with_encryption(tmp_path):
    """Create a LocalJsonConfigStorage with encryption enabled."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("utf-8")
    with patch(
        "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
        key,
    ):
        return LocalJsonConfigStorage(org_id="test_org", base_dir=str(tmp_path))


# ===============================
# Tests for load/save roundtrip
# ===============================


class TestLoadSaveRoundtrip:
    """Tests for load and save configuration roundtrip."""

    def test_save_and_load_preserves_config(self, storage):
        """Test that saving then loading a config preserves all fields."""
        config = Config(
            storage_config=StorageConfigLocal(dir_path="/test/path"),
            agent_context_prompt="test context",
        )

        storage.save_config(config)
        loaded = storage.load_config()

        assert isinstance(loaded.storage_config, StorageConfigLocal)
        assert loaded.storage_config.dir_path == "/test/path"
        assert loaded.agent_context_prompt == "test context"

    def test_multiple_save_load_cycles(self, storage):
        """Test multiple save/load cycles maintain data integrity."""
        for i in range(3):
            config = Config(
                storage_config=StorageConfigLocal(dir_path=f"/path/{i}"),
                agent_context_prompt=f"context_{i}",
            )
            storage.save_config(config)
            loaded = storage.load_config()
            assert loaded.agent_context_prompt == f"context_{i}"


# ===============================
# Tests for encryption/decryption
# ===============================


class TestEncryption:
    """Tests for encryption and decryption of config files."""

    def test_encrypted_file_not_plain_json(self, storage_with_encryption):
        """Test that saved config file is encrypted (not plain JSON)."""
        config = Config(
            storage_config=StorageConfigLocal(dir_path="/test"),
            agent_context_prompt="secret context",
        )

        storage_with_encryption.save_config(config)

        config_path = Path(storage_with_encryption.config_file)
        raw_content = config_path.read_text(encoding="utf-8")

        # Encrypted content should not be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw_content)

    def test_encrypted_roundtrip(self, storage_with_encryption):
        """Test that encrypted save/load preserves config."""
        config = Config(
            storage_config=StorageConfigLocal(dir_path="/encrypted/path"),
            agent_context_prompt="encrypted context",
        )

        storage_with_encryption.save_config(config)
        loaded = storage_with_encryption.load_config()

        assert loaded.agent_context_prompt == "encrypted context"
        assert isinstance(loaded.storage_config, StorageConfigLocal)
        assert loaded.storage_config.dir_path == "/encrypted/path"


# ===============================
# Tests for file-not-exists creates default config
# ===============================


class TestDefaultConfig:
    """Tests for default config creation."""

    def test_file_not_exists_creates_default(self, storage):
        """Test that loading when file doesn't exist creates default config."""
        config = storage.load_config()

        assert isinstance(config.storage_config, StorageConfigLocal)
        assert config.agent_context_prompt is None
        # Config file should have been created
        assert Path(storage.config_file).exists()

    def test_default_config_storage_dir_path(self, storage):
        """Test that default config has the storage base_dir as dir_path."""
        config = storage.get_default_config()
        assert isinstance(config.storage_config, StorageConfigLocal)
        # dir_path should be set to the base_dir (configs subdirectory)
        assert config.storage_config.dir_path == storage.base_dir


# ===============================
# Tests for invalid JSON returns default config
# ===============================


class TestInvalidJson:
    """Tests for handling invalid JSON in config files."""

    def test_invalid_json_returns_default(self, storage):
        """Test that invalid JSON in config file returns default config."""
        Path(storage.base_dir).mkdir(parents=True, exist_ok=True)
        Path(storage.config_file).write_text(
            "this is not valid json{{{", encoding="utf-8"
        )

        config = storage.load_config()

        assert isinstance(config.storage_config, StorageConfigLocal)

    def test_empty_file_returns_default(self, storage):
        """Test that empty config file returns default config."""
        Path(storage.base_dir).mkdir(parents=True, exist_ok=True)
        Path(storage.config_file).write_text("", encoding="utf-8")

        config = storage.load_config()

        assert isinstance(config.storage_config, StorageConfigLocal)


# ===============================
# Tests for path resolution
# ===============================


class TestPathResolution:
    """Tests for path resolution in LocalJsonConfigStorage."""

    def test_absolute_path_used_as_is(self, tmp_path):
        """Test that absolute base_dir is used as-is."""
        abs_path = str(tmp_path / "my_configs")
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            "",
        ):
            storage = LocalJsonConfigStorage(org_id="org1", base_dir=abs_path)
        assert storage.base_dir == str(Path(abs_path) / "configs")
        assert "org1" in storage.config_file

    def test_relative_path_resolved_to_absolute(self):
        """Test that relative base_dir is resolved to absolute."""
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            "",
        ):
            storage = LocalJsonConfigStorage(org_id="org2", base_dir="relative/path")
        # Should be resolved to absolute path
        assert Path(storage.base_dir).is_absolute()

    def test_no_base_dir_uses_data_package(self):
        """Test that no base_dir falls back to data package directory."""
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            "",
        ):
            storage = LocalJsonConfigStorage(org_id="org3")
        assert "configs" in storage.base_dir
        assert Path(storage.base_dir).is_absolute()


# ===============================
# Tests for save with no base_dir configured
# ===============================


class TestSaveEdgeCases:
    """Tests for save_config edge cases."""

    def test_save_when_base_dir_and_config_file_set(self, storage):
        """Test that saving works when base_dir and config_file are both set."""
        config = Config(storage_config=StorageConfigLocal(dir_path="/test"))
        storage.save_config(config)

        assert Path(storage.config_file).exists()

    def test_save_config_to_local_dir_raises_when_no_paths(self):
        """Test that _save_config_to_local_dir raises when base_dir/config_file unset."""
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            "",
        ):
            storage = LocalJsonConfigStorage(org_id="org_test")
        # Manually unset to test the guard
        original_base = storage.base_dir
        original_file = storage.config_file
        storage.base_dir = ""
        storage.config_file = ""

        config = Config(storage_config=StorageConfigLocal(dir_path="/test"))
        with pytest.raises(ValueError, match="base_dir and config_file must be set"):
            storage._save_config_to_local_dir(config)

        storage.base_dir = original_base
        storage.config_file = original_file

    def test_save_config_prints_when_no_base_dir(self, capsys):
        """Test that save_config prints a message when base_dir is empty."""
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            "",
        ):
            storage = LocalJsonConfigStorage(org_id="org_test")
        storage.base_dir = ""
        storage.config_file = ""

        config = Config(storage_config=StorageConfigLocal(dir_path="/test"))
        storage.save_config(config)

        captured = capsys.readouterr()
        assert "Cannot save config" in captured.out


# ===============================
# Tests for exception handling during save/load
# ===============================


class TestExceptionHandling:
    """Tests for exception handling in save and load operations."""

    def test_load_with_corrupted_encrypted_data_returns_default(self, tmp_path):
        """Test that corrupted encrypted data returns default config."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode("utf-8")
        with patch(
            "reflexio.server.services.configurator.local_json_config_storage.FERNET_KEYS",
            key,
        ):
            storage = LocalJsonConfigStorage(org_id="org_test", base_dir=str(tmp_path))

        # Write corrupted data that will fail decryption
        Path(storage.base_dir).mkdir(parents=True, exist_ok=True)
        Path(storage.config_file).write_text("corrupted_data", encoding="utf-8")

        config = storage.load_config()
        # Should fall back to default config
        assert isinstance(config.storage_config, StorageConfigLocal)
