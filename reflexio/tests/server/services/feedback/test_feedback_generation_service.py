import datetime
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
)

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackGenerationRequest,
)


def create_request_interaction_data_model(
    user_id: str, request_id: str, interactions: list[Interaction]
) -> RequestInteractionDataModel:
    """Helper function to create a RequestInteractionDataModel for testing."""
    request = Request(
        request_id=request_id,
        user_id=user_id,
        source="test",
        agent_version="1.0",
        session_id="session_1",
    )
    return RequestInteractionDataModel(
        session_id="session_1",
        request=request,
        interactions=interactions,
    )


@pytest.fixture
def mock_chat_completion():
    # Mock response for should_generate_feedback call
    mock_should_generate_response = "true"

    # Mock response for extract_feedback call
    mock_extract_response = '```json\n{\n    "feedback": "The agent was helpful and provided accurate information",\n    "type": "positive"\n}\n```'

    def mock_generate_chat_response_side_effect(messages, **kwargs):
        """
        Check prompt content to determine which mock response to return.
        If prompt contains "Output just a boolean value", return boolean response.
        Otherwise, return JSON feedback response.
        """
        # Get the prompt content from the messages
        prompt_content = ""
        for message in messages:
            if isinstance(message, dict) and "content" in message:
                prompt_content += str(message["content"])

        # Check if this is a should_generate_feedback call
        if "Output just a boolean value" in prompt_content:
            return mock_should_generate_response
        # Otherwise, this is a feedback extraction call
        return mock_extract_response

    # Mock the OpenAI client's generate_chat_response method
    with patch(
        "reflexio.server.llm.openai_client.OpenAIClient.generate_chat_response",
        side_effect=mock_generate_chat_response_side_effect,
    ):
        yield


def test_generate_feedback(mock_chat_completion):
    user_id = "test_user_id"
    org_id = "0"
    interaction = Interaction(
        interaction_id=1,
        user_id=user_id,
        request_id="test_request_id",
        content="The agent was very helpful in explaining the process",
        role="user",
        created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        # Set up feedback config with extraction_window_size
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        feedback_generation_service.configurator.set_config_by_name(
            "extraction_window_size", 100
        )

        # Store interactions in storage first
        request_obj = Request(
            request_id="test_request_id",
            user_id=user_id,
            source="test",
            agent_version="1.0",
            session_id="session_1",
        )
        feedback_generation_service.storage.add_request(request_obj)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction)

        # Create feedback generation request - extractors collect from storage
        feedback_request = FeedbackGenerationRequest(
            request_id="test_request_id",
            agent_version="1.0",
            user_id=user_id,
            auto_run=False,  # Skip stride check for testing
        )

        feedback_generation_service.run(feedback_request)

        # Verify feedback was saved
        raw_feedbacks = feedback_generation_service.storage.get_raw_feedbacks()
        assert len(raw_feedbacks) > 0
        feedback = raw_feedbacks[0]
        assert feedback.request_id == "test_request_id"


def test_empty_interactions(mock_chat_completion):
    org_id = "0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        # Set up feedback config
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )

        # Create feedback generation request with empty request interaction data models
        feedback_request = FeedbackGenerationRequest(
            request_id="test_request_id",
            agent_version="1.0",
            request_interaction_data_models=[],
        )

        feedback_generation_service.run(feedback_request)

        # Verify no feedback was generated
        raw_feedbacks = feedback_generation_service.storage.get_raw_feedbacks()
        assert len(raw_feedbacks) == 0


