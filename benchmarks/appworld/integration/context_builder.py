"""
Builds enhanced prompts from Reflexio search results for AppWorld agents.

Fetches user profiles, raw feedbacks, and skills from Reflexio and formats
them into a context block for injection into the agent's system prompt.

Follows the pattern from demo/simulate_conversation.py:get_reflexio_context().
"""

import logging

from benchmarks.appworld.config import ReflexioConfig

logger = logging.getLogger(__name__)


def fetch_reflexio_context(
    client,
    query: str,
    user_id: str,
    agent_version: str = "appworld-v1",
    config: ReflexioConfig | None = None,
) -> str:
    """
    Fetch user profiles, feedbacks, and skills from Reflexio and format as a context block.

    Searches three data types using the task instruction as the query:
    1. User profiles — supervisor details and preferences
    2. Raw feedbacks — behavioral corrections from past mistakes
    3. Skills — reusable patterns extracted from feedback clusters

    Args:
        client: ReflexioClient instance
        query (str): Search query (typically the task instruction)
        user_id (str): Reflexio user ID for profile search
        agent_version (str): Agent version for feedback search
        config (ReflexioConfig | None): Search parameters (defaults used if None)

    Returns:
        str: Formatted context block, or empty string if nothing found
    """
    if config is None:
        config = ReflexioConfig()

    profile_section = _fetch_profiles(client, query, user_id, config)
    feedback_section = _fetch_feedbacks(client, query, agent_version, config)
    skill_section = _fetch_skills(client, query, config)

    if not profile_section and not feedback_section and not skill_section:
        logger.info("No Reflexio context found for query: %s", query[:80])
        return ""

    return (
        "\n\n---\n# Context and Corrections from Past Experience"
        + profile_section
        + feedback_section
        + skill_section
        + "\n---"
    )


def _fetch_profiles(client, query: str, user_id: str, config: ReflexioConfig) -> str:
    """
    Search Reflexio for relevant user profiles.

    Args:
        client: ReflexioClient instance
        query (str): Search query
        user_id (str): User ID to search profiles for
        config (ReflexioConfig): Search parameters

    Returns:
        str: Formatted profile section or empty string
    """
    try:
        resp = client.search_profiles(
            user_id=user_id,
            query=query,
            top_k=config.profile_top_k,
            threshold=config.search_threshold,
        )
        if resp.success and resp.user_profiles:
            lines = [f"- {p.profile_content}" for p in resp.user_profiles]
            logger.info(
                "Found %d profiles for user %s", len(resp.user_profiles), user_id
            )
            return "\n## Known User Preferences & Information\n" + "\n".join(lines)
    except Exception:
        logger.exception("Failed to fetch profiles for user %s", user_id)
    return ""


def _fetch_feedbacks(
    client, query: str, agent_version: str, config: ReflexioConfig
) -> str:
    """
    Search Reflexio for relevant raw feedbacks (behavioral corrections).

    Args:
        client: ReflexioClient instance
        query (str): Search query
        agent_version (str): Agent version filter
        config (ReflexioConfig): Search parameters

    Returns:
        str: Formatted feedback section or empty string
    """
    try:
        resp = client.search_raw_feedbacks(
            query=query,
            agent_version=agent_version,
            top_k=config.feedback_top_k,
            threshold=config.search_threshold,
        )
        if resp.success and resp.raw_feedbacks:
            lines = []
            for fb in resp.raw_feedbacks:
                parts = [f"- {fb.feedback_content}"]
                if fb.do_action:
                    parts.append(f"  DO: {fb.do_action}")
                if fb.do_not_action:
                    parts.append(f"  DON'T: {fb.do_not_action}")
                if fb.when_condition:
                    parts.append(f"  WHEN: {fb.when_condition}")
                lines.append("\n".join(parts))
            logger.info("Found %d feedbacks", len(resp.raw_feedbacks))
            return (
                "\n## Behavior Corrections\n"
                "The following rules are learned from past mistakes and OVERRIDE your "
                "standard flow above. Before responding, check each rule: if the WHEN "
                "condition matches the current situation, you MUST follow the DO/DON'T "
                "actions even if they differ from your default steps.\n\n"
                + "\n\n".join(lines)
            )
    except Exception:
        logger.exception("Failed to fetch feedbacks")
    return ""


def _fetch_skills(client, query: str, config: ReflexioConfig) -> str:
    """
    Search Reflexio for relevant skills (reusable patterns from feedback clusters).

    Args:
        client: ReflexioClient instance
        query (str): Search query
        config (ReflexioConfig): Search parameters

    Returns:
        str: Formatted skills section or empty string
    """
    try:
        resp = client.search_skills(
            query=query,
            top_k=config.skill_top_k,
            threshold=config.search_threshold,
        )
        if resp.success and resp.skills:
            lines = []
            for skill in resp.skills:
                parts = [f"- **{skill.skill_name}**: {skill.skill_instruction}"]
                if hasattr(skill, "allowed_tools") and skill.allowed_tools:
                    parts.append(f"  Tools: {', '.join(skill.allowed_tools)}")
                lines.append("\n".join(parts))
            logger.info("Found %d skills", len(resp.skills))
            return (
                "\n## Learned Skills\n"
                "The following skills were extracted from successful patterns. "
                "Apply them when relevant to the current task.\n\n" + "\n\n".join(lines)
            )
    except Exception:
        logger.exception("Failed to fetch skills")
    return ""
