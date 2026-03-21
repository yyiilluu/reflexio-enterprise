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


# ===============================
# Tests for deduplicate happy path and advanced scenarios
# ===============================


class TestDeduplicateHappyPath:
    """Tests for the full deduplicate() flow with LLM mocks returning FeedbackDeduplicationOutput."""

    def test_happy_path_with_duplicates(self, mock_deduplicator):
        """Full happy path: LLM returns a merge group and unique feedbacks."""
        fb0 = _make_raw_feedback(0, content="do X when Y", source_interaction_ids=[10])
        fb1 = _make_raw_feedback(
            1, content="do X when Y again", source_interaction_ids=[20]
        )
        fb2 = _make_raw_feedback(2, content="do Z when W", source_interaction_ids=[30])

        # No existing feedbacks found via search
        mock_deduplicator.client.get_embeddings.return_value = [
            [0.1],
            [0.2],
            [0.3],
        ]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = []

        # LLM merges fb0 and fb1, keeps fb2 as unique
        mock_deduplicator.client.generate_chat_response.return_value = (
            FeedbackDeduplicationOutput(
                duplicate_groups=[
                    FeedbackDeduplicationDuplicateGroup(
                        item_ids=["NEW-0", "NEW-1"],
                        merged_content=StructuredFeedbackContent(
                            do_action="do X",
                            when_condition="when Y",
                        ),
                        reasoning="Same instruction",
                    )
                ],
                unique_ids=["NEW-2"],
            )
        )

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb0, fb1], [fb2]],
                request_id="req_test",
                agent_version="v1",
            )

        # 1 merged + 1 unique = 2 feedbacks
        assert len(result) == 2
        assert delete_ids == []

        # Merged feedback should have combined source_interaction_ids
        merged = result[0]
        assert set(merged.source_interaction_ids) == {10, 20}

        # Unique feedback should be fb2
        assert result[1].feedback_content == "do Z when W"

    def test_multiple_extractor_results_nested_lists(self, mock_deduplicator):
        """Multiple extractor results (nested list of lists) are flattened correctly."""
        fb0 = _make_raw_feedback(0, content="feedback from extractor 1")
        fb1 = _make_raw_feedback(1, content="feedback from extractor 2")
        fb2 = _make_raw_feedback(2, content="feedback from extractor 3")

        mock_deduplicator.client.get_embeddings.return_value = [
            [0.1],
            [0.2],
            [0.3],
        ]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = []

        # LLM says all are unique
        mock_deduplicator.client.generate_chat_response.return_value = (
            FeedbackDeduplicationOutput(
                duplicate_groups=[],
                unique_ids=["NEW-0", "NEW-1", "NEW-2"],
            )
        )

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb0], [fb1], [fb2]],
                request_id="req_test",
                agent_version="v1",
            )

        assert len(result) == 3
        assert delete_ids == []

    def test_all_feedbacks_are_duplicates_of_existing(self, mock_deduplicator):
        """All new feedbacks are duplicates of existing feedbacks in the DB."""
        fb0 = _make_raw_feedback(0, content="do X when Y", source_interaction_ids=[10])
        existing_fb = _make_raw_feedback(
            99,
            raw_feedback_id=500,
            content="do X when Y (existing)",
            source_interaction_ids=[5],
        )

        mock_deduplicator.client.get_embeddings.return_value = [[0.1]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = [
            existing_fb
        ]

        # LLM merges NEW-0 with EXISTING-0
        mock_deduplicator.client.generate_chat_response.return_value = (
            FeedbackDeduplicationOutput(
                duplicate_groups=[
                    FeedbackDeduplicationDuplicateGroup(
                        item_ids=["NEW-0", "EXISTING-0"],
                        merged_content=StructuredFeedbackContent(
                            do_action="do X",
                            when_condition="when Y",
                        ),
                        reasoning="Same instruction as existing",
                    )
                ],
                unique_ids=[],
            )
        )

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb0]],
                request_id="req_test",
                agent_version="v1",
            )

        # 1 merged feedback replaces both
        assert len(result) == 1
        # Existing feedback should be marked for deletion
        assert 500 in delete_ids
        # Merged feedback should combine source_interaction_ids from both
        assert set(result[0].source_interaction_ids) == {5, 10}


# ===============================
# Tests for _retrieve_existing_feedbacks with user_id filter
# ===============================