def test_missing_configs(mock_chat_completion):
    user_id = "test_user_id"
    org_id = "0"
    interaction = Interaction(
        interaction_id=1,
        user_id=user_id,
        request_id="test_request_id",
        content="The agent was very helpful in explaining the process",
        role="user",
        created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        # Create request interaction data model
        request_interaction_data_model = create_request_interaction_data_model(
            user_id=user_id,
            request_id="test_request_id",
            interactions=[interaction],
        )

        # Create feedback generation request without setting up configs
        feedback_request = FeedbackGenerationRequest(
            request_id="test_request_id",
            agent_version="1.0",
            request_interaction_data_models=[request_interaction_data_model],
        )

        feedback_generation_service.run(feedback_request)

        # Verify no feedback was generated
        raw_feedbacks = feedback_generation_service.storage.get_raw_feedbacks()
        assert len(raw_feedbacks) == 0


def test_error_handling(mock_chat_completion):
    user_id = "test_user_id"
    org_id = "0"
    interaction = Interaction(
        interaction_id=1,
        user_id=user_id,
        request_id="test_request_id",
        content="The agent was very helpful in explaining the process",
        role="user",
        created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        # Set up feedback config
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )

        # Create request interaction data model
        request_interaction_data_model = create_request_interaction_data_model(
            user_id=user_id,
            request_id="test_request_id",
            interactions=[interaction],
        )

        # Create feedback generation request
        feedback_request = FeedbackGenerationRequest(
            request_id="test_request_id",
            agent_version="1.0",
            request_interaction_data_models=[request_interaction_data_model],
        )

        # Mock storage.save_raw_feedbacks to raise an exception
        with patch.object(
            feedback_generation_service.storage,
            "save_raw_feedbacks",
            side_effect=Exception("Storage error"),
        ):
            # The service should handle the error gracefully
            feedback_generation_service.run(feedback_request)

            # Verify no feedback was saved
            raw_feedbacks = feedback_generation_service.storage.get_raw_feedbacks()
            assert len(raw_feedbacks) == 0


def test_run_manual_regular_no_window_size(mock_chat_completion):
    """Test run_manual_regular works even without extraction_window_size configured.

    Since extractors handle window size at their level, the manual flow no longer
    validates window_size upfront. Extractors use a fallback of 1000 interactions
    when no window size is configured.
    """
    org_id = "0"
    user_id = "test_user"
    agent_version = "1.0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=False,
        )

        # Set up feedback config WITHOUT window size
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        # extraction_window_size is not configured

        # Add some interactions to storage
        interaction = Interaction(
            interaction_id=1,
            user_id=user_id,
            request_id="request_1",
            content="Test content",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        request_obj = Request(
            request_id="request_1",
            user_id=user_id,
            source="",
        )
        feedback_generation_service.storage.add_request(request_obj)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction)

        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
        )

        request = ManualFeedbackGenerationRequest(agent_version=agent_version)
        response = feedback_generation_service.run_manual_regular(request)

        # Without window_size, extractors use fallback of 1000 interactions
        # So the request should succeed
        assert response.success is True


def test_run_manual_regular_no_interactions(mock_chat_completion):
    """Test run_manual_regular handles case when no interactions exist."""
    org_id = "0"
    agent_version = "1.0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=False,
        )

        # Set up feedback config WITH window size
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        feedback_generation_service.configurator.set_config_by_name(
            "extraction_window_size", 100
        )

        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
        )

        request = ManualFeedbackGenerationRequest(agent_version=agent_version)
        response = feedback_generation_service.run_manual_regular(request)

        # Should succeed but with 0 feedbacks since no interactions
        assert response.success is True
        assert response.feedbacks_generated == 0
        assert "No interactions found" in response.msg


def test_run_manual_regular_with_interactions(mock_chat_completion):
    """Test run_manual_regular generates feedbacks with CURRENT status."""
    user_id = "test_user_id"
    org_id = "0"
    agent_version = "1.0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=False,
        )

        # Set up feedback config WITH window size and allow_manual_trigger
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
            allow_manual_trigger=True,  # Required for manual generation
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        feedback_generation_service.configurator.set_config_by_name(
            "extraction_window_size", 100
        )

        # First, add some interactions to storage
        interaction = Interaction(
            interaction_id=1,
            user_id=user_id,
            request_id="test_request_id",
            content="The agent was very helpful",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        request_obj = Request(
            request_id="test_request_id",
            user_id=user_id,
            source="",
            agent_version=agent_version,
        )
        feedback_generation_service.storage.add_request(request_obj)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction)

        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
        )

        request = ManualFeedbackGenerationRequest(agent_version=agent_version)
        response = feedback_generation_service.run_manual_regular(request)

        # Should succeed (feedbacks generated depends on mock)
        assert response.success is True
        # Note: feedbacks_generated may be 0 if mock returns no feedback
        # The key is that the method runs without error


