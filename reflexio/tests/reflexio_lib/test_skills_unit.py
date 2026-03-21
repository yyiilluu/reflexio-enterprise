"""Unit tests for SkillsMixin.

Tests get_skills, search_skills, update_skill_status, delete_skill,
and export_skills with mocked storage.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.retriever_schema import SearchSkillsRequest
from reflexio_commons.api_schema.service_schemas import Skill, SkillStatus

from reflexio.reflexio_lib._skills import SkillsMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin(*, storage_configured: bool = True) -> SkillsMixin:
    """Create a SkillsMixin instance with mocked internals."""
    mixin = object.__new__(SkillsMixin)
    mock_storage = MagicMock()

    mock_request_context = MagicMock()
    mock_request_context.org_id = "test_org"
    mock_request_context.storage = mock_storage if storage_configured else None
    mock_request_context.is_storage_configured.return_value = storage_configured

    mixin.request_context = mock_request_context
    mixin.llm_client = MagicMock()
    return mixin


def _get_storage(mixin: SkillsMixin) -> MagicMock:
    return mixin.request_context.storage


def _sample_skill(**overrides) -> Skill:
    defaults = {
        "skill_id": 1,
        "skill_name": "test_skill",
        "description": "A test skill",
        "agent_version": "v1",
        "feedback_name": "fb1",
    }
    defaults.update(overrides)
    return Skill(**defaults)


# ---------------------------------------------------------------------------
# get_skills
# ---------------------------------------------------------------------------


class TestGetSkills:
    def test_returns_skills(self):
        """Successful retrieval returns skills from storage."""
        mixin = _make_mixin()
        sample = _sample_skill()
        _get_storage(mixin).get_skills.return_value = [sample]

        result = mixin.get_skills(limit=10)

        assert len(result) == 1
        assert result[0].skill_name == "test_skill"
        _get_storage(mixin).get_skills.assert_called_once_with(
            limit=10,
            feedback_name=None,
            agent_version=None,
            skill_status=None,
        )

    def test_with_filters(self):
        """Passes filter parameters to storage."""
        mixin = _make_mixin()
        _get_storage(mixin).get_skills.return_value = []

        mixin.get_skills(
            feedback_name="fb1",
            agent_version="v2",
            skill_status=SkillStatus.PUBLISHED,
        )

        _get_storage(mixin).get_skills.assert_called_once_with(
            limit=100,
            feedback_name="fb1",
            agent_version="v2",
            skill_status=SkillStatus.PUBLISHED,
        )

    def test_storage_not_configured(self):
        """Raises ValueError when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        try:
            mixin.get_skills()
            msg = "Expected ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Storage not configured" in str(e)


# ---------------------------------------------------------------------------
# search_skills
# ---------------------------------------------------------------------------


class TestSearchSkills:
    def test_query_delegation(self):
        """Delegates search to storage."""
        mixin = _make_mixin()
        sample = _sample_skill()
        _get_storage(mixin).search_skills.return_value = [sample]

        request = SearchSkillsRequest(query="test")
        result = mixin.search_skills(request)

        assert len(result) == 1
        _get_storage(mixin).search_skills.assert_called_once()

    def test_storage_not_configured(self):
        """Raises ValueError when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = SearchSkillsRequest(query="test")
        try:
            mixin.search_skills(request)
            msg = "Expected ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Storage not configured" in str(e)


# ---------------------------------------------------------------------------
# update_skill_status
# ---------------------------------------------------------------------------


class TestUpdateSkillStatus:
    def test_update_status(self):
        """Updates a skill's status via storage."""
        mixin = _make_mixin()

        mixin.update_skill_status(skill_id=1, skill_status=SkillStatus.PUBLISHED)

        _get_storage(mixin).update_skill_status.assert_called_once_with(
            1, SkillStatus.PUBLISHED
        )

    def test_storage_not_configured(self):
        """Raises ValueError when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        try:
            mixin.update_skill_status(skill_id=1, skill_status=SkillStatus.PUBLISHED)
            msg = "Expected ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Storage not configured" in str(e)


# ---------------------------------------------------------------------------
# delete_skill
# ---------------------------------------------------------------------------


class TestDeleteSkill:
    def test_delete_by_id(self):
        """Deletes a skill by ID."""
        mixin = _make_mixin()

        mixin.delete_skill(skill_id=42)

        _get_storage(mixin).delete_skill.assert_called_once_with(42)

    def test_storage_not_configured(self):
        """Raises ValueError when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        try:
            mixin.delete_skill(skill_id=42)
            msg = "Expected ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Storage not configured" in str(e)


# ---------------------------------------------------------------------------
# export_skills
# ---------------------------------------------------------------------------


class TestExportSkills:
    @patch(
        "reflexio.server.services.feedback.skill_generator.render_skills_markdown",
        return_value="# Skills\n- test_skill",
    )
    def test_export_returns_markdown(self, mock_render):
        """Export skills returns rendered markdown."""
        mixin = _make_mixin()
        sample = _sample_skill()
        _get_storage(mixin).get_skills.return_value = [sample]

        result = mixin.export_skills(feedback_name="fb1")

        assert "Skills" in result
        mock_render.assert_called_once_with([sample])

    def test_storage_not_configured(self):
        """Raises ValueError when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        try:
            mixin.export_skills()
            msg = "Expected ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Storage not configured" in str(e)
