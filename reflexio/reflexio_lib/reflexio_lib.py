import logging
from typing import Optional, Union

from reflexio_commons.api_schema.service_schemas import (
    ProfileChangeLogResponse,
    FeedbackAggregationChangeLogResponse,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    AddFeedbackRequest,
    AddFeedbackResponse,
    RawFeedback,
    Feedback,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    DeleteRequestRequest,
    DeleteRequestResponse,
    DeleteRequestGroupRequest,
    DeleteRequestGroupResponse,
    DeleteFeedbackRequest,
    DeleteFeedbackResponse,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbackResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
    ManualProfileGenerationRequest,
    ManualProfileGenerationResponse,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    ManualFeedbackGenerationRequest,
    ManualFeedbackGenerationResponse,
    UpgradeProfilesRequest,
    UpgradeProfilesResponse,
    DowngradeProfilesRequest,
    DowngradeProfilesResponse,
    UpgradeRawFeedbacksRequest,
    UpgradeRawFeedbacksResponse,
    DowngradeRawFeedbacksRequest,
    DowngradeRawFeedbacksResponse,
    Status,
    OperationStatus,
    OperationStatusInfo,
    GetOperationStatusRequest,
    GetOperationStatusResponse,
    CancelOperationRequest,
    CancelOperationResponse,
)
from reflexio_commons.api_schema.retriever_schema import (
    GetProfileStatisticsResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
    GetInteractionsRequest,
    GetInteractionsResponse,
    GetUserProfilesRequest,
    GetUserProfilesResponse,
    SetConfigResponse,
    GetRawFeedbacksRequest,
    GetRawFeedbacksResponse,
    GetFeedbacksRequest,
    GetFeedbacksResponse,
    SearchRawFeedbackRequest,
    SearchRawFeedbackResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    GetAgentSuccessEvaluationResultsRequest,
    GetAgentSuccessEvaluationResultsResponse,
    GetRequestsRequest,
    GetRequestsResponse,
    RequestData,
    RequestGroup,
    UpdateFeedbackStatusRequest,
    UpdateFeedbackStatusResponse,
    GetDashboardStatsRequest,
    GetDashboardStatsResponse,
    DashboardStats,
    PeriodStats,
    TimeSeriesDataPoint,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
)
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio.server.services.generation_service import GenerationService
from reflexio.server.services.profile.profile_generation_service import (
    ProfileGenerationService,
)
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.services.configurator.configurator import SimpleConfigurator
from reflexio_commons.config_schema import Config

from reflexio.server.services.operation_state_utils import OperationStateManager
from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)

# Error message for when storage is not configured
STORAGE_NOT_CONFIGURED_MSG = (
    "Storage not configured. Please configure storage in settings first."
)


