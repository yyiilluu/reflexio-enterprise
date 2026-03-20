from __future__ import annotations

from typing import Any

from reflexio_commons.api_schema.service_schemas import (
    ManualFeedbackGenerationRequest,
    ManualFeedbackGenerationResponse,
    ManualProfileGenerationRequest,
    ManualProfileGenerationResponse,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
)

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio.server.services.profile.profile_generation_service import (
    ProfileGenerationService,
)


class GenerationMixin(ReflexioBase):
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