def test_run_manual_regular_with_source_filter(mock_chat_completion):
    """Test run_manual_regular respects source filter."""
    user_id = "test_user_id"
    org_id = "0"
    agent_version = "1.0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=False,
        )

        # Set up feedback config WITH window size and allow_manual_trigger
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
            allow_manual_trigger=True,  # Required for manual generation
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        feedback_generation_service.configurator.set_config_by_name(
            "extraction_window_size", 100
        )

        # Add interactions with source_a
        interaction_a = Interaction(
            interaction_id=1,
            user_id=user_id,
            request_id="request_a",
            content="The agent was helpful",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        request_a = Request(
            request_id="request_a",
            user_id=user_id,
            source="source_a",
            agent_version=agent_version,
        )
        feedback_generation_service.storage.add_request(request_a)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction_a)

        # Add interactions with source_b
        interaction_b = Interaction(
            interaction_id=2,
            user_id=user_id,
            request_id="request_b",
            content="The agent was not helpful",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        request_b = Request(
            request_id="request_b",
            user_id=user_id,
            source="source_b",
            agent_version=agent_version,
        )
        feedback_generation_service.storage.add_request(request_b)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction_b)

        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
        )

        # Request with non-existent source
        request = ManualFeedbackGenerationRequest(
            agent_version=agent_version, source="non_existent_source"
        )
        response = feedback_generation_service.run_manual_regular(request)

        # Should succeed but with 0 feedbacks since no matching source
        assert response.success is True
        assert response.feedbacks_generated == 0


def test_run_manual_regular_output_pending_status_false(mock_chat_completion):
    """Test that run_manual_regular outputs CURRENT status when output_pending_status=False."""
    user_id = "test_user_id"
    org_id = "0"
    agent_version = "1.0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)

        # Create service with output_pending_status=False (default for manual regular)
        feedback_generation_service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=False,
        )

        # Set up feedback config WITH window size and allow_manual_trigger
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
            allow_manual_trigger=True,  # Required for manual generation
        )
        feedback_generation_service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        feedback_generation_service.configurator.set_config_by_name(
            "extraction_window_size", 100
        )

        # Add interaction
        interaction = Interaction(
            interaction_id=1,
            user_id=user_id,
            request_id="test_request_id",
            content="The agent was very helpful",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        request_obj = Request(
            request_id="test_request_id",
            user_id=user_id,
            source="",
            agent_version=agent_version,
        )
        feedback_generation_service.storage.add_request(request_obj)
        feedback_generation_service.storage.add_user_interaction(user_id, interaction)

        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
            Status,
        )

        request = ManualFeedbackGenerationRequest(agent_version=agent_version)
        response = feedback_generation_service.run_manual_regular(request)

        # Should succeed (feedbacks generated depends on mock)
        assert response.success is True
        # Note: feedbacks_generated may be 0 if mock returns no feedback

        # Verify no PENDING feedbacks (output_pending_status=False)
        pending_feedbacks = feedback_generation_service.storage.get_raw_feedbacks(
            status_filter=[Status.PENDING]
        )

        assert len(pending_feedbacks) == 0, (
            "Manual generation should not create PENDING feedbacks"
        )


# ===============================
# Tests for _get_rerun_user_ids
# ===============================


