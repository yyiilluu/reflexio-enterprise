from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from reflexio.server.services.query_rewriter import QueryRewriter

from datetime import UTC

from reflexio_commons.api_schema.retriever_schema import (
    DashboardStats,
    GetAgentSuccessEvaluationResultsRequest,
    GetAgentSuccessEvaluationResultsResponse,
    GetDashboardStatsRequest,
    GetDashboardStatsResponse,
    GetFeedbacksRequest,
    GetFeedbacksResponse,
    GetInteractionsRequest,
    GetInteractionsResponse,
    GetProfileStatisticsResponse,
    GetRawFeedbacksRequest,
    GetRawFeedbacksResponse,
    GetRequestsRequest,
    GetRequestsResponse,
    GetUserProfilesRequest,
    GetUserProfilesResponse,
    PeriodStats,
    RequestData,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
    SearchRawFeedbackRequest,
    SearchRawFeedbackResponse,
    SearchSkillsRequest,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
    Session,
    SetConfigResponse,
    TimeSeriesDataPoint,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
    UpdateFeedbackStatusRequest,
    UpdateFeedbackStatusResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    AddFeedbackRequest,
    AddFeedbackResponse,
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    BulkDeleteResponse,
    CancelOperationRequest,
    CancelOperationResponse,
    DeleteFeedbackRequest,
    DeleteFeedbackResponse,
    DeleteFeedbacksByIdsRequest,
    DeleteProfilesByIdsRequest,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbackResponse,
    DeleteRawFeedbacksByIdsRequest,
    DeleteRequestRequest,
    DeleteRequestResponse,
    DeleteRequestsByIdsRequest,
    DeleteSessionRequest,
    DeleteSessionResponse,
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    DowngradeProfilesRequest,
    DowngradeProfilesResponse,
    DowngradeRawFeedbacksRequest,
    DowngradeRawFeedbacksResponse,
    Feedback,
    FeedbackAggregationChangeLogResponse,
    GetOperationStatusRequest,
    GetOperationStatusResponse,
    ManualFeedbackGenerationRequest,
    ManualFeedbackGenerationResponse,
    ManualProfileGenerationRequest,
    ManualProfileGenerationResponse,
    OperationStatus,
    OperationStatusInfo,
    ProfileChangeLogResponse,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    RawFeedback,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
    Skill,
    SkillStatus,
    Status,
    UpgradeProfilesRequest,
    UpgradeProfilesResponse,
    UpgradeRawFeedbacksRequest,
    UpgradeRawFeedbacksResponse,
)
from reflexio_commons.config_schema import Config

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.configurator.configurator import SimpleConfigurator
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio.server.services.generation_service import GenerationService
from reflexio.server.services.operation_state_utils import OperationStateManager
from reflexio.server.services.profile.profile_generation_service import (
    ProfileGenerationService,
)
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)

# Error message for when storage is not configured
STORAGE_NOT_CONFIGURED_MSG = (
    "Storage not configured. Please configure storage in settings first."
)

_T = TypeVar("_T")


def _require_storage(
    response_type: type[_T], *, msg_field: str = "message"
) -> Callable[..., Callable[..., _T]]:
    """Decorator that guards a Reflexio method with storage-configured check and error handling.

    Args:
        response_type: The Pydantic response model to return on failure
        msg_field: Name of the message field on the response ('message' or 'msg')
    """

    def decorator(method: Callable[..., _T]) -> Callable[..., _T]:
        @functools.wraps(method)
        def wrapper(self: Reflexio, *args: Any, **kwargs: Any) -> _T:
            if not self._is_storage_configured():
                return response_type(
                    success=False, **{msg_field: STORAGE_NOT_CONFIGURED_MSG}
                )  # type: ignore[call-arg]
            try:
                return method(self, *args, **kwargs)
            except Exception as e:
                return response_type(success=False, **{msg_field: str(e)})  # type: ignore[call-arg]

        return wrapper

    return decorator  # type: ignore[return-value]


