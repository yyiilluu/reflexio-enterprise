"""Tests for feedback deduplication service."""

from unittest.mock import MagicMock, patch

import pytest
from reflexio_commons.api_schema.service_schemas import RawFeedback

from reflexio.server.services.feedback.feedback_deduplicator import (
    FeedbackDeduplicationDuplicateGroup,
    FeedbackDeduplicationOutput,
    FeedbackDeduplicator,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    StructuredFeedbackContent,
)

# ===============================
# Fixtures
# ===============================


def _make_raw_feedback(
    idx: int,
    feedback_name: str = "test_fb",
    content: str | None = None,
    when_condition: str | None = None,
    source_interaction_ids: list[int] | None = None,
    raw_feedback_id: int = 0,
) -> RawFeedback:
    """Helper to create a RawFeedback object for tests."""
    return RawFeedback(
        raw_feedback_id=raw_feedback_id,
        agent_version="v1",
        request_id=f"req_{idx}",
        feedback_name=feedback_name,
        feedback_content=content or f"content_{idx}",
        when_condition=when_condition or f"condition_{idx}",
        do_action=f"do_{idx}",
        source="test",
        source_interaction_ids=source_interaction_ids or [],
    )


@pytest.fixture
def mock_deduplicator():
    """Create a FeedbackDeduplicator with mocked dependencies."""
    mock_request_context = MagicMock()
    mock_request_context.storage = MagicMock()
    mock_request_context.prompt_manager = MagicMock()
    mock_request_context.prompt_manager.render_prompt.return_value = "mock prompt"

    mock_llm_client = MagicMock()

    with patch(
        "reflexio.server.services.deduplication_utils.SiteVarManager"
    ) as mock_svm:
        mock_svm.return_value.get_site_var.return_value = {
            "default_generation_model_name": "gpt-test"
        }
        return FeedbackDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )


# ===============================
# Tests for _format_feedbacks_with_prefix
# ===============================


class TestFormatFeedbacksWithPrefix:
    """Tests for _format_feedbacks_with_prefix."""

    def test_single_feedback(self, mock_deduplicator):
        """Test formatting a single feedback."""
        fb = _make_raw_feedback(0, content="do X when Y")
        result = mock_deduplicator._format_feedbacks_with_prefix([fb], "NEW")
        assert '[NEW-0] Content: "do X when Y"' in result
        assert "Name: test_fb" in result
        assert "Source: test" in result

    def test_multiple_feedbacks(self, mock_deduplicator):
        """Test formatting multiple feedbacks with incrementing indices."""
        feedbacks = [_make_raw_feedback(i) for i in range(3)]
        result = mock_deduplicator._format_feedbacks_with_prefix(feedbacks, "EXISTING")
        assert "[EXISTING-0]" in result
        assert "[EXISTING-1]" in result
        assert "[EXISTING-2]" in result

    def test_empty_list(self, mock_deduplicator):
        """Test formatting empty list returns '(None)'."""
        result = mock_deduplicator._format_feedbacks_with_prefix([], "NEW")
        assert result == "(None)"


# ===============================
# Tests for _format_new_and_existing_for_prompt
# ===============================


class TestFormatNewAndExistingForPrompt:
    """Tests for _format_new_and_existing_for_prompt."""

    def test_formats_both_lists(self, mock_deduplicator):
        """Test that new and existing feedbacks are formatted with correct prefixes."""
        new_fbs = [_make_raw_feedback(0)]
        existing_fbs = [_make_raw_feedback(1)]

        new_text, existing_text = mock_deduplicator._format_new_and_existing_for_prompt(
            new_fbs, existing_fbs
        )

        assert "[NEW-0]" in new_text
        assert "[EXISTING-0]" in existing_text

    def test_empty_existing(self, mock_deduplicator):
        """Test formatting with empty existing feedbacks."""
        new_fbs = [_make_raw_feedback(0)]

        new_text, existing_text = mock_deduplicator._format_new_and_existing_for_prompt(
            new_fbs, []
        )

        assert "[NEW-0]" in new_text
        assert existing_text == "(None)"


# ===============================
# Tests for _retrieve_existing_feedbacks
# ===============================


