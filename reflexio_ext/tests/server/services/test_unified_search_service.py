"""Unit tests for the unified search service.

Tests the critical orchestration logic: empty query, embedding failure,
rewritten_query propagation, skills feature-flag gating, phase-level
error handling, and profile search edge cases.
"""

import unittest
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

from reflexio.server.services.unified_search_service import (
    _run_phase_a,
    _run_phase_b,
    _search_profiles_via_storage,
    run_unified_search,
)
from reflexio_commons.api_schema.retriever_schema import (
    RewrittenQuery,
    UnifiedSearchRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    UserProfile,
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


class TestRunUnifiedSearchEdgeCases(unittest.TestCase):
    """Additional tests for run_unified_search covering uncovered lines."""

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_returns_failure_when_profiles_none(self, _flag, _rewriter_cls):
        """Test that search returns success=False when _run_phase_b returns all Nones (line 96)."""
        _rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
            fts_query="test query"
        )

        storage = _mock_storage()
        # Make profile search raise a FuturesTimeoutError so _run_phase_b returns (None, None, None, None)
        storage.search_user_profile.side_effect = FuturesTimeoutError("timeout")

        request = UnifiedSearchRequest(query="test query", user_id="user1")

        with patch(
            "reflexio.server.services.unified_search_service._run_phase_b",
            return_value=(None, None, None, None),
        ):
            result = run_unified_search(
                request=request,
                org_id="test-org",
                storage=storage,
                api_key_config=MagicMock(),
                prompt_manager=MagicMock(),
            )

        self.assertFalse(result.success)
        self.assertEqual(result.msg, "Search failed")

    @patch("reflexio.server.services.unified_search_service.QueryRewriter")
    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_uses_default_top_k_and_threshold(self, _flag, _rewriter_cls):
        """Test that default top_k=5 and threshold=0.3 are used when not specified."""
        _rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
            fts_query="test query"
        )
        storage = _mock_storage()

        request = UnifiedSearchRequest(query="test query")
        result = run_unified_search(
            request=request,
            org_id="test-org",
            storage=storage,
            api_key_config=MagicMock(),
            prompt_manager=MagicMock(),
        )

        self.assertTrue(result.success)


class TestPhaseAErrors(unittest.TestCase):
    """Tests for _run_phase_a error handling (lines 159-161)."""

    def test_query_rewrite_failure_falls_back_to_original(self):
        """Test that query rewrite failure returns the original query (lines 159-161)."""
        storage = _mock_storage()
        api_key_config = MagicMock()
        prompt_manager = MagicMock()

        with patch(
            "reflexio.server.services.unified_search_service.QueryRewriter"
        ) as mock_rewriter_cls:
            mock_rewriter_cls.return_value.rewrite.side_effect = RuntimeError(
                "Rewrite API down"
            )

            rewritten_query, embedding = _run_phase_a(
                query="original query",
                org_id="test-org",
                storage=storage,
                api_key_config=api_key_config,
                prompt_manager=prompt_manager,
                supports_embedding=True,
                query_rewrite=True,
            )

        # Should fall back to original query
        self.assertEqual(rewritten_query.fts_query, "original query")
        # Embedding should still succeed
        self.assertIsNotNone(embedding)

    def test_embedding_skipped_when_not_supported(self):
        """Test that embedding is None when supports_embedding=False."""
        storage = _mock_storage()
        api_key_config = MagicMock()
        prompt_manager = MagicMock()

        with patch(
            "reflexio.server.services.unified_search_service.QueryRewriter"
        ) as mock_rewriter_cls:
            mock_rewriter_cls.return_value.rewrite.return_value = RewrittenQuery(
                fts_query="test query"
            )

            rewritten_query, embedding = _run_phase_a(
                query="test query",
                org_id="test-org",
                storage=storage,
                api_key_config=api_key_config,
                prompt_manager=prompt_manager,
                supports_embedding=False,
                query_rewrite=False,
            )

        self.assertEqual(rewritten_query.fts_query, "test query")
        self.assertIsNone(embedding)
        storage._get_embedding.assert_not_called()


