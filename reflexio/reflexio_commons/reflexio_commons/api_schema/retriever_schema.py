from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from reflexio_commons.api_schema.service_schemas import (
    AgentSuccessEvaluationResult,
    Feedback,
    FeedbackStatus,
    Interaction,
    RawFeedback,
    Request,
    Skill,
    SkillStatus,
    Status,
    UserProfile,
)
from reflexio_commons.api_schema.validators import (
    NonEmptyStr,
    TimeRangeValidatorMixin,
)


class SearchInteractionRequest(BaseModel):
    user_id: NonEmptyStr
    request_id: str | None = None
    query: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    top_k: int | None = Field(default=None, gt=0)
    most_recent_k: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class SearchUserProfileRequest(BaseModel):
    user_id: NonEmptyStr
    generated_from_request_id: str | None = None
    query: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    top_k: int | None = Field(default=10, gt=0)
    source: str | None = None
    custom_feature: str | None = None
    extractor_name: str | None = None
    threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    query_rewrite: bool | None = False

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class SearchInteractionResponse(BaseModel):
    success: bool
    interactions: list[Interaction]
    msg: str | None = None


class SearchUserProfileResponse(BaseModel):
    success: bool
    user_profiles: list[UserProfile]
    msg: str | None = None


class GetInteractionsRequest(BaseModel):
    user_id: NonEmptyStr
    start_time: datetime | None = None
    end_time: datetime | None = None
    top_k: int | None = Field(default=30, gt=0)

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class GetInteractionsResponse(BaseModel):
    success: bool
    interactions: list[Interaction]
    msg: str | None = None


class GetUserProfilesRequest(BaseModel):
    user_id: NonEmptyStr
    start_time: datetime | None = None
    end_time: datetime | None = None
    top_k: int | None = Field(default=30, gt=0)
    status_filter: list[Status | None] | None = None

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class GetUserProfilesResponse(BaseModel):
    success: bool
    user_profiles: list[UserProfile]
    msg: str | None = None


class GetProfileStatisticsResponse(BaseModel):
    success: bool
    current_count: int = 0
    pending_count: int = 0
    archived_count: int = 0
    expiring_soon_count: int = 0
    msg: str | None = None


class SetConfigResponse(BaseModel):
    success: bool
    msg: str | None = None


class GetRawFeedbacksRequest(BaseModel):
    limit: int | None = Field(default=100, gt=0)
    feedback_name: str | None = None
    status_filter: list[Status | None] | None = None


class GetRawFeedbacksResponse(BaseModel):
    success: bool
    raw_feedbacks: list[RawFeedback]
    msg: str | None = None


class GetFeedbacksRequest(BaseModel):
    limit: int | None = Field(default=100, gt=0)
    feedback_name: str | None = None
    status_filter: list[Status | None] | None = None
    feedback_status_filter: FeedbackStatus | None = None


class GetFeedbacksResponse(BaseModel):
    success: bool
    feedbacks: list[Feedback]
    msg: str | None = None


class SearchRawFeedbackRequest(BaseModel):
    """Request for searching raw feedbacks with semantic/text search and filtering.

    Args:
        query (str, optional): Query for semantic/text search
        user_id (str, optional): Filter by user (via request_id linkage to requests table)
        agent_version (str, optional): Filter by agent version
        feedback_name (str, optional): Filter by feedback name
        start_time (datetime, optional): Start time for created_at filter
        end_time (datetime, optional): End time for created_at filter
        status_filter (list[Optional[Status]], optional): Filter by status (None for CURRENT, PENDING, ARCHIVED)
        top_k (int, optional): Maximum number of results to return. Defaults to 10
        threshold (float, optional): Similarity threshold for vector search. Defaults to 0.5
    """

    query: str | None = None
    user_id: str | None = None
    agent_version: str | None = None
    feedback_name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status_filter: list[Status | None] | None = None
    top_k: int | None = Field(default=10, gt=0)
    threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    query_rewrite: bool | None = False

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class SearchRawFeedbackResponse(BaseModel):
    """Response for searching raw feedbacks.

    Args:
        success (bool): Whether the search was successful
        raw_feedbacks (list[RawFeedback]): List of matching raw feedbacks
        msg (str, optional): Additional message
    """

    success: bool
    raw_feedbacks: list[RawFeedback]
    msg: str | None = None


class SearchFeedbackRequest(BaseModel):
    """Request for searching aggregated feedbacks with semantic/text search and filtering.

    Args:
        query (str, optional): Query for semantic/text search
        agent_version (str, optional): Filter by agent version
        feedback_name (str, optional): Filter by feedback name
        start_time (datetime, optional): Start time for created_at filter
        end_time (datetime, optional): End time for created_at filter
        status_filter (list[Optional[Status]], optional): Filter by status (None for CURRENT, PENDING, ARCHIVED)
        feedback_status_filter (FeedbackStatus, optional): Filter by feedback status (PENDING, APPROVED, REJECTED)
        top_k (int, optional): Maximum number of results to return. Defaults to 10
        threshold (float, optional): Similarity threshold for vector search. Defaults to 0.5
    """

    query: str | None = None
    agent_version: str | None = None
    feedback_name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    status_filter: list[Status | None] | None = None
    feedback_status_filter: FeedbackStatus | None = None
    top_k: int | None = Field(default=10, gt=0)
    threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    query_rewrite: bool | None = False

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class SearchFeedbackResponse(BaseModel):
    """Response for searching aggregated feedbacks.

    Args:
        success (bool): Whether the search was successful
        feedbacks (list[Feedback]): List of matching feedbacks
        msg (str, optional): Additional message
    """

    success: bool
    feedbacks: list[Feedback]
    msg: str | None = None


