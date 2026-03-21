"""Unit tests for the SkillGenerator service."""

import time
from unittest.mock import MagicMock, patch

import pytest
from reflexio_commons.api_schema.service_schemas import (
    BlockingIssue,
    BlockingIssueKind,
    RawFeedback,
    Skill,
    SkillStatus,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    Config,
    FeedbackAggregatorConfig,
    SkillGeneratorConfig,
    StorageConfigLocal,
    ToolUseConfig,
)

from reflexio.server.services.feedback.feedback_service_utils import (
    SkillGenerationOutput,
    SkillGeneratorRequest,
)
from reflexio.server.services.feedback.skill_generator import (
    SkillGenerator,
    render_skills_markdown,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.config = MagicMock()
    client.config.model = "test-model"
    return client


@pytest.fixture
def mock_config():
    """Create a Config with skill generator enabled."""
    return Config(
        storage_config=StorageConfigLocal(dir_path="/tmp/test_skill_gen"),  # noqa: S108
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="test_feedback",
                feedback_definition_prompt="Test feedback",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=2,
                ),
                skill_generator_config=SkillGeneratorConfig(
                    enabled=True,
                    min_feedback_per_cluster=2,
                    cooldown_hours=24,
                    auto_generate_on_aggregation=False,
                    max_interactions_per_skill=20,
                ),
            ),
        ],
        tool_can_use=[
            ToolUseConfig(tool_name="search", tool_description="Search the web"),
        ],
    )


@pytest.fixture
def request_context(mock_config):
    """Create a request context with mocked storage and configurator."""
    context = MagicMock()
    context.org_id = "test_org"
    context.storage = MagicMock()
    context.configurator = MagicMock()
    context.configurator.get_config.return_value = mock_config
    context.prompt_manager = MagicMock()
    context.prompt_manager.render_prompt.return_value = "rendered prompt"
    return context


@pytest.fixture
def skill_generator(mock_llm_client, request_context):
    """Create a SkillGenerator instance with mocked dependencies."""
    return SkillGenerator(
        llm_client=mock_llm_client,
        request_context=request_context,
        agent_version="1.0.0",
    )


@pytest.fixture
def sample_raw_feedbacks():
    """Create sample raw feedbacks for clustering."""
    return [
        RawFeedback(
            raw_feedback_id=i,
            agent_version="1.0.0",
            request_id=f"req_{i}",
            feedback_name="test_feedback",
            feedback_content=f"Feedback content {i}",
            when_condition="user asks about pricing",
            do_action="provide detailed pricing table",
            do_not_action="don't give vague answers",
        )
        for i in range(5)
    ]


@pytest.fixture
def sample_skill():
    """Create a sample Skill for update tests."""
    return Skill(
        skill_id=1,
        skill_name="Pricing Inquiry Handler",
        description="Handle pricing-related questions",
        version="1.0.0",
        agent_version="1.0.0",
        feedback_name="test_feedback",
        instructions="1. Check product catalog\n2. Present pricing table",
        allowed_tools=["search"],
        raw_feedback_ids=[1, 2, 3],
        skill_status=SkillStatus.DRAFT,
    )


@pytest.fixture
def mock_skill_generation_output():
    """Create a mock SkillGenerationOutput."""
    return SkillGenerationOutput(
        skill_name="Error Handling Skill",
        description="Handle errors gracefully",
        instructions="1. Acknowledge the error\n2. Provide solution",
        allowed_tools=["search"],
    )


# ---------------------------------------------------------------------------
# Tests: Config & State Management
# ---------------------------------------------------------------------------


