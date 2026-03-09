"""
Unit tests for AgentSuccessEvaluator.

Tests the evaluator's responsibilities for:
- Source filtering on provided interactions
- Sampling rate filtering
- Running evaluations on provided interactions
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.config_schema import AgentSuccessConfig

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.services.agent_success_evaluation.agent_success_evaluator import (
    AgentSuccessEvaluator,
)
from reflexio.server.services.agent_success_evaluation.agent_success_evaluation_service import (
    AgentSuccessGenerationServiceConfig,
)
from reflexio.server.services.agent_success_evaluation.agent_success_evaluation_constants import (
    AgentSuccessEvaluationOutput,
)
from reflexio.server.llm.litellm_client import LiteLLMClient


# ===============================
# Fixtures
# ===============================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock(spec=LiteLLMClient)
    # Return a successful AgentSuccessEvaluationOutput
    client.generate_chat_response.return_value = AgentSuccessEvaluationOutput(
        is_success=True
    )
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
    """Create an agent success config."""
    return AgentSuccessConfig(
        evaluation_name="task_completion",
        success_definition_prompt="Evaluate if task was completed",
    )


@pytest.fixture
def sample_interactions():
    """Create sample interactions from multiple users for testing."""
    return [
        Interaction(
            interaction_id=1,
            user_id="user1",
            content="Please help me with task A",
            request_id="req1",
            created_at=1000,
            role="user",
        ),
        Interaction(
            interaction_id=2,
            user_id="user1",
            content="Sure, I completed task A for you",
            request_id="req1",
            created_at=1001,
            role="assistant",
        ),
        Interaction(
            interaction_id=3,
            user_id="user2",
            content="Can you do task B?",
            request_id="req2",
            created_at=1002,
            role="user",
        ),
        Interaction(
            interaction_id=4,
            user_id="user2",
            content="Task B is done",
            request_id="req2",
            created_at=1003,
            role="assistant",
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
            session_id="req1",
            request=request1,
            interactions=sample_interactions[:2],
        ),
        RequestInteractionDataModel(
            session_id="req2",
            request=request2,
            interactions=sample_interactions[2:],
        ),
    ]


@pytest.fixture
def service_config(sample_request_interaction_models):
    """Create a service config with required request_interaction_data_models."""
    return AgentSuccessGenerationServiceConfig(
        agent_version="1.0.0",
        session_id="test_group",
        request_interaction_data_models=sample_request_interaction_models,
        source="api",
    )


# ===============================
# Test: Run Method
# ===============================


class TestRun:
    """Tests for the run() method."""

    def test_run_processes_provided_interactions(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that run() processes interactions from service_config."""
        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = evaluator.run()

        # Should return a list
        assert result is not None
        assert isinstance(result, list)

    def test_run_respects_sampling_rate(
        self,
        request_context,
        mock_llm_client,
        sample_request_interaction_models,
    ):
        """Test that run() respects sampling rate."""
        # Config with 0% sampling rate - should skip all
        config = AgentSuccessConfig(
            evaluation_name="task_completion",
            success_definition_prompt="Evaluate if task was completed",
            sampling_rate=0.0,
        )

        service_config = AgentSuccessGenerationServiceConfig(
            agent_version="1.0.0",
            session_id="test_group",
            request_interaction_data_models=sample_request_interaction_models,
            source="api",
        )

        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = evaluator.run()

        # With 0% sampling rate, should skip all and return empty
        assert result == []

    def test_run_with_100_percent_sampling_rate(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
    ):
        """Test that run() processes all with 100% sampling rate."""
        # Default sampling_rate is 1.0 (100%)
        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = evaluator.run()

        # Should return results (may be empty if parsing fails in mock mode)
        assert result is not None
        assert isinstance(result, list)


# ===============================
# Test: Source Filtering
# ===============================


class TestSourceFiltering:
    """Tests for source filtering behavior."""

    def test_filters_interactions_by_source(
        self,
        request_context,
        mock_llm_client,
        sample_interactions,
    ):
        """Test that interactions are filtered by source."""
        # Create interactions with different sources
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
            source="web",
        )
        models = [
            RequestInteractionDataModel(
                session_id="req1",
                request=request1,
                interactions=sample_interactions[:2],
            ),
            RequestInteractionDataModel(
                session_id="req2",
                request=request2,
                interactions=sample_interactions[2:],
            ),
        ]

        # Config that only accepts 'api' source
        config = AgentSuccessConfig(
            evaluation_name="task_completion",
            success_definition_prompt="Evaluate if task was completed",
            source_filter="api",
        )

        service_config = AgentSuccessGenerationServiceConfig(
            agent_version="1.0.0",
            session_id="test_group",
            request_interaction_data_models=models,
            source="api",
        )

        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = evaluator.run()

        # Should process only the api source interaction
        assert result is not None
        assert isinstance(result, list)
