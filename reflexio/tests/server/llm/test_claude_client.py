"""
Unit tests for the Claude client.

Tests cover initialization, response generation, retry logic, structured output parsing,
image encoding helpers, error classification, and embedding delegation.
All Anthropic API calls are mocked to avoid real network requests.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reflexio.server.llm.claude_client import (
    ClaudeClient,
    ClaudeClientError,
    ClaudeConfig,
    create_image_content_block,
    encode_image_bytes_to_base64,
    encode_image_to_base64,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Stub exception class mirroring OpenAIClientError for get_embedding tests
_OpenAIClientErrorStub = type("OpenAIClientError", (Exception,), {})


def _make_text_block(text: str) -> MagicMock:
    """Create a mock content block with a text attribute."""
    block = MagicMock()
    block.text = text
    block.json = None
    block.content = ""
    return block


def _make_json_block(data: dict[str, Any]) -> MagicMock:
    """Create a mock content block with a json attribute."""
    block = MagicMock()
    block.text = None
    block.json = data
    block.content = ""
    return block


def _make_bare_block(content_str: str) -> MagicMock:
    """Create a mock content block with no text/json attributes (fallback path)."""
    block = MagicMock(spec=[])
    block.text = None
    block.json = None
    block.content = content_str
    return block


def _make_response(*blocks: MagicMock) -> MagicMock:
    """Wrap content blocks into a mock Anthropic Message response."""
    response = MagicMock()
    response.content = list(blocks)
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_config() -> ClaudeConfig:
    """Return a config with a fake API key and fast retries."""
    return ClaudeConfig(
        api_key="sk-ant-test-key-123",
        max_retries=2,
        retry_delay=0.0,  # no actual sleep during tests
    )


@pytest.fixture
def mock_anthropic():
    """Patch the Anthropic constructor and yield (mock_class, mock_instance)."""
    with patch("reflexio.server.llm.claude_client.Anthropic") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_cls, mock_instance


@pytest.fixture
def client(claude_config, mock_anthropic) -> ClaudeClient:
    """Return a ClaudeClient with a mocked Anthropic backend."""
    return ClaudeClient(claude_config)


# ====================================================================
# Init tests
# ====================================================================


class TestInit:
    """Tests for ClaudeClient.__init__."""

    def test_init_with_config_key(self, mock_anthropic):
        """Client should initialize using the key from config."""
        config = ClaudeConfig(api_key="sk-ant-from-config")
        client = ClaudeClient(config)
        assert client.config.api_key == "sk-ant-from-config"

    def test_init_with_env_key(self, mock_anthropic, monkeypatch):
        """Client should fall back to ANTHROPIC_API_KEY env var."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
        config = ClaudeConfig(api_key=None)
        client = ClaudeClient(config)
        assert client.config is config

    def test_init_no_key_raises(self, mock_anthropic, monkeypatch):
        """Client should raise ClaudeClientError when no key is available."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = ClaudeConfig(api_key=None)
        with pytest.raises(ClaudeClientError, match="API key not provided"):
            ClaudeClient(config)


# ====================================================================
# generate_response tests
# ====================================================================


class TestGenerateResponse:
    """Tests for ClaudeClient.generate_response."""

    def test_text_only_prompt(self, client, mock_anthropic):
        """Simple text prompt should pass a single user message."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("Hello!")
        )

        result = client.generate_response("Hi there")
        assert result == "Hello!"

        call_kwargs = mock_inst.messages.create.call_args[1]
        assert call_kwargs["messages"] == [
            {"role": "user", "content": "Hi there"}
        ]

    def test_with_system_message(self, client, mock_anthropic):
        """System message should be passed as a top-level 'system' param."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("response")
        )

        client.generate_response("question", system_message="You are helpful")

        call_kwargs = mock_inst.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful"

    def test_with_images(self, client, mock_anthropic, tmp_path):
        """Images should be encoded and placed before the text block."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("I see an image")
        )

        # Create a tiny valid file
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"\x89PNG fake image data")

        with patch(
            "reflexio.server.llm.claude_client.create_image_content_block"
        ) as mock_create:
            mock_create.return_value = {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "abc"},
            }

            result = client.generate_response(
                "describe this", images=[str(img_path)]
            )

        assert result == "I see an image"
        call_kwargs = mock_inst.messages.create.call_args[1]
        content_blocks = call_kwargs["messages"][0]["content"]
        # Image block first, then text
        assert content_blocks[0]["type"] == "image"
        assert content_blocks[-1] == {"type": "text", "text": "describe this"}

    def test_with_bytes_image(self, client, mock_anthropic):
        """Bytes images should use the image_media_type kwarg."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("ok")
        )

        raw = b"\x89PNG fake"

        with patch(
            "reflexio.server.llm.claude_client.create_image_content_block"
        ) as mock_create:
            mock_create.return_value = {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": "x"},
            }

            client.generate_response(
                "describe", images=[raw], image_media_type="image/jpeg"
            )
            mock_create.assert_called_once_with(raw, media_type="image/jpeg")

    def test_with_preformatted_image_dict(self, client, mock_anthropic):
        """Pre-formatted dicts should pass through unchanged."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("ok")
        )

        block = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}
        client.generate_response("describe", images=[block])

        call_kwargs = mock_inst.messages.create.call_args[1]
        assert call_kwargs["messages"][0]["content"][0] is block

    def test_empty_prompt_raises(self, client):
        """Empty or whitespace-only prompt should raise."""
        with pytest.raises(ClaudeClientError, match="Prompt cannot be empty"):
            client.generate_response("   ")


