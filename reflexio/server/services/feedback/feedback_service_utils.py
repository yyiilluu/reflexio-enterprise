import logging
from dataclasses import dataclass
from typing import Any, Optional

from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import RawFeedback, BlockingIssue
from pydantic import BaseModel, Field, ConfigDict, model_validator

logger = logging.getLogger(__name__)

from reflexio.server.services.feedback.feedback_service_constants import (
    FeedbackServiceConstants,
)
from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.service_utils import (
    PromptConfig,
    MessageConstructionConfig,
    construct_messages_from_interactions,
    format_sessions_to_history_string,
    extract_interactions_from_request_interaction_data_models,
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

    do_action: Optional[str] = Field(
        default=None,
        description="The preferred behavior the agent should adopt",
    )
    do_not_action: Optional[str] = Field(
        default=None,
        description="The mistaken behavior the agent should avoid",
    )
    when_condition: Optional[str] = Field(
        default=None,
        description="The condition or context when this rule applies",
    )
    blocking_issue: Optional[BlockingIssue] = Field(
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
            if isinstance(feedback_value, list) and len(feedback_value) > 0:
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
        if self.when_condition is not None:
            if self.do_action is None and self.do_not_action is None:
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


# ===============================
# Pydantic classes for feedback_generation prompt output schema (v2.1.0+)
# ===============================


class FeedbackAggregationOutput(BaseModel):
    """
    Output schema for feedback_generation prompt (version >= 2.1.0).

    Contains the consolidated feedback or null if no new feedback should be generated
    (e.g., when it duplicates existing approved feedback).
    """

    feedback: Optional[StructuredFeedbackContent] = Field(
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


@dataclass
class SkillGeneratorRequest:
    agent_version: str
    feedback_name: str
    rerun: bool = False


class FeedbackGenerationRequest(BaseModel):
    request_id: str
    agent_version: str
    user_id: Optional[str] = None  # for per-user feedback extraction
    source: Optional[str] = None
    rerun_start_time: Optional[int] = None  # Unix timestamp for rerun flows
    rerun_end_time: Optional[int] = None  # Unix timestamp for rerun flows
    feedback_name: Optional[str] = None  # Filter to run only specific extractor
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
    existing_raw_feedbacks: Optional[list[RawFeedback]] = None,
    tool_can_use: Optional[str] = None,
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
        existing_raw_feedbacks: Optional list of existing raw feedbacks from past 7 days
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

    # Format existing feedbacks for context
    formatted_existing_feedbacks = ""
    if existing_raw_feedbacks:
        formatted_existing_feedbacks = "\n".join(
            [f"- {feedback.feedback_content}" for feedback in existing_raw_feedbacks]
        )
    else:
        formatted_existing_feedbacks = "(No existing feedbacks)"

    # Configure final user message (after interactions)
    # Only dynamic per-call data goes in user message
    user_config = PromptConfig(
        prompt_id=FeedbackServiceConstants.RAW_FEEDBACK_EXTRACTION_PROMPT_ID,
        variables={
            "existing_feedbacks": formatted_existing_feedbacks,
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
    existing_raw_feedbacks: Optional[list[RawFeedback]] = None,
    previously_extracted: Optional[list[RawFeedback]] = None,
    tool_can_use: Optional[str] = None,
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
        existing_raw_feedbacks: Optional list of existing raw feedbacks from past 7 days
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

    # Format existing feedbacks for context
    formatted_existing_feedbacks = ""
    if existing_raw_feedbacks:
        formatted_existing_feedbacks = "\n".join(
            [f"- {feedback.feedback_content}" for feedback in existing_raw_feedbacks]
        )
    else:
        formatted_existing_feedbacks = "(No existing feedbacks)"

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
            "existing_feedbacks": formatted_existing_feedbacks,
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
