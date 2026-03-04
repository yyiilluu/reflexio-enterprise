"""
Storage class that uses Supabase as vector db for storing data
"""

import os
import logging
import functools
import reflexio.data as data
from typing import Optional
from datetime import datetime, timezone
from supabase import create_client, Client
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
from reflexio.server.services.storage.supabase_storage_utils import (
    raw_feedback_to_data,
    response_to_interaction,
    user_profile_to_data,
    interaction_to_data,
    request_to_data,
    response_to_request,
    response_list_to_user_profiles,
    response_list_to_interactions,
    profile_change_log_to_data,
    response_list_to_profile_change_logs,
    feedback_to_data,
    skill_to_data,
    response_to_skill,
    agent_success_evaluation_result_to_data,
    execute_migration,
)
from reflexio_commons.api_schema.service_schemas import (
    DeleteUserProfileRequest,
    DeleteUserInteractionRequest,
    Feedback,
    Skill,
    SkillStatus,
    UserProfile,
    Interaction,
    Request,
    ProfileChangeLog,
    RawFeedback,
    BlockingIssue,
    AgentSuccessEvaluationResult,
    FeedbackStatus,
    Status,
    UserActionType,
    RegularVsShadow,
    ToolUsed,
)
from reflexio_commons.api_schema.retriever_schema import (
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio.server.services.storage.error import StorageError
from reflexio_commons.config_schema import (
    StorageConfigSupabase,
    APIKeyConfig,
    LLMConfig,
    SearchMode,
    EMBEDDING_DIMENSIONS,
)

from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)


def _parse_blocking_issue(data: dict) -> Optional[BlockingIssue]:
    """Safely parse a blocking_issue JSONB value from the database.

    Args:
        data: A database row dict that may contain a 'blocking_issue' key

    Returns:
        BlockingIssue if valid data present, None otherwise
    """
    raw = data.get("blocking_issue")
    if not raw:
        return None
    try:
        return BlockingIssue(**raw)
    except Exception:
        logger.warning("Failed to parse blocking_issue from DB row: %s", raw)
        return None


