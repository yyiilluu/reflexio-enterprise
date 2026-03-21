import asyncio
import logging
import os
import time
import warnings
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, TypeVar
from urllib.parse import urljoin

import aiohttp
import requests
from dotenv import load_dotenv
from reflexio_commons.api_schema.login_schema import Token
from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    GetAgentSuccessEvaluationResultsRequest,
    GetAgentSuccessEvaluationResultsResponse,
    GetFeedbacksRequest,
    GetFeedbacksResponse,
    GetInteractionsRequest,
    GetInteractionsResponse,
    GetRawFeedbacksRequest,
    GetRawFeedbacksResponse,
    GetRequestsRequest,
    GetRequestsResponse,
    GetUserProfilesRequest,
    GetUserProfilesResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SearchInteractionRequest,
    SearchInteractionResponse,
    SearchRawFeedbackRequest,
    SearchRawFeedbackResponse,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
)
from reflexio_commons.config_schema import SearchMode

# Load environment variables from .env file
load_dotenv()

IS_TEST_ENV = os.environ.get("IS_TEST_ENV", "false").strip() == "true"

BACKEND_URL = "http://127.0.0.1:8000" if IS_TEST_ENV else "https://www.reflexio.com/"

from reflexio_commons.api_schema.service_schemas import (
    AddFeedbackRequest,
    AddFeedbackResponse,
    AddRawFeedbackRequest,
    AddRawFeedbackResponse,
    BulkDeleteResponse,
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
    Feedback,
    FeedbackStatus,
    GetOperationStatusResponse,
    InteractionData,
    ManualFeedbackGenerationRequest,
    ManualProfileGenerationRequest,
    OperationStatus,
    ProfileChangeLogResponse,
    PublishUserInteractionRequest,
    PublishUserInteractionResponse,
    RawFeedback,
    RerunFeedbackGenerationRequest,
    RerunFeedbackGenerationResponse,
    RerunProfileGenerationRequest,
    RerunProfileGenerationResponse,
    RunFeedbackAggregationRequest,
    RunFeedbackAggregationResponse,
    Status,
)
from reflexio_commons.config_schema import Config

