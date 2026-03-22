"""Unit tests for the QueryRewriter service.

Tests the critical paths: feature-flag bypass, LLM failure fallback,
successful rewrite propagation, and conversation-aware rewriting.
"""

import unittest
from unittest.mock import MagicMock

from reflexio.server.services.query_rewriter import QueryRewriter
from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    RewrittenQuery,
)


def _make_rewriter(query_rewrite_model_name: str | None = None):
    """Create a QueryRewriter with mocked dependencies."""
    llm_client = MagicMock()
    prompt_manager = MagicMock()
    prompt_manager.render_prompt.return_value = "rendered prompt"

    return QueryRewriter(
        llm_client=llm_client,
        prompt_manager=prompt_manager,
        query_rewrite_model_name=query_rewrite_model_name,
    )


class TestQueryRewriter(unittest.TestCase):
    """Unit tests for QueryRewriter."""

    def test_rewrite_disabled_returns_original_query(self):
        """When enabled=False, should skip LLM and return original query."""
        rewriter = _make_rewriter()
        result = rewriter.rewrite("agent failed to refund", enabled=False)

        self.assertIsInstance(result, RewrittenQuery)
        self.assertEqual(result.fts_query, "agent failed to refund")
        # LLM should NOT have been called
        rewriter.llm_client.generate_response.assert_not_called()

    def test_rewrite_llm_failure_returns_fallback(self):
        """When LLM raises an exception, should gracefully fall back to original query."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.side_effect = RuntimeError("API timeout")

        result = rewriter.rewrite("slow response time", enabled=True)

        self.assertIsInstance(result, RewrittenQuery)
        self.assertEqual(result.fts_query, "slow response time")

    def test_rewrite_success_returns_expanded_query(self):
        """When LLM succeeds, should return the expanded query."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "agent failed OR error to refund OR return OR reimburse"
        )

        result = rewriter.rewrite("agent failed to refund", enabled=True)

        self.assertIsInstance(result, RewrittenQuery)
        self.assertEqual(
            result.fts_query,
            "agent failed OR error to refund OR return OR reimburse",
        )

    def test_rewrite_empty_response_returns_fallback(self):
        """When LLM returns an empty string, should fall back."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = "  "

        result = rewriter.rewrite("test query", enabled=True)

        self.assertIsInstance(result, RewrittenQuery)
        self.assertEqual(result.fts_query, "test query")

    def test_rewrite_strips_whitespace(self):
        """Response should be stripped of leading/trailing whitespace."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "  slow OR sluggish response OR reply time  \n"
        )

        result = rewriter.rewrite("slow response time", enabled=True)

        self.assertEqual(result.fts_query, "slow OR sluggish response OR reply time")

    def test_rewrite_extracts_query_from_json_wrapper(self):
        """When model returns a JSON wrapper, should extract and use fts_query."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            '{"fts_query":"refund OR return OR reimburse"}'
        )

        result = rewriter.rewrite("refund", enabled=True)

        self.assertEqual(result.fts_query, "refund OR return OR reimburse")

    def test_rewrite_rejects_prose_response(self):
        """When model returns explanatory prose, should fall back."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "Here is your expanded query: refund OR return OR reimburse"
        )

        result = rewriter.rewrite("refund", enabled=True)

        self.assertEqual(result.fts_query, "refund")

    def test_rewrite_extracts_query_from_code_block(self):
        """When model returns fenced output, should extract query line."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "```text\nrefund OR return OR reimburse\n```"
        )

        result = rewriter.rewrite("refund", enabled=True)

        self.assertEqual(result.fts_query, "refund OR return OR reimburse")

    def test_rewrite_extracts_query_from_json_code_block(self):
        """When model returns fenced JSON, should extract fts_query value."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            '```json\n{"fts_query":"refund OR return OR reimburse"}\n```'
        )

        result = rewriter.rewrite("refund", enabled=True)

        self.assertEqual(result.fts_query, "refund OR return OR reimburse")

    def test_rewrite_with_conversation_history_passes_context_to_prompt(self):
        """When conversation_history is provided, the formatted context should be passed to the prompt."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "backup OR sync failure S3 OR storage timeout"
        )

        history = [
            ConversationTurn(
                role="user", content="Hi, our nightly backup keeps failing"
            ),
            ConversationTurn(
                role="agent", content="I can help with that. What error do you see?"
            ),
            ConversationTurn(
                role="user", content="The error is S3 sync timeout after 900s"
            ),
        ]

        result = rewriter.rewrite(
            "what should I do", enabled=True, conversation_history=history
        )

        self.assertEqual(
            result.fts_query, "backup OR sync failure S3 OR storage timeout"
        )
        # Verify the prompt was rendered with conversation_context_block
        call_args = rewriter.prompt_manager.render_prompt.call_args
        variables = call_args[0][1]
        self.assertEqual(variables["query"], "what should I do")
        self.assertIn(
            "[user]: Hi, our nightly backup keeps failing",
            variables["conversation_context_block"],
        )
        self.assertIn(
            "[agent]: I can help with that.", variables["conversation_context_block"]
        )
        self.assertIn(
            "[user]: The error is S3 sync timeout after 900s",
            variables["conversation_context_block"],
        )

    def test_rewrite_without_conversation_history_passes_empty_context_block(self):
        """When no conversation_history, the prompt should receive an empty conversation_context_block."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = (
            "agent failed OR error to refund OR return"
        )

        _result = rewriter.rewrite("agent failed to refund", enabled=True)

        call_args = rewriter.prompt_manager.render_prompt.call_args
        variables = call_args[0][1]
        self.assertEqual(variables["conversation_context_block"], "")


