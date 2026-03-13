"""
Query rewriter service that expands user search queries with synonyms
for improved full-text search recall using websearch_to_tsquery syntax.
"""

import json
import logging
import re

from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    RewrittenQuery,
)
from reflexio_commons.config_schema import APIKeyConfig

from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)


class QueryRewriter:
    """Rewrites search queries by expanding them with synonyms via LLM.

    Uses a fast, cheap model (query_rewrite_model_name from llm_model_setting.json)
    to produce expanded FTS queries in websearch_to_tsquery format.
    Falls back to the original query on any failure.
    """

    MAX_REWRITE_LENGTH = 512
    MAX_CONVERSATION_TURNS = 10
    MAX_CONVERSATION_CHARS = 4000
    _CODE_BLOCK_PATTERN = re.compile(r"```(?:\w+)?\s*([\s\S]*?)```")
    _PREFIX_PATTERN = re.compile(
        r"^(?:fts_query|query|expanded\s+query|search\s+query)\s*[:=-]\s*",
        re.IGNORECASE,
    )
    _UNSAFE_PHRASES = (
        "here is",
        "output:",
        "json {",
        "```json",
        "i cannot",
        "i can't",
    )

    def __init__(
        self,
        api_key_config: APIKeyConfig | None,
        prompt_manager: PromptManager,
        model: str | None = None,
        timeout: int = 5,
    ):
        """
        Initialize the QueryRewriter.

        Args:
            api_key_config (APIKeyConfig, optional): API key config for the LLM
            prompt_manager (PromptManager): Prompt manager for rendering prompts
            model (str, optional): LLM model override. Defaults to query_rewrite_model_name from llm_model_setting.json
            timeout (int): Request timeout in seconds. Defaults to 5
        """
        self.prompt_manager = prompt_manager
        if model is None:
            model_setting = SiteVarManager().get_site_var("llm_model_setting")
            model = (
                model_setting.get("query_rewrite_model_name", "gpt-5-nano")
                if isinstance(model_setting, dict)
                else "gpt-5-nano"
            )
        llm_config = LiteLLMConfig(
            model=model,
            temperature=0.0,
            max_tokens=1024,
            timeout=timeout,
            max_retries=1,
            api_key_config=api_key_config,
        )
        self.llm_client = LiteLLMClient(llm_config)

    def rewrite(
        self,
        query: str,
        enabled: bool = True,
        conversation_history: list[ConversationTurn] | None = None,
    ) -> RewrittenQuery:
        """
        Rewrite a search query with expanded synonyms, optionally using conversation context.

        When disabled or on failure, returns the original query unchanged.

        Args:
            query (str): The original user search query
            enabled (bool): Whether query rewriting is enabled. When False,
                skips LLM call and returns fallback immediately.
            conversation_history (list, optional): Prior conversation turns for context-aware rewriting.
                Each item should have 'role' and 'content' attributes.

        Returns:
            RewrittenQuery: The rewritten query with expanded FTS terms
        """
        if not enabled:
            return self._fallback_rewrite(query)

        try:
            return self._llm_rewrite(query, conversation_history=conversation_history)
        except Exception as e:
            logger.warning("Query rewrite failed, using fallback: %s", e)
            return self._fallback_rewrite(query)

    def _llm_rewrite(
        self,
        query: str,
        conversation_history: list[ConversationTurn] | None = None,
    ) -> RewrittenQuery:
        """
        Use LLM to expand the query with synonyms, optionally incorporating conversation context.

        Args:
            query (str): The original search query
            conversation_history (list, optional): Prior conversation turns

        Returns:
            RewrittenQuery: LLM-generated expanded query

        Raises:
            Exception: If LLM call or parsing fails
        """
        conversation_context = self._format_conversation_context(conversation_history)
        conversation_context_block = (
            f"\nConversation context: {conversation_context}\n"
            if conversation_context
            else ""
        )
        prompt = self.prompt_manager.render_prompt(
            "query_rewrite",
            {"query": query, "conversation_context_block": conversation_context_block},
        )
        result = self.llm_client.generate_response(prompt)
        logger.debug("Query rewrite response: %s", result)

        if isinstance(result, str):
            extracted = self._extract_candidate_query(result)
            if extracted and self._is_valid_rewrite(extracted):
                return RewrittenQuery(fts_query=extracted)
            logger.warning("LLM returned invalid query rewrite text, %s", extracted)
            return self._fallback_rewrite(query)

        logger.warning("LLM returned empty response for query rewrite")
        return self._fallback_rewrite(query)

    @classmethod
    def _extract_candidate_query(cls, output: str) -> str | None:
        """
        Extract a candidate query string from raw model output.

        Args:
            output (str): Raw LLM response text

        Returns:
            Optional[str]: Candidate query if extractable, otherwise None
        """
        if not output or not output.strip():
            return None

        raw = output.strip()

        # Markdown code-fence fallback
        code_match = cls._CODE_BLOCK_PATTERN.search(raw)
        if code_match:
            fenced_content = code_match.group(1).strip()

            # Handle fenced JSON payloads like:
            # ```json
            # {"fts_query":"..."}
            # ```
            try:
                parsed_fenced = json.loads(fenced_content)
                if isinstance(parsed_fenced, dict):
                    for key in ("fts_query", "query"):
                        value = parsed_fenced.get(key)
                        if isinstance(value, str):
                            cleaned = cls._clean_candidate(value)
                            if cleaned:
                                return cleaned
            except json.JSONDecodeError:
                pass

            cleaned = cls._clean_candidate(fenced_content)
            if cleaned:
                return cleaned

        # JSON-wrapper fallback (defensive compatibility path)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key in ("fts_query", "query"):
                    value = parsed.get(key)
                    if isinstance(value, str):
                        cleaned = cls._clean_candidate(value)
                        if cleaned:
                            return cleaned
        except json.JSONDecodeError:
            pass

        # Direct output path (expected case)
        cleaned = cls._clean_candidate(raw)
        if cleaned:
            return cleaned

        return None

    @classmethod
    def _clean_candidate(cls, text: str) -> str | None:
        """
        Normalize candidate query text.

        Args:
            text (str): Candidate raw text

        Returns:
            Optional[str]: Cleaned candidate, or None if empty
        """
        candidate = text.strip()
        if not candidate:
            return None

        # If multi-line text slipped through, prefer the first non-empty line.
        if "\n" in candidate:
            lines = [line.strip() for line in candidate.splitlines() if line.strip()]
            if not lines:
                return None
            candidate = lines[0]

        candidate = cls._PREFIX_PATTERN.sub("", candidate).strip()
        candidate = candidate.strip("`\"' ")
        candidate = " ".join(candidate.split())
        return candidate or None

    @classmethod
    def _is_valid_rewrite(cls, query: str) -> bool:
        """
        Validate candidate rewrite before passing it downstream.

        Args:
            query (str): Candidate rewritten query

        Returns:
            bool: True when the query looks safe and usable
        """
        if not query:
            return False
        if len(query) > cls.MAX_REWRITE_LENGTH:
            return False
        if any(marker in query for marker in ("{", "}", "[", "]", "```")):
            return False
        if not any(char.isalnum() for char in query):
            return False

        lower_query = query.lower()
        return not any(phrase in lower_query for phrase in cls._UNSAFE_PHRASES)

    @staticmethod
    def _format_conversation_context(
        conversation_history: list[ConversationTurn] | None = None,
    ) -> str:
        """
        Format conversation history into a string for the prompt.

        Args:
            conversation_history (list, optional): List of conversation turns with role and content attributes

        Returns:
            str: Formatted conversation context, or empty string when empty/None
        """
        if not conversation_history:
            return ""

        # Limit to the most recent turns to avoid prompt overflow
        truncated = conversation_history[-QueryRewriter.MAX_CONVERSATION_TURNS :]

        lines = []
        total_chars = 0
        for turn in truncated:
            if isinstance(turn, dict):
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
            else:
                role = turn.role
                content = turn.content
            line = f"[{role}]: {content}"
            if total_chars + len(line) > QueryRewriter.MAX_CONVERSATION_CHARS:
                break
            lines.append(line)
            total_chars += len(line)
        return "\n".join(lines)

    def _fallback_rewrite(self, query: str) -> RewrittenQuery:
        """
        Return the original query unchanged as a fallback.

        Args:
            query (str): The original search query

        Returns:
            RewrittenQuery: Fallback with original query
        """
        return RewrittenQuery(fts_query=query)
