"""
Tests for feedback archival system.

This module tests the archival, restoration, and deletion of feedbacks
using the status field during feedback aggregation.
"""

import contextlib
import os
import tempfile

import pytest
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

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio.server.services.storage.supabase_storage import SupabaseStorage
from reflexio.tests.server.test_utils import skip_in_precommit, skip_low_priority


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
    storage = SupabaseStorage(org_id="test_archival", config=config)
    return storage  # noqa: RET504


TEST_FEEDBACK_NAMES = [
    "test_archival",
    "test_restore",
    "test_delete",
    "test_aggregation",
    "test_error",
]


@pytest.fixture
def cleanup_after_test(supabase_storage):
    """Fixture to clean up test data before and after each test."""

    def _cleanup():
        try:
            # Only delete feedbacks and raw_feedbacks created by this test file
            supabase_storage.client.table("feedbacks").delete().in_(
                "feedback_name", TEST_FEEDBACK_NAMES
            ).execute()
            supabase_storage.client.table("raw_feedbacks").delete().in_(
                "feedback_name", TEST_FEEDBACK_NAMES
            ).execute()
            # Clean up operation state entries for aggregation tests
            for feedback_name in TEST_FEEDBACK_NAMES:
                for org_id in ["test_org", "test_archival"]:
                    for version in ["1.0.0"]:
                        base_key = (
                            f"feedback_aggregator::{org_id}::{feedback_name}::{version}"
                        )
                        for key in [base_key, f"{base_key}::clusters"]:
                            with contextlib.suppress(Exception):
                                supabase_storage.delete_operation_state(key)
            print("Test data cleaned up successfully")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def llm_client():
    """Create a LiteLLMClient instance for testing."""
    config = LiteLLMConfig(model="gpt-4o-mini")
    return LiteLLMClient(config)


@skip_in_precommit
def test_archive_feedbacks_by_feedback_name(supabase_storage, cleanup_after_test):
    """Test archiving feedbacks by feedback name."""
    # Create and save test feedbacks
    feedbacks = [
        Feedback(
            feedback_name="test_archival",
            agent_version="1.0.0",
            feedback_content="Test feedback 1",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.1] * 512,
        ),
        Feedback(
            feedback_name="test_archival",
            agent_version="1.0.0",
            feedback_content="Test feedback 2",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.2] * 512,
        ),
    ]
    supabase_storage.save_feedbacks(feedbacks)

    # Verify feedbacks were saved
    saved_feedbacks = supabase_storage.get_feedbacks(feedback_name="test_archival")
    assert len(saved_feedbacks) == 2

    # Archive feedbacks
    supabase_storage.archive_feedbacks_by_feedback_name(
        "test_archival", agent_version="1.0.0"
    )

    # Verify archived feedbacks are excluded from get_feedbacks
    active_feedbacks = supabase_storage.get_feedbacks(feedback_name="test_archival")
    assert len(active_feedbacks) == 0


@skip_in_precommit
@skip_low_priority
def test_restore_archived_feedbacks(supabase_storage, cleanup_after_test):
    """Test restoring archived feedbacks."""
    # Create and save test feedbacks
    feedbacks = [
        Feedback(
            feedback_name="test_restore",
            agent_version="1.0.0",
            feedback_content="Test feedback 1",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.1] * 512,
        ),
    ]
    supabase_storage.save_feedbacks(feedbacks)

    # Archive feedbacks
    supabase_storage.archive_feedbacks_by_feedback_name(
        "test_restore", agent_version="1.0.0"
    )

    # Verify archived
    active_feedbacks = supabase_storage.get_feedbacks(feedback_name="test_restore")
    assert len(active_feedbacks) == 0

    # Restore archived feedbacks
    supabase_storage.restore_archived_feedbacks_by_feedback_name(
        "test_restore", agent_version="1.0.0"
    )

    # Verify restored feedbacks are now active
    restored_feedbacks = supabase_storage.get_feedbacks(feedback_name="test_restore")
    assert len(restored_feedbacks) == 1
    assert restored_feedbacks[0].feedback_content == "Test feedback 1"


@skip_in_precommit
@skip_low_priority
def test_delete_archived_feedbacks(supabase_storage, cleanup_after_test):
    """Test permanently deleting archived feedbacks."""
    # Create and save test feedbacks
    feedbacks = [
        Feedback(
            feedback_name="test_delete",
            agent_version="1.0.0",
            feedback_content="Test feedback 1",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.1] * 512,
        ),
        Feedback(
            feedback_name="test_delete",
            agent_version="1.0.0",
            feedback_content="Test feedback 2",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.2] * 512,
        ),
    ]
    supabase_storage.save_feedbacks(feedbacks)

    # Archive feedbacks
    supabase_storage.archive_feedbacks_by_feedback_name(
        "test_delete", agent_version="1.0.0"
    )

    # Delete archived feedbacks
    supabase_storage.delete_archived_feedbacks_by_feedback_name(
        "test_delete", agent_version="1.0.0"
    )

    # Verify feedbacks were permanently deleted
    # Query directly from database to check archived feedbacks are gone
    response = (
        supabase_storage.client.table("feedbacks")
        .select("*")
        .eq("feedback_name", "test_delete")
        .execute()
    )
    assert len(response.data) == 0


