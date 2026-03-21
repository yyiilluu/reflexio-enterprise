import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel
from reflexio.server.llm.llm_utils import is_pydantic_model


@dataclass
class OpenAIConfig:
    """Configuration for OpenAI client.

    Supports both OpenAI and Azure OpenAI. The provider is automatically detected
    based on which API key is provided:
    - If azure_api_key is set (or AZURE_OPENAI_API_KEY env var), uses Azure OpenAI
    - Otherwise, uses standard OpenAI
    """

    # Common settings
    api_key: str | None = None  # OpenAI API key
    model: str = "gpt-5-mini"
    temperature: float = 0.7
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 60
    max_retries: int = 1
    retry_delay: float = 1.0

    # Azure OpenAI specific settings
    azure_api_key: str | None = None
    azure_endpoint: str | None = None
    azure_api_version: str = "2024-08-01-preview"
    azure_deployment: str | None = None  # If None, uses model name as deployment


class OpenAIClientError(Exception):
    """Custom exception for OpenAI client errors."""


class OpenAIClient:
    """
    Production-ready OpenAI API client with robust error handling and retry logic.
    Supports both OpenAI and Azure OpenAI providers.
    """

    def __init__(self, config: OpenAIConfig | None = None):
        """
        Initialize the OpenAI client.

        The provider (OpenAI or Azure OpenAI) is automatically detected based on
        which API key is available:
        - If AZURE_OPENAI_API_KEY env var is set (or azure_api_key in config), uses Azure OpenAI
        - Otherwise, uses standard OpenAI with OPENAI_API_KEY

        Args:
            config: OpenAI configuration. If None, uses default config.
        """
        self.config = config or OpenAIConfig()
        self.logger = logging.getLogger(__name__)

        # Check for Azure OpenAI first
        azure_api_key = self.config.azure_api_key or os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = self.config.azure_endpoint or os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        )

        if azure_api_key:
            print("Azure OpenAI API key found")
            # Use Azure OpenAI
            if not azure_endpoint:
                raise OpenAIClientError(
                    "Azure OpenAI endpoint not provided. Set AZURE_OPENAI_ENDPOINT environment variable "
                    "or pass azure_endpoint in config."
                )

            azure_api_version = self.config.azure_api_version or os.getenv(
                "AZURE_OPENAI_API_VERSION", "2024-08-01-preview"
            )

            try:
                self.client = AzureOpenAI(
                    api_key=azure_api_key,
                    api_version=azure_api_version,
                    azure_endpoint=azure_endpoint,
                    timeout=self.config.timeout,
                )
                self.is_azure = True
                self.azure_deployment = self.config.azure_deployment or os.getenv(
                    "AZURE_OPENAI_DEPLOYMENT"
                )
                self.logger.info(
                    "Azure OpenAI client initialized with endpoint: %s, api_version: %s",
                    azure_endpoint,
                    azure_api_version,
                )
            except Exception as e:
                raise OpenAIClientError(
                    f"Failed to initialize Azure OpenAI client: {str(e)}"
                ) from e
        else:
            # Use standard OpenAI
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise OpenAIClientError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY "
                    "environment variable, or pass api_key/azure_api_key in config."
                )

            try:
                self.client = OpenAI(api_key=api_key, timeout=self.config.timeout)
                self.is_azure = False
                self.azure_deployment = None
                self.logger.info(
                    "OpenAI client initialized with model: %s",
                    self.config.model,
                )
            except Exception as e:
                raise OpenAIClientError(
                    f"Failed to initialize OpenAI client: {str(e)}"
                ) from e

    def _get_model_for_request(self, model: str | None = None) -> str:
        """
        Get the model/deployment name to use for API requests.

        For Azure OpenAI, returns the deployment name.
        For standard OpenAI, returns the model name.

        Args:
            model: Optional model name override.

        Returns:
            The model or deployment name to use in API calls.
        """
        if self.is_azure:
            # For Azure, prefer explicit deployment, then fall back to model name
            return self.azure_deployment or model or self.config.model
        return model or self.config.model

    def generate_response(
        self, prompt: str, system_message: str | None = None, **kwargs
    ) -> str | BaseModel:
        """
        Generate a response from OpenAI API.

        Args:
            prompt: The user prompt/message.
            system_message: Optional system message to set context.
            **kwargs: Additional parameters to override config defaults.
                - response_format: A Pydantic BaseModel class for structured output.
                  When provided, the response will be parsed into an instance of this model.

        Returns:
            Generated response content. For text generations returns a string.
            When response_format is provided, returns a Pydantic model instance.

        Raises:
            OpenAIClientError: If the API call fails after all retries, or if
                response_format is not a Pydantic BaseModel class.
        """
        if not prompt.strip():
            raise OpenAIClientError("Prompt cannot be empty")

        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        # Merge config with kwargs
        requested_model = kwargs.get("model", self.config.model)
        model = self._get_model_for_request(requested_model)
        params = {"model": model, "messages": messages}

        # Some models (like gpt-5, gpt-5-mini) only support temperature=1
        # Only add temperature if it equals 1.0 for gpt-5 models
        temperature = kwargs.get("temperature", self.config.temperature)
        if requested_model.startswith("gpt-5"):
            # gpt-5 models only support temperature=1
            if temperature == 1.0:
                params["temperature"] = 1.0
        else:
            # Other models support custom temperature
            params["temperature"] = temperature

        # Add other parameters
        params["top_p"] = kwargs.get("top_p", self.config.top_p)
        params["frequency_penalty"] = kwargs.get(
            "frequency_penalty", self.config.frequency_penalty
        )
        params["presence_penalty"] = kwargs.get(
            "presence_penalty", self.config.presence_penalty
        )

        response_format = kwargs.get("response_format")
        if response_format:
            if not is_pydantic_model(response_format):
                raise OpenAIClientError(
                    "response_format must be a Pydantic BaseModel class"
                )
            params["response_format"] = response_format

        # Add max_completion_tokens or max_tokens if specified (prefer max_completion_tokens for newer models)
        max_completion_tokens = kwargs.get(
            "max_completion_tokens", self.config.max_completion_tokens
        )
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

        if max_completion_tokens is not None:
            params["max_completion_tokens"] = max_completion_tokens
        elif max_tokens is not None:
            params["max_completion_tokens"] = max_tokens

        return self._make_request_with_retry(params, response_format)

    def generate_chat_response(
        self, messages: list[dict[str, str]], **kwargs
    ) -> str | BaseModel:
        """
        Generate a response from a list of chat messages.

        Args:
            messages: List of messages in OpenAI chat format.
            **kwargs: Additional parameters to override config defaults.
                - response_format: A Pydantic BaseModel class for structured output.
                  When provided, the response will be parsed into an instance of this model.

        Returns:
            Generated response content. For text generations returns a string.
            When response_format is provided, returns a Pydantic model instance.

        Raises:
            OpenAIClientError: If the API call fails after all retries, or if
                response_format is not a Pydantic BaseModel class.
        """
        if not messages:
            raise OpenAIClientError("Messages list cannot be empty")

        # Validate message format
        for msg in messages:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise OpenAIClientError(
                    "Each message must be a dict with 'role' and 'content' keys"
                )

        # Merge config with kwargs
        requested_model = kwargs.get("model", self.config.model)
        model = self._get_model_for_request(requested_model)
        params = {"model": model, "messages": messages}

        # Some models (like gpt-5, gpt-5-mini) only support temperature=1
        # Only add temperature if it equals 1.0 for gpt-5 models
        temperature = kwargs.get("temperature", self.config.temperature)
        if requested_model.startswith("gpt-5"):
            # gpt-5 models only support temperature=1
            if temperature == 1.0:
                params["temperature"] = 1.0
        else:
            # Other models support custom temperature
            params["temperature"] = temperature

        # Add other parameters
        params["top_p"] = kwargs.get("top_p", self.config.top_p)
        params["frequency_penalty"] = kwargs.get(
            "frequency_penalty", self.config.frequency_penalty
        )
        params["presence_penalty"] = kwargs.get(
            "presence_penalty", self.config.presence_penalty
        )

        response_format = kwargs.get("response_format")
        if response_format:
            if not is_pydantic_model(response_format):
                raise OpenAIClientError(
                    "response_format must be a Pydantic BaseModel class"
                )
            params["response_format"] = response_format

        # Add max_completion_tokens or max_tokens if specified (prefer max_completion_tokens for newer models)
        max_completion_tokens = kwargs.get(
            "max_completion_tokens", self.config.max_completion_tokens
        )
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)

        if max_completion_tokens is not None:
            params["max_completion_tokens"] = max_completion_tokens
        elif max_tokens is not None:
            params["max_completion_tokens"] = max_tokens

        return self._make_request_with_retry(params, response_format)

    def _make_request_with_retry(
        self, params: dict[str, Any], response_format: Any = None
    ) -> str | BaseModel:
        """
        Make OpenAI API request with retry logic.

        Args:
            params: Parameters for the API call.
            response_format: The response format (can be Pydantic model or dict).

        Returns:
            Generated response text or parsed Pydantic object.

        Raises:
            OpenAIClientError: If the API call fails after all retries.
        """
        # Check if we should use the parse API (for Pydantic models)
        use_parse_api = is_pydantic_model(response_format)

        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug("Making OpenAI API request (attempt %s)", attempt + 1)

                if use_parse_api:
                    # Use parse API for Pydantic models
                    response = self.client.chat.completions.parse(**params)

                    if not response.choices:
                        raise OpenAIClientError("No choices returned from OpenAI API")

                    # Check for refusal
                    if response.choices[0].message.refusal:
                        raise OpenAIClientError(
                            f"Model refused to respond: {response.choices[0].message.refusal}"
                        )

                    parsed = response.choices[0].message.parsed
                    if parsed is None:
                        raise OpenAIClientError("No parsed content from OpenAI API")

                    self.logger.debug(
                        "Successfully received parsed response from OpenAI API"
                    )
                    return parsed
                # Use create API for dict-based formats
                response = self.client.chat.completions.create(**params)

                if not response.choices:
                    raise OpenAIClientError("No choices returned from OpenAI API")

                content = response.choices[0].message.content
                if content is None:
                    raise OpenAIClientError("Empty response content from OpenAI API")

                self.logger.debug("Successfully received response from OpenAI API")
                return content.strip()

            except Exception as e:  # noqa: PERF203
                last_exception = e
                self.logger.warning(
                    "OpenAI API request failed (attempt %s/%s): %s",
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
            f"OpenAI API request failed after {self.config.max_retries + 1} attempts"
        )
        if last_exception:
            error_msg += f": {str(last_exception)}"

        raise OpenAIClientError(error_msg)

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

    def get_config(self) -> OpenAIConfig:
        """
        Get current configuration.

        Returns:
            Current OpenAI configuration.
        """
        return self.config

    def get_embedding(
        self, text: str, model: str = "text-embedding-3-small"
    ) -> list[float]:
        """
        Get embedding vector for the given text using OpenAI's Embeddings API.

        Args:
            text: The text to get embedding for
            model: The embedding model to use (default: text-embedding-3-small)

        Returns:
            List of floats representing the embedding vector

        Raises:
            OpenAIClientError: If the API call fails after all retries
        """
        if not text.strip():
            raise OpenAIClientError("Text cannot be empty")

        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug("Getting embedding (attempt %s)", attempt + 1)

                response = self.client.embeddings.create(model=model, input=text)

                if not response.data:
                    raise OpenAIClientError(
                        "No embedding data returned from OpenAI API"
                    )

                embedding = response.data[0].embedding
                self.logger.debug("Successfully received embedding from OpenAI API")
                return embedding

            except Exception as e:  # noqa: PERF203
                last_exception = e
                self.logger.warning(
                    "OpenAI embedding request failed (attempt %s/%s): %s",
                    attempt + 1,
                    self.config.max_retries + 1,
                    e,
                )

                # Don't retry on certain errors
                if self._is_non_retryable_error(e):
                    break

                # Wait before retrying (except on last attempt)
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay * (2**attempt))

        # All retries failed
        error_msg = f"OpenAI embedding request failed after {self.config.max_retries + 1} attempts"
        if last_exception:
            error_msg += f": {str(last_exception)}"
        raise OpenAIClientError(error_msg)


