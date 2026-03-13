import enum
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from reflexio_commons.api_schema.validators import (
    EmbeddingVector,
    NonEmptyStr,
    TimeRangeValidatorMixin,
    _check_safe_url,
)

# OS-agnostic "never expires" timestamp (January 1, 2100 00:00:00 UTC)
# This is well within the safe range for all systems (32-bit timestamp limit is 2038)
NEVER_EXPIRES_TIMESTAMP = 4102444800


# ===============================
# Enums
# ===============================
class UserActionType(str, enum.Enum):
    CLICK = "click"
    SCROLL = "scroll"
    TYPE = "type"
    NONE = "none"


class ProfileTimeToLive(str, enum.Enum):
    ONE_DAY = "one_day"
    ONE_WEEK = "one_week"
    ONE_MONTH = "one_month"
    ONE_QUARTER = "one_quarter"
    ONE_YEAR = "one_year"
    INFINITY = "infinity"


class FeedbackStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SkillStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class Status(str, enum.Enum):
    CURRENT = None  # None for current profile/feedback
    ARCHIVED = "archived"  # archived old profiles/feedbacks
    PENDING = "pending"  # new profiles/feedbacks that are not approved
    ARCHIVE_IN_PROGRESS = (
        "archive_in_progress"  # temporary status during downgrade operation
    )


class OperationStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RegularVsShadow(str, enum.Enum):
    """
    This enum is used to indicate the relative performance of the regular and shadow versions of the agent.
    """

    REGULAR_IS_BETTER = "regular_is_better"
    REGULAR_IS_SLIGHTLY_BETTER = "regular_is_slightly_better"
    SHADOW_IS_BETTER = "shadow_is_better"
    SHADOW_IS_SLIGHTLY_BETTER = "shadow_is_slightly_better"
    TIED = "tied"


class BlockingIssueKind(str, enum.Enum):
    MISSING_TOOL = "missing_tool"
    PERMISSION_DENIED = "permission_denied"
    EXTERNAL_DEPENDENCY = "external_dependency"
    POLICY_RESTRICTION = "policy_restriction"


# ===============================
# Data Models
# ===============================


class BlockingIssue(BaseModel):
    kind: BlockingIssueKind
    details: str = Field(
        description="What capability is missing and why it blocks the request"
    )


class ToolUsed(BaseModel):
    tool_name: str
    tool_input: dict = Field(default_factory=dict)  # dict of param name -> value


# information about the user interaction sent by the client
class Interaction(BaseModel):
    interaction_id: int = 0  # 0 = placeholder for DB auto-increment
    user_id: str
    request_id: str
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    role: str = "User"
    content: str = ""
    user_action: UserActionType = UserActionType.NONE
    user_action_description: str = ""
    interacted_image_url: str = ""
    image_encoding: str = ""  # base64 encoded image
    shadow_content: str = ""
    tools_used: list[ToolUsed] = Field(default_factory=list)
    embedding: EmbeddingVector = []

    @field_validator("interacted_image_url", mode="after")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        """SSRF prevention: if URL is provided, must be safe http(s) or data URI."""
        if not v:
            return v  # empty string is allowed (no image)
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https", "data"):
            raise ValueError(
                f"Image URL scheme must be http, https, or data — got '{parsed.scheme}'"
            )
        if parsed.scheme in ("http", "https"):
            _check_safe_url(v)
        return v


class Request(BaseModel):
    request_id: str
    user_id: str
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    source: str = ""
    agent_version: str = ""
    session_id: str | None = None


# information about the user profile generated from the user interaction
# output of the profile generation service send back to the client
class UserProfile(BaseModel):
    profile_id: str
    user_id: str
    profile_content: str
    last_modified_timestamp: int
    generated_from_request_id: str
    profile_time_to_live: ProfileTimeToLive = ProfileTimeToLive.INFINITY
    # this is the expiration date calculated based on last modified timestamp and profile time to live instead of generated timestamp
    expiration_timestamp: int = NEVER_EXPIRES_TIMESTAMP
    custom_features: dict | None = None
    source: str | None = None
    status: Status | None = None  # indicates the status of the profile
    extractor_names: list[str] | None = None
    embedding: EmbeddingVector = []