# ====================================================================
# generate_chat_response tests
# ====================================================================


class TestGenerateChatResponse:
    """Tests for ClaudeClient.generate_chat_response."""

    def test_valid_messages(self, client, mock_anthropic):
        """User/assistant messages should be forwarded correctly."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("sure")
        )

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
        ]

        result = client.generate_chat_response(messages)
        assert result == "sure"

        call_kwargs = mock_inst.messages.create.call_args[1]
        assert call_kwargs["messages"] == messages

    def test_system_message_separation(self, client, mock_anthropic):
        """System messages should be extracted and joined into the system param."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("ok")
        )

        messages = [
            {"role": "system", "content": "You are a bot"},
            {"role": "user", "content": "Hi"},
        ]

        client.generate_chat_response(messages, system_message="Be concise")

        call_kwargs = mock_inst.messages.create.call_args[1]
        # system messages from both sources should be joined
        assert "You are a bot" in call_kwargs["system"]
        assert "Be concise" in call_kwargs["system"]
        # Only user/assistant in messages list
        assert all(m["role"] != "system" for m in call_kwargs["messages"])

    def test_empty_messages_raises(self, client):
        """Empty message list should raise."""
        with pytest.raises(ClaudeClientError, match="Messages list cannot be empty"):
            client.generate_chat_response([])

    def test_invalid_message_format_raises(self, client):
        """Messages without role/content should raise."""
        with pytest.raises(ClaudeClientError, match="'role' and 'content'"):
            client.generate_chat_response([{"text": "hi"}])

    def test_system_only_messages_raises(self, client):
        """Only system messages (no user/assistant) should raise."""
        with pytest.raises(ClaudeClientError, match="At least one user or assistant"):
            client.generate_chat_response(
                [{"role": "system", "content": "system only"}]
            )

    def test_invalid_role_raises(self, client):
        """Unknown role should raise."""
        with pytest.raises(ClaudeClientError, match="got 'admin'"):
            client.generate_chat_response(
                [{"role": "admin", "content": "hi"}]
            )

    def test_system_message_non_string_raises(self, client):
        """System message with non-string content should raise."""
        with pytest.raises(ClaudeClientError, match="System message content must be a string"):
            client.generate_chat_response(
                [
                    {"role": "system", "content": ["not", "a", "string"]},
                    {"role": "user", "content": "hi"},
                ]
            )


# ====================================================================
# _make_request_with_retry tests
# ====================================================================