from .cache import InMemoryCache

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ReflexioClient:
    """Client for interacting with the Reflexio API."""

    # Shared thread pool for all instances to maximize efficiency
    _thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="reflexio")

    def __init__(
        self, api_key: str = "", url_endpoint: str = "", timeout: int = 300
    ) -> None:
        """Initialize the Reflexio client.

        The client authenticates using an API key. You can provide the key directly
        or set the REFLEXIO_API_KEY environment variable. Similarly, the URL can be
        provided directly or via the REFLEXIO_API_URL environment variable.

        Args:
            api_key (str): Your API key for authentication. Falls back to REFLEXIO_API_KEY env var.
            url_endpoint (str): Base URL for the API. Falls back to REFLEXIO_API_URL env var,
                then to the default backend URL.
            timeout (int): Default request timeout in seconds (default 300)
        """
        self.api_key = api_key or os.environ.get("REFLEXIO_API_KEY", "")
        self.base_url = (
            url_endpoint or os.environ.get("REFLEXIO_API_URL", "") or BACKEND_URL
        )
        self.timeout = timeout
        self.session = requests.Session()
        self._cache = InMemoryCache()

    def _get_auth_headers(self) -> dict:
        """Get authentication headers for API requests.

        Returns:
            dict: Headers with authorization and content-type
        """
        if self.api_key:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        return {}

    def _convert_to_model(self, data: dict | object, model_class: type[T]) -> T:
        """Convert dict to model instance if needed.

        Args:
            data: Either a dict or already an instance of model_class
            model_class: The target class to convert to

        Returns:
            An instance of model_class
        """
        if isinstance(data, dict):
            return model_class(**data)
        return data  # type: ignore[reportReturnType]

    def _build_request(
        self,
        request: T | dict | None,
        model_class: type[T],
        **kwargs: Any,
    ) -> T:
        """Build request object from request param or kwargs.

        Args:
            request: Optional request object or dict
            model_class: The request class to instantiate
            **kwargs: Field values to use if request is None

        Returns:
            An instance of model_class
        """
        if request is not None:
            return self._convert_to_model(request, model_class)  # type: ignore[reportReturnType]
        # Filter out None values and build from kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return model_class(**filtered_kwargs)

    def _fire_and_forget(
        self,
        async_func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Execute an async request in fire-and-forget mode.

        Args:
            async_func: Asynchronous function to call
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(async_func(*args, **kwargs))
        except RuntimeError:
            self._thread_pool.submit(lambda: asyncio.run(async_func(*args, **kwargs)))

    async def _make_async_request(
        self, method: str, endpoint: str, headers: dict | None = None, **kwargs: Any
    ) -> Any:
        """Make an async HTTP request to the API."""
        url = urljoin(self.base_url, endpoint)

        # Merge auth headers with any provided headers
        request_headers = self._get_auth_headers()
        if headers:
            request_headers.update(headers)

        async with aiohttp.ClientSession() as async_session:
            response = await async_session.request(
                method, url, headers=request_headers, **kwargs
            )
            response.raise_for_status()
            return await response.json()

    def _make_request(
        self, method: str, endpoint: str, headers: dict | None = None, **kwargs: Any
    ) -> Any:
        """Make an HTTP request to the API.

        Args:
            method (str): HTTP method (GET, POST, DELETE)
            endpoint (str): API endpoint
            headers (dict, optional): Additional headers to include in the request
            **kwargs: Additional arguments to pass to requests

        Returns:
            dict: API response
        """
        url = urljoin(self.base_url, endpoint)

        # Merge auth headers with any provided headers
        request_headers = self._get_auth_headers()
        if headers:
            request_headers.update(headers)

        self.session.headers.update(request_headers)
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def login(self, email: str, password: str) -> Token:
        """Login to the Reflexio API.

        .. deprecated::
            The login() method is deprecated. Pass your API key directly instead:

            client = ReflexioClient(api_key="your-api-key")

            Or set the REFLEXIO_API_KEY environment variable:

            export REFLEXIO_API_KEY="your-api-key"
            client = ReflexioClient()

        Args:
            email (str): User email
            password (str): User password

        Returns:
            Token: Authentication token response
        """
        warnings.warn(
            "login() is deprecated. Pass api_key directly to ReflexioClient() "
            "or set the REFLEXIO_API_KEY environment variable instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        response = self._make_request(
            "POST",
            "/token",
            data={"username": email, "password": password},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "accept": "application/json",
            },
        )
        self.api_key = response["api_key"]
        return Token(**response)

    def _publish_interaction_sync(
        self,
        request: PublishUserInteractionRequest,
        wait_for_response: bool = False,
    ) -> PublishUserInteractionResponse:
        """Internal sync method to publish interaction.

        Args:
            request (PublishUserInteractionRequest): The publish request
            wait_for_response (bool): If True, server processes synchronously and returns real result
        """
        params = {"wait_for_response": "true"} if wait_for_response else None
        response = self._make_request(
            "POST",
            "/api/publish_interaction",
            json=request.model_dump(),
            params=params,
        )
        return PublishUserInteractionResponse(**response)

    async def _publish_interaction_async(
        self,
        request: PublishUserInteractionRequest,
        wait_for_response: bool = False,
    ) -> PublishUserInteractionResponse:
        """Internal async method to publish interaction.

        Args:
            request (PublishUserInteractionRequest): The publish request
            wait_for_response (bool): If True, server processes synchronously and returns real result
        """
        params = {"wait_for_response": "true"} if wait_for_response else None
        response = await self._make_async_request(
            "POST",
            "/api/publish_interaction",
            json=request.model_dump(),
            params=params,
        )
        return PublishUserInteractionResponse(**response)

    def publish_interaction(
        self,
        user_id: str,
        interactions: list[InteractionData | dict],
        source: str = "",
        agent_version: str = "",
        session_id: str | None = None,
        wait_for_response: bool = False,
    ) -> PublishUserInteractionResponse | None:
        """Publish user interactions.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            user_id (str): The user ID
            interactions (List[InteractionData]): List of interaction data
            source (str, optional): The source of the interaction
            agent_version (str, optional): The agent version
            session_id (Optional[str], optional): The session ID for grouping requests together. Defaults to None.
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.
        Returns:
            Optional[PublishUserInteractionResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        interaction_data_list = [
            (
                InteractionData(**interaction_request)
                if isinstance(interaction_request, dict)
                else interaction_request
            )
            for interaction_request in interactions
        ]
        request = PublishUserInteractionRequest(
            session_id=session_id,
            user_id=user_id,
            interaction_data_list=interaction_data_list,
            source=source,
            agent_version=agent_version,
        )

        if wait_for_response:
            # Synchronous blocking call — server processes synchronously too
            return self._publish_interaction_sync(request, wait_for_response=True)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._publish_interaction_async, request)
        return None

    def search_interactions(
        self,
        request: SearchInteractionRequest | dict | None = None,
        *,
        user_id: str | None = None,
        request_id: str | None = None,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        top_k: int | None = None,
        most_recent_k: int | None = None,
        search_mode: SearchMode | None = None,
    ) -> SearchInteractionResponse:
        """Search for user interactions.

        Args:
            request (Optional[SearchInteractionRequest]): The search request object (alternative to kwargs)
            user_id (str): The user ID to search for
            request_id (Optional[str]): Filter by specific request ID
            query (Optional[str]): Search query string
            start_time (Optional[datetime]): Filter by start time
            end_time (Optional[datetime]): Filter by end time
            top_k (Optional[int]): Maximum number of results to return
            most_recent_k (Optional[int]): Return most recent k interactions

        Returns:
            SearchInteractionResponse: Response containing matching interactions
        """
        req = self._build_request(
            request,
            SearchInteractionRequest,
            user_id=user_id,
            request_id=request_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            top_k=top_k,
            most_recent_k=most_recent_k,
            search_mode=search_mode,
        )
        response = self._make_request(
            "POST",
            "/api/search_interactions",
            json=req.model_dump(),
        )
        return SearchInteractionResponse(**response)

    def search_profiles(
        self,
        request: SearchUserProfileRequest | dict | None = None,
        *,
        user_id: str | None = None,
        generated_from_request_id: str | None = None,
        query: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        top_k: int | None = None,
        source: str | None = None,
        custom_feature: str | None = None,
        extractor_name: str | None = None,
        threshold: float | None = None,
        query_rewrite: bool | None = None,
        search_mode: SearchMode | None = None,
    ) -> SearchUserProfileResponse:
        """Search for user profiles.

        Args:
            request (Optional[SearchUserProfileRequest]): The search request object (alternative to kwargs)
            user_id (str): The user ID to search for
            generated_from_request_id (Optional[str]): Filter by request ID that generated the profile
            query (Optional[str]): Search query string
            start_time (Optional[datetime]): Filter by start time
            end_time (Optional[datetime]): Filter by end time
            top_k (Optional[int]): Maximum number of results to return (default: 10)
            source (Optional[str]): Filter by source
            custom_feature (Optional[str]): Filter by custom feature
            extractor_name (Optional[str]): Filter by extractor name
            threshold (Optional[float]): Similarity threshold (default: 0.7)
            query_rewrite (Optional[bool]): Enable LLM query rewriting (default: False)

        Returns:
            SearchUserProfileResponse: Response containing matching profiles
        """
        req = self._build_request(
            request,
            SearchUserProfileRequest,
            user_id=user_id,
            generated_from_request_id=generated_from_request_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
            top_k=top_k,
            source=source,
            custom_feature=custom_feature,
            extractor_name=extractor_name,
            threshold=threshold,
            query_rewrite=query_rewrite,
            search_mode=search_mode,
        )
        response = self._make_request(
            "POST", "/api/search_profiles", json=req.model_dump()
        )
        return SearchUserProfileResponse(**response)

    def search_raw_feedbacks(
        self,
        request: SearchRawFeedbackRequest | dict | None = None,
        *,
        query: str | None = None,
        user_id: str | None = None,
        agent_version: str | None = None,
        feedback_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status_filter: list[Status | None] | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
        query_rewrite: bool | None = None,
        search_mode: SearchMode | None = None,
    ) -> SearchRawFeedbackResponse:
        """Search for raw feedbacks with semantic/text search and filtering.

        Args:
            request (Optional[SearchRawFeedbackRequest]): The search request object (alternative to kwargs)
            query (Optional[str]): Query for semantic/text search
            user_id (Optional[str]): Filter by user (via request_id linkage to requests table)
            agent_version (Optional[str]): Filter by agent version
            feedback_name (Optional[str]): Filter by feedback name
            start_time (Optional[datetime]): Start time for created_at filter
            end_time (Optional[datetime]): End time for created_at filter
            status_filter (Optional[list[Optional[Status]]]): Filter by status (None for CURRENT, PENDING, ARCHIVED)
            top_k (Optional[int]): Maximum number of results to return (default: 10)
            threshold (Optional[float]): Similarity threshold for vector search (default: 0.5)
            query_rewrite (Optional[bool]): Enable LLM query rewriting (default: False)

        Returns:
            SearchRawFeedbackResponse: Response containing matching raw feedbacks
        """
        req = self._build_request(
            request,
            SearchRawFeedbackRequest,
            query=query,
            user_id=user_id,
            agent_version=agent_version,
            feedback_name=feedback_name,
            start_time=start_time,
            end_time=end_time,
            status_filter=status_filter,
            top_k=top_k,
            threshold=threshold,
            query_rewrite=query_rewrite,
            search_mode=search_mode,
        )
        response = self._make_request(
            "POST", "/api/search_raw_feedbacks", json=req.model_dump()
        )
        return SearchRawFeedbackResponse(**response)

    def search_feedbacks(
        self,
        request: SearchFeedbackRequest | dict | None = None,
        *,
        query: str | None = None,
        agent_version: str | None = None,
        feedback_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status_filter: list[Status | None] | None = None,
        feedback_status_filter: FeedbackStatus | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
        query_rewrite: bool | None = None,
        search_mode: SearchMode | None = None,
    ) -> SearchFeedbackResponse:
        """Search for aggregated feedbacks with semantic/text search and filtering.

        Args:
            request (Optional[SearchFeedbackRequest]): The search request object (alternative to kwargs)
            query (Optional[str]): Query for semantic/text search
            agent_version (Optional[str]): Filter by agent version
            feedback_name (Optional[str]): Filter by feedback name
            start_time (Optional[datetime]): Start time for created_at filter
            end_time (Optional[datetime]): End time for created_at filter
            status_filter (Optional[list[Optional[Status]]]): Filter by status (None for CURRENT, PENDING, ARCHIVED)
            feedback_status_filter (Optional[FeedbackStatus]): Filter by feedback status (PENDING, APPROVED, REJECTED)
            top_k (Optional[int]): Maximum number of results to return (default: 10)
            threshold (Optional[float]): Similarity threshold for vector search (default: 0.5)
            query_rewrite (Optional[bool]): Enable LLM query rewriting (default: False)

        Returns:
            SearchFeedbackResponse: Response containing matching feedbacks
        """
        req = self._build_request(
            request,
            SearchFeedbackRequest,
            query=query,
            agent_version=agent_version,
            feedback_name=feedback_name,
            start_time=start_time,
            end_time=end_time,
            status_filter=status_filter,
            feedback_status_filter=feedback_status_filter,
            top_k=top_k,
            threshold=threshold,
            query_rewrite=query_rewrite,
            search_mode=search_mode,
        )
        response = self._make_request(
            "POST", "/api/search_feedbacks", json=req.model_dump()
        )
        return SearchFeedbackResponse(**response)

    def _delete_profile_sync(
        self, request: DeleteUserProfileRequest
    ) -> DeleteUserProfileResponse:
        """Internal sync method to delete profile."""
        response = self._make_request(
            "DELETE",
            "/api/delete_profile",
            json=request.model_dump(),
        )
        return DeleteUserProfileResponse(**response)

    async def _delete_profile_async(
        self, request: DeleteUserProfileRequest
    ) -> DeleteUserProfileResponse:
        """Internal async method to delete profile."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_profile",
            json=request.model_dump(),
        )
        return DeleteUserProfileResponse(**response)

    def delete_profile(
        self,
        user_id: str,
        profile_id: str = "",
        search_query: str = "",
        wait_for_response: bool = False,
    ) -> DeleteUserProfileResponse | None:
        """Delete user profiles.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            user_id (str): The user ID
            profile_id (str, optional): Specific profile ID to delete
            search_query (str, optional): Query to match profiles for deletion
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteUserProfileResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        request = DeleteUserProfileRequest(
            user_id=user_id,
            profile_id=profile_id,
            search_query=search_query,
        )

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_profile_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_profile_async, request)
        return None

    def _delete_interaction_sync(
        self, request: DeleteUserInteractionRequest
    ) -> DeleteUserInteractionResponse:
        """Internal sync method to delete interaction."""
        response = self._make_request(
            "DELETE",
            "/api/delete_interaction",
            json=request.model_dump(),
        )
        return DeleteUserInteractionResponse(**response)

    async def _delete_interaction_async(
        self, request: DeleteUserInteractionRequest
    ) -> DeleteUserInteractionResponse:
        """Internal async method to delete interaction."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_interaction",
            json=request.model_dump(),
        )
        return DeleteUserInteractionResponse(**response)

    def delete_interaction(
        self, user_id: str, interaction_id: str, wait_for_response: bool = False
    ) -> DeleteUserInteractionResponse | None:
        """Delete a user interaction.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            user_id (str): The user ID
            interaction_id (str): The interaction ID to delete
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteUserInteractionResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        request = DeleteUserInteractionRequest(
            user_id=user_id,
            interaction_id=interaction_id,  # type: ignore[reportArgumentType]
        )

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_interaction_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_interaction_async, request)
        return None

    def _delete_request_sync(
        self, request: DeleteRequestRequest
    ) -> DeleteRequestResponse:
        """Internal sync method to delete request."""
        response = self._make_request(
            "DELETE",
            "/api/delete_request",
            json=request.model_dump(),
        )
        return DeleteRequestResponse(**response)

    async def _delete_request_async(
        self, request: DeleteRequestRequest
    ) -> DeleteRequestResponse:
        """Internal async method to delete request."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_request",
            json=request.model_dump(),
        )
        return DeleteRequestResponse(**response)

    def delete_request(
        self, request_id: str, wait_for_response: bool = False
    ) -> DeleteRequestResponse | None:
        """Delete a request and all its associated interactions.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            request_id (str): The request ID to delete
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteRequestResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        request = DeleteRequestRequest(request_id=request_id)

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_request_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_request_async, request)
        return None

    def _delete_session_sync(
        self, request: DeleteSessionRequest
    ) -> DeleteSessionResponse:
        """Internal sync method to delete session."""
        response = self._make_request(
            "DELETE",
            "/api/delete_session",
            json=request.model_dump(),
        )
        return DeleteSessionResponse(**response)

    async def _delete_session_async(
        self, request: DeleteSessionRequest
    ) -> DeleteSessionResponse:
        """Internal async method to delete session."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_session",
            json=request.model_dump(),
        )
        return DeleteSessionResponse(**response)

    def delete_session(
        self, session_id: str, wait_for_response: bool = False
    ) -> DeleteSessionResponse | None:
        """Delete all requests and interactions in a session.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            session_id (str): The session ID to delete
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteSessionResponse]: Response containing success status, message, and deleted count if wait_for_response=True, None otherwise
        """
        request = DeleteSessionRequest(session_id=session_id)

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_session_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_session_async, request)
        return None

    def _delete_feedback_sync(
        self, request: DeleteFeedbackRequest
    ) -> DeleteFeedbackResponse:
        """Internal sync method to delete feedback."""
        response = self._make_request(
            "DELETE",
            "/api/delete_feedback",
            json=request.model_dump(),
        )
        return DeleteFeedbackResponse(**response)

    async def _delete_feedback_async(
        self, request: DeleteFeedbackRequest
    ) -> DeleteFeedbackResponse:
        """Internal async method to delete feedback."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_feedback",
            json=request.model_dump(),
        )
        return DeleteFeedbackResponse(**response)

    def delete_feedback(
        self, feedback_id: int, wait_for_response: bool = False
    ) -> DeleteFeedbackResponse | None:
        """Delete a feedback by ID.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            feedback_id (int): The feedback ID to delete
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteFeedbackResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        request = DeleteFeedbackRequest(feedback_id=feedback_id)

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_feedback_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_feedback_async, request)
        return None

    def _delete_raw_feedback_sync(
        self, request: DeleteRawFeedbackRequest
    ) -> DeleteRawFeedbackResponse:
        """Internal sync method to delete raw feedback."""
        response = self._make_request(
            "DELETE",
            "/api/delete_raw_feedback",
            json=request.model_dump(),
        )
        return DeleteRawFeedbackResponse(**response)

    async def _delete_raw_feedback_async(
        self, request: DeleteRawFeedbackRequest
    ) -> DeleteRawFeedbackResponse:
        """Internal async method to delete raw feedback."""
        response = await self._make_async_request(
            "DELETE",
            "/api/delete_raw_feedback",
            json=request.model_dump(),
        )
        return DeleteRawFeedbackResponse(**response)

    def delete_raw_feedback(
        self, raw_feedback_id: int, wait_for_response: bool = False
    ) -> DeleteRawFeedbackResponse | None:
        """Delete a raw feedback by ID.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            raw_feedback_id (int): The raw feedback ID to delete
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.

        Returns:
            Optional[DeleteRawFeedbackResponse]: Response containing success status and message if wait_for_response=True, None otherwise
        """
        request = DeleteRawFeedbackRequest(raw_feedback_id=raw_feedback_id)

        if wait_for_response:
            # Synchronous blocking call
            return self._delete_raw_feedback_sync(request)
        # Non-blocking fire-and-forget
        self._fire_and_forget(self._delete_raw_feedback_async, request)
        return None

    def get_profile_change_log(self) -> ProfileChangeLogResponse:
        """Get profile change log.

        Returns:
            ProfileChangeLogResponse: Response containing profile change log
        """
        response = self._make_request("GET", "/api/profile_change_log")
        return ProfileChangeLogResponse(**response)

    def get_interactions(
        self,
        request: GetInteractionsRequest | dict | None = None,
        *,
        user_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        top_k: int | None = None,
    ) -> GetInteractionsResponse:
        """Get user interactions.

        Args:
            request (Optional[GetInteractionsRequest]): The list request object (alternative to kwargs)
            user_id (str): The user ID to get interactions for
            start_time (Optional[datetime]): Filter by start time
            end_time (Optional[datetime]): Filter by end time
            top_k (Optional[int]): Maximum number of results to return (default: 30)

        Returns:
            GetInteractionsResponse: Response containing list of interactions
        """
        req = self._build_request(
            request,
            GetInteractionsRequest,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            top_k=top_k,
        )
        response = self._make_request(
            "POST",
            "/api/get_interactions",
            json=req.model_dump(),
        )
        return GetInteractionsResponse(**response)

    def get_profiles(
        self,
        request: GetUserProfilesRequest | dict | None = None,
        force_refresh: bool = False,
        *,
        user_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        top_k: int | None = None,
        status_filter: list[Status | str | None] | None = None,
    ) -> GetUserProfilesResponse:
        """Get user profiles.

        Args:
            request (Optional[GetUserProfilesRequest]): The list request object (alternative to kwargs)
            force_refresh (bool, optional): If True, bypass cache and fetch fresh data. Defaults to False.
            user_id (str): The user ID to get profiles for
            start_time (Optional[datetime]): Filter by start time
            end_time (Optional[datetime]): Filter by end time
            top_k (Optional[int]): Maximum number of results to return (default: 30)
            status_filter (Optional[list[Optional[Union[Status, str]]]]): Filter by profile status. Accepts Status enum or string values (e.g., "archived", "pending").

        Returns:
            GetUserProfilesResponse: Response containing list of profiles
        """
        # Convert string status values to Status enum
        converted_status_filter = None
        if status_filter is not None:
            converted_status_filter = []
            for status in status_filter:
                if status is None:
                    converted_status_filter.append(None)
                elif isinstance(status, str):
                    converted_status_filter.append(Status(status))
                else:
                    converted_status_filter.append(status)

        req = self._build_request(
            request,
            GetUserProfilesRequest,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            top_k=top_k,
            status_filter=converted_status_filter,
        )

        # Check cache if not forcing refresh
        if not force_refresh:
            cached_result = self._cache.get(
                "get_profiles",
                user_id=req.user_id,
                start_time=req.start_time,
                end_time=req.end_time,
                top_k=req.top_k,
                status_filter=req.status_filter,
            )
            if cached_result is not None:
                return cached_result

        # Make API call
        response = self._make_request(
            "POST",
            "/api/get_profiles",
            json=req.model_dump(),
        )
        result = GetUserProfilesResponse(**response)

        # Store in cache
        self._cache.set(
            "get_profiles",
            result,
            user_id=req.user_id,
            start_time=req.start_time,
            end_time=req.end_time,
            top_k=req.top_k,
            status_filter=req.status_filter,
        )

        return result

    def get_all_interactions(
        self,
        limit: int = 100,
    ) -> GetInteractionsResponse:
        """Get all user interactions across all users.

        Args:
            limit (int, optional): Maximum number of interactions to return. Defaults to 100.

        Returns:
            GetInteractionsResponse: Response containing all user interactions
        """
        response = self._make_request(
            "GET",
            f"/api/get_all_interactions?limit={limit}",
        )
        return GetInteractionsResponse(**response)

    def get_all_profiles(
        self,
        limit: int = 100,
    ) -> GetUserProfilesResponse:
        """Get all user profiles across all users.

        Args:
            limit (int, optional): Maximum number of profiles to return. Defaults to 100.

        Returns:
            GetUserProfilesResponse: Response containing all user profiles
        """
        response = self._make_request(
            "GET",
            f"/api/get_all_profiles?limit={limit}",
        )
        return GetUserProfilesResponse(**response)

    def set_config(self, config: Config | dict) -> dict:
        """Set configuration for the organization.

        Args:
            config (Union[Config, dict]): The configuration to set

        Returns:
            dict: Response containing success status and message
        """
        config = self._convert_to_model(config, Config)  # type: ignore[reportAssignmentType]
        return self._make_request(
            "POST",
            "/api/set_config",
            json=config.model_dump(),  # type: ignore[reportAttributeAccessIssue]
        )

    def get_config(self) -> Config:
        """Get configuration for the organization.

        Returns:
            Config: The current configuration
        """
        response = self._make_request(
            "GET",
            "/api/get_config",
        )
        return Config(**response)

    def get_raw_feedbacks(
        self,
        request: GetRawFeedbacksRequest | dict | None = None,
        *,
        limit: int | None = None,
        feedback_name: str | None = None,
        status_filter: list[Status | None] | None = None,
    ) -> GetRawFeedbacksResponse:
        """Get raw feedbacks.

        Args:
            request (Optional[GetRawFeedbacksRequest]): The get request object (alternative to kwargs)
            limit (Optional[int]): Maximum number of results to return (default: 100)
            feedback_name (Optional[str]): Filter by feedback name
            status_filter (Optional[list[Optional[Status]]]): Filter by status

        Returns:
            GetRawFeedbacksResponse: Response containing raw feedbacks
        """
        req = self._build_request(
            request,
            GetRawFeedbacksRequest,
            limit=limit,
            feedback_name=feedback_name,
            status_filter=status_filter,
        )
        response = self._make_request(
            "POST",
            "/api/get_raw_feedbacks",
            json=req.model_dump(),
        )
        return GetRawFeedbacksResponse(**response)

    def add_raw_feedback(
        self,
        raw_feedbacks: list[RawFeedback | dict],
    ) -> AddRawFeedbackResponse:
        """Add raw feedback directly to storage.

        Args:
            raw_feedbacks (list[Union[RawFeedback, dict]]): List of raw feedbacks to add.
                Each raw feedback should contain:
                - agent_version (str): Required. The agent version.
                - request_id (str): Required. The request ID.
                - feedback_content (str): Required. The feedback content.
                - feedback_name (str): Optional. The feedback name/category.

        Returns:
            AddRawFeedbackResponse: Response containing success status, message, and added count.
        """
        # Convert dicts to RawFeedback objects if needed
        raw_feedback_list = [
            RawFeedback(**rf) if isinstance(rf, dict) else rf for rf in raw_feedbacks
        ]
        request = AddRawFeedbackRequest(raw_feedbacks=raw_feedback_list)
        response = self._make_request(
            "POST",
            "/api/add_raw_feedback",
            json=request.model_dump(),
        )
        return AddRawFeedbackResponse(**response)

    def add_feedbacks(
        self,
        feedbacks: list[Feedback | dict],
    ) -> AddFeedbackResponse:
        """Add aggregated feedback directly to storage.

        Args:
            feedbacks (list[Union[Feedback, dict]]): List of feedbacks to add.
                Each feedback should contain:
                - agent_version (str): Required. The agent version.
                - feedback_content (str): Required. The feedback content.
                - feedback_status (FeedbackStatus): Required. The feedback approval status.
                - feedback_metadata (str): Required. Metadata about the feedback.
                - feedback_name (str): Optional. The feedback name/category.

        Returns:
            AddFeedbackResponse: Response containing success status, message, and added count.
        """
        # Convert dicts to Feedback objects if needed
        feedback_list = [
            Feedback(**fb) if isinstance(fb, dict) else fb for fb in feedbacks
        ]
        request = AddFeedbackRequest(feedbacks=feedback_list)
        response = self._make_request(
            "POST",
            "/api/add_feedbacks",
            json=request.model_dump(),
        )
        return AddFeedbackResponse(**response)

    def get_feedbacks(
        self,
        request: GetFeedbacksRequest | dict | None = None,
        force_refresh: bool = False,
        *,
        limit: int | None = None,
        feedback_name: str | None = None,
        status_filter: list[Status | None] | None = None,
        feedback_status_filter: FeedbackStatus | None = None,
    ) -> GetFeedbacksResponse:
        """Get feedbacks.

        Args:
            request (Optional[GetFeedbacksRequest]): The get request object (alternative to kwargs)
            force_refresh (bool, optional): If True, bypass cache and fetch fresh data. Defaults to False.
            limit (Optional[int]): Maximum number of results to return (default: 100)
            feedback_name (Optional[str]): Filter by feedback name
            status_filter (Optional[list[Optional[Status]]]): Filter by status
            feedback_status_filter (Optional[FeedbackStatus]): Filter by feedback status (default: APPROVED)

        Returns:
            GetFeedbacksResponse: Response containing feedbacks
        """
        req = self._build_request(
            request,
            GetFeedbacksRequest,
            limit=limit,
            feedback_name=feedback_name,
            status_filter=status_filter,
            feedback_status_filter=feedback_status_filter,
        )

        # Check cache if not forcing refresh
        if not force_refresh:
            cached_result = self._cache.get(
                "get_feedbacks",
                limit=req.limit,
                feedback_name=req.feedback_name,
                status_filter=req.status_filter,
                feedback_status_filter=req.feedback_status_filter,
            )
            if cached_result is not None:
                return cached_result

        # Make API call
        response = self._make_request(
            "POST",
            "/api/get_feedbacks",
            json=req.model_dump(),
        )
        result = GetFeedbacksResponse(**response)

        # Store in cache
        self._cache.set(
            "get_feedbacks",
            result,
            limit=req.limit,
            feedback_name=req.feedback_name,
            status_filter=req.status_filter,
            feedback_status_filter=req.feedback_status_filter,
        )

        return result

    def get_requests(
        self,
        request: GetRequestsRequest | dict | None = None,
        *,
        user_id: str | None = None,
        request_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        top_k: int | None = None,
    ) -> GetRequestsResponse:
        """Get requests with their associated interactions, grouped by session.

        Args:
            request (Optional[GetRequestsRequest]): The get request object (alternative to kwargs)
            user_id (Optional[str]): Filter by user ID
            request_id (Optional[str]): Filter by request ID
            start_time (Optional[datetime]): Filter by start time
            end_time (Optional[datetime]): Filter by end time
            top_k (Optional[int]): Maximum number of results to return (default: 30)

        Returns:
            GetRequestsResponse: Response containing requests grouped by session with their interactions
        """
        req = self._build_request(
            request,
            GetRequestsRequest,
            user_id=user_id,
            request_id=request_id,
            start_time=start_time,
            end_time=end_time,
            top_k=top_k,
        )
        response = self._make_request(
            "POST",
            "/api/get_requests",
            json=req.model_dump(),
        )
        return GetRequestsResponse(**response)

    def get_agent_success_evaluation_results(
        self,
        request: GetAgentSuccessEvaluationResultsRequest | dict | None = None,
        *,
        limit: int | None = None,
        agent_version: str | None = None,
    ) -> GetAgentSuccessEvaluationResultsResponse:
        """Get agent success evaluation results.

        Args:
            request (Optional[GetAgentSuccessEvaluationResultsRequest]): The get request object (alternative to kwargs)
            limit (Optional[int]): Maximum number of results to return (default: 100)
            agent_version (Optional[str]): Filter by agent version

        Returns:
            GetAgentSuccessEvaluationResultsResponse: Response containing agent success evaluation results
        """
        req = self._build_request(
            request,
            GetAgentSuccessEvaluationResultsRequest,
            limit=limit,
            agent_version=agent_version,
        )
        response = self._make_request(
            "POST",
            "/api/get_agent_success_evaluation_results",
            json=req.model_dump(),
        )
        return GetAgentSuccessEvaluationResultsResponse(**response)

    def _poll_operation_status(
        self, service_name: str, poll_interval: float = 3.0, max_wait: float = 600.0
    ) -> GetOperationStatusResponse:
        """
        Poll the operation status endpoint until the operation completes, fails, or is cancelled.

        Args:
            service_name: The service name to poll (e.g. "profile_generation", "feedback_generation")
            poll_interval: Seconds between polls
            max_wait: Maximum seconds to wait before raising TimeoutError

        Returns:
            GetOperationStatusResponse: Final operation status
        """
        start = time.monotonic()
        while True:
            try:
                response = self._make_request(
                    "GET",
                    "/api/get_operation_status",
                    params={"service_name": service_name},
                )
            except Exception as e:
                logger.warning("Failed to poll operation status: %s", e)
                elapsed = time.monotonic() - start
                if elapsed + poll_interval > max_wait:
                    raise TimeoutError(
                        f"Operation '{service_name}' did not complete within {max_wait}s"
                    ) from e
                time.sleep(poll_interval)
                continue
            status_response = GetOperationStatusResponse(**response)
            op = status_response.operation_status
            if op and op.status in (
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            ):
                return status_response
            elapsed = time.monotonic() - start
            if elapsed + poll_interval > max_wait:
                raise TimeoutError(
                    f"Operation '{service_name}' did not complete within {max_wait}s"
                )
            time.sleep(poll_interval)

    def _rerun_profile_generation_sync(
        self, request: RerunProfileGenerationRequest
    ) -> RerunProfileGenerationResponse:
        """Internal sync method to rerun profile generation.

        Submits the request, then polls operation status until completion.
        """
        response = self._make_request(
            "POST",
            "/api/rerun_profile_generation",
            json=request.model_dump(),
        )
        initial = RerunProfileGenerationResponse(**response)
        if not initial.success:
            return initial

        # Poll until the background task completes
        try:
            status_response = self._poll_operation_status("profile_generation")
            op = status_response.operation_status
            if op and op.status == OperationStatus.COMPLETED:
                return RerunProfileGenerationResponse(
                    success=True,
                    msg="Profile generation completed",
                    profiles_generated=op.processed_users,
                )
            if op and op.status == OperationStatus.FAILED:
                return RerunProfileGenerationResponse(
                    success=False,
                    msg=op.error_message or "Profile generation failed",
                )
            return RerunProfileGenerationResponse(
                success=False,
                msg="Profile generation was cancelled",
            )
        except (TimeoutError, Exception) as e:
            logger.warning("Error while polling profile generation status: %s", e)
            return initial

    async def _rerun_profile_generation_async(
        self, request: RerunProfileGenerationRequest
    ) -> RerunProfileGenerationResponse:
        """Internal async method to rerun profile generation."""
        response = await self._make_async_request(
            "POST",
            "/api/rerun_profile_generation",
            json=request.model_dump(),
        )
        return RerunProfileGenerationResponse(**response)

    def rerun_profile_generation(
        self,
        request: RerunProfileGenerationRequest | dict | None = None,
        wait_for_response: bool = False,
        *,
        user_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        source: str | None = None,
        extractor_names: list[str] | None = None,
    ) -> RerunProfileGenerationResponse | None:
        """Rerun profile generation for users.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            request (Optional[RerunProfileGenerationRequest]): The rerun request object (alternative to kwargs)
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.
            user_id (Optional[str]): Specific user ID to rerun for. If None, runs for all users.
            start_time (Optional[datetime]): Filter interactions by start time.
            end_time (Optional[datetime]): Filter interactions by end time.
            source (Optional[str]): Filter interactions by source.
            extractor_names (Optional[list[str]]): List of specific extractor names to run. If None, runs all extractors.

        Returns:
            Optional[RerunProfileGenerationResponse]: Response containing success status, message, profiles_generated count, and operation_id if wait_for_response=True, None otherwise.
        """
        req = self._build_request(
            request,
            RerunProfileGenerationRequest,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            source=source,
            extractor_names=extractor_names,
        )

        if wait_for_response:
            return self._rerun_profile_generation_sync(req)
        self._fire_and_forget(self._rerun_profile_generation_async, req)
        return None

    async def _manual_profile_generation_async(
        self, request: ManualProfileGenerationRequest
    ) -> None:
        """Internal async method for manual profile generation."""
        await self._make_async_request(
            "POST",
            "/api/manual_profile_generation",
            json=request.model_dump(),
        )

    def manual_profile_generation(
        self,
        request: ManualProfileGenerationRequest | dict | None = None,
        *,
        user_id: str | None = None,
        source: str | None = None,
        extractor_names: list[str] | None = None,
    ) -> None:
        """Manually trigger profile generation with window-sized interactions (fire-and-forget).

        Unlike rerun_profile_generation which uses ALL interactions and outputs PENDING status,
        this method uses window-sized interactions (from extraction_window_size config) and
        outputs profiles with CURRENT status.

        This is a fire-and-forget operation that runs asynchronously in the background.

        Args:
            request (Optional[ManualProfileGenerationRequest]): The request object (alternative to kwargs)
            user_id (Optional[str]): Specific user ID to generate for. If None, generates for all users.
            source (Optional[str]): Filter interactions by source.
            extractor_names (Optional[list[str]]): List of specific extractor names to run. If None, runs all extractors with allow_manual_trigger=True.

        Returns:
            None: This method always returns None (fire-and-forget).
        """
        req = self._build_request(
            request,
            ManualProfileGenerationRequest,
            user_id=user_id,
            source=source,
            extractor_names=extractor_names,
        )
        self._fire_and_forget(self._manual_profile_generation_async, req)

    def _rerun_feedback_generation_sync(
        self, request: RerunFeedbackGenerationRequest
    ) -> RerunFeedbackGenerationResponse:
        """Internal sync method to rerun feedback generation.

        Submits the request, then polls operation status until completion.
        """
        response = self._make_request(
            "POST",
            "/api/rerun_feedback_generation",
            json=request.model_dump(),
        )
        initial = RerunFeedbackGenerationResponse(**response)
        if not initial.success:
            return initial

        # Poll until the background task completes
        try:
            status_response = self._poll_operation_status("feedback_generation")
            op = status_response.operation_status
            if op and op.status == OperationStatus.COMPLETED:
                return RerunFeedbackGenerationResponse(
                    success=True,
                    msg="Feedback generation completed",
                    feedbacks_generated=op.processed_users,
                )
            if op and op.status == OperationStatus.FAILED:
                return RerunFeedbackGenerationResponse(
                    success=False,
                    msg=op.error_message or "Feedback generation failed",
                )
            return RerunFeedbackGenerationResponse(
                success=False,
                msg="Feedback generation was cancelled",
            )
        except (TimeoutError, Exception) as e:
            logger.warning("Error while polling feedback generation status: %s", e)
            return initial

    async def _rerun_feedback_generation_async(
        self, request: RerunFeedbackGenerationRequest
    ) -> RerunFeedbackGenerationResponse:
        """Internal async method to rerun feedback generation."""
        response = await self._make_async_request(
            "POST",
            "/api/rerun_feedback_generation",
            json=request.model_dump(),
        )
        return RerunFeedbackGenerationResponse(**response)

    def rerun_feedback_generation(
        self,
        request: RerunFeedbackGenerationRequest | dict | None = None,
        wait_for_response: bool = False,
        *,
        agent_version: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        feedback_name: str | None = None,
    ) -> RerunFeedbackGenerationResponse | None:
        """Rerun feedback generation for an agent version.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            request (Optional[RerunFeedbackGenerationRequest]): The rerun request object (alternative to kwargs)
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.
            agent_version (str): Required. The agent version to evaluate.
            start_time (Optional[datetime]): Filter by start time.
            end_time (Optional[datetime]): Filter by end time.
            feedback_name (Optional[str]): Specific feedback type to generate.

        Returns:
            Optional[RerunFeedbackGenerationResponse]: Response containing success status, message, feedbacks_generated count, and operation_id if wait_for_response=True, None otherwise.
        """
        req = self._build_request(
            request,
            RerunFeedbackGenerationRequest,
            agent_version=agent_version,
            start_time=start_time,
            end_time=end_time,
            feedback_name=feedback_name,
        )

        if wait_for_response:
            return self._rerun_feedback_generation_sync(req)
        self._fire_and_forget(self._rerun_feedback_generation_async, req)
        return None

    async def _manual_feedback_generation_async(
        self, request: ManualFeedbackGenerationRequest
    ) -> None:
        """Internal async method for manual feedback generation."""
        await self._make_async_request(
            "POST",
            "/api/manual_feedback_generation",
            json=request.model_dump(),
        )

    def manual_feedback_generation(
        self,
        request: ManualFeedbackGenerationRequest | dict | None = None,
        *,
        agent_version: str | None = None,
        source: str | None = None,
        feedback_name: str | None = None,
    ) -> None:
        """Manually trigger feedback generation with window-sized interactions (fire-and-forget).

        Unlike rerun_feedback_generation which uses ALL interactions and outputs PENDING status,
        this method uses window-sized interactions (from extraction_window_size config) and
        outputs feedbacks with CURRENT status.

        This is a fire-and-forget operation that runs asynchronously in the background.

        Args:
            request (Optional[ManualFeedbackGenerationRequest]): The request object (alternative to kwargs)
            agent_version (str): Required. The agent version to evaluate.
            source (Optional[str]): Filter interactions by source.
            feedback_name (Optional[str]): Specific feedback type to generate.

        Returns:
            None: This method always returns None (fire-and-forget).
        """
        req = self._build_request(
            request,
            ManualFeedbackGenerationRequest,
            agent_version=agent_version,
            source=source,
            feedback_name=feedback_name,
        )
        self._fire_and_forget(self._manual_feedback_generation_async, req)

    def _run_feedback_aggregation_sync(
        self, request: RunFeedbackAggregationRequest
    ) -> RunFeedbackAggregationResponse:
        """Internal sync method to run feedback aggregation."""
        response = self._make_request(
            "POST",
            "/api/run_feedback_aggregation",
            json=request.model_dump(),
        )
        return RunFeedbackAggregationResponse(**response)

    async def _run_feedback_aggregation_async(
        self, request: RunFeedbackAggregationRequest
    ) -> RunFeedbackAggregationResponse:
        """Internal async method to run feedback aggregation."""
        response = await self._make_async_request(
            "POST",
            "/api/run_feedback_aggregation",
            json=request.model_dump(),
        )
        return RunFeedbackAggregationResponse(**response)

    def run_feedback_aggregation(
        self,
        request: RunFeedbackAggregationRequest | dict | None = None,
        wait_for_response: bool = False,
        *,
        agent_version: str | None = None,
        feedback_name: str | None = None,
    ) -> RunFeedbackAggregationResponse | None:
        """Run feedback aggregation to cluster similar raw feedbacks.

        This method is optimized for resource efficiency:
        - In async contexts (e.g., FastAPI): Uses existing event loop (most efficient)
        - In sync contexts: Uses shared thread pool (avoids thread creation overhead)

        Args:
            request (Optional[RunFeedbackAggregationRequest]): The aggregation request object (alternative to kwargs)
            wait_for_response (bool, optional): If True, wait for response. If False, send request without waiting. Defaults to False.
            agent_version (str): Required. The agent version.
            feedback_name (str): Required. The feedback type to aggregate.

        Returns:
            Optional[RunFeedbackAggregationResponse]: Response containing success status and message if wait_for_response=True, None otherwise.
        """
        req = self._build_request(
            request,
            RunFeedbackAggregationRequest,
            agent_version=agent_version,
            feedback_name=feedback_name,
        )

        if wait_for_response:
            return self._run_feedback_aggregation_sync(req)
        self._fire_and_forget(self._run_feedback_aggregation_async, req)
        return None

    def search(
        self,
        request: UnifiedSearchRequest | dict | None = None,
        *,
        query: str | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
        agent_version: str | None = None,
        feedback_name: str | None = None,
        user_id: str | None = None,
        query_rewrite: bool | None = None,
        conversation_history: list[ConversationTurn] | None = None,
        search_mode: SearchMode | None = None,
    ) -> UnifiedSearchResponse:
        """Search across all entity types (profiles, feedbacks, raw_feedbacks, skills).

        Runs query rewriting and searches all entity types in parallel.
        Query rewriting is controlled per-request via the query_rewrite parameter.
        Skills are only searched if the skill_generation feature flag is enabled.

        Args:
            request (Optional[UnifiedSearchRequest]): The search request object (alternative to kwargs)
            query (str): Search query text
            top_k (Optional[int]): Maximum results per entity type (default: 5)
            threshold (Optional[float]): Similarity threshold for vector search (default: 0.3)
            agent_version (Optional[str]): Filter by agent version (feedbacks, raw_feedbacks, skills)
            feedback_name (Optional[str]): Filter by feedback name (feedbacks, raw_feedbacks, skills)
            user_id (Optional[str]): Filter by user ID (profiles, raw_feedbacks)
            query_rewrite (Optional[bool]): Enable LLM query rewriting (default: False)
            conversation_history (Optional[list[ConversationTurn]]): Prior conversation turns for context-aware query rewriting

        Returns:
            UnifiedSearchResponse: Combined search results from all entity types
        """
        req = self._build_request(
            request,
            UnifiedSearchRequest,
            query=query,
            top_k=top_k,
            threshold=threshold,
            agent_version=agent_version,
            feedback_name=feedback_name,
            user_id=user_id,
            query_rewrite=query_rewrite,
            conversation_history=conversation_history,
            search_mode=search_mode,
        )
        response = self._make_request("POST", "/api/search", json=req.model_dump())
        return UnifiedSearchResponse(**response)

    # =========================================================================
    # Bulk Delete Operations
    # =========================================================================

    def delete_requests_by_ids(self, request_ids: list[str]) -> BulkDeleteResponse:
        """Delete multiple requests by their IDs.

        Args:
            request_ids (list[str]): List of request IDs to delete

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        req = DeleteRequestsByIdsRequest(request_ids=request_ids)
        response = self._make_request(
            "DELETE", "/api/delete_requests_by_ids", json=req.model_dump()
        )
        return BulkDeleteResponse(**response)

    def delete_profiles_by_ids(self, profile_ids: list[str]) -> BulkDeleteResponse:
        """Delete multiple profiles by their IDs.

        Args:
            profile_ids (list[str]): List of profile IDs to delete

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        req = DeleteProfilesByIdsRequest(profile_ids=profile_ids)
        response = self._make_request(
            "DELETE", "/api/delete_profiles_by_ids", json=req.model_dump()
        )
        return BulkDeleteResponse(**response)

    def delete_feedbacks_by_ids(self, feedback_ids: list[int]) -> BulkDeleteResponse:
        """Delete multiple feedbacks by their IDs.

        Args:
            feedback_ids (list[int]): List of feedback IDs to delete

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        req = DeleteFeedbacksByIdsRequest(feedback_ids=feedback_ids)
        response = self._make_request(
            "DELETE", "/api/delete_feedbacks_by_ids", json=req.model_dump()
        )
        return BulkDeleteResponse(**response)

    def delete_raw_feedbacks_by_ids(
        self, raw_feedback_ids: list[int]
    ) -> BulkDeleteResponse:
        """Delete multiple raw feedbacks by their IDs.

        Args:
            raw_feedback_ids (list[int]): List of raw feedback IDs to delete

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        req = DeleteRawFeedbacksByIdsRequest(raw_feedback_ids=raw_feedback_ids)
        response = self._make_request(
            "DELETE", "/api/delete_raw_feedbacks_by_ids", json=req.model_dump()
        )
        return BulkDeleteResponse(**response)

    def delete_all_interactions(self) -> BulkDeleteResponse:
        """Delete all requests and their associated interactions.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        response = self._make_request("DELETE", "/api/delete_all_interactions")
        return BulkDeleteResponse(**response)

    def delete_all_profiles(self) -> BulkDeleteResponse:
        """Delete all profiles.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        response = self._make_request("DELETE", "/api/delete_all_profiles")
        return BulkDeleteResponse(**response)

    def delete_all_feedbacks(self) -> BulkDeleteResponse:
        """Delete all feedbacks (both raw and aggregated).

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        response = self._make_request("DELETE", "/api/delete_all_feedbacks")
        return BulkDeleteResponse(**response)