class TestPhaseBErrors(unittest.TestCase):
    """Tests for _run_phase_b timeout and exception handling (lines 260-265)."""

    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_timeout_returns_all_none(self, _flag):
        """Test that FuturesTimeoutError returns (None, None, None, None) (lines 260-262)."""
        storage = _mock_storage()
        # Make search_feedbacks hang by raising TimeoutError
        storage.search_feedbacks.side_effect = FuturesTimeoutError("timeout")

        profiles, feedbacks, raw_feedbacks, skills = _run_phase_b(
            request=UnifiedSearchRequest(query="test"),
            org_id="test-org",
            storage=storage,
            embedding=[0.1] * 1536,
            query="test",
            top_k=5,
            threshold=0.3,
        )

        self.assertIsNone(profiles)
        self.assertIsNone(feedbacks)
        self.assertIsNone(raw_feedbacks)
        self.assertIsNone(skills)

    @patch(
        "reflexio.server.services.unified_search_service.is_skill_generation_enabled",
        return_value=False,
    )
    def test_general_exception_returns_all_none(self, _flag):
        """Test that a general exception returns (None, None, None, None) (lines 263-265)."""
        storage = _mock_storage()
        storage.search_raw_feedbacks.side_effect = ValueError("Unexpected error")

        profiles, feedbacks, raw_feedbacks, skills = _run_phase_b(
            request=UnifiedSearchRequest(query="test"),
            org_id="test-org",
            storage=storage,
            embedding=[0.1] * 1536,
            query="test",
            top_k=5,
            threshold=0.3,
        )

        self.assertIsNone(profiles)
        self.assertIsNone(feedbacks)
        self.assertIsNone(raw_feedbacks)
        self.assertIsNone(skills)


class TestSearchProfilesViaStorage(unittest.TestCase):
    """Tests for _search_profiles_via_storage (lines 295-311)."""

    def test_returns_empty_when_no_user_id(self):
        """Test that missing user_id returns empty list (line 294)."""
        storage = _mock_storage()
        request = UnifiedSearchRequest(query="test")  # no user_id

        result = _search_profiles_via_storage(
            storage=storage,
            request=request,
            query="test",
            top_k=5,
            threshold=0.3,
            embedding=[0.1] * 1536,
        )

        self.assertEqual(result, [])
        storage.search_user_profile.assert_not_called()

    def test_returns_profiles_on_success(self):
        """Test that profiles are returned on successful search (lines 295-308)."""
        storage = _mock_storage()
        mock_profile = MagicMock(spec=UserProfile)
        storage.search_user_profile.return_value = [mock_profile]

        request = UnifiedSearchRequest(query="test", user_id="user1")

        result = _search_profiles_via_storage(
            storage=storage,
            request=request,
            query="test",
            top_k=5,
            threshold=0.3,
            embedding=[0.1] * 1536,
        )

        self.assertEqual(len(result), 1)
        storage.search_user_profile.assert_called_once()

    def test_returns_empty_on_exception(self):
        """Test that exception in profile search returns empty list (lines 309-311)."""
        storage = _mock_storage()
        storage.search_user_profile.side_effect = RuntimeError("DB connection failed")

        request = UnifiedSearchRequest(query="test", user_id="user1")

        result = _search_profiles_via_storage(
            storage=storage,
            request=request,
            query="test",
            top_k=5,
            threshold=0.3,
            embedding=[0.1] * 1536,
        )

        self.assertEqual(result, [])

    def test_passes_embedding_to_search_options(self):
        """Test that embedding is passed through SearchOptions to storage."""
        storage = _mock_storage()
        storage.search_user_profile.return_value = []

        request = UnifiedSearchRequest(query="test", user_id="user1")
        embedding = [0.2] * 1536

        _search_profiles_via_storage(
            storage=storage,
            request=request,
            query="test",
            top_k=5,
            threshold=0.3,
            embedding=embedding,
        )

        call_args = storage.search_user_profile.call_args
        options = (
            call_args[1].get("options") or call_args[0][2]
            if len(call_args[0]) > 2
            else call_args[1].get("options")
        )
        self.assertIsNotNone(options)

    def test_passes_none_embedding_for_text_only(self):
        """Test that None embedding works for text-only search."""
        storage = _mock_storage()
        storage.search_user_profile.return_value = []

        request = UnifiedSearchRequest(query="test", user_id="user1")

        result = _search_profiles_via_storage(
            storage=storage,
            request=request,
            query="test",
            top_k=5,
            threshold=0.3,
            embedding=None,
        )

        self.assertEqual(result, [])
        storage.search_user_profile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