class TestSkillGeneratorConfig:
    """Tests for configuration lookup."""

    def test_get_skill_generator_config_found(self, skill_generator):
        """Test that config is found for matching feedback_name."""
        config = skill_generator._get_skill_generator_config("test_feedback")
        assert config is not None
        assert config.enabled is True
        assert config.min_feedback_per_cluster == 2

    def test_get_skill_generator_config_not_found(self, skill_generator):
        """Test that None is returned for non-matching feedback_name."""
        config = skill_generator._get_skill_generator_config("nonexistent")
        assert config is None

    def test_get_skill_generator_config_no_configs(self, skill_generator):
        """Test when no agent_feedback_configs exist."""
        mock_config = MagicMock()
        mock_config.agent_feedback_configs = None
        skill_generator.configurator.get_config.return_value = mock_config
        config = skill_generator._get_skill_generator_config("test_feedback")
        assert config is None

    def test_get_feedback_aggregator_config(self, skill_generator):
        """Test feedback aggregator config lookup."""
        config = skill_generator._get_feedback_aggregator_config("test_feedback")
        assert config is not None
        assert config.min_feedback_threshold == 2

    def test_get_feedback_aggregator_config_not_found(self, skill_generator):
        """Test feedback aggregator config for non-matching name."""
        config = skill_generator._get_feedback_aggregator_config("nonexistent")
        assert config is None


class TestShouldRunGeneration:
    """Tests for the _should_run_generation decision logic."""

    def test_rerun_always_returns_true(self, skill_generator):
        """Test that rerun=True bypasses all checks."""
        config = SkillGeneratorConfig(enabled=False)
        assert (
            skill_generator._should_run_generation("test_feedback", config, rerun=True)
            is True
        )

    def test_disabled_config_returns_false(self, skill_generator):
        """Test that disabled config skips generation."""
        config = SkillGeneratorConfig(enabled=False)
        assert (
            skill_generator._should_run_generation("test_feedback", config, rerun=False)
            is False
        )

    def test_cooldown_not_elapsed(self, skill_generator):
        """Test that generation is skipped when cooldown hasn't elapsed."""
        config = SkillGeneratorConfig(enabled=True, cooldown_hours=24)

        # Mock the state manager to return a recent timestamp
        mock_mgr = MagicMock()
        mock_mgr.get_aggregator_bookmark.return_value = (
            int(time.time()) - 3600
        )  # 1 hour ago
        skill_generator._create_state_manager = MagicMock(return_value=mock_mgr)

        assert (
            skill_generator._should_run_generation("test_feedback", config, rerun=False)
            is False
        )

    def test_cooldown_elapsed(self, skill_generator):
        """Test that generation runs when cooldown has elapsed."""
        config = SkillGeneratorConfig(enabled=True, cooldown_hours=24)

        # Mock the state manager to return a timestamp from 25 hours ago
        mock_mgr = MagicMock()
        mock_mgr.get_aggregator_bookmark.return_value = (
            int(time.time()) - 90000
        )  # 25 hours ago
        skill_generator._create_state_manager = MagicMock(return_value=mock_mgr)

        assert (
            skill_generator._should_run_generation("test_feedback", config, rerun=False)
            is True
        )

    def test_no_previous_run(self, skill_generator):
        """Test that generation runs when there's no previous run."""
        config = SkillGeneratorConfig(enabled=True, cooldown_hours=24)

        mock_mgr = MagicMock()
        mock_mgr.get_aggregator_bookmark.return_value = None
        skill_generator._create_state_manager = MagicMock(return_value=mock_mgr)

        assert (
            skill_generator._should_run_generation("test_feedback", config, rerun=False)
            is True
        )


# ---------------------------------------------------------------------------
# Tests: Prompt Formatting
# ---------------------------------------------------------------------------