class TestMakeRequestWithRetry:
    """Tests for retry logic and response block concatenation."""

    def test_concatenation_of_text_blocks(self, client, mock_anthropic):
        """Multiple text blocks should be concatenated."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("Hello "),
            _make_text_block("World"),
        )

        result = client._make_request_with_retry(
            {"model": "test", "max_tokens": 10, "messages": []}
        )
        assert result == "Hello World"

    def test_json_block_concatenation(self, client, mock_anthropic):
        """JSON blocks should be serialised and concatenated."""
        _, mock_inst = mock_anthropic
        data = {"key": "value"}
        mock_inst.messages.create.return_value = _make_response(
            _make_json_block(data),
        )

        result = client._make_request_with_retry(
            {"model": "test", "max_tokens": 10, "messages": []}
        )
        assert json.loads(result) == data

    def test_retry_on_transient_error(self, client, mock_anthropic):
        """Transient errors should be retried up to max_retries times."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.side_effect = [
            RuntimeError("connection timeout"),
            _make_response(_make_text_block("recovered")),
        ]

        result = client._make_request_with_retry(
            {"model": "test", "max_tokens": 10, "messages": []}
        )
        assert result == "recovered"
        assert mock_inst.messages.create.call_count == 2

    def test_no_retry_on_non_retryable(self, client, mock_anthropic):
        """Non-retryable errors should break out immediately."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.side_effect = RuntimeError("invalid api key")

        with pytest.raises(ClaudeClientError, match="invalid api key"):
            client._make_request_with_retry(
                {"model": "test", "max_tokens": 10, "messages": []}
            )
        assert mock_inst.messages.create.call_count == 1

    def test_all_retries_exhausted(self, client, mock_anthropic):
        """After all retries fail, ClaudeClientError should be raised."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.side_effect = RuntimeError("server error")

        with pytest.raises(ClaudeClientError, match="failed after 3 attempts"):
            client._make_request_with_retry(
                {"model": "test", "max_tokens": 10, "messages": []}
            )
        # 1 initial + 2 retries = 3 total
        assert mock_inst.messages.create.call_count == 3

    def test_empty_response_content_raises(self, client, mock_anthropic):
        """An empty content list should raise ClaudeClientError."""
        _, mock_inst = mock_anthropic
        resp = MagicMock()
        resp.content = []
        mock_inst.messages.create.return_value = resp

        with pytest.raises(ClaudeClientError, match="No content returned"):
            client._make_request_with_retry(
                {"model": "test", "max_tokens": 10, "messages": []}
            )


# ====================================================================
# Structured output parsing tests
# ====================================================================


class TestStructuredOutputParsing:
    """Tests for _maybe_parse_structured_output."""

    def test_json_object_format(self, client, mock_anthropic):
        """json_object format should parse JSON from the response."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block('{"result": 42}')
        )

        result = client.generate_response(
            "compute",
            response_format={"type": "json_object"},
        )
        assert result == {"result": 42}

    def test_json_schema_format(self, client, mock_anthropic):
        """json_schema format should also trigger JSON parsing."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block('{"name": "test"}')
        )

        result = client.generate_response(
            "extract",
            response_format={"type": "json_schema"},
        )
        assert result == {"name": "test"}

    def test_fallback_json_extraction_from_code_block(self, client, mock_anthropic):
        """JSON wrapped in markdown code fences should be extracted."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block('```json\n{"key": "value"}\n```')
        )

        result = client.generate_response(
            "extract",
            response_format={"type": "json_object"},
        )
        assert result == {"key": "value"}

    def test_parse_disabled(self, client, mock_anthropic):
        """When parse_structured_output=False, raw string should be returned."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block('{"raw": true}')
        )

        result = client.generate_response(
            "compute",
            response_format={"type": "json_object"},
            parse_structured_output=False,
        )
        assert isinstance(result, str)

    def test_no_format_returns_string(self, client, mock_anthropic):
        """Without response_format, output should remain a plain string."""
        _, mock_inst = mock_anthropic
        mock_inst.messages.create.return_value = _make_response(
            _make_text_block("just text")
        )

        result = client.generate_response("question")
        assert result == "just text"
        assert isinstance(result, str)


# ====================================================================
# _is_non_retryable_error tests
# ====================================================================


class TestIsNonRetryableError:
    """Tests for error classification."""

    @pytest.mark.parametrize(
        "message",
        [
            "Invalid API Key provided",
            "Unauthorized access",
            "Permission denied for resource",
            "Quota exceeded for account",
            "Billing issue detected",
            "Invalid request body",
            "Authentication failed",
            "Forbidden: you do not have access",
        ],
    )
    def test_non_retryable_patterns(self, client, message):
        """Known non-retryable patterns should return True."""
        assert client._is_non_retryable_error(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "connection timeout",
            "server error 500",
            "rate limit exceeded",
            "network unreachable",
        ],
    )
    def test_retryable_patterns(self, client, message):
        """Transient errors should return False (retryable)."""
        assert client._is_non_retryable_error(RuntimeError(message)) is False


# ====================================================================
# Image encoding helpers
# ====================================================================


