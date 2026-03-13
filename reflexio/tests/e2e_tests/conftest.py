"""Shared fixtures and utilities for end-to-end integration tests."""

import csv
import os

import pytest
from reflexio_commons.api_schema.service_schemas import (
    InteractionData,
    RawFeedback,
    UserActionType,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    AgentSuccessConfig,
    Config,
    FeedbackAggregatorConfig,
    ProfileExtractorConfig,
    StorageConfigSupabase,
    ToolUseConfig,
)

import reflexio.tests.test_data as test_data
from reflexio.reflexio_lib.reflexio_lib import Reflexio
from reflexio.server.services.configurator.configurator import SimpleConfigurator


@pytest.fixture
def supabase_storage_config() -> StorageConfigSupabase:
    """Create a StorageConfigSupabase instance with credentials from environment.

    Requires TEST_SUPABASE_URL, TEST_SUPABASE_KEY, and TEST_SUPABASE_DB_URL
    environment variables to be set.
    """
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    if not supabase_url or not supabase_key:
        pytest.skip(
            "TEST_SUPABASE_URL and TEST_SUPABASE_KEY environment variables must be set"
        )

    return StorageConfigSupabase(
        url=supabase_url,
        key=supabase_key,
        db_url=supabase_db_url,
    )


@pytest.fixture
def test_org_id(worker_id: str) -> str:
    """Test organization ID unique per worker to avoid parallel test conflicts.

    Uses pytest-xdist's worker_id fixture to create unique org IDs when running
    tests in parallel. For single-process runs, worker_id is 'master'.
    """
    return f"e2e_test_org_{worker_id}"


