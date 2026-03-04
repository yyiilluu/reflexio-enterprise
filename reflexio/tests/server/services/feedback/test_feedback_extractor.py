"""
Unit tests for FeedbackExtractor.

Tests the extractor's new responsibilities for:
- Operation state key generation (not user-scoped)
- Interaction collection with window/stride across all users
- Source filtering
- Operation state updates
- Integration of run() method
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
    RawFeedback,
    BlockingIssue,
    BlockingIssueKind,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.config_schema import AgentFeedbackConfig

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.services.feedback.feedback_extractor import FeedbackExtractor
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationServiceConfig,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    StructuredFeedbackContent,
)
from reflexio.server.llm.litellm_client import LiteLLMClient


# ===============================
# Fixtures
# ===============================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock(spec=LiteLLMClient)
    client.generate_chat_response.return_value = "true"
    return client


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def request_context(temp_storage_dir):
    """Create a request context with mock storage."""
    context = RequestContext(org_id="test_org", storage_base_dir=temp_storage_dir)
    context.storage = MagicMock()
    return context


@pytest.fixture
def extractor_config():
    """Create a feedback extractor config."""
    return AgentFeedbackConfig(
        feedback_name="quality_feedback",
        feedback_definition_prompt="Evaluate agent quality",
    )


@pytest.fixture
def service_config():
    """Create a service config."""
    return FeedbackGenerationServiceConfig(
        agent_version="1.0.0",
        request_id="test_request",
        source="api",
    )


@pytest.fixture
def sample_interactions():
    """Create sample interactions from multiple users for testing."""
    return [
        Interaction(
            interaction_id=1,
            user_id="user1",
            content="The agent helped me well",
            request_id="req1",
            created_at=1000,
            role="user",
        ),
        Interaction(
            interaction_id=2,
            user_id="user1",
            content="Glad I could help!",
            request_id="req1",
            created_at=1001,
            role="assistant",
        ),
        Interaction(
            interaction_id=3,
            user_id="user2",
            content="Could be faster",
            request_id="req2",
            created_at=1002,
            role="user",
        ),
    ]


@pytest.fixture
def sample_request_interaction_models(sample_interactions):
    """Create sample RequestInteractionDataModel objects."""
    request1 = Request(
        request_id="req1",
        user_id="user1",
        created_at=1000,
        source="api",
    )
    request2 = Request(
        request_id="req2",
        user_id="user2",
        created_at=1002,
        source="api",
    )
    return [
        RequestInteractionDataModel(
            request_group="req1",
            request=request1,
            interactions=sample_interactions[:2],
        ),
        RequestInteractionDataModel(
            request_group="req2",
            request=request2,
            interactions=[sample_interactions[2]],
        ),
    ]


# ===============================
# Test: Operation State Key
# ===============================


class TestOperationStateKey:
    """Tests for operation state key generation."""

    def test_state_manager_key_does_not_include_user_id(
        self, request_context, mock_llm_client, extractor_config, service_config
    ):
        """Test that feedback extractor state manager builds keys without user_id (not user-scoped)."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        mgr = extractor._create_state_manager()

        assert mgr.service_name == "feedback_extractor"
        assert mgr.org_id == "test_org"
        # Verify the bookmark key format does NOT include user_id
        key = mgr._bookmark_key(name="quality_feedback")
        assert "feedback_extractor" in key
        assert "test_org" in key
        assert "quality_feedback" in key
        assert key == "feedback_extractor::test_org::quality_feedback"

    def test_different_feedback_names_have_different_keys(
        self, request_context, mock_llm_client, service_config
    ):
        """Test that different feedback names get different operation state keys."""
        config1 = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Quality prompt",
        )
        config2 = AgentFeedbackConfig(
            feedback_name="speed_feedback",
            feedback_definition_prompt="Speed prompt",
        )

        extractor1 = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config1,
            service_config=service_config,
            agent_context="Test agent",
        )
        extractor2 = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config2,
            service_config=service_config,
            agent_context="Test agent",
        )

        mgr1 = extractor1._create_state_manager()
        mgr2 = extractor2._create_state_manager()
        key1 = mgr1._bookmark_key(name="quality_feedback")
        key2 = mgr2._bookmark_key(name="speed_feedback")
        assert key1 != key2