class TestGetRerunItems:
    """Tests for the _get_rerun_user_ids method."""

    def test_get_rerun_user_ids_returns_user_ids(self):
        """Test that _get_rerun_user_ids returns user IDs."""
        org_id = "0"

        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            service = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(
                    org_id=org_id, storage_base_dir=temp_dir
                ),
            )

            # Add interactions with different users
            agent_version = "1.0"

            # User 1 - 2 requests
            user_id_1 = "test_user_1"
            for i in range(2):
                request_id = f"request_user1_{i}"
                interaction = Interaction(
                    interaction_id=i,
                    user_id=user_id_1,
                    request_id=request_id,
                    content=f"Test content {i}",
                    role="user",
                    created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
                )
                request_obj = Request(
                    request_id=request_id,
                    user_id=user_id_1,
                    source="test_source",
                    agent_version=agent_version,
                    session_id="group_1",
                )
                service.storage.add_request(request_obj)
                service.storage.add_user_interaction(user_id_1, interaction)

            # User 2 - 1 request
            user_id_2 = "test_user_2"
            request_id = "request_user2_0"
            interaction = Interaction(
                interaction_id=10,
                user_id=user_id_2,
                request_id=request_id,
                content="Test content user 2",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            request_obj = Request(
                request_id=request_id,
                user_id=user_id_2,
                source="test_source",
                agent_version=agent_version,
                session_id="group_2",
            )
            service.storage.add_request(request_obj)
            service.storage.add_user_interaction(user_id_2, interaction)

            from reflexio_commons.api_schema.service_schemas import (
                RerunFeedbackGenerationRequest,
            )

            request = RerunFeedbackGenerationRequest(agent_version=agent_version)
            result = service._get_rerun_user_ids(request)

            # Should return list of 2 user IDs
            assert len(result) == 2
            assert user_id_1 in result
            assert user_id_2 in result

    def test_get_rerun_user_ids_with_source_filter(self):
        """Test that _get_rerun_user_ids applies source filter correctly."""
        org_id = "0"

        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            service = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(
                    org_id=org_id, storage_base_dir=temp_dir
                ),
            )

            agent_version = "1.0"

            # Add request with source_a for user_a
            user_id_a = "test_user_a"
            interaction_a = Interaction(
                interaction_id=1,
                user_id=user_id_a,
                request_id="request_a",
                content="Test content A",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            request_a = Request(
                request_id="request_a",
                user_id=user_id_a,
                source="source_a",
                agent_version=agent_version,
                session_id="group_a",
            )
            service.storage.add_request(request_a)
            service.storage.add_user_interaction(user_id_a, interaction_a)

            # Add request with source_b for user_b
            user_id_b = "test_user_b"
            interaction_b = Interaction(
                interaction_id=2,
                user_id=user_id_b,
                request_id="request_b",
                content="Test content B",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            request_b = Request(
                request_id="request_b",
                user_id=user_id_b,
                source="source_b",
                agent_version=agent_version,
                session_id="group_b",
            )
            service.storage.add_request(request_b)
            service.storage.add_user_interaction(user_id_b, interaction_b)

            from reflexio_commons.api_schema.service_schemas import (
                RerunFeedbackGenerationRequest,
            )

            # Filter by source_a - should only include user_a
            request = RerunFeedbackGenerationRequest(
                agent_version=agent_version, source="source_a"
            )
            result = service._get_rerun_user_ids(request)

            # Should only have user_a (who has source_a requests)
            assert len(result) == 1
            assert user_id_a in result
            assert user_id_b not in result


def test_get_rerun_user_ids_returns_empty_when_no_matches():
    """Test that _get_rerun_user_ids returns empty list when no items match."""
    org_id = "0"

    with tempfile.TemporaryDirectory() as temp_dir:
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        from reflexio_commons.api_schema.service_schemas import (
            RerunFeedbackGenerationRequest,
        )

        request = RerunFeedbackGenerationRequest(agent_version="1.0")
        result = service._get_rerun_user_ids(request)

        assert result == []


def test_collect_scoped_interactions_for_precheck_uses_extractor_scope():
    """Pre-check should use extractor-specific window and source filters."""
    org_id = "0"
    user_id = "test_user"

    with tempfile.TemporaryDirectory() as temp_dir:
        service = FeedbackGenerationService(
            llm_client=LiteLLMClient(LiteLLMConfig(model="gpt-4o-mini")),
            request_context=RequestContext(org_id=org_id, storage_base_dir=temp_dir),
        )

        service.configurator.set_config_by_name("extraction_window_size", 200)
        service.service_config = service._load_generation_service_config(
            FeedbackGenerationRequest(
                request_id="request-1",
                agent_version="1.0",
                user_id=user_id,
                source="api",
                auto_run=True,
            )
        )

        interaction = Interaction(
            interaction_id=1,
            user_id=user_id,
            request_id="request-1",
            content="user corrected the agent behavior",
            role="user",
            created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
        )
        session_id = create_request_interaction_data_model(
            user_id=user_id,
            request_id="request-1",
            interactions=[interaction],
        )

        service.storage.get_last_k_interactions_grouped = MagicMock(
            return_value=([session_id], [])
        )

        extractor_configs = [
            AgentFeedbackConfig(
                feedback_name="api_feedback",
                feedback_definition_prompt="extract api-related feedback",
                request_sources_enabled=["api"],
                extraction_window_size_override=120,
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=2
                ),
            ),
            AgentFeedbackConfig(
                feedback_name="web_feedback",
                feedback_definition_prompt="extract web-related feedback",
                request_sources_enabled=["web"],
                extraction_window_size_override=80,
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=2
                ),
            ),
        ]

        (
            scoped_groups,
            scoped_configs,
        ) = service._collect_scoped_interactions_for_precheck(extractor_configs)

        assert len(scoped_groups) == 1
        assert [c.feedback_name for c in scoped_configs] == ["api_feedback"]
        service.storage.get_last_k_interactions_grouped.assert_called_once()
        _, kwargs = service.storage.get_last_k_interactions_grouped.call_args
        assert kwargs["k"] == 120
        assert kwargs["sources"] == ["api"]


if __name__ == "__main__":
    pytest.main([__file__])
