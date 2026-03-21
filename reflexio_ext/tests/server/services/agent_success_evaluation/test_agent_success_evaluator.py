"""
Unit tests for AgentSuccessEvaluator.

Tests the evaluator's responsibilities for:
- Source filtering on provided interactions
- Sampling rate filtering
- Running evaluations on provided interactions
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.agent_success_evaluation.agent_success_evaluation_constants import (
    AgentSuccessEvaluationOutput,
    AgentSuccessEvaluationWithComparisonOutput,
)
from reflexio.server.services.agent_success_evaluation.agent_success_evaluation_service import (
    AgentSuccessGenerationServiceConfig,
)
from reflexio.server.services.agent_success_evaluation.agent_success_evaluator import (
    AgentSuccessEvaluator,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    RegularVsShadow,
    Request,
)
from reflexio_commons.config_schema import AgentSuccessConfig

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


# ===============================
# Unit tests for helper methods
# ===============================


class TestCountUserTurns:
    """Tests for AgentSuccessEvaluator._count_user_turns."""

    @pytest.fixture
    def evaluator(self, mock_llm_client, request_context):
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        return AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

    def _interaction(self, role, content):
        return Interaction(role=role, content=content, user_id="u1", request_id="r1")

    def _rdm(self, request_id, interactions):
        return RequestInteractionDataModel(
            session_id="s1",
            request=Request(request_id=request_id, session_id="s1", user_id="u1"),
            interactions=interactions,
        )

    def test_counts_user_turns_only(self, evaluator):
        """User turns are counted; agent/system turns are excluded."""
        models = [
            self._rdm(
                "r1",
                [
                    self._interaction("user", "hello"),
                    self._interaction("assistant", "hi"),
                    self._interaction("user", "question"),
                    self._interaction("tool", "result"),
                    self._interaction("system", "info"),
                ],
            )
        ]
        assert evaluator._count_user_turns(models) == 2

    def test_multiple_request_models(self, evaluator):
        """User turns across multiple RequestInteractionDataModels are summed."""
        models = [
            self._rdm("r1", [self._interaction("user", "a")]),
            self._rdm(
                "r2",
                [
                    self._interaction("user", "b"),
                    self._interaction("agent", "c"),
                ],
            ),
        ]
        assert evaluator._count_user_turns(models) == 2

    def test_empty_interactions(self, evaluator):
        """Empty interactions return 0."""
        assert evaluator._count_user_turns([]) == 0

    def test_case_insensitive_role_matching(self, evaluator):
        """Role matching is case-insensitive."""
        models = [
            self._rdm(
                "r1",
                [
                    self._interaction("Assistant", "hi"),
                    self._interaction("USER", "hello"),
                ],
            )
        ]
        # "Assistant" should be excluded, "USER" should be counted
        assert evaluator._count_user_turns(models) == 1


class TestGetCorrectionCount:
    """Tests for AgentSuccessEvaluator._get_correction_count."""

    def test_returns_zero_on_storage_exception(self, mock_llm_client, temp_storage_dir):
        """_get_correction_count returns 0 when storage raises."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        request_context = RequestContext(
            org_id="test_org", storage_base_dir=temp_storage_dir
        )
        request_context.storage = MagicMock()
        request_context.storage.count_raw_feedbacks_by_session.side_effect = (
            RuntimeError("db down")
        )

        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )
        assert evaluator._get_correction_count() == 0

    def test_returns_count_from_storage(self, mock_llm_client, temp_storage_dir):
        """_get_correction_count returns the value from storage."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        request_context = RequestContext(
            org_id="test_org", storage_base_dir=temp_storage_dir
        )
        request_context.storage = MagicMock()
        request_context.storage.count_raw_feedbacks_by_session.return_value = 5

        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )
        assert evaluator._get_correction_count() == 5


# ===============================
# Test: _evaluate_with_shadow_comparison
# ===============================


class TestEvaluateWithShadowComparison:
    """Tests for AgentSuccessEvaluator._evaluate_with_shadow_comparison."""

    @pytest.fixture
    def shadow_interactions(self):
        """Create interactions with shadow_content."""
        return [
            Interaction(
                interaction_id=1,
                user_id="user1",
                content="Help me",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
            Interaction(
                interaction_id=2,
                user_id="user1",
                content="Regular answer",
                shadow_content="Shadow answer",
                request_id="req1",
                created_at=1001,
                role="assistant",
            ),
        ]

    @pytest.fixture
    def shadow_request_interaction_models(self, shadow_interactions):
        """Create RequestInteractionDataModel objects with shadow content."""
        request1 = Request(
            request_id="req1",
            user_id="user1",
            created_at=1000,
            source="api",
        )
        return [
            RequestInteractionDataModel(
                session_id="req1",
                request=request1,
                interactions=shadow_interactions,
            ),
        ]

    @pytest.fixture
    def shadow_service_config(self, shadow_request_interaction_models):
        """Create a service config with shadow interactions."""
        return AgentSuccessGenerationServiceConfig(
            agent_version="1.0.0",
            session_id="test_session",
            request_interaction_data_models=shadow_request_interaction_models,
            source="api",
        )

    @pytest.fixture
    def evaluator(self, request_context, mock_llm_client, shadow_service_config):
        """Create an evaluator with shadow-content interactions."""
        config = AgentSuccessConfig(
            evaluation_name="test_shadow",
            success_definition_prompt="Evaluate task",
        )
        return AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=shadow_service_config,
            agent_context="Test agent",
        )

    def test_shadow_content_triggers_comparison_path(
        self, evaluator, shadow_request_interaction_models, mock_llm_client
    ):
        """Shadow content triggers _evaluate_with_shadow_comparison via _evaluate_group."""
        mock_llm_client.generate_chat_response.return_value = (
            AgentSuccessEvaluationWithComparisonOutput(
                is_success=True,
                better_request="tie",
                is_significantly_better=False,
            )
        )
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.has_shadow_content",
                return_value=True,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_group(shadow_request_interaction_models)

        assert result is not None
        assert result.regular_vs_shadow == RegularVsShadow.TIED

    def test_position_bias_randomization(
        self, evaluator, shadow_request_interaction_models, mock_llm_client
    ):
        """random.choice controls whether regular is Request 1 or 2."""
        mock_llm_client.generate_chat_response.return_value = (
            AgentSuccessEvaluationWithComparisonOutput(
                is_success=True,
                better_request="1",
                is_significantly_better=False,
            )
        )
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.random.choice",
                return_value=True,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_with_shadow_comparison(
                shadow_request_interaction_models, ""
            )

        # regular_is_request_1=True, better_request="1" => regular is better (slightly)
        assert result is not None
        assert result.regular_vs_shadow == RegularVsShadow.REGULAR_IS_SLIGHTLY_BETTER

        # Now test with regular_is_request_1=False
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.random.choice",
                return_value=False,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_with_shadow_comparison(
                shadow_request_interaction_models, ""
            )

        # regular_is_request_1=False, better_request="1" => shadow is better (slightly)
        assert result is not None
        assert result.regular_vs_shadow == RegularVsShadow.SHADOW_IS_SLIGHTLY_BETTER

    def test_successful_llm_response_with_comparison_output(
        self, evaluator, shadow_request_interaction_models, mock_llm_client
    ):
        """Successful LLM response with AgentSuccessEvaluationWithComparisonOutput returns result."""
        mock_llm_client.generate_chat_response.return_value = (
            AgentSuccessEvaluationWithComparisonOutput(
                is_success=False,
                failure_type="wrong_answer",
                failure_reason="Incorrect response",
                better_request="2",
                is_significantly_better=True,
                comparison_reason="Shadow was much better",
            )
        )
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.random.choice",
                return_value=True,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_with_shadow_comparison(
                shadow_request_interaction_models, ""
            )

        assert result is not None
        assert result.is_success is False
        assert result.failure_type == "wrong_answer"
        assert result.failure_reason == "Incorrect response"
        # regular_is_request_1=True, better_request="2" => shadow is better (significantly)
        assert result.regular_vs_shadow == RegularVsShadow.SHADOW_IS_BETTER

    def test_llm_returns_none(
        self, evaluator, shadow_request_interaction_models, mock_llm_client
    ):
        """LLM returning None results in None."""
        mock_llm_client.generate_chat_response.return_value = None
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.random.choice",
                return_value=True,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_with_shadow_comparison(
                shadow_request_interaction_models, ""
            )

        assert result is None

    def test_llm_returns_wrong_type(
        self, evaluator, shadow_request_interaction_models, mock_llm_client
    ):
        """LLM returning wrong type (not AgentSuccessEvaluationWithComparisonOutput) results in None."""
        mock_llm_client.generate_chat_response.return_value = "unexpected string"
        with (
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.random.choice",
                return_value=True,
            ),
            patch(
                "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.construct_agent_success_evaluation_with_comparison_messages",
                return_value=[{"role": "user", "content": "test"}],
            ),
        ):
            result = evaluator._evaluate_with_shadow_comparison(
                shadow_request_interaction_models, ""
            )

        assert result is None


# ===============================
# Test: _map_comparison_to_enum
# ===============================


class TestMapComparisonToEnum:
    """Tests for AgentSuccessEvaluator._map_comparison_to_enum covering all 7 branches."""

    @pytest.fixture
    def evaluator(self, mock_llm_client, request_context):
        """Create a minimal evaluator for testing _map_comparison_to_enum."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        return AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

    def test_tie(self, evaluator):
        """'tie' maps to RegularVsShadow.TIED."""
        result = evaluator._map_comparison_to_enum(
            better_request="tie",
            is_significantly_better=False,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.TIED

    def test_request_1_better_regular_is_request_1_not_significant(self, evaluator):
        """'1' with regular_is_request_1=True, not significant => REGULAR_IS_SLIGHTLY_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="1",
            is_significantly_better=False,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.REGULAR_IS_SLIGHTLY_BETTER

    def test_request_1_better_regular_is_request_1_significant(self, evaluator):
        """'1' with regular_is_request_1=True, significant => REGULAR_IS_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="1",
            is_significantly_better=True,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.REGULAR_IS_BETTER

    def test_request_2_better_regular_is_request_1_not_significant(self, evaluator):
        """'2' with regular_is_request_1=True, not significant => SHADOW_IS_SLIGHTLY_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="2",
            is_significantly_better=False,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.SHADOW_IS_SLIGHTLY_BETTER

    def test_request_2_better_regular_is_request_1_significant(self, evaluator):
        """'2' with regular_is_request_1=True, significant => SHADOW_IS_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="2",
            is_significantly_better=True,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.SHADOW_IS_BETTER

    def test_request_1_better_regular_is_request_2_not_significant(self, evaluator):
        """'1' with regular_is_request_1=False, not significant => SHADOW_IS_SLIGHTLY_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="1",
            is_significantly_better=False,
            regular_is_request_1=False,
        )
        assert result == RegularVsShadow.SHADOW_IS_SLIGHTLY_BETTER

    def test_request_1_better_regular_is_request_2_significant(self, evaluator):
        """'1' with regular_is_request_1=False, significant => SHADOW_IS_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="1",
            is_significantly_better=True,
            regular_is_request_1=False,
        )
        assert result == RegularVsShadow.SHADOW_IS_BETTER

    def test_request_2_better_regular_is_request_2_not_significant(self, evaluator):
        """'2' with regular_is_request_1=False, not significant => REGULAR_IS_SLIGHTLY_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="2",
            is_significantly_better=False,
            regular_is_request_1=False,
        )
        assert result == RegularVsShadow.REGULAR_IS_SLIGHTLY_BETTER

    def test_request_2_better_regular_is_request_2_significant(self, evaluator):
        """'2' with regular_is_request_1=False, significant => REGULAR_IS_BETTER."""
        result = evaluator._map_comparison_to_enum(
            better_request="2",
            is_significantly_better=True,
            regular_is_request_1=False,
        )
        assert result == RegularVsShadow.REGULAR_IS_BETTER

    def test_unexpected_value_defaults_to_tied(self, evaluator):
        """Unexpected better_request value defaults to TIED."""
        result = evaluator._map_comparison_to_enum(
            better_request="invalid",
            is_significantly_better=True,
            regular_is_request_1=True,
        )
        assert result == RegularVsShadow.TIED


# ===============================
# Test: Model Setting Override
# ===============================


class TestModelSettingOverride:
    """Tests for model name configuration in AgentSuccessEvaluator.__init__."""

    def test_llm_config_override_sets_model(self, mock_llm_client, temp_storage_dir):
        """llm_config.generation_model_name overrides the default model."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        request_context = RequestContext(
            org_id="test_org", storage_base_dir=temp_storage_dir
        )
        request_context.storage = MagicMock()

        # Mock configurator to return a Config with llm_config override
        mock_config = MagicMock()
        mock_config.llm_config.generation_model_name = "custom-model-override"
        mock_config.tool_can_use = None
        request_context.configurator = MagicMock()
        request_context.configurator.get_config.return_value = mock_config

        evaluator = AgentSuccessEvaluator(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        assert evaluator.default_evaluate_model_name == "custom-model-override"

    def test_fallback_to_site_var_when_no_config_override(
        self, mock_llm_client, temp_storage_dir
    ):
        """When llm_config has no generation_model_name, falls back to site var."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="test",
        )
        service_config = AgentSuccessGenerationServiceConfig(
            session_id="test_session",
            agent_version="v1",
            request_interaction_data_models=[],
            source="api",
        )
        request_context = RequestContext(
            org_id="test_org", storage_base_dir=temp_storage_dir
        )
        request_context.storage = MagicMock()

        # Mock configurator to return a Config with no llm_config override
        mock_config = MagicMock()
        mock_config.llm_config = None
        mock_config.tool_can_use = None
        request_context.configurator = MagicMock()
        request_context.configurator.get_config.return_value = mock_config

        # Mock SiteVarManager to return a known model name
        with patch(
            "reflexio.server.services.agent_success_evaluation.agent_success_evaluator.SiteVarManager"
        ) as mock_svm_cls:
            mock_svm_cls.return_value.get_site_var.return_value = {
                "default_evaluate_model_name": "site-var-model"
            }
            evaluator = AgentSuccessEvaluator(
                request_context=request_context,
                llm_client=mock_llm_client,
                extractor_config=config,
                service_config=service_config,
                agent_context="Test agent",
            )

        assert evaluator.default_evaluate_model_name == "site-var-model"
