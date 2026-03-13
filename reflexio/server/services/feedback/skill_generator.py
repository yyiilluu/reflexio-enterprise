import logging
import time

from reflexio_commons.api_schema.service_schemas import (
    RawFeedback,
    Skill,
    SkillStatus,
)
from reflexio_commons.config_schema import (
    FeedbackAggregatorConfig,
    SkillGeneratorConfig,
)

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_constants import (
    FeedbackServiceConstants,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    SkillGenerationOutput,
    SkillGeneratorRequest,
)
from reflexio.server.services.operation_state_utils import OperationStateManager
from reflexio.server.services.service_utils import (
    format_interactions_to_history_string,
    format_messages_for_logging,
    log_model_response,
)

logger = logging.getLogger(__name__)


class SkillGenerator:
    def __init__(
        self,
        llm_client: LiteLLMClient,
        request_context: RequestContext,
        agent_version: str,
    ) -> None:
        self.client = llm_client
        self.storage = request_context.storage
        self.configurator = request_context.configurator
        self.request_context = request_context
        self.agent_version = agent_version

    def _create_state_manager(self) -> OperationStateManager:
        """
        Create an OperationStateManager for the skill generator.

        Returns:
            OperationStateManager configured for skill_generator
        """
        return OperationStateManager(
            self.storage,  # type: ignore[reportArgumentType]
            self.request_context.org_id,
            "skill_generator",
        )

    def _get_skill_generator_config(
        self, feedback_name: str
    ) -> SkillGeneratorConfig | None:
        """
        Get the skill generator config for a given feedback name.

        Args:
            feedback_name: Name of the feedback type

        Returns:
            SkillGeneratorConfig or None if not found
        """
        agent_feedback_configs = self.configurator.get_config().agent_feedback_configs
        if not agent_feedback_configs:
            return None
        for config in agent_feedback_configs:
            if config.feedback_name == feedback_name:
                return config.skill_generator_config
        return None

    def _get_feedback_aggregator_config(
        self, feedback_name: str
    ) -> FeedbackAggregatorConfig | None:
        """
        Get the feedback aggregator config for a given feedback name.

        Args:
            feedback_name: Name of the feedback type

        Returns:
            FeedbackAggregatorConfig or None if not found
        """
        agent_feedback_configs = self.configurator.get_config().agent_feedback_configs
        if not agent_feedback_configs:
            return None
        for config in agent_feedback_configs:
            if config.feedback_name == feedback_name:
                return config.feedback_aggregator_config
        return None

    def _should_run_generation(
        self,
        feedback_name: str,
        config: SkillGeneratorConfig,
        rerun: bool = False,
    ) -> bool:
        """
        Check if skill generation should run based on cooldown.

        Args:
            feedback_name: Name of the feedback type
            config: Skill generator configuration
            rerun: If True, bypass cooldown check

        Returns:
            bool: True if generation should run
        """
        if rerun:
            return True
        if not config.enabled:
            logger.info("Skill generation disabled for '%s'", feedback_name)
            return False
        # Check cooldown
        mgr = self._create_state_manager()
        bookmark = mgr.get_aggregator_bookmark(
            name=feedback_name, version=self.agent_version
        )
        if bookmark is not None:
            last_run_timestamp = bookmark
            cooldown_seconds = config.cooldown_hours * 3600
            elapsed = int(time.time()) - last_run_timestamp
            if elapsed < cooldown_seconds:
                logger.info(
                    "Skill generation on cooldown for '%s' (%d/%d seconds elapsed)",
                    feedback_name,
                    elapsed,
                    cooldown_seconds,
                )
                return False
        return True

    def _collect_interaction_context(
        self, cluster_feedbacks: list[RawFeedback], max_interactions: int
    ) -> str:
        """
        Collect interaction context for a cluster of feedbacks by fetching the original conversations.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster
            max_interactions: Maximum number of interactions to include

        Returns:
            str: Formatted interaction history string
        """
        request_ids = list({fb.request_id for fb in cluster_feedbacks if fb.request_id})
        if not request_ids:
            return "(No interaction context available)"
        interactions = self.storage.get_interactions_by_request_ids(request_ids)  # type: ignore[reportOptionalMemberAccess]
        interactions.sort(key=lambda i: i.created_at)
        interactions = interactions[:max_interactions]
        if not interactions:
            return "(No interaction context available)"
        return format_interactions_to_history_string(interactions)

    def _format_cluster_for_prompt(self, cluster_feedbacks: list[RawFeedback]) -> str:
        """
        Format a cluster of feedbacks for the skill generation prompt.

        Collects all do_action, do_not_action, when_condition, and blocking_issue
        values from the cluster.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster

        Returns:
            str: Formatted input for the generation prompt
        """
        do_actions = []
        do_not_actions = []
        when_conditions = []
        blocking_issues = []

        for fb in cluster_feedbacks:
            if fb.do_action:
                do_actions.append(fb.do_action)
            if fb.do_not_action:
                do_not_actions.append(fb.do_not_action)
            if fb.when_condition:
                when_conditions.append(fb.when_condition)
            if fb.blocking_issue:
                blocking_issues.append(
                    f"[{fb.blocking_issue.kind.value}] {fb.blocking_issue.details}"
                )

        lines = []
        if when_conditions:
            lines.append("WHEN conditions:")
            lines.extend(f"- {condition}" for condition in when_conditions)

        if do_actions:
            lines.append("DO actions:")
            lines.extend(f"- {action}" for action in do_actions)

        if do_not_actions:
            lines.append("DON'T actions:")
            lines.extend(f"- {action}" for action in do_not_actions)

        if blocking_issues:
            lines.append("BLOCKED BY issues:")
            lines.extend(f"- {issue}" for issue in blocking_issues)

        return "\n".join(lines)

    def _get_tool_can_use_str(self) -> str:
        """
        Format the tool_can_use config into a string for the prompt.

        Returns:
            str: Formatted string of available tools
        """
        tool_configs = self.configurator.get_config().tool_can_use
        if not tool_configs:
            return "(No tools configured)"
        lines = [
            f"- {tool.tool_name}: {tool.tool_description}" for tool in tool_configs
        ]
        return "\n".join(lines)

    def _generate_new_skill(
        self,
        cluster_feedbacks: list[RawFeedback],
        interaction_context: str,
        tool_can_use_str: str,
        existing_skills_str: str,
    ) -> Skill | None:
        """
        Generate a new skill from a cluster of feedbacks.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster
            interaction_context: Formatted interaction history
            tool_can_use_str: Formatted available tools string
            existing_skills_str: Formatted existing skills for dedup

        Returns:
            Skill or None if generation failed
        """
        raw_feedbacks_str = self._format_cluster_for_prompt(cluster_feedbacks)

        messages = [
            {
                "role": "user",
                "content": self.request_context.prompt_manager.render_prompt(
                    FeedbackServiceConstants.SKILL_GENERATION_PROMPT_ID,
                    {
                        "raw_feedbacks": raw_feedbacks_str,
                        "interaction_context": interaction_context,
                        "available_tools": tool_can_use_str,
                        "existing_skills": existing_skills_str,
                    },
                ),
            }
        ]

        logger.info(
            "Skill generation messages: %s",
            format_messages_for_logging(messages),
        )

        try:
            response = self.client.generate_chat_response(
                messages=messages,
                model=self.client.config.model,
                response_format=SkillGenerationOutput,
                parse_structured_output=True,
            )
            log_model_response(logger, "Skill generation response", response)

            if not response:
                return None

            raw_feedback_ids = [fb.raw_feedback_id for fb in cluster_feedbacks]

            return Skill(
                skill_name=response.skill_name,  # type: ignore[reportAttributeAccessIssue]
                description=response.description,  # type: ignore[reportAttributeAccessIssue]
                instructions=response.instructions,  # type: ignore[reportAttributeAccessIssue]
                allowed_tools=response.allowed_tools,  # type: ignore[reportAttributeAccessIssue]
                raw_feedback_ids=raw_feedback_ids,
                agent_version=self.agent_version,
                feedback_name=cluster_feedbacks[0].feedback_name,
                skill_status=SkillStatus.DRAFT,
            )
        except Exception as exc:
            logger.error("Skill generation failed: %s", str(exc))
            return None

    def _update_existing_skill(
        self,
        existing_skill: Skill,
        cluster_feedbacks: list[RawFeedback],
        interaction_context: str,
        tool_can_use_str: str,
    ) -> Skill | None:
        """
        Update an existing skill with new feedback learnings.

        Args:
            existing_skill: The existing skill to update
            cluster_feedbacks: List of new raw feedbacks
            interaction_context: Formatted interaction history
            tool_can_use_str: Formatted available tools string

        Returns:
            Updated Skill or None if update failed
        """
        raw_feedbacks_str = self._format_cluster_for_prompt(cluster_feedbacks)

        # Format existing skill for prompt
        existing_skill_str = (
            f"Skill Name: {existing_skill.skill_name}\n"
            f"Description: {existing_skill.description}\n"
            f"Instructions:\n{existing_skill.instructions}\n"
            f"Tools: {', '.join(existing_skill.allowed_tools)}"
        )

        messages = [
            {
                "role": "user",
                "content": self.request_context.prompt_manager.render_prompt(
                    FeedbackServiceConstants.SKILL_UPDATE_PROMPT_ID,
                    {
                        "existing_skill": existing_skill_str,
                        "new_raw_feedbacks": raw_feedbacks_str,
                        "interaction_context": interaction_context,
                        "available_tools": tool_can_use_str,
                    },
                ),
            }
        ]

        logger.info(
            "Skill update messages: %s",
            format_messages_for_logging(messages),
        )

        try:
            response = self.client.generate_chat_response(
                messages=messages,
                model=self.client.config.model,
                response_format=SkillGenerationOutput,
                parse_structured_output=True,
            )
            log_model_response(logger, "Skill update response", response)

            if not response:
                return None

            # Bump version: 1.0.0 -> 1.1.0, 1.1.0 -> 1.2.0, etc.
            version_parts = existing_skill.version.split(".")
            if len(version_parts) == 3:
                version_parts[1] = str(int(version_parts[1]) + 1)
                new_version = ".".join(version_parts)
            else:
                new_version = existing_skill.version

            # Merge raw_feedback_ids
            new_fb_ids = [fb.raw_feedback_id for fb in cluster_feedbacks]
            merged_ids = list(set(existing_skill.raw_feedback_ids + new_fb_ids))

            return Skill(
                skill_id=existing_skill.skill_id,
                skill_name=response.skill_name,  # type: ignore[reportAttributeAccessIssue]
                description=response.description,  # type: ignore[reportAttributeAccessIssue]
                version=new_version,
                agent_version=self.agent_version,
                feedback_name=existing_skill.feedback_name,
                instructions=response.instructions,  # type: ignore[reportAttributeAccessIssue]
                allowed_tools=response.allowed_tools,  # type: ignore[reportAttributeAccessIssue]
                raw_feedback_ids=merged_ids,
                skill_status=existing_skill.skill_status,
            )
        except Exception as exc:
            logger.error("Skill update failed: %s", str(exc))
            return None

    def run(self, request: SkillGeneratorRequest) -> dict:
        """
        Main entry point for skill generation.

        Args:
            request: SkillGeneratorRequest with agent_version, feedback_name, rerun

        Returns:
            dict with keys: skills_generated (int), skills_updated (int)
        """
        result = {"skills_generated": 0, "skills_updated": 0}

        # Get config
        skill_config = self._get_skill_generator_config(request.feedback_name)
        if skill_config is None:
            skill_config = SkillGeneratorConfig()

        # Check if should run
        if not self._should_run_generation(
            request.feedback_name, skill_config, rerun=request.rerun
        ):
            logger.info("Skipping skill generation for '%s'", request.feedback_name)
            return result

        logger.info("Running skill generation for '%s'", request.feedback_name)

        # Get feedback aggregator config for clustering
        aggregator_config = self._get_feedback_aggregator_config(request.feedback_name)
        if not aggregator_config:
            aggregator_config = FeedbackAggregatorConfig(
                min_feedback_threshold=skill_config.min_feedback_per_cluster
            )

        # Fetch raw feedbacks
        raw_feedbacks = self.storage.get_raw_feedbacks(  # type: ignore[reportOptionalMemberAccess]
            feedback_name=request.feedback_name,
            agent_version=self.agent_version,
            status_filter=[None],  # Current feedbacks only
            include_embedding=True,
        )

        if not raw_feedbacks:
            logger.info("No raw feedbacks found for '%s'", request.feedback_name)
            return result

        # Run clustering (reuse FeedbackAggregator)
        aggregator = FeedbackAggregator(
            llm_client=self.client,
            request_context=self.request_context,
            agent_version=self.agent_version,
        )
        clusters = aggregator.get_clusters(raw_feedbacks, aggregator_config)

        # Filter clusters by min_feedback_per_cluster
        min_size = skill_config.min_feedback_per_cluster
        clusters = {k: v for k, v in clusters.items() if len(v) >= min_size}

        if not clusters:
            logger.info("No clusters meet min_feedback_per_cluster=%d", min_size)
            return result

        # Get existing skills for dedup/update
        existing_skills = self.storage.get_skills(  # type: ignore[reportOptionalMemberAccess]
            feedback_name=request.feedback_name,
            agent_version=self.agent_version,
        )

        # Format existing skills for prompt
        existing_skills_str = "None"
        if existing_skills:
            lines = [f"- {s.skill_name}: {s.description}" for s in existing_skills]
            existing_skills_str = "\n".join(lines)

        tool_can_use_str = self._get_tool_can_use_str()
        max_interactions = skill_config.max_interactions_per_skill

        new_skills = []
        updated_skills = []

        for cluster_id, cluster_feedbacks in clusters.items():
            logger.info(
                "Processing cluster %d with %d feedbacks",
                cluster_id,
                len(cluster_feedbacks),
            )

            # Collect interaction context for enrichment
            interaction_context = self._collect_interaction_context(
                cluster_feedbacks, max_interactions
            )

            # Check for existing skill match by searching with cluster when_conditions
            when_conditions = [
                fb.when_condition for fb in cluster_feedbacks if fb.when_condition
            ]
            search_query = " ".join(when_conditions[:3]) if when_conditions else ""

            matched_skill = None
            if existing_skills and search_query:
                # Search for similar existing skill
                try:
                    matches = self.storage.search_skills(  # type: ignore[reportOptionalMemberAccess]
                        query=search_query,
                        feedback_name=request.feedback_name,
                        agent_version=self.agent_version,
                        match_threshold=0.7,
                        match_count=1,
                    )
                    if matches:
                        matched_skill = matches[0]
                except Exception as exc:
                    logger.warning("Skill search failed: %s", str(exc))

            if matched_skill:
                # Update existing skill
                updated = self._update_existing_skill(
                    matched_skill,
                    cluster_feedbacks,
                    interaction_context,
                    tool_can_use_str,
                )
                if updated:
                    updated_skills.append(updated)
                    logger.info(
                        "Updated skill '%s' -> v%s", updated.skill_name, updated.version
                    )
            else:
                # Generate new skill
                skill = self._generate_new_skill(
                    cluster_feedbacks,
                    interaction_context,
                    tool_can_use_str,
                    existing_skills_str,
                )
                if skill:
                    new_skills.append(skill)
                    logger.info("Generated new skill '%s'", skill.skill_name)

        # Save all skills
        all_skills = new_skills + updated_skills
        if all_skills:
            self.storage.save_skills(all_skills)  # type: ignore[reportOptionalMemberAccess]

        # Update operation state with timestamp as bookmark for cooldown
        if raw_feedbacks:
            mgr = self._create_state_manager()
            mgr.update_aggregator_bookmark(
                name=request.feedback_name,
                version=self.agent_version,
                last_processed_id=int(time.time()),
            )

        result["skills_generated"] = len(new_skills)
        result["skills_updated"] = len(updated_skills)

        logger.info(
            "Skill generation complete for '%s': %d generated, %d updated",
            request.feedback_name,
            len(new_skills),
            len(updated_skills),
        )

        return result


def render_skills_markdown(skills: list[Skill]) -> str:
    """
    Render a list of skills as a SKILL.md markdown document.

    Args:
        skills: List of Skill objects to render

    Returns:
        str: Formatted markdown string
    """
    if not skills:
        return "# Skills\n\nNo skills generated yet.\n"

    lines = ["# Skills\n"]

    for skill in skills:
        lines.append(f"## {skill.skill_name}")
        lines.append(f"**Description:** {skill.description}")
        lines.append(f"**Version:** {skill.version}")
        lines.append("")

        if skill.instructions:
            lines.append("### Instructions")
            lines.append(skill.instructions)
            lines.append("")

        if skill.allowed_tools:
            lines.append("### Tools")
            lines.extend(f"- {tool}" for tool in skill.allowed_tools)
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)
