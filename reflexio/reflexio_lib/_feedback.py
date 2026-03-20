from __future__ import annotations

from reflexio_commons.api_schema.retriever_schema import (
    GetFeedbacksRequest,
    GetFeedbacksResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    UpdateFeedbackStatusRequest,
    UpdateFeedbackStatusResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    AddFeedbackRequest,
    AddFeedbackResponse,
    BulkDeleteResponse,
    DeleteFeedbackRequest,
    DeleteFeedbackResponse,
    DeleteFeedbacksByIdsRequest,
    Feedback,
    FeedbackAggregationChangeLogResponse,
)

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)


class FeedbackMixin(ReflexioBase):
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