# raw feedback for agents
class RawFeedback(BaseModel):
    raw_feedback_id: int = 0
    user_id: str | None = None  # optional for backward compatibility
    agent_version: str
    request_id: str
    feedback_name: str = ""
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    feedback_content: str = ""

    # Structured feedback fields (v1.2.0+)
    do_action: str | None = None  # What the agent should do (preferred behavior)
    do_not_action: str | None = None  # What the agent should avoid (mistaken behavior)
    when_condition: str | None = None  # The condition/context when this applies

    status: Status | None = (
        None  # Status.PENDING (from rerun), None (current), Status.ARCHIVED (old)
    )
    source: str | None = None  # source of the interaction that generated this feedback
    blocking_issue: BlockingIssue | None = (
        None  # Root cause when agent couldn't complete action
    )
    indexed_content: str | None = (
        None  # Content used for embedding/indexing (extracted from feedback_content)
    )
    source_interaction_ids: list[int] = Field(default_factory=list)
    embedding: EmbeddingVector = []


class ProfileChangeLog(BaseModel):
    id: int
    user_id: str
    request_id: str
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    added_profiles: list[UserProfile]
    removed_profiles: list[UserProfile]
    mentioned_profiles: list[UserProfile]


class Feedback(BaseModel):
    feedback_id: int = 0
    feedback_name: str = ""
    agent_version: str
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    feedback_content: str

    # Structured feedback fields (v1.2.0+)
    do_action: str | None = None  # What the agent should do (preferred behavior)
    do_not_action: str | None = None  # What the agent should avoid (mistaken behavior)
    when_condition: str | None = None  # The condition/context when this applies

    blocking_issue: BlockingIssue | None = (
        None  # Root cause when agent couldn't complete action
    )
    feedback_status: FeedbackStatus = FeedbackStatus.PENDING
    feedback_metadata: str = ""
    embedding: EmbeddingVector = []
    status: Status | None = (
        None  # used for tracking intermediate states during feedback aggregation. Status.ARCHIVED for feedbacks during aggregation process, None for current feedbacks
    )


class Skill(BaseModel):
    skill_id: int = 0
    skill_name: str
    description: str = ""
    version: str = "1.0.0"
    agent_version: str = ""
    feedback_name: str = ""
    instructions: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    raw_feedback_ids: list[int] = Field(default_factory=list)
    skill_status: SkillStatus = SkillStatus.DRAFT
    embedding: EmbeddingVector = Field(default_factory=list, exclude=True)
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    updated_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )


class AgentSuccessEvaluationResult(BaseModel):
    result_id: int = 0
    agent_version: str
    session_id: str
    is_success: bool
    failure_type: str | None = None
    failure_reason: str | None = None
    evaluation_name: str | None = None
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    regular_vs_shadow: RegularVsShadow | None = None
    number_of_correction_per_session: int = 0
    user_turns_to_resolution: int | None = None
    is_escalated: bool = False
    embedding: EmbeddingVector = []


# ===============================
# Request Models
# ===============================


# delete user profile request
class DeleteUserProfileRequest(BaseModel):
    user_id: NonEmptyStr
    profile_id: str = ""
    search_query: str = ""


# delete user profile response
class DeleteUserProfileResponse(BaseModel):
    success: bool
    message: str = ""


# delete user interaction request
class DeleteUserInteractionRequest(BaseModel):
    user_id: NonEmptyStr
    interaction_id: int = Field(gt=0)


# delete user interaction response
class DeleteUserInteractionResponse(BaseModel):
    success: bool
    message: str = ""


# delete request request
class DeleteRequestRequest(BaseModel):
    request_id: NonEmptyStr


# delete request response
class DeleteRequestResponse(BaseModel):
    success: bool
    message: str = ""


# delete session request
class DeleteSessionRequest(BaseModel):
    session_id: NonEmptyStr


# delete session response
class DeleteSessionResponse(BaseModel):
    success: bool
    message: str = ""
    deleted_requests_count: int = 0


# delete feedback request
class DeleteFeedbackRequest(BaseModel):
    feedback_id: int = Field(gt=0)


# delete feedback response
class DeleteFeedbackResponse(BaseModel):
    success: bool
    message: str = ""


# delete raw feedback request
class DeleteRawFeedbackRequest(BaseModel):
    raw_feedback_id: int = Field(gt=0)


# delete raw feedback response
class DeleteRawFeedbackResponse(BaseModel):
    success: bool
    message: str = ""


# user provided interaction data from the request
class InteractionData(BaseModel):
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    role: str = "User"
    content: str = ""
    shadow_content: str = ""
    user_action: UserActionType = UserActionType.NONE
    user_action_description: str = ""
    interacted_image_url: str = ""
    image_encoding: str = ""  # base64 encoded image
    tools_used: list[ToolUsed] = Field(default_factory=list)

    @field_validator("interacted_image_url", mode="after")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        """SSRF prevention: if URL is provided, must be safe http(s) or data URI."""
        if not v:
            return v  # empty string is allowed (no image)
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https", "data"):
            raise ValueError(
                f"Image URL scheme must be http, https, or data — got '{parsed.scheme}'"
            )
        if parsed.scheme in ("http", "https"):
            _check_safe_url(v)
        return v


