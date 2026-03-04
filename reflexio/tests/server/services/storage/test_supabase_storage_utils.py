"""
Unit tests for supabase_storage_utils serialization functions.

Tests blocking_issue serialization in raw_feedback_to_data and feedback_to_data.
"""

from reflexio_commons.api_schema.service_schemas import (
    RawFeedback,
    Feedback,
    FeedbackStatus,
    BlockingIssue,
    BlockingIssueKind,
)
from reflexio.server.services.storage.supabase_storage_utils import (
    raw_feedback_to_data,
    feedback_to_data,
)


class TestRawFeedbackToData:
    """Tests for raw_feedback_to_data serialization."""

    def test_serializes_blocking_issue(self):
        """Test that blocking_issue is serialized to dict via model_dump."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.MISSING_TOOL,
                details="No database query tool",
            ),
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["blocking_issue"] is not None
        assert data["blocking_issue"]["kind"] == "missing_tool"
        assert data["blocking_issue"]["details"] == "No database query tool"

    def test_serializes_none_blocking_issue(self):
        """Test that None blocking_issue is serialized as None."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["blocking_issue"] is None

    def test_serializes_source_interaction_ids(self):
        """Test that source_interaction_ids list is serialized as-is."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
            source_interaction_ids=[10, 20, 30],
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["source_interaction_ids"] == [10, 20, 30]

    def test_serializes_empty_source_interaction_ids_as_none(self):
        """Test that empty source_interaction_ids is serialized as None for DB storage."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["source_interaction_ids"] is None


class TestFeedbackToData:
    """Tests for feedback_to_data serialization."""

    def test_serializes_blocking_issue(self):
        """Test that blocking_issue is serialized to dict via model_dump."""
        feedback = Feedback(
            agent_version="1.0",
            feedback_name="test",
            feedback_content="test content",
            feedback_status=FeedbackStatus.PENDING,
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.PERMISSION_DENIED,
                details="Cannot access admin API",
            ),
        )

        data = feedback_to_data(feedback)

        assert data["blocking_issue"] is not None
        assert data["blocking_issue"]["kind"] == "permission_denied"
        assert data["blocking_issue"]["details"] == "Cannot access admin API"

    def test_serializes_none_blocking_issue(self):
        """Test that None blocking_issue is serialized as None."""
        feedback = Feedback(
            agent_version="1.0",
            feedback_name="test",
            feedback_content="test content",
            feedback_status=FeedbackStatus.PENDING,
        )

        data = feedback_to_data(feedback)

        assert data["blocking_issue"] is None
