"""Unit tests for the unified search service.

Tests the critical orchestration logic: empty query, embedding failure,
rewritten_query propagation, and skills feature-flag gating.
"""

import unittest
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.retriever_schema import (
    RewrittenQuery,
    UnifiedSearchRequest,
)

from reflexio.server.services.unified_search_service import (
    _run_phase_b,
    run_unified_search,
)


def _mock_storage(embedding=None):
    """Create a mock storage with configurable embedding."""
    storage = MagicMock()
    storage._get_embedding.return_value = embedding or [0.1] * 1536
    # Storage search methods return empty lists by default
    storage.search_user_profile.return_value = []
    storage.search_feedbacks.return_value = []
    storage.search_raw_feedbacks.return_value = []
    storage.search_skills.return_value = []
    return storage


class TestRunUnifiedSearch(unittest.TestCase):
    """Tests for the top-level run_unified_search function."""

    def test_empty_query_rejected_by_validation(self):
        """Empty query is now rejected at the Pydantic validation level."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            UnifiedSearchRequest(query="")

    def test_whitespace_query_rejected_by_validation(self):
        """Whitespace-only query is rejected at the Pydantic validation level."""
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            UnifiedSearchRequest(query="   ")

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_embedding_failure_degrades_to_text_search(self, _flag1, _rewriter_cls):
        """When embedding generation fails, should degrade to text-only search (not crash)."""
        storage = _mock_storage()
        storage._get_embedding.side_effect = RuntimeError("Embedding API down")

        _rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
            fts_query="test query"
        )

        request = UnifiedSearchRequest(query="test query")
        result = run_unified_search(
            request=request,
            org_id="test-org",
            storage=storage,
            api_key_config=MagicMock(),
            prompt_manager=MagicMock(),
        )

        self.assertTrue(result.success)
        storage.search_feedbacks.assert_called_once()

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_local_storage_without_get_embedding(self, _flag1, _rewriter_cls):
        """LocalJsonStorage (no _get_embedding) should not crash and should use text-only search."""
        storage = _mock_storage()
        del storage._get_embedding  # Simulate LocalJsonStorage which lacks this method

        _rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
            fts_query="test query"
        )

        request = UnifiedSearchRequest(query="test query")
        result = run_unified_search(
            request=request,
            org_id="test-org",
            storage=storage,
            api_key_config=MagicMock(),
            prompt_manager=MagicMock(),
        )

        self.assertTrue(result.success)
        storage.search_feedbacks.assert_called_once()

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_rewritten_query_populated_when_changed(self, _flag1, _rewriter_cls):
        """rewritten_query field should only be set when query was actually rewritten."""
        expanded = RewrittenQuery(fts_query="agent failed OR error to refund OR return")
        _rewriter_cls.return_value.rewrite.return_value = expanded

        storage = _mock_storage()
        request = UnifiedSearchRequest(
            query="agent failed to refund", query_rewrite=True
        )
        result = run_unified_search(
            request=request,
            org_id="test-org",
            storage=storage,
            api_key_config=MagicMock(),
            prompt_manager=MagicMock(),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.rewritten_query,
            "agent failed OR error to refund OR return",
        )

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_rewritten_query_none_when_unchanged(self, _flag1, _rewriter_cls):
        """rewritten_query should be None when query was not rewritten."""
        _rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
            fts_query="same query"
        )

        storage = _mock_storage()
        request = UnifiedSearchRequest(query="same query")
        result = run_unified_search(
            request=request,
            org_id="test-org",
            storage=storage,
            api_key_config=MagicMock(),
            prompt_manager=MagicMock(),
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.rewritten_query)


class TestPhaseB(unittest.TestCase):
    """Tests for _run_phase_b skills gating."""

    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_skills_search_skipped_when_disabled(self, _flag):
        """When skill_generation is disabled, storage.search_skills should not be called."""
        storage = _mock_storage()

        profiles, feedbacks, raw_feedbacks, skills = _run_phase_b(
            request=UnifiedSearchRequest(query="test"),
            org_id="test-org",
            storage=storage,
            embedding=[0.1] * 1536,
            query="test",
            top_k=5,
            threshold=0.3,
        )

        self.assertEqual(skills, [])
        storage.search_skills.assert_not_called()

    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=True,
    )
    def test_skills_search_called_when_enabled(self, _flag):
        """When skill_generation is enabled, storage.search_skills should be called."""
        storage = _mock_storage()

        _run_phase_b(
            request=UnifiedSearchRequest(query="test"),
            org_id="test-org",
            storage=storage,
            embedding=[0.1] * 1536,
            query="test",
            top_k=5,
            threshold=0.3,
        )

        storage.search_skills.assert_called_once()


if __name__ == "__main__":
    unittest.main()
