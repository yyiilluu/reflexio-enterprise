from __future__ import annotations

from reflexio_commons.api_schema.retriever_schema import SearchSkillsRequest
from reflexio_commons.api_schema.service_schemas import Skill, SkillStatus

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG, ReflexioBase


class SkillsMixin(ReflexioBase):
    def get_skills(
        self,
        limit: int = 100,
        feedback_name: str | None = None,
        agent_version: str | None = None,
        skill_status: SkillStatus | None = None,
    ) -> list[Skill]:
        """Get skills from storage."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        return self._get_storage().get_skills(
            limit=limit,
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
        )

    def search_skills(self, request: SearchSkillsRequest) -> list[Skill]:
        """Search skills with hybrid search."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        rewritten = self._rewrite_query(request.query)
        if rewritten:
            request = request.model_copy(update={"query": rewritten})
        return self._get_storage().search_skills(request)

    def update_skill_status(self, skill_id: int, skill_status: SkillStatus) -> None:
        """Update skill status."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        self._get_storage().update_skill_status(skill_id, skill_status)

    def delete_skill(self, skill_id: int) -> None:
        """Delete a skill by ID."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        self._get_storage().delete_skill(skill_id)

    def export_skills(
        self,
        feedback_name: str | None = None,
        agent_version: str | None = None,
        skill_status: SkillStatus | None = None,
    ) -> str:
        """Export skills as markdown."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        from reflexio.server.services.feedback.skill_generator import (
            render_skills_markdown,
        )

        skills = self._get_storage().get_skills(
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
        )
        return render_skills_markdown(skills)
