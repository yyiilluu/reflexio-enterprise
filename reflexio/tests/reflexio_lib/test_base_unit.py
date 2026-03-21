"""Unit tests for ReflexioBase and _require_storage decorator.

Tests initialization, storage property, _rewrite_query,
and the _require_storage decorator behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_base(*, storage_configured: bool = True) -> ReflexioBase:
    """Create a ReflexioBase instance with mocked internals, bypassing __init__."""
    base = object.__new__(ReflexioBase)
    mock_storage = MagicMock()

    mock_request_context = MagicMock()
    mock_request_context.org_id = "test_org"
    mock_request_context.storage = mock_storage if storage_configured else None
    mock_request_context.is_storage_configured.return_value = storage_configured

    base.request_context = mock_request_context
    base.llm_client = MagicMock()
    return base


# ---------------------------------------------------------------------------
# _is_storage_configured
# ---------------------------------------------------------------------------


class TestIsStorageConfigured:
    def test_returns_true_when_configured(self):
        """Returns True when storage is configured."""
        base = _make_base(storage_configured=True)
        assert base._is_storage_configured() is True

    def test_returns_false_when_not_configured(self):
        """Returns False when storage is not configured."""
        base = _make_base(storage_configured=False)
        assert base._is_storage_configured() is False


# ---------------------------------------------------------------------------
# _get_storage
# ---------------------------------------------------------------------------


class TestGetStorage:
    def test_returns_storage(self):
        """Returns the storage object when configured."""
        base = _make_base(storage_configured=True)
        storage = base._get_storage()
        assert storage is not None

    def test_raises_when_not_configured(self):
        """Raises RuntimeError when storage is None."""
        base = _make_base(storage_configured=False)
        try:
            base._get_storage()
            msg = "Expected RuntimeError"
            raise AssertionError(msg)
        except RuntimeError as e:
            assert STORAGE_NOT_CONFIGURED_MSG in str(e)


# ---------------------------------------------------------------------------
# _rewrite_query
# ---------------------------------------------------------------------------


class TestRewriteQuery:
    def test_returns_none_when_disabled(self):
        """Returns None when rewriting is disabled."""
        base = _make_base()
        result = base._rewrite_query("some query", enabled=False)
        assert result is None

    def test_returns_none_when_query_empty(self):
        """Returns None when query is empty or None."""
        base = _make_base()
        assert base._rewrite_query("", enabled=True) is None
        assert base._rewrite_query(None, enabled=True) is None

    def test_returns_rewritten_query(self):
        """Returns rewritten query when different from original."""
        base = _make_base()
        mock_rewriter = MagicMock()
        mock_result = MagicMock()
        mock_result.fts_query = "rewritten query"
        mock_rewriter.rewrite.return_value = mock_result
        base._query_rewriter = mock_rewriter

        result = base._rewrite_query("original query", enabled=True)

        assert result == "rewritten query"
        mock_rewriter.rewrite.assert_called_once_with("original query", enabled=True)

    def test_returns_none_when_same_as_original(self):
        """Returns None when rewritten query is the same as original."""
        base = _make_base()
        mock_rewriter = MagicMock()
        mock_result = MagicMock()
        mock_result.fts_query = "same query"
        mock_rewriter.rewrite.return_value = mock_result
        base._query_rewriter = mock_rewriter

        result = base._rewrite_query("same query", enabled=True)

        assert result is None


# ---------------------------------------------------------------------------
# _get_query_rewriter (lazy creation)
# ---------------------------------------------------------------------------


class TestGetQueryRewriter:
    @patch("reflexio.server.services.query_rewriter.QueryRewriter")
    def test_creates_rewriter_lazily(self, mock_rewriter_cls):
        """Creates QueryRewriter on first call."""
        base = _make_base()
        mock_config = MagicMock()
        mock_config.api_key_config = MagicMock()
        base.request_context.configurator.get_config.return_value = mock_config

        rewriter = base._get_query_rewriter()

        assert rewriter is not None
        mock_rewriter_cls.assert_called_once()

    @patch("reflexio.server.services.query_rewriter.QueryRewriter")
    def test_caches_rewriter(self, mock_rewriter_cls):
        """Caches QueryRewriter on subsequent calls."""
        base = _make_base()
        mock_config = MagicMock()
        mock_config.api_key_config = MagicMock()
        base.request_context.configurator.get_config.return_value = mock_config

        rewriter1 = base._get_query_rewriter()
        rewriter2 = base._get_query_rewriter()

        assert rewriter1 is rewriter2
        # Only called once due to caching
        mock_rewriter_cls.assert_called_once()

    @patch("reflexio.server.services.query_rewriter.QueryRewriter")
    def test_handles_no_config(self, mock_rewriter_cls):
        """Handles None config gracefully for api_key_config."""
        base = _make_base()
        base.request_context.configurator.get_config.return_value = None

        rewriter = base._get_query_rewriter()

        assert rewriter is not None
        call_kwargs = mock_rewriter_cls.call_args[1]
        assert call_kwargs["api_key_config"] is None


# ---------------------------------------------------------------------------
# _require_storage decorator
# ---------------------------------------------------------------------------


class _TestResponse(BaseModel):
    success: bool
    message: str = ""


class _TestMsgResponse(BaseModel):
    success: bool
    msg: str = ""


class TestRequireStorageDecorator:
    def test_returns_failure_when_storage_not_configured(self):
        """Decorated method returns failure when storage not configured."""

        class FakeMixin(ReflexioBase):
            @_require_storage(_TestResponse)
            def do_something(self) -> _TestResponse:
                return _TestResponse(success=True)

        mixin = object.__new__(FakeMixin)
        mock_ctx = MagicMock()
        mock_ctx.is_storage_configured.return_value = False
        mock_ctx.storage = None
        mixin.request_context = mock_ctx

        result = mixin.do_something()

        assert result.success is False
        assert STORAGE_NOT_CONFIGURED_MSG in result.message

    def test_returns_success_when_storage_configured(self):
        """Decorated method runs normally when storage is configured."""

        class FakeMixin(ReflexioBase):
            @_require_storage(_TestResponse)
            def do_something(self) -> _TestResponse:
                return _TestResponse(success=True, message="ok")

        mixin = object.__new__(FakeMixin)
        mock_ctx = MagicMock()
        mock_ctx.is_storage_configured.return_value = True
        mock_ctx.storage = MagicMock()
        mixin.request_context = mock_ctx

        result = mixin.do_something()

        assert result.success is True
        assert result.message == "ok"

    def test_catches_exception(self):
        """Decorated method catches exceptions and returns failure."""

        class FakeMixin(ReflexioBase):
            @_require_storage(_TestResponse)
            def do_something(self) -> _TestResponse:
                raise RuntimeError("boom")

        mixin = object.__new__(FakeMixin)
        mock_ctx = MagicMock()
        mock_ctx.is_storage_configured.return_value = True
        mock_ctx.storage = MagicMock()
        mixin.request_context = mock_ctx

        result = mixin.do_something()

        assert result.success is False
        assert "boom" in result.message

    def test_custom_msg_field(self):
        """Decorator uses custom msg_field for the response."""

        class FakeMixin(ReflexioBase):
            @_require_storage(_TestMsgResponse, msg_field="msg")
            def do_something(self) -> _TestMsgResponse:
                return _TestMsgResponse(success=True)

        mixin = object.__new__(FakeMixin)
        mock_ctx = MagicMock()
        mock_ctx.is_storage_configured.return_value = False
        mock_ctx.storage = None
        mixin.request_context = mock_ctx

        result = mixin.do_something()

        assert result.success is False
        assert STORAGE_NOT_CONFIGURED_MSG in result.msg


# ---------------------------------------------------------------------------
# __init__ (integration-style with patches)
# ---------------------------------------------------------------------------


class TestReflexioBaseInit:
    @patch("reflexio.reflexio_lib._base.SiteVarManager")
    @patch("reflexio.reflexio_lib._base.LiteLLMClient")
    @patch("reflexio.reflexio_lib._base.RequestContext")
    def test_init_basic(self, mock_ctx_cls, mock_llm_cls, mock_svm_cls):
        """Basic initialization with org_id and storage_base_dir."""
        mock_ctx = MagicMock()
        mock_config = MagicMock()
        mock_config.api_key_config = None
        mock_config.llm_config = None
        mock_ctx.configurator.get_config.return_value = mock_config
        mock_ctx_cls.return_value = mock_ctx

        mock_svm = MagicMock()
        mock_svm.get_site_var.return_value = {
            "default_generation_model_name": "gpt-5-mini"
        }
        mock_svm_cls.return_value = mock_svm

        base = ReflexioBase(org_id="org1", storage_base_dir="/var/data/test")

        assert base.org_id == "org1"
        assert base.storage_base_dir == "/var/data/test"
        mock_ctx_cls.assert_called_once_with(
            org_id="org1", storage_base_dir="/var/data/test", configurator=None
        )
        mock_llm_cls.assert_called_once()

    @patch("reflexio.reflexio_lib._base.SiteVarManager")
    @patch("reflexio.reflexio_lib._base.LiteLLMClient")
    @patch("reflexio.reflexio_lib._base.RequestContext")
    def test_init_with_llm_config_override(
        self, mock_ctx_cls, mock_llm_cls, mock_svm_cls
    ):
        """Initialization uses LLM config override when available."""
        mock_ctx = MagicMock()
        mock_config = MagicMock()
        mock_config.api_key_config = MagicMock()
        mock_llm_config = MagicMock()
        mock_llm_config.generation_model_name = "custom-model"
        mock_config.llm_config = mock_llm_config
        mock_ctx.configurator.get_config.return_value = mock_config
        mock_ctx_cls.return_value = mock_ctx

        mock_svm = MagicMock()
        mock_svm.get_site_var.return_value = {}
        mock_svm_cls.return_value = mock_svm

        ReflexioBase(org_id="org1")

        # Verify LiteLLMConfig was created with the custom model
        llm_config_arg = mock_llm_cls.call_args[0][0]
        assert llm_config_arg.model == "custom-model"

    @patch("reflexio.reflexio_lib._base.SiteVarManager")
    @patch("reflexio.reflexio_lib._base.LiteLLMClient")
    @patch("reflexio.reflexio_lib._base.RequestContext")
    def test_init_with_no_config(self, mock_ctx_cls, mock_llm_cls, mock_svm_cls):
        """Initialization handles None config gracefully."""
        mock_ctx = MagicMock()
        mock_ctx.configurator.get_config.return_value = None
        mock_ctx_cls.return_value = mock_ctx

        mock_svm = MagicMock()
        mock_svm.get_site_var.return_value = "not_a_dict"
        mock_svm_cls.return_value = mock_svm

        base = ReflexioBase(org_id="org1")

        # Falls back to default model name when site var is not a dict
        llm_config_arg = mock_llm_cls.call_args[0][0]
        assert llm_config_arg.model == "gpt-5-mini"
        assert base.org_id == "org1"

    @patch("reflexio.reflexio_lib._base.SiteVarManager")
    @patch("reflexio.reflexio_lib._base.LiteLLMClient")
    @patch("reflexio.reflexio_lib._base.RequestContext")
    def test_init_with_configurator(self, mock_ctx_cls, mock_llm_cls, mock_svm_cls):
        """Initialization passes configurator to RequestContext."""
        mock_configurator = MagicMock()
        mock_ctx = MagicMock()
        mock_config = MagicMock()
        mock_config.api_key_config = None
        mock_config.llm_config = None
        mock_ctx.configurator.get_config.return_value = mock_config
        mock_ctx_cls.return_value = mock_ctx

        mock_svm = MagicMock()
        mock_svm.get_site_var.return_value = {}
        mock_svm_cls.return_value = mock_svm

        ReflexioBase(org_id="org1", configurator=mock_configurator)

        mock_ctx_cls.assert_called_once_with(
            org_id="org1", storage_base_dir=None, configurator=mock_configurator
        )
