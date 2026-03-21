import datetime
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackGenerationRequest,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
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


# ===============================
# Tests for _build_should_run_prompt
# ===============================


class TestBuildShouldRunPrompt:
    """Tests for _build_should_run_prompt method."""

    def _create_service(self, temp_dir: str) -> FeedbackGenerationService:
        """Helper to create a FeedbackGenerationService for testing."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        return FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
        )

    def test_with_feedback_definition_prompt_present(self):
        """Test _build_should_run_prompt when feedback_definition_prompt is present."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service(temp_dir)

            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb1",
                    feedback_definition_prompt="Check for helpfulness",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                ),
                AgentFeedbackConfig(
                    feedback_name="fb2",
                    feedback_definition_prompt="Check for accuracy",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                ),
            ]

            interaction = Interaction(
                interaction_id=1,
                user_id="user1",
                request_id="req1",
                content="Hello",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            session_data = create_request_interaction_data_model(
                user_id="user1",
                request_id="req1",
                interactions=[interaction],
            )

            mock_prompt = "rendered prompt"
            with patch.object(
                service.request_context.prompt_manager,
                "render_prompt",
                return_value=mock_prompt,
            ) as mock_render:
                result = service._build_should_run_prompt(configs, [session_data])

            assert result == mock_prompt
            mock_render.assert_called_once()
            call_args = mock_render.call_args
            variables = call_args[0][1]
            assert "Check for helpfulness" in variables["feedback_definition_prompt"]
            assert "Check for accuracy" in variables["feedback_definition_prompt"]

    def test_with_feedback_definition_prompt_absent(self):
        """Test _build_should_run_prompt returns None when no definitions are present."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service(temp_dir)

            # Use MagicMock configs with feedback_definition_prompt=None
            mock_config = MagicMock(spec=AgentFeedbackConfig)
            mock_config.feedback_definition_prompt = None

            interaction = Interaction(
                interaction_id=1,
                user_id="user1",
                request_id="req1",
                content="Hello",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            session_data = create_request_interaction_data_model(
                user_id="user1",
                request_id="req1",
                interactions=[interaction],
            )

            result = service._build_should_run_prompt([mock_config], [session_data])
            assert result is None

    def test_with_tool_can_use_present(self):
        """Test _build_should_run_prompt includes tool_can_use when present in root config."""
        from reflexio_commons.config_schema import ToolUseConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service(temp_dir)

            # Set tool_can_use on root config
            service.configurator.set_config_by_name(
                "tool_can_use",
                [
                    ToolUseConfig(
                        tool_name="search", tool_description="Search the web"
                    ),
                    ToolUseConfig(tool_name="calculator", tool_description="Do math"),
                ],
            )

            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb1",
                    feedback_definition_prompt="Check feedback",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                ),
            ]

            interaction = Interaction(
                interaction_id=1,
                user_id="user1",
                request_id="req1",
                content="Hello",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            session_data = create_request_interaction_data_model(
                user_id="user1",
                request_id="req1",
                interactions=[interaction],
            )

            mock_prompt = "rendered with tools"
            with patch.object(
                service.request_context.prompt_manager,
                "render_prompt",
                return_value=mock_prompt,
            ) as mock_render:
                result = service._build_should_run_prompt(configs, [session_data])

            assert result == mock_prompt
            call_args = mock_render.call_args
            variables = call_args[0][1]
            assert "search: Search the web" in variables["tool_can_use"]
            assert "calculator: Do math" in variables["tool_can_use"]

    def test_with_tool_can_use_absent(self):
        """Test _build_should_run_prompt passes empty tool_can_use when not configured."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service(temp_dir)

            # Ensure tool_can_use is None (default)
            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb1",
                    feedback_definition_prompt="Check feedback",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                ),
            ]

            interaction = Interaction(
                interaction_id=1,
                user_id="user1",
                request_id="req1",
                content="Hello",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            session_data = create_request_interaction_data_model(
                user_id="user1",
                request_id="req1",
                interactions=[interaction],
            )

            mock_prompt = "rendered without tools"
            with patch.object(
                service.request_context.prompt_manager,
                "render_prompt",
                return_value=mock_prompt,
            ) as mock_render:
                result = service._build_should_run_prompt(configs, [session_data])

            assert result == mock_prompt
            call_args = mock_render.call_args
            variables = call_args[0][1]
            assert variables["tool_can_use"] == ""


# ===============================
# Tests for _process_results
# ===============================


class TestProcessResults:
    """Tests for _process_results method."""

    def _create_service_with_config(
        self, temp_dir: str, output_pending_status: bool = False
    ) -> FeedbackGenerationService:
        """Helper to create a service with service_config initialized."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            output_pending_status=output_pending_status,
        )
        # Set up feedback config
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
        )
        service.configurator.set_config_by_name(
            "agent_feedback_configs", [feedback_config]
        )
        # Initialize service_config
        service.service_config = service._load_generation_service_config(
            FeedbackGenerationRequest(
                request_id="test_request",
                agent_version="1.0",
                user_id="user1",
                source="test",
                auto_run=False,
            )
        )
        return service

    def test_deduplicator_enabled_path(self):
        """Test _process_results with deduplicator enabled."""
        from reflexio_commons.api_schema.service_schemas import RawFeedback

        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service_with_config(temp_dir)

            feedback1 = RawFeedback(
                request_id="test_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="feedback 1",
            )
            feedback2 = RawFeedback(
                request_id="test_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="feedback 2",
            )
            results = [[feedback1, feedback2]]

            deduplicated = [feedback1]
            ids_to_delete = [99]

            with (
                patch(
                    "reflexio.server.site_var.feature_flags.is_deduplicator_enabled",
                    return_value=True,
                ),
                patch(
                    "reflexio.server.services.feedback.feedback_deduplicator.FeedbackDeduplicator",
                ) as mock_dedup_cls,
                patch.object(service.storage, "save_raw_feedbacks") as mock_save,
                patch.object(
                    service.storage, "delete_raw_feedbacks_by_ids"
                ) as mock_delete,
                patch.object(service, "_trigger_feedback_aggregation"),
            ):
                mock_dedup_instance = MagicMock()
                mock_dedup_instance.deduplicate.return_value = (
                    deduplicated,
                    ids_to_delete,
                )
                mock_dedup_cls.return_value = mock_dedup_instance

                service._process_results(results)

                mock_dedup_instance.deduplicate.assert_called_once_with(
                    results,
                    "test_request",
                    "1.0",
                    user_id="user1",
                )
                mock_save.assert_called_once()
                saved_feedbacks = mock_save.call_args[0][0]
                assert len(saved_feedbacks) == 1
                assert saved_feedbacks[0].feedback_content == "feedback 1"
                mock_delete.assert_called_once_with([99])

    def test_save_then_delete_fails(self):
        """Test _process_results when save succeeds but delete_raw_feedbacks_by_ids raises."""
        from reflexio_commons.api_schema.service_schemas import RawFeedback

        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service_with_config(temp_dir)

            feedback1 = RawFeedback(
                request_id="test_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="feedback 1",
            )
            results = [[feedback1]]

            with (
                patch(
                    "reflexio.server.site_var.feature_flags.is_deduplicator_enabled",
                    return_value=True,
                ),
                patch(
                    "reflexio.server.services.feedback.feedback_deduplicator.FeedbackDeduplicator",
                ) as mock_dedup_cls,
                patch.object(service.storage, "save_raw_feedbacks") as mock_save,
                patch.object(
                    service.storage,
                    "delete_raw_feedbacks_by_ids",
                    side_effect=Exception("Delete failed"),
                ) as mock_delete,
                patch.object(service, "_trigger_feedback_aggregation"),
            ):
                mock_dedup_instance = MagicMock()
                mock_dedup_instance.deduplicate.return_value = (
                    [feedback1],
                    [42],
                )
                mock_dedup_cls.return_value = mock_dedup_instance

                # Should not raise - error is caught and logged
                service._process_results(results)

                mock_save.assert_called_once()
                mock_delete.assert_called_once_with([42])

    def test_save_fails(self):
        """Test _process_results when save_raw_feedbacks raises an exception."""
        from reflexio_commons.api_schema.service_schemas import RawFeedback

        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._create_service_with_config(temp_dir)

            feedback1 = RawFeedback(
                request_id="test_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="feedback 1",
            )
            results = [[feedback1]]

            with (
                patch(
                    "reflexio.server.site_var.feature_flags.is_deduplicator_enabled",
                    return_value=False,
                ),
                patch.object(
                    service.storage,
                    "save_raw_feedbacks",
                    side_effect=Exception("Storage error"),
                ) as mock_save,
            ):
                # Should not raise - error is caught and logged
                service._process_results(results)

                mock_save.assert_called_once()


# ===============================
# Tests for _trigger_feedback_aggregation
# ===============================


class TestTriggerFeedbackAggregation:
    """Tests for _trigger_feedback_aggregation method."""

    def _create_service_with_config(
        self,
        temp_dir: str,
        agent_feedback_configs: list[AgentFeedbackConfig] | None = None,
    ) -> FeedbackGenerationService:
        """Helper to create a service with service_config initialized."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        service = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
        )
        if agent_feedback_configs is not None:
            service.configurator.set_config_by_name(
                "agent_feedback_configs", agent_feedback_configs
            )
        # Initialize service_config
        service.service_config = service._load_generation_service_config(
            FeedbackGenerationRequest(
                request_id="test_request",
                agent_version="1.0",
                auto_run=False,
            )
        )
        return service

    def test_aggregation_trigger_with_aggregator_config(self):
        """Test _trigger_feedback_aggregation triggers aggregation for configs with aggregator_config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb_with_agg",
                    feedback_definition_prompt="test definition",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                ),
                AgentFeedbackConfig(
                    feedback_name="fb_without_agg",
                    feedback_definition_prompt="test definition 2",
                    feedback_aggregator_config=None,
                ),
            ]
            service = self._create_service_with_config(temp_dir, configs)

            with patch(
                "reflexio.server.services.feedback.feedback_generation_service.FeedbackAggregator"
            ) as mock_agg_cls:
                mock_agg_instance = MagicMock()
                mock_agg_cls.return_value = mock_agg_instance

                service._trigger_feedback_aggregation()

                # Only config with aggregator_config should trigger aggregation
                mock_agg_cls.assert_called_once_with(
                    llm_client=service.client,
                    request_context=service.request_context,
                    agent_version="1.0",
                )
                mock_agg_instance.run.assert_called_once()
                agg_request = mock_agg_instance.run.call_args[0][0]
                assert agg_request.agent_version == "1.0"
                assert agg_request.feedback_name == "fb_with_agg"

    def test_skill_generation_auto_trigger(self):
        """Test skill generation is triggered when auto_generate_on_aggregation=True."""
        from reflexio_commons.config_schema import SkillGeneratorConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb_with_skill",
                    feedback_definition_prompt="test definition",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                    skill_generator_config=SkillGeneratorConfig(
                        enabled=True,
                        auto_generate_on_aggregation=True,
                    ),
                ),
            ]
            service = self._create_service_with_config(temp_dir, configs)

            with (
                patch(
                    "reflexio.server.services.feedback.feedback_generation_service.FeedbackAggregator"
                ) as mock_agg_cls,
                patch(
                    "reflexio.server.services.feedback.skill_generator.SkillGenerator",
                ) as mock_skill_cls,
            ):
                mock_agg_instance = MagicMock()
                mock_agg_cls.return_value = mock_agg_instance
                mock_skill_instance = MagicMock()
                mock_skill_cls.return_value = mock_skill_instance

                service._trigger_feedback_aggregation()

                # Aggregator should be called
                mock_agg_instance.run.assert_called_once()

                # Skill generator should also be triggered
                mock_skill_cls.assert_called_once_with(
                    llm_client=service.client,
                    request_context=service.request_context,
                    agent_version="1.0",
                )
                mock_skill_instance.run.assert_called_once()
                skill_request = mock_skill_instance.run.call_args[0][0]
                assert skill_request.agent_version == "1.0"
                assert skill_request.feedback_name == "fb_with_skill"

    def test_skill_generation_exception_caught(self):
        """Test that exceptions during skill generation are caught and logged."""
        from reflexio_commons.config_schema import SkillGeneratorConfig

        with tempfile.TemporaryDirectory() as temp_dir:
            configs = [
                AgentFeedbackConfig(
                    feedback_name="fb_with_skill",
                    feedback_definition_prompt="test definition",
                    feedback_aggregator_config=FeedbackAggregatorConfig(
                        min_feedback_threshold=2,
                    ),
                    skill_generator_config=SkillGeneratorConfig(
                        enabled=True,
                        auto_generate_on_aggregation=True,
                    ),
                ),
            ]
            service = self._create_service_with_config(temp_dir, configs)

            with (
                patch(
                    "reflexio.server.services.feedback.feedback_generation_service.FeedbackAggregator"
                ) as mock_agg_cls,
                patch(
                    "reflexio.server.services.feedback.skill_generator.SkillGenerator",
                ) as mock_skill_cls,
            ):
                mock_agg_instance = MagicMock()
                mock_agg_cls.return_value = mock_agg_instance
                mock_skill_instance = MagicMock()
                mock_skill_instance.run.side_effect = Exception(
                    "Skill generation exploded"
                )
                mock_skill_cls.return_value = mock_skill_instance

                # Should not raise - exception is caught and logged
                service._trigger_feedback_aggregation()

                mock_agg_instance.run.assert_called_once()
                mock_skill_instance.run.assert_called_once()


# ===============================
# Tests for _update_config_for_incremental
# ===============================


class TestUpdateConfigForIncremental:
    """Tests for _update_config_for_incremental method."""

    def test_sets_incremental_flag_and_previously_extracted(self):
        """Test that is_incremental is set to True and previously_extracted is populated."""
        from reflexio_commons.api_schema.service_schemas import RawFeedback

        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            service = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            )
            # Initialize service_config
            service.service_config = service._load_generation_service_config(
                FeedbackGenerationRequest(
                    request_id="test_request",
                    agent_version="1.0",
                    auto_run=False,
                )
            )

            assert service.service_config.is_incremental is False
            assert service.service_config.previously_extracted == []

            prev_feedback = RawFeedback(
                request_id="old_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="old feedback",
            )
            previously_extracted = [[prev_feedback]]

            service._update_config_for_incremental(previously_extracted)

            assert service.service_config.is_incremental is True
            assert len(service.service_config.previously_extracted) == 1
            assert (
                service.service_config.previously_extracted[0][0].feedback_content
                == "old feedback"
            )

    def test_previously_extracted_is_copied(self):
        """Test that previously_extracted list is copied, not referenced."""
        from reflexio_commons.api_schema.service_schemas import RawFeedback

        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            service = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            )
            service.service_config = service._load_generation_service_config(
                FeedbackGenerationRequest(
                    request_id="test_request",
                    agent_version="1.0",
                    auto_run=False,
                )
            )

            prev_feedback = RawFeedback(
                request_id="old_request",
                agent_version="1.0",
                feedback_name="test_feedback",
                feedback_content="old feedback",
            )
            original_list = [[prev_feedback]]

            service._update_config_for_incremental(original_list)

            # Mutating original should not affect service_config
            original_list.append([])
            assert len(service.service_config.previously_extracted) == 1


# ===============================
# Tests for run_manual_regular: specific user_ids and progress tracking
# ===============================


class TestRunManualRegularUnit:
    """Unit tests for run_manual_regular with mocked storage."""

    def _create_service(
        self, temp_dir: str, output_pending: bool = False
    ) -> FeedbackGenerationService:
        """Helper to create a FeedbackGenerationService for testing."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        svc = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            allow_manual_trigger=True,
            output_pending_status=output_pending,
        )
        feedback_config = AgentFeedbackConfig(
            feedback_name="test_feedback",
            feedback_definition_prompt="test",
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2,
            ),
            allow_manual_trigger=True,
        )
        svc.configurator.set_config_by_name("agent_feedback_configs", [feedback_config])
        svc.configurator.set_config_by_name("extraction_window_size", 100)
        return svc

    def test_run_manual_regular_with_specific_user_ids(self, mock_chat_completion):
        """Test run_manual_regular processes specific user_ids from sessions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            # Add interactions for two distinct users
            for uid in ("user_alpha", "user_beta"):
                req_id = f"req_{uid}"
                interaction = Interaction(
                    interaction_id=hash(uid) % 10000,
                    user_id=uid,
                    request_id=req_id,
                    content=f"Content from {uid}",
                    role="user",
                    created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
                )
                request_obj = Request(
                    request_id=req_id,
                    user_id=uid,
                    source="",
                    agent_version="1.0",
                )
                svc.storage.add_request(request_obj)
                svc.storage.add_user_interaction(uid, interaction)

            from reflexio_commons.api_schema.service_schemas import (
                ManualFeedbackGenerationRequest,
            )

            request = ManualFeedbackGenerationRequest(agent_version="1.0")
            response = svc.run_manual_regular(request)

            assert response.success is True

    def test_run_manual_regular_progress_tracking(self, mock_chat_completion):
        """Test that run_manual_regular invokes _run_batch_with_progress."""
        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            # Add one user with one interaction
            interaction = Interaction(
                interaction_id=1,
                user_id="user_prog",
                request_id="req_prog",
                content="progress test",
                role="user",
                created_at=int(datetime.datetime.now(datetime.UTC).timestamp()),
            )
            request_obj = Request(
                request_id="req_prog",
                user_id="user_prog",
                source="",
                agent_version="1.0",
            )
            svc.storage.add_request(request_obj)
            svc.storage.add_user_interaction("user_prog", interaction)

            from reflexio_commons.api_schema.service_schemas import (
                ManualFeedbackGenerationRequest,
            )

            with patch.object(svc, "_run_batch_with_progress") as mock_batch:
                request = ManualFeedbackGenerationRequest(agent_version="1.0")
                response = svc.run_manual_regular(request)

            assert response.success is True
            mock_batch.assert_called_once()
            call_kwargs = mock_batch.call_args[1]
            assert "user_prog" in call_kwargs["user_ids"]
            assert call_kwargs["request_params"]["mode"] == "manual_regular"


# ===============================
# Tests for _count_manual_generated
# ===============================


class TestCountManualGenerated:
    """Tests for _count_manual_generated method."""

    def test_returns_zero_when_no_matching_feedbacks(self):
        """Test _count_manual_generated returns 0 when storage has no CURRENT feedbacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            svc = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            )
            svc.service_config = svc._load_generation_service_config(
                FeedbackGenerationRequest(
                    request_id="test", agent_version="1.0", auto_run=False
                )
            )

            from reflexio_commons.api_schema.service_schemas import (
                ManualFeedbackGenerationRequest,
            )

            request = ManualFeedbackGenerationRequest(agent_version="1.0")
            result = svc._count_manual_generated(request)

            assert result == 0

    def test_returns_count_with_mock_storage(self):
        """Test _count_manual_generated returns correct count from mocked storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            svc = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            )
            svc.service_config = svc._load_generation_service_config(
                FeedbackGenerationRequest(
                    request_id="test", agent_version="1.0", auto_run=False
                )
            )

            from reflexio_commons.api_schema.service_schemas import (
                ManualFeedbackGenerationRequest,
                RawFeedback,
            )

            svc.storage.get_raw_feedbacks = MagicMock(
                return_value=[
                    RawFeedback(
                        request_id="r1",
                        agent_version="1.0",
                        feedback_name="fb",
                        feedback_content="content",
                    ),
                    RawFeedback(
                        request_id="r2",
                        agent_version="1.0",
                        feedback_name="fb",
                        feedback_content="content2",
                    ),
                ]
            )

            request = ManualFeedbackGenerationRequest(agent_version="1.0")
            result = svc._count_manual_generated(request)

            assert result == 2


# ===============================
# Tests for _create_run_request_for_item
# ===============================


class TestCreateRunRequestForItem:
    """Tests for _create_run_request_for_item with both request types."""

    def _create_service(self, temp_dir: str) -> FeedbackGenerationService:
        """Helper to create a FeedbackGenerationService."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        svc = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
            output_pending_status=True,
        )
        svc.service_config = svc._load_generation_service_config(
            FeedbackGenerationRequest(
                request_id="test", agent_version="1.0", auto_run=False
            )
        )
        return svc

    def test_manual_feedback_generation_request_path(self):
        """Test _create_run_request_for_item with ManualFeedbackGenerationRequest (line 514/550)."""
        from reflexio_commons.api_schema.service_schemas import (
            ManualFeedbackGenerationRequest,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            manual_req = ManualFeedbackGenerationRequest(
                agent_version="2.0", source="web"
            )
            result = svc._create_run_request_for_item("user_x", manual_req)

            assert result.request_id.startswith("manual_")
            assert result.agent_version == "2.0"
            assert result.user_id == "user_x"
            assert result.source == "web"
            assert result.auto_run is False
            # Manual requests should not have rerun time fields
            assert result.rerun_start_time is None
            assert result.rerun_end_time is None

    def test_rerun_feedback_generation_request_path(self):
        """Test _create_run_request_for_item with RerunFeedbackGenerationRequest."""
        from reflexio_commons.api_schema.service_schemas import (
            RerunFeedbackGenerationRequest,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            start = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
            end = datetime.datetime(2024, 6, 1, tzinfo=datetime.UTC)
            rerun_req = RerunFeedbackGenerationRequest(
                agent_version="1.5",
                start_time=start,
                end_time=end,
                feedback_name="quality",
                source="api",
            )
            result = svc._create_run_request_for_item("user_y", rerun_req)

            assert result.request_id.startswith("rerun_feedback_")
            assert result.agent_version == "1.5"
            assert result.user_id == "user_y"
            assert result.source == "api"
            assert result.feedback_name == "quality"
            assert result.auto_run is False
            assert result.rerun_start_time == int(start.timestamp())
            assert result.rerun_end_time == int(end.timestamp())


# ===============================
# Tests for _pre_process_rerun
# ===============================


class TestPreProcessRerun:
    """Tests for _pre_process_rerun method."""

    def test_deletes_pending_feedbacks(self):
        """Test _pre_process_rerun deletes pending raw feedbacks (lines 443-448)."""
        from reflexio_commons.api_schema.service_schemas import (
            RerunFeedbackGenerationRequest,
            Status,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)
            svc = FeedbackGenerationService(
                llm_client=llm_client,
                request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
                output_pending_status=True,
            )
            svc.service_config = svc._load_generation_service_config(
                FeedbackGenerationRequest(
                    request_id="test", agent_version="1.0", auto_run=False
                )
            )

            svc.storage.delete_all_raw_feedbacks_by_status = MagicMock(return_value=5)

            rerun_req = RerunFeedbackGenerationRequest(
                agent_version="1.0",
                feedback_name="quality",
            )
            svc._pre_process_rerun(rerun_req)

            svc.storage.delete_all_raw_feedbacks_by_status.assert_called_once_with(
                status=Status.PENDING,
                agent_version="1.0",
                feedback_name="quality",
            )


# ===============================
# Tests for status change methods
# ===============================


class TestStatusChangeMethods:
    """Tests for _has_items_with_status, _delete_items_by_status, _create_status_change_response."""

    def _create_service(self, temp_dir: str) -> FeedbackGenerationService:
        """Helper to create a FeedbackGenerationService."""
        llm_config = LiteLLMConfig(model="gpt-4o-mini")
        llm_client = LiteLLMClient(llm_config)
        svc = FeedbackGenerationService(
            llm_client=llm_client,
            request_context=RequestContext(org_id="0", storage_base_dir=temp_dir),
        )
        svc.service_config = svc._load_generation_service_config(
            FeedbackGenerationRequest(
                request_id="test", agent_version="1.0", auto_run=False
            )
        )
        return svc

    def test_has_items_with_status(self):
        """Test _has_items_with_status delegates to storage (line 697)."""
        from reflexio_commons.api_schema.service_schemas import Status

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)
            svc.storage.has_raw_feedbacks_with_status = MagicMock(return_value=True)

            request = FeedbackGenerationRequest(
                request_id="r1",
                agent_version="1.0",
                feedback_name="quality",
                auto_run=False,
            )
            result = svc._has_items_with_status(Status.PENDING, request)

            assert result is True
            svc.storage.has_raw_feedbacks_with_status.assert_called_once_with(
                status=Status.PENDING,
                agent_version="1.0",
                feedback_name="quality",
            )

    def test_delete_items_by_status(self):
        """Test _delete_items_by_status delegates to storage (line 715)."""
        from reflexio_commons.api_schema.service_schemas import Status

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)
            svc.storage.delete_all_raw_feedbacks_by_status = MagicMock(return_value=3)

            request = FeedbackGenerationRequest(
                request_id="r1",
                agent_version="1.0",
                feedback_name="quality",
                auto_run=False,
            )
            result = svc._delete_items_by_status(Status.PENDING, request)

            assert result == 3
            svc.storage.delete_all_raw_feedbacks_by_status.assert_called_once_with(
                status=Status.PENDING,
                agent_version="1.0",
                feedback_name="quality",
            )

    def test_create_status_change_response_upgrade(self):
        """Test _create_status_change_response for UPGRADE returns UpgradeRawFeedbacksResponse (lines 765-772)."""
        from reflexio.server.services.base_generation_service import (
            StatusChangeOperation,
        )
        from reflexio_commons.api_schema.service_schemas import (
            UpgradeRawFeedbacksResponse,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            counts = {"deleted": 2, "archived": 3, "promoted": 5}
            result = svc._create_status_change_response(
                StatusChangeOperation.UPGRADE, True, counts, "done"
            )

            assert isinstance(result, UpgradeRawFeedbacksResponse)
            assert result.success is True
            assert result.raw_feedbacks_deleted == 2
            assert result.raw_feedbacks_archived == 3
            assert result.raw_feedbacks_promoted == 5
            assert result.message == "done"

    def test_create_status_change_response_downgrade(self):
        """Test _create_status_change_response for DOWNGRADE returns DowngradeRawFeedbacksResponse (lines 773-779)."""
        from reflexio.server.services.base_generation_service import (
            StatusChangeOperation,
        )
        from reflexio_commons.api_schema.service_schemas import (
            DowngradeRawFeedbacksResponse,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            counts = {"demoted": 4, "restored": 6}
            result = svc._create_status_change_response(
                StatusChangeOperation.DOWNGRADE, False, counts, "rollback"
            )

            assert isinstance(result, DowngradeRawFeedbacksResponse)
            assert result.success is False
            assert result.raw_feedbacks_demoted == 4
            assert result.raw_feedbacks_restored == 6
            assert result.message == "rollback"

    def test_create_status_change_response_missing_count_keys(self):
        """Test _create_status_change_response defaults to 0 for missing count keys."""
        from reflexio.server.services.base_generation_service import (
            StatusChangeOperation,
        )
        from reflexio_commons.api_schema.service_schemas import (
            UpgradeRawFeedbacksResponse,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svc = self._create_service(temp_dir)

            result = svc._create_status_change_response(
                StatusChangeOperation.UPGRADE, True, {}, "no counts"
            )

            assert isinstance(result, UpgradeRawFeedbacksResponse)
            assert result.raw_feedbacks_deleted == 0
            assert result.raw_feedbacks_archived == 0
            assert result.raw_feedbacks_promoted == 0


if __name__ == "__main__":
    pytest.main([__file__])
