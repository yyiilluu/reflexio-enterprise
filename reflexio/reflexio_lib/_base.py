from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from reflexio.server.services.query_rewriter import QueryRewriter


from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.configurator.configurator import SimpleConfigurator
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)

# Error message for when storage is not configured
STORAGE_NOT_CONFIGURED_MSG = (
    "Storage not configured. Please configure storage in settings first."
)

_T = TypeVar("_T")


def _require_storage(
    response_type: type[_T], *, msg_field: str = "message"
) -> Callable[..., Callable[..., _T]]:
    """Decorator that guards a Reflexio method with storage-configured check and error handling.

    Args:
        response_type: The Pydantic response model to return on failure
        msg_field: Name of the message field on the response ('message' or 'msg')
    """

    def decorator(method: Callable[..., _T]) -> Callable[..., _T]:
        @functools.wraps(method)
        def wrapper(self: Reflexio, *args: Any, **kwargs: Any) -> _T:
            if not self._is_storage_configured():
                return response_type(
                    success=False, **{msg_field: STORAGE_NOT_CONFIGURED_MSG}
                )  # type: ignore[call-arg]
            try:
                return method(self, *args, **kwargs)
            except Exception as e:
                return response_type(success=False, **{msg_field: str(e)})  # type: ignore[call-arg]

        return wrapper

    return decorator  # type: ignore[return-value]


class ReflexioBase:
    def __init__(
        self,
        org_id: str,
        storage_base_dir: str | None = None,
        configurator: SimpleConfigurator | None = None,
    ) -> None:
        """Initialize Reflexio with organization ID and storage directory.

        Args:
            org_id (str): Organization ID
            storage_base_dir (str, optional): Base directory for storing data
        """
        self.org_id = org_id
        self.storage_base_dir = storage_base_dir
        self.request_context = RequestContext(
            org_id=org_id, storage_base_dir=storage_base_dir, configurator=configurator
        )

        # Create single LLM client for all services
        model_setting = SiteVarManager().get_site_var("llm_model_setting")

        # Get API key config and LLM config from configuration if available
        config = self.request_context.configurator.get_config()
        api_key_config = config.api_key_config if config else None
        config_llm_config = config.llm_config if config else None

        # Use LLM config override if available, otherwise fallback to site var
        generation_model_name = (
            config_llm_config.generation_model_name
            if config_llm_config and config_llm_config.generation_model_name
            else (
                model_setting.get("default_generation_model_name", "gpt-5-mini")
                if isinstance(model_setting, dict)
                else "gpt-5-mini"
            )
        )

        llm_config = LiteLLMConfig(
            model=generation_model_name,
            api_key_config=api_key_config,
        )
        self.llm_client = LiteLLMClient(llm_config)

    def _is_storage_configured(self) -> bool:
        """Check if storage is configured and available.

        Returns:
            bool: True if storage is configured, False otherwise
        """
        return self.request_context.is_storage_configured()

    def _get_storage(self) -> BaseStorage:
        """Return storage, raising if not configured."""
        storage = self.request_context.storage
        if storage is None:
            raise RuntimeError(STORAGE_NOT_CONFIGURED_MSG)
        return storage

    def _get_query_rewriter(self) -> QueryRewriter:
        """Lazily create and cache a QueryRewriter instance.

        Returns:
            QueryRewriter: Cached rewriter instance
        """
        if not hasattr(self, "_query_rewriter"):
            from reflexio.server.services.query_rewriter import QueryRewriter

            config = self.request_context.configurator.get_config()
            api_key_config = config.api_key_config if config else None
            self._query_rewriter = QueryRewriter(
                api_key_config=api_key_config,
                prompt_manager=self.request_context.prompt_manager,
            )
        return self._query_rewriter

    def _rewrite_query(self, query: str | None, enabled: bool = False) -> str | None:
        """Rewrite a search query using the query rewriter if enabled.

        Returns the rewritten FTS query, or None if rewriting is disabled,
        the query is empty, or rewriting fails.

        Args:
            query (str, optional): The original search query
            enabled (bool): Whether query rewriting is enabled for this request

        Returns:
            str or None: Rewritten FTS query, or None to use original query
        """
        if not query or not enabled:
            return None

        rewriter = self._get_query_rewriter()
        result = rewriter.rewrite(query, enabled=True)
        # Only return if different from original
        if result.fts_query != query:
            return result.fts_query
        return None


if TYPE_CHECKING:
    from reflexio.reflexio_lib.reflexio_lib import Reflexio
