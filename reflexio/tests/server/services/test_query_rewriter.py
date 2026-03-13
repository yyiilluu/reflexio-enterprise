"""Unit tests for the QueryRewriter service.

Tests the critical paths: feature-flag bypass, LLM failure fallback,
successful rewrite propagation, and conversation-aware rewriting.
"""

import unittest
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    RewrittenQuery,
)

from reflexio.server.services.query_rewriter import QueryRewriter


def _make_rewriter(**overrides):
    """Create a QueryRewriter with mocked dependencies."""
    api_key_config = MagicMock()
    prompt_manager = MagicMock()
    prompt_manager.render_prompt.return_value = "rendered prompt"

    with (
        patch("reflexio.server.services.query_rewriter.LiteLLMClient"),
        patch("reflexio.server.services.query_rewriter.SiteVarManager") as mock_svm,
    ):
        mock_svm.return_value.get_site_var.return_value = {
            "query_rewrite_model_name": "gpt-5-nano"
        }
        rewriter = QueryRewriter(
            api_key_config=api_key_config,
            prompt_manager=prompt_manager,
            **overrides,
        )
    return rewriter  # noqa: RET504


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


if __name__ == "__main__":
    unittest.main()