class TestFormatClusterForPrompt:
    """Tests for _format_cluster_for_prompt."""

    def test_formats_all_sections(self, skill_generator):
        """Test formatting with do, don't, when, and blocking issues."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content1",
                when_condition="user asks about pricing",
                do_action="show pricing table",
                do_not_action="give vague answers",
                blocking_issue=BlockingIssue(
                    kind=BlockingIssueKind.PERMISSION_DENIED,
                    details="No admin access",
                ),
            ),
        ]

        result = skill_generator._format_cluster_for_prompt(feedbacks)

        assert "WHEN conditions:" in result
        assert "user asks about pricing" in result
        assert "DO actions:" in result
        assert "show pricing table" in result
        assert "DON'T actions:" in result
        assert "give vague answers" in result
        assert "BLOCKED BY issues:" in result
        assert "[permission_denied] No admin access" in result

    def test_formats_partial_feedback(self, skill_generator):
        """Test formatting when some fields are missing."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content1",
                when_condition="user is confused",
                do_action="explain clearly",
            ),
        ]

        result = skill_generator._format_cluster_for_prompt(feedbacks)

        assert "WHEN conditions:" in result
        assert "DO actions:" in result
        assert "DON'T" not in result
        assert "BLOCKED BY" not in result

    def test_formats_empty_feedbacks(self, skill_generator):
        """Test formatting with empty feedback list."""
        result = skill_generator._format_cluster_for_prompt([])
        assert result == ""

    def test_aggregates_multiple_feedbacks(self, skill_generator):
        """Test that multiple feedbacks are aggregated together."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="c1",
                when_condition="condition A",
                do_action="action A",
            ),
            RawFeedback(
                agent_version="1.0",
                request_id="req2",
                feedback_name="test",
                feedback_content="c2",
                when_condition="condition B",
                do_action="action B",
            ),
        ]

        result = skill_generator._format_cluster_for_prompt(feedbacks)

        assert "condition A" in result
        assert "condition B" in result
        assert "action A" in result
        assert "action B" in result


class TestGetToolCanUseStr:
    """Tests for _get_tool_can_use_str."""

    def test_formats_tools(self, skill_generator):
        """Test formatting of available tools."""
        result = skill_generator._get_tool_can_use_str()
        assert "search: Search the web" in result

    def test_no_tools(self, skill_generator):
        """Test when no tools are configured."""
        mock_config = MagicMock()
        mock_config.tool_can_use = None
        skill_generator.configurator.get_config.return_value = mock_config
        result = skill_generator._get_tool_can_use_str()
        assert "(No tools configured)" in result


# ---------------------------------------------------------------------------
# Tests: Interaction Context Collection
# ---------------------------------------------------------------------------


class TestCollectInteractionContext:
    """Tests for _collect_interaction_context."""

    def test_no_request_ids(self, skill_generator):
        """Test with feedbacks that have no request_ids."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="",
                feedback_name="test",
                feedback_content="content",
            ),
        ]
        result = skill_generator._collect_interaction_context(feedbacks, 20)
        assert "(No interaction context available)" in result

    def test_no_interactions_found(self, skill_generator):
        """Test when storage returns no interactions."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="content",
            ),
        ]
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        result = skill_generator._collect_interaction_context(feedbacks, 20)
        assert "(No interaction context available)" in result

    def test_deduplicates_request_ids(self, skill_generator):
        """Test that duplicate request_ids are deduplicated."""
        feedbacks = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="c1",
            ),
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="c2",
            ),
        ]
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator._collect_interaction_context(feedbacks, 20)

        call_args = skill_generator.storage.get_interactions_by_request_ids.call_args[
            0
        ][0]
        assert call_args == ["req1"]


# ---------------------------------------------------------------------------
# Tests: Skill Generation
# ---------------------------------------------------------------------------


class TestGenerateNewSkill:
    """Tests for _generate_new_skill."""

    def test_generates_skill_from_llm_output(
        self, skill_generator, sample_raw_feedbacks, mock_skill_generation_output
    ):
        """Test that a skill is generated from LLM output."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        skill = skill_generator._generate_new_skill(
            sample_raw_feedbacks,
            "interaction context",
            "tools",
            "existing skills",
        )

        assert skill is not None
        assert skill.skill_name == "Error Handling Skill"
        assert skill.description == "Handle errors gracefully"
        assert skill.instructions == "1. Acknowledge the error\n2. Provide solution"
        assert skill.allowed_tools == ["search"]
        assert skill.agent_version == "1.0.0"
        assert skill.feedback_name == "test_feedback"
        assert skill.skill_status == SkillStatus.DRAFT
        assert skill.raw_feedback_ids == [0, 1, 2, 3, 4]

    def test_returns_none_when_llm_returns_none(
        self, skill_generator, sample_raw_feedbacks
    ):
        """Test that None is returned when LLM returns None."""
        skill_generator.client.generate_chat_response.return_value = None

        skill = skill_generator._generate_new_skill(
            sample_raw_feedbacks,
            "interaction context",
            "tools",
            "existing skills",
        )

        assert skill is None

    def test_returns_none_on_exception(self, skill_generator, sample_raw_feedbacks):
        """Test that None is returned on LLM exception."""
        skill_generator.client.generate_chat_response.side_effect = Exception(
            "LLM error"
        )

        skill = skill_generator._generate_new_skill(
            sample_raw_feedbacks,
            "interaction context",
            "tools",
            "existing skills",
        )

        assert skill is None

    def test_uses_correct_prompt(
        self, skill_generator, sample_raw_feedbacks, mock_skill_generation_output
    ):
        """Test that the correct prompt is rendered."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        skill_generator._generate_new_skill(
            sample_raw_feedbacks,
            "interaction ctx",
            "available tools str",
            "existing skills str",
        )

        render_call = skill_generator.request_context.prompt_manager.render_prompt
        render_call.assert_called_once()
        prompt_vars = render_call.call_args[0][1]
        assert "interaction ctx" in prompt_vars["interaction_context"]
        assert "available tools str" in prompt_vars["available_tools"]
        assert "existing skills str" in prompt_vars["existing_skills"]


class TestUpdateExistingSkill:
    """Tests for _update_existing_skill."""

    def test_updates_skill_with_version_bump(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test skill update with version bump."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "interaction context",
            "tools",
        )

        assert updated is not None
        assert updated.version == "1.1.0"
        assert updated.skill_id == 1
        assert updated.feedback_name == "test_feedback"
        assert updated.skill_status == SkillStatus.DRAFT

    def test_merges_raw_feedback_ids(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test that raw_feedback_ids are merged."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "interaction context",
            "tools",
        )

        assert updated is not None
        # Original: [1,2,3], New: [0,1,2,3,4] -> merged set
        merged = set(updated.raw_feedback_ids)
        assert {0, 1, 2, 3, 4}.issubset(merged)

    def test_version_bump_incremental(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test version bump from 1.5.0 to 1.6.0."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )
        sample_skill.version = "1.5.0"

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "ctx",
            "tools",
        )

        assert updated.version == "1.6.0"

    def test_returns_none_on_exception(
        self, skill_generator, sample_skill, sample_raw_feedbacks
    ):
        """Test that None is returned on LLM exception."""
        skill_generator.client.generate_chat_response.side_effect = Exception("fail")

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "ctx",
            "tools",
        )

        assert updated is None


# ---------------------------------------------------------------------------
# Tests: Main Run Method
# ---------------------------------------------------------------------------


class TestSkillGeneratorRun:
    """Tests for the main run() method."""

    def test_returns_zero_when_no_raw_feedbacks(self, skill_generator):
        """Test that run returns zeros when no raw feedbacks exist."""
        skill_generator.storage.get_raw_feedbacks.return_value = []

        request = SkillGeneratorRequest(
            agent_version="1.0.0",
            feedback_name="test_feedback",
            rerun=True,
        )
        result = skill_generator.run(request)

        assert result["skills_generated"] == 0
        assert result["skills_updated"] == 0

    def test_returns_zero_when_cooldown_not_elapsed(self, skill_generator):
        """Test that run returns zeros when cooldown hasn't elapsed."""
        mock_mgr = MagicMock()
        mock_mgr.get_aggregator_bookmark.return_value = int(time.time())  # just now
        skill_generator._create_state_manager = MagicMock(return_value=mock_mgr)

        request = SkillGeneratorRequest(
            agent_version="1.0.0",
            feedback_name="test_feedback",
            rerun=False,
        )
        result = skill_generator.run(request)

        assert result["skills_generated"] == 0
        assert result["skills_updated"] == 0

    def test_skips_clusters_below_min_size(
        self, skill_generator, mock_skill_generation_output
    ):
        """Test that clusters below min_feedback_per_cluster are filtered out."""
        # Create feedbacks with different embeddings to form separate clusters
        feedbacks = [
            RawFeedback(
                raw_feedback_id=1,
                agent_version="1.0.0",
                request_id="req_1",
                feedback_name="test_feedback",
                feedback_content="Solo feedback",
                when_condition="solo condition",
            ),
        ]
        skill_generator.storage.get_raw_feedbacks.return_value = feedbacks
        skill_generator.storage.get_skills.return_value = []

        # Mock clustering to return a single cluster with 1 feedback (below min of 2)
        with patch.object(skill_generator, "_generate_new_skill") as mock_gen:  # noqa: SIM117
            with patch(
                "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
            ) as MockAgg:  # noqa: N806
                mock_agg_instance = MagicMock()
                mock_agg_instance.get_clusters.return_value = {0: feedbacks}
                MockAgg.return_value = mock_agg_instance

                request = SkillGeneratorRequest(
                    agent_version="1.0.0",
                    feedback_name="test_feedback",
                    rerun=True,
                )
                result = skill_generator.run(request)

                mock_gen.assert_not_called()
                assert result["skills_generated"] == 0

    def test_generates_new_skills(
        self, skill_generator, sample_raw_feedbacks, mock_skill_generation_output
    ):
        """Test that new skills are generated for valid clusters."""
        skill_generator.storage.get_raw_feedbacks.return_value = sample_raw_feedbacks
        skill_generator.storage.get_skills.return_value = []
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        # Mock clustering to return one cluster with all feedbacks
        with patch(
            "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
        ) as MockAgg:  # noqa: N806
            mock_agg_instance = MagicMock()
            mock_agg_instance.get_clusters.return_value = {0: sample_raw_feedbacks}
            MockAgg.return_value = mock_agg_instance

            request = SkillGeneratorRequest(
                agent_version="1.0.0",
                feedback_name="test_feedback",
                rerun=True,
            )
            result = skill_generator.run(request)

            assert result["skills_generated"] == 1
            assert result["skills_updated"] == 0
            skill_generator.storage.save_skills.assert_called_once()

    def test_updates_existing_skills(
        self,
        skill_generator,
        sample_raw_feedbacks,
        sample_skill,
        mock_skill_generation_output,
    ):
        """Test that existing skills are updated when a match is found."""
        skill_generator.storage.get_raw_feedbacks.return_value = sample_raw_feedbacks
        skill_generator.storage.get_skills.return_value = [sample_skill]
        skill_generator.storage.search_skills.return_value = [sample_skill]
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        with patch(
            "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
        ) as MockAgg:  # noqa: N806
            mock_agg_instance = MagicMock()
            mock_agg_instance.get_clusters.return_value = {0: sample_raw_feedbacks}
            MockAgg.return_value = mock_agg_instance

            request = SkillGeneratorRequest(
                agent_version="1.0.0",
                feedback_name="test_feedback",
                rerun=True,
            )
            result = skill_generator.run(request)

            assert result["skills_generated"] == 0
            assert result["skills_updated"] == 1
            skill_generator.storage.save_skills.assert_called_once()

    def test_updates_operation_state_after_run(
        self, skill_generator, sample_raw_feedbacks, mock_skill_generation_output
    ):
        """Test that operation state is updated after a successful run."""
        skill_generator.storage.get_raw_feedbacks.return_value = sample_raw_feedbacks
        skill_generator.storage.get_skills.return_value = []
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        mock_mgr = MagicMock()
        skill_generator._create_state_manager = MagicMock(return_value=mock_mgr)

        with patch(
            "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
        ) as MockAgg:  # noqa: N806
            mock_agg_instance = MagicMock()
            mock_agg_instance.get_clusters.return_value = {0: sample_raw_feedbacks}
            MockAgg.return_value = mock_agg_instance

            request = SkillGeneratorRequest(
                agent_version="1.0.0",
                feedback_name="test_feedback",
                rerun=True,
            )
            skill_generator.run(request)

            mock_mgr.update_aggregator_bookmark.assert_called_once()

    def test_search_skills_failure_falls_back_to_new_generation(
        self,
        skill_generator,
        sample_raw_feedbacks,
        sample_skill,
        mock_skill_generation_output,
    ):
        """Test that search failure falls back to generating a new skill."""
        skill_generator.storage.get_raw_feedbacks.return_value = sample_raw_feedbacks
        skill_generator.storage.get_skills.return_value = [sample_skill]
        skill_generator.storage.search_skills.side_effect = Exception("Search failed")
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        with patch(
            "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
        ) as MockAgg:  # noqa: N806
            mock_agg_instance = MagicMock()
            mock_agg_instance.get_clusters.return_value = {0: sample_raw_feedbacks}
            MockAgg.return_value = mock_agg_instance

            request = SkillGeneratorRequest(
                agent_version="1.0.0",
                feedback_name="test_feedback",
                rerun=True,
            )
            result = skill_generator.run(request)

            # Should fall back to generating new skill since search failed
            assert result["skills_generated"] == 1
            assert result["skills_updated"] == 0


