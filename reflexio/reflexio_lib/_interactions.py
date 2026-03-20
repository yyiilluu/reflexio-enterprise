from __future__ import annotations

from reflexio_commons.api_schema.retriever_schema import (
    GetInteractionsRequest,
    GetInteractionsResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    BulkDeleteResponse,
    DeleteRequestRequest,
    DeleteRequestResponse,
    DeleteRequestsByIdsRequest,
    DeleteSessionRequest,
    DeleteSessionResponse,
    DeleteUserInteractionRequest,
    DeleteUserInteractionResponse,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
)

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)
from reflexio.server.services.generation_service import GenerationService


class InteractionsMixin(ReflexioBase):
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

    @_require_storage(BulkDeleteResponse)
    def delete_all_interactions_bulk(self) -> BulkDeleteResponse:
        """Delete all requests and their associated interactions.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        self._get_storage().delete_all_requests()
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
