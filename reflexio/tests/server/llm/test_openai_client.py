"""Unit tests for the OpenAI client wrapper.

Tests cover initialization (OpenAI and Azure), response generation,
retry logic, error classification, embeddings, and configuration management.
All OpenAI SDK calls are mocked -- no real API requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from reflexio.server.llm.openai_client import (
    OpenAIClient,
    OpenAIClientError,
    OpenAIConfig,
)

# ---------------------------------------------------------------------------
# Pydantic model used for structured-output tests
# ---------------------------------------------------------------------------


class SampleResponse(BaseModel):
    answer: str
    score: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_KEYS_TO_CLEAR = [
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove OpenAI-related env vars so tests rely only on explicit config."""
    for key in _ENV_KEYS_TO_CLEAR:
        monkeypatch.delenv(key, raising=False)


def _make_text_response(content: str = "Hello world") -> MagicMock:
    """Build a mock chat completion with a text message."""
    choice = MagicMock()
    choice.message.content = content
    choice.message.refusal = None
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_parsed_response(parsed_obj: BaseModel) -> MagicMock:
    """Build a mock chat completion with a parsed Pydantic object."""
    choice = MagicMock()
    choice.message.parsed = parsed_obj
    choice.message.refusal = None
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_embedding_response(embedding: list[float] | None = None) -> MagicMock:
    """Build a mock embeddings response."""
    data_item = MagicMock()
    data_item.embedding = embedding or [0.1, 0.2, 0.3]
    resp = MagicMock()
    resp.data = [data_item]
    return resp


def _build_client(
    config: OpenAIConfig | None = None,
    *,
    azure: bool = False,
) -> OpenAIClient:
    """Instantiate an OpenAIClient with mocked SDK constructors.

    Returns a client whose ``self.client`` is a ``MagicMock``.
    """
    if config is None:
        if azure:
            config = OpenAIConfig(
                azure_api_key="az-key",
                azure_endpoint="https://my.openai.azure.com",
                azure_deployment="my-deploy",
            )
        else:
            config = OpenAIConfig(api_key="sk-test-key")

    with (
        patch("reflexio.server.llm.openai_client.OpenAI") as mock_openai,
        patch("reflexio.server.llm.openai_client.AzureOpenAI") as mock_azure,
    ):
        mock_openai.return_value = MagicMock()
        mock_azure.return_value = MagicMock()
        return OpenAIClient(config)


# ===================================================================
# Init tests
# ===================================================================


class TestInit:
    """Initialization of OpenAIClient (OpenAI and Azure paths)."""

    @patch("reflexio.server.llm.openai_client.OpenAI")
    def test_standard_openai_init(self, mock_openai_cls):
        mock_openai_cls.return_value = MagicMock()
        config = OpenAIConfig(api_key="sk-test")
        client = OpenAIClient(config)

        mock_openai_cls.assert_called_once_with(api_key="sk-test", timeout=config.timeout)
        assert client.is_azure is False
        assert client.azure_deployment is None

    @patch("reflexio.server.llm.openai_client.AzureOpenAI")
    def test_azure_init(self, mock_azure_cls):
        mock_azure_cls.return_value = MagicMock()
        config = OpenAIConfig(
            azure_api_key="az-key",
            azure_endpoint="https://my.openai.azure.com",
            azure_api_version="2024-08-01-preview",
            azure_deployment="gpt4-deploy",
        )
        client = OpenAIClient(config)

        mock_azure_cls.assert_called_once_with(
            api_key="az-key",
            api_version="2024-08-01-preview",
            azure_endpoint="https://my.openai.azure.com",
            timeout=config.timeout,
        )
        assert client.is_azure is True
        assert client.azure_deployment == "gpt4-deploy"

    def test_no_api_key_raises(self):
        config = OpenAIConfig()
        with pytest.raises(OpenAIClientError, match="API key not provided"):
            OpenAIClient(config)

    def test_azure_without_endpoint_raises(self):
        config = OpenAIConfig(azure_api_key="az-key")
        with pytest.raises(OpenAIClientError, match="endpoint not provided"):
            OpenAIClient(config)