class TestQueryRewriterInit(unittest.TestCase):
    """Tests for QueryRewriter.__init__ parameter handling."""

    def test_default_model_name_is_none(self):
        """When no model name is provided, query_rewrite_model_name should be None."""
        rewriter = _make_rewriter()
        self.assertIsNone(rewriter.query_rewrite_model_name)

    def test_explicit_model_name_is_stored(self):
        """When a model name is provided, it should be stored on the instance."""
        rewriter = _make_rewriter(query_rewrite_model_name="custom-model")
        self.assertEqual(rewriter.query_rewrite_model_name, "custom-model")

    def test_no_model_name_omits_model_kwarg(self):
        """When no model name is set, generate_response should not receive a model kwarg."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = "expanded"

        rewriter.rewrite("test", enabled=True)

        call_kwargs = rewriter.llm_client.generate_response.call_args[1]
        self.assertNotIn("model", call_kwargs)


class TestLlmRewriteBranches(unittest.TestCase):
    """Tests for _llm_rewrite branch coverage."""

    def test_llm_returns_none_falls_back(self):
        """When LLM returns None (non-string), should fall back to original query."""
        rewriter = _make_rewriter()
        rewriter.llm_client.generate_response.return_value = None

        result = rewriter.rewrite("test query", enabled=True)

        self.assertEqual(result.fts_query, "test query")

    def test_llm_returns_invalid_rewrite_falls_back(self):
        """When LLM returns a string that fails validation, should fall back."""
        rewriter = _make_rewriter()
        # Contains curly braces, which _is_valid_rewrite rejects
        rewriter.llm_client.generate_response.return_value = '{"bad": "json"}'

        result = rewriter.rewrite("test query", enabled=True)

        self.assertEqual(result.fts_query, "test query")

    def test_explicit_model_passed_to_generate_response(self):
        """When model is explicitly provided, it should be passed to generate_response."""
        rewriter = _make_rewriter(query_rewrite_model_name="explicit-model")
        rewriter.llm_client.generate_response.return_value = "expanded query"

        result = rewriter.rewrite("test query", enabled=True)

        self.assertEqual(result.fts_query, "expanded query")
        # Verify model kwarg was passed to generate_response
        call_kwargs = rewriter.llm_client.generate_response.call_args[1]
        self.assertEqual(call_kwargs["model"], "explicit-model")


class TestExtractCandidateQuery(unittest.TestCase):
    """Tests for QueryRewriter._extract_candidate_query edge cases."""

    def test_code_block_json_without_valid_keys(self):
        """Fenced JSON with neither fts_query nor query key falls through to _clean_candidate."""
        output = '```json\n{"other_key": "value"}\n```'
        result = QueryRewriter._extract_candidate_query(output)
        # Falls through JSON key loop, then _clean_candidate on fenced content,
        # then to _clean_candidate on raw -- returns the raw cleaned text
        self.assertEqual(result, '{"other_key": "value"}')

    def test_code_block_json_with_empty_fts_query(self):
        """Fenced JSON with whitespace-only fts_query falls through to clean fenced content."""
        output = '```json\n{"fts_query": "  "}\n```'
        result = QueryRewriter._extract_candidate_query(output)
        # _clean_candidate("  ") returns None, falls to _clean_candidate on fenced content
        self.assertEqual(result, '{"fts_query": " "}')

    def test_code_block_json_with_query_key(self):
        """Fenced JSON with 'query' key (not fts_query) should be extracted."""
        output = '```json\n{"query": "refund OR return"}\n```'
        result = QueryRewriter._extract_candidate_query(output)
        self.assertEqual(result, "refund OR return")

    def test_code_block_non_json_content_that_cleans_to_empty(self):
        """Fenced content with only whitespace falls through; 'text' from language tag is cleaned from raw."""
        output = "```text\n   \n```"
        result = QueryRewriter._extract_candidate_query(output)
        # Fenced content is whitespace-only, _clean_candidate returns None.
        # Raw is the full string including ```, _clean_candidate returns "text" from first line
        self.assertEqual(result, "text")

    def test_raw_json_without_valid_keys(self):
        """Raw JSON dict without fts_query or query keys falls through to _clean_candidate on raw."""
        output = '{"unrelated_key": "value"}'
        result = QueryRewriter._extract_candidate_query(output)
        # Falls through JSON key loop, then _clean_candidate on raw returns the text as-is
        self.assertEqual(result, '{"unrelated_key": "value"}')

    def test_raw_json_with_empty_value(self):
        """Raw JSON with empty fts_query falls through to _clean_candidate on raw."""
        output = '{"fts_query": ""}'
        result = QueryRewriter._extract_candidate_query(output)
        # _clean_candidate("") returns None, falls through to _clean_candidate on raw
        self.assertEqual(result, '{"fts_query": ""}')

    def test_raw_json_with_query_key(self):
        """Raw JSON with 'query' key should be extracted."""
        output = '{"query": "refund OR return"}'
        result = QueryRewriter._extract_candidate_query(output)
        self.assertEqual(result, "refund OR return")

    def test_empty_input_returns_none(self):
        """Empty string should return None."""
        self.assertIsNone(QueryRewriter._extract_candidate_query(""))

    def test_whitespace_input_returns_none(self):
        """Whitespace-only string should return None."""
        self.assertIsNone(QueryRewriter._extract_candidate_query("   "))

    def test_none_input_returns_none(self):
        """None input should return None."""
        self.assertIsNone(QueryRewriter._extract_candidate_query(None))

    def test_fenced_json_with_non_string_fts_query(self):
        """Fenced JSON where fts_query value is not a string should skip it."""
        output = '```json\n{"fts_query": 123}\n```'
        result = QueryRewriter._extract_candidate_query(output)
        # fts_query is int, not str -- skipped; falls through to _clean_candidate
        self.assertIsNotNone(result)

    def test_raw_json_with_non_string_query(self):
        """Raw JSON where query value is not a string should skip it."""
        output = '{"query": 42}'
        result = QueryRewriter._extract_candidate_query(output)
        # query is int, not str -- skipped; falls through to _clean_candidate
        self.assertIsNotNone(result)

    def test_all_paths_exhausted_returns_none(self):
        """When all extraction and cleaning paths fail, should return None (line 212)."""
        # Triple backticks get stripped by _clean_candidate, yielding empty string -> None
        result = QueryRewriter._extract_candidate_query("```")
        self.assertIsNone(result)


class TestCleanCandidate(unittest.TestCase):
    """Tests for QueryRewriter._clean_candidate edge cases."""

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        self.assertIsNone(QueryRewriter._clean_candidate(""))

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string should return None."""
        self.assertIsNone(QueryRewriter._clean_candidate("   "))

    def test_multiline_text_returns_first_nonempty_line(self):
        """Multi-line text should return the first non-empty line."""
        result = QueryRewriter._clean_candidate("refund OR return\nreimburse OR credit")
        self.assertEqual(result, "refund OR return")

    def test_multiline_text_all_empty_lines(self):
        """Multi-line text with all empty lines should return None."""
        result = QueryRewriter._clean_candidate("\n  \n   \n")
        self.assertIsNone(result)

    def test_strips_prefix_patterns(self):
        """Should strip known prefix patterns like 'fts_query:'."""
        result = QueryRewriter._clean_candidate("fts_query: refund OR return")
        self.assertEqual(result, "refund OR return")

    def test_strips_quotes_and_backticks(self):
        """Should strip surrounding quotes and backticks."""
        result = QueryRewriter._clean_candidate('"refund OR return"')
        self.assertEqual(result, "refund OR return")


