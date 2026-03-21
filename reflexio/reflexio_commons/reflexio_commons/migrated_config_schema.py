from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from reflexio_commons.api_schema.validators import (
    NonEmptyStr,
    SafeHttpUrl,
    SanitizedNonEmptyStr,
)

# Embedding vector dimensions. Changing this requires a DB migration and re-embedding,
# so it is intentionally a constant rather than a configurable setting.
EMBEDDING_DIMENSIONS = 512


@dataclass
class SearchOptions:
    """Engine-level search parameters that are pre-computed or not part of the API request."""

    query_embedding: list[float] | None = field(default=None)


class SearchMode(str, Enum):
    """Search mode for hybrid search functionality.

    Controls how search queries are processed:
    - VECTOR: Pure vector similarity search using embeddings
    - FTS: Pure full-text search using PostgreSQL tsvector
    - HYBRID: Combined search using Reciprocal Rank Fusion (RRF)
    """

    VECTOR = "vector"
    FTS = "fts"
    HYBRID = "hybrid"


class StorageConfigTest(IntEnum):
    UNKNOWN = 0
    INCOMPLETE = 1
    FAILED = 2
    SUCCEEDED = 3


class StorageConfigLocal(BaseModel):
    dir_path: NonEmptyStr


class StorageConfigSupabase(BaseModel):
    url: NonEmptyStr
    key: NonEmptyStr
    db_url: NonEmptyStr


StorageConfig = StorageConfigLocal | StorageConfigSupabase | None


class AzureOpenAIConfig(BaseModel):
    """Azure OpenAI specific configuration."""

    api_key: NonEmptyStr
    endpoint: SafeHttpUrl  # e.g., "https://your-resource.openai.azure.com/"
    api_version: str = "2024-02-15-preview"
    deployment_name: str | None = None  # Optional, can be specified per request


class OpenAIConfig(BaseModel):
    """OpenAI API configuration (direct or Azure)."""

    api_key: str | None = None  # Direct OpenAI API key
    azure_config: AzureOpenAIConfig | None = None  # Azure OpenAI configuration

    @model_validator(mode="after")
    def check_at_least_one_auth(self) -> Self:
        """Validate that at least one of api_key or azure_config is provided."""
        if not self.api_key and not self.azure_config:
            raise ValueError(
                "At least one of 'api_key' or 'azure_config' must be provided"
            )
        return self


class AnthropicConfig(BaseModel):
    """Anthropic API configuration."""

    api_key: NonEmptyStr


class OpenRouterConfig(BaseModel):
    """OpenRouter API configuration."""

    api_key: NonEmptyStr


class GeminiConfig(BaseModel):
    """Google Gemini API configuration."""

    api_key: NonEmptyStr


class MiniMaxConfig(BaseModel):
    """MiniMax API configuration."""

    api_key: NonEmptyStr


class CustomEndpointConfig(BaseModel):
    """Custom OpenAI-compatible endpoint configuration.

    Args:
        model (str): Model name to use (e.g., 'openai/mistral', 'mistral'). Passed as-is to LiteLLM.
        api_key (str): API key for the custom endpoint.
        api_base (SafeHttpUrl): Base URL of the custom endpoint (e.g., 'http://localhost:8000/v1').
            Validated against SSRF: always blocks cloud metadata endpoints;
            blocks private IPs when REFLEXIO_BLOCK_PRIVATE_URLS=true.
    """

    model: NonEmptyStr
    api_key: NonEmptyStr
    api_base: SafeHttpUrl


class APIKeyConfig(BaseModel):
    """
    API key configuration for LLM providers.

    Supports OpenAI (direct and Azure), Anthropic, OpenRouter, Google Gemini, MiniMax, and custom
    OpenAI-compatible endpoints. When custom_endpoint is configured with non-empty fields,
    it takes priority over all other providers for LLM completion calls (but not embeddings).
    """

    custom_endpoint: CustomEndpointConfig | None = None
    openai: OpenAIConfig | None = None
    anthropic: AnthropicConfig | None = None
    openrouter: OpenRouterConfig | None = None
    gemini: GeminiConfig | None = None
    minimax: MiniMaxConfig | None = None