@skip_in_precommit
def test_aggregator_archives_then_deletes_on_success(
    supabase_storage, cleanup_after_test, llm_client
):
    """Test that aggregator archives feedbacks before processing and deletes after success."""
    org_id = "test_org"

    # Create existing feedbacks that should be archived
    existing_feedbacks = [
        Feedback(
            feedback_name="test_aggregation",
            agent_version="1.0.0",
            feedback_content="Old feedback 1",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.1] * 512,
        ),
        Feedback(
            feedback_name="test_aggregation",
            agent_version="1.0.0",
            feedback_content="Old feedback 2",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.2] * 512,
        ),
    ]
    supabase_storage.save_feedbacks(existing_feedbacks)

    # Create raw feedbacks for aggregation
    raw_feedbacks = [
        RawFeedback(
            agent_version="1.0.0",
            request_id="1",
            feedback_content="New feedback 1",
            embedding=[0.3] * 512,
            feedback_name="test_aggregation",
        ),
        RawFeedback(
            agent_version="1.0.0",
            request_id="2",
            feedback_content="New feedback 2",
            embedding=[0.4] * 512,
            feedback_name="test_aggregation",
        ),
        RawFeedback(
            agent_version="1.0.0",
            request_id="3",
            feedback_content="New feedback 3",
            embedding=[0.5] * 512,
            feedback_name="test_aggregation",
        ),
    ]
    supabase_storage.save_raw_feedbacks(raw_feedbacks)

    # Setup request context
    with tempfile.TemporaryDirectory() as temp_dir:
        request_context = RequestContext(org_id=org_id, storage_base_dir=temp_dir)
        request_context.configurator.set_config_by_name(
            "storage_config",
            StorageConfigSupabase(
                url="http://placeholder",
                key="placeholder",
                db_url="postgresql://placeholder",
            ),
        )
        request_context.configurator.set_config_by_name(
            "agent_feedback_configs",
            [
                AgentFeedbackConfig(
                    feedback_name="test_aggregation",
                    feedback_definition_prompt="test feedback definition",
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

        # Run aggregation
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version="1.0.0",
            feedback_name="test_aggregation",
        )
        feedback_aggregator.run(feedback_aggregator_request)

        # Verify:
        # 1. New feedbacks were created
        saved_feedbacks = supabase_storage.get_feedbacks(
            feedback_name="test_aggregation"
        )
        assert len(saved_feedbacks) > 0, "New feedbacks should be created"
        for feedback in saved_feedbacks:
            assert feedback.feedback_content not in (
                "Old feedback 1",
                "Old feedback 2",
            ), "Old feedbacks should not be present"

        # 2. Old feedbacks were deleted (not just archived)
        response = (
            supabase_storage.client.table("feedbacks")
            .select("*")
            .eq("feedback_name", "test_aggregation")
            .eq("status", "archived")
            .execute()
        )
        assert len(response.data) == 0, (
            "Archived feedbacks should be permanently deleted"
        )


@skip_in_precommit
@skip_low_priority
def test_aggregator_restores_on_error(supabase_storage, cleanup_after_test, llm_client):
    """Test that aggregator restores archived feedbacks when an error occurs."""
    org_id = "test_org"

    # Create existing feedbacks
    existing_feedbacks = [
        Feedback(
            feedback_name="test_error",
            agent_version="1.0.0",
            feedback_content="Original feedback 1",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.1] * 512,
        ),
        Feedback(
            feedback_name="test_error",
            agent_version="1.0.0",
            feedback_content="Original feedback 2",
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
            embedding=[0.2] * 512,
        ),
    ]
    supabase_storage.save_feedbacks(existing_feedbacks)

    # Create raw feedbacks (need at least 2 for min_feedback_threshold)
    raw_feedbacks = [
        RawFeedback(
            agent_version="1.0.0",
            request_id="1",
            feedback_content="New feedback 1",
            embedding=[0.3] * 512,
            feedback_name="test_error",
        ),
        RawFeedback(
            agent_version="1.0.0",
            request_id="2",
            feedback_content="New feedback 2",
            embedding=[0.4] * 512,
            feedback_name="test_error",
        ),
    ]
    supabase_storage.save_raw_feedbacks(raw_feedbacks)

    # Setup request context
    with tempfile.TemporaryDirectory() as temp_dir:
        request_context = RequestContext(org_id=org_id, storage_base_dir=temp_dir)
        request_context.configurator.set_config_by_name(
            "storage_config",
            StorageConfigSupabase(
                url="http://placeholder",
                key="placeholder",
                db_url="postgresql://placeholder",
            ),
        )
        request_context.configurator.set_config_by_name(
            "agent_feedback_configs",
            [
                AgentFeedbackConfig(
                    feedback_name="test_error",
                    feedback_definition_prompt="test feedback definition",
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

        # Mock the save_feedbacks to raise an error
        original_save = supabase_storage.save_feedbacks

        def mock_save_error(feedbacks):
            raise Exception("Simulated save error")

        supabase_storage.save_feedbacks = mock_save_error

        # Run aggregation and expect error
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version="1.0.0",
            feedback_name="test_error",
        )

        with pytest.raises(Exception, match="Simulated save error"):
            feedback_aggregator.run(feedback_aggregator_request)

        # Restore original method
        supabase_storage.save_feedbacks = original_save

        # Verify original feedbacks were restored
        restored_feedbacks = supabase_storage.get_feedbacks(feedback_name="test_error")
        assert len(restored_feedbacks) == 2, "Original feedbacks should be restored"
        feedback_contents = [f.feedback_content for f in restored_feedbacks]
        assert "Original feedback 1" in feedback_contents
        assert "Original feedback 2" in feedback_contents


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
