import datetime
import logging
import tempfile
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, Mock, patch

import pytest
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.generation_service import GenerationService
from reflexio_commons.api_schema.service_schemas import (
    InteractionData,
    PublishUserInteractionRequest,
)


@pytest.fixture
def mock_llm_responses():
    """Mock all LLM calls to avoid actual API calls"""

    def mock_generate_chat_response_side_effect(messages, **kwargs):
        """Mock LLM responses for different types of calls"""
        prompt_content = ""
        for message in messages:
            if isinstance(message, dict) and "content" in message:
                prompt_content += str(message["content"])

        # Check if this is a should_extract_profile call
        if "Output just a boolean value" in prompt_content:
            return "false"  # Don't extract profiles in this test
        # For structured output parsing
        if kwargs.get("parse_structured_output", False):
            return {"add": [], "update": [], "delete": []}
        return '```json\n{"add": [], "update": [], "delete": []}\n```'

    with patch(
        "reflexio.server.llm.litellm_client.LiteLLMClient.generate_chat_response",
        side_effect=mock_generate_chat_response_side_effect,
    ):
        yield


def test_publish_request_with_session_id(mock_llm_responses):
    """
    Test that requests with a session_id are stored correctly.
    """
    user_id = "test_user_id"
    org_id = "test_org"
    session_id = "test_session_id"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        generation_service = GenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        interaction = InteractionData(
            content="test interaction",
            created_at=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        )

        request = PublishUserInteractionRequest(
            user_id=user_id,
            interaction_data_list=[interaction],
            session_id=session_id,
        )

        # Request should succeed
        generation_service.run(request)


def test_empty_session_id_allows_multiple_requests(mock_llm_responses):
    """
    Test that multiple requests with empty session_id are allowed.
    """
    user_id = "test_user_id"
    org_id = "test_org"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        generation_service = GenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        interaction = InteractionData(
            content="interaction without session",
            created_at=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        )

        # Request without session_id (empty string)
        request = PublishUserInteractionRequest(
            user_id=user_id,
            interaction_data_list=[interaction],
            session_id="",  # Empty session
        )

        # Should not raise any exception
        generation_service.run(request)

        # Try another request with empty session_id - should also succeed
        another_interaction = InteractionData(
            content="another interaction without session",
            created_at=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        )

        another_request = PublishUserInteractionRequest(
            user_id=user_id,
            interaction_data_list=[another_interaction],
            session_id="",
        )

        # Should not raise any exception
        generation_service.run(another_request)


# NOTE: TestWindowSizeStrideOverrides class was removed because the global
# _get_extraction_window_size() and _get_stride_size() methods were removed
# from GenerationService. Each extractor now handles its own window/stride
# calculation using the get_extractor_window_params() utility function.
# See: reflexio/server/services/extractor_interaction_utils.py


# ── Fixtures for unit tests with mocked storage ──


@pytest.fixture
def mock_storage():
    """Create a mock storage with all required methods."""
    storage = MagicMock()
    storage.add_request = MagicMock()
    storage.add_user_interactions_bulk = MagicMock()
    storage.count_all_interactions = MagicMock(return_value=0)
    storage.delete_oldest_interactions = MagicMock(return_value=0)
    return storage


@pytest.fixture
def mock_request_context(mock_storage):
    """Create a mock RequestContext backed by mock_storage."""
    ctx = MagicMock(spec=RequestContext)
    ctx.storage = mock_storage
    ctx.org_id = "test_org"
    ctx.configurator = MagicMock()
    return ctx


@pytest.fixture
def generation_service(mock_request_context):
    """Create a GenerationService with mocked dependencies."""
    llm_client = MagicMock(spec=LiteLLMClient)
    return GenerationService(
        llm_client=llm_client, request_context=mock_request_context
    )


def _make_request(
    user_id: str = "user_1",
    content: str = "hello",
    session_id: str | None = None,
) -> PublishUserInteractionRequest:
    """Helper to build a minimal PublishUserInteractionRequest."""
    interaction = InteractionData(
        content=content,
        created_at=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    )
    return PublishUserInteractionRequest(
        user_id=user_id,
        interaction_data_list=[interaction],
        session_id=session_id or "",
    )


# ── None / empty validation ──


class TestRunValidation:
    """Tests for early-return validation paths in GenerationService.run()."""

    def test_none_request_returns_early(self, generation_service, mock_storage):
        """Passing None as the request should return immediately without touching storage."""
        generation_service.run(None)
        mock_storage.add_request.assert_not_called()
        mock_storage.add_user_interactions_bulk.assert_not_called()

    def test_none_user_id_returns_early(self, generation_service, mock_storage):
        """A request with user_id=None should return immediately."""
        # Pydantic enforces NonEmptyStr, so we use a Mock to bypass validation
        request = Mock(spec=PublishUserInteractionRequest)
        request.user_id = None
        generation_service.run(request)
        mock_storage.add_request.assert_not_called()

    def test_empty_interactions_returns_early(self, generation_service, mock_storage):
        """A request with an empty interaction_data_list should store nothing after cleanup."""
        # Pydantic enforces min_length=1, so we use a Mock to bypass validation
        request = Mock(spec=PublishUserInteractionRequest)
        request.user_id = "user_1"
        request.interaction_data_list = []
        generation_service.run(request)
        # add_request is not called because get_interaction_from... returns []
        mock_storage.add_user_interactions_bulk.assert_not_called()


# ── ThreadPoolExecutor timeout ──


