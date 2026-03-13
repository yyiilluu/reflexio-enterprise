"""
LLM client package providing unified access to multiple LLM providers.

This package uses LiteLLM as the backend to provide a consistent interface
for OpenAI, Claude, Azure OpenAI, and other LLM providers.
"""

from .litellm_client import (
    LiteLLMClient,
    LiteLLMClientError,
    LiteLLMConfig,
    create_litellm_client,
)

# Legacy imports for backward compatibility
from .openai_client import OpenAIClient, OpenAIClientError, OpenAIConfig

# Make Claude client optional
try:
    from .claude_client import (
        ClaudeClient,
        ClaudeClientError,
        ClaudeConfig,
        create_claude_client,
    )

    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    ClaudeClient = None
    ClaudeConfig = None
    create_claude_client = None
    ClaudeClientError = None

__all__ = [
    # LiteLLM client (recommended)
    "LiteLLMClient",
    "LiteLLMConfig",
    "LiteLLMClientError",
    "create_litellm_client",
    # Legacy individual clients (for advanced use)
    "OpenAIClient",
    "OpenAIConfig",
    "OpenAIClientError",
]

# Add Claude exports if available
if CLAUDE_AVAILABLE:
    __all__.extend(
        [
            "ClaudeClient",
            "ClaudeConfig",
            "create_claude_client",
            "ClaudeClientError",
        ]
    )
