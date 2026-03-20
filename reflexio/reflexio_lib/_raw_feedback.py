from __future__ import annotations

from reflexio_commons.api_schema.retriever_schema import (
    GetRawFeedbacksRequest,
    GetRawFeedbacksResponse,
    SearchRawFeedbackRequest,
    SearchRawFeedbackResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    BulkDeleteResponse,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbackResponse,
    DeleteRawFeedbacksByIdsRequest,
    DowngradeRawFeedbacksRequest,
    DowngradeRawFeedbacksResponse,
    RawFeedback,
    UpgradeRawFeedbacksRequest,
    UpgradeRawFeedbacksResponse,
)

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)
from reflexio.server.services.feedback.feedback_generation_service import (
    FeedbackGenerationService,
)


class RawFeedbackMixin(ReflexioBase):
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