class Reflexio:
    def __init__(
        self,
        org_id: str,
        storage_base_dir: Optional[str] = None,
        configurator: SimpleConfigurator = None,
    ):
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
            else model_setting.get("default_generation_model_name", "gpt-5-mini")
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

    def _get_query_rewriter(self):
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

    def _rewrite_query(
        self, query: Optional[str], enabled: bool = False
    ) -> Optional[str]:
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
        request: Union[PublishUserInteractionRequest, dict],
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
        request: Union[SearchInteractionRequest, dict],
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
        interactions = self.request_context.storage.search_interaction(request)
        return SearchInteractionResponse(success=True, interactions=interactions)

    def search_profiles(
        self,
        request: Union[SearchUserProfileRequest, dict],
        status_filter: Optional[list[Optional[Status]]] = None,
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
        profiles = self.request_context.storage.search_user_profile(
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
        changelogs = self.request_context.storage.get_profile_change_logs()
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
        change_logs = self.request_context.storage.get_feedback_aggregation_change_logs(
            feedback_name=feedback_name, agent_version=agent_version
        )
        return FeedbackAggregationChangeLogResponse(
            success=True, change_logs=change_logs
        )

    def delete_profile(
        self,
        request: Union[DeleteUserProfileRequest, dict],
    ) -> DeleteUserProfileResponse:
        """Delete user profiles.

        Args:
            request (DeleteUserProfileRequest): The delete request

        Returns:
            DeleteUserProfileResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return DeleteUserProfileResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteUserProfileRequest(**request)
        try:
            self.request_context.storage.delete_user_profile(request)
            return DeleteUserProfileResponse(success=True)
        except Exception as e:
            return DeleteUserProfileResponse(success=False, message=str(e))

    def delete_interaction(
        self,
        request: Union[DeleteUserInteractionRequest, dict],
    ) -> DeleteUserInteractionResponse:
        """Delete user interactions.

        Args:
            request (DeleteUserInteractionRequest): The delete request

        Returns:
            DeleteUserInteractionResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return DeleteUserInteractionResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteUserInteractionRequest(**request)
        try:
            self.request_context.storage.delete_user_interaction(request)
            return DeleteUserInteractionResponse(success=True)
        except Exception as e:
            return DeleteUserInteractionResponse(success=False, message=str(e))

    def delete_request(
        self,
        request: Union[DeleteRequestRequest, dict],
    ) -> DeleteRequestResponse:
        """Delete a request and all its associated interactions.

        Args:
            request (DeleteRequestRequest): The delete request containing request_id

        Returns:
            DeleteRequestResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return DeleteRequestResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteRequestRequest(**request)
        try:
            self.request_context.storage.delete_request(request.request_id)
            return DeleteRequestResponse(success=True)
        except Exception as e:
            return DeleteRequestResponse(success=False, message=str(e))

    def delete_request_group(
        self,
        request: Union[DeleteRequestGroupRequest, dict],
    ) -> DeleteRequestGroupResponse:
        """Delete all requests and interactions in a request group.

        Args:
            request (DeleteRequestGroupRequest): The delete request containing request_group

        Returns:
            DeleteRequestGroupResponse: Response containing success status, message, and deleted count
        """
        if not self._is_storage_configured():
            return DeleteRequestGroupResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteRequestGroupRequest(**request)
        try:
            deleted_count = self.request_context.storage.delete_request_group(
                request.request_group
            )
            return DeleteRequestGroupResponse(
                success=True, deleted_requests_count=deleted_count
            )
        except Exception as e:
            return DeleteRequestGroupResponse(success=False, message=str(e))

    def delete_feedback(
        self,
        request: Union[DeleteFeedbackRequest, dict],
    ) -> DeleteFeedbackResponse:
        """Delete a feedback by ID.

        Args:
            request (DeleteFeedbackRequest): The delete request containing feedback_id

        Returns:
            DeleteFeedbackResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return DeleteFeedbackResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteFeedbackRequest(**request)
        try:
            self.request_context.storage.delete_feedback(request.feedback_id)
            return DeleteFeedbackResponse(success=True)
        except Exception as e:
            return DeleteFeedbackResponse(success=False, message=str(e))

    def delete_raw_feedback(
        self,
        request: Union[DeleteRawFeedbackRequest, dict],
    ) -> DeleteRawFeedbackResponse:
        """Delete a raw feedback by ID.

        Args:
            request (DeleteRawFeedbackRequest): The delete request containing raw_feedback_id

        Returns:
            DeleteRawFeedbackResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return DeleteRawFeedbackResponse(
                success=False, message=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = DeleteRawFeedbackRequest(**request)
        try:
            self.request_context.storage.delete_raw_feedback(request.raw_feedback_id)
            return DeleteRawFeedbackResponse(success=True)
        except Exception as e:
            return DeleteRawFeedbackResponse(success=False, message=str(e))

    def get_interactions(
        self,
        request: Union[GetInteractionsRequest, dict],
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
        interactions = self.request_context.storage.get_user_interaction(
            request.user_id
        )
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
        request: Union[GetUserProfilesRequest, dict],
        status_filter: Optional[list[Optional[Status]]] = None,
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

        profiles = self.request_context.storage.get_user_profile(
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
        status_filter: Optional[list[Optional[Status]]] = None,
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
        profiles = self.request_context.storage.get_all_profiles(
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
        interactions = self.request_context.storage.get_all_interactions(limit=limit)
        interactions = sorted(interactions, key=lambda x: x.created_at, reverse=True)
        return GetInteractionsResponse(success=True, interactions=interactions)

    def get_dashboard_stats(
        self, request: Union[GetDashboardStatsRequest, dict]
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
            stats_dict = self.request_context.storage.get_dashboard_stats(
                days_back=request.days_back
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

    def run_feedback_aggregation(self, agent_version: str, feedback_name: str):
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

    def run_skill_generation(self, agent_version: str, feedback_name: str):
        """Run skill generation for a given agent version.

        Args:
            agent_version (str): The agent version
            feedback_name (str): The feedback name

        Raises:
            ValueError: If storage is not configured
        """
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        from reflexio.server.services.feedback.skill_generator import SkillGenerator
        from reflexio.server.services.feedback.feedback_service_utils import (
            SkillGeneratorRequest,
        )

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
        feedback_name=None,
        agent_version=None,
        skill_status=None,
    ):
        """Get skills from storage."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        return self.request_context.storage.get_skills(
            limit=limit,
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
        )

    def search_skills(
        self,
        query=None,
        feedback_name=None,
        agent_version=None,
        skill_status=None,
        threshold=0.5,
        count=10,
    ):
        """Search skills with hybrid search."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        rewritten = self._rewrite_query(query)
        return self.request_context.storage.search_skills(
            query=rewritten or query,
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
            match_threshold=threshold,
            match_count=count,
        )

    def update_skill_status(self, skill_id: int, skill_status):
        """Update skill status."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        self.request_context.storage.update_skill_status(skill_id, skill_status)

    def delete_skill(self, skill_id: int):
        """Delete a skill by ID."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        self.request_context.storage.delete_skill(skill_id)

    def export_skills(self, feedback_name=None, agent_version=None, skill_status=None):
        """Export skills as markdown."""
        if not self._is_storage_configured():
            raise ValueError(STORAGE_NOT_CONFIGURED_MSG)
        from reflexio.server.services.feedback.skill_generator import (
            render_skills_markdown,
        )

        skills = self.request_context.storage.get_skills(
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
        )
        return render_skills_markdown(skills)

    def set_config(self, config: Union[Config, dict]) -> SetConfigResponse:
        """Set configuration for the organization.

        Args:
            config (Union[Config, dict]): The configuration to set

        Returns:
            dict: Response containing success status and message
        """
        try:
            if isinstance(config, dict):
                config = Config(**config)

            # Validate storage connection before setting config
            storage_config = config.storage_config

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
        request: Union[GetRawFeedbacksRequest, dict],
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
            raw_feedbacks = self.request_context.storage.get_raw_feedbacks(
                limit=request.limit,
                feedback_name=request.feedback_name,
                status_filter=request.status_filter,
            )
            return GetRawFeedbacksResponse(success=True, raw_feedbacks=raw_feedbacks)
        except Exception as e:
            return GetRawFeedbacksResponse(success=False, raw_feedbacks=[], msg=str(e))

    def add_raw_feedback(
        self,
        request: Union[AddRawFeedbackRequest, dict],
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

            self.request_context.storage.save_raw_feedbacks(normalized_feedbacks)
            return AddRawFeedbackResponse(
                success=True, added_count=len(normalized_feedbacks)
            )
        except Exception as e:
            return AddRawFeedbackResponse(success=False, message=str(e))

    def add_feedback(
        self,
        request: Union[AddFeedbackRequest, dict],
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
            normalized_feedbacks = []
            for fb in request.feedbacks:
                normalized_feedbacks.append(
                    Feedback(
                        agent_version=fb.agent_version,
                        feedback_name=fb.feedback_name,
                        feedback_content=fb.feedback_content,
                        feedback_status=fb.feedback_status,
                        feedback_metadata=(
                            fb.feedback_metadata if fb.feedback_metadata else ""
                        ),
                    )
                )

            self.request_context.storage.save_feedbacks(normalized_feedbacks)
            return AddFeedbackResponse(
                success=True, added_count=len(normalized_feedbacks)
            )
        except Exception as e:
            return AddFeedbackResponse(success=False, message=str(e))

    def get_feedbacks(
        self,
        request: Union[GetFeedbacksRequest, dict],
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
            feedbacks = self.request_context.storage.get_feedbacks(
                limit=request.limit,
                feedback_name=request.feedback_name,
                status_filter=request.status_filter,
                feedback_status_filter=request.feedback_status_filter,
            )
            return GetFeedbacksResponse(success=True, feedbacks=feedbacks)
        except Exception as e:
            return GetFeedbacksResponse(success=False, feedbacks=[], msg=str(e))

    def search_raw_feedbacks(
        self,
        request: Union[SearchRawFeedbackRequest, dict],
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
            query = (
                self._rewrite_query(request.query, enabled=bool(request.query_rewrite))
                or request.query
            )
            raw_feedbacks = self.request_context.storage.search_raw_feedbacks(
                query=query,
                user_id=request.user_id,
                agent_version=request.agent_version,
                feedback_name=request.feedback_name,
                start_time=(
                    int(request.start_time.timestamp()) if request.start_time else None
                ),
                end_time=(
                    int(request.end_time.timestamp()) if request.end_time else None
                ),
                status_filter=request.status_filter,
                match_threshold=request.threshold or 0.5,
                match_count=request.top_k or 10,
            )
            return SearchRawFeedbackResponse(success=True, raw_feedbacks=raw_feedbacks)
        except Exception as e:
            return SearchRawFeedbackResponse(
                success=False, raw_feedbacks=[], msg=str(e)
            )

    def search_feedbacks(
        self,
        request: Union[SearchFeedbackRequest, dict],
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
            query = (
                self._rewrite_query(request.query, enabled=bool(request.query_rewrite))
                or request.query
            )
            feedbacks = self.request_context.storage.search_feedbacks(
                query=query,
                agent_version=request.agent_version,
                feedback_name=request.feedback_name,
                start_time=(
                    int(request.start_time.timestamp()) if request.start_time else None
                ),
                end_time=(
                    int(request.end_time.timestamp()) if request.end_time else None
                ),
                status_filter=request.status_filter,
                feedback_status_filter=request.feedback_status_filter,
                match_threshold=request.threshold or 0.5,
                match_count=request.top_k or 10,
            )
            return SearchFeedbackResponse(success=True, feedbacks=feedbacks)
        except Exception as e:
            return SearchFeedbackResponse(success=False, feedbacks=[], msg=str(e))

    def get_agent_success_evaluation_results(
        self,
        request: Union[GetAgentSuccessEvaluationResultsRequest, dict],
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
            results = self.request_context.storage.get_agent_success_evaluation_results(
                limit=request.limit, agent_version=request.agent_version
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
        request: Union[GetRequestsRequest, dict],
    ) -> GetRequestsResponse:
        """Get requests with their associated interactions, grouped by request_group.

        Args:
            request (Union[GetRequestsRequest, dict]): The get request

        Returns:
            GetRequestsResponse: Response containing requests grouped by request_group with their interactions
        """
        if not self._is_storage_configured():
            return GetRequestsResponse(
                success=True, request_groups=[], msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = GetRequestsRequest(**request)

        try:
            # Get requests with interactions from storage (already grouped by request_group)
            grouped_results = self.request_context.storage.get_request_groups(
                user_id=request.user_id,
                request_id=request.request_id,
                start_time=(
                    int(request.start_time.timestamp()) if request.start_time else None
                ),
                end_time=(
                    int(request.end_time.timestamp()) if request.end_time else None
                ),
                top_k=request.top_k,
                offset=request.offset or 0,
            )

            # Transform the dictionary into RequestGroup objects
            request_groups = []
            for group_name, request_interaction_data_models in grouped_results.items():
                # Convert each RequestInteractionDataModel to RequestData
                request_data_list = [
                    RequestData(
                        request=request_interaction.request,
                        interactions=request_interaction.interactions,
                    )
                    for request_interaction in request_interaction_data_models
                ]
                request_groups.append(
                    RequestGroup(request_group=group_name, requests=request_data_list)
                )

            # Determine has_more: count total requests returned across all groups
            total_returned = sum(len(rg.requests) for rg in request_groups)
            effective_limit = request.top_k or 100
            has_more = total_returned >= effective_limit

            return GetRequestsResponse(
                success=True,
                request_groups=request_groups,
                has_more=has_more,
            )
        except Exception as e:
            return GetRequestsResponse(success=False, request_groups=[], msg=str(e))

    def update_feedback_status(
        self,
        request: Union[UpdateFeedbackStatusRequest, dict],
    ) -> UpdateFeedbackStatusResponse:
        """Update the status of a specific feedback.

        Args:
            request (Union[UpdateFeedbackStatusRequest, dict]): The update request

        Returns:
            UpdateFeedbackStatusResponse: Response containing success status and message
        """
        if not self._is_storage_configured():
            return UpdateFeedbackStatusResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        if isinstance(request, dict):
            request = UpdateFeedbackStatusRequest(**request)

        try:
            self.request_context.storage.update_feedback_status(
                feedback_id=request.feedback_id,
                feedback_status=request.feedback_status,
            )
            return UpdateFeedbackStatusResponse(success=True)
        except ValueError as e:
            return UpdateFeedbackStatusResponse(success=False, msg=str(e))
        except Exception as e:
            return UpdateFeedbackStatusResponse(success=False, msg=str(e))

    def rerun_profile_generation(
        self,
        request: Union[RerunProfileGenerationRequest, dict],
    ) -> RerunProfileGenerationResponse:
        """Rerun profile generation for one or all users with filtered interactions.

        Args:
            request (Union[RerunProfileGenerationRequest, dict]): The rerun request containing optional user_id, time filters, and source.
                If user_id is None, reruns for all users.

        Returns:
            RerunProfileGenerationResponse: Response containing success status, message, and count of profiles generated
        """
        if not self._is_storage_configured():
            return RerunProfileGenerationResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = RerunProfileGenerationRequest(**request)

        # Create service with shared LLM client
        service = ProfileGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
            allow_manual_trigger=True,  # Allow manual_trigger extractors
            output_pending_status=True,  # Output PENDING status
        )

        # Delegate to service
        return service.run_rerun(request)

    def manual_profile_generation(
        self,
        request: Union[ManualProfileGenerationRequest, dict],
    ) -> ManualProfileGenerationResponse:
        """Manually trigger profile generation with window-sized interactions and CURRENT output.

        This behaves like regular generation (uses extraction_window_size from config,
        outputs CURRENT profiles) but only runs profile extraction (not feedback or
        agent success evaluation).

        Args:
            request (Union[ManualProfileGenerationRequest, dict]): The request containing
                optional user_id, source, and extractor_names.
                If user_id is None, runs for all users.

        Returns:
            ManualProfileGenerationResponse: Response containing success status, message,
                and count of profiles generated
        """
        if not self._is_storage_configured():
            return ManualProfileGenerationResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = ManualProfileGenerationRequest(**request)

        # Create service with shared LLM client
        service = ProfileGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
            allow_manual_trigger=True,  # Allow manual_trigger extractors
            output_pending_status=False,  # Output CURRENT status (not PENDING)
        )

        # Delegate to service
        return service.run_manual_regular(request)

    def rerun_feedback_generation(
        self,
        request: Union[RerunFeedbackGenerationRequest, dict],
    ) -> RerunFeedbackGenerationResponse:
        """Rerun feedback generation with filtered interactions.

        Args:
            request (Union[RerunFeedbackGenerationRequest, dict]): The rerun request containing agent_version,
                optional time filters, and optional feedback_name.

        Returns:
            RerunFeedbackGenerationResponse: Response containing success status, message, and count of feedbacks generated
        """
        if not self._is_storage_configured():
            return RerunFeedbackGenerationResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = RerunFeedbackGenerationRequest(**request)

        # Create service with shared LLM client
        service = FeedbackGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
            allow_manual_trigger=True,
            output_pending_status=True,
        )

        # Delegate to service
        return service.run_rerun(request)

    def manual_feedback_generation(
        self,
        request: Union[ManualFeedbackGenerationRequest, dict],
    ) -> ManualFeedbackGenerationResponse:
        """Manually trigger feedback generation with window-sized interactions and CURRENT output.

        This is the feedback equivalent of manual_profile_generation(). It triggers feedback
        extraction using only the most recent window-sized interactions (from extraction_window_size
        config) and outputs feedbacks with CURRENT status (not PENDING like rerun).

        Use this when you want to:
        - Force regeneration of feedbacks without waiting for automatic triggers
        - Test feedback extraction with current interactions
        - Generate feedbacks immediately without going through the PENDING → upgrade flow

        Args:
            request (Union[ManualFeedbackGenerationRequest, dict]): The generation request containing:
                - agent_version: Required. The agent version for feedback association.
                - source: Optional filter by interaction source.
                - feedback_name: Optional filter by feedback extractor name.

        Returns:
            ManualFeedbackGenerationResponse: Response containing success status, message, and count of feedbacks generated
        """
        if not self._is_storage_configured():
            return ManualFeedbackGenerationResponse(
                success=False, msg=STORAGE_NOT_CONFIGURED_MSG
            )
        # Convert dict to request object if needed
        if isinstance(request, dict):
            request = ManualFeedbackGenerationRequest(**request)

        # Create service with shared LLM client
        service = FeedbackGenerationService(
            llm_client=self.llm_client,
            request_context=self.request_context,
            allow_manual_trigger=True,
            output_pending_status=False,  # CURRENT output
        )

        # Delegate to service
        return service.run_manual_regular(request)

    def upgrade_all_profiles(
        self,
        request: Union[UpgradeProfilesRequest, dict] = None,
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
        return service.run_upgrade(request)

    def downgrade_all_profiles(
        self,
        request: Union[DowngradeProfilesRequest, dict] = None,
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
        return service.run_downgrade(request)

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
            stats = self.request_context.storage.get_profile_statistics()
            return GetProfileStatisticsResponse(success=True, **stats)
        except Exception as e:
            return GetProfileStatisticsResponse(
                success=False, msg=f"Failed to get profile statistics: {str(e)}"
            )

    def get_operation_status(
        self, request: Union[GetOperationStatusRequest, dict]
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
            state_entry = self.request_context.storage.get_operation_state(progress_key)

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
                from reflexio.server.services.operation_state_utils import (
                    BATCH_STALE_PROGRESS_SECONDS,
                )
                from datetime import datetime, timezone

                started_at = operation_state.get("started_at")
                if started_at is not None:
                    current_time = int(datetime.now(timezone.utc).timestamp())
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
                        self.request_context.storage.update_operation_state(
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
        self, request: Union[CancelOperationRequest, dict]
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
                    storage=self.request_context.storage,
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
            else:
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
        request: Union[UnifiedSearchRequest, dict],
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
            storage=self.request_context.storage,
            api_key_config=api_key_config,
            prompt_manager=self.request_context.prompt_manager,
        )

    def upgrade_all_raw_feedbacks(
        self,
        request: Union[UpgradeRawFeedbacksRequest, dict] = None,
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
        return service.run_upgrade(request)

    def downgrade_all_raw_feedbacks(
        self,
        request: Union[DowngradeRawFeedbacksRequest, dict] = None,
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
        return service.run_downgrade(request)
