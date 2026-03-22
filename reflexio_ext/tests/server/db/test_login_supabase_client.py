"""Tests for login_supabase_client.py."""

from unittest.mock import MagicMock, patch



# ---------------------------------------------------------------------------
# get_login_supabase_client
# ---------------------------------------------------------------------------

class TestGetLoginSupabaseClient:
    def _reset_singleton(self):
        """Reset the module-level singleton before each test."""
        import reflexio_ext.server.db.login_supabase_client as mod
        mod._login_supabase_client = None

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL", ""
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY", ""
    )
    def test_no_url_or_key_returns_none(self):
        self._reset_singleton()
        from reflexio_ext.server.db.login_supabase_client import (
            get_login_supabase_client,
        )
        result = get_login_supabase_client()
        assert result is None

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://supabase.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY", ""
    )
    def test_url_without_key_returns_none(self):
        self._reset_singleton()
        from reflexio_ext.server.db.login_supabase_client import (
            get_login_supabase_client,
        )
        result = get_login_supabase_client()
        assert result is None

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://supabase.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY",
        "test-key",
    )
    @patch("reflexio_ext.server.db.login_supabase_client.create_client")
    def test_creates_client_successfully(self, mock_create):
        self._reset_singleton()
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        from reflexio_ext.server.db.login_supabase_client import (
            get_login_supabase_client,
        )
        result = get_login_supabase_client()
        assert result is mock_client
        mock_create.assert_called_once_with(
            "https://supabase.example.com", "test-key"
        )

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://supabase.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY",
        "test-key",
    )
    @patch("reflexio_ext.server.db.login_supabase_client.create_client")
    def test_returns_cached_client(self, mock_create):
        self._reset_singleton()
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        from reflexio_ext.server.db.login_supabase_client import (
            get_login_supabase_client,
        )
        first = get_login_supabase_client()
        second = get_login_supabase_client()
        assert first is second
        mock_create.assert_called_once()

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://supabase.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY",
        "test-key",
    )
    @patch("reflexio_ext.server.db.login_supabase_client.create_client")
    def test_create_client_exception_returns_none(self, mock_create):
        self._reset_singleton()
        mock_create.side_effect = RuntimeError("connection error")

        from reflexio_ext.server.db.login_supabase_client import (
            get_login_supabase_client,
        )
        result = get_login_supabase_client()
        assert result is None


# ---------------------------------------------------------------------------
# is_using_login_supabase
# ---------------------------------------------------------------------------

class TestIsUsingLoginSupabase:
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL", ""
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY", ""
    )
    def test_false_when_not_configured(self):
        from reflexio_ext.server.db.login_supabase_client import (
            is_using_login_supabase,
        )
        assert is_using_login_supabase() is False

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://sb.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY",
        "key-123",
    )
    def test_true_when_configured(self):
        from reflexio_ext.server.db.login_supabase_client import (
            is_using_login_supabase,
        )
        assert is_using_login_supabase() is True

    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_URL",
        "https://sb.example.com",
    )
    @patch(
        "reflexio_ext.server.db.login_supabase_client.LOGIN_SUPABASE_KEY",
        "",
    )
    def test_false_when_key_missing(self):
        from reflexio_ext.server.db.login_supabase_client import (
            is_using_login_supabase,
        )
        assert is_using_login_supabase() is False
