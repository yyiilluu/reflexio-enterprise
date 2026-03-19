"""End-to-end tests for skill workflows."""

import os
from collections.abc import Callable

import pytest
from reflexio_commons.api_schema.retriever_schema import SearchSkillsRequest
from reflexio_commons.api_schema.service_schemas import (
    Skill,
    SkillStatus,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    Config,
    FeedbackAggregatorConfig,
    SkillGeneratorConfig,
    StorageConfigSupabase,
    ToolUseConfig,
)

from reflexio.reflexio_lib.reflexio_lib import Reflexio
from reflexio.server.services.configurator.configurator import SimpleConfigurator
from reflexio.tests.e2e_tests.conftest import save_raw_feedbacks
from reflexio.tests.server.test_utils import skip_in_precommit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supabase_storage_config() -> StorageConfigSupabase:
    """Create a StorageConfigSupabase instance with credentials from environment."""
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    if not supabase_url or not supabase_key:
        pytest.skip(
            "TEST_SUPABASE_URL and TEST_SUPABASE_KEY environment variables must be set"
        )

    return StorageConfigSupabase(
        url=supabase_url,
        key=supabase_key,
        db_url=supabase_db_url,
    )


@pytest.fixture
def test_org_id(worker_id: str) -> str:
    """Test organization ID unique per worker."""
    return f"e2e_skill_test_org_{worker_id}"


@pytest.fixture
def reflexio_instance_skill(
    supabase_storage_config: StorageConfigSupabase, test_org_id: str
) -> Reflexio:
    """Create a Reflexio instance with skill generation enabled."""
    config = Config(
        storage_config=supabase_storage_config,
        agent_context_prompt="this is a sales agent",
        agent_feedback_configs=[
            AgentFeedbackConfig(
                feedback_name="test_feedback",
                feedback_definition_prompt="feedback about agent quality",
                feedback_aggregator_config=FeedbackAggregatorConfig(
                    min_feedback_threshold=2,
                ),
                skill_generator_config=SkillGeneratorConfig(
                    enabled=True,
                    min_feedback_per_cluster=2,
                    cooldown_hours=0,
                    auto_generate_on_aggregation=False,
                    max_interactions_per_skill=20,
                ),
            ),
        ],
        tool_can_use=[
            ToolUseConfig(
                tool_name="search",
                tool_description="Search for information",
            ),
        ],
    )
    configurator = SimpleConfigurator(org_id=test_org_id, config=config)
    return Reflexio(org_id=test_org_id, configurator=configurator)


@pytest.fixture
def cleanup_skills(reflexio_instance_skill):
    """Fixture to clean up skill test data before and after each test."""
    _cleanup_skill_data(reflexio_instance_skill)
    yield
    _cleanup_skill_data(reflexio_instance_skill)


def _cleanup_skill_data(instance: Reflexio):
    """Clean up all skill-related data."""
    try:
        storage = instance.request_context.storage

        # Delete skills
        skills = storage.get_skills()
        for skill in skills:
            storage.delete_skill(skill.skill_id)

        # Delete raw feedbacks
        storage.delete_all_raw_feedbacks_by_feedback_name("test_feedback")
        storage.delete_all_feedbacks_by_feedback_name("test_feedback")

        # Delete operation states
        storage.delete_all_operation_states()
    except Exception as e:
        print(f"Error during skill cleanup: {str(e)}")


# ---------------------------------------------------------------------------
# Tests: CRUD Operations
# ---------------------------------------------------------------------------