class Reflexio:
    def __init__(
        self,
        org_id: str,
        storage_base_dir: str | None = None,
        configurator: SimpleConfigurator | None = None,
    ) -> None:
        """Initialize Reflexio with organization ID and storage directory.

        Args:
            org_id (str): Organization ID
            storage_base_dir (str, optional): Base directory for storing data
        """
        self.org_id = org_id
        self.storage_base_dir = storage_base_dir
        self.request_context = RequestContext(
            org_id=org_id, storage_base_dir=storage_base_dir, configurator=configurator
        )

        # Create single LLM client for all services
        model_setting = SiteVarManager().get_site_var("llm_model_setting")

        # Get API key config and LLM config from configuration if available
        config = self.request_context.configurator.get_config()
        api_key_config = config.api_key_config if config else None
        config_llm_config = config.llm_config if config else None

        # Use LLM config override if available, otherwise fallback to site var
        generation_model_name = (
            config_llm_config.generation_model_name
            if config_llm_config and config_llm_config.generation_model_name
            else (
                model_setting.get("default_generation_model_name", "gpt-5-mini")
                if isinstance(model_setting, dict)
                else "gpt-5-mini"
            )
        )

        llm_config = LiteLLMConfig(
            model=generation_model_name,
            api_key_config=api_key_config,
        )
        self.llm_client = LiteLLMClient(llm_config)

    def _is_storage_configured(self) -> bool:
        """Check if storage is configured and available.

        Returns:
            bool: True if storage is configured, False otherwise
        """
        return self.request_context.is_storage_configured()

    def _get_storage(self) -> BaseStorage:
        """Return storage, raising if not configured."""
        storage = self.request_context.storage
        if storage is None:
            raise RuntimeError(STORAGE_NOT_CONFIGURED_MSG)
        return storage

    def _get_query_rewriter(self) -> QueryRewriter:
        """Lazily create and cache a QueryRewriter instance.

        Returns:
            QueryRewriter: Cached rewriter instance
        """
        if not hasattr(self, "_query_rewriter"):
            from reflexio.server.services.query_rewriter import QueryRewriter

            config = self.request_context.configurator.get_config()
            api_key_config = config.api_key_config if config else None
            self._query_rewriter = QueryRewriter(
                api_key_config=api_key_config,
                prompt_manager=self.request_context.prompt_manager,
            )
        return self._query_rewriter

    def _rewrite_query(self, query: str | None, enabled: bool = False) -> str | None:
        """Rewrite a search query using the query rewriter if enabled.

        Returns the rewritten FTS query, or None if rewriting is disabled,
        the query is empty, or rewriting fails.

        Args:
            query (str, optional): The original search query
            enabled (bool): Whether query rewriting is enabled for this request

        Returns:
            str or None: Rewritten FTS query, or None to use original query
        """
        if not query or not enabled:
            return None

        rewriter = self._get_query_rewriter()
        result = rewriter.rewrite(query, enabled=True)
        # Only return if different from original
        if result.fts_query != query:
            return result.fts_query
        return None

    def publish_interaction(
        self,
        request: PublishUserInteractionRequest | dict,
    ) -> PublishUserInteractionResponse:
        """Publish user interactions.

        Args:
            request (Union[PublishUserInteractionRequest, dict]): The publish user interaction request

        Returns:
            PublishUserInteractionResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return PublishUserInteractionResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        generation_service = GenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
        )
        try:
            # Convert dict to PublishUserInteractionRequest if needed
            if isinstance(request, dict):
                request = PublishUserInteractionRequest(**request)
            generation_service.run(request)
            return PublishUserInteractionResponse(success=True)
        except Exception as e:
            return PublishUserInteractionResponse(success=False, message=str(e))

    def search_interactions(
        self,
        request: SearchInteractionRequest | dict,
    ) -> SearchInteractionResponse:
        """Search for user interactions.

        Args:
            request (SearchInteractionRequest): The search request

        Returns:
            SearchInteractionResponse: Response containing matching interactions
        """
        if not self._is_storage_configured():
            return SearchInteractionResponse(
                success=True, interactions=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = SearchInteractionRequest(**request)
        interactions = self._get_storage().search_interaction(request)
        return SearchInteractionResponse(success=True, interactions=interactions)

    def search_profiles(
        self,
        request: SearchUserProfileRequest | dict,
        status_filter: list[Status | None] | None = None,
    ) -> SearchUserProfileResponse:
        """Search for user profiles.

        Args:
            request (SearchUserProfileRequest): The search request
            status_filter (Optional[list[Optional[Status]]]): Filter profiles by status. Defaults to [None] for current profiles only.

        Returns:
            SearchUserProfileResponse: Response containing matching profiles
        """
        if not self._is_storage_configured():
            return SearchUserProfileResponse(
                success=True, user_profiles=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = SearchUserProfileRequest(**request)
        if status_filter is None:
            status_filter = [None]  # Default to current profiles
        rewritten = self._rewrite_query(
            request.query, enabled=bool(request.query_rewrite)
        )
        if rewritten:
            request = request.model_copy(update={"query": rewritten})
        profiles = self._get_storage().search_user_profile(
            request, status_filter=status_filter
        )
        return SearchUserProfileResponse(success=True, user_profiles=profiles)

    def get_profile_change_logs(self) -> ProfileChangeLogResponse:
        """Get profile change logs.

        Returns:
            ProfileChangeLogResponse: Response containing profile change logs
        """
        if not self._is_storage_configured():
            return ProfileChangeLogResponse(success=True, profile_change_logs=[])
        changelogs = self._get_storage().get_profile_change_logs()
        return ProfileChangeLogResponse(success=True, profile_change_logs=changelogs)

    def get_feedback_aggregation_change_logs(
        self, feedback_name: str, agent_version: str
    ) -> FeedbackAggregationChangeLogResponse:
        """Get feedback aggregation change logs.

        Args:
            feedback_name (str): Feedback name to filter by
            agent_version (str): Agent version to filter by

        Returns:
            FeedbackAggregationChangeLogResponse: Response containing change logs
        """
        if not self._is_storage_configured():
            return FeedbackAggregationChangeLogResponse(success=True, change_logs=[])
        change_logs = self._get_storage().get_feedback_aggregation_change_logs(
            feedback_name=feedback_name, agent_version=agent_version
        )
        return FeedbackAggregationChangeLogResponse(
            success=True, change_logs=change_logs
        )

    @_require_storage(DeleteUserProfileResponse)
    def delete_profile(
        self,
        request: DeleteUserProfileRequest | dict,
    ) -> DeleteUserProfileResponse:
        """Delete user profiles.

        Args:
            request (DeleteUserProfileRequest): The delete request

        Returns:
            DeleteUserProfileResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteUserProfileRequest(**request)
        self._get_storage().delete_user_profile(request)
        return DeleteUserProfileResponse(success=True)

    @_require_storage(DeleteUserInteractionResponse)
    def delete_interaction(
        self,
        request: DeleteUserInteractionRequest | dict,
    ) -> DeleteUserInteractionResponse:
        """Delete user interactions.

        Args:
            request (DeleteUserInteractionRequest): The delete request

        Returns:
            DeleteUserInteractionResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteUserInteractionRequest(**request)
        self._get_storage().delete_user_interaction(request)
        return DeleteUserInteractionResponse(success=True)

    @_require_storage(DeleteRequestResponse)
    def delete_request(
        self,
        request: DeleteRequestRequest | dict,
    ) -> DeleteRequestResponse:
        """Delete a request and all its associated interactions.

        Args:
            request (DeleteRequestRequest): The delete request containing request_id

        Returns:
            DeleteRequestResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteRequestRequest(**request)
        self._get_storage().delete_request(request.request_id)
        return DeleteRequestResponse(success=True)

    @_require_storage(DeleteSessionResponse)
    def delete_session(
        self,
        request: DeleteSessionRequest | dict,
    ) -> DeleteSessionResponse:
        """Delete all requests and interactions in a session.

        Args:
            request (DeleteSessionRequest): The delete request containing session_id

        Returns:
            DeleteSessionResponse: Response containing success status, message, and deleted count
        """
        if isinstance(request, dict):
            request = DeleteSessionRequest(**request)
        deleted_count = self._get_storage().delete_session(request.session_id)
        return DeleteSessionResponse(success=True, deleted_requests_count=deleted_count)

    @_require_storage(DeleteFeedbackResponse)
    def delete_feedback(
        self,
        request: DeleteFeedbackRequest | dict,
    ) -> DeleteFeedbackResponse:
        """Delete a feedback by ID.

        Args:
            request (DeleteFeedbackRequest): The delete request containing feedback_id

        Returns:
            DeleteFeedbackResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteFeedbackRequest(**request)
        self._get_storage().delete_feedback(request.feedback_id)
        return DeleteFeedbackResponse(success=True)

    @_require_storage(DeleteRawFeedbackResponse)
    def delete_raw_feedback(
        self,
        request: DeleteRawFeedbackRequest | dict,
    ) -> DeleteRawFeedbackResponse:
        """Delete a raw feedback by ID.

        Args:
            request (DeleteRawFeedbackRequest): The delete request containing raw_feedback_id

        Returns:
            DeleteRawFeedbackResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteRawFeedbackRequest(**request)
        self._get_storage().delete_raw_feedback(request.raw_feedback_id)
        return DeleteRawFeedbackResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_all_interactions_bulk(self) -> BulkDeleteResponse:
        """Delete all requests and their associated interactions.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        self._get_storage().delete_all_requests()
        return BulkDeleteResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_all_profiles_bulk(self) -> BulkDeleteResponse:
        """Delete all profiles.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        self._get_storage().delete_all_profiles()
        return BulkDeleteResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_all_feedbacks_bulk(self) -> BulkDeleteResponse:
        """Delete all feedbacks (both raw and aggregated).

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        self._get_storage().delete_all_feedbacks()
        self._get_storage().delete_all_raw_feedbacks()
        return BulkDeleteResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_requests_by_ids(
        self,
        request: DeleteRequestsByIdsRequest | dict,
    ) -> BulkDeleteResponse:
        """Delete requests by their IDs.

        Args:
            request (DeleteRequestsByIdsRequest): The delete request containing request_ids

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        if isinstance(request, dict):
            request = DeleteRequestsByIdsRequest(**request)
        deleted = self._get_storage().delete_requests_by_ids(request.request_ids)
        return BulkDeleteResponse(success=True, deleted_count=deleted)

    @_require_storage(BulkDeleteResponse)
    def delete_profiles_by_ids(
        self,
        request: DeleteProfilesByIdsRequest | dict,
    ) -> BulkDeleteResponse:
        """Delete profiles by their IDs.

        Args:
            request (DeleteProfilesByIdsRequest): The delete request containing profile_ids

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        if isinstance(request, dict):
            request = DeleteProfilesByIdsRequest(**request)
        deleted = self._get_storage().delete_profiles_by_ids(request.profile_ids)
        return BulkDeleteResponse(success=True, deleted_count=deleted)

    @_require_storage(BulkDeleteResponse)
    def delete_feedbacks_by_ids_bulk(
        self,
        request: DeleteFeedbacksByIdsRequest | dict,
    ) -> BulkDeleteResponse:
        """Delete aggregated feedbacks by their IDs.

        Args:
            request (DeleteFeedbacksByIdsRequest): The delete request containing feedback_ids

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        if isinstance(request, dict):
            request = DeleteFeedbacksByIdsRequest(**request)
        self._get_storage().delete_feedbacks_by_ids(request.feedback_ids)
        return BulkDeleteResponse(success=True, deleted_count=len(request.feedback_ids))

    @_require_storage(BulkDeleteResponse)
    def delete_raw_feedbacks_by_ids_bulk(
        self,
        request: DeleteRawFeedbacksByIdsRequest | dict,
    ) -> BulkDeleteResponse:
        """Delete raw feedbacks by their IDs.

        Args:
            request (DeleteRawFeedbacksByIdsRequest): The delete request containing raw_feedback_ids

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        if isinstance(request, dict):
            request = DeleteRawFeedbacksByIdsRequest(**request)
        deleted = self._get_storage().delete_raw_feedbacks_by_ids(
            request.raw_feedback_ids
        )
        return BulkDeleteResponse(success=True, deleted_count=deleted)

    def get_interactions(
        self,
        request: GetInteractionsRequest | dict,
    ) -> GetInteractionsResponse:
        """Get user interactions.

        Args:
            request (GetInteractionsRequest): The get request

        Returns:
            GetInteractionsResponse: Response containing user interactions
        """
        if not self._is_storage_configured():
            return GetInteractionsResponse(
                success=True, interactions=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetInteractionsRequest(**request)
        interactions = self._get_storage().get_user_interaction(request.user_id)
        interactions = sorted(interactions, key=lambda x: x.created_at, reverse=True)

        # Apply time filters
        if request.start_time:
            interactions = [
                i
                for i in interactions
                if i.created_at >= int(request.start_time.timestamp())
            ]
        if request.end_time:
            interactions = [
                i
                for i in interactions
                if i.created_at <= int(request.end_time.timestamp())
            ]

        # Apply top_k limit
        if request.top_k:
            interactions = interactions[: request.top_k]

        return GetInteractionsResponse(success=True, interactions=interactions)

    def get_profiles(
        self,
        request: GetUserProfilesRequest | dict,
        status_filter: list[Status | None] | None = None,
    ) -> GetUserProfilesResponse:
        """Get user profiles.

        Args:
            request (GetUserProfilesRequest): The get request
            status_filter (Optional[list[Optional[Status]]]): Filter profiles by status. Defaults to [None] for current profiles only.
                If provided, takes precedence over request.status_filter.

        Returns:
            GetUserProfilesResponse: Response containing user profiles
        """
        if not self._is_storage_configured():
            return GetUserProfilesResponse(
                success=True, user_profiles=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetUserProfilesRequest(**request)

        # Priority: parameter > request.status_filter > default [None]
        if status_filter is None:
            if hasattr(request, "status_filter") and request.status_filter is not None:
                status_filter = request.status_filter
            else:
                status_filter = [None]  # Default to current profiles

        profiles = self._get_storage().get_user_profile(
            request.user_id, status_filter=status_filter
        )
        profiles = sorted(
            profiles, key=lambda x: x.last_modified_timestamp, reverse=True
        )

        # Apply time filters
        if request.start_time:
            profiles = [
                p
                for p in profiles
                if p.last_modified_timestamp >= int(request.start_time.timestamp())
            ]
        if request.end_time:
            profiles = [
                p
                for p in profiles
                if p.last_modified_timestamp <= int(request.end_time.timestamp())
            ]

        # Apply top_k limit
        if request.top_k:
            profiles = sorted(
                profiles, key=lambda x: x.last_modified_timestamp, reverse=True
            )[: request.top_k]

        return GetUserProfilesResponse(success=True, user_profiles=profiles)

    def get_all_profiles(
        self,
        limit: int = 100,
        status_filter: list[Status | None] | None = None,
    ) -> GetUserProfilesResponse:
        """Get all user profiles across all users.

        Args:
            limit (int, optional): Maximum number of profiles to return. Defaults to 100.
            status_filter (Optional[list[Optional[Status]]]): Filter profiles by status. Defaults to [None] for current profiles only.

        Returns:
            GetUserProfilesResponse: Response containing all user profiles
        """
        if not self._is_storage_configured():
            return GetUserProfilesResponse(
                success=True, user_profiles=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if status_filter is None:
            status_filter = [None]  # Default to current profiles
        profiles = self._get_storage().get_all_profiles(
            limit=limit, status_filter=status_filter
        )
        profiles = sorted(
            profiles, key=lambda x: x.last_modified_timestamp, reverse=True
        )
        return GetUserProfilesResponse(success=True, user_profiles=profiles)

    def get_all_interactions(self, limit: int = 100) -> GetInteractionsResponse:
        """Get all user interactions across all users.

        Args:
            limit (int, optional): Maximum number of interactions to return. Defaults to 100.

        Returns:
            GetInteractionsResponse: Response containing all user interactions
        """
        if not self._is_storage_configured():
            return GetInteractionsResponse(
                success=True, interactions=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        interactions = self._get_storage().get_all_interactions(limit=limit)
        interactions = sorted(interactions, key=lambda x: x.created_at, reverse=True)
        return GetInteractionsResponse(success=True, interactions=interactions)

    def get_dashboard_stats(
        self, request: GetDashboardStatsRequest | dict
    ) -> GetDashboardStatsResponse:
        """Get dashboard statistics including counts and time-series data.

        Args:
            request (Union[GetDashboardStatsRequest, dict]): Request containing days_back and granularity

        Returns:
            GetDashboardStatsResponse: Response containing dashboard statistics
        """
        if not self._is_storage_configured():
            # Return empty stats when storage is not configured
            empty_period = PeriodStats(
                total_profiles=0,
                total_interactions=0,
                total_feedbacks=0,
                success_rate=0.0,
            )
            empty_stats = DashboardStats(
                current_period=empty_period,
                previous_period=empty_period,
                interactions_time_series=[],
                profiles_time_series=[],
                feedbacks_time_series=[],
                evaluations_time_series=[],
            )
            return GetDashboardStatsResponse(
                success=True, stats=empty_stats, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        try:
            # Convert dict to request object if needed
            if isinstance(request, dict):
                request = GetDashboardStatsRequest(**request)

            # Get stats from storage layer
            stats_dict = self._get_storage().get_dashboard_stats(
                days_back=request.days_back or 30
            )

            # Convert dict to Pydantic models
            current_period = PeriodStats(**stats_dict["current_period"])
            previous_period = PeriodStats(**stats_dict["previous_period"])

            interactions_time_series = [
                TimeSeriesDataPoint(**ts)
                for ts in stats_dict["interactions_time_series"]
            ]
            profiles_time_series = [
                TimeSeriesDataPoint(**ts) for ts in stats_dict["profiles_time_series"]
            ]
            feedbacks_time_series = [
                TimeSeriesDataPoint(**ts) for ts in stats_dict["feedbacks_time_series"]
            ]
            evaluations_time_series = [
                TimeSeriesDataPoint(**ts)
                for ts in stats_dict["evaluations_time_series"]
            ]

            # Build dashboard stats object
            dashboard_stats = DashboardStats(
                current_period=current_period,
                previous_period=previous_period,
                interactions_time_series=interactions_time_series,
                profiles_time_series=profiles_time_series,
                feedbacks_time_series=feedbacks_time_series,
                evaluations_time_series=evaluations_time_series,
            )

            return GetDashboardStatsResponse(success=True, stats=dashboard_stats)

        except Exception as e:
            return GetDashboardStatsResponse(
                success=False, msg=f"Failed to get dashboard stats: {str(e)}"
            )

    def run_feedback_aggregation(self, agent_version: str, feedback_name: str) -> None:
        """Run feedback aggregation for a given agent version.

        Args:
            agent_version (str): The agent version
            feedback_name (str): The feedback name

        Raises:
            ValueError: If storage is not configured
        """
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        feedback_aggregator = FeedbackAggregator(
            llm_client=self.llm_client,
            request_context=self.request_context,
            agent_version=agent_version,
        )
        feedback_aggregator_request = FeedbackAggregatorRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
            rerun=True,
        )
        feedback_aggregator.run(feedback_aggregator_request)

    def run_skill_generation(self, agent_version: str, feedback_name: str) -> dict:
        """Run skill generation for a given agent version.

        Args:
            agent_version (str): The agent version
            feedback_name (str): The feedback name

        Raises:
            ValueError: If storage is not configured
        """
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        from reflexio.server.services.feedback.feedback_service_utils import (
            SkillGeneratorRequest,
        )
        from reflexio.server.services.feedback.skill_generator import SkillGenerator

        skill_generator = SkillGenerator(
            llm_client=self.llm_client,
            request_context=self.request_context,
            agent_version=agent_version,
        )
        skill_generator_request = SkillGeneratorRequest(
            agent_version=agent_version,
            feedback_name=feedback_name,
            rerun=True,
        )
        return skill_generator.run(skill_generator_request)

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

    def set_config(self, config: Config | dict) -> SetConfigResponse:
        """Set configuration for the organization.

        Args:
            config (Union[Config, dict]): The configuration to set

        Returns:
            dict: Response containing success status and message
        """
        try:
            if isinstance(config, dict):
                config = Config(**config)

            # Validate storage connection before setting config.
            # If no storage_config provided, preserve the existing one (callers
            # like get_config() don't expose storage_config for security).
            storage_config = config.storage_config
            if storage_config is None:
                storage_config = self.request_context.configurator.get_current_storage_configuration()
                config.storage_config = storage_config

            # Check if storage config is ready to test
            if not self.request_context.configurator.is_storage_config_ready_to_test(
                storage_config=storage_config
            ):
                return SetConfigResponse(
                    success=False, msg="Storage configuration is incomplete"
                )

            # Test and initialize storage connection
            (
                success,
                error_msg,
            ) = self.request_context.configurator.test_and_init_storage_config(
                storage_config=storage_config
            )

            if not success:
                return SetConfigResponse(
                    success=False,
                    msg=f"Failed to validate storage connection: {error_msg}",
                )

            # Only set config if validation passed
            self.request_context.configurator.set_config(config)

            return SetConfigResponse(success=True, msg="Configuration set successfully")
        except Exception as e:
            return SetConfigResponse(
                success=False, msg=f"Failed to set configuration: {str(e)}"
            )

    def get_config(self) -> Config:
        """Get configuration for the organization.

        Returns:
            Config: The current configuration
        """
        return self.request_context.configurator.get_config()

    def get_raw_feedbacks(
        self,
        request: GetRawFeedbacksRequest | dict,
    ) -> GetRawFeedbacksResponse:
        """Get raw feedbacks.

        Args:
            request (Union[GetRawFeedbacksRequest, dict]): The get request

        Returns:
            GetRawFeedbacksResponse: Response containing raw feedbacks
        """
        if not self._is_storage_configured():
            return GetRawFeedbacksResponse(
                success=True, raw_feedbacks=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetRawFeedbacksRequest(**request)

        try:
            raw_feedbacks = self._get_storage().get_raw_feedbacks(
                limit=request.limit or 100,
                feedback_name=request.feedback_name,
                status_filter=request.status_filter,
            )
            return GetRawFeedbacksResponse(success=True, raw_feedbacks=raw_feedbacks)
        except Exception as e:
            return GetRawFeedbacksResponse(success=False, raw_feedbacks=[], msg=str(e))

    def add_raw_feedback(
        self,
        request: AddRawFeedbackRequest | dict,
    ) -> AddRawFeedbackResponse:
        """Add raw feedback directly to storage.

        Args:
            request (Union[AddRawFeedbackRequest, dict]): The add request containing raw feedbacks

        Returns:
            AddRawFeedbackResponse: Response containing success status, message, and count of added feedbacks
        """
        if not self._is_storage_configured():
            return AddRawFeedbackResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = AddRawFeedbackRequest(**request)

        try:
            # Normalize raw feedbacks - preserve user-provided fields, auto-set indexed_content
            normalized_feedbacks = []
            for rf in request.raw_feedbacks:
                # Ensure indexed_content always has a value for clustering/embedding
                indexed_content = (
                    rf.indexed_content
                    or rf.when_condition
                    or rf.feedback_content
                    or " ".join(filter(None, [rf.do_action, rf.do_not_action]))
                    or ""
                )

                normalized_feedbacks.append(
                    RawFeedback(
                        user_id=rf.user_id,
                        agent_version=rf.agent_version,
                        request_id=rf.request_id,
                        feedback_name=rf.feedback_name,
                        created_at=rf.created_at,
                        feedback_content=rf.feedback_content,
                        do_action=rf.do_action,
                        do_not_action=rf.do_not_action,
                        when_condition=rf.when_condition,
                        status=rf.status,
                        source=rf.source,
                        blocking_issue=rf.blocking_issue,
                        indexed_content=indexed_content,
                        source_interaction_ids=rf.source_interaction_ids,
                    )
                )

            self._get_storage().save_raw_feedbacks(normalized_feedbacks)
            return AddRawFeedbackResponse(
                success=True, added_count=len(normalized_feedbacks)
            )
        except Exception as e:
            return AddRawFeedbackResponse(success=False, message=str(e))

    def add_feedback(
        self,
        request: AddFeedbackRequest | dict,
    ) -> AddFeedbackResponse:
        """Add aggregated feedback directly to storage.

        Args:
            request (Union[AddFeedbackRequest, dict]): The add request containing feedbacks

        Returns:
            AddFeedbackResponse: Response containing success status, message, and count of added feedbacks
        """
        if not self._is_storage_configured():
            return AddFeedbackResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = AddFeedbackRequest(**request)

        try:
            # Normalize feedbacks - only keep required fields, reset others to defaults
            normalized_feedbacks = [
                Feedback(
                    agent_version=fb.agent_version,
                    feedback_name=fb.feedback_name,
                    feedback_content=fb.feedback_content,
                    feedback_status=fb.feedback_status,
                    feedback_metadata=(fb.feedback_metadata or ""),
                )
                for fb in request.feedbacks
            ]

            self._get_storage().save_feedbacks(normalized_feedbacks)
            return AddFeedbackResponse(
                success=True, added_count=len(normalized_feedbacks)
            )
        except Exception as e:
            return AddFeedbackResponse(success=False, message=str(e))

    def get_feedbacks(
        self,
        request: GetFeedbacksRequest | dict,
    ) -> GetFeedbacksResponse:
        """Get feedbacks.

        Args:
            request (Union[GetFeedbacksRequest, dict]): The get request

        Returns:
            GetFeedbacksResponse: Response containing feedbacks
        """
        if not self._is_storage_configured():
            return GetFeedbacksResponse(
                success=True, feedbacks=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetFeedbacksRequest(**request)

        try:
            feedbacks = self._get_storage().get_feedbacks(
                limit=request.limit or 100,
                feedback_name=request.feedback_name,
                status_filter=request.status_filter,
                feedback_status_filter=[request.feedback_status_filter]
                if request.feedback_status_filter
                else None,
            )
            return GetFeedbacksResponse(success=True, feedbacks=feedbacks)
        except Exception as e:
            return GetFeedbacksResponse(success=False, feedbacks=[], msg=str(e))

    def search_raw_feedbacks(
        self,
        request: SearchRawFeedbackRequest | dict,
    ) -> SearchRawFeedbackResponse:
        """Search raw feedbacks with advanced filtering and semantic search.

        Args:
            request (Union[SearchRawFeedbackRequest, dict]): The search request

        Returns:
            SearchRawFeedbackResponse: Response containing matching raw feedbacks
        """
        if not self._is_storage_configured():
            return SearchRawFeedbackResponse(
                success=True, raw_feedbacks=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = SearchRawFeedbackRequest(**request)

        try:
            rewritten = self._rewrite_query(
                request.query, enabled=bool(request.query_rewrite)
            )
            if rewritten:
                request = request.model_copy(update={"query": rewritten})
            raw_feedbacks = self._get_storage().search_raw_feedbacks(request)
            return SearchRawFeedbackResponse(success=True, raw_feedbacks=raw_feedbacks)
        except Exception as e:
            return SearchRawFeedbackResponse(
                success=False, raw_feedbacks=[], msg=str(e)
            )

    def search_feedbacks(
        self,
        request: SearchFeedbackRequest | dict,
    ) -> SearchFeedbackResponse:
        """Search feedbacks with advanced filtering and semantic search.

        Args:
            request (Union[SearchFeedbackRequest, dict]): The search request

        Returns:
            SearchFeedbackResponse: Response containing matching feedbacks
        """
        if not self._is_storage_configured():
            return SearchFeedbackResponse(
                success=True, feedbacks=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = SearchFeedbackRequest(**request)

        try:
            rewritten = self._rewrite_query(
                request.query, enabled=bool(request.query_rewrite)
            )
            if rewritten:
                request = request.model_copy(update={"query": rewritten})
            feedbacks = self._get_storage().search_feedbacks(request)
            return SearchFeedbackResponse(success=True, feedbacks=feedbacks)
        except Exception as e:
            return SearchFeedbackResponse(success=False, feedbacks=[], msg=str(e))

    def get_agent_success_evaluation_results(
        self,
        request: GetAgentSuccessEvaluationResultsRequest | dict,
    ) -> GetAgentSuccessEvaluationResultsResponse:
        """Get agent success evaluation results.

        Args:
            request (Union[GetAgentSuccessEvaluationResultsRequest, dict]): The get request

        Returns:
            GetAgentSuccessEvaluationResultsResponse: Response containing agent success evaluation results
        """
        if not self._is_storage_configured():
            return GetAgentSuccessEvaluationResultsResponse(
                success=True,
                agent_success_evaluation_results=[],
                msg=STORAGE_NOT_CONFIGURED_MSG,
            )
        if isinstance(request, dict):
            request = GetAgentSuccessEvaluationResultsRequest(**request)

        try:
            results = self._get_storage().get_agent_success_evaluation_results(
                limit=request.limit or 100, agent_version=request.agent_version
            )
            return GetAgentSuccessEvaluationResultsResponse(
                success=True, agent_success_evaluation_results=results
            )
        except Exception as e:
            return GetAgentSuccessEvaluationResultsResponse(
                success=False, agent_success_evaluation_results=[], msg=str(e)
            )

    def get_requests(
        self,
        request: GetRequestsRequest | dict,
    ) -> GetRequestsResponse:
        """Get requests with their associated interactions, grouped by session.

        Args:
            request (Union[GetRequestsRequest, dict]): The get request

        Returns:
            GetRequestsResponse: Response containing requests grouped by session with their interactions
        """
        if not self._is_storage_configured():
            return GetRequestsResponse(
                success=True, sessions=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetRequestsRequest(**request)

        try:
            # Get requests with interactions from storage (already grouped by session)
            grouped_results = self._get_storage().get_sessions(
                user_id=request.user_id,
                request_id=request.request_id,
                session_id=request.session_id,
                start_time=(
                    int(request.start_time.timestamp()) if request.start_time else None
                ),
                end_time=(
                    int(request.end_time.timestamp()) if request.end_time else None
                ),
                top_k=request.top_k,
                offset=request.offset or 0,
            )

            # Transform the dictionary into Session objects
            sessions = []
            for group_name, request_interaction_data_models in grouped_results.items():
                # Convert each RequestInteractionDataModel to RequestData
                request_data_list = [
                    RequestData(
                        request=request_interaction.request,
                        interactions=request_interaction.interactions,
                    )
                    for request_interaction in request_interaction_data_models
                ]
                sessions.append(
                    Session(session_id=group_name, requests=request_data_list)
                )

            # Determine has_more: count total requests returned across all groups
            total_returned = sum(len(s.requests) for s in sessions)
            effective_limit = request.top_k or 100
            has_more = total_returned >= effective_limit

            return GetRequestsResponse(
                success=True,
                sessions=sessions,
                has_more=has_more,
            )
        except Exception as e:
            return GetRequestsResponse(success=False, sessions=[], msg=str(e))

    @_require_storage(UpdateFeedbackStatusResponse, msg_field="msg")
    def update_feedback_status(
        self,
        request: UpdateFeedbackStatusRequest | dict,
    ) -> UpdateFeedbackStatusResponse:
        """Update the status of a specific feedback.

        Args:
            request (Union[UpdateFeedbackStatusRequest, dict]): The update request

        Returns:
            UpdateFeedbackStatusResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = UpdateFeedbackStatusRequest(**request)
        self._get_storage().update_feedback_status(
            feedback_id=request.feedback_id,
            feedback_status=request.feedback_status,
        )
        return UpdateFeedbackStatusResponse(success=True)

    def _run_generation_service(
        self,
        request: Any,
        request_type: type,
        service_cls: type,
        output_pending: bool,
        run_method: str,
    ) -> Any:
        """Shared logic for rerun and manual generation endpoints."""
        if isinstance(request, dict):
            request = request_type(**request)
        service = service_cls(
            llm_client=self.llm_client,
            request_context=self.request_context,
            allow_manual_trigger=True,
            output_pending_status=output_pending,
        )
        return getattr(service, run_method)(request)

    @_require_storage(RerunProfileGenerationResponse, msg_field="msg")
    def rerun_profile_generation(
        self,
        request: RerunProfileGenerationRequest | dict,
    ) -> RerunProfileGenerationResponse:
        """Rerun profile generation for one or all users with filtered interactions.

        Args:
            request (Union[RerunProfileGenerationRequest, dict]): The rerun request containing optional user_id, time filters, and source.
                If user_id is None, reruns for all users.

        Returns:
            RerunProfileGenerationResponse: Response containing success status, message, and count of profiles generated
        """
        return self._run_generation_service(
            request,
            RerunProfileGenerationRequest,
            ProfileGenerationService,
            output_pending=True,
            run_method="run_rerun",
        )

    @_require_storage(ManualProfileGenerationResponse, msg_field="msg")
    def manual_profile_generation(
        self,
        request: ManualProfileGenerationRequest | dict,
    ) -> ManualProfileGenerationResponse:
        """Manually trigger profile generation with window-sized interactions and CURRENT output.

        Args:
            request (Union[ManualProfileGenerationRequest, dict]): The request containing
                optional user_id, source, and extractor_names.
                If user_id is None, runs for all users.

        Returns:
            ManualProfileGenerationResponse: Response containing success status, message,
                and count of profiles generated
        """
        return self._run_generation_service(
            request,
            ManualProfileGenerationRequest,
            ProfileGenerationService,
            output_pending=False,
            run_method="run_manual_regular",
        )

    @_require_storage(RerunFeedbackGenerationResponse, msg_field="msg")
    def rerun_feedback_generation(
        self,
        request: RerunFeedbackGenerationRequest | dict,
    ) -> RerunFeedbackGenerationResponse:
        """Rerun feedback generation with filtered interactions.

        Args:
            request (Union[RerunFeedbackGenerationRequest, dict]): The rerun request containing agent_version,
                optional time filters, and optional feedback_name.

        Returns:
            RerunFeedbackGenerationResponse: Response containing success status, message, and count of feedbacks generated
        """
        return self._run_generation_service(
            request,
            RerunFeedbackGenerationRequest,
            FeedbackGenerationService,
            output_pending=True,
            run_method="run_rerun",
        )

    @_require_storage(ManualFeedbackGenerationResponse, msg_field="msg")
    def manual_feedback_generation(
        self,
        request: ManualFeedbackGenerationRequest | dict,
    ) -> ManualFeedbackGenerationResponse:
        """Manually trigger feedback generation with window-sized interactions and CURRENT output.

        Args:
            request (Union[ManualFeedbackGenerationRequest, dict]): The generation request containing:
                - agent_version: Required. The agent version for feedback association.
                - source: Optional filter by interaction source.
                - feedback_name: Optional filter by feedback extractor name.

        Returns:
            ManualFeedbackGenerationResponse: Response containing success status, message, and count of feedbacks generated
        """
        return self._run_generation_service(
            request,
            ManualFeedbackGenerationRequest,
            FeedbackGenerationService,
            output_pending=False,
            run_method="run_manual_regular",
        )

    def upgrade_all_profiles(
        self,
        request: UpgradeProfilesRequest | dict | None = None,
    ) -> UpgradeProfilesResponse:
        """Upgrade all profiles by deleting old ARCHIVED, archiving CURRENT, and promoting PENDING.

        This operation performs three atomic steps:
        1. Delete all ARCHIVED profiles (old archived profiles from previous upgrades)
        2. Archive all CURRENT profiles → ARCHIVED (save current state for potential rollback)
        3. Promote all PENDING profiles → CURRENT (activate new profiles)

        Args:
            request (Union[UpgradeProfilesRequest, dict], optional): The upgrade request
                - only_affected_users: If True, only upgrade users who have pending profiles

        Returns:
            UpgradeProfilesResponse: Response containing success status and counts
        """
        if not self._is_storage_configured():
            return UpgradeProfilesResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = UpgradeProfilesRequest(**request)
        elif request is None:
            request = UpgradeProfilesRequest(user_id=None, only_affected_users=False)

        # Create service with shared LLM client
        service = ProfileGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
        )

        # Delegate to service
        return service.run_upgrade(request)  # type: ignore[reportArgumentType]

    def downgrade_all_profiles(
        self,
        request: DowngradeProfilesRequest | dict | None = None,
    ) -> DowngradeProfilesResponse:
        """Downgrade all profiles by archiving CURRENT and restoring ARCHIVED.

        This operation performs three atomic steps:
        1. Mark all CURRENT profiles → ARCHIVE_IN_PROGRESS (temporary status)
        2. Restore all ARCHIVED profiles → CURRENT
        3. Move all ARCHIVE_IN_PROGRESS profiles → ARCHIVED

        Args:
            request (Union[DowngradeProfilesRequest, dict], optional): The downgrade request
                - only_affected_users: If True, only downgrade users who have archived profiles

        Returns:
            DowngradeProfilesResponse: Response containing success status and counts
        """
        if not self._is_storage_configured():
            return DowngradeProfilesResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = DowngradeProfilesRequest(**request)
        elif request is None:
            request = DowngradeProfilesRequest(user_id=None, only_affected_users=False)

        # Create service with shared LLM client
        service = ProfileGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
        )

        # Delegate to service
        return service.run_downgrade(request)  # type: ignore[reportArgumentType]

    def get_profile_statistics(self) -> GetProfileStatisticsResponse:
        """Get profile count statistics by status.

        Returns:
            GetProfileStatisticsResponse: Response containing profile counts
        """
        if not self._is_storage_configured():
            return GetProfileStatisticsResponse(
                success=True,
                current_count=0,
                pending_count=0,
                archived_count=0,
                expiring_soon_count=0,
                msg=STORAGE_NOT_CONFIGURED_MSG,
            )
        try:
            stats = self._get_storage().get_profile_statistics()
            return GetProfileStatisticsResponse(success=True, **stats)
        except Exception as e:
            return GetProfileStatisticsResponse(
                success=False, msg=f"Failed to get profile statistics: {str(e)}"
            )

    def get_operation_status(
        self, request: GetOperationStatusRequest | dict
    ) -> GetOperationStatusResponse:
        """Get the status of an operation.

        Args:
            request (Union[GetOperationStatusRequest, dict]): Request containing service_name

        Returns:
            GetOperationStatusResponse: Response containing operation status info
        """
        if not self._is_storage_configured():
            return GetOperationStatusResponse(
                success=True, operation_status=None, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        try:
            # Convert dict to request object if needed
            if isinstance(request, dict):
                request = GetOperationStatusRequest(**request)

            # Build the progress key: {service_name}::{org_id}::progress
            org_id = self.request_context.org_id
            progress_key = f"{request.service_name}::{org_id}::progress"

            # Get operation state from storage
            state_entry = self._get_storage().get_operation_state(progress_key)

            if not state_entry:
                return GetOperationStatusResponse(
                    success=False,
                    msg=f"No operation found for service: {request.service_name}",
                )

            # Extract the actual operation_state from the storage wrapper
            # Storage returns: {"service_name": "...", "operation_state": {...}, "updated_at": "..."}
            operation_state = state_entry.get("operation_state", state_entry)

            # Auto-recover stale IN_PROGRESS operations so the frontend
            # doesn't show "in progress" forever after a crash/restart
            if operation_state.get("status") == OperationStatus.IN_PROGRESS.value:
                from datetime import datetime

                from reflexio.server.services.operation_state_utils import (
                    BATCH_STALE_PROGRESS_SECONDS,
                )

                started_at = operation_state.get("started_at")
                if started_at is not None:
                    current_time = int(datetime.now(UTC).timestamp())
                    elapsed = current_time - started_at
                    if elapsed > BATCH_STALE_PROGRESS_SECONDS:
                        logger.warning(
                            "Stale %s operation detected during status poll "
                            "(started %d seconds ago), auto-marking as FAILED",
                            request.service_name,
                            elapsed,
                        )
                        operation_state["status"] = OperationStatus.FAILED.value
                        operation_state["completed_at"] = current_time
                        operation_state["error_message"] = (
                            f"Auto-recovered: operation was stuck for {elapsed}s "
                            f"(threshold: {BATCH_STALE_PROGRESS_SECONDS}s)"
                        )
                        self._get_storage().update_operation_state(
                            progress_key, operation_state
                        )

            # Convert to OperationStatusInfo
            operation_status_info = OperationStatusInfo(**operation_state)

            return GetOperationStatusResponse(
                success=True, operation_status=operation_status_info
            )

        except Exception as e:
            return GetOperationStatusResponse(
                success=False, msg=f"Failed to get operation status: {str(e)}"
            )

    def cancel_operation(
        self, request: CancelOperationRequest | dict
    ) -> CancelOperationResponse:
        """Cancel an in-progress operation (rerun or manual generation).

        Sets a cancellation flag so the batch loop stops before the next user.
        The current LLM call finishes, but no new users are started.

        Args:
            request (Union[CancelOperationRequest, dict]): Request containing optional service_name.
                If service_name is None, cancels both profile_generation and feedback_generation.

        Returns:
            CancelOperationResponse: Response with list of services that were cancelled
        """
        if not self._is_storage_configured():
            return CancelOperationResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        try:
            if isinstance(request, dict):
                request = CancelOperationRequest(**request)

            # Determine which services to cancel
            if request.service_name:
                service_names = [request.service_name]
            else:
                service_names = ["profile_generation", "feedback_generation"]

            cancelled_services = []
            for svc in service_names:
                mgr = OperationStateManager(
                    storage=self._get_storage(),
                    org_id=self.request_context.org_id,
                    service_name=svc,
                )
                if mgr.request_cancellation():
                    cancelled_services.append(svc)

            if cancelled_services:
                return CancelOperationResponse(
                    success=True,
                    cancelled_services=cancelled_services,
                    msg=f"Cancellation requested for: {', '.join(cancelled_services)}",
                )
            return CancelOperationResponse(
                success=True,
                cancelled_services=[],
                msg="No in-progress operations found to cancel",
            )

        except Exception as e:
            return CancelOperationResponse(
                success=False, msg=f"Failed to cancel operation: {str(e)}"
            )

    def unified_search(
        self,
        request: UnifiedSearchRequest | dict,
        org_id: str,
    ) -> UnifiedSearchResponse:
        """
        Search across all entity types (profiles, feedbacks, raw_feedbacks, skills) in parallel.

        Delegates to unified_search_service for the actual search logic.

        Args:
            request (Union[UnifiedSearchRequest, dict]): The unified search request
            org_id (str): Organization ID (used for feature flag checks)

        Returns:
            UnifiedSearchResponse: Combined results from all entity types
        """
        if not self._is_storage_configured():
            return UnifiedSearchResponse(success=True, msg=STORAGE_NOT_CONFIGURED_MSG)
        if isinstance(request, dict):
            request = UnifiedSearchRequest(**request)

        from reflexio.server.services.unified_search_service import run_unified_search

        config = self.request_context.configurator.get_config()
        api_key_config = config.api_key_config if config else None

        return run_unified_search(
            request=request,
            org_id=org_id,
            storage=self._get_storage(),
            api_key_config=api_key_config,
            prompt_manager=self.request_context.prompt_manager,
        )

    def upgrade_all_raw_feedbacks(
        self,
        request: UpgradeRawFeedbacksRequest | dict | None = None,
    ) -> UpgradeRawFeedbacksResponse:
        """Upgrade all raw feedbacks by deleting old ARCHIVED, archiving CURRENT, and promoting PENDING.

        This operation performs three atomic steps:
        1. Delete all ARCHIVED raw feedbacks (old archived from previous upgrades)
        2. Archive all CURRENT raw feedbacks → ARCHIVED (save current state for potential rollback)
        3. Promote all PENDING raw feedbacks → CURRENT (activate new raw feedbacks)

        Args:
            request (Union[UpgradeRawFeedbacksRequest, dict], optional): The upgrade request
                - agent_version: Optional filter by agent version
                - feedback_name: Optional filter by feedback name

        Returns:
            UpgradeRawFeedbacksResponse: Response containing success status and counts
        """
        if not self._is_storage_configured():
            return UpgradeRawFeedbacksResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = UpgradeRawFeedbacksRequest(**request)
        elif request is None:
            request = UpgradeRawFeedbacksRequest()

        # Create service with shared LLM client
        service = FeedbackGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
        )

        # Delegate to service
        return service.run_upgrade(request)  # type: ignore[reportArgumentType]

    def downgrade_all_raw_feedbacks(
        self,
        request: DowngradeRawFeedbacksRequest | dict | None = None,
    ) -> DowngradeRawFeedbacksResponse:
        """Downgrade all raw feedbacks by archiving CURRENT and restoring ARCHIVED.

        This operation performs three atomic steps:
        1. Mark all CURRENT raw feedbacks → ARCHIVE_IN_PROGRESS (temporary status)
        2. Restore all ARCHIVED raw feedbacks → CURRENT
        3. Move all ARCHIVE_IN_PROGRESS raw feedbacks → ARCHIVED

        Args:
            request (Union[DowngradeRawFeedbacksRequest, dict], optional): The downgrade request
                - agent_version: Optional filter by agent version
                - feedback_name: Optional filter by feedback name

        Returns:
            DowngradeRawFeedbacksResponse: Response containing success status and counts
        """
        if not self._is_storage_configured():
            return DowngradeRawFeedbacksResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = DowngradeRawFeedbacksRequest(**request)
        elif request is None:
            request = DowngradeRawFeedbacksRequest()

        # Create service with shared LLM client
        service = FeedbackGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
        )

        # Delegate to service
        return service.run_downgrade(request)  # type: ignore[reportArgumentType]
