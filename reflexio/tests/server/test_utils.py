import base64
import os

import pytest


def skip_in_precommit(func):
    """Decorator to skip tests during pre-commit hooks"""
    return pytest.mark.skipif(
        os.environ.get("PRECOMMIT") == "1", reason="Test skipped in pre-commit hook"
    )(func)


def skip_low_priority(func):
    """
    Decorator to skip low priority tests unless explicitly requested.
    These tests are skipped by default and only run when RUN_LOW_PRIORITY=1 is set.

    Usage:
        @skip_low_priority
        def test_something_low_priority():
            ...

    To run low priority tests:
        RUN_LOW_PRIORITY=1 pytest ...
    """
    return pytest.mark.skipif(
        os.environ.get("RUN_LOW_PRIORITY") != "1",
        reason="Low priority test - set RUN_LOW_PRIORITY=1 to run",
    )(func)


def encode_image_to_base64(image_fp: str) -> str:
    with open(image_fp, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