# ---------------------------------------------------------------------------
# Tests: Markdown Rendering
# ---------------------------------------------------------------------------


class TestRenderSkillsMarkdown:
    """Tests for render_skills_markdown."""

    def test_empty_skills(self):
        """Test rendering with no skills."""
        result = render_skills_markdown([])
        assert "No skills generated yet" in result

    def test_renders_skill_sections(self, sample_skill):
        """Test that all skill sections are rendered."""
        result = render_skills_markdown([sample_skill])

        assert "## Pricing Inquiry Handler" in result
        assert "**Description:** Handle pricing-related questions" in result
        assert "**Description:** Handle pricing-related questions" in result
        assert "**Version:** 1.0.0" in result
        assert "### Instructions" in result
        assert "Check product catalog" in result
        assert "### Tools" in result
        assert "search" in result

    def test_renders_multiple_skills(self, sample_skill):
        """Test rendering multiple skills."""
        skill2 = Skill(
            skill_name="Error Handler",
            description="Handle errors",
            instructions="Fix it",
            agent_version="1.0.0",
            feedback_name="test",
        )
        result = render_skills_markdown([sample_skill, skill2])

        assert "## Pricing Inquiry Handler" in result
        assert "## Error Handler" in result

    def test_omits_empty_sections(self):
        """Test that empty sections are not rendered."""
        skill = Skill(
            skill_name="Minimal Skill",
            description="desc",
            instructions="",
            agent_version="1.0",
            feedback_name="test",
        )
        result = render_skills_markdown([skill])

        assert "## Minimal Skill" in result
        assert "### Instructions" not in result
        assert "### Do" not in result
        assert "### Don't" not in result
        assert "### Tools" not in result
        assert "### Examples" not in result


