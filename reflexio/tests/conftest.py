"""
Test configuration utilities.

Ensures the project root is available on ``sys.path`` so imports such as
``reflexio.reflexio_lib`` resolve correctly during pytest collection.

Also sets MOCK_LLM_RESPONSE environment variable and patches litellm for tests.
Note: E2E tests are excluded from mocking to allow real API calls.
"""

from __future__ import annotations

import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Global LiteLLM Mock for reflexio tests (excludes e2e_tests)
# Uses pytest_configure hook for earliest possible patching in each worker
# ============================================================================

import json
from unittest.mock import MagicMock, patch


def _create_mock_completion(prompt_content, parse_structured_output=False):
    """Create a mock LiteLLM completion response."""
    if "Output just a boolean value" in prompt_content:
        content = "true"
    elif (
        "policy consolidation" in prompt_content or "WHEN conditions" in prompt_content
    ):
        # Feedback aggregation response (feedback_generation prompt)
        content = json.dumps(
            {
                "feedback": {
                    "do_action": "consolidated helpful action",
                    "when_condition": "when user asks a question",
                }
            }
        )
    elif parse_structured_output:
        content = json.dumps(
            {
                "add": [{"content": "likes sushi", "time_to_live": "one_month"}],
                "update": [],
                "delete": [],
            }
        )
    else:
        content = '```json\n{"add": [{"content": "likes sushi", "time_to_live": "one_month"}], "update": [], "delete": []}\n```'

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response.choices[0].finish_reason = "stop"
    return mock_response


def _mock_completion(*args, **kwargs):
    """Mock implementation for litellm.completion."""
    messages = kwargs.get("messages", args[0] if args else [])
    prompt_content = ""
    for message in messages:
        if isinstance(message, dict) and "content" in message:
            prompt_content += str(message["content"])

    parse_structured = kwargs.get("response_format") is not None
    return _create_mock_completion(prompt_content, parse_structured)


def _is_e2e_test_run(config) -> bool:
    """
    Check if this pytest run includes e2e tests.

    Returns True if any of the test paths contain 'e2e_tests'.
    """
    # Check command line arguments for test paths
    args = config.args if hasattr(config, "args") else []
    for arg in args:
        if "e2e_tests" in str(arg):
            return True

    # Check if running from xdist worker - check the workerinput
    if hasattr(config, "workerinput"):
        worker_args = config.workerinput.get("args", [])
        for arg in worker_args:
            if "e2e_tests" in str(arg):
                return True

    return False


# Global patcher reference to keep it alive
_litellm_patcher = None


def pytest_configure(config):
    """
    Pytest hook that runs during configuration, before any tests.
    This is called in each xdist worker process.

    Skips mocking for e2e tests to allow real API calls.
    """
    global _litellm_patcher

    # Skip mocking for e2e tests - they need real API calls
    if _is_e2e_test_run(config):
        return

    # Set mock env var and start the litellm.completion patch for unit tests
    os.environ["MOCK_LLM_RESPONSE"] = "true"
    _litellm_patcher = patch("litellm.completion", side_effect=_mock_completion)
    _litellm_patcher.start()


def pytest_unconfigure(config):
    """
    Pytest hook that runs during cleanup.
    """
    global _litellm_patcher

    if _litellm_patcher:
        _litellm_patcher.stop()
        _litellm_patcher = None