class SupabaseStorage(BaseStorage):
    """
    Storage class that uses Supabase as vector db for storing data
    """

    @staticmethod
    def handle_exceptions(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                import traceback

                stack_trace = traceback.format_exc()
                logger.error(
                    "Error in %s: %s\nStack trace:\n%s",
                    func.__name__,
                    str(e),
                    stack_trace,
                )
                error_msg = f"{str(e)}\nStack trace:\n{stack_trace}"
                raise StorageError(message=error_msg) from e

        return wrapper

    def __init__(
        self,
        org_id: str,
        config: StorageConfigSupabase,
        api_key_config: Optional[APIKeyConfig] = None,
        llm_config: Optional[LLMConfig] = None,
    ):
        super().__init__(org_id)
        self.api_key_config = api_key_config

        self.supabase_url = config.url
        self.supabase_key = config.key
        self.supabase_db_url = config.db_url

        # Initialize Supabase client
        if not self.supabase_url or not self.supabase_key:
            err_msg = (
                f"Supabase Storage for org {org_id} missing required configuration"
            )
            logger.error(err_msg)
            raise StorageError(err_msg)

        logger.info(f"Supabase Storage for org {org_id} uses URL {self.supabase_url}")
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
        except Exception as e:
            err_msg = f"Supabase Storage failed to connect: {str(e)}"
            logger.error(err_msg, exc_info=True)
            raise StorageError(err_msg)

        # Get site var for supabase settings (including search_mode)
        self.supabase_settings = SiteVarManager().get_site_var("supabase_settings")
        if self.supabase_settings:
            search_mode_str = self.supabase_settings.get("search_mode", "hybrid")
            self.search_mode = SearchMode(search_mode_str)
        else:
            self.search_mode = SearchMode.HYBRID

        # Get site var as fallback for model settings
        self.model_setting = SiteVarManager().get_site_var("llm_model_setting")
        assert isinstance(self.model_setting, dict), "llm_model_setting must be a dict"

        # Use LLM config override if present, otherwise fallback to site var
        self.embedding_model_name = (
            llm_config.embedding_model_name
            if llm_config and llm_config.embedding_model_name
            else self.model_setting.get(
                "embedding_model_name", "text-embedding-3-small"
            )
        )
        self.embedding_dimensions = EMBEDDING_DIMENSIONS

        try:
            # Use LiteLLMClient with embedding model configuration
            litellm_config = LiteLLMConfig(
                model=self.embedding_model_name,
                temperature=0.0,  # Embeddings don't use temperature
                api_key_config=self.api_key_config,
            )
            self.llm_client = LiteLLMClient(litellm_config)
        except Exception as e:
            err_msg = f"Supabase Storage failed to create LLM client: {str(e)}"
            logger.error(err_msg, exc_info=True)
            raise StorageError(err_msg)

    def _current_timestamp(self) -> str:
        """Return a timezone-aware ISO timestamp for updated_at."""
        return datetime.now(timezone.utc).isoformat()

    # ==============================
    # CRUD methods
    # ==============================

    def check_migration_needed(self) -> bool:
        if not self.supabase_db_url:
            return False
        from reflexio.server.services.storage.supabase_storage_utils import (
            check_migration_needed as _check_migration_needed,
        )

        return _check_migration_needed(self.supabase_db_url)

    @handle_exceptions
    def migrate(self) -> bool:
        if not self.supabase_db_url:
            logger.error("Supabase Storage failed to migrate: no valid Supabase DB URL")
            return False
        supabase_migrate_folder = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(data.__file__))),
            "supabase",
            "migrations",
        )
        logger.info(
            f"Supabase Storage for org {self.org_id} try to migrate from {supabase_migrate_folder}"
        )
        if not os.path.isdir(supabase_migrate_folder):
            logger.error(
                f"Supabase Storage failed to migrate: migration folder {supabase_migrate_folder} does not exist!"
            )
            return False
        success, message = execute_migration(db_url=self.supabase_db_url)
        if not success:
            logger.error(
                f"Supabase Storage migration failed for org {self.org_id}: {message}"
            )
            raise StorageError(message=f"Migration failed: {message}")
        logger.info(
            f"Supabase Storage migration succeeded for org {self.org_id}: {message}"
        )
        return True

    @handle_exceptions
    def get_all_profiles(
        self,
        limit: int = 100,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        query = self.client.table("profiles").select("*")

        # Convert Status enum values to strings for database query
        # Handle None values and Status.CURRENT (which has value None)
        status_strings = []
        has_none = False
        for status in status_filter:
            if status is None or (hasattr(status, "value") and status.value is None):
                has_none = True
            elif isinstance(status, Status):
                status_strings.append(status.value)
            elif isinstance(status, str):
                status_strings.append(status)

        # Build status filter: handle None and string values
        if has_none and len(status_strings) > 0:
            # Mix of None and other statuses: (status IS NULL OR status IN (...))
            query = query.or_(f"status.is.null,status.in.({','.join(status_strings)})")
        elif has_none:
            # Only None: status IS NULL
            query = query.is_("status", "null")
        else:
            # Only non-None statuses: status IN (...)
            query = query.in_("status", status_strings)

        response = (
            query.order("last_modified_timestamp", desc=True).limit(limit).execute()
        )
        return response_list_to_user_profiles(response.data)

    @handle_exceptions
    def get_all_interactions(self, limit: int = 100) -> list[Interaction]:
        response = (
            self.client.table("interactions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response_list_to_interactions(response.data)

    @handle_exceptions
    def get_user_profile(
        self,
        user_id: str,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        query = (
            self.client.table("profiles")
            .select("*")
            .eq("user_id", user_id)
            .gte("expiration_timestamp", current_timestamp)
        )

        # Convert Status enum values to strings for database query
        status_strings = []
        has_none = False
        for status in status_filter:
            if status is None or (hasattr(status, "value") and status.value is None):
                has_none = True
            elif isinstance(status, Status):
                status_strings.append(status.value)
            elif isinstance(status, str):
                status_strings.append(status)

        # Build status filter: handle None and string values
        if has_none and len(status_strings) > 0:
            # Mix of None and other statuses: (status IS NULL OR status IN (...))
            query = query.or_(f"status.is.null,status.in.({','.join(status_strings)})")
        elif has_none:
            # Only None: status IS NULL
            query = query.is_("status", "null")
        else:
            # Only non-None statuses: status IN (...)
            query = query.in_("status", status_strings)

        response = query.execute()
        return response_list_to_user_profiles(response.data)

    @handle_exceptions
    def get_user_interaction(self, user_id: str) -> list[Interaction]:
        response = (
            self.client.table("interactions")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return response_list_to_interactions(response.data)

    @handle_exceptions
    def add_user_profile(self, user_id: str, user_profiles: list[UserProfile]):
        for profile in user_profiles:
            embedding = self._get_embedding(
                "\n".join([profile.profile_content, str(profile.custom_features)])
            )
            profile.embedding = embedding
            self.client.table("profiles").upsert(
                user_profile_to_data(profile)
            ).execute()

    @handle_exceptions
    def add_user_interaction(self, user_id: str, interaction: Interaction):
        embedding = self._get_embedding(
            "\n".join([interaction.content, interaction.user_action_description])
        )
        interaction.embedding = embedding
        self.client.table("interactions").upsert(
            interaction_to_data(interaction)
        ).execute()

    @handle_exceptions
    def add_user_interactions_bulk(
        self, user_id: str, interactions: list[Interaction]
    ) -> None:
        """
        Add multiple user interactions with batched embedding generation.

        This method generates embeddings for all interactions in a single API call,
        significantly reducing the number of embedding API calls when adding multiple
        interactions at once.

        Args:
            user_id: The user ID
            interactions: List of interactions to add
        """
        if not interactions:
            return

        # Prepare texts for batch embedding
        texts = [
            "\n".join(
                [interaction.content or "", interaction.user_action_description or ""]
            )
            for interaction in interactions
        ]

        # Get all embeddings in a single API call
        embeddings = self.llm_client.get_embeddings(
            texts, self.embedding_model_name, self.embedding_dimensions
        )

        # Assign embeddings to interactions
        for interaction, embedding in zip(interactions, embeddings):
            interaction.embedding = embedding

        # Bulk upsert all interactions
        data_list = [interaction_to_data(interaction) for interaction in interactions]
        self.client.table("interactions").upsert(data_list).execute()

    @handle_exceptions
    def delete_user_interaction(self, request: DeleteUserInteractionRequest):
        self.client.table("interactions").delete().eq("user_id", request.user_id).eq(
            "interaction_id", request.interaction_id
        ).execute()

    @handle_exceptions
    def delete_user_profile(self, request: DeleteUserProfileRequest):
        self.client.table("profiles").delete().eq("user_id", request.user_id).eq(
            "profile_id", request.profile_id
        ).execute()

    @handle_exceptions
    def update_user_profile_by_id(
        self, user_id: str, profile_id: str, new_profile: UserProfile
    ):
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        response = (
            self.client.table("profiles")
            .select("profile_id")
            .eq("user_id", user_id)
            .eq("profile_id", profile_id)
            .gte("expiration_timestamp", current_timestamp)
            .execute()
        )

        if not response.data:
            logger.warning("User profile not found for user id: %s", user_id)
            return

        # Get embedding for the updated profile
        embedding = self._get_embedding(
            "\n".join([new_profile.profile_content, str(new_profile.custom_features)])
        )
        new_profile.embedding = embedding
        self.client.table("profiles").update(user_profile_to_data(new_profile)).eq(
            "profile_id", profile_id
        ).execute()

    @handle_exceptions
    def delete_all_interactions_for_user(self, user_id: str):
        self.client.table("interactions").delete().eq("user_id", user_id).execute()

    @handle_exceptions
    def delete_all_profiles_for_user(self, user_id: str):
        self.client.table("profiles").delete().eq("user_id", user_id).execute()

    @handle_exceptions
    def delete_all_profiles(self):
        """Delete all profiles across all users."""
        self.client.table("profiles").delete().gte("profile_id", 0).execute()

    @handle_exceptions
    def delete_all_interactions(self):
        """Delete all interactions across all users."""
        self.client.table("interactions").delete().gte("interaction_id", 0).execute()

    @handle_exceptions
    def count_all_interactions(self) -> int:
        """
        Count total interactions across all users.

        Returns:
            int: Total number of interactions
        """
        result = self.client.table("interactions").select("*", count="exact").execute()
        return result.count or 0

    @handle_exceptions
    def delete_oldest_interactions(self, count: int) -> int:
        """
        Delete the oldest N interactions based on created_at timestamp.

        Args:
            count (int): Number of oldest interactions to delete

        Returns:
            int: Number of interactions actually deleted
        """
        if count <= 0:
            return 0

        # Get oldest interaction IDs
        result = (
            self.client.table("interactions")
            .select("interaction_id")
            .order("created_at", desc=False)
            .limit(count)
            .execute()
        )
        if not result.data:
            return 0

        ids_to_delete = [row["interaction_id"] for row in result.data]
        self.client.table("interactions").delete().in_(
            "interaction_id", ids_to_delete
        ).execute()
        return len(ids_to_delete)

    @handle_exceptions
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
        # Build the query based on old_status
        # Update both status and last_modified_timestamp
        query = self.client.table("profiles").update(
            {
                "status": new_status.value if new_status else None,
                "last_modified_timestamp": int(datetime.now(timezone.utc).timestamp()),
            }
        )

        if old_status is None or (
            hasattr(old_status, "value") and old_status.value is None
        ):
            # Match CURRENT profiles (status IS NULL)
            query = query.is_("status", "null")
        else:
            # Match specific status
            query = query.eq("status", old_status.value)

        # Add user_ids filter if provided
        if user_ids is not None:
            query = query.in_("user_id", user_ids)

        # Execute the update
        response = query.execute()

        # Count the number of rows updated
        updated_count = len(response.data) if response.data else 0
        logger.info(
            f"Updated {updated_count} profiles from {old_status} to {new_status}"
        )
        return updated_count

    @handle_exceptions
    def delete_all_profiles_by_status(self, status: Status) -> int:
        """
        Delete all profiles with the given status atomically.

        Args:
            status: The status of profiles to delete

        Returns:
            int: Number of profiles deleted
        """
        # Build the delete query
        query = self.client.table("profiles").delete().eq("status", status.value)

        # Execute the delete
        response = query.execute()

        # Count the number of rows deleted
        deleted_count = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_count} profiles with status {status}")
        return deleted_count

    @handle_exceptions
    def get_user_ids_with_status(self, status: Optional[Status]) -> list[str]:
        """
        Get list of unique user_ids that have profiles with the given status.

        Args:
            status: The status to filter by (None for CURRENT)

        Returns:
            list[str]: List of unique user_ids
        """
        # Build the query to select distinct user_ids
        query = self.client.table("profiles").select("user_id")

        if status is None or (hasattr(status, "value") and status.value is None):
            # Match CURRENT profiles (status IS NULL)
            query = query.is_("status", "null")
        else:
            # Match specific status
            query = query.eq("status", status.value)

        # Execute the query
        response = query.execute()

        # Extract unique user_ids
        user_ids = (
            list({row["user_id"] for row in response.data}) if response.data else []
        )
        return user_ids

    # ==============================
    # Request methods
    # ==============================

    @handle_exceptions
    def add_request(self, request: Request):
        """
        Add a request to storage.

        Args:
            request: Request object to store
        """
        self.client.table("requests").upsert(request_to_data(request)).execute()

    @handle_exceptions
    def get_request(self, request_id: str) -> Optional[Request]:
        """
        Get a request by its ID.

        Args:
            request_id: The request ID to retrieve

        Returns:
            Request object if found, None otherwise
        """
        response = (
            self.client.table("requests")
            .select("*")
            .eq("request_id", request_id)
            .execute()
        )

        if not response.data:
            return None

        return response_to_request(response.data[0])

    @handle_exceptions
    def delete_request(self, request_id: str):
        """
        Delete a request by its ID and all associated interactions.

        Args:
            request_id: The request ID to delete
        """
        # First delete all interactions associated with this request
        self.client.table("interactions").delete().eq(
            "request_id", request_id
        ).execute()
        # Then delete the request itself
        self.client.table("requests").delete().eq("request_id", request_id).execute()

    @handle_exceptions
    def delete_request_group(self, request_group: str) -> int:
        """
        Delete all requests and interactions in a request group.

        Args:
            request_group: The request group name to delete

        Returns:
            int: Number of requests deleted
        """
        # First get all request IDs in this group
        response = (
            self.client.table("requests")
            .select("request_id")
            .eq("request_group", request_group)
            .execute()
        )

        if not response.data:
            return 0

        request_ids = [r["request_id"] for r in response.data]
        request_count = len(request_ids)

        # Delete all interactions for all requests in this group
        for request_id in request_ids:
            self.client.table("interactions").delete().eq(
                "request_id", request_id
            ).execute()

        # Delete all requests in this group
        self.client.table("requests").delete().eq(
            "request_group", request_group
        ).execute()

        return request_count

    @handle_exceptions
    def delete_all_requests(self):
        """Delete all requests and their associated interactions."""
        # First delete all interactions
        self.client.table("interactions").delete().neq(
            "request_id", "impossible_value"
        ).execute()
        # Then delete all requests
        self.client.table("requests").delete().neq(
            "request_id", "impossible_value"
        ).execute()

    @handle_exceptions
    def get_requests_by_request_group(
        self, user_id: str, request_group: str
    ) -> list[Request]:
        """
        Get all requests for a specific request_group.

        Args:
            user_id (str): User ID to filter requests
            request_group (str): Request group to filter by

        Returns:
            list[Request]: List of Request objects in the request_group
        """
        response = (
            self.client.table("requests")
            .select("*")
            .eq("user_id", user_id)
            .eq("request_group", request_group)
            .execute()
        )

        if not response.data:
            return []

        return [response_to_request(item) for item in response.data]

    @handle_exceptions
    def get_request_groups(
        self,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        top_k: Optional[int] = 30,
        offset: int = 0,
    ) -> dict[str, list[RequestInteractionDataModel]]:
        """
        Get requests with their associated interactions, grouped by request_group.

        Uses PostgREST's automatic JOIN syntax via the foreign key relationship between
        requests and interactions tables. Applies request-level filters and pagination,
        then groups returned requests by request_group.

        Args:
            user_id (str, optional): User ID to filter requests.
            request_id (str, optional): Specific request ID to retrieve
            start_time (int, optional): Start timestamp for filtering
            end_time (int, optional): End timestamp for filtering
            top_k (int, optional): Maximum number of requests to return
            offset (int): Number of requests to skip for pagination

        Returns:
            dict[str, list[RequestInteractionDataModel]]: Dictionary mapping request_group to list of RequestInteractionDataModel objects
        """
        # Explicit interaction columns to avoid fetching embedding vector(1536) and content_fts
        interaction_columns = "interaction_id,user_id,content,request_id,created_at,role,user_action,user_action_description,interacted_image_url,shadow_content,tools_used"
        select_expr = f"*, interactions({interaction_columns})"
        query = (
            self.client.table("requests")
            .select(select_expr)
            .order("created_at", desc=True)
        )

        # Apply user_id filter if specified
        if user_id:
            query = query.eq("user_id", user_id)

        # Apply filters
        if request_id:
            query = query.eq("request_id", request_id)
        if start_time:
            start_time_iso = datetime.fromtimestamp(
                start_time, tz=timezone.utc
            ).isoformat()
            query = query.gte("created_at", start_time_iso)
        if end_time:
            end_time_iso = datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()
            query = query.lte("created_at", end_time_iso)

        # Apply pagination: limit and offset on filtered requests.
        effective_limit = top_k or 100
        query = query.limit(effective_limit)
        if offset:
            query = query.offset(offset)

        response = query.execute()

        if not response.data:
            return {}

        # Parse and group the results
        grouped_results = {}
        for item in response.data:
            # Parse request
            req = response_to_request(item)

            # Get the group name
            group_name = req.request_group if req.request_group else ""

            # Parse interactions
            interactions = []
            if item.get("interactions"):
                # Handle both single interaction and array of interactions
                interaction_data = item["interactions"]
                if isinstance(interaction_data, list):
                    for int_data in interaction_data:
                        interactions.append(response_to_interaction(int_data))
                else:
                    # Single interaction case
                    interactions.append(response_to_interaction(interaction_data))

            # Sort interactions by created_at
            interactions = sorted(interactions, key=lambda x: x.created_at)

            # Add to grouped results
            if group_name not in grouped_results:
                grouped_results[group_name] = []
            grouped_results[group_name].append(
                RequestInteractionDataModel(
                    request_group=group_name,
                    request=req,
                    interactions=interactions,
                )
            )

        return grouped_results

    @handle_exceptions
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
        page_size = 1000
        current_offset = 0
        user_ids: set[str] = set()

        while True:
            query = (
                self.client.table("requests")
                .select("user_id")
                .order("created_at", desc=True)
                .limit(page_size)
                .offset(current_offset)
            )

            if user_id:
                query = query.eq("user_id", user_id)
            if start_time:
                start_time_iso = datetime.fromtimestamp(
                    start_time, tz=timezone.utc
                ).isoformat()
                query = query.gte("created_at", start_time_iso)
            if end_time:
                end_time_iso = datetime.fromtimestamp(
                    end_time, tz=timezone.utc
                ).isoformat()
                query = query.lte("created_at", end_time_iso)
            if source:
                query = query.eq("source", source)
            if agent_version:
                query = query.eq("agent_version", agent_version)

            response = query.execute()
            rows = response.data or []

            if not rows:
                break

            for row in rows:
                row_user_id = row.get("user_id")
                if row_user_id:
                    user_ids.add(row_user_id)

            if len(rows) < page_size:
                break
            current_offset += page_size

        return sorted(user_ids)

    # ==============================
    # Profile Change Log methods
    # ==============================

    @handle_exceptions
    def add_profile_change_log(self, profile_change_log: ProfileChangeLog):
        data = profile_change_log_to_data(profile_change_log)
        self.client.table("profile_change_logs").upsert(data).execute()

    @handle_exceptions
    def get_profile_change_logs(self, limit: int = 100) -> list[ProfileChangeLog]:
        response = (
            self.client.table("profile_change_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response_list_to_profile_change_logs(response.data)

    @handle_exceptions
    def delete_profile_change_log_for_user(self, user_id: str):
        self.client.table("profile_change_logs").delete().eq(
            "user_id", user_id
        ).execute()

    @handle_exceptions
    def delete_all_profile_change_logs(self):
        self.client.table("profile_change_logs").delete().gte("id", 0).execute()

    # ==============================
    # Search methods
    # ==============================

    @handle_exceptions
    def search_interaction(
        self, search_interaction_request: SearchInteractionRequest
    ) -> list[Interaction]:
        # Perform hybrid search (vector + FTS)
        if not search_interaction_request.query:
            return []

        query_text = search_interaction_request.query
        response = self.client.rpc(
            "hybrid_match_interactions",
            {
                "p_query_embedding": self._get_embedding(query_text),
                "p_query_text": query_text,
                "p_match_threshold": 0.1,
                "p_match_count": search_interaction_request.most_recent_k or 10,
                "p_search_mode": self.search_mode.value,
                "p_rrf_k": 60,
            },
        ).execute()

        interactions = response_list_to_interactions(response.data)

        if search_interaction_request.most_recent_k:
            sorted_interactions = sorted(
                interactions, key=lambda x: x.created_at, reverse=True
            )
            return list(
                reversed(
                    sorted_interactions[: search_interaction_request.most_recent_k]
                )
            )
        return interactions

    @handle_exceptions
    def search_user_profile(
        self,
        search_user_profile_request: SearchUserProfileRequest,
        status_filter: Optional[list[Optional[Status]]] = None,
        query_embedding: Optional[list[float]] = None,
    ) -> list[UserProfile]:
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        # Perform hybrid search (vector + FTS)
        if not search_user_profile_request.query:
            return []

        query_text = search_user_profile_request.query
        response = self.client.rpc(
            "hybrid_match_profiles",
            {
                "p_query_embedding": query_embedding or self._get_embedding(query_text),
                "p_query_text": query_text,
                "p_match_threshold": search_user_profile_request.threshold or 0.7,
                "p_match_count": search_user_profile_request.top_k or 10,
                "p_current_epoch": current_timestamp,
                "p_filter_user_id": search_user_profile_request.user_id,
                "p_search_mode": self.search_mode.value,
                "p_rrf_k": 60,
                "p_filter_extractor_name": search_user_profile_request.extractor_name,
            },
        ).execute()

        profiles = response_list_to_user_profiles(response.data)
        filtered_profiles = []
        for profile in profiles:
            # Apply status filter - compare Status enum values
            profile_matches_filter = False
            for status in status_filter:
                if status is None or (
                    hasattr(status, "value") and status.value is None
                ):
                    # Filter includes None/CURRENT - check if profile status is None
                    if profile.status is None:
                        profile_matches_filter = True
                        break
                elif isinstance(status, Status):
                    # Compare enum values
                    if profile.status == status:
                        profile_matches_filter = True
                        break
                elif isinstance(status, str):
                    # Legacy string comparison
                    if profile.status and profile.status.value == status:
                        profile_matches_filter = True
                        break

            if not profile_matches_filter:
                continue

            if search_user_profile_request.source:
                if search_user_profile_request.source.lower() != profile.source.lower():
                    continue
            if search_user_profile_request.custom_feature:
                if (
                    not search_user_profile_request.custom_feature.lower()
                    in str(profile.custom_features).lower()
                ):
                    continue
            filtered_profiles.append(profile)

        return filtered_profiles

    def _get_embedding(self, text: str) -> list[float]:
        """
        Get embedding for the given text using LLM client.

        Args:
            text: Text to get embedding for

        Returns:
            list[float]: Embedding vector
        """
        return self.llm_client.get_embedding(
            text, self.embedding_model_name, self.embedding_dimensions
        )

    @handle_exceptions
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

        # Helper to convert Unix timestamp to ISO format for Supabase queries
        def _timestamp_to_iso(ts: int) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # Helper to build status filter OR condition string
        def _build_status_or_condition(
            status_list: list[Optional[Status]],
        ) -> Optional[str]:
            has_none = None in status_list
            status_values = [
                s.value for s in status_list if s is not None and hasattr(s, "value")
            ]
            conditions = []
            if has_none:
                conditions.append("status.is.null")
            for sv in status_values:
                conditions.append(f"status.eq.{sv}")
            return ",".join(conditions) if conditions else None

        # If query is provided, use hybrid search first (filters applied in Python)
        if query:
            response = self.client.rpc(
                "hybrid_match_raw_feedbacks",
                {
                    "p_query_embedding": query_embedding or self._get_embedding(query),
                    "p_query_text": query,
                    "p_match_threshold": match_threshold,
                    "p_match_count": match_count
                    * 10,  # Get more results to allow for filtering
                    "p_filter_user_id": user_id,
                    "p_search_mode": self.search_mode.value,
                    "p_rrf_k": 60,
                },
            ).execute()
            raw_feedbacks = [
                RawFeedback(
                    raw_feedback_id=item["raw_feedback_id"],
                    user_id=item.get("user_id"),
                    feedback_name=item["feedback_name"],
                    created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                    request_id=item["request_id"],
                    agent_version=item["agent_version"],
                    feedback_content=item["feedback_content"],
                    do_action=item.get("do_action"),
                    do_not_action=item.get("do_not_action"),
                    when_condition=item.get("when_condition"),
                    blocking_issue=_parse_blocking_issue(item),
                    source=item.get("source"),
                    status=Status(item["status"]) if item.get("status") else None,
                    source_interaction_ids=item.get("source_interaction_ids") or [],
                    embedding=(
                        [float(x) for x in item["embedding"].strip("[]").split(",")]
                        if item.get("embedding")
                        else []
                    ),
                )
                for item in response.data
            ]

            # Apply filters in Python for RPC results
            filtered_feedbacks = []
            for rf in raw_feedbacks:
                if agent_version and rf.agent_version != agent_version:
                    continue
                if feedback_name and rf.feedback_name != feedback_name:
                    continue
                if start_time and rf.created_at < start_time:
                    continue
                if end_time and rf.created_at > end_time:
                    continue
                if status_filter is not None:
                    has_none = None in status_filter
                    status_strings = [
                        s.value
                        for s in status_filter
                        if s is not None and hasattr(s, "value")
                    ]
                    if has_none and rf.status is None:
                        pass
                    elif rf.status is not None and rf.status.value in status_strings:
                        pass
                    elif has_none and len(status_strings) == 0:
                        if rf.status is not None:
                            continue
                    else:
                        continue
                filtered_feedbacks.append(rf)
            return filtered_feedbacks[:match_count]

        # No query - use regular table query with Supabase filters
        # For the non-RPC path, resolve user_id to request_ids via the requests table
        request_ids_for_user: Optional[list[str]] = None
        if user_id:
            requests_response = (
                self.client.table("requests")
                .select("request_id")
                .eq("user_id", user_id)
                .execute()
            )
            request_ids_for_user = [r["request_id"] for r in requests_response.data]
            if not request_ids_for_user:
                return []

        db_query = (
            self.client.table("raw_feedbacks")
            .select("*")
            .order("created_at", desc=True)
            .limit(match_count)
        )

        # Apply filters at database level
        if request_ids_for_user is not None:
            db_query = db_query.in_("request_id", request_ids_for_user)
        if agent_version:
            db_query = db_query.eq("agent_version", agent_version)
        if feedback_name:
            db_query = db_query.eq("feedback_name", feedback_name)
        if start_time:
            db_query = db_query.gte("created_at", _timestamp_to_iso(start_time))
        if end_time:
            db_query = db_query.lte("created_at", _timestamp_to_iso(end_time))
        if status_filter is not None:
            or_condition = _build_status_or_condition(status_filter)
            if or_condition:
                db_query = db_query.or_(or_condition)

        response = db_query.execute()
        return [
            RawFeedback(
                raw_feedback_id=int(item["raw_feedback_id"]),
                user_id=item.get("user_id"),
                feedback_name=item["feedback_name"],
                created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                request_id=item["request_id"],
                agent_version=item["agent_version"],
                feedback_content=item["feedback_content"],
                do_action=item.get("do_action"),
                do_not_action=item.get("do_not_action"),
                when_condition=item.get("when_condition"),
                blocking_issue=_parse_blocking_issue(item),
                status=Status(item["status"]) if item.get("status") else None,
                source=item.get("source"),
                source_interaction_ids=item.get("source_interaction_ids") or [],
                embedding=(
                    [float(x) for x in item["embedding"].strip("[]").split(",")]
                    if item.get("embedding")
                    else []
                ),
            )
            for item in response.data
        ]

    @handle_exceptions
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
            status_filter (list[Optional[Status]], optional): List of Status values to filter by
            feedback_status_filter (FeedbackStatus, optional): Filter by FeedbackStatus (PENDING/APPROVED/REJECTED)
            match_threshold (float): Minimum similarity threshold (0.0 to 1.0)
            match_count (int): Maximum number of results to return

        Returns:
            list[Feedback]: List of matching feedback objects
        """

        # Helper to convert Unix timestamp to ISO format for Supabase queries
        def _timestamp_to_iso(ts: int) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        # Helper to build status filter OR condition string
        def _build_status_or_condition(
            status_list: list[Optional[Status]],
        ) -> Optional[str]:
            has_none = None in status_list
            status_values = [
                s.value for s in status_list if s is not None and hasattr(s, "value")
            ]
            conditions = []
            if has_none:
                conditions.append("status.is.null")
            for sv in status_values:
                conditions.append(f"status.eq.{sv}")
            return ",".join(conditions) if conditions else None

        # If query is provided, use hybrid search first (filters applied in Python)
        if query:
            response = self.client.rpc(
                "hybrid_match_feedbacks",
                {
                    "p_query_embedding": query_embedding or self._get_embedding(query),
                    "p_query_text": query,
                    "p_match_threshold": match_threshold,
                    "p_match_count": match_count
                    * 10,  # Get more results to allow for filtering
                    "p_search_mode": self.search_mode.value,
                    "p_rrf_k": 60,
                },
            ).execute()
            feedbacks = [
                Feedback(
                    feedback_id=item["feedback_id"],
                    feedback_name=item["feedback_name"],
                    created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                    feedback_content=item["feedback_content"],
                    do_action=item.get("do_action"),
                    do_not_action=item.get("do_not_action"),
                    when_condition=item.get("when_condition"),
                    blocking_issue=_parse_blocking_issue(item),
                    feedback_status=item["feedback_status"],
                    agent_version=item["agent_version"],
                    feedback_metadata=item.get("feedback_metadata") or "",
                    embedding=(
                        [float(x) for x in item["embedding"].strip("[]").split(",")]
                        if item.get("embedding")
                        else []
                    ),
                    status=Status(item["status"]) if item.get("status") else None,
                )
                for item in response.data
            ]

            # Apply filters in Python for RPC results
            filtered_feedbacks = []
            for f in feedbacks:
                if agent_version and f.agent_version != agent_version:
                    continue
                if feedback_name and f.feedback_name != feedback_name:
                    continue
                if start_time and f.created_at < start_time:
                    continue
                if end_time and f.created_at > end_time:
                    continue
                if (
                    feedback_status_filter
                    and f.feedback_status != feedback_status_filter.value
                ):
                    continue
                if status_filter is not None:
                    has_none = None in status_filter
                    status_strings = [
                        s.value
                        for s in status_filter
                        if s is not None and hasattr(s, "value")
                    ]
                    if has_none and f.status is None:
                        pass
                    elif f.status is not None and f.status.value in status_strings:
                        pass
                    elif has_none and len(status_strings) == 0:
                        if f.status is not None:
                            continue
                    else:
                        continue
                filtered_feedbacks.append(f)
            return filtered_feedbacks[:match_count]

        # No query - use regular table query with Supabase filters
        db_query = (
            self.client.table("feedbacks")
            .select("*")
            .order("created_at", desc=True)
            .limit(match_count)
        )

        # Apply filters at database level
        if agent_version:
            db_query = db_query.eq("agent_version", agent_version)
        if feedback_name:
            db_query = db_query.eq("feedback_name", feedback_name)
        if start_time:
            db_query = db_query.gte("created_at", _timestamp_to_iso(start_time))
        if end_time:
            db_query = db_query.lte("created_at", _timestamp_to_iso(end_time))
        if feedback_status_filter:
            db_query = db_query.eq("feedback_status", feedback_status_filter.value)
        if status_filter is not None:
            or_condition = _build_status_or_condition(status_filter)
            if or_condition:
                db_query = db_query.or_(or_condition)

        response = db_query.execute()
        return [
            Feedback(
                feedback_id=item["feedback_id"],
                feedback_name=item["feedback_name"],
                created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                agent_version=item["agent_version"],
                feedback_content=item["feedback_content"],
                do_action=item.get("do_action"),
                do_not_action=item.get("do_not_action"),
                when_condition=item.get("when_condition"),
                blocking_issue=_parse_blocking_issue(item),
                feedback_status=item["feedback_status"],
                feedback_metadata=item.get("feedback_metadata") or "",
                embedding=(
                    [float(x) for x in item["embedding"].strip("[]").split(",")]
                    if item.get("embedding")
                    else []
                ),
                status=Status(item["status"]) if item.get("status") else None,
            )
            for item in response.data
        ]

    # ==============================
    # Feedback methods
    # ==============================

    @handle_exceptions
    def save_raw_feedbacks(self, raw_feedbacks: list[RawFeedback]):
        for raw_feedback in raw_feedbacks:
            # Use indexed_content if available, otherwise when_condition,
            # otherwise build from structured fields
            embedding_text = (
                raw_feedback.indexed_content
                or raw_feedback.when_condition
                or raw_feedback.feedback_content
                or " ".join(
                    filter(
                        None,
                        [
                            raw_feedback.do_action,
                            raw_feedback.do_not_action,
                        ],
                    )
                )
            )
            if embedding_text:
                raw_feedback.embedding = self._get_embedding(embedding_text)
            self.client.table("raw_feedbacks").upsert(
                raw_feedback_to_data(raw_feedback)
            ).execute()

    @handle_exceptions
    def save_feedbacks(self, feedbacks: list[Feedback]) -> list[Feedback]:
        """
        Save regular feedbacks with embeddings.

        Args:
            feedbacks (list[Feedback]): List of feedback objects to save

        Returns:
            list[Feedback]: Saved feedbacks with feedback_id populated from storage
        """
        saved_feedbacks = []
        for feedback in feedbacks:
            embedding_text = feedback.when_condition or feedback.feedback_content
            embedding = self._get_embedding(embedding_text)
            feedback.embedding = embedding
            response = (
                self.client.table("feedbacks")
                .upsert(feedback_to_data(feedback))
                .execute()
            )
            if response.data:
                feedback.feedback_id = response.data[0].get(
                    "feedback_id", feedback.feedback_id
                )
            saved_feedbacks.append(feedback)
        return saved_feedbacks

    @handle_exceptions
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
        query = (
            self.client.table("raw_feedbacks")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        # Add user_id filter if specified
        if user_id is not None:
            query = query.eq("user_id", user_id)

        # Add feedback_name filter if specified (skip if None or empty string)
        if feedback_name:
            query = query.eq("feedback_name", feedback_name)

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        # Add time range filters if specified
        if start_time is not None:
            start_time_iso = datetime.fromtimestamp(
                start_time, tz=timezone.utc
            ).isoformat()
            query = query.gte("created_at", start_time_iso)
        if end_time is not None:
            end_time_iso = datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()
            query = query.lte("created_at", end_time_iso)

        # Add status filter if specified
        # Convert Status enum values to strings for database query
        if status_filter is not None:
            # Check for None values (current status)
            has_none = None in status_filter
            # Convert Status enum values to their string values
            status_strings = []
            for s in status_filter:
                if s is None:
                    continue
                elif isinstance(s, Status):
                    if s.value is not None:
                        status_strings.append(s.value)
                    else:
                        has_none = True
                elif isinstance(s, str):
                    status_strings.append(s)

            if has_none and len(status_strings) > 0:
                # Mix of None and other statuses: (status IS NULL OR status IN (...))
                query = query.or_(
                    f"status.is.null,status.in.({','.join(status_strings)})"
                )
            elif has_none:
                # Only None: status IS NULL
                query = query.is_("status", "null")
            elif len(status_strings) > 0:
                # Only non-None statuses: status IN (...)
                query = query.in_("status", status_strings)

        response = query.execute()
        return [
            RawFeedback(
                raw_feedback_id=int(item["raw_feedback_id"]),
                user_id=item.get("user_id"),
                feedback_name=item["feedback_name"],
                created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                request_id=item["request_id"],
                agent_version=item["agent_version"],
                feedback_content=item["feedback_content"],
                do_action=item.get("do_action"),
                do_not_action=item.get("do_not_action"),
                when_condition=item.get("when_condition"),
                blocking_issue=_parse_blocking_issue(item),
                status=Status(item["status"]) if item.get("status") else None,
                source=item.get("source"),
                source_interaction_ids=item.get("source_interaction_ids") or [],
                embedding=(
                    [float(x) for x in item["embedding"].strip("[]").split(",")]
                    if item["embedding"]
                    else []
                ),
            )
            for item in response.data
        ]

    @handle_exceptions
    def count_raw_feedbacks(
        self,
        user_id: Optional[str] = None,
        feedback_name: Optional[str] = None,
        min_raw_feedback_id: Optional[int] = None,
        agent_version: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> int:
        """
        Count raw feedbacks in storage efficiently using SQL COUNT.

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
        query = self.client.table("raw_feedbacks").select("*", count="exact")

        # Add user_id filter if specified
        if user_id is not None:
            query = query.eq("user_id", user_id)

        # Add feedback_name filter if specified (skip if None or empty string)
        if feedback_name:
            query = query.eq("feedback_name", feedback_name)

        # Add min_raw_feedback_id filter if specified
        if min_raw_feedback_id is not None:
            query = query.gt("raw_feedback_id", min_raw_feedback_id)

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        # Add status filter if specified
        # Convert Status enum values to strings for database query
        if status_filter is not None:
            # Check for None values (current status)
            has_none = None in status_filter
            # Convert Status enum values to their string values
            status_strings = []
            for s in status_filter:
                if s is None:
                    continue
                elif isinstance(s, Status):
                    if s.value is not None:
                        status_strings.append(s.value)
                    else:
                        has_none = True
                elif isinstance(s, str):
                    status_strings.append(s)

            if has_none and len(status_strings) > 0:
                # Mix of None and other statuses: (status IS NULL OR status IN (...))
                query = query.or_(
                    f"status.is.null,status.in.({','.join(status_strings)})"
                )
            elif has_none:
                # Only None: status IS NULL
                query = query.is_("status", "null")
            elif len(status_strings) > 0:
                # Only non-None statuses: status IN (...)
                query = query.in_("status", status_strings)

        response = query.execute()
        return response.count if response.count is not None else 0

    @handle_exceptions
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
        query = (
            self.client.table("feedbacks")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        # Add feedback_name filter if specified (skip if None or empty string)
        if feedback_name:
            query = query.eq("feedback_name", feedback_name)

        # Apply status filter (for Status: CURRENT, ARCHIVED, PENDING, etc.)
        if status_filter is not None:
            has_none = None in status_filter
            status_strings = [s.value for s in status_filter if s is not None]
            if has_none and len(status_strings) > 0:
                query = query.or_(
                    f"status.is.null,status.in.({','.join(status_strings)})"
                )
            elif has_none:
                query = query.is_("status", "null")
            elif len(status_strings) > 0:
                query = query.in_("status", status_strings)
        else:
            # Default behavior: exclude archived (keep current feedbacks)
            query = query.is_("status", "null")

        # Apply feedback_status filter (for FeedbackStatus: PENDING, APPROVED, REJECTED)
        # Only apply if specified; when None or empty, return all feedback statuses
        if feedback_status_filter:
            status_values = [s.value for s in feedback_status_filter]
            query = query.in_("feedback_status", status_values)

        response = query.execute()
        return [
            Feedback(
                feedback_id=item["feedback_id"],
                feedback_name=item["feedback_name"],
                created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                agent_version=item["agent_version"],
                feedback_content=item["feedback_content"],
                do_action=item.get("do_action"),
                do_not_action=item.get("do_not_action"),
                when_condition=item.get("when_condition"),
                blocking_issue=_parse_blocking_issue(item),
                feedback_status=item["feedback_status"],
                feedback_metadata=item["feedback_metadata"] or "",
                embedding=(
                    [float(x) for x in item["embedding"].strip("[]").split(",")]
                    if item["embedding"]
                    else []
                ),
                status=item.get("status"),
            )
            for item in response.data
        ]

    @handle_exceptions
    def delete_all_raw_feedbacks(self):
        self.client.table("raw_feedbacks").delete().gte("raw_feedback_id", 0).execute()

    @handle_exceptions
    def delete_all_feedbacks(self):
        self.client.table("feedbacks").delete().gte("feedback_id", 0).execute()

    @handle_exceptions
    def delete_feedback(self, feedback_id: int):
        """Delete a feedback by ID.

        Args:
            feedback_id (int): The ID of the feedback to delete
        """
        self.client.table("feedbacks").delete().eq("feedback_id", feedback_id).execute()

    @handle_exceptions
    def delete_raw_feedback(self, raw_feedback_id: int):
        """Delete a raw feedback by ID.

        Args:
            raw_feedback_id (int): The ID of the raw feedback to delete
        """
        self.client.table("raw_feedbacks").delete().eq(
            "raw_feedback_id", raw_feedback_id
        ).execute()

    @handle_exceptions
    def delete_all_raw_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all raw feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        query = (
            self.client.table("raw_feedbacks")
            .delete()
            .eq("feedback_name", feedback_name)
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        query.execute()

    @handle_exceptions
    def delete_all_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all regular feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        query = (
            self.client.table("feedbacks").delete().eq("feedback_name", feedback_name)
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        query.execute()

    @handle_exceptions
    def update_feedback_status(self, feedback_id: int, feedback_status: FeedbackStatus):
        """
        Update the status of a specific feedback.

        Args:
            feedback_id (int): The ID of the feedback to update
            feedback_status (FeedbackStatus): The new status to set

        Raises:
            ValueError: If feedback with the given ID is not found
        """
        # Check if feedback exists
        response = (
            self.client.table("feedbacks")
            .select("feedback_id")
            .eq("feedback_id", feedback_id)
            .execute()
        )

        if not response.data:
            raise ValueError(f"Feedback with ID {feedback_id} not found")

        # Update the feedback status
        self.client.table("feedbacks").update(
            {"feedback_status": feedback_status.value}
        ).eq("feedback_id", feedback_id).execute()

    @handle_exceptions
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
        query = (
            self.client.table("feedbacks")
            .update({"status": "archived"})
            .eq("feedback_name", feedback_name)
            .neq("feedback_status", FeedbackStatus.APPROVED.value)
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        query.execute()

    @handle_exceptions
    def restore_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Restore archived feedbacks by setting their status field to null.

        Args:
            feedback_name (str): The feedback name to restore
            agent_version (str, optional): The agent version to filter by. If None, restores all agent versions.
        """
        query = (
            self.client.table("feedbacks")
            .update({"status": None})
            .eq("feedback_name", feedback_name)
            .eq("status", "archived")
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        query.execute()

    @handle_exceptions
    def delete_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Permanently delete feedbacks that have status='archived'.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        query = (
            self.client.table("feedbacks")
            .delete()
            .eq("feedback_name", feedback_name)
            .eq("status", "archived")
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        query.execute()

    @handle_exceptions
    def archive_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Archive non-APPROVED feedbacks by IDs, setting their status field to 'archived'.
        APPROVED feedbacks are left untouched. No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to archive
        """
        if not feedback_ids:
            return
        self.client.table("feedbacks").update({"status": "archived"}).in_(
            "feedback_id", feedback_ids
        ).neq("feedback_status", FeedbackStatus.APPROVED.value).execute()

    @handle_exceptions
    def restore_archived_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Restore archived feedbacks by IDs, setting their status field to null.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to restore
        """
        if not feedback_ids:
            return
        self.client.table("feedbacks").update({"status": None}).in_(
            "feedback_id", feedback_ids
        ).eq("status", "archived").execute()

    @handle_exceptions
    def delete_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Permanently delete feedbacks by their IDs.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to delete
        """
        if not feedback_ids:
            return
        self.client.table("feedbacks").delete().in_(
            "feedback_id", feedback_ids
        ).execute()

    @handle_exceptions
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
        # Build the update query
        query = self.client.table("raw_feedbacks").update(
            {"status": new_status.value if new_status else None}
        )

        # Apply old_status filter
        if old_status is None or (
            hasattr(old_status, "value") and old_status.value is None
        ):
            # Match CURRENT raw feedbacks (status IS NULL)
            query = query.is_("status", "null")
        else:
            # Match specific status
            query = query.eq("status", old_status.value)

        # Add optional filters
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)
        if feedback_name is not None:
            query = query.eq("feedback_name", feedback_name)

        # Execute the update
        response = query.execute()

        # Count the number of rows updated
        updated_count = len(response.data) if response.data else 0
        logger.info(
            f"Updated {updated_count} raw feedbacks from {old_status} to {new_status}"
        )
        return updated_count

    @handle_exceptions
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
        # Build the delete query
        query = self.client.table("raw_feedbacks").delete().eq("status", status.value)

        # Add optional filters
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)
        if feedback_name is not None:
            query = query.eq("feedback_name", feedback_name)

        # Execute the delete
        response = query.execute()

        # Count the number of rows deleted
        deleted_count = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_count} raw feedbacks with status {status}")
        return deleted_count

    @handle_exceptions
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
        # Build the query to count matching raw feedbacks
        query = self.client.table("raw_feedbacks").select(
            "raw_feedback_id", count="exact"
        )

        # Apply status filter
        if status is None or (hasattr(status, "value") and status.value is None):
            # Match CURRENT raw feedbacks (status IS NULL)
            query = query.is_("status", "null")
        else:
            # Match specific status
            query = query.eq("status", status.value)

        # Add optional filters
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)
        if feedback_name is not None:
            query = query.eq("feedback_name", feedback_name)

        # Execute the query with limit 1 for efficiency
        response = query.limit(1).execute()

        return response.count is not None and response.count > 0

    def _parse_datetime_to_timestamp(self, datetime_str: str) -> int:
        """
        Parse datetime string to timestamp, handling various formats.

        Args:
            datetime_str (str): Datetime string to parse

        Returns:
            int: Unix timestamp
        """
        if not datetime_str:
            return int(datetime.now(timezone.utc).timestamp())

        try:
            # Normalize fractional seconds to 6 digits for consistent parsing
            # PostgreSQL may return variable precision (e.g., .47232 instead of .472320)
            import re

            normalized_str = datetime_str
            match = re.search(r"\.(\d+)", datetime_str)
            if match:
                frac = match.group(1)
                if len(frac) < 6:
                    frac = frac.ljust(6, "0")
                elif len(frac) > 6:
                    frac = frac[:6]
                normalized_str = re.sub(r"\.\d+", f".{frac}", datetime_str)

            # Try parsing as ISO format first
            if normalized_str.endswith("Z"):
                normalized_str = normalized_str.replace("Z", "+00:00")
            return int(datetime.fromisoformat(normalized_str).timestamp())
        except ValueError:
            try:
                # Try parsing with different formats using normalized string
                for fmt in [
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                ]:
                    try:
                        return int(datetime.strptime(normalized_str, fmt).timestamp())
                    except ValueError:
                        continue

                # If all parsing attempts fail, log warning and return current timestamp
                logger.warning("Could not parse datetime string: %s", datetime_str)
                return int(datetime.now(timezone.utc).timestamp())
            except Exception as e:
                logger.warning(
                    "Error parsing datetime string '%s': %s", datetime_str, str(e)
                )
                return int(datetime.now(timezone.utc).timestamp())

    # ==============================
    # Agent Success Evaluation methods
    # ==============================

    @handle_exceptions
    def save_agent_success_evaluation_results(
        self, results: list[AgentSuccessEvaluationResult]
    ):
        """
        Save agent success evaluation results with embeddings.

        Args:
            results (list[AgentSuccessEvaluationResult]): List of agent success evaluation result objects to save
        """
        for result in results:
            # Generate embedding from combined content
            embedding_text = f"{result.failure_type} {result.failure_reason} {result.agent_prompt_update}"
            if embedding_text.strip():
                embedding = self._get_embedding(embedding_text)
                result.embedding = embedding
            else:
                result.embedding = []

            self.client.table("agent_success_evaluation_result").upsert(
                agent_success_evaluation_result_to_data(result)
            ).execute()

    @handle_exceptions
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
        query = (
            self.client.table("agent_success_evaluation_result")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        # Add agent_version filter if specified
        if agent_version is not None:
            query = query.eq("agent_version", agent_version)

        response = query.execute()
        return [
            AgentSuccessEvaluationResult(
                result_id=int(item["result_id"]),
                request_id=item["request_id"],
                agent_version=item["agent_version"],
                evaluation_name=item.get("evaluation_name"),
                is_success=item["is_success"],
                failure_type=item["failure_type"],
                failure_reason=item["failure_reason"],
                agent_prompt_update=item["agent_prompt_update"],
                created_at=self._parse_datetime_to_timestamp(item["created_at"]),
                regular_vs_shadow=(
                    RegularVsShadow(item["regular_vs_shadow"])
                    if item.get("regular_vs_shadow")
                    else None
                ),
                embedding=(
                    [float(x) for x in item["embedding"].strip("[]").split(",")]
                    if item["embedding"]
                    else []
                ),
            )
            for item in response.data
        ]

    @handle_exceptions
    def delete_all_agent_success_evaluation_results(self):
        """Delete all agent success evaluation results from storage."""
        self.client.table("agent_success_evaluation_result").delete().gte(
            "result_id", 0
        ).execute()

    # ==============================
    # Dashboard methods
    # ==============================

    @handle_exceptions
    def get_dashboard_stats(self, days_back: int = 30) -> dict:
        """
        Get comprehensive dashboard statistics including counts and time-series data.
        Returns raw ungrouped time-series data for frontend grouping.

        Args:
            days_back (int): Number of days to include in time series data

        Returns:
            dict: Dictionary containing current_period, previous_period, and raw time_series data
        """

        current_time = int(datetime.now(timezone.utc).timestamp())

        # Calculate time boundaries
        seconds_in_period = days_back * 24 * 60 * 60
        current_period_start = current_time - seconds_in_period
        previous_period_start = current_period_start - seconds_in_period

        # Convert timestamps to ISO format for Supabase queries
        current_time_iso = datetime.fromtimestamp(
            current_time, tz=timezone.utc
        ).isoformat()
        current_period_start_iso = datetime.fromtimestamp(
            current_period_start, tz=timezone.utc
        ).isoformat()
        previous_period_start_iso = datetime.fromtimestamp(
            previous_period_start, tz=timezone.utc
        ).isoformat()

        # Get current and previous period stats using count queries
        # Interactions
        interactions_current = (
            self.client.table("interactions")
            .select("interaction_id", count="exact")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .execute()
        )

        interactions_previous = (
            self.client.table("interactions")
            .select("interaction_id", count="exact")
            .gte("created_at", previous_period_start_iso)
            .lt("created_at", current_period_start_iso)
            .execute()
        )

        # Profiles (uses bigint timestamps, not datetime)
        profiles_current = (
            self.client.table("profiles")
            .select("profile_id", count="exact")
            .gte("last_modified_timestamp", current_period_start)
            .lte("last_modified_timestamp", current_time)
            .execute()
        )

        profiles_previous = (
            self.client.table("profiles")
            .select("profile_id", count="exact")
            .gte("last_modified_timestamp", previous_period_start)
            .lt("last_modified_timestamp", current_period_start)
            .execute()
        )

        # Feedbacks (raw + aggregated)
        raw_feedbacks_current = (
            self.client.table("raw_feedbacks")
            .select("raw_feedback_id", count="exact")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .execute()
        )

        raw_feedbacks_previous = (
            self.client.table("raw_feedbacks")
            .select("raw_feedback_id", count="exact")
            .gte("created_at", previous_period_start_iso)
            .lt("created_at", current_period_start_iso)
            .execute()
        )

        aggregated_feedbacks_current = (
            self.client.table("feedbacks")
            .select("feedback_id", count="exact")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .execute()
        )

        aggregated_feedbacks_previous = (
            self.client.table("feedbacks")
            .select("feedback_id", count="exact")
            .gte("created_at", previous_period_start_iso)
            .lt("created_at", current_period_start_iso)
            .execute()
        )

        # Agent success evaluations
        evaluations_current = (
            self.client.table("agent_success_evaluation_result")
            .select("is_success")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .execute()
        )

        evaluations_previous = (
            self.client.table("agent_success_evaluation_result")
            .select("is_success")
            .gte("created_at", previous_period_start_iso)
            .lt("created_at", current_period_start_iso)
            .execute()
        )

        # Calculate success rates
        total_eval_current = len(evaluations_current.data)
        success_count_current = sum(
            1 for e in evaluations_current.data if e.get("is_success")
        )
        success_rate_current = (
            (success_count_current / total_eval_current * 100)
            if total_eval_current > 0
            else 0.0
        )

        total_eval_previous = len(evaluations_previous.data)
        success_count_previous = sum(
            1 for e in evaluations_previous.data if e.get("is_success")
        )
        success_rate_previous = (
            (success_count_previous / total_eval_previous * 100)
            if total_eval_previous > 0
            else 0.0
        )

        # Build stats objects
        current_stats = {
            "total_profiles": profiles_current.count
            if profiles_current.count is not None
            else 0,
            "total_interactions": interactions_current.count
            if interactions_current.count is not None
            else 0,
            "total_feedbacks": (
                (
                    raw_feedbacks_current.count
                    if raw_feedbacks_current.count is not None
                    else 0
                )
                + (
                    aggregated_feedbacks_current.count
                    if aggregated_feedbacks_current.count is not None
                    else 0
                )
            ),
            "success_rate": success_rate_current,
        }

        previous_stats = {
            "total_profiles": profiles_previous.count
            if profiles_previous.count is not None
            else 0,
            "total_interactions": interactions_previous.count
            if interactions_previous.count is not None
            else 0,
            "total_feedbacks": (
                (
                    raw_feedbacks_previous.count
                    if raw_feedbacks_previous.count is not None
                    else 0
                )
                + (
                    aggregated_feedbacks_previous.count
                    if aggregated_feedbacks_previous.count is not None
                    else 0
                )
            ),
            "success_rate": success_rate_previous,
        }

        # Get time-series data (simplified approach - fetch and group in Python)
        # For a production system with large data, consider creating SQL functions for aggregation

        # Interactions time series
        interactions_ts_data = (
            self.client.table("interactions")
            .select("created_at")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .order("created_at")
            .execute()
        )

        # Profiles time series (uses bigint timestamps)
        profiles_ts_data = (
            self.client.table("profiles")
            .select("last_modified_timestamp")
            .gte("last_modified_timestamp", current_period_start)
            .lte("last_modified_timestamp", current_time)
            .order("last_modified_timestamp")
            .execute()
        )

        # Feedbacks time series
        feedbacks_ts_data = (
            self.client.table("raw_feedbacks")
            .select("created_at")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .order("created_at")
            .execute()
        )

        # Evaluations time series
        evaluations_ts_data = (
            self.client.table("agent_success_evaluation_result")
            .select("created_at, is_success")
            .gte("created_at", current_period_start_iso)
            .lte("created_at", current_time_iso)
            .order("created_at")
            .execute()
        )

        # Convert to raw time series data points (no grouping - frontend will handle)
        interactions_time_series = [
            {
                "timestamp": self._parse_datetime_to_timestamp(r["created_at"]),
                "value": 1,
            }
            for r in interactions_ts_data.data
        ]

        profiles_time_series = [
            {"timestamp": r["last_modified_timestamp"], "value": 1}  # Already bigint
            for r in profiles_ts_data.data
        ]

        feedbacks_time_series = [
            {
                "timestamp": self._parse_datetime_to_timestamp(r["created_at"]),
                "value": 1,
            }
            for r in feedbacks_ts_data.data
        ]

        # For evaluations, include success rate value
        evaluations_time_series = [
            {
                "timestamp": self._parse_datetime_to_timestamp(record["created_at"]),
                "value": 100 if record.get("is_success") else 0,
            }
            for record in evaluations_ts_data.data
        ]

        return {
            "current_period": current_stats,
            "previous_period": previous_stats,
            "interactions_time_series": sorted(
                interactions_time_series, key=lambda x: x["timestamp"]
            ),
            "profiles_time_series": sorted(
                profiles_time_series, key=lambda x: x["timestamp"]
            ),
            "feedbacks_time_series": sorted(
                feedbacks_time_series, key=lambda x: x["timestamp"]
            ),
            "evaluations_time_series": sorted(
                evaluations_time_series, key=lambda x: x["timestamp"]
            ),
        }

    def _group_by_time_bucket(
        self, timestamps: list[int], period_start: int, granularity: str
    ) -> dict:
        """
        Group timestamps into buckets based on granularity.

        Args:
            timestamps (list[int]): List of Unix timestamps
            period_start (int): Start of the period
            granularity (str): Time grouping ('daily', 'weekly', 'monthly')

        Returns:
            dict: Dictionary mapping bucket timestamp to count
        """
        buckets = {}
        for timestamp in timestamps:
            ts_key = self._get_time_bucket(timestamp, period_start, granularity)
            buckets[ts_key] = buckets.get(ts_key, 0) + 1
        return buckets

    def _get_time_bucket(
        self, timestamp: int, period_start: int, granularity: str
    ) -> int:
        """
        Get the time bucket key for a timestamp based on granularity.

        Args:
            timestamp (int): The timestamp to bucket
            period_start (int): Start of the period
            granularity (str): 'daily', 'weekly', or 'monthly'

        Returns:
            int: Bucket timestamp (start of day/week/month)
        """
        from datetime import (
            timedelta,
        )  # Keep local import for infrequently used function

        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        if granularity == "daily":
            bucket_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif granularity == "weekly":
            # Start of week (Monday)
            days_since_monday = dt.weekday()
            bucket_dt = (dt - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif granularity == "monthly":
            bucket_dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to daily
            bucket_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)

        return int(bucket_dt.timestamp())

    # ==============================
    # Operation State methods
    # ==============================

    @handle_exceptions
    def create_operation_state(self, service_name: str, operation_state: dict):
        """
        Create operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        data = {
            "service_name": service_name,
            "operation_state": operation_state,
            "updated_at": self._current_timestamp(),
        }
        self.client.table("_operation_state").insert(data).execute()

    @handle_exceptions
    def upsert_operation_state(self, service_name: str, operation_state: dict):
        """
        Create or update operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        data = {
            "service_name": service_name,
            "operation_state": operation_state,
            "updated_at": self._current_timestamp(),
        }
        self.client.table("_operation_state").upsert(data).execute()

    @handle_exceptions
    def get_operation_state(self, service_name: str) -> Optional[dict]:
        """
        Get operation state for a specific service.

        Args:
            service_name (str): Name of the service

        Returns:
            Optional[dict]: Operation state data or None if not found
        """
        response = (
            self.client.table("_operation_state")
            .select("*")
            .eq("service_name", service_name)
            .execute()
        )

        if response.data:
            return {
                "service_name": response.data[0]["service_name"],
                "operation_state": response.data[0]["operation_state"],
                "updated_at": response.data[0]["updated_at"],
            }
        return None

    @handle_exceptions
    def try_acquire_in_progress_lock(
        self, state_key: str, request_id: str, stale_lock_seconds: int = 300
    ) -> dict:
        """
        Atomically try to acquire an in-progress lock using PostgreSQL RPC.

        This method uses a single atomic database operation to either:
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
        response = self.client.rpc(
            "try_acquire_in_progress_lock",
            {
                "p_state_key": state_key,
                "p_request_id": request_id,
                "p_stale_lock_seconds": stale_lock_seconds,
            },
        ).execute()

        if response.data:
            return response.data
        return {"acquired": False, "state": {}}

    @handle_exceptions
    def get_operation_state_with_new_request_interaction(
        self,
        service_name: str,
        user_id: Optional[str],
        sources: Optional[list[str]] = None,
    ) -> tuple[dict, list[RequestInteractionDataModel]]:
        """
        Retrieve operation state and new interactions grouped by request using a single SQL query.

        Uses an RPC function to perform JOIN and filtering in the database for efficiency.

        Args:
            service_name (str): Name of the service
            user_id (Optional[str]): User identifier to filter interactions.
                If None, returns interactions across all users (for non-user-scoped extractors).
            sources (Optional[list[str]]): Optional list of sources to filter interactions by

        Returns:
            tuple[dict, list[RequestInteractionDataModel]]: Operation state payload and list of
                RequestInteractionDataModel objects containing new interactions grouped by request
        """
        # Query 1: Get operation state
        state_record = self.get_operation_state(service_name)
        operation_state: dict = {}
        if state_record and isinstance(state_record.get("operation_state"), dict):
            operation_state = state_record["operation_state"]

        # Extract filtering params
        last_processed_ids = operation_state.get("last_processed_interaction_ids") or []
        last_processed_timestamp = operation_state.get("last_processed_timestamp")

        # Convert timestamp to ISO format for SQL
        timestamp_iso = None
        if last_processed_timestamp is not None:
            timestamp_iso = datetime.fromtimestamp(
                last_processed_timestamp, tz=timezone.utc
            ).isoformat()

        # Query 2: Call RPC function for JOIN and filtering in database
        response = self.client.rpc(
            "get_new_request_interaction_groups",
            {
                "p_user_id": user_id,
                "p_last_processed_timestamp": timestamp_iso,
                "p_excluded_interaction_ids": [int(id) for id in last_processed_ids],
                "p_sources": sources,
            },
        ).execute()

        # Group results by request_id
        requests_map: dict[str, Request] = {}
        interactions_by_request: dict[str, list[Interaction]] = {}

        for row in response.data:
            req_id = row["request_id"]

            # Build Request object (once per request)
            if req_id not in requests_map:
                requests_map[req_id] = Request(
                    request_id=req_id,
                    user_id=row["request_user_id"],
                    created_at=int(
                        datetime.fromisoformat(
                            row["request_created_at"].replace("Z", "+00:00")
                        ).timestamp()
                    ),
                    source=row.get("request_source") or "",
                    agent_version=row.get("request_agent_version") or "",
                    request_group=row.get("request_group"),
                )
                interactions_by_request[req_id] = []

            # Deserialize tools_used from JSONB array
            tools_used = []
            tools_used_data = row.get("interaction_tools_used")
            if tools_used_data and isinstance(tools_used_data, list):
                tools_used = [
                    ToolUsed(**t) for t in tools_used_data if isinstance(t, dict)
                ]

            # Build Interaction object
            interaction = Interaction(
                interaction_id=row["interaction_id"],
                user_id=row["interaction_user_id"],
                content=row["interaction_content"],
                request_id=row["interaction_request_id"],
                created_at=int(
                    datetime.fromisoformat(
                        row["interaction_created_at"].replace("Z", "+00:00")
                    ).timestamp()
                ),
                role=row.get("interaction_role") or "User",
                user_action=UserActionType(row["interaction_user_action"]),
                user_action_description=row["interaction_user_action_description"],
                interacted_image_url=row["interaction_interacted_image_url"],
                shadow_content=row.get("interaction_shadow_content") or "",
                tools_used=tools_used,
            )
            interactions_by_request[req_id].append(interaction)

        # Build RequestInteractionDataModel objects
        request_groups: list[RequestInteractionDataModel] = []
        for req_id, req in requests_map.items():
            interactions = sorted(
                interactions_by_request[req_id], key=lambda x: x.created_at or 0
            )
            group_name = req.request_group or req.request_id
            request_groups.append(
                RequestInteractionDataModel(
                    request_group=group_name,
                    request=req,
                    interactions=interactions,
                )
            )

        # Sort groups by earliest interaction
        request_groups.sort(
            key=lambda g: min(i.created_at or 0 for i in g.interactions)
            if g.interactions
            else 0
        )

        return operation_state, request_groups

    @handle_exceptions
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

        Uses an RPC function to efficiently retrieve the last K interactions and their
        associated request data in a single database query.

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
                - List of RequestInteractionDataModel objects (grouped by request/request_group)
                - Flat list of all interactions sorted by created_at DESC
        """
        # Call RPC function for efficient retrieval
        response = self.client.rpc(
            "get_last_k_interactions",
            {
                "p_user_id": user_id,
                "p_limit": k,
                "p_sources": sources,
                "p_start_time": start_time,
                "p_end_time": end_time,
                "p_agent_version": agent_version,
            },
        ).execute()

        # Build flat interactions list and group by request
        flat_interactions: list[Interaction] = []
        requests_map: dict[str, Request] = {}
        interactions_by_request: dict[str, list[Interaction]] = {}

        for row in response.data:
            req_id = row["request_id"]

            # Build Request object (once per request)
            if req_id not in requests_map:
                requests_map[req_id] = Request(
                    request_id=req_id,
                    user_id=row["request_user_id"],
                    created_at=int(
                        datetime.fromisoformat(
                            row["request_created_at"].replace("Z", "+00:00")
                        ).timestamp()
                    ),
                    source=row.get("request_source") or "",
                    agent_version=row.get("request_agent_version") or "",
                    request_group=row.get("request_group"),
                )
                interactions_by_request[req_id] = []

            # Deserialize tools_used from JSONB array
            tools_used = []
            tools_used_data = row.get("interaction_tools_used")
            if tools_used_data and isinstance(tools_used_data, list):
                tools_used = [
                    ToolUsed(**t) for t in tools_used_data if isinstance(t, dict)
                ]

            # Build Interaction object
            interaction = Interaction(
                interaction_id=row["interaction_id"],
                user_id=row["interaction_user_id"],
                content=row["interaction_content"],
                request_id=row["interaction_request_id"],
                created_at=int(
                    datetime.fromisoformat(
                        row["interaction_created_at"].replace("Z", "+00:00")
                    ).timestamp()
                ),
                role=row.get("interaction_role") or "User",
                user_action=UserActionType(row["interaction_user_action"]),
                user_action_description=row["interaction_user_action_description"],
                interacted_image_url=row["interaction_interacted_image_url"],
                shadow_content=row.get("interaction_shadow_content") or "",
                tools_used=tools_used,
            )
            flat_interactions.append(interaction)
            interactions_by_request[req_id].append(interaction)

        # Build RequestInteractionDataModel objects
        request_groups: list[RequestInteractionDataModel] = []
        for req_id, req in requests_map.items():
            # Sort interactions by created_at ASC within each group
            interactions = sorted(
                interactions_by_request[req_id], key=lambda x: x.created_at or 0
            )
            group_name = req.request_group or req.request_id
            request_groups.append(
                RequestInteractionDataModel(
                    request_group=group_name,
                    request=req,
                    interactions=interactions,
                )
            )

        # Sort groups by earliest interaction timestamp
        request_groups.sort(
            key=lambda g: min(i.created_at or 0 for i in g.interactions)
            if g.interactions
            else 0
        )

        return request_groups, flat_interactions

    @handle_exceptions
    def update_operation_state(self, service_name: str, operation_state: dict):
        """
        Update operation state for a specific service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        data = {
            "operation_state": operation_state,
            "updated_at": self._current_timestamp(),
        }
        self.client.table("_operation_state").update(data).eq(
            "service_name", service_name
        ).execute()

    @handle_exceptions
    def get_all_operation_states(self) -> list[dict]:
        """
        Get all operation states.

        Returns:
            list[dict]: List of all operation state records
        """
        response = self.client.table("_operation_state").select("*").execute()
        return [
            {
                "service_name": item["service_name"],
                "operation_state": item["operation_state"],
                "updated_at": item["updated_at"],
            }
            for item in response.data
        ]

    @handle_exceptions
    def delete_operation_state(self, service_name: str):
        """
        Delete operation state for a specific service.

        Args:
            service_name (str): Name of the service
        """
        self.client.table("_operation_state").delete().eq(
            "service_name", service_name
        ).execute()

    @handle_exceptions
    def delete_all_operation_states(self):
        """Delete all operation states."""
        self.client.table("_operation_state").delete().neq(
            "service_name", "impossible_value"
        ).execute()

    # ==============================
    # Statistics methods
    # ==============================

    @handle_exceptions
    def get_profile_statistics(self) -> dict:
        """Get profile count statistics by status using efficient SQL queries.

        Returns:
            dict with keys: current_count, pending_count, archived_count, expiring_soon_count
        """
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        expiring_soon_timestamp = current_timestamp + (7 * 24 * 60 * 60)  # 7 days

        # Get all profiles that are not expired
        response = (
            self.client.table("profiles")
            .select("status, expiration_timestamp")
            .gte("expiration_timestamp", current_timestamp)
            .execute()
        )

        stats = {
            "current_count": 0,
            "pending_count": 0,
            "archived_count": 0,
            "expiring_soon_count": 0,
        }

        # Count profiles by status
        for profile_data in response.data:
            status = profile_data.get("status")
            expiration_timestamp = profile_data.get("expiration_timestamp")

            # Count by status
            if status is None:
                stats["current_count"] += 1
            elif status == "pending":
                stats["pending_count"] += 1
            elif status == "archived":
                stats["archived_count"] += 1

            # Count expiring soon (current profiles only)
            if (
                status is None
                and expiration_timestamp is not None
                and expiration_timestamp <= expiring_soon_timestamp
            ):
                stats["expiring_soon_count"] += 1

        return stats

    # ==============================
    # Skill methods
    # ==============================

    @handle_exceptions
    def save_skills(self, skills: list[Skill]):
        """
        Save skills with embeddings.

        Args:
            skills (list[Skill]): List of skill objects to save
        """
        for skill in skills:
            embedding_text = skill.instructions or skill.description
            embedding = self._get_embedding(embedding_text)
            skill.embedding = embedding
            data = skill_to_data(skill)
            data["org_id"] = self.org_id

            if skill.skill_id:
                # Update existing skill (skill_id is GENERATED ALWAYS, cannot be inserted)
                skill_id = data.pop("skill_id")
                self.client.table("skills").update(data).eq(
                    "skill_id", skill_id
                ).execute()
            else:
                # Insert new skill, let DB auto-generate skill_id
                self.client.table("skills").insert(data).execute()

    @handle_exceptions
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
        db_query = (
            self.client.table("skills")
            .select("*")
            .eq("org_id", self.org_id)
            .order("created_at", desc=True)
            .limit(limit)
        )

        if feedback_name:
            db_query = db_query.eq("feedback_name", feedback_name)
        if agent_version:
            db_query = db_query.eq("agent_version", agent_version)
        if skill_status:
            db_query = db_query.eq("skill_status", skill_status.value)

        response = db_query.execute()
        return [response_to_skill(item) for item in response.data]

    @handle_exceptions
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

        Returns:
            list[Skill]: List of matching skill objects
        """
        if query:
            response = self.client.rpc(
                "hybrid_match_skills",
                {
                    "p_query_embedding": query_embedding or self._get_embedding(query),
                    "p_query_text": query,
                    "p_match_threshold": match_threshold,
                    "p_match_count": match_count * 10,
                    "p_org_id": self.org_id,
                    "p_search_mode": self.search_mode.value,
                    "p_rrf_k": 60,
                },
            ).execute()

            skills = [response_to_skill(item) for item in response.data]

            # Apply Python-level filters
            filtered_skills = []
            for s in skills:
                if feedback_name and s.feedback_name != feedback_name:
                    continue
                if agent_version and s.agent_version != agent_version:
                    continue
                if skill_status and s.skill_status != skill_status:
                    continue
                filtered_skills.append(s)
            return filtered_skills[:match_count]

        # No query - use regular table query
        return self.get_skills(
            limit=match_count,
            feedback_name=feedback_name,
            agent_version=agent_version,
            skill_status=skill_status,
        )

    @handle_exceptions
    def update_skill_status(self, skill_id: int, skill_status: SkillStatus):
        """
        Update the status of a specific skill.

        Args:
            skill_id (int): The ID of the skill to update
            skill_status (SkillStatus): The new status to set
        """
        self.client.table("skills").update({"skill_status": skill_status.value}).eq(
            "skill_id", skill_id
        ).eq("org_id", self.org_id).execute()

    @handle_exceptions
    def delete_skill(self, skill_id: int):
        """
        Delete a skill by ID.

        Args:
            skill_id (int): The ID of the skill to delete
        """
        self.client.table("skills").delete().eq("skill_id", skill_id).eq(
            "org_id", self.org_id
        ).execute()

    @handle_exceptions
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
        if not request_ids:
            return []

        response = (
            self.client.table("interactions")
            .select("*")
            .eq("org_id", self.org_id)
            .in_("request_id", request_ids)
            .order("created_at", desc=False)
            .execute()
        )
        return [response_to_interaction(item) for item in response.data]