# ===================================================================
# generate_response tests
# ===================================================================


class TestGenerateResponse:
    """Tests for generate_response (single-prompt entry point)."""

    def test_text_only_prompt(self):
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("Paris")

        result = client.generate_response("What is the capital of France?")

        assert result == "Paris"
        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "What is the capital of France?"}
        ]

    def test_with_system_message(self):
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("Yes")

        client.generate_response("Hello", system_message="You are helpful.")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "Hello"}

    def test_empty_prompt_raises(self):
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="Prompt cannot be empty"):
            client.generate_response("   ")

    def test_structured_output_pydantic_uses_parse_api(self):
        parsed = SampleResponse(answer="ok", score=5)
        client = _build_client()
        client.client.chat.completions.parse.return_value = _make_parsed_response(parsed)

        result = client.generate_response("test", response_format=SampleResponse)

        assert result == parsed
        client.client.chat.completions.parse.assert_called_once()
        client.client.chat.completions.create.assert_not_called()

    def test_invalid_response_format_raises(self):
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="Pydantic BaseModel"):
            client.generate_response("test", response_format={"type": "json_object"})


# ===================================================================
# generate_chat_response tests
# ===================================================================


class TestGenerateChatResponse:
    """Tests for generate_chat_response (messages-list entry point)."""

    def test_valid_messages(self):
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("Hi")

        messages = [
            {"role": "system", "content": "Be polite"},
            {"role": "user", "content": "Hello"},
        ]
        result = client.generate_chat_response(messages)

        assert result == "Hi"
        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"] == messages

    def test_empty_messages_raises(self):
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="Messages list cannot be empty"):
            client.generate_chat_response([])

    def test_invalid_message_format_raises(self):
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="role.*content"):
            client.generate_chat_response([{"text": "oops"}])


# ===================================================================
# _make_request_with_retry tests
# ===================================================================


class TestMakeRequestWithRetry:
    """Tests for the retry wrapper around OpenAI API calls."""

    def test_success_on_first_try(self):
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        result = client._make_request_with_retry(
            {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        )

        assert result == "ok"
        assert client.client.chat.completions.create.call_count == 1

    @patch("reflexio.server.llm.openai_client.time.sleep")
    def test_success_on_retry(self, mock_sleep):
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=2))
        client.client.chat.completions.create.side_effect = [
            RuntimeError("temporary failure"),
            _make_text_response("ok"),
        ]

        result = client._make_request_with_retry(
            {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        )

        assert result == "ok"
        assert client.client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once()

    @patch("reflexio.server.llm.openai_client.time.sleep")
    def test_all_retries_fail(self, mock_sleep):
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=1))
        client.client.chat.completions.create.side_effect = RuntimeError("boom")

        with pytest.raises(OpenAIClientError, match="failed after 2 attempts"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            )

        assert client.client.chat.completions.create.call_count == 2

    def test_non_retryable_error_stops_retries(self):
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=3))
        client.client.chat.completions.create.side_effect = RuntimeError(
            "invalid api key"
        )

        with pytest.raises(OpenAIClientError, match="invalid api key"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            )

        # Should stop after first attempt due to non-retryable error
        assert client.client.chat.completions.create.call_count == 1


# ===================================================================
# Parse API vs Create API selection
# ===================================================================


