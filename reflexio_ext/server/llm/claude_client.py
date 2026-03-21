import base64
import json
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from anthropic.types import Message
from pydantic import BaseModel
from reflexio.server.services.service_utils import extract_json_from_string

# Supported image MIME types for Claude vision
SUPPORTED_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ClaudeConfig:
    """Configuration for Claude client."""

    api_key: str | None = None
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0


class ClaudeClientError(Exception):
    """Custom exception for Claude client errors."""


def encode_image_to_base64(image_path: str | Path) -> tuple[str, str]:
    """
    Encode an image file to base64 string.

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (base64_encoded_data, media_type).

    Raises:
        ClaudeClientError: If the file doesn't exist or has unsupported format.
    """
    path = Path(image_path)

    if not path.exists():
        raise ClaudeClientError(f"Image file not found: {image_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_TYPES:
        raise ClaudeClientError(
            f"Unsupported image format: {suffix}. "
            f"Supported formats: {list(SUPPORTED_IMAGE_TYPES.keys())}"
        )

    media_type = SUPPORTED_IMAGE_TYPES[suffix]

    with Path(path).open("rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    return image_data, media_type


def encode_image_bytes_to_base64(
    image_bytes: bytes,
    media_type: str = "image/png",  # noqa: ARG001
) -> str:
    """
    Encode image bytes to base64 string.

    Args:
        image_bytes: Raw image bytes.
        media_type: MIME type of the image (default: image/png).

    Returns:
        Base64 encoded string.
    """
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def create_image_content_block(
    image_source: str | Path | bytes,
    media_type: str | None = None,
) -> dict[str, Any]:
    """
    Create a Claude API image content block.

    Args:
        image_source: Either a file path (str/Path) or raw image bytes.
        media_type: MIME type (required if image_source is bytes).

    Returns:
        Image content block dict for Claude API.

    Raises:
        ClaudeClientError: If media_type is missing for bytes input.
    """
    if isinstance(image_source, bytes):
        if not media_type:
            raise ClaudeClientError(
                "media_type is required when providing image as bytes"
            )
        image_data = encode_image_bytes_to_base64(image_source, media_type)
    else:
        image_data, media_type = encode_image_to_base64(image_source)

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": image_data,
        },
    }


