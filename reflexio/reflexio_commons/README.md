# /user_profiler/reflexio/reflexio_commons
Description: Shared data schemas and configurations used across client and server

## Purpose
Central repository for Pydantic models that define the contract between client and server. All API requests/responses and configuration schemas are defined here to ensure consistency.

## API Schemas
**Directory**: `reflexio_commons/api_schema`
**Purpose**: Pydantic models for API requests and responses

Key files:
- `service_schemas.py`: Core data models
  - **Interaction**: User interaction data (content, actions, images)
  - **UserProfile**: Generated user profile with TTL and embeddings
  - **Request**: Tracks individual requests with metadata (request_id, user_id, source, agent_version)
  - **PublishUserInteractionRequest/Response**: Publishing new interactions
  - **DeleteUserProfileRequest/Response**: Profile deletion
  - **DeleteUserInteractionRequest/Response**: Interaction deletion
  - **InteractionData**: Client-provided interaction data (includes optional `tools_used` list)
  - **ToolUsed**: Tool usage tracking (tool_name, tool_input)
  - **ProfileChangeLog**: History of profile changes
  - **RawFeedback**: Raw developer feedback from interactions (includes optional `blocking_issue`)
  - **Feedback**: Aggregated feedback with status (pending/approved/rejected, includes optional `blocking_issue`)
  - **BlockingIssue**: Capability gap that blocks user request (kind, details)
  - **BlockingIssueKind**: Enum (`MISSING_TOOL`, `PERMISSION_DENIED`, `EXTERNAL_DEPENDENCY`, `POLICY_RESTRICTION`)
  - **AgentSuccessEvaluationResult**: Agent success evaluation results
  - **RunFeedbackAggregationRequest/Response**: Run feedback aggregation
  - Enums: `UserActionType`, `ProfileTimeToLive`, `FeedbackStatus`

- `retriever_schema.py`: Search and retrieval models
  - **SearchUserProfileRequest/Response**: Profile search with query and filters
  - **SearchInteractionRequest/Response**: Interaction search
  - **GetUserProfilesRequest/Response**: Get profiles by user_id
  - **GetInteractionsRequest/Response**: Get interactions by user_id
  - **GetRequestsRequest/Response**: Get requests with filters (user_id, request_id, session_id)
  - **RequestData**: Request with associated interactions
  - **Session**: Group of requests sharing a session_id
  - **GetRawFeedbacksRequest/Response**: Get raw feedbacks
  - **GetFeedbacksRequest/Response**: Get aggregated feedbacks

- `login_schema.py`: Authentication models
  - **Token**: JWT token for authentication
  - User login/registration schemas (with `EmailStr` validation)

- `validators.py`: Reusable Pydantic v2 validator types
  - **NonEmptyStr / OptionalNonEmptyStr**: Reject empty/whitespace-only strings
  - **EmbeddingVector**: Validate embedding is empty or exactly 512 dimensions
  - **SafeHttpUrl**: SSRF-safe URL type (blocks cloud metadata always; blocks private IPs when `REFLEXIO_BLOCK_PRIVATE_URLS=true`)
  - **SanitizedStr / SanitizedNonEmptyStr**: Strip C0 control characters from strings flowing into LLM prompts
  - **TimeRangeValidatorMixin**: Reusable start_time/end_time validation

- `data_schema.py`: Additional data structures

## Configuration Schema
**File**: `config_schema.py`
**Purpose**: YAML configuration file schemas

Key models:
- **Config**: Root configuration object
  - `storage_config`: Storage backend configuration (Local/S3/Supabase)
  - `agent_context_prompt`: Agent environment description
  - `tool_can_use`: List of available tools shared across evaluators and feedback extractors (`ToolUseConfig`)
  - `profile_extractor_configs`: List of profile extraction configurations
  - `agent_feedback_configs`: List of feedback extraction configurations
  - `agent_success_configs`: List of success evaluation configurations
  - `extraction_window_size`: Max interactions to process per batch (optional)
  - `extraction_window_stride`: Min new interactions needed to trigger processing (optional)

- **StorageConfig**: Storage backend options
  - `StorageConfigLocal`: Local file storage (dir_path)
  - `StorageConfigSupabase`: Supabase storage (url, key, db_url)

- **ProfileExtractorConfig**: Profile extraction configuration
  - `profile_content_definition_prompt`: What to extract as profiles
  - `context_prompt`: Additional context
  - `metadata_definition_prompt`: Custom metadata fields

- **AgentFeedbackConfig**: Feedback extraction configuration
  - `feedback_name`: Unique identifier for feedback type
  - `feedback_definition_prompt`: What constitutes this feedback
  - `metadata_definition_prompt`: Custom metadata fields
  - `feedback_aggregator_config`: Aggregation settings

- **AgentSuccessConfig**: Success evaluation configuration
  - `feedback_name`: Unique identifier
  - `success_definition_prompt`: What constitutes success
  - `metadata_definition_prompt`: Custom metadata fields

**Note**: `tool_can_use` lives at root `Config` level (shared across success evaluation and feedback extraction), NOT per-`AgentSuccessConfig`.
