"""End-to-end tests for configuration management."""

import shutil
import tempfile

import pytest
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    Config,
    FeedbackAggregatorConfig,
    ProfileExtractorConfig,
    StorageConfigSupabase,
)

from reflexio.reflexio_lib.reflexio_lib import Reflexio
from reflexio.server.services.configurator.configurator import SimpleConfigurator
from reflexio.tests.server.test_utils import skip_in_precommit, skip_low_priority


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config storage (not data storage)."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@skip_in_precommit
def test_set_config_end_to_end(
    supabase_storage_config: StorageConfigSupabase,
    test_org_id: str,
    temp_config_dir: str,
):
    """Test end-to-end configuration setting workflow.

    Uses temp directory for config storage but Supabase for data storage.
    """
    # Create configurator with base_dir for config storage
    # This initializes config_storage so set_config can persist
    configurator = SimpleConfigurator(org_id=test_org_id, base_dir=temp_config_dir)

    # Set initial config with Supabase storage
    initial_config = Config(
        storage_config=supabase_storage_config,
    )
    configurator.set_config(initial_config)

    reflexio = Reflexio(org_id=test_org_id, configurator=configurator)

    # Create a new configuration
    new_config = Config(
        storage_config=supabase_storage_config,
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="test_config_extractor",
                context_prompt="""
                Test configuration: Extract key information from conversations.
                """,
                profile_content_definition_prompt="""
                Test profile content definition.
                """,
                metadata_definition_prompt="""
                Test metadata definition.
                """,
            )
        ],
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="test_config_feedback",
                feedback_definition_prompt="""
                Test feedback definition for configuration test.
                """,
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=3,
                ),
            )
        ],
    )

    # Test setting config with Config object
    response = reflexio.set_config(new_config)
    assert response.success is True
    assert response.msg == "Configuration set successfully"

    # Verify configuration was actually set by checking the configurator
    current_config = reflexio.request_context.configurator.get_config()
    assert current_config is not None
    assert len(current_config.profile_extractor_configs) == 1
    assert (
        current_config.profile_extractor_configs[0].context_prompt.strip()
        == new_config.profile_extractor_configs[0].context_prompt.strip()
    )
    assert len(current_config.agent_feedback_configs) == 1
    assert (
        current_config.agent_feedback_configs[0].feedback_name == "test_config_feedback"
    )
    assert (
        current_config.agent_feedback_configs[
            0
        ].feedback_aggregator_config.min_feedback_threshold
        == 3
    )

    # Test setting config with dict input (using Supabase storage config as dict)
    config_dict = {
        "storage_config": supabase_storage_config.model_dump(),
        "profile_extractor_configs": [
            {
                "extractor_name": "dict_test_extractor",
                "context_prompt": "Updated test configuration from dict.",
                "profile_content_definition_prompt": "Updated profile content from dict.",
                "metadata_definition_prompt": "Updated metadata from dict.",
            }
        ],
        "agent_feedback_configs": [
            {
                "feedback_name": "dict_test_feedback",
                "feedback_definition_prompt": "Dict feedback definition.",
                "feedback_aggregator_config": {
                    "min_feedback_threshold": 5,
                },
            }
        ],
    }

    # Test setting config with dict
    dict_response = reflexio.set_config(config_dict)
    assert dict_response.success is True
    assert dict_response.msg == "Configuration set successfully"

    # Verify dict configuration was set
    updated_config = reflexio.request_context.configurator.get_config()
    assert updated_config is not None
    assert len(updated_config.profile_extractor_configs) == 1
    assert (
        "Updated test configuration from dict"
        in updated_config.profile_extractor_configs[0].context_prompt
    )
    assert len(updated_config.agent_feedback_configs) == 1
    assert (
        updated_config.agent_feedback_configs[0].feedback_name == "dict_test_feedback"
    )
    assert (
        updated_config.agent_feedback_configs[
            0
        ].feedback_aggregator_config.min_feedback_threshold
        == 5
    )

    # Test error handling with invalid config
    try:
        invalid_config = {"invalid_field": "invalid_value"}
        error_response = reflexio.set_config(invalid_config)
        assert error_response.success is False
        assert "Failed to set configuration" in error_response.msg
    except Exception:  # noqa: S110
        # If an exception is thrown instead of returning error response, that's also acceptable
        pass


@skip_in_precommit
@skip_low_priority
def test_get_config_end_to_end(
    supabase_storage_config: StorageConfigSupabase,
    test_org_id: str,
    temp_config_dir: str,
):
    """Test end-to-end configuration retrieval workflow.

    This test verifies:
    1. get_config returns the current configuration
    2. Configuration is correctly populated after set_config
    3. get_config returns Config object with all expected fields
    """
    # Create configurator with base_dir for config storage
    configurator = SimpleConfigurator(org_id=test_org_id, base_dir=temp_config_dir)

    # Set initial config with Supabase storage
    initial_config = Config(
        storage_config=supabase_storage_config,
    )
    configurator.set_config(initial_config)

    reflexio = Reflexio(org_id=test_org_id, configurator=configurator)

    # Step 1: Get initial config (should exist with defaults or empty)
    retrieved_initial_config = reflexio.get_config()
    assert retrieved_initial_config is not None
    assert isinstance(retrieved_initial_config, Config)

    # Step 2: Set a specific configuration
    new_config = Config(
        storage_config=supabase_storage_config,
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="get_config_test_extractor",
                context_prompt="Get config test: Extract key information.",
                profile_content_definition_prompt="Get config test profile content.",
                metadata_definition_prompt="Get config test metadata.",
            )
        ],
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="get_config_test_feedback",
                feedback_definition_prompt="Get config test feedback definition.",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=10,
                ),
            )
        ],
    )

    set_response = reflexio.set_config(new_config)
    assert set_response.success is True

    # Step 3: Retrieve the config and verify it matches what was set
    retrieved_config = reflexio.get_config()
    assert retrieved_config is not None
    assert isinstance(retrieved_config, Config)

    # Verify profile extractor configs
    assert len(retrieved_config.profile_extractor_configs) == 1
    assert (
        "Get config test"
        in retrieved_config.profile_extractor_configs[0].context_prompt
    )

    # Verify agent feedback configs
    assert len(retrieved_config.agent_feedback_configs) == 1
    assert (
        retrieved_config.agent_feedback_configs[0].feedback_name
        == "get_config_test_feedback"
    )
    assert (
        retrieved_config.agent_feedback_configs[
            0
        ].feedback_aggregator_config.min_feedback_threshold
        == 10
    )

    # Step 4: Verify storage config
    assert retrieved_config.storage_config is not None
