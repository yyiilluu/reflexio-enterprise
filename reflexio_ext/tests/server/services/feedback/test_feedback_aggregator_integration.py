import contextlib
import csv
import os
import tempfile
from unittest.mock import patch

import pytest
import reflexio.tests.test_data as test_data
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio.server.services.storage.supabase_storage import SupabaseStorage
from reflexio.tests.server.test_utils import skip_in_precommit, skip_low_priority
from reflexio_commons.api_schema.service_schemas import (
    Feedback,
    FeedbackStatus,
    RawFeedback,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
    StorageConfigSupabase,
)


@pytest.fixture
def supabase_storage():
    """Create a SupabaseStorage instance with real credentials from environment.

    Requires TEST_SUPABASE_URL, TEST_SUPABASE_KEY, and TEST_SUPABASE_DB_URL
    environment variables to be set for integration tests.
    """
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    if not supabase_url or not supabase_key:
        pytest.skip(
            "TEST_SUPABASE_URL and TEST_SUPABASE_KEY environment variables must be set"
        )

    config = StorageConfigSupabase(
        url=supabase_url,
        key=supabase_key,
        db_url=supabase_db_url,
    )
    storage = SupabaseStorage(org_id="test", config=config)
    return storage  # noqa: RET504


TEST_FEEDBACK_NAME = "test_feedback"


@pytest.fixture
def cleanup_after_test(supabase_storage):
    """Fixture to clean up test data after each test."""
    yield  # This allows the test to run
    try:
        # Only delete feedbacks and raw_feedbacks created by this test file
        supabase_storage.client.table("feedbacks").delete().eq(
            "feedback_name", TEST_FEEDBACK_NAME
        ).execute()
        supabase_storage.client.table("raw_feedbacks").delete().eq(
            "feedback_name", TEST_FEEDBACK_NAME
        ).execute()
        print("Test data cleaned up successfully")
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")


@pytest.fixture
def llm_client():
    """Create a LiteLLMClient instance for testing."""
    config = LiteLLMConfig(model="gpt-4o-mini")
    return LiteLLMClient(config)


def load_mock_feedbacks():
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
    return raw_feedbacks


@pytest.fixture
def setup_mock_feedbacks(supabase_storage, cleanup_after_test):
    """Fixture to load and save mock feedbacks before each test."""
    # Clean up any existing test raw_feedbacks first to ensure a clean state
    with contextlib.suppress(Exception):
        supabase_storage.client.table("raw_feedbacks").delete().eq(
            "feedback_name", TEST_FEEDBACK_NAME
        ).execute()

    # Load mock feedbacks from CSV
    raw_feedbacks = load_mock_feedbacks()
    assert len(raw_feedbacks) == 20  # Verify we loaded all 20 feedbacks

    # Save feedbacks to storage
    supabase_storage.save_raw_feedbacks(raw_feedbacks)

    # Verify feedbacks were saved
    loaded_feedbacks = supabase_storage.get_raw_feedbacks()
    assert len(loaded_feedbacks) == 20

    return loaded_feedbacks


@pytest.fixture
def disable_mock_llm_response(monkeypatch):
    """Disable MOCK_LLM_RESPONSE env var so tests use real clustering."""
    monkeypatch.delenv("MOCK_LLM_RESPONSE", raising=False)


@skip_in_precommit
def test_feedback_aggregator_get_clusters(
    supabase_storage, setup_mock_feedbacks, llm_client, disable_mock_llm_response
):
    # Get the loaded feedbacks from the fixture
    loaded_feedbacks = setup_mock_feedbacks

    # Initialize feedback aggregator with proper credentials from environment
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    request_context = RequestContext(org_id="test")
    request_context.configurator.set_config_by_name(
        "storage_config",
        StorageConfigSupabase(
            url=supabase_url,
            key=supabase_key,
            db_url=supabase_db_url,
        ),
    )
    feedback_aggregator = FeedbackAggregator(
        llm_client=llm_client,
        request_context=request_context,
        agent_version="1.0.0",
    )

    # Run aggregation
    clusters = feedback_aggregator.get_clusters(
        raw_feedbacks=loaded_feedbacks,
        feedback_aggregator_config=FeedbackAggregatorConfig(
            min_feedback_threshold=2,  # Set to 2 since we expect clusters of 5
        ),
    )

    assert len(clusters) > 1, "Expected at least 2 clusters"


@pytest.fixture
def mock_chat_completion():
    # Mock for feedback generation call - patch generate_chat_response which returns string directly
    mock_content = "The agent was helpful and provided accurate information"

    with patch(
        "reflexio.server.llm.litellm_client.LiteLLMClient.generate_chat_response",
        return_value=mock_content,
    ):
        yield