class TestImageEncodingHelpers:
    """Tests for standalone image encoding functions."""

    def test_encode_image_to_base64_with_file(self, tmp_path):
        """Valid image file should be encoded to base64."""
        img_path = tmp_path / "photo.png"
        img_path.write_bytes(b"\x89PNG raw data")

        data, media_type = encode_image_to_base64(str(img_path))
        assert media_type == "image/png"
        assert base64.standard_b64decode(data) == b"\x89PNG raw data"

    def test_encode_image_to_base64_jpeg(self, tmp_path):
        """JPEG extension should map to image/jpeg media type."""
        img_path = tmp_path / "photo.jpg"
        img_path.write_bytes(b"\xff\xd8\xff data")

        data, media_type = encode_image_to_base64(img_path)
        assert media_type == "image/jpeg"

    def test_encode_image_to_base64_missing_file(self):
        """Non-existent file should raise ClaudeClientError."""
        with pytest.raises(ClaudeClientError, match="Image file not found"):
            encode_image_to_base64("/nonexistent/path.png")

    def test_encode_image_to_base64_unsupported_format(self, tmp_path):
        """Unsupported extension should raise ClaudeClientError."""
        img_path = tmp_path / "image.bmp"
        img_path.write_bytes(b"BM data")

        with pytest.raises(ClaudeClientError, match="Unsupported image format"):
            encode_image_to_base64(str(img_path))

    def test_encode_image_bytes_to_base64(self):
        """Raw bytes should be base64-encoded correctly."""
        raw = b"hello image bytes"
        result = encode_image_bytes_to_base64(raw)
        assert base64.standard_b64decode(result) == raw

    def test_create_image_content_block_from_path(self, tmp_path):
        """File-path source should produce a well-formed content block."""
        img_path = tmp_path / "test.webp"
        img_path.write_bytes(b"webp content")

        block = create_image_content_block(str(img_path))
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/webp"
        assert block["source"]["type"] == "base64"

    def test_create_image_content_block_from_bytes(self):
        """Bytes source with explicit media_type should produce a content block."""
        block = create_image_content_block(b"raw", media_type="image/png")
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/png"

    def test_create_image_content_block_bytes_no_media_type_raises(self):
        """Bytes without media_type should raise."""
        with pytest.raises(ClaudeClientError, match="media_type is required"):
            create_image_content_block(b"raw")


# ====================================================================
# get_embedding tests
# ====================================================================


class TestGetEmbedding:
    """Tests for embedding delegation to OpenAI client."""

    def test_delegates_to_openai(self, client):
        """get_embedding should create an OpenAIClient and call its get_embedding."""
        fake_embedding = [0.1, 0.2, 0.3]

        mock_openai_instance = MagicMock()
        mock_openai_instance.get_embedding.return_value = fake_embedding
        mock_openai_cls = MagicMock(return_value=mock_openai_instance)

        mock_module = MagicMock()
        mock_module.OpenAIClient = mock_openai_cls
        mock_module.OpenAIClientError = _OpenAIClientErrorStub

        with patch.dict("sys.modules", {"reflexio.server.llm.openai_client": mock_module}):
            result = client.get_embedding("test text", model="text-embedding-3-small")

        assert result == fake_embedding
        mock_openai_instance.get_embedding.assert_called_once_with(
            "test text", "text-embedding-3-small"
        )

    def test_wraps_openai_error(self, client):
        """OpenAI errors should be wrapped in ClaudeClientError."""
        mock_openai_instance = MagicMock()
        mock_openai_instance.get_embedding.side_effect = _OpenAIClientErrorStub("api down")

        mock_module = MagicMock()
        mock_module.OpenAIClient = MagicMock(return_value=mock_openai_instance)
        mock_module.OpenAIClientError = _OpenAIClientErrorStub

        with (
            patch.dict("sys.modules", {"reflexio.server.llm.openai_client": mock_module}),
            pytest.raises(ClaudeClientError, match="OpenAI fallback"),
        ):
            client.get_embedding("test")


# ====================================================================
# Miscellaneous / config helpers
# ====================================================================


class TestConfigHelpers:
    """Tests for update_config, get_config, get_available_models."""

    def test_update_config(self, client):
        """update_config should mutate known fields."""
        client.update_config(temperature=0.2, max_tokens=100)
        assert client.config.temperature == 0.2
        assert client.config.max_tokens == 100

    def test_update_config_ignores_unknown(self, client):
        """Unknown fields should be silently ignored."""
        client.update_config(nonexistent_field=42)
        assert not hasattr(client.config, "nonexistent_field")

    def test_get_config(self, client, claude_config):
        """get_config should return the config object."""
        assert client.get_config() is claude_config

    def test_get_available_models(self, client):
        """Should return a non-empty list of model strings."""
        models = client.get_available_models()
        assert models
        assert all(isinstance(m, str) for m in models)