# publish user interaction request
class PublishUserInteractionRequest(BaseModel):
    user_id: NonEmptyStr
    interaction_data_list: list[InteractionData] = Field(min_length=1)
    source: str = ""
    agent_version: str = (
        ""  # this is used for aggregating interactions for generating agent feedback
    )
    session_id: str | None = None  # used for grouping requests together


# publish user interaction response
class PublishUserInteractionResponse(BaseModel):
    success: bool
    message: str = ""


# add raw feedback request/response
class AddRawFeedbackRequest(BaseModel):
    raw_feedbacks: list[RawFeedback] = Field(min_length=1)

    @model_validator(mode="after")
    def check_content_fields(self) -> Self:
        """Ensure each raw feedback has at least one field for indexed_content."""
        for i, rf in enumerate(self.raw_feedbacks):
            has_content = any(
                (
                    rf.indexed_content,
                    rf.when_condition,
                    rf.feedback_content,
                    rf.do_action,
                    rf.do_not_action,
                )
            )
            if not has_content:
                raise ValueError(
                    f"raw_feedbacks[{i}]: at least one of indexed_content, when_condition, "
                    "feedback_content, do_action, or do_not_action must be provided"
                )
        return self


class AddRawFeedbackResponse(BaseModel):
    success: bool
    message: str | None = None
    added_count: int = 0


# add feedback request/response (for aggregated feedbacks)
class AddFeedbackRequest(BaseModel):
    feedbacks: list[Feedback] = Field(min_length=1)


class AddFeedbackResponse(BaseModel):
    success: bool
    message: str | None = None
    added_count: int = 0


class ProfileChangeLogResponse(BaseModel):
    success: bool
    profile_change_logs: list[ProfileChangeLog]


class FeedbackSnapshot(BaseModel):
    """Lightweight feedback snapshot for change log JSONB payloads (excludes embedding and internal status)."""

    feedback_id: int = 0
    feedback_name: str = ""
    agent_version: str = ""
    feedback_content: str = ""
    do_action: str | None = None
    do_not_action: str | None = None
    when_condition: str | None = None
    blocking_issue: BlockingIssue | None = None
    feedback_status: FeedbackStatus = FeedbackStatus.PENDING
    feedback_metadata: str = ""


class FeedbackUpdateEntry(BaseModel):
    """Before/after pair for an updated feedback."""

    before: FeedbackSnapshot
    after: FeedbackSnapshot


class FeedbackAggregationChangeLog(BaseModel):
    """Tracks changes from a single feedback aggregation run."""

    id: int = 0
    created_at: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )
    feedback_name: str
    agent_version: str
    run_mode: Literal["full_archive", "incremental"]
    added_feedbacks: list[FeedbackSnapshot] = Field(default_factory=list)
    removed_feedbacks: list[FeedbackSnapshot] = Field(default_factory=list)
    updated_feedbacks: list[FeedbackUpdateEntry] = Field(default_factory=list)


class FeedbackAggregationChangeLogResponse(BaseModel):
    success: bool
    change_logs: list[FeedbackAggregationChangeLog]


def feedback_to_snapshot(feedback: Feedback) -> FeedbackSnapshot:
    """Convert a Feedback to a lightweight FeedbackSnapshot (excludes embedding and internal status).

    Args:
        feedback (Feedback): Full feedback object

    Returns:
        FeedbackSnapshot: Lightweight snapshot for change log storage
    """
    return FeedbackSnapshot(
        feedback_id=feedback.feedback_id,
        feedback_name=feedback.feedback_name,
        agent_version=feedback.agent_version,
        feedback_content=feedback.feedback_content,
        do_action=feedback.do_action,
        do_not_action=feedback.do_not_action,
        when_condition=feedback.when_condition,
        blocking_issue=feedback.blocking_issue,
        feedback_status=feedback.feedback_status,
        feedback_metadata=feedback.feedback_metadata,
    )


class RunFeedbackAggregationRequest(BaseModel):
    agent_version: NonEmptyStr
    feedback_name: NonEmptyStr


class RunFeedbackAggregationResponse(BaseModel):
    success: bool
    message: str = ""


class RerunProfileGenerationRequest(BaseModel):
    user_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    source: str | None = None
    extractor_names: list[str] | None = None

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class RerunProfileGenerationResponse(BaseModel):
    success: bool
    msg: str | None = None
    profiles_generated: int | None = None
    operation_id: str = "rerun_profile_generation"


class ManualProfileGenerationRequest(BaseModel):
    """Request for manual trigger of regular profile generation.

    Uses window-sized interactions (from config) instead of all interactions.
    Outputs profiles with CURRENT status (not PENDING like rerun).
    """

    user_id: str | None = None
    source: str | None = None
    extractor_names: list[str] | None = None


