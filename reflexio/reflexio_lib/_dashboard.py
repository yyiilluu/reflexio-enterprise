"""Shim re-exporting from open_source submodule."""

from src.reflexio_lib._dashboard import DashboardMixin  # noqa: F401

__all__ = ["DashboardMixin"]