class ProfileExtractorConfig(BaseModel):
    extractor_name: NonEmptyStr
    profile_content_definition_prompt: SanitizedNonEmptyStr
    context_prompt: str | None = None
    metadata_definition_prompt: str | None = None
    should_extract_profile_prompt_override: str | None = None
    request_sources_enabled: list[str] | None = (
        None  # default enabled for all sources, if set, only extract profiles from the enabled request sources
    )
    manual_trigger: bool = False  # require manual triggering (rerun) to run extraction and skip auto extraction if set to True
    extraction_window_size_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_size for this extractor
    extraction_window_stride_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_stride for this extractor


class FeedbackAggregatorConfig(BaseModel):
    min_feedback_threshold: int = Field(default=2, ge=1)
    refresh_count: int = Field(default=2, ge=1)


class SkillGeneratorConfig(BaseModel):
    enabled: bool = False
    min_feedback_per_cluster: int = Field(default=5, ge=1)
    cooldown_hours: int = Field(default=24, ge=0)
    auto_generate_on_aggregation: bool = False
    max_interactions_per_skill: int = Field(default=20, ge=1)


class AgentFeedbackConfig(BaseModel):
    feedback_name: NonEmptyStr
    # define what success looks like
    feedback_definition_prompt: SanitizedNonEmptyStr
    metadata_definition_prompt: str | None = None
    feedback_aggregator_config: FeedbackAggregatorConfig | None = None
    skill_generator_config: SkillGeneratorConfig | None = None
    request_sources_enabled: list[str] | None = (
        None  # default enabled for all sources, if set, only extract feedbacks from the enabled request sources
    )
    extraction_window_size_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_size for this extractor
    extraction_window_stride_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_stride for this extractor


class ToolUseConfig(BaseModel):
    tool_name: NonEmptyStr
    tool_description: NonEmptyStr


# define what success looks like for agent
class AgentSuccessConfig(BaseModel):
    evaluation_name: NonEmptyStr
    success_definition_prompt: SanitizedNonEmptyStr
    metadata_definition_prompt: str | None = None
    sampling_rate: float = Field(
        default=1.0, ge=0.0, le=1.0
    )  # fraction of batch of interactions to be sampled for success evaluation
    extraction_window_size_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_size for this extractor
    extraction_window_stride_override: int | None = Field(
        default=None, gt=0
    )  # override global extraction_window_stride for this extractor


class LLMConfig(BaseModel):
    """
    LLM model configuration overrides.

    These settings override the default model names from llm_model_setting.json site variable.
    If a field is None, the default from site variable is used.
    """

    should_run_model_name: str | None = None  # Model for "should run extraction" checks
    generation_model_name: str | None = (
        None  # Model for generation and evaluation tasks
    )
    embedding_model_name: str | None = None  # Model for embedding generation


class Config(BaseModel):
    # define where user configuration is stored at
    storage_config: StorageConfig
    storage_config_test: StorageConfigTest | None = StorageConfigTest.UNKNOWN
    # define agent working environment, tool can use and action space
    agent_context_prompt: str | None = None
    # tools agent can use (shared across success evaluation and feedback extraction)
    tool_can_use: list[ToolUseConfig] | None = None
    # user level memory
    profile_extractor_configs: list[ProfileExtractorConfig] | None = None
    # agent level feedback
    agent_feedback_configs: list[AgentFeedbackConfig] | None = None
    # agent level success
    agent_success_configs: list[AgentSuccessConfig] | None = None
    # sliding window parameters for extraction
    extraction_window_size: int | None = Field(default=None, gt=0)
    extraction_window_stride: int | None = Field(default=None, gt=0)
    # API key configuration for LLM providers
    api_key_config: APIKeyConfig | None = None
    # LLM model configuration overrides
    llm_config: LLMConfig | None = None

    @model_validator(mode="after")
    def check_stride_le_window(self) -> Self:
        """Validate that extraction_window_stride <= extraction_window_size when both are set."""
        if (
            self.extraction_window_size
            and self.extraction_window_stride
            and self.extraction_window_stride > self.extraction_window_size
        ):
            raise ValueError(
                "extraction_window_stride must be <= extraction_window_size"
            )
        return self
