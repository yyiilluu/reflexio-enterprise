from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from reflexio_commons.api_schema.retriever_schema import SearchSkillsRequest
from reflexio_commons.api_schema.service_schemas import Skill, SkillStatus

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG

# ==============================
# get_skills tests
# ==============================


def test_get_skills_storage_not_configured(reflexio_no_storage):
    with pytest.raises(ValueError, match=STORAGE_NOT_CONFIGURED_MSG):
        reflexio_no_storage.get_skills()


def test_get_skills_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    skills = [Skill(skill_name="skill_1"), Skill(skill_name="skill_2")]
    storage.get_skills.return_value = skills

    result = reflexio_mock.get_skills()

    assert result == skills
    storage.get_skills.assert_called_once_with(
        limit=100,
        feedback_name=None,
        agent_version=None,
        skill_status=None,
    )


def test_get_skills_with_filters(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    skills = [Skill(skill_name="filtered_skill")]
    storage.get_skills.return_value = skills

    result = reflexio_mock.get_skills(
        limit=50,
        feedback_name="my_feedback",
        agent_version="v2",
        skill_status=SkillStatus.PUBLISHED,
    )

    assert result == skills
    storage.get_skills.assert_called_once_with(
        limit=50,
        feedback_name="my_feedback",
        agent_version="v2",
        skill_status=SkillStatus.PUBLISHED,
    )


# ==============================
# search_skills tests
# ==============================


def test_search_skills_storage_not_configured(reflexio_no_storage):
    with pytest.raises(ValueError, match=STORAGE_NOT_CONFIGURED_MSG):
        reflexio_no_storage.search_skills(SearchSkillsRequest(query="test query"))


def test_search_skills_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    skills = [Skill(skill_name="found_skill")]
    storage.search_skills.return_value = skills
    reflexio_mock._rewrite_query = MagicMock(return_value=None)

    request = SearchSkillsRequest(query="test query")
    result = reflexio_mock.search_skills(request)

    assert result == skills
    reflexio_mock._rewrite_query.assert_called_once_with("test query")
    storage.search_skills.assert_called_once_with(request)


def test_search_skills_query_rewrite_disabled_by_default(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    skills = [Skill(skill_name="original_query_skill")]
    storage.search_skills.return_value = skills
    reflexio_mock._rewrite_query = MagicMock(return_value=None)

    request = SearchSkillsRequest(query="test query")
    result = reflexio_mock.search_skills(request)

    assert result == skills
    reflexio_mock._rewrite_query.assert_called_once_with("test query")
    passed_request = storage.search_skills.call_args[0][0]
    assert passed_request.query == "test query"


# ==============================
# update_skill_status tests
# ==============================


def test_update_skill_status_storage_not_configured(reflexio_no_storage):
    with pytest.raises(ValueError, match=STORAGE_NOT_CONFIGURED_MSG):
        reflexio_no_storage.update_skill_status(1, SkillStatus.PUBLISHED)


def test_update_skill_status_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage

    reflexio_mock.update_skill_status(42, SkillStatus.DEPRECATED)

    storage.update_skill_status.assert_called_once_with(42, SkillStatus.DEPRECATED)


# ==============================
# delete_skill tests
# ==============================


def test_delete_skill_storage_not_configured(reflexio_no_storage):
    with pytest.raises(ValueError, match=STORAGE_NOT_CONFIGURED_MSG):
        reflexio_no_storage.delete_skill(1)


def test_delete_skill_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage

    reflexio_mock.delete_skill(99)

    storage.delete_skill.assert_called_once_with(99)


# ==============================
# export_skills tests
# ==============================


def test_export_skills_storage_not_configured(reflexio_no_storage):
    with pytest.raises(ValueError, match=STORAGE_NOT_CONFIGURED_MSG):
        reflexio_no_storage.export_skills()


@patch("reflexio.server.services.feedback.skill_generator.render_skills_markdown")
def test_export_skills_success(mock_render, reflexio_mock):
    storage = reflexio_mock.request_context.storage
    skills = [Skill(skill_name="exportable_skill")]
    storage.get_skills.return_value = skills
    mock_render.return_value = "# Skills\n- exportable_skill"

    result = reflexio_mock.export_skills(
        feedback_name="fb", agent_version="v1", skill_status=SkillStatus.PUBLISHED
    )

    assert result == "# Skills\n- exportable_skill"
    storage.get_skills.assert_called_once_with(
        feedback_name="fb",
        agent_version="v1",
        skill_status=SkillStatus.PUBLISHED,
    )
    mock_render.assert_called_once_with(skills)
