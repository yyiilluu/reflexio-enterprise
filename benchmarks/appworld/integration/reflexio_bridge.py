"""
Maps AppWorld execution traces to Reflexio InteractionData format.

Converts agent code-generation steps and execution outputs into the
User/Assistant interaction format that Reflexio expects for profile
and feedback extraction.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
    ProfileExtractorConfig,
    SkillGeneratorConfig,
    StorageConfigLocal,
    StorageConfigSupabase,
    ToolUseConfig,
)

from benchmarks.appworld.agent.base_agent import AgentTrace

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env")

logger = logging.getLogger(__name__)


def trace_to_interactions(
    trace: AgentTrace,
    task_instruction: str,
    supervisor_email: str = "",
    supervisor_name: str = "",
) -> list:
    """
    Convert an AppWorld AgentTrace into a list of Reflexio InteractionData objects.

    Mapping:
        - Task instruction + supervisor info -> User message (first interaction)
        - Agent-generated code block -> Assistant message
        - Execution output (stdout/stderr) -> User message
        - Final evaluation result -> User message (last interaction)

    Args:
        trace (AgentTrace): Complete agent execution trace
        task_instruction (str): The original task instruction
        supervisor_email (str): Supervisor email for context
        supervisor_name (str): Supervisor name for context

    Returns:
        list: List of InteractionData objects ready for Reflexio publishing
    """
    from reflexio.reflexio_client.reflexio import InteractionData

    interactions = []

    # First interaction: task instruction with supervisor context
    task_context_parts = [f"Task: {task_instruction}"]
    if supervisor_name:
        task_context_parts.append(f"Supervisor: {supervisor_name}")
    if supervisor_email:
        task_context_parts.append(f"Email: {supervisor_email}")
    interactions.append(
        InteractionData(role="User", content="\n".join(task_context_parts))
    )

    # Map each step to Assistant (code) + User (output) pairs
    for step in trace.steps:
        if step.code:
            interactions.append(InteractionData(role="Assistant", content=step.code))
        if step.output:
            interactions.append(InteractionData(role="User", content=step.output))

    return interactions


def get_user_id(supervisor_email: str) -> str:
    """
    Map an AppWorld supervisor email to a Reflexio user ID.

    Each supervisor persona maps to a unique Reflexio user so that
    profiles accumulate per-supervisor across tasks.

    Args:
        supervisor_email (str): Supervisor's email address

    Returns:
        str: Reflexio user ID
    """
    if supervisor_email:
        # Sanitize email for use as ID
        return f"appworld_{supervisor_email.replace('@', '_at_').replace('.', '_')}"
    return "appworld_unknown"


def publish_trace_to_reflexio(
    client,
    trace: AgentTrace,
    task_instruction: str,
    supervisor_email: str = "",
    supervisor_name: str = "",
    agent_version: str = "appworld-v1",
    task_passed: bool | None = None,
) -> bool:
    """
    Convert an agent trace to InteractionData and publish it to Reflexio.

    Optionally appends a final evaluation result message indicating
    whether the task succeeded or failed.

    Args:
        client: ReflexioClient instance
        trace (AgentTrace): Agent execution trace to publish
        task_instruction (str): Original task instruction
        supervisor_email (str): Supervisor email for user ID mapping
        supervisor_name (str): Supervisor display name
        agent_version (str): Agent version tag for Reflexio
        task_passed (bool | None): Whether the task passed evaluation (None if unknown)

    Returns:
        bool: True if publishing succeeded
    """
    from reflexio.reflexio_client.reflexio import InteractionData

    interactions = trace_to_interactions(
        trace, task_instruction, supervisor_email, supervisor_name
    )

    # Append evaluation result if known
    if task_passed is not None:
        result_msg = (
            "TASK SUCCEEDED — all test assertions passed."
            if task_passed
            else "TASK FAILED — one or more test assertions did not pass."
        )
        interactions.append(InteractionData(role="User", content=result_msg))

    user_id = get_user_id(supervisor_email)

    try:
        resp = client.publish_interaction(
            user_id=user_id,
            interactions=interactions,
            source="appworld-benchmark",
            agent_version=agent_version,
            wait_for_response=True,
        )
        if resp and resp.success:
            logger.info(
                "Published %d interactions for task %s (user=%s)",
                len(interactions),
                trace.task_id,
                user_id,
            )
            return True
        msg = resp.message if resp else "no response"
        logger.warning("Publish failed for task %s: %s", trace.task_id, msg)
        return False
    except Exception:
        logger.exception("Error publishing task %s to Reflexio", trace.task_id)
        return False


def setup_reflexio_config(client) -> None:
    """
    Configure Reflexio extractors for AppWorld benchmark evaluation.

    Sets up profile extraction (supervisor details, preferences) and
    feedback extraction (agent mistakes, wrong API usage) tailored
    to the AppWorld code-generation setting.

    Follows the pattern from demo/run_comparison.py:_setup_reflexio_config().

    Args:
        client: ReflexioClient instance
    """
    config = client.get_config()

    # Storage: prefer Supabase for vector search, fall back to local
    supabase_url = os.getenv("TEST_SUPABASE_URL")
    supabase_key = os.getenv("TEST_SUPABASE_KEY")
    supabase_db_url = os.getenv("TEST_SUPABASE_DB_URL")
    if supabase_url and supabase_key and supabase_db_url:
        config.storage_config = StorageConfigSupabase(
            url=supabase_url, key=supabase_key, db_url=supabase_db_url
        )
        logger.info("Using Supabase storage at %s", supabase_url)
    elif config.storage_config is None:
        storage_dir = str(Path(__file__).resolve().parent.parent / "reflexio_storage")
        config.storage_config = StorageConfigLocal(dir_path=storage_dir)
        logger.warning(
            "Using local storage at %s — set TEST_SUPABASE_URL/KEY/DB_URL for semantic search",
            storage_dir,
        )

    config.agent_context_prompt = (
        "The agent operates in the AppWorld benchmark environment, writing Python code "
        "to interact with 9 simulated app APIs (Amazon, Gmail, Spotify, Venmo, etc.) "
        "to complete tasks on behalf of a supervisor user."
    )

    config.profile_extractor_configs = [
        ProfileExtractorConfig(
            extractor_name="appworld_supervisor_profile",
            profile_content_definition_prompt=(
                "Extract supervisor details from the conversation: account credentials, "
                "personal preferences, app usage patterns, relationships with other users, "
                "personal information (name, email, addresses), payment methods, "
                "subscription details, and any other factual details about the supervisor."
            ),
            context_prompt=(
                "An autonomous coding agent solving tasks in a simulated app environment "
                "on behalf of a supervisor user."
            ),
            extraction_window_stride_override=1,
            extraction_window_size_override=40,
        )
    ]

    config.agent_feedback_configs = [
        AgentFeedbackConfig(
            feedback_name="appworld_task_feedback",
            feedback_definition_prompt=(
                "Identify agent mistakes and inefficiencies: wrong API endpoint usage, "
                "missing authentication steps, incorrect parameters, wrong assumptions "
                "about data formats, failed search strategies, unnecessary API calls, "
                "incomplete task handling, and any patterns that led to task failure."
            ),
            feedback_aggregator_config=FeedbackAggregatorConfig(
                min_feedback_threshold=2
            ),
            skill_generator_config=SkillGeneratorConfig(
                enabled=True,
                min_feedback_per_cluster=3,
                cooldown_hours=0,
                auto_generate_on_aggregation=True,
            ),
            extraction_window_stride_override=1,
            extraction_window_size_override=40,
        )
    ]

    config.tool_can_use = [
        ToolUseConfig(
            tool_name="apis",
            tool_description=(
                "AppWorld API object providing access to 9 simulated apps: "
                "Amazon, Gmail, Spotify, Venmo, File Manager, Phone, Reminders, "
                "Notes, Calendar. Used as apis.<app>.<method>(...)."
            ),
        )
    ]

    resp = client.set_config(config)
    if not resp.get("success"):
        raise RuntimeError(
            f"Failed to set Reflexio config: {resp.get('msg', 'unknown error')}"
        )
    logger.info("Reflexio config set successfully for AppWorld benchmark")
