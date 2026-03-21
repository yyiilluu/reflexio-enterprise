"""
Unit tests for blocking_issue handling in FeedbackAggregator.

Tests the formatting and processing methods that carry blocking_issue
through the aggregation pipeline.
"""

from unittest.mock import MagicMock

import pytest
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregationOutput,
    StructuredFeedbackContent,
    format_structured_feedback_content,
)
from reflexio_commons.api_schema.service_schemas import (
    BlockingIssue,
    BlockingIssueKind,
    RawFeedback,
)


@pytest.fixture
def aggregator():
    """Create a FeedbackAggregator with mocked dependencies."""
    mock_llm_client = MagicMock()
    mock_request_context = MagicMock()
    mock_request_context.storage = MagicMock()
    mock_request_context.configurator = MagicMock()

    return FeedbackAggregator(
        llm_client=mock_llm_client,
        request_context=mock_request_context,
        agent_version="1.0",
    )


class TestFormatStructuredClusterInput:
    """Tests for _format_structured_cluster_input with blocking_issue."""

    def test_includes_blocking_issues_in_output(self, aggregator):
        """Test that blocking issues from cluster feedbacks appear in formatted output."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content1",
                when_condition="user asks to delete files",
                do_action="inform user about permission requirements",
                blocking_issue=BlockingIssue(
                    kind=BlockingIssueKind.PERMISSION_DENIED,
                    details="No admin file deletion access",
                ),
            ),
            RawFeedback(
                agent_version="1.0",
                request_id="req2",
                feedback_name="test",
                feedback_content="content2",
                when_condition="user requests file removal",
                do_action="suggest contacting admin",
                blocking_issue=BlockingIssue(
                    kind=BlockingIssueKind.PERMISSION_DENIED,
                    details="Lacks write permissions on shared drive",
                ),
            ),
        ]

        result = aggregator._format_structured_cluster_input(feedbacks)

        assert "BLOCKED BY issues:" in result
        assert "[permission_denied] No admin file deletion access" in result
        assert "[permission_denied] Lacks write permissions on shared drive" in result

    def test_omits_blocked_by_section_when_no_blocking_issues(self, aggregator):
        """Test that BLOCKED BY section is absent when no feedbacks have blocking_issue."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content1",
                when_condition="user asks a question",
                do_action="provide a detailed answer",
            ),
        ]

        result = aggregator._format_structured_cluster_input(feedbacks)

        assert "BLOCKED BY" not in result

    def test_includes_only_non_none_blocking_issues(self, aggregator):
        """Test that only feedbacks with blocking_issue are included in BLOCKED BY section."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content1",
                when_condition="user asks to query DB",
                do_action="use API instead",
                blocking_issue=BlockingIssue(
                    kind=BlockingIssueKind.MISSING_TOOL,
                    details="No DB query tool",
                ),
            ),
            RawFeedback(
                agent_version="1.0",
                request_id="req2",
                feedback_name="test",
                feedback_content="content2",
                when_condition="user asks to query DB",
                do_action="suggest API endpoint",
                # No blocking_issue
            ),
        ]

        result = aggregator._format_structured_cluster_input(feedbacks)

        assert "BLOCKED BY issues:" in result
        assert "[missing_tool] No DB query tool" in result
        # Only one blocking issue line
        assert result.count("[missing_tool]") == 1


class TestFormatStructuredFeedbackContent:
    """Tests for _format_structured_feedback_content with blocking_issue."""

    def test_includes_blocked_by_line(self, aggregator):
        """Test that blocking_issue is formatted as 'Blocked by:' line."""
        structured = StructuredFeedbackContent(
            do_action="use API endpoint",
            when_condition="user asks for DB access",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.EXTERNAL_DEPENDENCY,
                details="Database service is unavailable",
            ),
        )

        result = format_structured_feedback_content(structured)

        assert (
            "Blocked by: [external_dependency] Database service is unavailable"
            in result
        )

    def test_omits_blocked_by_when_none(self, aggregator):
        """Test that no 'Blocked by:' line when blocking_issue is None."""
        structured = StructuredFeedbackContent(
            do_action="validate inputs",
            when_condition="processing data",
        )

        result = format_structured_feedback_content(structured)

        assert "Blocked by:" not in result


class TestProcessAggregationResponse:
    """Tests for _process_aggregation_response with blocking_issue."""

    def test_carries_blocking_issue_to_feedback(self, aggregator):
        """Test that blocking_issue from LLM response is set on the resulting Feedback."""
        response = FeedbackAggregationOutput(
            feedback=StructuredFeedbackContent(
                do_action="inform user about limitation",
                when_condition="user requests restricted action",
                blocking_issue=BlockingIssue(
                    kind=BlockingIssueKind.POLICY_RESTRICTION,
                    details="Corporate policy blocks external API calls",
                ),
            )
        )
        cluster_feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content",
            ),
        ]

        result = aggregator._process_aggregation_response(response, cluster_feedbacks)

        assert result is not None
        assert result.blocking_issue is not None
        assert result.blocking_issue.kind == BlockingIssueKind.POLICY_RESTRICTION
        assert "Corporate policy" in result.blocking_issue.details
        assert "Blocked by: [policy_restriction]" in result.feedback_content

    def test_feedback_without_blocking_issue(self, aggregator):
        """Test that Feedback has no blocking_issue when LLM doesn't return one."""
        response = FeedbackAggregationOutput(
            feedback=StructuredFeedbackContent(
                do_action="provide clear instructions",
                when_condition="user is confused",
            )
        )
        cluster_feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content",
            ),
        ]

        result = aggregator._process_aggregation_response(response, cluster_feedbacks)

        assert result is not None
        assert result.blocking_issue is None
        assert "Blocked by:" not in result.feedback_content