# ===============================
# Test: Get Interactions (Not User-Scoped)
# ===============================


class TestGetInteractions:
    """Tests for interaction collection logic (not user-scoped).

    Note: Stride checking is handled upstream by BaseGenerationService._filter_configs_by_stride()
    before the extractor is created, so stride tests are at the service level.
    """

    def test_passes_none_user_id_to_storage(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that user_id from service_config is passed to get_last_k_interactions_grouped."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._get_interactions()

        # Verify user_id from service_config was passed to storage
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args[
            1
        ]
        assert call_kwargs["user_id"] is None  # service_config.user_id is None

    def test_returns_interactions(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that interactions are returned from storage."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor._get_interactions()

        assert result is not None
        assert len(result) == 2  # Two request groups

    def test_uses_window_size_with_none_user_id(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that window size is used with user_id=None for all users."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
            extraction_window_size_override=50,
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._get_interactions()

        # Verify get_last_k_interactions_grouped was called with user_id=None
        request_context.storage.get_last_k_interactions_grouped.assert_called_once()
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args[
            1
        ]
        assert call_kwargs["user_id"] is None
        assert call_kwargs["k"] == 50

    def test_none_sources_enabled_gets_all_sources(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that request_sources_enabled=None gets interactions from all sources."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate quality",
            request_sources_enabled=None,  # Get all sources
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._get_interactions()

        # Verify sources filter is None (get all sources) in get_last_k_interactions_grouped
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args[
            1
        ]
        assert call_kwargs["sources"] is None


# ===============================
# Test: Update Operation State
# ===============================


class TestUpdateOperationState:
    """Tests for operation state update logic."""

    def test_updates_state_with_all_users_interactions(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that operation state is updated with interactions from all users."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._update_operation_state(sample_request_interaction_models)

        # Verify upsert was called
        request_context.storage.upsert_operation_state.assert_called_once()

        # Verify state contains all interaction IDs (from both users)
        call_args = request_context.storage.upsert_operation_state.call_args
        state = call_args[0][1]

        assert 1 in state["last_processed_interaction_ids"]
        assert 2 in state["last_processed_interaction_ids"]
        assert 3 in state["last_processed_interaction_ids"]


# ===============================
# Test: Run Integration
# ===============================


class TestRun:
    """Integration tests for the run() method."""

    def test_run_collects_interactions_from_all_users(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that run() collects interactions from all users."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            extractor.run()

        # Verify storage was queried with user_id=None
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args[
            1
        ]
        assert call_kwargs["user_id"] is None

    def test_run_returns_raw_feedback(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that run() returns RawFeedback objects."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = extractor.run()

        assert result is not None
        assert len(result) > 0
        assert all(isinstance(f, RawFeedback) for f in result)

    def test_mock_mode_includes_source_interaction_ids(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that mock mode populates source_interaction_ids from input interactions."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = extractor.run()

        assert len(result) == 1
        assert result[0].source_interaction_ids == [1, 2, 3]

    def test_run_returns_empty_when_no_interactions(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that run() returns empty list when no interactions available."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            [],
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor.run()

        assert result == []

    def test_run_updates_operation_state_on_success(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that operation state is updated after successful extraction."""
        config = AgentFeedbackConfig(
            feedback_name="quality_feedback",
            feedback_definition_prompt="Evaluate agent quality",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = extractor.run()

        # Verify operation state was updated
        if result:
            request_context.storage.upsert_operation_state.assert_called()


# ===============================
# Test: Structured Feedback Extraction
# ===============================


class TestStructuredFeedbackExtraction:
    """Tests for structured feedback extraction with JSON output."""

    def test_extracts_structured_feedback_with_all_fields(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that structured feedback with all fields is correctly extracted."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Mock LLM response with flat fields (new schema)
        mock_llm_client.generate_chat_response.return_value = StructuredFeedbackContent(
            do_action="ask for CLI preference",
            do_not_action="assume GUI workflows by default",
            when_condition="assisting technical users",
        )

        # Mock prompt manager
        request_context.prompt_manager = MagicMock()
        request_context.prompt_manager.render_prompt.return_value = "mock prompt"
        request_context.prompt_manager.get_active_version.return_value = "1.2.0"

        # Disable mock mode to use the mocked LLM response
        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}):
            result = extractor.extract_feedbacks(sample_request_interaction_models)

        assert len(result) == 1
        assert result[0].do_action == "ask for CLI preference"
        assert result[0].do_not_action == "assume GUI workflows by default"
        assert result[0].when_condition == "assisting technical users"
        assert result[0].indexed_content == "assisting technical users"
        assert 'When: "assisting technical users"' in result[0].feedback_content
        assert 'Do: "ask for CLI preference"' in result[0].feedback_content
        assert 'Don\'t: "assume GUI workflows by default"' in result[0].feedback_content
        assert result[0].source_interaction_ids == [1, 2, 3]

    def test_extracts_structured_feedback_with_only_do_action(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that structured feedback with only do_action is correctly extracted."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Mock LLM response with only do_action (flat fields)
        mock_llm_client.generate_chat_response.return_value = StructuredFeedbackContent(
            do_action="provide step-by-step instructions",
            do_not_action=None,
            when_condition="user asks for help",
        )

        # Mock prompt manager
        request_context.prompt_manager = MagicMock()
        request_context.prompt_manager.render_prompt.return_value = "mock prompt"
        request_context.prompt_manager.get_active_version.return_value = "1.2.0"

        # Disable mock mode to use the mocked LLM response
        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}):
            result = extractor.extract_feedbacks(sample_request_interaction_models)

        assert len(result) == 1
        assert result[0].do_action == "provide step-by-step instructions"
        assert result[0].do_not_action is None
        assert result[0].when_condition == "user asks for help"

    def test_returns_empty_when_feedback_is_null(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that empty list is returned when feedback is null."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Mock LLM response with no feedback (when_condition is None)
        mock_llm_client.generate_chat_response.return_value = (
            StructuredFeedbackContent()
        )

        # Mock prompt manager
        request_context.prompt_manager = MagicMock()
        request_context.prompt_manager.render_prompt.return_value = "mock prompt"
        request_context.prompt_manager.get_active_version.return_value = "1.2.0"

        # Disable mock mode to use the mocked LLM response
        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}):
            result = extractor.extract_feedbacks(sample_request_interaction_models)

        assert result == []

    def test_returns_empty_on_invalid_response_format(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that empty list is returned when response format is invalid."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Mock LLM response with invalid format (string instead of dict)
        mock_llm_client.generate_chat_response.return_value = "invalid response"

        # Mock prompt manager
        request_context.prompt_manager = MagicMock()
        request_context.prompt_manager.render_prompt.return_value = "mock prompt"
        request_context.prompt_manager.get_active_version.return_value = "1.2.0"

        # Disable mock mode to use the mocked LLM response
        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}):
            result = extractor.extract_feedbacks(sample_request_interaction_models)

        assert result == []


# ===============================
# Test: _process_structured_response Direct Unit Tests
# ===============================


class TestProcessStructuredResponse:
    """
    Direct unit tests for _process_structured_response method.

    These tests ensure the method correctly handles Pydantic model inputs,
    matching the actual return type from LiteLLMClient when parse_structured_output=True.
    """

    def test_processes_raw_feedback_output_pydantic_model(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response correctly handles StructuredFeedbackContent Pydantic model.

        This test ensures the method works with the actual return type from LiteLLMClient
        when response_format=StructuredFeedbackContent and parse_structured_output=True.
        """
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Create the Pydantic model as LiteLLMClient would return it (flat fields)
        pydantic_response = StructuredFeedbackContent(
            do_action="validate inputs",
            do_not_action="trust user data blindly",
            when_condition="processing external data",
        )

        result = extractor._process_structured_response(pydantic_response)

        assert result is not None
        assert result.do_action == "validate inputs"
        assert result.do_not_action == "trust user data blindly"
        assert result.when_condition == "processing external data"
        assert result.feedback_name == extractor_config.feedback_name

    def test_handles_null_feedback_in_pydantic_model(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response returns None when feedback is null."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # No feedback: when_condition is None
        pydantic_response = StructuredFeedbackContent()

        result = extractor._process_structured_response(pydantic_response)

        assert result is None

    def test_passes_source_interaction_ids(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response includes source_interaction_ids when provided."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        pydantic_response = StructuredFeedbackContent(
            do_action="validate inputs",
            when_condition="processing external data",
        )

        result = extractor._process_structured_response(
            pydantic_response, source_interaction_ids=[10, 20, 30]
        )

        assert result is not None
        assert result.source_interaction_ids == [10, 20, 30]

    def test_defaults_source_interaction_ids_to_empty(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response defaults source_interaction_ids to [] when not provided."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        pydantic_response = StructuredFeedbackContent(
            do_action="validate inputs",
            when_condition="processing external data",
        )

        result = extractor._process_structured_response(pydantic_response)

        assert result is not None
        assert result.source_interaction_ids == []

    def test_handles_none_response(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response returns None for None input."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor._process_structured_response(None)

        assert result is None


# ===============================
# Test: Blocking Issue Round-Trip
# ===============================


class TestBlockingIssueRoundTrip:
    """Tests for blocking_issue field in structured feedback extraction."""

    def test_process_structured_response_with_blocking_issue(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response correctly populates blocking_issue on RawFeedback."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        pydantic_response = StructuredFeedbackContent(
            do_action="inform user that file deletion requires admin approval",
            do_not_action="attempt to delete files without permission",
            when_condition="user asks to delete shared files",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.PERMISSION_DENIED,
                details="Agent lacks admin-level file deletion permissions on shared drives",
            ),
        )

        result = extractor._process_structured_response(pydantic_response)

        assert result is not None
        assert result.blocking_issue is not None
        assert result.blocking_issue.kind == BlockingIssueKind.PERMISSION_DENIED
        assert "admin-level file deletion" in result.blocking_issue.details
        assert "Blocked by:" in result.feedback_content
        assert "[permission_denied]" in result.feedback_content

    def test_process_structured_response_without_blocking_issue(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that _process_structured_response works correctly when blocking_issue is None."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        pydantic_response = StructuredFeedbackContent(
            do_action="validate inputs",
            when_condition="processing external data",
        )

        result = extractor._process_structured_response(pydantic_response)

        assert result is not None
        assert result.blocking_issue is None
        assert "Blocked by:" not in result.feedback_content

    def test_extracts_feedback_with_blocking_issue_end_to_end(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test end-to-end extraction with blocking_issue included in LLM response."""
        extractor = FeedbackExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        mock_llm_client.generate_chat_response.return_value = StructuredFeedbackContent(
            do_action="suggest using the API endpoint instead",
            do_not_action="attempt to access the database directly",
            when_condition="user requests direct database access",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.MISSING_TOOL,
                details="No direct database query tool available",
            ),
        )

        request_context.prompt_manager = MagicMock()
        request_context.prompt_manager.render_prompt.return_value = "mock prompt"
        request_context.prompt_manager.get_active_version.return_value = "2.0.0"

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}):
            result = extractor.extract_feedbacks(sample_request_interaction_models)

        assert len(result) == 1
        assert result[0].blocking_issue is not None
        assert result[0].blocking_issue.kind == BlockingIssueKind.MISSING_TOOL
        assert (
            result[0].blocking_issue.details
            == "No direct database query tool available"
        )
        assert "Blocked by: [missing_tool]" in result[0].feedback_content
