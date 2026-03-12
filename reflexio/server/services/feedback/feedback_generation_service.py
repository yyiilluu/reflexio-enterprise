from dataclasses import dataclass, field
import logging
import uuid
from typing import Optional, Union

from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    RawFeedback,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    ManualFeedbackGenerationRequest,
    ManualFeedbackGenerationResponse,
    UpgradeRawFeedbacksResponse,
    DowngradeRawFeedbacksResponse,
    Status,
)
from reflexio_commons.config_schema import AgentFeedbackConfig
from reflexio.server.services.feedback.feedback_extractor import FeedbackExtractor
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackGenerationRequest,
    FeedbackAggregatorRequest,
)
from reflexio.server.services.feedback.feedback_service_constants import (
    FeedbackServiceConstants,
)
from reflexio.server.services.base_generation_service import (
    BaseGenerationService,
    StatusChangeOperation,
)
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.service_utils import (
    format_sessions_to_history_string,
)

logger = logging.getLogger(__name__)


@dataclass
class FeedbackGenerationServiceConfig:
    """Runtime configuration for feedback generation service shared across all extractors.

    Attributes:
        request_id: The request ID
        agent_version: The agent version
        user_id: The user ID for per-user feedback extraction
        source: Source of the interactions
        existing_data: Existing raw feedbacks for the user (from past 7 days)
        allow_manual_trigger: Whether to allow extractors with manual_trigger=True
        rerun_start_time: Optional start time filter for rerun flows (Unix timestamp)
        rerun_end_time: Optional end time filter for rerun flows (Unix timestamp)
        auto_run: True for regular flow (checks stride), False for rerun/manual (skips stride)
        extractor_names: Optional list of extractor names to run (derived from feedback_name)
    """

    request_id: str
    agent_version: str
    user_id: Optional[str] = None
    source: Optional[str] = None
    existing_data: list[RawFeedback] = field(default_factory=list)
    allow_manual_trigger: bool = False
    rerun_start_time: Optional[int] = None
    rerun_end_time: Optional[int] = None
    auto_run: bool = True
    extractor_names: Optional[list[str]] = None
    is_incremental: bool = False
    previously_extracted: list[list[RawFeedback]] = field(default_factory=list)