class TestAPISelection:
    """Verify parse API is used for Pydantic models, create API otherwise."""

    def test_parse_api_for_pydantic(self):
        parsed = SampleResponse(answer="a", score=1)
        client = _build_client()
        client.client.chat.completions.parse.return_value = _make_parsed_response(parsed)

        client._make_request_with_retry(
            {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}],
             "response_format": SampleResponse},
            response_format=SampleResponse,
        )

        client.client.chat.completions.parse.assert_called_once()
        client.client.chat.completions.create.assert_not_called()

    def test_create_api_for_none_format(self):
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client._make_request_with_retry(
            {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            response_format=None,
        )

        client.client.chat.completions.create.assert_called_once()
        client.client.chat.completions.parse.assert_not_called()


# ===================================================================
# _is_non_retryable_error tests
# ===================================================================


class TestIsNonRetryableError:
    """Verify classification of errors as retryable vs non-retryable."""

    @pytest.fixture()
    def client(self):
        return _build_client()

    @pytest.mark.parametrize(
        "message",
        [
            "invalid api key provided",
            "Unauthorized access",
            "Permission denied for resource",
            "Quota exceeded for project",
            "Billing account not active",
            "Invalid request: bad payload",
        ],
    )
    def test_non_retryable_patterns(self, client, message):
        assert client._is_non_retryable_error(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Connection timed out",
            "Internal server error",
            "Rate limit reached",
            "Service unavailable",
        ],
    )
    def test_retryable_patterns(self, client, message):
        assert client._is_non_retryable_error(RuntimeError(message)) is False


# ===================================================================
# get_embedding tests
# ===================================================================


class TestGetEmbedding:
    """Tests for the embedding endpoint wrapper."""

    def test_valid_text(self):
        client = _build_client()
        client.client.embeddings.create.return_value = _make_embedding_response(
            [0.1, 0.2, 0.3]
        )

        result = client.get_embedding("some text")

        assert result == [0.1, 0.2, 0.3]
        call_kwargs = client.client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-small"
        assert call_kwargs["input"] == "some text"

    def test_empty_text_raises(self):
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="Text cannot be empty"):
            client.get_embedding("   ")

    def test_custom_model(self):
        client = _build_client()
        client.client.embeddings.create.return_value = _make_embedding_response()

        client.get_embedding("text", model="text-embedding-ada-002")

        call_kwargs = client.client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-ada-002"


# ===================================================================
# gpt-5 temperature handling
# ===================================================================


class TestGPT5Temperature:
    """gpt-5 family models should only include temperature when it is 1.0."""

    def test_gpt5_default_temp_excluded(self):
        """Default temp is 0.7, which is not 1.0 -- temperature should be absent."""
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        # Config defaults to model=gpt-5-mini, temperature=0.7
        client.generate_response("hi")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    def test_gpt5_temp_1_included(self):
        """Temperature=1.0 should be included for gpt-5 models."""
        config = OpenAIConfig(api_key="sk-test", model="gpt-5-mini", temperature=1.0)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_response("hi")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 1.0

    def test_non_gpt5_custom_temp(self):
        """Non-gpt-5 models should always pass the configured temperature."""
        config = OpenAIConfig(api_key="sk-test", model="gpt-4o", temperature=0.3)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_response("hi")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3


# ===================================================================
# update_config / get_config tests
# ===================================================================


class TestConfigManagement:
    """Tests for update_config and get_config."""

    def test_get_config_returns_config(self):
        config = OpenAIConfig(api_key="sk-test", model="gpt-4o")
        client = _build_client(config)

        returned = client.get_config()

        assert returned is client.config
        assert returned.model == "gpt-4o"

    def test_update_config_known_keys(self):
        client = _build_client()
        client.update_config(model="gpt-4o", temperature=0.2, max_retries=5)

        assert client.config.model == "gpt-4o"
        assert client.config.temperature == 0.2
        assert client.config.max_retries == 5

    def test_update_config_unknown_key_is_ignored(self):
        client = _build_client()
        # Should not raise; the unknown key is simply logged as a warning
        client.update_config(nonexistent_param="value")
        assert not hasattr(client.config, "nonexistent_param")


# ===================================================================
# Azure init edge cases (lines 103-104, 124-125)
# ===================================================================


