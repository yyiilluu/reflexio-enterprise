"""Shim re-exporting from open_source submodule."""

from src.server.api import app  # noqa: F401

__all__ = ["app"]
