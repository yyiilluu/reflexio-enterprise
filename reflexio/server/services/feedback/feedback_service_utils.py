import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import BlockingIssue, RawFeedback

logger = logging.getLogger(__name__)

from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.feedback.feedback_service_constants import (
    FeedbackServiceConstants,
)
from reflexio.server.services.service_utils import (
    MessageConstructionConfig,
    PromptConfig,
    construct_messages_from_interactions,
    extract_interactions_from_request_interaction_data_models,
    format_sessions_to_history_string,
)

# ===============================
# Pydantic classes for raw_feedback_extraction_main prompt output schema
# ===============================


class StructuredFeedbackContent(BaseModel):
    """
    Structured representation of feedback content.

    Handles two formats:
    1. Feedback present: {"do_action": "...", "do_not_action": "...", "when_condition": "..."}
    2. No feedback: {"feedback": null}

    Represents feedback in the format: "Do [do_action] instead of [do_not_action] when [when_condition]"
    At least one of do_action or do_not_action must be provided when when_condition is set.
    """

    do_action: str | None = Field(
        default=None,
        description="The preferred behavior the agent should adopt",
    )
    do_not_action: str | None = Field(
        default=None,
        description="The mistaken behavior the agent should avoid",
    )
    when_condition: str | None = Field(
        default=None,
        description="The condition or context when this rule applies",
    )
    blocking_issue: BlockingIssue | None = Field(
        default=None,
        description="Present only when the agent could not complete the user's request due to a capability limitation",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )

    @model_validator(mode="before")
    @classmethod
    def handle_null_feedback_format(cls, data: Any) -> Any:
        """Handle wrapped feedback formats from LLMs.

        Some models wrap the response in {"feedback": ...}. This handles:
        - {"feedback": null} → empty (no feedback)
        - {"feedback": [{...}, ...]} → first item extracted
        - {"feedback": {...}} → inner dict extracted
        """
        if isinstance(data, dict) and "feedback" in data:
            feedback_value = data["feedback"]
            if feedback_value is None:
                return {}
            if isinstance(feedback_value, list) and feedback_value:
                if len(feedback_value) > 1:
                    logger.warning(
                        "LLM returned %d feedback items in a list; using only the first",
                        len(feedback_value),
                    )
                first = feedback_value[0]
                if isinstance(first, dict):
                    return first
                return {}
            if isinstance(feedback_value, dict):
                return feedback_value
        return data

    @model_validator(mode="after")
    def validate_feedback_fields(self) -> "StructuredFeedbackContent":
        """Ensure at least one action is provided when condition is present."""
        if (
            self.when_condition is not None
            and self.do_action is None
            and self.do_not_action is None
        ):
            raise ValueError(
                "At least one of 'do_action' or 'do_not_action' must be provided when 'when_condition' is set"
            )
        return self

    @property
    def has_feedback(self) -> bool:
        """Check if this output contains actual feedback.

        Requires a non-empty when_condition and at least one non-empty action (do or don't).
        """
        has_condition = bool(self.when_condition and self.when_condition.strip())
        has_action = bool(
            (self.do_action and self.do_action.strip())
            or (self.do_not_action and self.do_not_action.strip())
        )
        return has_condition and has_action


class FeedbackAggregationOutput(BaseModel):
    """
    Output schema for feedback_generation prompt (version >= 2.1.0).

    Contains the consolidated feedback or null if no new feedback should be generated
    (e.g., when it duplicates existing approved feedback).
    """

    feedback: StructuredFeedbackContent | None = Field(
        default=None,
        description="The consolidated feedback, or null if no new feedback should be generated",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )


# ===============================
# Pydantic classes for skill generation prompt output schema
# ===============================


class SkillGenerationOutput(BaseModel):
    """Output schema for skill_generation prompt."""

    skill_name: str
    description: str
    instructions: str
    allowed_tools: list[str] = Field(default_factory=list)
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )


def format_structured_feedback_content(structured: StructuredFeedbackContent) -> str:
    """
    Format structured feedback content to prompt instruction format.

    Converts structured fields to bullet format:
    - When: "condition."
    - Do: "action."
    - Don't: "avoid action."

    Args:
        structured (StructuredFeedbackContent): The structured feedback content

    Returns:
        str: Formatted feedback content string for prompts
    """
    lines = []

    if structured.when_condition:
        lines.append(f'When: "{structured.when_condition}"')

    if structured.do_action:
        lines.append(f'Do: "{structured.do_action}"')

    if structured.do_not_action:
        lines.append(f'Don\'t: "{structured.do_not_action}"')

    if structured.blocking_issue:
        lines.append(
            f"Blocked by: [{structured.blocking_issue.kind.value}] {structured.blocking_issue.details}"
        )

    return "\n".join(lines)


@dataclass
class SkillGeneratorRequest:
    agent_version: str
    feedback_name: str
    rerun: bool = False