class TestRunTimeout:
    """Tests for timeout handling in the parallel generation executor."""

    @patch("reflexio.server.services.generation_service.ProfileGenerationService")
    @patch("reflexio.server.services.generation_service.FeedbackGenerationService")
    def test_futures_timeout_is_logged_not_raised(
        self,
        mock_feedback_cls,
        mock_profile_cls,
        generation_service,
        mock_storage,
        caplog,
    ):
        """When future.result() raises FuturesTimeoutError, the error is logged but not raised."""
        mock_profile_cls.return_value.run = MagicMock(side_effect=FuturesTimeoutError())
        mock_feedback_cls.return_value.run = MagicMock(
            side_effect=FuturesTimeoutError()
        )

        request = _make_request()
        with caplog.at_level(logging.ERROR):
            generation_service.run(request)

        assert "timed out" in caplog.text


# ── Exception in one service ──


class TestRunPartialFailure:
    """Tests that one service failing does not block the other."""

    @patch("reflexio.server.services.generation_service.ProfileGenerationService")
    @patch("reflexio.server.services.generation_service.FeedbackGenerationService")
    def test_profile_failure_does_not_block_feedback(
        self,
        mock_feedback_cls,
        mock_profile_cls,
        generation_service,
    ):
        """If profile generation raises, feedback generation should still complete."""
        mock_profile_cls.return_value.run = MagicMock(
            side_effect=RuntimeError("profile boom")
        )
        mock_feedback_cls.return_value.run = MagicMock()

        request = _make_request()
        generation_service.run(request)

        mock_feedback_cls.return_value.run.assert_called_once()

    @patch("reflexio.server.services.generation_service.ProfileGenerationService")
    @patch("reflexio.server.services.generation_service.FeedbackGenerationService")
    def test_feedback_failure_does_not_block_profile(
        self,
        mock_feedback_cls,
        mock_profile_cls,
        generation_service,
    ):
        """If feedback generation raises, profile generation should still complete."""
        mock_profile_cls.return_value.run = MagicMock()
        mock_feedback_cls.return_value.run = MagicMock(
            side_effect=RuntimeError("feedback boom")
        )

        request = _make_request()
        generation_service.run(request)

        mock_profile_cls.return_value.run.assert_called_once()


# ── _cleanup_old_interactions_if_needed ──


class TestCleanupOldInteractions:
    """Tests for _cleanup_old_interactions_if_needed()."""

    def test_threshold_disabled_skips_cleanup(self, generation_service, mock_storage):
        """When INTERACTION_CLEANUP_THRESHOLD <= 0, cleanup should be skipped entirely."""
        with (
            patch("reflexio.server.INTERACTION_CLEANUP_THRESHOLD", 0),
            patch("reflexio.server.INTERACTION_CLEANUP_DELETE_COUNT", 100),
        ):
            generation_service._cleanup_old_interactions_if_needed()
        mock_storage.count_all_interactions.assert_not_called()

    def test_below_threshold_no_delete(self, generation_service, mock_storage):
        """When total count is below threshold, no deletion should occur."""
        mock_storage.count_all_interactions.return_value = 100

        with (
            patch("reflexio.server.INTERACTION_CLEANUP_THRESHOLD", 500),
            patch("reflexio.server.INTERACTION_CLEANUP_DELETE_COUNT", 50),
        ):
            generation_service._cleanup_old_interactions_if_needed()

        mock_storage.count_all_interactions.assert_called_once()
        mock_storage.delete_oldest_interactions.assert_not_called()

    @patch("reflexio.server.services.generation_service.OperationStateManager")
    def test_above_threshold_with_lock_deletes_oldest(
        self, mock_osm_cls, generation_service, mock_storage
    ):
        """When above threshold and lock acquired, oldest interactions should be deleted."""
        mock_storage.count_all_interactions.return_value = 600
        mock_storage.delete_oldest_interactions.return_value = 50

        mock_mgr = MagicMock()
        mock_mgr.acquire_simple_lock.return_value = True
        mock_osm_cls.return_value = mock_mgr

        with (
            patch("reflexio.server.INTERACTION_CLEANUP_THRESHOLD", 500),
            patch("reflexio.server.INTERACTION_CLEANUP_DELETE_COUNT", 50),
        ):
            generation_service._cleanup_old_interactions_if_needed()

        mock_storage.delete_oldest_interactions.assert_called_once_with(50)
        mock_mgr.release_simple_lock.assert_called_once()

    @patch("reflexio.server.services.generation_service.OperationStateManager")
    def test_lock_not_acquired_skips_delete(
        self, mock_osm_cls, generation_service, mock_storage
    ):
        """When lock cannot be acquired, deletion should be skipped."""
        mock_storage.count_all_interactions.return_value = 600

        mock_mgr = MagicMock()
        mock_mgr.acquire_simple_lock.return_value = False
        mock_osm_cls.return_value = mock_mgr

        with (
            patch("reflexio.server.INTERACTION_CLEANUP_THRESHOLD", 500),
            patch("reflexio.server.INTERACTION_CLEANUP_DELETE_COUNT", 50),
        ):
            generation_service._cleanup_old_interactions_if_needed()

        mock_storage.delete_oldest_interactions.assert_not_called()
        mock_mgr.release_simple_lock.assert_not_called()

    def test_cleanup_exception_caught_and_logged(
        self, generation_service, mock_storage, caplog
    ):
        """If cleanup raises, the exception should be caught and logged without propagating."""
        mock_storage.count_all_interactions.side_effect = RuntimeError("db down")

        with (
            patch("reflexio.server.INTERACTION_CLEANUP_THRESHOLD", 500),
            patch("reflexio.server.INTERACTION_CLEANUP_DELETE_COUNT", 50),
            caplog.at_level(logging.ERROR),
        ):
            # Should not raise
            generation_service._cleanup_old_interactions_if_needed()

        assert "Failed to cleanup old interactions" in caplog.text