class TestBuildDeduplicatedResultsEdgeCases:
    """Extended tests for _build_deduplicated_results edge cases."""

    def test_template_fallback_to_existing_feedback(self, mock_deduplicator):
        """Test template selection falls back to existing feedback when no NEW in group."""
        existing_feedbacks = [
            _make_raw_feedback(
                0,
                raw_feedback_id=100,
                feedback_name="existing_fb",
                source_interaction_ids=[5],
            ),
        ]

        # Group only has EXISTING items, no NEW items
        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["EXISTING-0"],
                    merged_content=StructuredFeedbackContent(
                        do_action="merged do",
                        when_condition="merged when",
                    ),
                    reasoning="Existing-only group",
                )
            ],
            unique_ids=[],
        )

        result, delete_ids = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=[],
            existing_feedbacks=existing_feedbacks,
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 1
        # Template should come from existing feedback
        assert result[0].feedback_name == "existing_fb"
        assert 100 in delete_ids

    def test_template_fallback_skips_out_of_range_existing(self, mock_deduplicator):
        """Test that out-of-range existing indices are skipped in fallback."""
        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["EXISTING-99"],  # out of range
                    merged_content=StructuredFeedbackContent(
                        do_action="merged do",
                        when_condition="merged when",
                    ),
                    reasoning="Bad index",
                )
            ],
            unique_ids=[],
        )

        result, delete_ids = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=[],
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        # Group should be skipped entirely since no valid template was found
        assert len(result) == 0
        assert delete_ids == []

    def test_source_interaction_ids_combined_from_new_and_existing(
        self, mock_deduplicator
    ):
        """Test that source_interaction_ids are combined from both NEW and EXISTING feedbacks."""
        new_feedbacks = [
            _make_raw_feedback(0, source_interaction_ids=[1, 2]),
        ]
        existing_feedbacks = [
            _make_raw_feedback(
                1, raw_feedback_id=100, source_interaction_ids=[3, 4]
            ),
        ]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["NEW-0", "EXISTING-0"],
                    merged_content=StructuredFeedbackContent(
                        do_action="merged",
                        when_condition="merged condition",
                    ),
                    reasoning="Combined",
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
        assert set(result[0].source_interaction_ids) == {1, 2, 3, 4}
        assert 100 in delete_ids

    def test_source_interaction_ids_deduplication(self, mock_deduplicator):
        """Test that duplicate source_interaction_ids are not repeated."""
        new_feedbacks = [
            _make_raw_feedback(0, source_interaction_ids=[1, 2]),
            _make_raw_feedback(1, source_interaction_ids=[2, 3]),
        ]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[
                FeedbackDeduplicationDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content=StructuredFeedbackContent(
                        do_action="merged",
                        when_condition="merged cond",
                    ),
                    reasoning="Overlap IDs",
                )
            ],
            unique_ids=[],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 1
        # ID 2 should appear only once
        assert result[0].source_interaction_ids == [1, 2, 3]

    def test_unhandled_feedbacks_safety_net(self, mock_deduplicator):
        """Test that feedbacks not mentioned in unique_ids or groups are added via safety net."""
        new_feedbacks = [
            _make_raw_feedback(0),
            _make_raw_feedback(1),
            _make_raw_feedback(2),
        ]

        # LLM only mentions index 1 as unique, leaves 0 and 2 unmentioned
        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-1"],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 3
        # Index 1 is from unique_ids, indices 0 and 2 from safety fallback
        contents = {fb.feedback_content for fb in result}
        assert "content_0" in contents
        assert "content_1" in contents
        assert "content_2" in contents

    def test_invalid_item_ids_are_skipped_in_unique_ids(self, mock_deduplicator):
        """Test that unparseable item IDs in unique_ids are skipped."""
        new_feedbacks = [_make_raw_feedback(0)]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["BADFORMAT", "NEW-0"],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        # NEW-0 added via unique_ids, BADFORMAT skipped
        assert len(result) == 1

    def test_existing_only_unique_ids_not_added(self, mock_deduplicator):
        """Test that EXISTING prefix in unique_ids does not add feedback."""
        new_feedbacks = [_make_raw_feedback(0)]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["EXISTING-0"],
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[_make_raw_feedback(1, raw_feedback_id=100)],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        # EXISTING-0 in unique_ids is ignored; NEW-0 added by safety net
        contents = {fb.feedback_content for fb in result}
        assert "content_0" in contents

    def test_out_of_range_new_index_in_unique_ids(self, mock_deduplicator):
        """Test that out-of-range NEW index in unique_ids is safely ignored."""
        new_feedbacks = [_make_raw_feedback(0)]

        dedup_output = FeedbackDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-0", "NEW-99"],  # 99 is out of range
        )

        result, _ = mock_deduplicator._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=[],
            dedup_output=dedup_output,
            request_id="req1",
            agent_version="v1",
        )

        assert len(result) == 1