class TestIsValidRewrite(unittest.TestCase):
    """Tests for QueryRewriter._is_valid_rewrite rejection branches."""

    def test_empty_string_is_invalid(self):
        """Empty string should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite(""))

    def test_too_long_is_invalid(self):
        """Query exceeding MAX_REWRITE_LENGTH should be invalid."""
        long_query = "a " * 300  # 600 chars
        self.assertFalse(QueryRewriter._is_valid_rewrite(long_query))

    def test_curly_braces_invalid(self):
        """Query with curly braces should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite('{"fts_query": "test"}'))

    def test_square_brackets_invalid(self):
        """Query with square brackets should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite("test [query]"))

    def test_backticks_invalid(self):
        """Query with triple backticks should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite("```test```"))

    def test_no_alphanumeric_invalid(self):
        """Query with no alphanumeric characters should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite("--- ... !!!"))

    def test_unsafe_phrase_here_is(self):
        """Query containing unsafe phrase 'here is' should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite("here is the expanded query"))

    def test_unsafe_phrase_i_cannot(self):
        """Query containing 'i cannot' should be invalid."""
        self.assertFalse(QueryRewriter._is_valid_rewrite("i cannot rewrite this query"))

    def test_valid_query_passes(self):
        """Normal valid query should pass."""
        self.assertTrue(
            QueryRewriter._is_valid_rewrite("refund OR return OR reimburse")
        )