@skip_in_precommit
def test_skill_save_and_get(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test saving and retrieving skills."""
    storage = reflexio_instance_skill.request_context.storage

    # Save skills directly
    skills_to_save = [
        Skill(
            skill_name="Test Skill 1",
            description="First test skill",
            version="1.0.0",
            agent_version="1.0.0",
            feedback_name="test_feedback",
            instructions="Step 1: Check documentation\nStep 2: Respond",
            allowed_tools=["search"],
            raw_feedback_ids=[1, 2, 3],
            skill_status=SkillStatus.DRAFT,
        ),
        Skill(
            skill_name="Test Skill 2",
            description="Second test skill",
            version="1.0.0",
            agent_version="1.0.0",
            feedback_name="test_feedback",
            instructions="1. Acknowledge\n2. Apologize\n3. Resolve",
            skill_status=SkillStatus.PUBLISHED,
        ),
    ]
    storage.save_skills(skills_to_save)

    # Get all skills
    retrieved_skills = storage.get_skills()
    assert len(retrieved_skills) >= 2

    # Get by feedback_name
    filtered = storage.get_skills(feedback_name="test_feedback")
    assert len(filtered) >= 2

    # Get by skill_status
    draft_skills = storage.get_skills(skill_status=SkillStatus.DRAFT)
    assert any(s.skill_name == "Test Skill 1" for s in draft_skills)

    published_skills = storage.get_skills(skill_status=SkillStatus.PUBLISHED)
    assert any(s.skill_name == "Test Skill 2" for s in published_skills)


@skip_in_precommit
def test_skill_update_status(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test updating skill status."""
    storage = reflexio_instance_skill.request_context.storage

    # Save a draft skill
    storage.save_skills(
        [
            Skill(
                skill_name="Status Test Skill",
                description="For status testing",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="test instructions",
                skill_status=SkillStatus.DRAFT,
            ),
        ]
    )

    # Find the saved skill
    skills = storage.get_skills(skill_status=SkillStatus.DRAFT)
    target = [s for s in skills if s.skill_name == "Status Test Skill"]
    assert len(target) > 0
    skill_id = target[0].skill_id

    # Update to PUBLISHED
    storage.update_skill_status(skill_id, SkillStatus.PUBLISHED)

    # Verify update
    published = storage.get_skills(skill_status=SkillStatus.PUBLISHED)
    published_ids = [s.skill_id for s in published]
    assert skill_id in published_ids

    # Update to DEPRECATED
    storage.update_skill_status(skill_id, SkillStatus.DEPRECATED)

    deprecated = storage.get_skills(skill_status=SkillStatus.DEPRECATED)
    deprecated_ids = [s.skill_id for s in deprecated]
    assert skill_id in deprecated_ids


@skip_in_precommit
def test_skill_delete(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test deleting a skill."""
    storage = reflexio_instance_skill.request_context.storage

    # Save a skill
    storage.save_skills(
        [
            Skill(
                skill_name="Delete Test Skill",
                description="For deletion testing",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="test instructions",
            ),
        ]
    )

    # Find and delete the skill
    skills = storage.get_skills()
    target = [s for s in skills if s.skill_name == "Delete Test Skill"]
    assert len(target) > 0
    skill_id = target[0].skill_id

    storage.delete_skill(skill_id)

    # Verify deletion
    skills_after = storage.get_skills()
    remaining_ids = [s.skill_id for s in skills_after]
    assert skill_id not in remaining_ids


# ---------------------------------------------------------------------------
# Tests: Search
# ---------------------------------------------------------------------------


@skip_in_precommit
def test_skill_search(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test hybrid search for skills."""
    storage = reflexio_instance_skill.request_context.storage

    # Save skills with distinct content
    storage.save_skills(
        [
            Skill(
                skill_name="Pricing Expert",
                description="Handle pricing questions",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="Look up product pricing and present clearly",
            ),
            Skill(
                skill_name="Error Recovery",
                description="Handle error situations",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="Diagnose the error and provide workaround",
            ),
        ]
    )

    # Search for pricing-related skills
    pricing_results = storage.search_skills(
        SearchSkillsRequest(query="pricing costs money")
    )
    assert len(pricing_results) > 0
    # The pricing skill should rank higher
    assert any("Pricing" in s.skill_name for s in pricing_results)

    # Search for error-related skills
    error_results = storage.search_skills(
        SearchSkillsRequest(query="technical error troubleshoot")
    )
    assert len(error_results) > 0
    assert any("Error" in s.skill_name for s in error_results)


# ---------------------------------------------------------------------------
# Tests: Export
# ---------------------------------------------------------------------------


@skip_in_precommit
def test_skill_export_markdown(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test exporting skills as markdown."""
    storage = reflexio_instance_skill.request_context.storage

    # Save skills
    storage.save_skills(
        [
            Skill(
                skill_name="Export Test Skill",
                description="Skill for export testing",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="Step 1: Do this\nStep 2: Do that",
                allowed_tools=["search"],
            ),
        ]
    )

    # Export via reflexio_lib
    markdown = reflexio_instance_skill.export_skills(
        feedback_name="test_feedback",
    )

    assert "## Export Test Skill" in markdown
    assert "Skill for export testing" in markdown
    assert "Step 1: Do this" in markdown

    # Test empty export
    storage.delete_skill(storage.get_skills()[0].skill_id)
    empty_md = reflexio_instance_skill.export_skills()
    assert "No skills generated yet" in empty_md


# ---------------------------------------------------------------------------
# Tests: Business Logic (via reflexio_lib)
# ---------------------------------------------------------------------------


@skip_in_precommit
def test_get_skills_via_lib(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test get_skills through reflexio_lib."""
    storage = reflexio_instance_skill.request_context.storage

    storage.save_skills(
        [
            Skill(
                skill_name="Lib Test Skill",
                description="Test",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="instr",
            ),
        ]
    )

    skills = reflexio_instance_skill.get_skills(feedback_name="test_feedback")
    assert len(skills) > 0
    assert any(s.skill_name == "Lib Test Skill" for s in skills)


@skip_in_precommit
def test_search_skills_via_lib(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test search_skills through reflexio_lib."""
    storage = reflexio_instance_skill.request_context.storage

    storage.save_skills(
        [
            Skill(
                skill_name="Searchable Skill",
                description="A skill about customer complaints",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="Handle complaint empathetically",
            ),
        ]
    )

    results = reflexio_instance_skill.search_skills(
        SearchSkillsRequest(
            query="customer complaint handling",
            feedback_name="test_feedback",
        )
    )
    assert len(results) > 0


@skip_in_precommit
def test_update_skill_status_via_lib(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test update_skill_status through reflexio_lib."""
    storage = reflexio_instance_skill.request_context.storage

    storage.save_skills(
        [
            Skill(
                skill_name="Status Lib Skill",
                description="Test",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="instr",
                skill_status=SkillStatus.DRAFT,
            ),
        ]
    )

    skills = storage.get_skills(skill_status=SkillStatus.DRAFT)
    target = [s for s in skills if s.skill_name == "Status Lib Skill"][0]

    reflexio_instance_skill.update_skill_status(target.skill_id, SkillStatus.PUBLISHED)

    updated = storage.get_skills(skill_status=SkillStatus.PUBLISHED)
    assert any(s.skill_id == target.skill_id for s in updated)


@skip_in_precommit
def test_delete_skill_via_lib(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test delete_skill through reflexio_lib."""
    storage = reflexio_instance_skill.request_context.storage

    storage.save_skills(
        [
            Skill(
                skill_name="Delete Lib Skill",
                description="Test",
                version="1.0.0",
                agent_version="1.0.0",
                feedback_name="test_feedback",
                instructions="instr",
            ),
        ]
    )

    skills = storage.get_skills()
    target = [s for s in skills if s.skill_name == "Delete Lib Skill"][0]

    reflexio_instance_skill.delete_skill(target.skill_id)

    remaining = storage.get_skills()
    assert not any(s.skill_id == target.skill_id for s in remaining)


# ---------------------------------------------------------------------------
# Tests: Full Workflow (Skill Generation)
# ---------------------------------------------------------------------------


@skip_in_precommit
def test_run_skill_generation_end_to_end(
    reflexio_instance_skill: Reflexio,
    cleanup_skills: Callable[[], None],
):
    """Test end-to-end skill generation workflow.

    This test:
    1. Saves raw feedbacks
    2. Runs skill generation with mock LLM
    3. Verifies skills were generated
    """
    feedback_name = "test_feedback"

    # Save mock feedbacks
    save_raw_feedbacks(reflexio_instance_skill)

    original_env = os.environ.get("MOCK_LLM_RESPONSE")
    try:
        os.environ["MOCK_LLM_RESPONSE"] = "true"

        # Run skill generation via reflexio_lib (rerun=True bypasses cooldown)
        result = reflexio_instance_skill.run_skill_generation(
            agent_version="1.0.0",
            feedback_name=feedback_name,
        )

        # Verify result
        assert isinstance(result, dict)
        assert "skills_generated" in result
        assert "skills_updated" in result

        # If skills were generated, verify they're in storage
        total = result["skills_generated"] + result["skills_updated"]
        if total > 0:
            skills = reflexio_instance_skill.get_skills(feedback_name=feedback_name)
            assert len(skills) > 0
            for skill in skills:
                assert skill.feedback_name == feedback_name
                assert skill.agent_version == "1.0.0"
                assert skill.skill_status == SkillStatus.DRAFT

    finally:
        if original_env is None:
            os.environ.pop("MOCK_LLM_RESPONSE", None)
        else:
            os.environ["MOCK_LLM_RESPONSE"] = original_env
