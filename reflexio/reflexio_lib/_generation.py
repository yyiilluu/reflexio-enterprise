"""Shim re-exporting from open_source submodule."""

from src.reflexio_lib._generation import GenerationMixin  # noqa: F401

__all__ = ["GenerationMixin"]