class TestFormatConversationContext(unittest.TestCase):
    """Unit tests for QueryRewriter._format_conversation_context."""

    def test_none_returns_empty_string(self):
        self.assertEqual(
            QueryRewriter._format_conversation_context(None),
            "",
        )

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(
            QueryRewriter._format_conversation_context([]),
            "",
        )

    def test_formats_conversation_turn_objects(self):
        turns = [
            ConversationTurn(role="user", content="Hello"),
            ConversationTurn(role="agent", content="Hi there"),
        ]
        result = QueryRewriter._format_conversation_context(turns)
        self.assertEqual(result, "[user]: Hello\n[agent]: Hi there")

    def test_formats_dict_turns(self):
        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "agent", "content": "Hi there"},
        ]
        result = QueryRewriter._format_conversation_context(turns)
        self.assertEqual(result, "[user]: Hello\n[agent]: Hi there")

    def test_truncates_at_char_limit(self):
        """Conversation context should stop adding turns when char limit is reached."""
        # Create a turn with content that nearly fills the budget
        long_content = "x" * 3990
        turns = [
            ConversationTurn(role="user", content=long_content),
            ConversationTurn(role="user", content="This should be excluded"),
        ]
        result = QueryRewriter._format_conversation_context(turns)
        self.assertIn(long_content, result)
        self.assertNotIn("This should be excluded", result)


if __name__ == "__main__":
    unittest.main()