class TestFormatItemsForPrompt:
    """Tests for _format_items_for_prompt (delegates to _format_feedbacks_with_prefix)."""

    def test_delegates_with_new_prefix(self, mock_deduplicator):
        """Test that _format_items_for_prompt uses 'NEW' prefix."""
        feedbacks = [_make_raw_feedback(0)]
        result = mock_deduplicator._format_items_for_prompt(feedbacks)
        assert "[NEW-0]" in result

    def test_empty_list(self, mock_deduplicator):
        """Test that empty list returns '(None)'."""
        result = mock_deduplicator._format_items_for_prompt([])
        assert result == "(None)"


class TestFormatFeedbacksEdgeCases:
    """Edge cases for _format_feedbacks_with_prefix."""

    def test_empty_feedback_name_shows_unknown(self, mock_deduplicator):
        """Test that empty feedback_name displays as 'unknown'."""
        fb = RawFeedback(
            raw_feedback_id=0,
            agent_version="v1",
            request_id="req1",
            feedback_name="",
            feedback_content="content",
        )
        result = mock_deduplicator._format_feedbacks_with_prefix([fb], "NEW")
        assert "Name: unknown" in result

    def test_none_source_shows_unknown(self, mock_deduplicator):
        """Test that None source displays as 'unknown'."""
        fb = RawFeedback(
            raw_feedback_id=0,
            agent_version="v1",
            request_id="req1",
            feedback_name="fb",
            feedback_content="content",
            source=None,
        )
        result = mock_deduplicator._format_feedbacks_with_prefix([fb], "NEW")
        assert "Source: unknown" in result


class TestMockModeCheck:
    """Tests for mock mode check in deduplicate."""

    def test_mock_mode_handles_non_list_results(self, mock_deduplicator):
        """Test that mock mode isinstance check filters non-list items."""
        fb = _make_raw_feedback(0)

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "true"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb]],
                request_id="req1",
                agent_version="v1",
            )

        assert len(result) == 1
        assert delete_ids == []

    def test_mock_mode_case_insensitive(self, mock_deduplicator):
        """Test that mock mode check is case insensitive."""
        fb = _make_raw_feedback(0)

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "True"}):
            result, delete_ids = mock_deduplicator.deduplicate(
                results=[[fb]],
                request_id="req1",
                agent_version="v1",
            )

        assert len(result) == 1
        assert delete_ids == []

    def test_mock_mode_false_proceeds_normally(self, mock_deduplicator):
        """Test that mock mode disabled runs full dedup path."""
        mock_deduplicator.client.get_embeddings.return_value = [[0.1]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = []
        mock_deduplicator.client.generate_chat_response.return_value = (
            FeedbackDeduplicationOutput(
                duplicate_groups=[],
                unique_ids=["NEW-0"],
            )
        )

        fb = _make_raw_feedback(0)
        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "false"}):
            result, _ = mock_deduplicator.deduplicate(
                results=[[fb]],
                request_id="req1",
                agent_version="v1",
            )

        assert len(result) == 1


class TestRetrieveExistingFeedbacksWithUserId:
    """Tests for _retrieve_existing_feedbacks with user_id filter."""

    def test_user_id_passed_to_search(self, mock_deduplicator):
        """Test that user_id is passed through to the search request."""
        new_fb = _make_raw_feedback(0, when_condition="user asks about billing")
        existing_fb = _make_raw_feedback(1, raw_feedback_id=100)

        mock_deduplicator.client.get_embeddings.return_value = [[0.1]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = [
            existing_fb
        ]

        mock_deduplicator._retrieve_existing_feedbacks([new_fb], user_id="user_abc")

        # Verify search was called with user_id
        call_args = (
            mock_deduplicator.request_context.storage.search_raw_feedbacks.call_args
        )
        search_request = call_args[0][0]
        assert search_request.user_id == "user_abc"

    def test_none_user_id_passed_to_search(self, mock_deduplicator):
        """Test that None user_id is passed through correctly."""
        new_fb = _make_raw_feedback(0, when_condition="some condition")

        mock_deduplicator.client.get_embeddings.return_value = [[0.1]]
        mock_deduplicator.request_context.storage.search_raw_feedbacks.return_value = []

        mock_deduplicator._retrieve_existing_feedbacks([new_fb], user_id=None)

        call_args = (
            mock_deduplicator.request_context.storage.search_raw_feedbacks.call_args
        )
        search_request = call_args[0][0]
        assert search_request.user_id is None