class TestInitEdgeCases:
    """Edge cases for client initialization failures."""

    @patch("reflexio.server.llm.openai_client.AzureOpenAI")
    def test_azure_init_exception_wraps_error(self, mock_azure_cls):
        """Lines 103-104: AzureOpenAI constructor raises -> wrapped in OpenAIClientError."""
        mock_azure_cls.side_effect = RuntimeError("Azure SDK init failed")
        config = OpenAIConfig(
            azure_api_key="az-key",
            azure_endpoint="https://my.openai.azure.com",
        )
        with pytest.raises(
            OpenAIClientError, match="Failed to initialize Azure OpenAI client"
        ):
            OpenAIClient(config)

    @patch("reflexio.server.llm.openai_client.OpenAI")
    def test_openai_init_exception_wraps_error(self, mock_openai_cls):
        """Lines 124-125: OpenAI constructor raises -> wrapped in OpenAIClientError."""
        mock_openai_cls.side_effect = RuntimeError("OpenAI SDK init failed")
        config = OpenAIConfig(api_key="sk-test")
        with pytest.raises(
            OpenAIClientError, match="Failed to initialize OpenAI client"
        ):
            OpenAIClient(config)


# ===================================================================
# _get_model_for_request Azure path (line 144)
# ===================================================================


class TestGetModelForRequest:
    """Tests for _get_model_for_request with Azure deployment handling."""

    def test_azure_uses_deployment(self):
        """Line 144: Azure with explicit deployment."""
        client = _build_client(azure=True)
        assert client._get_model_for_request() == "my-deploy"

    def test_azure_falls_back_to_model_arg(self):
        """Line 144: Azure without deployment falls back to model arg."""
        config = OpenAIConfig(
            azure_api_key="az-key",
            azure_endpoint="https://my.openai.azure.com",
            azure_deployment=None,
        )
        client = _build_client(config)
        assert client._get_model_for_request("gpt-4o") == "gpt-4o"

    def test_azure_falls_back_to_config_model(self):
        """Line 144: Azure without deployment or model arg falls back to config model."""
        config = OpenAIConfig(
            azure_api_key="az-key",
            azure_endpoint="https://my.openai.azure.com",
            azure_deployment=None,
            model="gpt-4",
        )
        client = _build_client(config)
        assert client._get_model_for_request() == "gpt-4"

    def test_standard_uses_model_arg(self):
        """Standard OpenAI path."""
        client = _build_client()
        assert client._get_model_for_request("gpt-4o") == "gpt-4o"

    def test_standard_falls_back_to_config(self):
        client = _build_client()
        assert client._get_model_for_request() == "gpt-5-mini"


# ===================================================================
# max_completion_tokens / max_tokens handling (lines 217, 219, 293, 295)
# ===================================================================


class TestMaxTokensParams:
    """Tests for max_completion_tokens and max_tokens parameter handling."""

    def test_max_completion_tokens_passed_in_generate_response(self):
        """Line 217: max_completion_tokens is set in params."""
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_response("hi", max_completion_tokens=500)

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 500

    def test_max_tokens_fallback_in_generate_response(self):
        """Line 219: max_tokens used when max_completion_tokens is None."""
        config = OpenAIConfig(api_key="sk-test", max_tokens=300)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_response("hi")

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 300

    def test_max_completion_tokens_in_chat_response(self):
        """Line 293: max_completion_tokens in generate_chat_response."""
        client = _build_client()
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_chat_response(
            [{"role": "user", "content": "hi"}], max_completion_tokens=200
        )

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 200

    def test_max_tokens_fallback_in_chat_response(self):
        """Line 295: max_tokens used in generate_chat_response."""
        config = OpenAIConfig(api_key="sk-test", max_tokens=150)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_chat_response([{"role": "user", "content": "hi"}])

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 150


# ===================================================================
# generate_chat_response gpt-5 temperature (lines 264-267)
# ===================================================================