@skip_in_precommit
def test_feedback_aggregator_run(
    supabase_storage, mock_chat_completion, setup_mock_feedbacks, llm_client
):
    """Test the feedback aggregator's run method with a temporary storage."""
    org_id = "0"

    with tempfile.TemporaryDirectory() as temp_dir:
        request_context = RequestContext(org_id=org_id, storage_base_dir=temp_dir)
        request_context.configurator.set_config_by_name(
            "storage_config",
            StorageConfigSupabase(
                url="",
                key="",
                db_url="",
            ),
        )

        request_context.configurator.set_config_by_name(
            "agent_feedback_configs",
            [
                AgentFeedbackConfig(
                    feedback_name="test_feedback",
                    feedback_definition_prompt="",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                )
            ],
        )

        request_context.storage = supabase_storage
        feedback_aggregator = FeedbackAggregator(
            llm_client=llm_client,
            request_context=request_context,
            agent_version="1.0.0",
        )
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version="1.0.0",
            feedback_name="test_feedback",
        )
        feedback_aggregator.run(feedback_aggregator_request)
        saved_feedbacks = feedback_aggregator.storage.get_feedbacks()
        assert len(saved_feedbacks) > 0
        for feedback in saved_feedbacks:
            assert isinstance(feedback, Feedback)
            assert feedback.agent_version == "1.0.0"
            assert feedback.feedback_status == FeedbackStatus.PENDING
            assert feedback.feedback_content is not None
            assert len(feedback.feedback_content) > 0
            assert isinstance(feedback.feedback_metadata, str)


@skip_in_precommit
@skip_low_priority
def test_feedback_aggregator_run_with_insufficient_feedback(
    supabase_storage, mock_chat_completion, cleanup_after_test, llm_client
):
    """Test the feedback aggregator's run method with insufficient feedback for clustering."""
    org_id = "0"
    # Create single raw feedback (insufficient for clustering)
    raw_feedbacks = [
        RawFeedback(
            agent_version="1.0.0",
            request_id="1",
            feedback_content="The agent was very helpful",
            embedding=[0.1] * 512,
            feedback_name="test_feedback",
        ),
    ]
    with tempfile.TemporaryDirectory() as temp_dir:
        request_context = RequestContext(org_id=org_id, storage_base_dir=temp_dir)
        request_context.configurator.set_config_by_name(
            "storage_config",
            StorageConfigSupabase(
                url="",
                key="",
                db_url="",
            ),
        )
        request_context.configurator.set_config_by_name(
            "agent_feedback_configs",
            [
                AgentFeedbackConfig(
                    feedback_name="test_feedback",
                    feedback_definition_prompt="",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                )
            ],
        )

        request_context.storage = supabase_storage
        supabase_storage.save_raw_feedbacks(raw_feedbacks)
        feedback_aggregator = FeedbackAggregator(
            llm_client=llm_client,
            request_context=request_context,
            agent_version="1.0.0",
        )
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version="1.0.0",
            feedback_name="test_feedback",
        )
        feedback_aggregator.run(feedback_aggregator_request)
        saved_feedbacks = feedback_aggregator.storage.get_feedbacks()
        assert len(saved_feedbacks) == 0


@skip_in_precommit
@skip_low_priority
def test_feedback_aggregator_run_with_empty_feedback(
    supabase_storage, mock_chat_completion, llm_client
):
    """Test the feedback aggregator's run method with empty feedback list."""
    org_id = "0"
    with tempfile.TemporaryDirectory() as temp_dir:
        request_context = RequestContext(org_id=org_id, storage_base_dir=temp_dir)
        request_context.configurator.set_config_by_name(
            "storage_config",
            StorageConfigSupabase(
                url="",
                key="",
                db_url="",
            ),
        )
        request_context.configurator.set_config_by_name(
            "agent_feedback_configs",
            [
                AgentFeedbackConfig(
                    feedback_name="test_feedback",
                    feedback_definition_prompt="",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                )
            ],
        )

        request_context.storage = supabase_storage
        # Save no feedbacks to storage
        feedback_aggregator = FeedbackAggregator(
            llm_client=llm_client,
            request_context=request_context,
            agent_version="1.0.0",
        )
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version="1.0.0",
            feedback_name="test_feedback",
        )
        feedback_aggregator.run(feedback_aggregator_request)
        saved_feedbacks = feedback_aggregator.storage.get_feedbacks()
        assert len(saved_feedbacks) == 0


if __name__ == "__main__":
    pytest.main([__file__])