class ClaudeClient:
    """
    Production-ready Claude API client with robust error handling and retry logic.
    """

    def __init__(self, config: ClaudeConfig | None = None):
        """
        Initialize the Claude client.

        Args:
            config: Claude configuration. If None, uses default config.
        """
        self.config = config or ClaudeConfig()
        self.logger = logging.getLogger(__name__)

        # Set up API key
        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ClaudeClientError(
                "Claude API key not provided. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key in config."
            )

        # Initialize Claude client
        try:
            self.client = Anthropic(api_key=api_key, timeout=self.config.timeout)
        except Exception as e:
            raise ClaudeClientError(
                f"Failed to initialize Claude client: {str(e)}"
            ) from e

        self.logger.info("Claude client initialized with model: %s", self.config.model)

    def generate_response(
        self,
        prompt: str,
        system_message: str | None = None,
        images: list[str | Path | bytes | dict[str, Any]] | None = None,
        **kwargs,
    ) -> str | dict[str, Any] | BaseModel:
        """
        Generate a response from Claude API.

        Args:
            prompt: The user prompt/message.
            system_message: Optional system message to set context.
            images: Optional list of images to include. Each item can be:
                - str/Path: File path to an image
                - bytes: Raw image bytes (requires media_type in kwargs)
                - dict: Pre-formatted image content block
            **kwargs: Additional parameters to override config defaults.
                - response_format: Structured output definition (dict-based format).
                - parse_structured_output: When True (default), attempts to JSON-decode
                  responses when a structured response format is provided.
                - image_media_type: MIME type for bytes images (default: image/png).

        Returns:
            Generated response content. Returns string for text responses or parsed
            dictionary when structured output parsing is enabled.

        Raises:
            ClaudeClientError: If the API call fails after all retries.
        """
        if not prompt.strip():
            raise ClaudeClientError("Prompt cannot be empty")

        # Build content - either simple string or list with images
        if images:
            content: list[dict[str, Any]] = []
            image_media_type = kwargs.pop("image_media_type", "image/png")

            # Add images first (Claude recommends images before text)
            for img in images:
                if isinstance(img, dict):
                    # Pre-formatted content block
                    content.append(img)
                elif isinstance(img, bytes):
                    content.append(
                        create_image_content_block(img, media_type=image_media_type)
                    )
                else:
                    # File path
                    content.append(create_image_content_block(img))

            # Add text prompt
            content.append({"type": "text", "text": prompt})
            messages = [{"role": "user", "content": content}]
        else:
            # Simple text-only message
            messages = [{"role": "user", "content": prompt}]

        # Merge config with kwargs
        params = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": messages,
        }

        # Claude API doesn't allow both temperature and top_p simultaneously
        # Use top_p only if explicitly set to non-default, otherwise use temperature
        top_p = kwargs.get("top_p", self.config.top_p)
        if top_p != 1.0:
            params["top_p"] = top_p
        else:
            params["temperature"] = kwargs.get("temperature", self.config.temperature)

        # Add system message if provided
        if system_message:
            params["system"] = system_message

        response_format = kwargs.get("response_format")

        content = self._make_request_with_retry(params)  # type: ignore[reportAssignmentType]
        return self._maybe_parse_structured_output(
            content,  # type: ignore[reportArgumentType]
            response_format,
            kwargs.get("parse_structured_output", True),  # type: ignore[reportArgumentType]
        )

    def generate_chat_response(
        self,
        messages: list[dict[str, Any]],
        system_message: str | None = None,
        **kwargs,
    ) -> str | dict[str, Any] | BaseModel:
        """
        Generate a response from a list of chat messages.

        Args:
            messages: List of messages in Claude chat format. Each message should have:
                - role: "system", "user", or "assistant"
                - content: String or list of content blocks (for images).
                  Content blocks can include:
                  - {"type": "text", "text": "..."}
                  - {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}
            system_message: Optional system message to set context.
            **kwargs: Additional parameters to override config defaults.
                - response_format: Structured output definition (dict-based format).
                - parse_structured_output: When True (default), attempts to JSON-decode
                  responses when a structured response format is provided.

        Returns:
            Generated response content. Returns string for text responses or parsed
            dictionary when structured output parsing is enabled.

        Raises:
            ClaudeClientError: If the API call fails after all retries.
        """
        if not messages:
            raise ClaudeClientError("Messages list cannot be empty")

        # Extract system messages and conversation messages separately
        # Claude API requires system messages to be passed via the system parameter
        system_messages = []
        conversation_messages = []

        for msg in messages:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise ClaudeClientError(
                    "Each message must be a dict with 'role' and 'content' keys"
                )
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # System messages must be strings
                if isinstance(content, str):
                    system_messages.append(content)
                else:
                    raise ClaudeClientError("System message content must be a string")
            elif role in ("user", "assistant"):
                # User/assistant messages can have string or list content (for images)
                conversation_messages.append({"role": role, "content": content})
            else:
                raise ClaudeClientError(
                    f"Message role must be 'system', 'user', or 'assistant', got '{role}'"
                )

        if not conversation_messages:
            raise ClaudeClientError(
                "At least one user or assistant message is required"
            )

        # Merge config with kwargs
        params = {
            "model": kwargs.get("model", self.config.model),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": conversation_messages,
        }

        # Claude API doesn't allow both temperature and top_p simultaneously
        # Use top_p only if explicitly set to non-default, otherwise use temperature
        top_p = kwargs.get("top_p", self.config.top_p)
        if top_p != 1.0:
            params["top_p"] = top_p
        else:
            params["temperature"] = kwargs.get("temperature", self.config.temperature)

        # Combine system messages from input with system_message parameter
        all_system_parts = []
        if system_messages:
            all_system_parts.extend(system_messages)
        if system_message:
            all_system_parts.append(system_message)
        if all_system_parts:
            params["system"] = "\n\n".join(all_system_parts)

        response_format = kwargs.get("response_format")

        content = self._make_request_with_retry(params)
        return self._maybe_parse_structured_output(
            content, response_format, kwargs.get("parse_structured_output", True)
        )

    def _make_request_with_retry(self, params: dict[str, Any]) -> str:
        """
        Make Claude API request with retry logic.

        Args:
            params: Parameters for the API call.

        Returns:
            Generated response text.

        Raises:
            ClaudeClientError: If the API call fails after all retries.
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug("Making Claude API request (attempt %s)", attempt + 1)

                response: Message = self.client.messages.create(**params)

                if not response.content:
                    raise ClaudeClientError("No content returned from Claude API")

                # Claude returns content as a list of content blocks
                # We'll concatenate all text blocks
                content_text = ""
                for content_block in response.content:
                    block_text = getattr(content_block, "text", None)
                    block_json = getattr(content_block, "json", None)
                    if block_text:
                        content_text += block_text
                    elif block_json is not None:
                        content_text += json.dumps(block_json)
                    else:
                        # Fallback to string representation if no text/json attributes
                        content_text += str(
                            getattr(content_block, "content", "")
                        ) or str(content_block)

                if not content_text.strip():
                    raise ClaudeClientError("Empty response content from Claude API")

                self.logger.debug("Successfully received response from Claude API")
                return content_text.strip()

            except Exception as e:  # noqa: PERF203
                last_exception = e
                self.logger.warning(
                    "Claude API request failed (attempt %s/%s): %s",
                    attempt + 1,
                    self.config.max_retries + 1,
                    e,
                )

                # Don't retry on certain errors
                if self._is_non_retryable_error(e):
                    break

                # Wait before retrying (except on last attempt)
                if attempt < self.config.max_retries:
                    time.sleep(
                        self.config.retry_delay * (2**attempt)
                    )  # Exponential backoff

        # All retries failed
        error_msg = (
            f"Claude API request failed after {self.config.max_retries + 1} attempts"
        )
        if last_exception:
            error_msg += f": {str(last_exception)}"

        raise ClaudeClientError(error_msg)

    def _maybe_parse_structured_output(
        self,
        content: str | dict[str, Any] | BaseModel,
        response_format: Any,
        parse_structured_output: bool,
    ) -> str | dict[str, Any] | BaseModel:
        """
        Attempt to parse structured output content when requested.

        Args:
            content: Raw content returned from the API.
            response_format: Response format definition used for the request.
            parse_structured_output: Whether to attempt parsing the content.

        Returns:
            Either the original content (str) or a parsed dictionary for structured outputs.
        """
        if not parse_structured_output:
            return content

        if not response_format:
            return content

        # If content is a BaseModel, convert to dict
        if isinstance(content, BaseModel):
            return content.model_dump()

        # If content is already a dict, return it
        if isinstance(content, dict):
            return content

        # If content is a string, try to parse it based on format type
        if isinstance(content, str):
            format_type = self._get_response_format_type(response_format)
            if format_type in {"json_object", "json_schema"}:
                # Use shared utility to extract JSON from markdown code blocks
                # and handle Python-style booleans
                return extract_json_from_string(content)
            # This is string content, return it as is
            return content

        # Default case: return content as-is
        return content

    @staticmethod
    def _get_response_format_type(response_format: Any) -> str | None:
        """
        Extract the response format type from different response format shapes.

        Args:
            response_format: Response format definition.

        Returns:
            The response format type string if available, otherwise None.
        """
        if isinstance(response_format, Mapping):
            format_type = response_format.get("type")
            if isinstance(format_type, str):
                return format_type

        format_type = getattr(response_format, "type", None)
        if isinstance(format_type, str):
            return format_type

        return None

    def _is_non_retryable_error(self, error: Exception) -> bool:
        """
        Check if an error should not be retried.

        Args:
            error: The exception that occurred.

        Returns:
            True if the error should not be retried, False otherwise.
        """
        error_str = str(error).lower()

        # Don't retry on authentication or permission errors
        non_retryable_patterns = [
            "invalid api key",
            "unauthorized",
            "permission denied",
            "quota exceeded",
            "billing",
            "invalid request",
            "authentication",
            "forbidden",
        ]

        return any(pattern in error_str for pattern in non_retryable_patterns)

    def update_config(self, **kwargs) -> None:
        """
        Update client configuration.

        Args:
            **kwargs: Configuration parameters to update.
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.logger.debug("Updated config: %s = %s", key, value)
            else:
                self.logger.warning("Unknown config parameter: %s", key)

    def get_config(self) -> ClaudeConfig:
        """
        Get current configuration.

        Returns:
            Current Claude configuration.
        """
        return self.config

    def get_available_models(self) -> list[str]:
        """
        Get list of available Claude models.

        Returns:
            List of available model names.
        """
        return [
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-haiku-20240307",
        ]

    def get_embedding(
        self, text: str, model: str = "text-embedding-3-small"
    ) -> list[float]:
        """
        Get embedding vector for the given text using OpenAI's Embeddings API.

        Note: Claude/Anthropic does not provide a native embeddings API.
        This method falls back to OpenAI's embedding models for compatibility.

        Args:
            text: The text to get embedding for
            model: The embedding model to use (default: text-embedding-3-small)

        Returns:
            List of floats representing the embedding vector

        Raises:
            ClaudeClientError: If the embedding generation fails
        """
        from .openai_client import OpenAIClient, OpenAIClientError

        try:
            openai_client = OpenAIClient()
            return openai_client.get_embedding(text, model)
        except OpenAIClientError as e:
            raise ClaudeClientError(
                f"Failed to get embedding via OpenAI fallback: {e}"
            ) from e
        except Exception as e:
            raise ClaudeClientError(f"Failed to get embedding: {e}") from e