@pytest.fixture
def reflexio_instance(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with Supabase storage for testing."""
    # Set up configuration for profile extraction
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="test_profile_extractor",
                context_prompt="""
Conversation between sales agent and user, extract any information from the interaction if contains any information listed under definition
""",
                profile_content_definition_prompt="""
name, age, intent of the conversations
""",
                metadata_definition_prompt="""
choice of ['basic_info', 'conversation_intent']
""",
            )
        ],
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="test_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session. something sales rep did that makes user not satisfied.
feedback content is what agent should do differently in the next session based on the conversation history and be actionable as much as possible.
for example:
if user mentions "I don't like the way you talked to me", summarize conversation history and feedback content should be what is the way agent talk which is not preferred by user.
""",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=3,
                ),
            )
        ],
        agent_success_configs=[
            AgentSuccessConfig(
                evaluation_name="test_agent_success",
                success_definition_prompt="sales agent is responding to user apporperately",
            )
        ],
        tool_can_use=[
            ToolUseConfig(
                tool_name="search",
                tool_description="Search for information",
            )
        ],
    )
    # Create configurator with the config directly
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def reflexio_instance_profile_only(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with only profile extraction config."""
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="test_profile_extractor",
                context_prompt="""
Conversation between sales agent and user, extract any information from the interaction if contains any information listed under definition
""",
                profile_content_definition_prompt="""
name, age, intent of the conversations
""",
                metadata_definition_prompt="""
choice of ['basic_info', 'conversation_intent']
""",
            )
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def reflexio_instance_feedback_only(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with only agent feedback config."""
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="test_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session. something sales rep did that makes user not satisfied.
feedback content is what agent should do differently in the next session based on the conversation history and be actionable as much as possible.
for example:
if user mentions "I don't like the way you talked to me", summarize conversation history and feedback content should be what is the way agent talk which is not preferred by user.
""",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=3,
                ),
            )
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def reflexio_instance_agent_success_only(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with only agent success config."""
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        agent_success_configs=[
            AgentSuccessConfig(
                evaluation_name="test_agent_success",
                success_definition_prompt="sales agent is responding to user apporperately",
            )
        ],
        tool_can_use=[
            ToolUseConfig(
                tool_name="search",
                tool_description="Search for information",
            )
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def sample_interaction_requests() -> list[InteractionData]:
    """Create sample interaction requests for testing."""
    return [
        InteractionData(
            content="Hey, this is Sarah calling with TechCorp. How have you been?",
            role="Sales Rep",
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        ),
        InteractionData(
            content="I wanted to reach out to you about our new software solution. We helped you implement our previous system back in 2022, does that ring a bell?",
            role="Sales Rep",
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        ),
        InteractionData(
            content="Yes, I remember! The system has been working great for us. But i think you have being annoying me with your constant reach out.",
            role="Customer",
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        ),
    ]


def save_raw_feedbacks(reflexio_instance: Reflexio):
    """Load mock feedbacks from CSV file."""
    raw_feedbacks = []
    csv_path = os.path.join(os.path.dirname(test_data.__file__), "mock_feedbacks.csv")

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        raw_feedbacks.extend(
            RawFeedback(
                agent_version=row["agent_version"],
                request_id=row["request_id"],
                feedback_content=row["feedback_content"],
                feedback_name=row["feedback_name"],
            )
            for row in reader
        )
    reflexio_instance.request_context.storage.save_raw_feedbacks(raw_feedbacks)


def _get_feedback_names(instance: Reflexio) -> list[str]:
    """Extract feedback names from the Reflexio instance's config."""
    config = instance.request_context.configurator.get_config()
    if config and config.agent_feedback_configs:
        return [fc.feedback_name for fc in config.agent_feedback_configs]
    return []


def _cleanup_storage(instance: Reflexio):
    """Helper function to cleanup storage for an Reflexio instance."""
    try:
        # Only delete raw_feedbacks and feedbacks created by this instance's config
        for name in _get_feedback_names(instance):
            instance.request_context.storage.delete_all_raw_feedbacks_by_feedback_name(
                name
            )
            instance.request_context.storage.delete_all_feedbacks_by_feedback_name(name)
        instance.request_context.storage.delete_all_interactions()
        instance.request_context.storage.delete_all_profiles()
        instance.request_context.storage.delete_all_profile_change_logs()
        instance.request_context.storage.delete_all_agent_success_evaluation_results()
        instance.request_context.storage.delete_all_requests()
        instance.request_context.storage.delete_all_operation_states()
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")


@pytest.fixture
def cleanup_after_test(reflexio_instance):
    """Fixture to clean up test data before and after each test."""
    # Cleanup before test to ensure clean state
    _cleanup_storage(reflexio_instance)
    yield  # This allows the test to run
    # Cleanup after test
    _cleanup_storage(reflexio_instance)


@pytest.fixture
def cleanup_profile_only(reflexio_instance_profile_only):
    """Fixture to clean up test data for profile_only instance."""
    _cleanup_storage(reflexio_instance_profile_only)
    yield
    _cleanup_storage(reflexio_instance_profile_only)


@pytest.fixture
def cleanup_feedback_only(reflexio_instance_feedback_only):
    """Fixture to clean up test data for feedback_only instance."""
    _cleanup_storage(reflexio_instance_feedback_only)
    yield
    _cleanup_storage(reflexio_instance_feedback_only)


@pytest.fixture
def cleanup_agent_success_only(reflexio_instance_agent_success_only):
    """Fixture to clean up test data for agent_success_only instance."""
    _cleanup_storage(reflexio_instance_agent_success_only)
    yield
    _cleanup_storage(reflexio_instance_agent_success_only)


@pytest.fixture
def reflexio_instance_feedback_source_filtering(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with feedback configs using request_sources_enabled filtering."""
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        agent_feedback_configs=[
            # Feedback config only enabled for "api" source
            AgentFeedbackConfig(
                feedback_name="api_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session.
""",
                request_sources_enabled=["api"],
            ),
            # Feedback config only enabled for "webhook" source
            AgentFeedbackConfig(
                feedback_name="webhook_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session.
""",
                request_sources_enabled=["webhook"],
            ),
            # Feedback config enabled for all sources (no filter)
            AgentFeedbackConfig(
                feedback_name="all_sources_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session.
""",
                request_sources_enabled=None,
            ),
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_feedback_source_filtering(reflexio_instance_feedback_source_filtering):
    """Fixture to clean up test data for feedback source filtering instance."""
    _cleanup_storage(reflexio_instance_feedback_source_filtering)
    yield
    _cleanup_storage(reflexio_instance_feedback_source_filtering)


@pytest.fixture
def reflexio_instance_manual_profile(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with manual profile generation config.

    This config has:
    - extraction_window_size set (required for manual generation)
    - allow_manual_trigger=True on the extractor
    """
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        extraction_window_size=10,  # Required for manual generation
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="manual_trigger_extractor",
                context_prompt="""
Conversation between sales agent and user, extract any information from the interaction if contains any information listed under definition
""",
                profile_content_definition_prompt="""
name, age, intent of the conversations
""",
                metadata_definition_prompt="""
choice of ['basic_info', 'conversation_intent']
""",
                allow_manual_trigger=True,  # Required for manual generation
            )
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_manual_profile(reflexio_instance_manual_profile):
    """Fixture to clean up test data for manual profile instance."""
    _cleanup_storage(reflexio_instance_manual_profile)
    yield
    _cleanup_storage(reflexio_instance_manual_profile)


@pytest.fixture
def reflexio_instance_manual_feedback(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with manual feedback generation config.

    This config has:
    - extraction_window_size set (required for manual generation)
    - allow_manual_trigger=True on the extractor
    """
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        extraction_window_size=10,  # Required for manual generation
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="manual_trigger_feedback",
                feedback_definition_prompt="""
feedback should be something user told you to do differently in the next session. something sales rep did that makes user not satisfied.
feedback content is what agent should do differently in the next session based on the conversation history and be actionable as much as possible.
""",
                allow_manual_trigger=True,  # Required for manual generation
            )
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_manual_feedback(reflexio_instance_manual_feedback):
    """Fixture to clean up test data for manual feedback instance."""
    _cleanup_storage(reflexio_instance_manual_feedback)
    yield
    _cleanup_storage(reflexio_instance_manual_feedback)


@pytest.fixture
def reflexio_instance_multiple_profile_extractors(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with multiple profile extractors.

    This config has multiple extractors for testing extractor_names filtering:
    - extractor_basic_info: Extracts basic info
    - extractor_preferences: Extracts preferences
    - extractor_intent: Extracts conversation intent
    """
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        extraction_window_size=20,
        profile_extractor_configs=[
            ProfileExtractorConfig(
                extractor_name="extractor_basic_info",
                context_prompt="Extract basic information about the user.",
                profile_content_definition_prompt="name, company, role",
                metadata_definition_prompt="choice of ['basic_info']",
            ),
            ProfileExtractorConfig(
                extractor_name="extractor_preferences",
                context_prompt="Extract user preferences from the conversation.",
                profile_content_definition_prompt="communication style, preferred contact method",
                metadata_definition_prompt="choice of ['preferences']",
            ),
            ProfileExtractorConfig(
                extractor_name="extractor_intent",
                context_prompt="Extract user intent from the conversation.",
                profile_content_definition_prompt="conversation goal, buying intent",
                metadata_definition_prompt="choice of ['intent']",
            ),
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_multiple_profile_extractors(
    reflexio_instance_multiple_profile_extractors,
):
    """Fixture to clean up test data for multiple profile extractors instance."""
    _cleanup_storage(reflexio_instance_multiple_profile_extractors)
    yield
    _cleanup_storage(reflexio_instance_multiple_profile_extractors)


@pytest.fixture
def reflexio_instance_multiple_feedback_extractors(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create an Reflexio instance with multiple feedback extractors.

    This config has multiple extractors with different source filters:
    - api_only_feedback: Only runs for 'api' source
    - webhook_only_feedback: Only runs for 'webhook' source
    - general_feedback: Runs for all sources
    """
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        extraction_window_size=20,
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="api_only_feedback",
                feedback_definition_prompt="Extract feedback from API interactions.",
                request_sources_enabled=["api"],
            ),
            AgentFeedbackConfig(
                feedback_name="webhook_only_feedback",
                feedback_definition_prompt="Extract feedback from webhook interactions.",
                request_sources_enabled=["webhook"],
            ),
            AgentFeedbackConfig(
                feedback_name="general_feedback",
                feedback_definition_prompt="Extract general feedback from all sources.",
                request_sources_enabled=None,  # All sources
            ),
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_multiple_feedback_extractors(
    reflexio_instance_multiple_feedback_extractors,
):
    """Fixture to clean up test data for multiple feedback extractors instance."""
    _cleanup_storage(reflexio_instance_multiple_feedback_extractors)
    yield
    _cleanup_storage(reflexio_instance_multiple_feedback_extractors)
