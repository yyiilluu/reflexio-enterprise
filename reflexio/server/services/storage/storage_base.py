from abc import ABC, abstractmethod
import os
from typing import Optional
import reflexio.data as data

from reflexio_commons.api_schema.service_schemas import (
    RawFeedback,
    Feedback,
    Skill,
    SkillStatus,
    UserProfile,
    Interaction,
    Request,
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
    ProfileChangeLog,
    FeedbackAggregationChangeLog,
    AgentSuccessEvaluationResult,
    FeedbackStatus,
    Status,
)
from reflexio_commons.api_schema.retriever_schema import (
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel


class BaseStorage(ABC):
    """
    Base class for storage
    """

    def __init__(self, org_id: str, base_dir: Optional[str] = None):
        self.org_id = org_id
        if base_dir is None:
            base_dir = os.path.dirname(data.__file__)
        self.base_dir = base_dir

    # ==============================
    # CRUD methods
    # ==============================

    # Migrate
    def migrate(self) -> bool:
        """
        Handle migration to transform the storage to the latest format.

        Returns
            A boolean indicating whether migration is successful.
        """
        return True

    def check_migration_needed(self) -> bool:
        """
        Check if storage needs migration. Returns False by default (no migration needed).

        Returns:
            bool: True if migration is needed, False otherwise
        """
        return False

    # read methods
    @abstractmethod
    def get_all_profiles(
        self,
        limit: int = 100,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        raise NotImplementedError

    @abstractmethod
    def get_all_interactions(self, limit: int = 100) -> list[Interaction]:
        raise NotImplementedError

    @abstractmethod
    def get_user_profile(
        self,
        user_id: str,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        raise NotImplementedError

    @abstractmethod
    def get_user_interaction(self, user_id: str) -> list[Interaction]:
        raise NotImplementedError

    # create or update methods
    @abstractmethod
    def add_user_profile(self, user_id: str, user_profiles: list[UserProfile]):
        """
        Add the user profile for a given user id
        """
        raise NotImplementedError

    @abstractmethod
    def add_user_interaction(self, user_id: str, interaction: Interaction):
        raise NotImplementedError

    @abstractmethod
    def add_user_interactions_bulk(
        self, user_id: str, interactions: list[Interaction]
    ) -> None:
        """
        Add multiple user interactions with batched embedding generation.

        Args:
            user_id: The user ID
            interactions: List of interactions to add
        """
        raise NotImplementedError

    # delete methods
    @abstractmethod
    def delete_user_interaction(self, request: DeleteUserInteractionRequest):
        raise NotImplementedError

    @abstractmethod
    def delete_user_profile(self, request: DeleteUserProfileRequest):
        raise NotImplementedError

    @abstractmethod
    def update_user_profile_by_id(
        self, user_id: str, profile_id: str, new_profile: UserProfile
    ):
        raise NotImplementedError

    @abstractmethod
    def delete_all_interactions_for_user(self, user_id: str):
        raise NotImplementedError

    @abstractmethod
    def delete_all_profiles_for_user(self, user_id: str):
        raise NotImplementedError

    @abstractmethod
    def delete_all_profiles(self):
        """Delete all profiles across all users."""
        raise NotImplementedError

    @abstractmethod
    def delete_all_interactions(self):
        """Delete all interactions across all users."""
        raise NotImplementedError

    @abstractmethod
    def count_all_interactions(self) -> int:
        """
        Count total interactions across all users.

        Returns:
            int: Total number of interactions
        """
        raise NotImplementedError

    @abstractmethod
    def delete_oldest_interactions(self, count: int) -> int:
        """
        Delete the oldest N interactions based on created_at timestamp.

        Args:
            count (int): Number of oldest interactions to delete

        Returns:
            int: Number of interactions actually deleted
        """
        raise NotImplementedError

    @abstractmethod
    def update_all_profiles_status(
        self,
        old_status: Optional[Status],
        new_status: Optional[Status],
        user_ids: Optional[list[str]] = None,
    ) -> int:
        """
        Update all profiles with old_status to new_status atomically.

        Args:
            old_status: The current status to match (None for CURRENT)
            new_status: The new status to set (None for CURRENT)
            user_ids: Optional list of user_ids to filter updates. If None, updates all users.

        Returns:
            int: Number of profiles updated
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_profiles_by_status(self, status: Status) -> int:
        """
        Delete all profiles with the given status atomically.

        Args:
            status: The status of profiles to delete

        Returns:
            int: Number of profiles deleted
        """
        raise NotImplementedError

    @abstractmethod
    def get_user_ids_with_status(self, status: Optional[Status]) -> list[str]:
        """
        Get list of unique user_ids that have profiles with the given status.

        Args:
            status: The status to filter by (None for CURRENT)

        Returns:
            list[str]: List of unique user_ids
        """
        raise NotImplementedError

    # ==============================
    # Request methods
    # ==============================

    @abstractmethod
    def add_request(self, request: Request):
        """
        Add a request to storage.

        Args:
            request: Request object to store
        """
        raise NotImplementedError

    @abstractmethod
    def get_request(self, request_id: str) -> Optional[Request]:
        """
        Get a request by its ID.

        Args:
            request_id: The request ID to retrieve

        Returns:
            Request object if found, None otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def delete_request(self, request_id: str):
        """
        Delete a request by its ID.

        Args:
            request_id: The request ID to delete
        """
        raise NotImplementedError

    @abstractmethod
    def delete_session(self, session_id: str) -> int:
        """
        Delete all requests and interactions in a session.

        Args:
            session_id: The session ID to delete

        Returns:
            int: Number of requests deleted
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_requests(self):
        """Delete all requests and their associated interactions."""
        raise NotImplementedError

    @abstractmethod
    def get_sessions(
        self,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        top_k: Optional[int] = 30,
        offset: int = 0,
    ) -> dict[str, list[RequestInteractionDataModel]]:
        """
        Get requests with their associated interactions, grouped by session_id.

        Args:
            user_id (str, optional): User ID to filter requests.
            request_id (str, optional): Specific request ID to retrieve
            session_id (str, optional): Specific session ID to retrieve
            start_time (int, optional): Start timestamp for filtering
            end_time (int, optional): End timestamp for filtering
            top_k (int, optional): Maximum number of requests to return
            offset (int): Number of requests to skip for pagination. Defaults to 0.

        Returns:
            dict[str, list[RequestInteractionDataModel]]: Dictionary mapping session_id to list of RequestInteractionDataModel objects
        """
        raise NotImplementedError

    @abstractmethod
    def get_rerun_user_ids(
        self,
        user_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        source: Optional[str] = None,
        agent_version: Optional[str] = None,
    ) -> list[str]:
        """
        Get distinct user IDs that have matching requests for rerun workflows.

        Args:
            user_id (str, optional): Restrict to a specific user ID.
            start_time (int, optional): Start timestamp for request filtering.
            end_time (int, optional): End timestamp for request filtering.
            source (str, optional): Restrict to requests from a source.
            agent_version (str, optional): Restrict to requests with an agent version.

        Returns:
            list[str]: Distinct user IDs matching the filters.
        """
        raise NotImplementedError

    @abstractmethod
    def get_requests_by_session(self, user_id: str, session_id: str) -> list[Request]:
        """
        Get all requests for a specific session.

        Args:
            user_id (str): User ID to filter requests
            session_id (str): Session ID to filter by

        Returns:
            list[Request]: List of Request objects in the session
        """
        raise NotImplementedError

    # ==============================
    # Profile Change Log methods
    # ==============================

    @abstractmethod
    def add_profile_change_log(self, profile_change_log: ProfileChangeLog):
        """Add a profile change log entry"""
        raise NotImplementedError

    @abstractmethod
    def get_profile_change_logs(self, limit: int = 100) -> list[ProfileChangeLog]:
        """Get profile change logs for an organization"""
        raise NotImplementedError

    @abstractmethod
    def delete_profile_change_log_for_user(self, user_id: str):
        """Delete all profile change logs for a user"""
        raise NotImplementedError

    @abstractmethod
    def delete_all_profile_change_logs(self):
        """Delete all profile change logs"""
        raise NotImplementedError

    # ==============================
    # Feedback Aggregation Change Log methods
    # ==============================

    @abstractmethod
    def add_feedback_aggregation_change_log(
        self, change_log: FeedbackAggregationChangeLog
    ):
        """Add a feedback aggregation change log entry."""
        raise NotImplementedError

    @abstractmethod
    def get_feedback_aggregation_change_logs(
        self,
        feedback_name: str,
        agent_version: str,
        limit: int = 100,
    ) -> list[FeedbackAggregationChangeLog]:
        """Get feedback aggregation change logs filtered by feedback_name and agent_version."""
        raise NotImplementedError

    @abstractmethod
    def delete_all_feedback_aggregation_change_logs(self):
        """Delete all feedback aggregation change logs."""
        raise NotImplementedError

    # ==============================
    # Statistics methods
    # ==============================

    @abstractmethod
    def get_profile_statistics(self) -> dict:
        """Get profile count statistics by status.

        Returns:
            dict with keys: current_count, pending_count, archived_count, expiring_soon_count
        """
        raise NotImplementedError

    # ==============================
    # Search methods
    # ==============================

    @abstractmethod
    def search_interaction(self, search_interaction_request: SearchInteractionRequest):
        raise NotImplementedError

    @abstractmethod
    def search_user_profile(
        self,
        search_user_profile_request: SearchUserProfileRequest,
        status_filter: Optional[list[Optional[Status]]] = None,
        query_embedding: Optional[list[float]] = None,
    ):
        raise NotImplementedError

    # ==============================
    # Feedback methods
    # ==============================

    @abstractmethod
    def save_raw_feedbacks(self, raw_feedbacks: list[RawFeedback]):
        raise NotImplementedError

    @abstractmethod
    def get_raw_feedbacks(
        self,
        limit: int = 100,
        user_id: Optional[str] = None,
        feedback_name: Optional[str] = None,
        agent_version: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[RawFeedback]:
        """
        Get raw feedbacks from storage.

        Args:
            limit (int): Maximum number of feedbacks to return
            user_id (str, optional): The user ID to filter by. If None, returns feedbacks for all users.
            feedback_name (str, optional): The feedback name to filter by. If None, returns all raw feedbacks.
            agent_version (str, optional): The agent version to filter by. If None, returns all agent versions.
            status_filter (list[Optional[Status]], optional): List of status values to filter by.
                Can include None (current), Status.PENDING (from rerun), Status.ARCHIVED (old).
                If None, returns feedbacks with all statuses.
            start_time (int, optional): Unix timestamp. Only return feedbacks created at or after this time.
            end_time (int, optional): Unix timestamp. Only return feedbacks created at or before this time.

        Returns:
            list[RawFeedback]: List of raw feedback objects
        """
        raise NotImplementedError

    @abstractmethod
    def count_raw_feedbacks(
        self,
        user_id: Optional[str] = None,
        feedback_name: Optional[str] = None,
        min_raw_feedback_id: Optional[int] = None,
        agent_version: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> int:
        """
        Count raw feedbacks in storage efficiently.

        Args:
            user_id (str, optional): The user ID to filter by. If None, counts feedbacks for all users.
            feedback_name (str, optional): The feedback name to filter by. If None, counts all raw feedbacks.
            min_raw_feedback_id (int, optional): Only count feedbacks with raw_feedback_id greater than this value.
            agent_version (str, optional): The agent version to filter by. If None, counts all agent versions.
            status_filter (list[Optional[Status]], optional): List of status values to filter by.
                Can include None (current), Status.PENDING (from rerun), Status.ARCHIVED (old).
                If None, returns feedbacks with all statuses.

        Returns:
            int: Count of raw feedbacks matching the filters
        """
        raise NotImplementedError

    @abstractmethod
    def save_feedbacks(self, feedbacks: list[Feedback]) -> list[Feedback]:
        """
        Save regular feedbacks with embeddings.

        Args:
            feedbacks (list[Feedback]): List of feedback objects to save

        Returns:
            list[Feedback]: Saved feedbacks with feedback_id populated from storage
        """
        raise NotImplementedError

    @abstractmethod
    def get_feedbacks(
        self,
        limit: int = 100,
        feedback_name: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        feedback_status_filter: Optional[list[FeedbackStatus]] = None,
    ) -> list[Feedback]:
        """
        Get regular feedbacks from storage.

        Args:
            limit (int): Maximum number of feedbacks to return
            feedback_name (str, optional): The feedback name to filter by. If None, returns all feedbacks.
            status_filter (list[Optional[Status]], optional): List of Status values to filter by. None in the list means CURRENT status.
            feedback_status_filter (Optional[list[FeedbackStatus]]): List of FeedbackStatus values to filter by.
                If None, returns all feedback statuses.

        Returns:
            list[Feedback]: List of feedback objects
        """
        raise NotImplementedError

    @abstractmethod
    def search_raw_feedbacks(
        self,
        query: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_version: Optional[str] = None,
        feedback_name: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        match_threshold: float = 0.5,
        match_count: int = 10,
        query_embedding: Optional[list[float]] = None,
    ) -> list[RawFeedback]:
        """
        Search raw feedbacks with advanced filtering including semantic search.

        Args:
            query (str, optional): Text query for semantic/text search
            user_id (str, optional): Filter by user (resolved via request_id -> requests table linkage)
            agent_version (str, optional): Filter by agent version
            feedback_name (str, optional): Filter by feedback name
            start_time (int, optional): Start timestamp (Unix) for created_at filter
            end_time (int, optional): End timestamp (Unix) for created_at filter
            status_filter (list[Optional[Status]], optional): List of status values to filter by
            match_threshold (float): Minimum similarity threshold (0.0 to 1.0)
            match_count (int): Maximum number of results to return
            query_embedding (list[float], optional): Pre-computed query embedding. When provided, skips internal embedding generation.

        Returns:
            list[RawFeedback]: List of matching raw feedback objects
        """
        raise NotImplementedError

    @abstractmethod
    def search_feedbacks(
        self,
        query: Optional[str] = None,
        agent_version: Optional[str] = None,
        feedback_name: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        feedback_status_filter: Optional[FeedbackStatus] = None,
        match_threshold: float = 0.5,
        match_count: int = 10,
        query_embedding: Optional[list[float]] = None,
    ) -> list[Feedback]:
        """
        Search aggregated feedbacks with advanced filtering including semantic search.

        Args:
            query (str, optional): Text query for semantic/text search
            agent_version (str, optional): Filter by agent version
            feedback_name (str, optional): Filter by feedback name
            start_time (int, optional): Start timestamp (Unix) for created_at filter
            end_time (int, optional): End timestamp (Unix) for created_at filter
            status_filter (list[Optional[Status]], optional): List of Status values to filter by (CURRENT/PENDING/ARCHIVED)
            feedback_status_filter (FeedbackStatus, optional): Filter by FeedbackStatus (PENDING/APPROVED/REJECTED)
            match_threshold (float): Minimum similarity threshold (0.0 to 1.0)
            match_count (int): Maximum number of results to return
            query_embedding (list[float], optional): Pre-computed query embedding. When provided, skips internal embedding generation.

        Returns:
            list[Feedback]: List of matching feedback objects
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_raw_feedbacks(self):
        """Delete all raw feedbacks from storage."""
        raise NotImplementedError

    @abstractmethod
    def delete_all_raw_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all raw feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_feedbacks(self):
        """Delete all regular feedbacks from storage."""
        raise NotImplementedError

    @abstractmethod
    def delete_feedback(self, feedback_id: int):
        """Delete a feedback by ID.

        Args:
            feedback_id (int): The ID of the feedback to delete
        """
        raise NotImplementedError

    @abstractmethod
    def delete_raw_feedback(self, raw_feedback_id: int):
        """Delete a raw feedback by ID.

        Args:
            raw_feedback_id (int): The ID of the raw feedback to delete
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all regular feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        raise NotImplementedError

    @abstractmethod
    def update_feedback_status(self, feedback_id: int, feedback_status: FeedbackStatus):
        """
        Update the status of a specific feedback.

        Args:
            feedback_id (int): The ID of the feedback to update
            feedback_status (FeedbackStatus): The new status to set

        Raises:
            ValueError: If feedback with the given ID is not found
        """
        raise NotImplementedError

    @abstractmethod
    def archive_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Archive non-APPROVED feedbacks by setting their status field to 'archived'.
        APPROVED feedbacks are left untouched to preserve user-approved feedback.

        Args:
            feedback_name (str): The feedback name to archive
            agent_version (str, optional): The agent version to filter by. If None, archives all agent versions.
        """
        raise NotImplementedError

    @abstractmethod
    def archive_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Archive non-APPROVED feedbacks by IDs, setting their status field to 'archived'.
        APPROVED feedbacks are left untouched. No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to archive
        """
        raise NotImplementedError

    @abstractmethod
    def restore_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Restore archived feedbacks by setting their status field to null.

        Args:
            feedback_name (str): The feedback name to restore
            agent_version (str, optional): The agent version to filter by. If None, restores all agent versions.
        """
        raise NotImplementedError

    @abstractmethod
    def restore_archived_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Restore archived feedbacks by IDs, setting their status field to null.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to restore
        """
        raise NotImplementedError

    @abstractmethod
    def delete_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Permanently delete feedbacks that have status='archived'.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Permanently delete feedbacks by their IDs.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to delete
        """
        raise NotImplementedError

    @abstractmethod
    def update_all_raw_feedbacks_status(
        self,
        old_status: Optional[Status],
        new_status: Optional[Status],
        agent_version: Optional[str] = None,
        feedback_name: Optional[str] = None,
    ) -> int:
        """
        Update all raw feedbacks with old_status to new_status atomically.

        Args:
            old_status: The current status to match (None for CURRENT)
            new_status: The new status to set (None for CURRENT)
            agent_version: Optional filter by agent version
            feedback_name: Optional filter by feedback name

        Returns:
            int: Number of raw feedbacks updated
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_raw_feedbacks_by_status(
        self,
        status: Status,
        agent_version: Optional[str] = None,
        feedback_name: Optional[str] = None,
    ) -> int:
        """
        Delete all raw feedbacks with the given status atomically.

        Args:
            status: The status of raw feedbacks to delete
            agent_version: Optional filter by agent version
            feedback_name: Optional filter by feedback name

        Returns:
            int: Number of raw feedbacks deleted
        """
        raise NotImplementedError

    @abstractmethod
    def has_raw_feedbacks_with_status(
        self,
        status: Optional[Status],
        agent_version: Optional[str] = None,
        feedback_name: Optional[str] = None,
    ) -> bool:
        """
        Check if any raw feedbacks exist with given status and filters.

        Args:
            status: The status to check for (None for CURRENT)
            agent_version: Optional filter by agent version
            feedback_name: Optional filter by feedback name

        Returns:
            bool: True if any matching raw feedbacks exist
        """
        raise NotImplementedError

    # ==============================
    # Agent Success Evaluation methods
    # ==============================

    @abstractmethod
    def save_agent_success_evaluation_results(
        self, results: list[AgentSuccessEvaluationResult]
    ):
        """
        Save agent success evaluation results to storage.

        Args:
            results (list[AgentSuccessEvaluationResult]): List of agent success evaluation results to save
        """
        raise NotImplementedError

    @abstractmethod
    def get_agent_success_evaluation_results(
        self, limit: int = 100, agent_version: Optional[str] = None
    ) -> list[AgentSuccessEvaluationResult]:
        """
        Get agent success evaluation results from storage.

        Args:
            limit (int): Maximum number of results to return
            agent_version (str, optional): The agent version to filter by. If None, returns all results.

        Returns:
            list[AgentSuccessEvaluationResult]: List of agent success evaluation result objects
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_agent_success_evaluation_results(self):
        """Delete all agent success evaluation results from storage."""
        raise NotImplementedError

    # ==============================
    # Dashboard methods
    # ==============================

    @abstractmethod
    def get_dashboard_stats(self, days_back: int = 30) -> dict:
        """
        Get comprehensive dashboard statistics including counts and time-series data.

        Args:
            days_back (int): Number of days to include in time series data

        Returns:
            dict: Dictionary containing:
                - current_period: Stats for the current period (days_back)
                - previous_period: Stats for the previous period (for trend calculation)
                - interactions_time_series: List of time series data points (raw, ungrouped)
                - profiles_time_series: List of time series data points (raw, ungrouped)
                - feedbacks_time_series: List of time series data points (raw, ungrouped)
                - evaluations_time_series: List of time series data points (raw, ungrouped)
        """
        raise NotImplementedError

    # ==============================
    # Operation State methods
    # ==============================

    @abstractmethod
    def create_operation_state(self, service_name: str, operation_state: dict):
        """
        Create operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        raise NotImplementedError

    @abstractmethod
    def upsert_operation_state(self, service_name: str, operation_state: dict):
        """
        Create or update operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        raise NotImplementedError

    @abstractmethod
    def get_operation_state(self, service_name: str) -> Optional[dict]:
        """
        Get operation state for a specific service.

        Args:
            service_name (str): Name of the service

        Returns:
            Optional[dict]: Operation state data or None if not found
        """
        raise NotImplementedError

    @abstractmethod
    def get_operation_state_with_new_request_interaction(
        self,
        service_name: str,
        user_id: Optional[str],
        sources: Optional[list[str]] = None,
    ) -> tuple[dict, list[RequestInteractionDataModel]]:
        """
        Get the last operation state and retrieve new interactions since last processing,
        grouped by request.

        Args:
            service_name (str): Name of the service
            user_id (Optional[str]): User identifier to filter interactions.
                If None, returns interactions across all users (for non-user-scoped extractors).
            sources (Optional[list[str]]): Optional list of sources to filter interactions by

        Returns:
            tuple[dict, list[RequestInteractionDataModel]]: Operation state payload and list of
                RequestInteractionDataModel objects containing new interactions grouped by request
        """
        raise NotImplementedError

    @abstractmethod
    def get_last_k_interactions_grouped(
        self,
        user_id: Optional[str],
        k: int,
        sources: Optional[list[str]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        agent_version: Optional[str] = None,
    ) -> tuple[list[RequestInteractionDataModel], list[Interaction]]:
        """
        Get the last K interactions ordered by time (most recent first), grouped by request.

        This method retrieves the most recent K interactions for a user and groups them
        by their associated requests. Used for sliding window extraction where we want
        to process the last K interactions regardless of whether they were previously processed.

        Args:
            user_id (Optional[str]): User identifier to filter interactions.
                If None, returns interactions across all users (for non-user-scoped extractors).
            k (int): Maximum number of interactions to retrieve
            sources (Optional[list[str]]): Optional list of sources to filter interactions by.
                If provided, only interactions from requests with source in this list are returned.
            start_time (Optional[int]): Unix timestamp. Only return interactions created at or after this time.
            end_time (Optional[int]): Unix timestamp. Only return interactions created at or before this time.
            agent_version (Optional[str]): Filter by agent_version on the request.
                If provided, only interactions from requests with this agent_version are returned.

        Returns:
            tuple[list[RequestInteractionDataModel], list[Interaction]]:
                - List of RequestInteractionDataModel objects (grouped by request/session)
                - Flat list of all interactions sorted by created_at DESC
        """
        raise NotImplementedError

    @abstractmethod
    def update_operation_state(self, service_name: str, operation_state: dict):
        """
        Update operation state for a specific service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        raise NotImplementedError

    @abstractmethod
    def get_all_operation_states(self) -> list[dict]:
        """
        Get all operation states.

        Returns:
            list[dict]: List of all operation state records
        """
        raise NotImplementedError

    @abstractmethod
    def delete_operation_state(self, service_name: str):
        """
        Delete operation state for a specific service.

        Args:
            service_name (str): Name of the service
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all_operation_states(self):
        """Delete all operation states."""
        raise NotImplementedError

    # ==============================
    # Skill methods
    # ==============================

    @abstractmethod
    def save_skills(self, skills: list[Skill]):
        """
        Save skills with embeddings.

        Args:
            skills (list[Skill]): List of skill objects to save
        """
        raise NotImplementedError

    @abstractmethod
    def get_skills(
        self,
        limit: int = 100,
        feedback_name: Optional[str] = None,
        agent_version: Optional[str] = None,
        skill_status: Optional[SkillStatus] = None,
    ) -> list[Skill]:
        """
        Get skills from storage.

        Args:
            limit (int): Maximum number of skills to return
            feedback_name (str, optional): Filter by feedback name
            agent_version (str, optional): Filter by agent version
            skill_status (SkillStatus, optional): Filter by skill status

        Returns:
            list[Skill]: List of skill objects
        """
        raise NotImplementedError

    @abstractmethod
    def search_skills(
        self,
        query: Optional[str] = None,
        feedback_name: Optional[str] = None,
        agent_version: Optional[str] = None,
        skill_status: Optional[SkillStatus] = None,
        match_threshold: float = 0.5,
        match_count: int = 10,
        query_embedding: Optional[list[float]] = None,
    ) -> list[Skill]:
        """
        Search skills with hybrid search (vector + FTS).

        Args:
            query (str, optional): Text query for semantic/text search
            feedback_name (str, optional): Filter by feedback name
            agent_version (str, optional): Filter by agent version
            skill_status (SkillStatus, optional): Filter by skill status
            match_threshold (float): Minimum similarity threshold
            match_count (int): Maximum number of results to return
            query_embedding (list[float], optional): Pre-computed query embedding. When provided, skips internal embedding generation.

        Returns:
            list[Skill]: List of matching skill objects
        """
        raise NotImplementedError

    @abstractmethod
    def update_skill_status(self, skill_id: int, skill_status: SkillStatus):
        """
        Update the status of a specific skill.

        Args:
            skill_id (int): The ID of the skill to update
            skill_status (SkillStatus): The new status to set
        """
        raise NotImplementedError

    @abstractmethod
    def delete_skill(self, skill_id: int):
        """
        Delete a skill by ID.

        Args:
            skill_id (int): The ID of the skill to delete
        """
        raise NotImplementedError

    @abstractmethod
    def get_interactions_by_request_ids(
        self, request_ids: list[str]
    ) -> list[Interaction]:
        """
        Fetch interactions by their request IDs.

        Args:
            request_ids (list[str]): List of request IDs to fetch interactions for

        Returns:
            list[Interaction]: List of matching interaction objects
        """
        raise NotImplementedError

    @abstractmethod
    def try_acquire_in_progress_lock(
        self, state_key: str, request_id: str, stale_lock_seconds: int = 300
    ) -> dict:
        """
        Atomically try to acquire an in-progress lock.

        This method should use atomic operations to either:
        1. Acquire the lock if no active lock exists (or lock is stale)
        2. Update pending_request_id if an active lock is held by another request

        Args:
            state_key (str): The operation state key (e.g., "profile_generation_in_progress::3::user_id")
            request_id (str): The current request's unique identifier
            stale_lock_seconds (int): Seconds after which a lock is considered stale (default 300)

        Returns:
            dict: Result with keys:
                - 'acquired' (bool): True if lock was acquired, False if blocked
                - 'state' (dict): The current operation state after the operation
        """
        raise NotImplementedError