# Convenience function for quick usage
def create_openai_client(
    api_key: str | None = None,
    model: str = "gpt-4",
    temperature: float = 0.7,
    **kwargs,
) -> OpenAIClient:
    """
    Create an OpenAI client with simplified parameters.

    Args:
        api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
        model: Model name to use.
        temperature: Temperature for response generation.
        **kwargs: Additional configuration parameters.

    Returns:
        Configured OpenAI client.
    """
    config = OpenAIConfig(
        api_key=api_key, model=model, temperature=temperature, **kwargs
    )
    return OpenAIClient(config)


if __name__ == "__main__":
    """
    Test the OpenAI client with placeholder parameters.
    Set OPENAI_API_KEY environment variable to run with real API.
    """
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Test 1: Basic client initialization
        print("🚀 Testing OpenAI Client...")
        print("-" * 50)

        # Check if API key is available
        api_key = os.getenv("OPENAI_API_KEY")
        has_valid_key = api_key and api_key.startswith("sk-")

        # Create client with placeholder/test configuration
        config = OpenAIConfig(
            api_key=api_key if has_valid_key else "sk-placeholder-key-for-testing",
            model="gpt-3.5-turbo",  # Using cheaper model for testing
            temperature=0.7,
            max_tokens=100,
            max_retries=2,
            timeout=30,
        )

        client = OpenAIClient(config)
        print(f"✅ Client initialized successfully with model: {client.config.model}")

        print("📋 Configuration:")
        print(f"   Model: {client.config.model}")
        print(f"   Temperature: {client.config.temperature}")
        print(f"   Max Tokens: {client.config.max_tokens}")
        print(f"   Max Retries: {client.config.max_retries}")
        print(f"   Timeout: {client.config.timeout}s")
        print()

        if has_valid_key:
            print("🔑 API key detected, testing actual API call...")

            test_prompt = (
                "What is the capital of France? Please answer in one sentence."
            )
            response = client.generate_response(test_prompt)
            print(f"📝 Test prompt: {test_prompt}")
            print(f"🤖 Response: {response}")
            print()
        else:
            print("⚠️  No valid OPENAI_API_KEY found in environment variables.")
            print("💡 To test API calls, set your OpenAI API key:")
            print("   export OPENAI_API_KEY='sk-your-api-key-here'")
            print()
            print("✅ Client initialization and configuration tests passed!")

        print("🔧 Testing convenience function...")
        quick_client = create_openai_client(
            api_key="sk-placeholder-key-for-testing" if not has_valid_key else None,
            model="gpt-3.5-turbo",
            temperature=0.5,
        )
        print(f"✅ Quick client created with model: {quick_client.config.model}")

        print("\n🎉 All tests completed successfully!")

    except OpenAIClientError as e:
        print(f"❌ OpenAI Client Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        sys.exit(1)