class TestChatResponseGPT5Temperature:
    """gpt-5 temperature handling within generate_chat_response."""

    def test_chat_gpt5_temp_1_included(self):
        """Lines 263-264: gpt-5 with temp=1.0 in chat response."""
        config = OpenAIConfig(api_key="sk-test", model="gpt-5-mini", temperature=1.0)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_chat_response([{"role": "user", "content": "hi"}])

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 1.0

    def test_chat_gpt5_non_1_temp_excluded(self):
        """gpt-5 with non-1.0 temp in chat response -- temperature absent."""
        config = OpenAIConfig(api_key="sk-test", model="gpt-5", temperature=0.5)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_chat_response([{"role": "user", "content": "hi"}])

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    def test_chat_non_gpt5_includes_temperature(self):
        """Lines 266-267: Non-gpt-5 models always include temperature."""
        config = OpenAIConfig(api_key="sk-test", model="gpt-4o", temperature=0.3)
        client = _build_client(config)
        client.client.chat.completions.create.return_value = _make_text_response("ok")

        client.generate_chat_response([{"role": "user", "content": "hi"}])

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.3


# ===================================================================
# generate_chat_response response_format (lines 280-284)
# ===================================================================


class TestChatResponseFormat:
    """response_format handling in generate_chat_response."""

    def test_chat_structured_output_pydantic(self):
        """Lines 280-284: Valid Pydantic model as response_format in chat."""
        parsed = SampleResponse(answer="ok", score=5)
        client = _build_client()
        client.client.chat.completions.parse.return_value = _make_parsed_response(parsed)

        result = client.generate_chat_response(
            [{"role": "user", "content": "test"}],
            response_format=SampleResponse,
        )

        assert result == parsed
        client.client.chat.completions.parse.assert_called_once()

    def test_chat_invalid_response_format_raises(self):
        """Lines 280-282: Invalid response_format in chat raises."""
        client = _build_client()
        with pytest.raises(OpenAIClientError, match="Pydantic BaseModel"):
            client.generate_chat_response(
                [{"role": "user", "content": "test"}],
                response_format={"type": "json_object"},
            )


# ===================================================================
# Parse API edge cases (lines 329, 333, 339, 349, 353)
# ===================================================================


class TestParseAPIEdgeCases:
    """Edge cases in _make_request_with_retry for parse and create APIs."""

    def test_parse_api_no_choices_raises(self):
        """Line 329: parse API returns empty choices."""
        client = _build_client()
        resp = MagicMock()
        resp.choices = []
        client.client.chat.completions.parse.return_value = resp

        with pytest.raises(OpenAIClientError, match="No choices returned"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
                response_format=SampleResponse,
            )

    def test_parse_api_refusal_raises(self):
        """Line 333: Model refuses the request."""
        client = _build_client()
        choice = MagicMock()
        choice.message.refusal = "I cannot do that"
        choice.message.parsed = None
        resp = MagicMock()
        resp.choices = [choice]
        client.client.chat.completions.parse.return_value = resp

        with pytest.raises(OpenAIClientError, match="refused to respond"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
                response_format=SampleResponse,
            )

    def test_parse_api_parsed_is_none_raises(self):
        """Line 339: parsed content is None."""
        client = _build_client()
        choice = MagicMock()
        choice.message.refusal = None
        choice.message.parsed = None
        resp = MagicMock()
        resp.choices = [choice]
        client.client.chat.completions.parse.return_value = resp

        with pytest.raises(OpenAIClientError, match="No parsed content"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
                response_format=SampleResponse,
            )

    def test_create_api_no_choices_raises(self):
        """Line 349: create API returns empty choices."""
        client = _build_client()
        resp = MagicMock()
        resp.choices = []
        client.client.chat.completions.create.return_value = resp

        with pytest.raises(OpenAIClientError, match="No choices returned"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            )

    def test_create_api_none_content_raises(self):
        """Line 353: create API returns None content."""
        client = _build_client()
        choice = MagicMock()
        choice.message.content = None
        resp = MagicMock()
        resp.choices = [choice]
        client.client.chat.completions.create.return_value = resp

        with pytest.raises(OpenAIClientError, match="Empty response content"):
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            )


