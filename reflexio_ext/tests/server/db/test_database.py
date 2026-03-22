"""Tests for database.py module-level configuration logic."""

from unittest.mock import MagicMock, patch



class TestIsS3ConfigReady:
    """Test the _is_s3_config_ready helper (already importable)."""

    def test_all_set(self):
        with patch(
            "reflexio_ext.server.db.database.CONFIG_S3_PATH", "bucket"
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_REGION", "us-east-1"
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_ACCESS_KEY", "AKIA"
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_SECRET_KEY", "secret"
        ):
            from reflexio_ext.server.db.database import _is_s3_config_ready
            assert _is_s3_config_ready() is True

    def test_missing_path(self):
        with patch(
            "reflexio_ext.server.db.database.CONFIG_S3_PATH", ""
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_REGION", "us-east-1"
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_ACCESS_KEY", "AKIA"
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_SECRET_KEY", "secret"
        ):
            from reflexio_ext.server.db.database import _is_s3_config_ready
            assert _is_s3_config_ready() is False

    def test_all_empty(self):
        with patch(
            "reflexio_ext.server.db.database.CONFIG_S3_PATH", ""
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_REGION", ""
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_ACCESS_KEY", ""
        ), patch(
            "reflexio_ext.server.db.database.CONFIG_S3_SECRET_KEY", ""
        ):
            from reflexio_ext.server.db.database import _is_s3_config_ready
            assert _is_s3_config_ready() is False


class TestEnsureSqliteTables:
    """Test the ensure_sqlite_tables function."""

    def test_engine_none_is_noop(self):
        with patch("reflexio_ext.server.db.database.engine", None):
            from reflexio_ext.server.db.database import ensure_sqlite_tables
            # Should not raise
            ensure_sqlite_tables()

    def test_engine_present_calls_create_all(self):
        mock_engine = MagicMock()
        mock_base = MagicMock()
        with patch(
            "reflexio_ext.server.db.database.engine", mock_engine
        ), patch("reflexio_ext.server.db.database.Base", mock_base):
            from reflexio_ext.server.db.database import ensure_sqlite_tables
            ensure_sqlite_tables()
            mock_base.metadata.create_all.assert_called_once_with(bind=mock_engine)


class TestModuleLevelConfig:
    """Test the module-level configuration paths."""

    def test_sqlite_fallback_path(self):
        """When no Supabase and no self-host, module uses SQLite."""

        # Current test env should not be self-host mode
        # Just verify the module attributes are accessible
        from reflexio_ext.server.db.database import (
            Base,
            sqlite_local_db_filename,
        )
        assert sqlite_local_db_filename == "sql_app.db"
        assert Base is not None

    def test_self_host_mode_constant(self):
        """SELF_HOST_MODE is a bool derived from env."""
        from reflexio_ext.server.db.database import SELF_HOST_MODE
        assert isinstance(SELF_HOST_MODE, bool)