class FeedbackGenerationService(
    BaseGenerationService[
        AgentFeedbackConfig,
        FeedbackExtractor,
        FeedbackGenerationServiceConfig,
        FeedbackGenerationRequest,
    ]
):
    """
    Service for generating feedback from user interactions.
    Runs multiple FeedbackExtractor instances sequentially with incremental context.
    """

    def __init__(
        self,
        llm_client,
        request_context,
        allow_manual_trigger: bool = False,
        output_pending_status: bool = False,
    ) -> None:
        """
        Initialize the feedback generation service.

        Args:
            llm_client: Unified LLM client supporting both OpenAI and Claude
            request_context: Request context with storage, configurator, and org_id
            allow_manual_trigger: Whether to allow extractors with manual_trigger=True
            output_pending_status: Whether to output feedbacks with PENDING status (for rerun)
        """
        super().__init__(llm_client=llm_client, request_context=request_context)
        self.allow_manual_trigger = allow_manual_trigger
        self.output_pending_status = output_pending_status

    def _load_generation_service_config(
        self, request: FeedbackGenerationRequest
    ) -> FeedbackGenerationServiceConfig:
        """
        Extract request parameters from FeedbackGenerationRequest.

        Args:
            request: FeedbackGenerationRequest containing evaluation parameters

        Returns:
            FeedbackGenerationServiceConfig object
        """
        # Get existing raw feedbacks for the user from past 7 days
        # Skip for rerun flows (output_pending_status=True) to generate fresh feedbacks
        existing_feedbacks: list[RawFeedback] = []
        if request.user_id and not self.output_pending_status:
            from datetime import datetime, timezone, timedelta

            seven_days_ago = int(
                (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
            )
            existing_feedbacks = self.storage.get_raw_feedbacks(
                user_id=request.user_id,
                agent_version=request.agent_version,
                status_filter=[None],  # Get current feedbacks only
                start_time=seven_days_ago,
                limit=100,
            )

        return FeedbackGenerationServiceConfig(
            request_id=request.request_id,
            agent_version=request.agent_version,
            user_id=request.user_id,
            source=request.source,
            existing_data=existing_feedbacks,
            allow_manual_trigger=self.allow_manual_trigger,
            rerun_start_time=request.rerun_start_time,
            rerun_end_time=request.rerun_end_time,
            auto_run=request.auto_run,
            extractor_names=[request.feedback_name] if request.feedback_name else None,
        )

    def _load_extractor_configs(self) -> list[AgentFeedbackConfig]:
        """
        Load agent feedback configs from configurator.

        Returns:
            list[AgentFeedbackConfig]: List of agent feedback configuration objects from YAML
        """
        return self.configurator.get_config().agent_feedback_configs

    def _create_extractor(
        self,
        extractor_config: AgentFeedbackConfig,
        service_config: FeedbackGenerationServiceConfig,
    ) -> FeedbackExtractor:
        """
        Create a FeedbackExtractor instance from configuration.

        Args:
            extractor_config: AgentFeedbackConfig configuration object from YAML
            service_config: FeedbackGenerationServiceConfig containing runtime parameters

        Returns:
            FeedbackExtractor instance
        """
        return FeedbackExtractor(
            request_context=self.request_context,
            llm_client=self.client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context=self.configurator.get_agent_context(),
        )

    def _build_should_run_prompt(
        self,
        scoped_configs: list[AgentFeedbackConfig],
        session_data_models: list[RequestInteractionDataModel],
    ) -> str | None:
        """
        Build prompt for consolidated should_generate feedback check.

        Combines all feedback_definition_prompt values into a single definition
        for one LLM call.

        Args:
            scoped_configs: Feedback extractor configs that had scoped interactions
            session_data_models: Deduplicated request interaction data models

        Returns:
            str | None: The rendered prompt, or None if no definitions to check
        """
        new_interactions = format_sessions_to_history_string(session_data_models)

        # Combine all feedback definitions into a numbered list
        definitions = []
        for i, config in enumerate(scoped_configs, 1):
            if config.feedback_definition_prompt:
                definitions.append(f"{i}. {config.feedback_definition_prompt.strip()}")
        combined_definition = "\n".join(definitions) if definitions else ""

        if not combined_definition:
            return None

        # Get tool_can_use from root config
        root_config = self.request_context.configurator.get_config()
        tool_can_use_str = ""
        if root_config and root_config.tool_can_use:
            tool_can_use_str = "\n".join(
                f"{tool.tool_name}: {tool.tool_description}"
                for tool in root_config.tool_can_use
            )

        agent_context = self.configurator.get_agent_context()
        prompt_manager = self.request_context.prompt_manager

        return prompt_manager.render_prompt(
            FeedbackServiceConstants.RAW_FEEDBACK_SHOULD_GENERATE_PROMPT_ID,
            {
                "agent_context_prompt": agent_context,
                "feedback_definition_prompt": combined_definition,
                "new_interactions": new_interactions,
                "tool_can_use": tool_can_use_str,
            },
        )

    def _get_precheck_interaction_query_kwargs(self) -> dict:
        """Return agent_version filter for non-auto runs."""
        return {
            "agent_version": (
                self.service_config.agent_version
                if not self.service_config.auto_run
                else None
            ),
        }

    def _update_config_for_incremental(self, previously_extracted: list) -> None:
        """Update service_config for incremental feedback extraction."""
        self.service_config.is_incremental = True
        self.service_config.previously_extracted = list(previously_extracted)

    def _process_results(self, results: list[list[RawFeedback]]) -> None:
        """
        Process, deduplicate, and save all feedback results. Called once after all extractors complete.

        Args:
            results: List of RawFeedback results from extractors (one list per extractor)
        """
        # Flatten results (each extractor returns list[RawFeedback])
        all_feedbacks = []
        for result in results:
            if isinstance(result, list):
                all_feedbacks.extend(result)

        # Deduplicate if multiple extractors returned results and deduplicator is enabled
        if len(results) > 1:
            from reflexio.server.site_var.feature_flags import is_deduplicator_enabled

            if is_deduplicator_enabled(self.org_id):
                from reflexio.server.services.feedback.feedback_deduplicator import (
                    FeedbackDeduplicator,
                )

                deduplicator = FeedbackDeduplicator(
                    request_context=self.request_context,
                    llm_client=self.client,
                )
                deduplicated_feedbacks = deduplicator.deduplicate(
                    results,
                    self.service_config.request_id,
                    self.service_config.agent_version,
                )
                logger.info("Feedbacks after deduplication: %s", deduplicated_feedbacks)
                if deduplicated_feedbacks:
                    all_feedbacks = deduplicated_feedbacks

        # Set status and source for all feedbacks
        for feedback in all_feedbacks:
            feedback.status = Status.PENDING if self.output_pending_status else None
            feedback.source = self.service_config.source

        logger.info("All feedbacks: %s", all_feedbacks)

        logger.info(
            "Successfully completed %d %s feedback generation for request id: %s",
            len(all_feedbacks),
            self._get_service_name(),
            self.service_config.request_id,
        )

        # Save results
        if all_feedbacks:
            try:
                self.storage.save_raw_feedbacks(all_feedbacks)
            except Exception as e:
                logger.error(
                    "Failed to save %s results for request id: %s due to %s, exception type: %s",
                    self._get_service_name(),
                    self.service_config.request_id,
                    str(e),
                    type(e).__name__,
                )

            # Trigger feedback aggregation
            if not self.output_pending_status:
                logger.info("Trigger feedback aggregation")
                self._trigger_feedback_aggregation()

    def _get_extractor_state_service_name(self) -> str:
        """
        Get the service name for stride bookmark lookups.

        Returns:
            str: "feedback_extractor" for OperationStateManager stride checks
        """
        return "feedback_extractor"

    def _get_service_name(self) -> str:
        """
        Get the name of the service for logging and operation state tracking.

        Returns:
            Service name string - "rerun_feedback_generation" for rerun operations,
            "feedback_generation" for regular operations
        """
        if self.output_pending_status:
            return "rerun_feedback_generation"
        return "feedback_generation"

    def _get_base_service_name(self) -> str:
        """
        Get the base service name for OperationStateManager keys.

        Returns:
            str: "feedback_generation"
        """
        return "feedback_generation"

    def _should_track_in_progress(self) -> bool:
        """
        Feedback generation should track in-progress state to prevent duplicates.

        Returns:
            bool: True - feedback generation tracks in-progress state
        """
        return True

    def _get_lock_scope_id(self, request: FeedbackGenerationRequest) -> Optional[str]:
        """
        Get the scope ID for lock key construction.

        Feedback generation is org-scoped, so returns None (no user scope).

        Args:
            request: The FeedbackGenerationRequest

        Returns:
            None: Feedback uses org-level scope only
        """
        return None

    def _trigger_feedback_aggregation(self) -> None:
        """
        Trigger feedback aggregation for feedback types that have aggregator config.
        This is called after raw feedbacks are saved to check if aggregation should run.
        """
        # Get all agent feedback configs
        agent_feedback_configs = self.configurator.get_config().agent_feedback_configs
        if not agent_feedback_configs:
            return

        # Iterate through configs and trigger aggregation for those with aggregator config
        for feedback_config in agent_feedback_configs:
            if not feedback_config.feedback_aggregator_config:
                continue

            feedback_name = feedback_config.feedback_name
            logger.info("Triggering aggregation for feedback_name: %s", feedback_name)

            # Create aggregator request
            aggregator_request = FeedbackAggregatorRequest(
                agent_version=self.service_config.agent_version,
                feedback_name=feedback_name,
            )

            # Initialize and run aggregator (synchronous)
            aggregator = FeedbackAggregator(
                llm_client=self.client,
                request_context=self.request_context,
                agent_version=self.service_config.agent_version,
            )
            aggregator.run(aggregator_request)

            # After aggregation, optionally trigger skill generation
            try:
                skill_config = feedback_config.skill_generator_config
                if (
                    skill_config
                    and skill_config.enabled
                    and skill_config.auto_generate_on_aggregation
                ):
                    from reflexio.server.services.feedback.skill_generator import (
                        SkillGenerator,
                    )
                    from reflexio.server.services.feedback.feedback_service_utils import (
                        SkillGeneratorRequest,
                    )

                    logger.info("Triggering skill generation")
                    skill_gen = SkillGenerator(
                        llm_client=self.client,
                        request_context=self.request_context,
                        agent_version=self.service_config.agent_version,
                    )
                    skill_gen.run(
                        SkillGeneratorRequest(
                            agent_version=self.service_config.agent_version,
                            feedback_name=feedback_name,
                        )
                    )
            except Exception as e:
                logger.error("Skill generation failed: %s", e)

    # ===============================
    # Rerun hook implementations (override base class methods)
    # ===============================

    def _pre_process_rerun(self, request: RerunFeedbackGenerationRequest) -> None:
        """Delete existing pending raw feedbacks before generating new ones.

        This ensures that each rerun starts fresh without accumulating pending feedbacks
        from previous reruns.

        Args:
            request: RerunFeedbackGenerationRequest with optional agent_version and feedback_name filters
        """
        deleted_count = self.storage.delete_all_raw_feedbacks_by_status(
            status=Status.PENDING,
            agent_version=request.agent_version,
            feedback_name=request.feedback_name,
        )
        logger.info(
            "Deleted %d existing pending raw feedbacks before rerun (agent_version=%s, feedback_name=%s)",
            deleted_count,
            request.agent_version,
            request.feedback_name,
        )

    def _get_rerun_user_ids(self, request: RerunFeedbackGenerationRequest) -> list[str]:
        """Get user IDs to process. Extractors collect their own data.

        Identifies unique user_ids with matching requests via storage-level filtering.

        Args:
            request: RerunFeedbackGenerationRequest with optional time and source filters

        Returns:
            List of user IDs to process
        """
        return self.storage.get_rerun_user_ids(
            user_id=None,
            start_time=(
                int(request.start_time.timestamp()) if request.start_time else None
            ),
            end_time=(int(request.end_time.timestamp()) if request.end_time else None),
            source=request.source,
            agent_version=request.agent_version,
        )

    def _build_rerun_request_params(
        self, request: RerunFeedbackGenerationRequest
    ) -> dict:
        """Build request params dict for operation state tracking.

        Args:
            request: Original rerun request

        Returns:
            Dictionary of request parameters
        """
        return {
            "agent_version": request.agent_version,
            "start_time": (
                request.start_time.isoformat() if request.start_time else None
            ),
            "end_time": request.end_time.isoformat() if request.end_time else None,
            "feedback_name": request.feedback_name,
        }

    def _create_run_request_for_item(
        self,
        user_id: str,
        request: Union[RerunFeedbackGenerationRequest, ManualFeedbackGenerationRequest],
    ) -> FeedbackGenerationRequest:
        """Create FeedbackGenerationRequest for a single user.

        Handles both rerun and manual request types.

        Args:
            user_id: The user ID to process
            request: The original rerun or manual request

        Returns:
            FeedbackGenerationRequest for this user with filter constraints
        """
        # Handle rerun requests (have start_time/end_time datetime objects)
        if isinstance(request, RerunFeedbackGenerationRequest):
            return FeedbackGenerationRequest(
                request_id=f"rerun_feedback_{uuid.uuid4().hex[:8]}",
                agent_version=request.agent_version,
                user_id=user_id,
                source=request.source,
                rerun_start_time=(
                    int(request.start_time.timestamp()) if request.start_time else None
                ),
                rerun_end_time=(
                    int(request.end_time.timestamp()) if request.end_time else None
                ),
                feedback_name=request.feedback_name,
                auto_run=False,
            )
        # Handle manual requests (ManualFeedbackGenerationRequest)
        return FeedbackGenerationRequest(
            request_id=f"manual_{uuid.uuid4().hex[:8]}",
            agent_version=request.agent_version,
            user_id=user_id,
            source=request.source,
            auto_run=False,
        )

    def _create_rerun_response(
        self, success: bool, msg: str, count: int
    ) -> RerunFeedbackGenerationResponse:
        """Create RerunFeedbackGenerationResponse.

        Args:
            success: Whether the operation succeeded
            msg: Status message
            count: Number of feedbacks generated

        Returns:
            RerunFeedbackGenerationResponse
        """
        return RerunFeedbackGenerationResponse(
            success=success,
            msg=msg,
            feedbacks_generated=count,
        )

    def _get_generated_count(self, request: RerunFeedbackGenerationRequest) -> int:
        """Get the count of feedbacks generated during rerun.

        Counts feedbacks with pending status, filtered by agent_version and optionally feedback_name.

        Args:
            request: The rerun request object

        Returns:
            Number of feedbacks generated
        """
        feedbacks = self.storage.get_raw_feedbacks(
            feedback_name=request.feedback_name,
            agent_version=request.agent_version,
            status_filter=[Status.PENDING],
            limit=10000,
        )
        return len(feedbacks)

    # ===============================
    # Manual Regular Generation (window-sized, CURRENT output)
    # ===============================

    def run_manual_regular(
        self, request: ManualFeedbackGenerationRequest
    ) -> ManualFeedbackGenerationResponse:
        """
        Run feedback generation with window-sized interactions and CURRENT output.

        Processes feedbacks per-user. Each extractor collects its own data
        using its configured window_size.
        Uses progress tracking via OperationStateManager.

        Args:
            request: ManualFeedbackGenerationRequest with agent_version, optional source and feedback_name

        Returns:
            ManualFeedbackGenerationResponse with success status and count
        """
        state_manager = self._create_state_manager()

        try:
            # Check for existing in-progress operation
            error = state_manager.check_in_progress()
            if error:
                return ManualFeedbackGenerationResponse(
                    success=False, msg=error, feedbacks_generated=0
                )

            # 1. Get user_ids with recent interactions
            requests_dict = self.storage.get_sessions(
                user_id=None,  # All users
                top_k=1000,  # Get recent sessions to find users
            )

            # Get unique user_ids
            user_ids_set: set[str] = set()
            for session_requests in requests_dict.values():
                for rig in session_requests:
                    # Apply source filter if provided
                    if request.source and rig.request.source != request.source:
                        continue
                    user_ids_set.add(rig.request.user_id)

            user_ids = list(user_ids_set)

            if not user_ids:
                return ManualFeedbackGenerationResponse(
                    success=True,
                    msg="No interactions found to process",
                    feedbacks_generated=0,
                )

            # 2. Run batch with progress tracking
            request_params = {
                "agent_version": request.agent_version,
                "source": request.source,
                "feedback_name": request.feedback_name,
                "mode": "manual_regular",
            }
            self._run_batch_with_progress(
                user_ids=user_ids,
                request=request,
                request_params=request_params,
                state_manager=state_manager,
            )

            # 3. Count generated feedbacks (CURRENT status = None)
            total_feedbacks = self._count_manual_generated(request)

            return ManualFeedbackGenerationResponse(
                success=True,
                msg=f"Generated {total_feedbacks} feedbacks",
                feedbacks_generated=total_feedbacks,
            )

        except Exception as e:
            state_manager.mark_progress_failed(str(e))
            return ManualFeedbackGenerationResponse(
                success=False,
                msg=f"Failed to generate feedbacks: {str(e)}",
                feedbacks_generated=0,
            )

    def _count_manual_generated(self, request: ManualFeedbackGenerationRequest) -> int:
        """
        Count feedbacks generated during manual regular generation.

        Counts feedbacks with CURRENT status (None), filtered by agent_version
        and optionally feedback_name.

        Args:
            request: The manual generation request object

        Returns:
            Number of feedbacks with CURRENT status
        """
        feedbacks = self.storage.get_raw_feedbacks(
            feedback_name=request.feedback_name,
            agent_version=request.agent_version,
            status_filter=[None],  # CURRENT feedbacks
            limit=10000,
        )
        return len(feedbacks)

    # ===============================
    # Upgrade/Downgrade hook implementations (override base class methods)
    # ===============================

    def _has_items_with_status(self, status, request) -> bool:
        """Check if raw feedbacks exist with given status.

        Args:
            status: The status to check for (None for CURRENT)
            request: The upgrade/downgrade request object

        Returns:
            bool: True if any matching raw feedbacks exist
        """
        return self.storage.has_raw_feedbacks_with_status(
            status=status,
            agent_version=getattr(request, "agent_version", None),
            feedback_name=getattr(request, "feedback_name", None),
        )

    def _delete_items_by_status(self, status, request) -> int:
        """Delete raw feedbacks with given status.

        Args:
            status: The status of raw feedbacks to delete
            request: The upgrade/downgrade request object

        Returns:
            int: Number of raw feedbacks deleted
        """
        return self.storage.delete_all_raw_feedbacks_by_status(
            status=status,
            agent_version=getattr(request, "agent_version", None),
            feedback_name=getattr(request, "feedback_name", None),
        )

    def _update_items_status(
        self, old_status, new_status, request, user_ids=None
    ) -> int:
        """Update raw feedbacks from old_status to new_status with request filters.

        Args:
            old_status: The current status to match (None for CURRENT)
            new_status: The new status to set (None for CURRENT)
            request: The upgrade/downgrade request object with filters
            user_ids: Optional pre-computed list of user IDs (not used for feedbacks)

        Returns:
            int: Number of raw feedbacks updated
        """
        # Note: user_ids is ignored for feedback service as it uses agent_version/feedback_name filters
        return self.storage.update_all_raw_feedbacks_status(
            old_status=old_status,
            new_status=new_status,
            agent_version=getattr(request, "agent_version", None),
            feedback_name=getattr(request, "feedback_name", None),
        )

    def _create_status_change_response(self, operation, success, counts, msg):
        """Create upgrade or downgrade response object for raw feedbacks.

        Args:
            operation: The operation type (UPGRADE or DOWNGRADE)
            success: Whether the operation succeeded
            counts: Dictionary of counts
            msg: Status message

        Returns:
            UpgradeRawFeedbacksResponse or DowngradeRawFeedbacksResponse
        """
        if operation == StatusChangeOperation.UPGRADE:
            return UpgradeRawFeedbacksResponse(
                success=success,
                raw_feedbacks_deleted=counts.get("deleted", 0),
                raw_feedbacks_archived=counts.get("archived", 0),
                raw_feedbacks_promoted=counts.get("promoted", 0),
                message=msg,
            )
        else:  # DOWNGRADE
            return DowngradeRawFeedbacksResponse(
                success=success,
                raw_feedbacks_demoted=counts.get("demoted", 0),
                raw_feedbacks_restored=counts.get("restored", 0),
                message=msg,
            )