class GetAgentSuccessEvaluationResultsRequest(BaseModel):
    limit: int | None = Field(default=100, gt=0)
    agent_version: str | None = None


class GetAgentSuccessEvaluationResultsResponse(BaseModel):
    success: bool
    agent_success_evaluation_results: list[AgentSuccessEvaluationResult]
    msg: str | None = None


class GetRequestsRequest(BaseModel):
    user_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    top_k: int | None = Field(default=30, gt=0)
    offset: int | None = Field(default=0, ge=0)

    @model_validator(mode="after")
    def check_time_range(self) -> Self:
        """Validate that end_time is after start_time."""
        TimeRangeValidatorMixin.validate_time_range(self.start_time, self.end_time)
        return self


class RequestData(BaseModel):
    request: Request
    interactions: list[Interaction]


class Session(BaseModel):
    session_id: str
    requests: list[RequestData]


class GetRequestsResponse(BaseModel):
    success: bool
    sessions: list[Session]
    has_more: bool = False
    msg: str | None = None


class UpdateFeedbackStatusRequest(BaseModel):
    feedback_id: int = Field(gt=0)
    feedback_status: FeedbackStatus


class UpdateFeedbackStatusResponse(BaseModel):
    success: bool
    msg: str | None = None


class TimeSeriesDataPoint(BaseModel):
    """A single data point in a time series."""

    timestamp: int = Field(gt=0)  # Unix timestamp
    value: int = Field(ge=0)  # Count or metric value


class PeriodStats(BaseModel):
    """Statistics for a specific time period."""

    total_profiles: int = Field(ge=0)
    total_interactions: int = Field(ge=0)
    total_feedbacks: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=100.0)  # Percentage (0-100)


class DashboardStats(BaseModel):
    """Comprehensive dashboard statistics including current and previous periods."""

    current_period: PeriodStats
    previous_period: PeriodStats
    interactions_time_series: list[TimeSeriesDataPoint]
    profiles_time_series: list[TimeSeriesDataPoint]
    feedbacks_time_series: list[TimeSeriesDataPoint]
    evaluations_time_series: list[TimeSeriesDataPoint]  # Success rate over time


class GetDashboardStatsRequest(BaseModel):
    """Request for dashboard statistics.

    Args:
        days_back (int): Number of days to include in time series data. Defaults to 30.
    """

    days_back: int | None = Field(default=30, gt=0)


class GetDashboardStatsResponse(BaseModel):
    """Response containing dashboard statistics."""

    success: bool
    stats: DashboardStats | None = None
    msg: str | None = None


# ===============================
# Skill Retriever Models
# ===============================


class GetSkillsRequest(BaseModel):
    limit: int | None = Field(default=100, gt=0)
    feedback_name: str | None = None
    agent_version: str | None = None
    skill_status: SkillStatus | None = None


class GetSkillsResponse(BaseModel):
    success: bool
    skills: list[Skill] = []
    msg: str | None = None


class SearchSkillsRequest(BaseModel):
    query: str | None = None
    feedback_name: str | None = None
    agent_version: str | None = None
    skill_status: SkillStatus | None = None
    threshold: float | None = Field(default=0.5, ge=0.0, le=1.0)
    top_k: int | None = Field(default=10, gt=0)


class SearchSkillsResponse(BaseModel):
    success: bool
    skills: list[Skill] = []
    msg: str | None = None


# ===============================
# Query Rewrite Models
# ===============================


class ConversationTurn(BaseModel):
    """A single turn in a conversation history.

    Args:
        role (str): The role of the speaker (e.g., "user", "agent")
        content (str): The message content
    """

    role: NonEmptyStr
    content: NonEmptyStr


class RewrittenQuery(BaseModel):
    """LLM structured output for query rewriting.

    Args:
        fts_query (str): Expanded FTS query using websearch_to_tsquery syntax (supports OR, phrases, negation)
    """

    fts_query: str


# ===============================
# Unified Search Models
# ===============================


class UnifiedSearchRequest(BaseModel):
    """Request for unified search across all entity types.

    Args:
        query (str): Search query text
        top_k (int, optional): Maximum results per entity type. Defaults to 5
        threshold (float, optional): Similarity threshold for vector search. Defaults to 0.3
        agent_version (str, optional): Filter by agent version (feedbacks, raw_feedbacks, skills)
        feedback_name (str, optional): Filter by feedback name (feedbacks, raw_feedbacks, skills)
        user_id (str, optional): Filter by user ID (profiles, raw_feedbacks)
        conversation_history (list[ConversationTurn], optional): Prior conversation turns for context-aware query rewriting
    """

    query: NonEmptyStr
    top_k: int | None = Field(default=5, gt=0)
    threshold: float | None = Field(default=0.3, ge=0.0, le=1.0)
    agent_version: str | None = None
    feedback_name: str | None = None
    user_id: str | None = None
    conversation_history: list[ConversationTurn] | None = None
    query_rewrite: bool | None = False


class UnifiedSearchResponse(BaseModel):
    """Response containing search results from all entity types.

    Args:
        success (bool): Whether the search was successful
        profiles (list[UserProfile]): Matching user profiles
        feedbacks (list[Feedback]): Matching aggregated feedbacks
        raw_feedbacks (list[RawFeedback]): Matching raw feedbacks
        skills (list[Skill]): Matching skills (empty if skill_generation disabled)
        rewritten_query (str, optional): The FTS query used after rewriting (None if rewrite disabled)
        msg (str, optional): Additional message
    """

    success: bool
    profiles: list[UserProfile] = []
    feedbacks: list[Feedback] = []
    raw_feedbacks: list[RawFeedback] = []
    skills: list[Skill] = []
    rewritten_query: str | None = None
    msg: str | None = None
