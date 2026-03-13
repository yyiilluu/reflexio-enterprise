"""Pytest configuration for reflexio_lib tests.

This conftest provides fixtures for unit tests with mocked LLM responses.
The LLM mock is applied globally in the parent conftest.py.
"""

import os

import pytest


@pytest.fixture(autouse=True, scope="function")
def ensure_mock_env():
    """Function-scoped fixture to ensure mock mode is enabled for each test.

    This provides extra safety by re-verifying the env var is set.
    """
    os.environ["MOCK_LLM_RESPONSE"] = "true"
    yield