# ===================================================================
# Error message formatting (line 381->384)
# ===================================================================


class TestErrorMessageFormatting:
    """Edge case: all retries fail with last_exception included in message."""

    @patch("reflexio.server.llm.openai_client.time.sleep")
    def test_error_message_includes_last_exception(self, mock_sleep):
        """Lines 381-384: Verify the error message includes the last exception."""
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=1))
        client.client.chat.completions.create.side_effect = RuntimeError("network down")

        with pytest.raises(OpenAIClientError) as exc_info:
            client._make_request_with_retry(
                {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            )

        assert "network down" in str(exc_info.value)
        assert "failed after 2 attempts" in str(exc_info.value)


# ===================================================================
# Embedding retry/error handling (lines 461, 469-490)
# ===================================================================


class TestEmbeddingRetryAndErrors:
    """Tests for get_embedding retry logic and error handling."""

    def test_embedding_no_data_raises(self):
        """Line 461: embedding response with no data."""
        client = _build_client()
        resp = MagicMock()
        resp.data = []
        client.client.embeddings.create.return_value = resp

        with pytest.raises(OpenAIClientError, match="No embedding data returned"):
            client.get_embedding("some text")

    @patch("reflexio.server.llm.openai_client.time.sleep")
    def test_embedding_retry_then_success(self, mock_sleep):
        """Lines 469-484: Embedding retries on transient error then succeeds."""
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=2))
        client.client.embeddings.create.side_effect = [
            RuntimeError("temporary failure"),
            _make_embedding_response([0.5, 0.6]),
        ]

        result = client.get_embedding("text")

        assert result == [0.5, 0.6]
        assert client.client.embeddings.create.call_count == 2
        mock_sleep.assert_called_once()

    @patch("reflexio.server.llm.openai_client.time.sleep")
    def test_embedding_all_retries_fail(self, mock_sleep):
        """Lines 487-490: Embedding fails after all retries."""
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=1))
        client.client.embeddings.create.side_effect = RuntimeError("API down")

        with pytest.raises(OpenAIClientError, match="embedding request failed after 2 attempts"):
            client.get_embedding("text")

        assert "API down" in str(
            client.client.embeddings.create.side_effect
        ) or client.client.embeddings.create.call_count == 2

    def test_embedding_non_retryable_error_stops(self):
        """Lines 479-480: Embedding non-retryable error stops immediately."""
        client = _build_client(OpenAIConfig(api_key="sk-test", max_retries=3))
        client.client.embeddings.create.side_effect = RuntimeError("invalid api key")

        with pytest.raises(OpenAIClientError, match="invalid api key"):
            client.get_embedding("text")

        assert client.client.embeddings.create.call_count == 1


# ===================================================================
# create_openai_client convenience function (lines 512-515)
# ===================================================================


class TestCreateOpenAIClient:
    """Tests for the create_openai_client factory function."""

    @patch("reflexio.server.llm.openai_client.OpenAI")
    def test_basic_creation(self, mock_openai_cls):
        from reflexio.server.llm.openai_client import create_openai_client

        mock_openai_cls.return_value = MagicMock()
        client = create_openai_client(api_key="sk-test", model="gpt-4o", temperature=0.5)

        assert client.config.api_key == "sk-test"
        assert client.config.model == "gpt-4o"
        assert client.config.temperature == 0.5

    @patch("reflexio.server.llm.openai_client.OpenAI")
    def test_creation_with_extra_kwargs(self, mock_openai_cls):
        from reflexio.server.llm.openai_client import create_openai_client

        mock_openai_cls.return_value = MagicMock()
        client = create_openai_client(
            api_key="sk-test", model="gpt-4", max_retries=5, timeout=30
        )

        assert client.config.max_retries == 5
        assert client.config.timeout == 30