# Convenience function for quick usage
def create_claude_client(
    api_key: str | None = None,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    **kwargs,
) -> ClaudeClient:
    """
    Create a Claude client with simplified parameters.

    Args:
        api_key: Claude API key. If None, uses ANTHROPIC_API_KEY env var.
        model: Model name to use.
        max_tokens: Maximum tokens to generate.
        temperature: Temperature for response generation.
        **kwargs: Additional configuration parameters.

    Returns:
        Configured Claude client.
    """
    config = ClaudeConfig(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    return ClaudeClient(config)


if __name__ == "__main__":
    """
    Test the Claude client with placeholder parameters.
    Set ANTHROPIC_API_KEY environment variable to run with real API.
    """
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Test 1: Basic client initialization
        print("Testing Claude Client...")
        print("-" * 50)

        # Check if API key is available
        api_key = os.getenv("ANTHROPIC_API_KEY")
        has_valid_key = api_key and (api_key.startswith("sk-ant-") or len(api_key) > 20)

        # Create client with placeholder/test configuration
        config = ClaudeConfig(
            api_key=api_key if has_valid_key else "sk-ant-placeholder-key-for-testing",
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0.7,
            max_retries=2,
            timeout=30,
        )

        client = ClaudeClient(config)
        print(f"Client initialized successfully with model: {client.config.model}")

        # Test 2: Configuration display
        print("Configuration:")
        print(f"   Model: {client.config.model}")
        print(f"   Max Tokens: {client.config.max_tokens}")
        print(f"   Temperature: {client.config.temperature}")
        print(f"   Max Retries: {client.config.max_retries}")
        print(f"   Timeout: {client.config.timeout}s")
        print()

        # Test 3: Available models
        print("Available Models:")
        available_models = client.get_available_models()
        for model in available_models[:20]:  # Show first 20 models
            print(f"   - {model}")
        print(f"   ... and {len(available_models) - 20} more")
        print()

        # Test 4: Simple response generation (only if API key is available)
        if has_valid_key:
            print("API key detected, testing actual API call...")

            test_prompt = (
                "What is the capital of France? Please answer in one sentence."
            )
            response = client.generate_response(test_prompt)
            print(f"Test prompt: {test_prompt}")
            print(f"Response: {response}")
            print()
        else:
            print("No valid ANTHROPIC_API_KEY found in environment variables.")
            print("To test API calls, set your Claude API key:")
            print("   export ANTHROPIC_API_KEY='sk-ant-your-api-key-here'")
            print()
            print("Client initialization and configuration tests passed!")

    except ClaudeClientError as e:
        print(f"Claude Client Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        sys.exit(1)