class TestRetrieveExistingFeedbacks:
    """Tests for _retrieve_existing_feedbacks."""

    def test_with_embeddings(self, mock_deduplicator):
        """Test retrieval using embeddings for vector search."""
        new_fb = _make_raw_feedback(0, when_condition="user asks about billing")
        existing_fb = _make_raw_feedback(
            1, raw_feedback_id=100, when_condition="billing inquiry"
        )

        mock_deduplicator.client.get_embeddings.return_value = [[0.1, 0.2, 0.3]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = [
            existing_fb
        ]

        result = mock_deduplicator._retrieve_existing_feedbacks([new_fb])

        assert len(result) == 1
        assert result[0].raw_feedback_id == 100
        mock_deduplicator.client.get_embeddings.assert_called_once()

    def test_fallback_to_text_search(self, mock_deduplicator):
        """Test fallback to text-only search when embedding generation fails."""
        new_fb = _make_raw_feedback(0)
        existing_fb = _make_raw_feedback(1, raw_feedback_id=200)

        mock_deduplicator.client.get_embeddings.side_effect = Exception("embed error")
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = [
            existing_fb
        ]

        result = mock_deduplicator._retrieve_existing_feedbacks([new_fb])

        assert len(result) == 1

    def test_empty_query_texts(self, mock_deduplicator):
        """Test that empty when_condition feedbacks return no results."""
        fb = RawFeedback(
            agent_version="v1",
            request_id="req1",
            feedback_name="test",
            feedback_content="",
            when_condition="",
        )

        result = mock_deduplicator._retrieve_existing_feedbacks([fb])

        assert result == []

    def test_deduplicates_by_id(self, mock_deduplicator):
        """Test that duplicate existing feedbacks from multiple queries are deduplicated."""
        fb1 = _make_raw_feedback(0, when_condition="query1")
        fb2 = _make_raw_feedback(1, when_condition="query2")

        shared_existing = _make_raw_feedback(99, raw_feedback_id=500)

        mock_deduplicator.client.get_embeddings.return_value = [
            [0.1],
            [0.2],
        ]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = [
            shared_existing
        ]

        result = mock_deduplicator._retrieve_existing_feedbacks([fb1, fb2])

        # Should only appear once despite being returned for both queries
        assert len(result) == 1


# ===============================
# Tests for deduplicate
# ===============================


class TestDeduplicate:
    """Tests for the main deduplicate method."""

    def test_mock_mode_skips_deduplication(self, mock_deduplicator):
        """Test that MOCK_LLM_RESPONSE=true skips deduplication."""
        fb1 = _make_raw_feedback(0)
        fb2 = _make_raw_feedback(1)

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "true"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb1], [fb2]],
                request_id="req1",
                agent_version="v1",
            )

        assert len(result) == 2
        assert delete_ids == []

    def test_empty_results(self, mock_deduplicator):
        """Test deduplication with no feedbacks."""
        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[]],
                request_id="req1",
                agent_version="v1",
            )

        assert result == []
        assert delete_ids == []

    def test_error_fallback_returns_all(self, mock_deduplicator):
        """Test that LLM call error falls back to returning all feedbacks."""
        fb = _make_raw_feedback(0)

        mock_deduplicator.client.get_embeddings.return_value = [[0.1]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = []
        mock_deduplicator.client.generate_chat_response.side_effect = Exception(
            "LLM error"
        )

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb]],
                request_id="req1",
                agent_version="v1",
            )

        assert len(result) == 1
        assert delete_ids == []


# ===============================
# Tests for _build_deduplicated_results
# ===============================


class TestBuildDeduplicatedResults:
    """Tests for _build_deduplicated_results merge logic."""

    def test_merge_group_combines_source_interaction_ids(self, mock_deduplicator):
        """Test that merged groups combine source_interaction_ids from all feedbacks."""
        new_feedbacks = [
            _make_raw_feedback(0, source_interaction_ids=[1, 2]),
            _make_raw_feedback(1, source_interaction_ids=[3, 4]),
        ]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content=StructuredFeedbackContent(
                        do_action="merged do",
                        when_condition="merged when",
                    ),
                    reasoning="Same topic",
                )
            ],
            unique_ids=[],
        )

        result, delete_ids = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 1
        assert set(result[0].source_interaction_ids) == {1, 2, 3, 4}
        assert delete_ids == []

    def test_unique_ids_passed_through(self, mock_deduplicator):
        """Test that unique NEW feedbacks are passed through unchanged."""
        new_feedbacks = [
            _make_raw_feedback(0),
            _make_raw_feedback(1),
        ]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-0", "NEW-1"],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 2

    def test_existing_feedbacks_to_delete(self, mock_deduplicator):
        """Test that existing feedbacks in merge groups are marked for deletion."""
        new_feedbacks = [_make_raw_feedback(0)]
        existing_feedbacks = [_make_raw_feedback(1, raw_feedback_id=999)]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["NEW-0", "EXISTING-0"],
                    merged_content=StructuredFeedbackContent(
                        do_action="merged",
                        when_condition="when merged",
                    ),
                    reasoning="Duplicate",
                )
            ],
            unique_ids=[],
        )

        result, delete_ids = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=existing_feedbacks,
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 1
        assert 999 in delete_ids

    def test_safety_fallback_unhandled_feedbacks(self, mock_deduplicator):
        """Test that feedbacks not mentioned by LLM are added via safety fallback."""
        new_feedbacks = [
            _make_raw_feedback(0),
            _make_raw_feedback(1),
            _make_raw_feedback(2),
        ]

        # LLM only mentions index 0
        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-0"],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        # Index 0 via unique_ids + index 1 and 2 via safety fallback
        assert len(result) == 3
