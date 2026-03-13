import json
import os

import pytest
from reflexio_commons.config_schema import (
    Config,
    ProfileExtractorConfig,
    StorageConfigLocal,
    StorageConfigSupabase,
)

from reflexio.server.services.configurator.configurator import SimpleConfigurator


@pytest.fixture
def temp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def test_org_id():
    return "test_org"


@pytest.fixture
def configurator(temp_dir, test_org_id):
    return SimpleConfigurator(org_id=test_org_id, base_dir=temp_dir)


def test_init_creates_config_file(temp_dir, test_org_id):
    # Test that initialization creates config file if it doesn't exist
    _config = SimpleConfigurator(org_id=test_org_id, base_dir=temp_dir)
    config_file = os.path.join(temp_dir, "configs", f"config_{test_org_id}.json")

    assert os.path.exists(config_file)
    with open(config_file, encoding="utf-8") as f:
        loaded_config = Config.model_validate(json.load(f))
        assert isinstance(loaded_config.storage_config, StorageConfigLocal)
        assert not loaded_config.profile_extractor_configs


def test_get_config_with_default(configurator):
    # Test getting non-existent config returns default value
    config = configurator.get_config()
    # Since get_config() returns the full Config object, we can check if a field exists
    # or has a default value by accessing it directly
    assert hasattr(config, "storage_config")
    assert isinstance(config.storage_config, StorageConfigLocal)


def test_set_and_get_config_by_name(configurator):
    # Test setting and getting config values using set_config_by_name
    test_cases = [
        (
            "storage_config",
            StorageConfigSupabase(
                url="https://test.supabase.co",
                key="test_key",
                db_url="postgresql://test:test@localhost:5432/test",
            ),
        ),
        (
            "profile_extractor_configs",
            [
                ProfileExtractorConfig(
                    extractor_name="test_extractor",
                    should_extract_profile_prompt_override="test",
                    context_prompt="test",
                    profile_content_definition_prompt="test",
                    metadata_definition_prompt="test",
                )
            ],
        ),
    ]

    for key, value in test_cases:
        configurator.set_config_by_name(key, value)
        config = configurator.get_config()
        assert getattr(config, key) == value


def test_config_persistence(temp_dir, test_org_id):
    # Test that config values persist after recreating the configurator
    config1 = SimpleConfigurator(org_id=test_org_id, base_dir=temp_dir)
    new_config = Config(
        storage_config=StorageConfigSupabase(
            url="https://test.supabase.co",
            key="test_key",
            db_url="postgresql://test:test@localhost:5432/test",
        ),
        profile_extractor_configs=[],
    )
    config1.set_config(new_config)

    # Create new instance to read from the same file
    config2 = SimpleConfigurator(org_id=test_org_id, base_dir=temp_dir)
    assert isinstance(config2.config.storage_config, StorageConfigSupabase)
    assert config2.config.storage_config.url == "https://test.supabase.co"


if __name__ == "__main__":
    pytest.main(["-v", __file__, "-k", "test_init_creates_config_file"])