class FeedbackGenerationRequest(BaseModel):
    request_id: str
    agent_version: str
    user_id: str | None = None  # for per-user feedback extraction
    source: str | None = None
    rerun_start_time: int | None = None  # Unix timestamp for rerun flows
    rerun_end_time: int | None = None  # Unix timestamp for rerun flows
    feedback_name: str | None = None  # Filter to run only specific extractor
    auto_run: bool = (
        True  # True for regular flow (checks stride), False for rerun/manual
    )


class FeedbackAggregatorRequest(BaseModel):
    agent_version: str
    feedback_name: str
    rerun: bool = False


def construct_feedback_extraction_messages_from_sessions(
    prompt_manager: PromptManager,
    request_interaction_data_models: list[RequestInteractionDataModel],
    agent_context_prompt: str,
    feedback_definition_prompt: str,
    tool_can_use: str | None = None,
) -> list[dict]:
    """
    Construct LLM messages for feedback extraction from sessions.

    This function uses the shared message construction interface to build messages
    with a system prompt and a final user prompt specific to feedback extraction.

    Args:
        prompt_manager: The prompt manager for rendering prompt templates
        request_interaction_data_models: List of request interaction groups to extract feedback from
        agent_context_prompt: Context about the agent for system message
        feedback_definition_prompt: Definition of what feedback should contain
        tool_can_use: Optional formatted string of tools available to the agent

    Returns:
        list[dict]: List of messages ready for feedback extraction
    """
    # Configure system message (before interactions)
    # Stable content (instructions, examples, definitions) goes in system message for token caching
    system_config = PromptConfig(
        prompt_id=FeedbackServiceConstants.RAW_FEEDBACK_EXTRACTION_CONTEXT_PROMPT_ID,
        variables={
            "agent_context_prompt": agent_context_prompt,
            "feedback_definition_prompt": feedback_definition_prompt,
            "tool_can_use": tool_can_use or "",
        },
    )

    # Configure final user message (after interactions)
    # Only dynamic per-call data goes in user message
    user_config = PromptConfig(
        prompt_id=FeedbackServiceConstants.RAW_FEEDBACK_EXTRACTION_PROMPT_ID,
        variables={
            "interactions": format_sessions_to_history_string(
                request_interaction_data_models
            ),
        },
    )

    # Extract flat interactions for message construction
    interactions = extract_interactions_from_request_interaction_data_models(
        request_interaction_data_models
    )

    # Use shared message construction
    config = MessageConstructionConfig(
        prompt_manager=prompt_manager,
        system_prompt_config=system_config,
        user_prompt_config=user_config,
    )

    return construct_messages_from_interactions(interactions, config)


def construct_incremental_feedback_extraction_messages(
    prompt_manager: PromptManager,
    request_interaction_data_models: list[RequestInteractionDataModel],
    agent_context_prompt: str,
    feedback_definition_prompt: str,
    previously_extracted: list[RawFeedback] | None = None,
    tool_can_use: str | None = None,
) -> list[dict]:
    """
    Construct LLM messages for incremental feedback extraction.

    Uses incremental prompts that show what previous extractors already found,
    so this extractor focuses on finding additional policies not already covered.

    Args:
        prompt_manager: The prompt manager for rendering prompt templates
        request_interaction_data_models: List of request interaction groups to extract feedback from
        agent_context_prompt: Context about the agent for system message
        feedback_definition_prompt: Definition of what feedback should contain
        previously_extracted: Flattened list of all RawFeedback from previous extractors
        tool_can_use: Optional formatted string of tools available to the agent

    Returns:
        list[dict]: List of messages ready for incremental feedback extraction
    """
    # Configure system message with incremental prompt
    system_config = PromptConfig(
        prompt_id=FeedbackServiceConstants.RAW_FEEDBACK_EXTRACTION_CONTEXT_INCREMENTAL_PROMPT_ID,
        variables={
            "agent_context_prompt": agent_context_prompt,
            "feedback_definition_prompt": feedback_definition_prompt,
            "tool_can_use": tool_can_use or "",
        },
    )

    # Format previously extracted feedbacks
    formatted_previously_extracted = ""
    if previously_extracted:
        formatted_previously_extracted = "\n".join(
            [f"- {feedback.feedback_content}" for feedback in previously_extracted]
        )
    else:
        formatted_previously_extracted = "(None)"

    # Configure final user message with incremental prompt
    user_config = PromptConfig(
        prompt_id=FeedbackServiceConstants.RAW_FEEDBACK_EXTRACTION_INCREMENTAL_PROMPT_ID,
        variables={
            "previously_extracted_feedbacks": formatted_previously_extracted,
            "interactions": format_sessions_to_history_string(
                request_interaction_data_models
            ),
        },
    )

    # Extract flat interactions for message construction
    interactions = extract_interactions_from_request_interaction_data_models(
        request_interaction_data_models
    )

    # Use shared message construction
    config = MessageConstructionConfig(
        prompt_manager=prompt_manager,
        system_prompt_config=system_config,
        user_prompt_config=user_config,
    )

    return construct_messages_from_interactions(interactions, config)