class ManualProfileGenerationResponse(BaseModel):
    """Response for manual profile generation."""

    success: bool
    msg: str | None = None
    profiles_generated: int | None = None


class ManualFeedbackGenerationRequest(BaseModel):
    """Request for manual trigger of regular feedback generation.

    Uses window-sized interactions (from config) instead of all interactions.
    Outputs feedbacks with CURRENT status (not PENDING like rerun).
    """

    agent_version: NonEmptyStr
    source: str | None = None
    feedback_name: str | None = None  # Optional filter by feedback name


class ManualFeedbackGenerationResponse(BaseModel):
    """Response for manual feedback generation."""

    success: bool
    msg: str | None = None
    feedbacks_generated: int | None = None


class RerunFeedbackGenerationRequest(BaseModel):
    agent_version: NonEmptyStr
    start_time: datetime | None = None
    end_time: datetime | None = None
    feedback_name: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class RerunFeedbackGenerationResponse(BaseModel):
    success: bool
    msg: str | None = None
    feedbacks_generated: int | None = None
    operation_id: str = "rerun_feedback_generation"


class UpgradeProfilesRequest(BaseModel):
    user_id: str | None = None  # None means "all users"
    profile_ids: list[str] | None = None
    only_affected_users: bool = (
        False  # If True, only upgrade users who have pending profiles
    )


class UpgradeProfilesResponse(BaseModel):
    success: bool
    profiles_archived: int = 0
    profiles_promoted: int = 0
    profiles_deleted: int = 0
    message: str = ""


class DowngradeProfilesRequest(BaseModel):
    user_id: str | None = None  # None means "all users"
    profile_ids: list[str] | None = None
    only_affected_users: bool = (
        False  # If True, only downgrade users who have archived profiles
    )


class DowngradeProfilesResponse(BaseModel):
    success: bool
    profiles_demoted: int = 0
    profiles_restored: int = 0
    message: str = ""


class UpgradeRawFeedbacksRequest(BaseModel):
    agent_version: str | None = None
    feedback_name: str | None = None
    archive_current: bool = True


class UpgradeRawFeedbacksResponse(BaseModel):
    success: bool
    raw_feedbacks_deleted: int = 0
    raw_feedbacks_archived: int = 0
    raw_feedbacks_promoted: int = 0
    message: str = ""


class DowngradeRawFeedbacksRequest(BaseModel):
    agent_version: str | None = None
    feedback_name: str | None = None


class DowngradeRawFeedbacksResponse(BaseModel):
    success: bool
    raw_feedbacks_demoted: int = 0
    raw_feedbacks_restored: int = 0
    message: str = ""


# ===============================
# Operation Status Models
# ===============================
class OperationStatusInfo(BaseModel):
    service_name: str
    status: OperationStatus
    started_at: int
    completed_at: int | None = None
    total_users: int = 0
    processed_users: int = 0
    failed_users: int = 0
    current_user_id: str | None = None
    processed_user_ids: list[str] = []
    failed_user_ids: list[dict] = []  # [{"user_id": "...", "error": "..."}]
    request_params: dict = {}
    stats: dict = {}
    error_message: str | None = None
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0)


class GetOperationStatusRequest(BaseModel):
    service_name: str = "profile_generation"


class GetOperationStatusResponse(BaseModel):
    success: bool
    operation_status: OperationStatusInfo | None = None
    msg: str | None = None


class CancelOperationRequest(BaseModel):
    service_name: str | None = None  # None cancels both services


class CancelOperationResponse(BaseModel):
    success: bool
    cancelled_services: list[str] = []
    msg: str | None = None


# ===============================
# Skill Request/Response Models
# ===============================


class RunSkillGenerationRequest(BaseModel):
    agent_version: NonEmptyStr
    feedback_name: NonEmptyStr


class RunSkillGenerationResponse(BaseModel):
    success: bool
    message: str = ""
    skills_generated: int = 0
    skills_updated: int = 0


class UpdateSkillStatusRequest(BaseModel):
    skill_id: int = Field(gt=0)
    skill_status: SkillStatus


class UpdateSkillStatusResponse(BaseModel):
    success: bool
    message: str = ""


class DeleteSkillRequest(BaseModel):
    skill_id: int = Field(gt=0)


class DeleteSkillResponse(BaseModel):
    success: bool
    message: str = ""


class ExportSkillsRequest(BaseModel):
    feedback_name: str | None = None
    agent_version: str | None = None
    skill_status: SkillStatus | None = None


class ExportSkillsResponse(BaseModel):
    success: bool
    markdown: str = ""
    msg: str | None = None
