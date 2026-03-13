from importlib.metadata import PackageNotFoundError, version

__package_name__ = "reflexio-client"

try:
    __version__ = version(__package_name__)
except PackageNotFoundError:
    # Package is not installed (e.g., running from source without installing)
    __version__ = "0.0.0-dev"


from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    GetSkillsRequest,
    GetSkillsResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
    SearchSkillsRequest,
    SearchSkillsResponse,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    BlockingIssue,
    BlockingIssueKind,
    DeleteSkillRequest,
    DeleteSkillResponse,
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    ExportSkillsRequest,
    ExportSkillsResponse,
    FeedbackStatus,
    Interaction,
    InteractionData,
    ProfileTimeToLive,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    RawFeedback,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
    RunSkillGenerationRequest,
    RunSkillGenerationResponse,
    Skill,
    SkillStatus,
    Status,
    ToolUsed,
    UpdateSkillStatusRequest,
    UpdateSkillStatusResponse,
    UserActionType,
    UserProfile,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    AgentSuccessConfig,
    Config,
    FeedbackAggregatorConfig,
    ProfileExtractorConfig,
    SkillGeneratorConfig,
    StorageConfig,
    StorageConfigLocal,
    StorageConfigSupabase,
    StorageConfigTest,
    ToolUseConfig,
)

from .client import ReflexioClient

debug = False
log = None  # Set to either 'debug' or 'info', controls console logging


__all__ = [
    "ReflexioClient",
    "UserActionType",
    "ProfileTimeToLive",
    "InteractionData",
    "Interaction",
    "UserProfile",
    "PublishUserInteractionRequest",
    "PublishUserInteractionResponse",
    "DeleteUserProfileRequest",
    "DeleteUserProfileResponse",
    "DeleteUserInteractionRequest",
    "DeleteUserInteractionResponse",
    "RawFeedback",
    "BlockingIssue",
    "BlockingIssueKind",
    "AddRawFeedbackRequest",
    "AddRawFeedbackResponse",
    "RerunProfileGenerationRequest",
    "RerunProfileGenerationResponse",
    "RerunFeedbackGenerationRequest",
    "RerunFeedbackGenerationResponse",
    "Skill",
    "SkillStatus",
    "RunSkillGenerationRequest",
    "RunSkillGenerationResponse",
    "UpdateSkillStatusRequest",
    "UpdateSkillStatusResponse",
    "DeleteSkillRequest",
    "DeleteSkillResponse",
    "ExportSkillsRequest",
    "ExportSkillsResponse",
    "GetSkillsRequest",
    "GetSkillsResponse",
    "SearchSkillsRequest",
    "SearchSkillsResponse",
    "SkillGeneratorConfig",
    "ConversationTurn",
    "SearchInteractionRequest",
    "SearchUserProfileRequest",
    "SearchInteractionResponse",
    "SearchUserProfileResponse",
    "StorageConfigTest",
    "StorageConfigLocal",
    "StorageConfigSupabase",
    "StorageConfig",
    "ProfileExtractorConfig",
    "FeedbackAggregatorConfig",
    "AgentFeedbackConfig",
    "AgentSuccessConfig",
    "ToolUseConfig",
    "Config",
    "Status",
    "FeedbackStatus",
    "ToolUsed",
]