# ---------------------------------------------------------------------------
# Tests: OperationStateManager Key
# ---------------------------------------------------------------------------


class TestOperationStateManager:
    """Tests for OperationStateManager creation."""

    def test_creates_state_manager_with_correct_service_name(self, skill_generator):
        """Test that state manager uses 'skill_generator' service name."""
        mgr = skill_generator._create_state_manager()
        assert mgr.service_name == "skill_generator"
        assert mgr.org_id == "test_org"


# ---------------------------------------------------------------------------
# Tests: Config None Fallback & Non-standard Version
# ---------------------------------------------------------------------------


class TestSkillConfigNoneFallback:
    """Tests for skill_config is None fallback in run()."""

    def test_run_uses_default_config_when_skill_config_is_none(self, skill_generator):
        """Test that run() creates a default SkillGeneratorConfig when config is None."""
        # Override configurator to return no agent_feedback_configs
        mock_config = MagicMock()
        mock_config.agent_feedback_configs = None
        mock_config.tool_can_use = None
        skill_generator.configurator.get_config.return_value = mock_config
        skill_generator.storage.get_raw_feedbacks.return_value = []

        request = SkillGeneratorRequest(
            agent_version="1.0.0",
            feedback_name="unknown_feedback",
            rerun=True,
        )
        result = skill_generator.run(request)

        # Should still return a valid result (zero counts since no feedbacks)
        assert result["skills_generated"] == 0
        assert result["skills_updated"] == 0

    def test_run_default_config_values_are_applied(
        self, skill_generator, sample_raw_feedbacks, mock_skill_generation_output
    ):
        """Test that the default SkillGeneratorConfig values are used when config lookup returns None."""
        # Override configurator so _get_skill_generator_config returns None
        mock_config = MagicMock()
        mock_config.agent_feedback_configs = None
        mock_config.tool_can_use = None
        skill_generator.configurator.get_config.return_value = mock_config
        skill_generator.storage.get_raw_feedbacks.return_value = sample_raw_feedbacks
        skill_generator.storage.get_skills.return_value = []
        skill_generator.storage.get_interactions_by_request_ids.return_value = []
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )

        default_config = SkillGeneratorConfig()

        with patch(
            "reflexio.server.services.feedback.skill_generator.FeedbackAggregator"
        ) as MockAgg:  # noqa: N806
            mock_agg_instance = MagicMock()
            # Cluster size exceeds default min_feedback_per_cluster
            mock_agg_instance.get_clusters.return_value = {0: sample_raw_feedbacks}
            MockAgg.return_value = mock_agg_instance

            request = SkillGeneratorRequest(
                agent_version="1.0.0",
                feedback_name="unknown_feedback",
                rerun=True,
            )
            skill_generator.run(request)

            # Verify FeedbackAggregator was called with a default aggregator config
            # whose min_feedback_threshold matches default min_feedback_per_cluster
            agg_call_args = mock_agg_instance.get_clusters.call_args
            aggregator_config_arg = agg_call_args[0][1]
            assert (
                aggregator_config_arg.min_feedback_threshold
                == default_config.min_feedback_per_cluster
            )


class TestVersionNonStandardFormat:
    """Tests for _update_existing_skill with non-standard version strings."""

    def test_non_standard_version_kept_unchanged(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test that a version with != 3 parts is kept unchanged."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )
        sample_skill.version = "2.0"

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "ctx",
            "tools",
        )

        assert updated is not None
        assert updated.version == "2.0"

    def test_single_part_version_kept_unchanged(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test that a single-part version string is kept unchanged."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )
        sample_skill.version = "5"

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "ctx",
            "tools",
        )

        assert updated is not None
        assert updated.version == "5"

    def test_four_part_version_kept_unchanged(
        self,
        skill_generator,
        sample_skill,
        sample_raw_feedbacks,
        mock_skill_generation_output,
    ):
        """Test that a four-part version string is kept unchanged."""
        skill_generator.client.generate_chat_response.return_value = (
            mock_skill_generation_output
        )
        sample_skill.version = "1.2.3.4"

        updated = skill_generator._update_existing_skill(
            sample_skill,
            sample_raw_feedbacks,
            "ctx",
            "tools",
        )

        assert updated is not None
        assert updated.version == "1.2.3.4"
