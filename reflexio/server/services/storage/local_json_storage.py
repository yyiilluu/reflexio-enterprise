import json
import os
import logging
import threading
import time
import reflexio.data as data
from typing import Optional
from datetime import datetime, timezone
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio_commons.api_schema.service_schemas import (
    DeleteUserProfileRequest,
    DeleteUserInteractionRequest,
    RawFeedback,
    UserProfile,
    Interaction,
    Request,
    ProfileChangeLog,
    FeedbackAggregationChangeLog,
    Feedback,
    Skill,
    SkillStatus,
    AgentSuccessEvaluationResult,
    FeedbackStatus,
    Status,
)
from reflexio_commons.api_schema.retriever_schema import (
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio.server.services.storage.error import StorageError
from reflexio_commons.config_schema import StorageConfigLocal
from reflexio.server import LOCAL_STORAGE_PATH


logger = logging.getLogger(__name__)


class LocalJsonStorage(BaseStorage):
    """
    Storage class that uses local json file to store data
    """

    # Class-level lock for atomic operations across all instances
    _lock = threading.Lock()

    def __init__(
        self,
        org_id: str,
        base_dir: Optional[str] = None,
        config: Optional[StorageConfigLocal] = None,
    ):
        self.config: Optional[StorageConfigLocal] = config
        if self.config:
            base_dir = self.config.dir_path
            if not os.path.isabs(base_dir):
                err_msg = f"Local Json Storage received a non absolute path {base_dir}"
                logger.error(err_msg)
                raise StorageError(err_msg)
            if not base_dir:
                err_msg = f"Local Json Storage received empty directory"
                logger.error(err_msg)
                raise StorageError(err_msg)
            try:
                if not os.path.exists(base_dir):
                    os.makedirs(base_dir, exist_ok=True)
            except OSError:
                err_msg = f"Local Json Storage cannot create directory at {base_dir}"
                logger.error(err_msg)
                raise StorageError(err_msg)

        if base_dir is None:
            base_dir = LOCAL_STORAGE_PATH or os.path.dirname(data.__file__)
        try:
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)
        except OSError:
            err_msg = f"Local Json Storage cannot create directory at {base_dir}"
            logger.error(err_msg)
            raise StorageError(err_msg)
        if not os.path.isdir(base_dir):
            err_msg = f"Local Json Storage specified an invalid directory at {base_dir}"
            logger.error(err_msg)
            raise StorageError(err_msg)
        logger.info(f"Local Json Storage for org {org_id} uses directory {base_dir}")
        super().__init__(org_id, base_dir)
        self.file_path = os.path.join(base_dir, f"user_profiles_{org_id}.json")
        if not os.path.exists(self.file_path):
            self._save({})

    def _load(self) -> dict:
        with open(self.file_path, encoding="utf-8") as file:
            return json.load(file)

    def _save(self, all_memories: dict):
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(all_memories, file)

    def _load_operation_states(self) -> tuple[dict, dict]:
        """
        Load operation state container from disk.

        Returns:
            tuple[dict, dict]: Tuple containing the full memory payload and the operation state map.
        """
        all_memories = self._load()
        operation_states = all_memories.get("operation_states")
        if operation_states is None:
            operation_states = {}
            all_memories["operation_states"] = operation_states
        return all_memories, operation_states

    def _current_timestamp(self) -> str:
        """Return a timezone-aware ISO timestamp for updated_at."""
        return datetime.now(timezone.utc).isoformat()

    # ==============================
    # CRUD methods
    # ==============================

    def get_all_profiles(
        self,
        limit: int = 100,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        with self._lock:
            all_memories = self._load()
        profiles = []
        for _, user_data in all_memories.items():
            if "profiles" in user_data:
                for profile in user_data["profiles"]:
                    profile_obj = UserProfile.model_validate_json(profile)
                    # Apply status filter - compare Status enum values
                    profile_matches_filter = False
                    for status in status_filter:
                        if status is None or (
                            hasattr(status, "value") and status.value is None
                        ):
                            # Filter includes None/CURRENT
                            if profile_obj.status is None:
                                profile_matches_filter = True
                                break
                        elif isinstance(status, Status):
                            # Compare enum values
                            if profile_obj.status == status:
                                profile_matches_filter = True
                                break
                        elif isinstance(status, str):
                            # Legacy string comparison
                            if (
                                profile_obj.status
                                and profile_obj.status.value == status
                            ):
                                profile_matches_filter = True
                                break

                    if profile_matches_filter:
                        profiles.append(profile_obj)

        # Sort by last_modified_timestamp in descending order and apply limit
        profiles = sorted(
            profiles, key=lambda x: x.last_modified_timestamp, reverse=True
        )
        return profiles[:limit]

    def get_all_interactions(self, limit: int = 100) -> list[Interaction]:
        with self._lock:
            all_memories = self._load()
        interactions = []
        for _, user_data in all_memories.items():
            if "interactions" in user_data:
                for interaction in user_data["interactions"]:
                    interactions.append(Interaction.model_validate_json(interaction))

        # Sort by created_at timestamp in descending order and apply limit
        interactions = sorted(interactions, key=lambda x: x.created_at, reverse=True)
        return interactions[:limit]

    def get_user_profile(
        self,
        user_id: str,
        status_filter: Optional[list[Optional[Status]]] = None,
    ) -> list[UserProfile]:
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        with self._lock:
            all_memories = self._load()
        if user_id not in all_memories or "profiles" not in all_memories[user_id]:
            logger.warning(
                "get_user_profile::User profile not found for user id: %s", user_id
            )
            return []

        profiles = []
        for profile in all_memories[user_id]["profiles"]:
            profile_obj = UserProfile.model_validate_json(profile)
            # Apply status filter - compare Status enum values
            profile_matches_filter = False
            for status in status_filter:
                if status is None or (
                    hasattr(status, "value") and status.value is None
                ):
                    # Filter includes None/CURRENT
                    if profile_obj.status is None:
                        profile_matches_filter = True
                        break
                elif isinstance(status, Status):
                    # Compare enum values
                    if profile_obj.status == status:
                        profile_matches_filter = True
                        break
                elif isinstance(status, str):
                    # Legacy string comparison
                    if profile_obj.status and profile_obj.status.value == status:
                        profile_matches_filter = True
                        break

            if profile_matches_filter:
                profiles.append(profile_obj)

        return profiles

    def get_user_interaction(self, user_id: str) -> list[Interaction]:
        with self._lock:
            all_memories = self._load()
        if user_id not in all_memories or "interactions" not in all_memories[user_id]:
            logger.warning(
                "get_user_interaction::User interaction not found for user id: %s",
                user_id,
            )
            return []

        interactions = all_memories[user_id]["interactions"]
        return [
            Interaction.model_validate_json(interaction_dict)
            for interaction_dict in interactions
        ]

    def add_user_profile(self, user_id: str, user_profiles: list[UserProfile]):
        with self._lock:
            all_memories = self._load()
            if user_id not in all_memories:
                all_memories[user_id] = {"profiles": []}

            if "profiles" not in all_memories[user_id]:
                all_memories[user_id]["profiles"] = []

            all_memories[user_id]["profiles"].extend(
                [profile.model_dump_json() for profile in user_profiles]
            )
            self._save(all_memories)

    def _get_next_interaction_id(self, all_memories: dict) -> int:
        """
        Get the next auto-increment interaction ID by finding max existing ID + 1.

        Args:
            all_memories: The full memory payload

        Returns:
            int: Next available interaction ID
        """
        max_id = 0
        for user_id, user_data in all_memories.items():
            if user_id.startswith("_"):  # Skip internal keys
                continue
            if not isinstance(
                user_data, dict
            ):  # Skip non-user-data entries like "requests"
                continue
            interactions = user_data.get("interactions", [])
            for interaction_json in interactions:
                try:
                    interaction = Interaction.model_validate_json(interaction_json)
                    if interaction.interaction_id > max_id:
                        max_id = interaction.interaction_id
                except Exception:
                    continue
        return max_id + 1

    def add_user_interaction(self, user_id: str, interaction: Interaction):
        with self._lock:
            all_memories = self._load()
            if user_id not in all_memories:
                all_memories[user_id] = {"interactions": []}
            if "interactions" not in all_memories[user_id]:
                all_memories[user_id]["interactions"] = []

            # Auto-generate interaction_id if not set (0 = placeholder)
            if interaction.interaction_id == 0:
                interaction.interaction_id = self._get_next_interaction_id(all_memories)

            all_memories[user_id]["interactions"].append(interaction.model_dump_json())
            self._save(all_memories)

    def add_user_interactions_bulk(
        self, user_id: str, interactions: list[Interaction]
    ) -> None:
        """
        Add multiple user interactions at once.

        For local JSON storage, embeddings are not used, so this simply adds
        all interactions in a single save operation.

        Args:
            user_id: The user ID
            interactions: List of interactions to add
        """
        if not interactions:
            return

        with self._lock:
            all_memories = self._load()
            if user_id not in all_memories:
                all_memories[user_id] = {"interactions": []}
            if "interactions" not in all_memories[user_id]:
                all_memories[user_id]["interactions"] = []

            for interaction in interactions:
                # Auto-generate interaction_id if not set (0 = placeholder)
                if interaction.interaction_id == 0:
                    interaction.interaction_id = self._get_next_interaction_id(
                        all_memories
                    )
                all_memories[user_id]["interactions"].append(
                    interaction.model_dump_json()
                )

            self._save(all_memories)

    def delete_user_interaction(self, request: DeleteUserInteractionRequest):
        with self._lock:
            all_memories = self._load()
            if (
                request.user_id not in all_memories
                or "interactions" not in all_memories[request.user_id]
            ):
                logger.warning(
                    "User interaction not found for user id: %s", request.user_id
                )
                return

            all_memories[request.user_id]["interactions"] = [
                interaction
                for interaction in all_memories[request.user_id]["interactions"]
                if Interaction.model_validate_json(interaction).interaction_id
                != request.interaction_id
            ]
            self._save(all_memories)

    def delete_user_profile(self, request: DeleteUserProfileRequest):
        with self._lock:
            all_memories = self._load()
            if (
                request.user_id not in all_memories
                or "profiles" not in all_memories[request.user_id]
            ):
                logger.warning(
                    "delete_user_profile::User profile not found for user id: %s",
                    request.user_id,
                )
                return

            all_memories[request.user_id]["profiles"] = [
                profile
                for profile in all_memories[request.user_id]["profiles"]
                if UserProfile.model_validate_json(profile).profile_id
                != request.profile_id
            ]
            self._save(all_memories)

    def update_user_profile_by_id(
        self, user_id: str, profile_id: str, new_profile: UserProfile
    ):
        with self._lock:
            all_memories = self._load()
            if user_id not in all_memories or "profiles" not in all_memories[user_id]:
                logger.warning(
                    "update_user_profile_by_id::User profile not found for user id: %s",
                    user_id,
                )
                return

            for i, profile in enumerate(all_memories[user_id]["profiles"]):
                profile_obj = UserProfile.model_validate_json(profile)
                if profile_obj.profile_id == profile_id:
                    all_memories[user_id]["profiles"][i] = new_profile.model_dump_json()
                    break
            self._save(all_memories)

    def delete_all_interactions_for_user(self, user_id: str):
        with self._lock:
            all_memories = self._load()
            if (
                user_id not in all_memories
                or "interactions" not in all_memories[user_id]
            ):
                logger.warning(
                    "delete_all_interactions_for_user::User interaction not found for user id: %s",
                    user_id,
                )
                return
            all_memories[user_id]["interactions"] = []
            self._save(all_memories)

    def delete_all_profiles_for_user(self, user_id: str):
        with self._lock:
            all_memories = self._load()
            if user_id not in all_memories or "profiles" not in all_memories[user_id]:
                logger.warning(
                    "delete_all_profiles_for_user::User profile not found for user id: %s",
                    user_id,
                )
                return
            all_memories[user_id]["profiles"] = []
            self._save(all_memories)

    def delete_all_profiles(self):
        """Delete all profiles across all users."""
        with self._lock:
            all_memories = self._load()
            for user_id in all_memories:
                if "profiles" in all_memories[user_id]:
                    all_memories[user_id]["profiles"] = []
            self._save(all_memories)

    def delete_all_interactions(self):
        """Delete all interactions across all users."""
        with self._lock:
            all_memories = self._load()
            for user_id in all_memories:
                if "interactions" in all_memories[user_id]:
                    all_memories[user_id]["interactions"] = []
            self._save(all_memories)

    def count_all_interactions(self) -> int:
        """
        Count total interactions across all users.

        Returns:
            int: Total number of interactions
        """
        all_memories = self._load()
        total = 0
        for user_data in all_memories.values():
            if isinstance(user_data, dict) and "interactions" in user_data:
                total += len(user_data["interactions"])
        return total

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

        with self._lock:
            all_memories = self._load()

            # Collect all interactions with user_id info
            all_interactions: list[tuple[str, Interaction]] = []
            for user_id, user_data in all_memories.items():
                if isinstance(user_data, dict) and "interactions" in user_data:
                    for interaction_json in user_data["interactions"]:
                        interaction = Interaction.model_validate_json(interaction_json)
                        all_interactions.append((user_id, interaction))

            if not all_interactions:
                return 0

            # Sort by created_at (oldest first)
            all_interactions.sort(key=lambda x: x[1].created_at or 0)

            # Get IDs to delete (oldest N)
            to_delete = all_interactions[:count]
            ids_to_delete = {(uid, i.interaction_id) for uid, i in to_delete}

            # Remove from each user
            for user_id, user_data in all_memories.items():
                if isinstance(user_data, dict) and "interactions" in user_data:
                    user_data["interactions"] = [
                        ij
                        for ij in user_data["interactions"]
                        if (
                            user_id,
                            Interaction.model_validate_json(ij).interaction_id,
                        )
                        not in ids_to_delete
                    ]

            self._save(all_memories)
            return len(to_delete)

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
        with self._lock:
            all_memories = self._load()
            updated_count = 0

            for user_id in all_memories:
                # Skip users not in the filter list
                if user_ids is not None and user_id not in user_ids:
                    continue

                if "profiles" not in all_memories[user_id]:
                    continue

                for i, profile_json in enumerate(all_memories[user_id]["profiles"]):
                    profile_obj = UserProfile.model_validate_json(profile_json)

                    # Check if profile matches old_status
                    status_matches = False
                    if old_status is None or (
                        hasattr(old_status, "value") and old_status.value is None
                    ):
                        # Looking for CURRENT profiles (status=None)
                        if profile_obj.status is None:
                            status_matches = True
                    elif isinstance(old_status, Status):
                        # Compare enum values
                        if profile_obj.status == old_status:
                            status_matches = True

                    if status_matches:
                        # Update the profile status and last modified timestamp
                        profile_obj.status = new_status
                        profile_obj.last_modified_timestamp = int(
                            datetime.now(timezone.utc).timestamp()
                        )
                        all_memories[user_id]["profiles"][
                            i
                        ] = profile_obj.model_dump_json()
                        updated_count += 1

            # Atomic save
            self._save(all_memories)
            logger.info(
                f"Updated {updated_count} profiles from {old_status} to {new_status}"
            )
            return updated_count

    def delete_all_profiles_by_status(self, status: Status) -> int:
        """
        Delete all profiles with the given status atomically.

        Args:
            status: The status of profiles to delete

        Returns:
            int: Number of profiles deleted
        """
        with self._lock:
            all_memories = self._load()
            deleted_count = 0

            for user_id in all_memories:
                if "profiles" not in all_memories[user_id]:
                    continue

                # Filter out profiles that match the status
                new_profiles = []
                for profile_json in all_memories[user_id]["profiles"]:
                    profile_obj = UserProfile.model_validate_json(profile_json)

                    # Check if profile matches the status to delete
                    should_delete = False
                    if isinstance(status, Status):
                        if profile_obj.status == status:
                            should_delete = True
                            deleted_count += 1

                    if not should_delete:
                        new_profiles.append(profile_json)

                all_memories[user_id]["profiles"] = new_profiles

            # Atomic save
            self._save(all_memories)
            logger.info(f"Deleted {deleted_count} profiles with status {status}")
            return deleted_count

    def get_user_ids_with_status(self, status: Optional[Status]) -> list[str]:
        """
        Get list of unique user_ids that have profiles with the given status.

        Args:
            status: The status to filter by (None for CURRENT)

        Returns:
            list[str]: List of unique user_ids
        """
        with self._lock:
            all_memories = self._load()
        user_ids_with_status = []

        for user_id in all_memories:
            if "profiles" not in all_memories[user_id]:
                continue

            for profile_json in all_memories[user_id]["profiles"]:
                profile_obj = UserProfile.model_validate_json(profile_json)

                # Check if profile matches the status
                status_matches = False
                if status is None or (
                    hasattr(status, "value") and status.value is None
                ):
                    # Looking for CURRENT profiles (status=None)
                    if profile_obj.status is None:
                        status_matches = True
                elif isinstance(status, Status):
                    # Compare enum values
                    if profile_obj.status == status:
                        status_matches = True

                if status_matches:
                    user_ids_with_status.append(user_id)
                    break  # Found a profile with this status for this user, move to next user

        return user_ids_with_status

    # ==============================
    # Request methods
    # ==============================

    def add_request(self, request: Request):
        """
        Add a request to storage.

        Args:
            request: Request object to store
        """
        with self._lock:
            all_memories = self._load()
            if "requests" not in all_memories:
                all_memories["requests"] = []

            # Check if request already exists and update it, otherwise append
            request_exists = False
            for i, existing_request_json in enumerate(all_memories["requests"]):
                existing_request = Request.model_validate_json(existing_request_json)
                if existing_request.request_id == request.request_id:
                    all_memories["requests"][i] = request.model_dump_json()
                    request_exists = True
                    break

            if not request_exists:
                all_memories["requests"].append(request.model_dump_json())

            self._save(all_memories)

    def get_request(self, request_id: str) -> Optional[Request]:
        """
        Get a request by its ID.

        Args:
            request_id: The request ID to retrieve

        Returns:
            Request object if found, None otherwise
        """
        with self._lock:
            all_memories = self._load()
        if "requests" not in all_memories:
            return None

        for request_json in all_memories["requests"]:
            request = Request.model_validate_json(request_json)
            if request.request_id == request_id:
                return request

        return None

    def delete_request(self, request_id: str):
        """
        Delete a request by its ID and all associated interactions.

        Args:
            request_id: The request ID to delete
        """
        with self._lock:
            all_memories = self._load()

            # First delete all interactions associated with this request
            for user_id in all_memories.keys():
                if "interactions" in all_memories[user_id]:
                    all_memories[user_id]["interactions"] = [
                        interaction_json
                        for interaction_json in all_memories[user_id]["interactions"]
                        if Interaction.model_validate_json(interaction_json).request_id
                        != request_id
                    ]

            # Then delete the request itself
            if "requests" not in all_memories:
                return

            all_memories["requests"] = [
                request_json
                for request_json in all_memories["requests"]
                if Request.model_validate_json(request_json).request_id != request_id
            ]
            self._save(all_memories)

    def delete_session(self, session_id: str) -> int:
        """
        Delete all requests and interactions in a session.

        Args:
            session_id: The session ID to delete

        Returns:
            int: Number of requests deleted
        """
        with self._lock:
            all_memories = self._load()

            # First get all request IDs in this session
            if "requests" not in all_memories:
                return 0

            request_ids = []
            for request_json in all_memories["requests"]:
                request = Request.model_validate_json(request_json)
                if request.session_id == session_id:
                    request_ids.append(request.request_id)

            if not request_ids:
                return 0

            # Delete all interactions for all requests in this session
            for user_id in all_memories.keys():
                if "interactions" in all_memories[user_id]:
                    all_memories[user_id]["interactions"] = [
                        interaction_json
                        for interaction_json in all_memories[user_id]["interactions"]
                        if Interaction.model_validate_json(interaction_json).request_id
                        not in request_ids
                    ]

            # Delete all requests in this session
            all_memories["requests"] = [
                request_json
                for request_json in all_memories["requests"]
                if Request.model_validate_json(request_json).session_id != session_id
            ]

            self._save(all_memories)
            return len(request_ids)

    def delete_all_requests(self):
        """Delete all requests and their associated interactions."""
        with self._lock:
            all_memories = self._load()

            # Delete all interactions
            for user_id in list(all_memories.keys()):
                if user_id != "requests" and "interactions" in all_memories[user_id]:
                    all_memories[user_id]["interactions"] = []

            # Delete all requests
            all_memories["requests"] = []

            self._save(all_memories)

    def get_requests_by_session(self, user_id: str, session_id: str) -> list[Request]:
        """
        Get all requests for a specific session.

        Args:
            user_id (str): User ID to filter requests
            session_id (str): Session ID to filter by

        Returns:
            list[Request]: List of Request objects in the session
        """
        with self._lock:
            all_memories = self._load()
        if "requests" not in all_memories:
            return []

        requests = []
        for request_json in all_memories["requests"]:
            request = Request.model_validate_json(request_json)
            if request.user_id == user_id and request.session_id == session_id:
                requests.append(request)

        return requests

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

        Returns:
            dict[str, list[RequestInteractionDataModel]]: Dictionary mapping session_id to list of RequestInteractionDataModel objects
        """
        with self._lock:
            all_memories = self._load()

        # Get all requests for the user
        if "requests" not in all_memories:
            return {}

        requests = []
        for request_json in all_memories["requests"]:
            req = Request.model_validate_json(request_json)

            # Filter by user_id if specified
            if user_id and req.user_id != user_id:
                continue

            # Filter by request_id if specified
            if request_id and req.request_id != request_id:
                continue

            # Filter by session_id if specified
            if session_id and req.session_id != session_id:
                continue

            # Filter by start_time if specified
            if start_time and req.created_at < start_time:
                continue

            # Filter by end_time if specified
            if end_time and req.created_at > end_time:
                continue

            requests.append(req)

        # Sort by created_at descending
        requests = sorted(requests, key=lambda x: x.created_at, reverse=True)

        # Apply offset and limit pagination on requests
        effective_limit = top_k or 100
        requests = requests[offset : offset + effective_limit]

        # Group requests by session_id first
        groups_dict = {}
        for req in requests:
            group_name = req.session_id if req.session_id else ""
            if group_name not in groups_dict:
                groups_dict[group_name] = []
            groups_dict[group_name].append(req)

        # Get all interactions - if user_id is specified, filter by user, otherwise get all
        if user_id:
            user_interactions = self.get_user_interaction(user_id)
        else:
            # Get interactions for all requests we're returning
            all_interactions_list = []
            if "interactions" in all_memories:
                for interaction_json in all_memories["interactions"]:
                    interaction = Interaction.model_validate_json(interaction_json)
                    # Only include interactions for requests we're returning
                    if any(
                        interaction.request_id == req.request_id
                        for group_requests in groups_dict.values()
                        for req in group_requests
                    ):
                        all_interactions_list.append(interaction)
            user_interactions = all_interactions_list

        # Group interactions by request_id
        interactions_by_request_id = {}
        for interaction in user_interactions:
            if interaction.request_id not in interactions_by_request_id:
                interactions_by_request_id[interaction.request_id] = []
            interactions_by_request_id[interaction.request_id].append(interaction)

        # Build grouped result
        grouped_results = {}
        for group_name, group_requests in groups_dict.items():
            grouped_results[group_name] = []
            for req in group_requests:
                associated_interactions = interactions_by_request_id.get(
                    req.request_id, []
                )
                # Sort interactions by created_at
                associated_interactions = sorted(
                    associated_interactions, key=lambda x: x.created_at
                )
                grouped_results[group_name].append(
                    RequestInteractionDataModel(
                        session_id=group_name,
                        request=req,
                        interactions=associated_interactions,
                    )
                )

        return grouped_results

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
        with self._lock:
            all_memories = self._load()

        if "requests" not in all_memories:
            return []

        user_ids: set[str] = set()
        for request_json in all_memories["requests"]:
            req = Request.model_validate_json(request_json)

            if user_id and req.user_id != user_id:
                continue
            if start_time and req.created_at < start_time:
                continue
            if end_time and req.created_at > end_time:
                continue
            if source and req.source != source:
                continue
            if agent_version and req.agent_version != agent_version:
                continue

            user_ids.add(req.user_id)

        return sorted(user_ids)

    # ==============================
    # Profile Change Log methods
    # ==============================

    def add_profile_change_log(self, profile_change_log: ProfileChangeLog):
        with self._lock:
            all_memories = self._load()
            if "profile_change_logs" not in all_memories:
                all_memories["profile_change_logs"] = []
            all_memories["profile_change_logs"].append(
                profile_change_log.model_dump_json()
            )
            self._save(all_memories)

    def get_profile_change_logs(self, limit: int = 100) -> list[ProfileChangeLog]:
        with self._lock:
            all_memories = self._load()
        if "profile_change_logs" not in all_memories:
            return []
        logs = []
        for log_json in all_memories["profile_change_logs"][:limit]:
            logs.append(ProfileChangeLog.model_validate_json(log_json))
        return logs

    def delete_profile_change_log_for_user(self, user_id: str):
        with self._lock:
            all_memories = self._load()
            if "profile_change_logs" not in all_memories:
                return
            all_memories["profile_change_logs"] = [
                log_json
                for log_json in all_memories["profile_change_logs"]
                if ProfileChangeLog.model_validate_json(log_json).user_id != user_id
            ]
            self._save(all_memories)

    def delete_all_profile_change_logs(self):
        with self._lock:
            all_memories = self._load()
            if "profile_change_logs" in all_memories:
                all_memories["profile_change_logs"] = []
                self._save(all_memories)

    # ==============================
    # Feedback Aggregation Change Log methods
    # ==============================

    def add_feedback_aggregation_change_log(
        self, change_log: FeedbackAggregationChangeLog
    ):
        with self._lock:
            all_memories = self._load()
            if "feedback_aggregation_change_logs" not in all_memories:
                all_memories["feedback_aggregation_change_logs"] = []
            all_memories["feedback_aggregation_change_logs"].append(
                change_log.model_dump_json()
            )
            self._save(all_memories)

    def get_feedback_aggregation_change_logs(
        self,
        feedback_name: str,
        agent_version: str,
        limit: int = 100,
    ) -> list[FeedbackAggregationChangeLog]:
        with self._lock:
            all_memories = self._load()
        if "feedback_aggregation_change_logs" not in all_memories:
            return []
        logs = []
        for log_json in all_memories["feedback_aggregation_change_logs"]:
            log = FeedbackAggregationChangeLog.model_validate_json(log_json)
            if (
                log.feedback_name == feedback_name
                and log.agent_version == agent_version
            ):
                logs.append(log)
        # Sort by created_at descending to match Supabase ordering
        logs.sort(key=lambda x: x.created_at, reverse=True)
        return logs[:limit]

    def delete_all_feedback_aggregation_change_logs(self):
        with self._lock:
            all_memories = self._load()
            if "feedback_aggregation_change_logs" in all_memories:
                all_memories["feedback_aggregation_change_logs"] = []
                self._save(all_memories)

    # ==============================
    # Search methods
    # ==============================

    def search_interaction(
        self, search_interaction_request: SearchInteractionRequest
    ) -> list[Interaction]:
        """Search user interaction from storage

        Args:
            search_interaction_request (SearchInteractionRequest): _description_

        Returns:
            list[Interaction]: _description_
        """
        interactions = self.get_user_interaction(search_interaction_request.user_id)
        if search_interaction_request.request_id:
            interactions = [
                interaction
                for interaction in interactions
                if interaction.request_id == search_interaction_request.request_id
            ]
        if search_interaction_request.query:
            interactions = [
                interaction
                for interaction in interactions
                if search_interaction_request.query in interaction.content
            ]
        if search_interaction_request.start_time:
            interactions = [
                interaction
                for interaction in interactions
                if interaction.created_at
                >= search_interaction_request.start_time.timestamp()
            ]
        if search_interaction_request.end_time:
            interactions = [
                interaction
                for interaction in interactions
                if interaction.created_at
                <= search_interaction_request.end_time.timestamp()
            ]

        return interactions

    def search_user_profile(
        self,
        search_user_profile_request: SearchUserProfileRequest,
        status_filter: Optional[list[Optional[Status]]] = None,
        query_embedding: Optional[list[float]] = None,
    ) -> list[UserProfile]:
        """Search user profile from storage

        Args:
            search_user_profile_request (SearchUserProfileRequest): _description_
            status_filter (Optional[list[Optional[Status]]]): Filter profiles by status

        Returns:
            list[UserProfile]: _description_
        """
        if status_filter is None:
            status_filter = [None]  # Default to current profiles (status=None)

        user_profiles = self.get_user_profile(
            search_user_profile_request.user_id, status_filter=status_filter
        )
        if search_user_profile_request.generated_from_request_id:
            user_profiles = [
                profile
                for profile in user_profiles
                if profile.generated_from_request_id
                == search_user_profile_request.generated_from_request_id
            ]
        if search_user_profile_request.query:
            user_profiles = [
                profile
                for profile in user_profiles
                if search_user_profile_request.query in profile.profile_content
            ]
        if search_user_profile_request.start_time:
            user_profiles = [
                profile
                for profile in user_profiles
                if profile.last_modified_timestamp
                >= search_user_profile_request.start_time.timestamp()
            ]
        if search_user_profile_request.end_time:
            user_profiles = [
                profile
                for profile in user_profiles
                if profile.last_modified_timestamp
                <= search_user_profile_request.end_time.timestamp()
            ]
        if search_user_profile_request.top_k:
            user_profiles = user_profiles[: search_user_profile_request.top_k]

        return user_profiles

    # ==============================
    # Raw feedback methods
    # ==============================

    def save_raw_feedbacks(self, raw_feedbacks: list[RawFeedback]):
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            all_memories["raw_feedbacks"] = []

        # Find the highest existing raw_feedback_id to auto-increment from
        max_id = 0
        for feedback_json in all_memories["raw_feedbacks"]:
            feedback = RawFeedback.model_validate_json(feedback_json)
            if feedback.raw_feedback_id > max_id:
                max_id = feedback.raw_feedback_id

        # Assign auto-incrementing IDs to new feedbacks (matching Supabase behavior)
        for i, feedback in enumerate(raw_feedbacks):
            if feedback.raw_feedback_id == 0:  # Only assign if not already set
                feedback.raw_feedback_id = max_id + i + 1

        all_memories["raw_feedbacks"].extend(
            [feedback.model_dump_json() for feedback in raw_feedbacks]
        )
        self._save(all_memories)

    def get_raw_feedbacks(
        self,
        limit: int = 100,
        user_id: Optional[str] = None,
        feedback_name: Optional[str] = None,
        agent_version: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        include_embedding: bool = False,
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
            include_embedding (bool): If True, include embedding vectors. Defaults to False.

        Returns:
            list[RawFeedback]: List of raw feedback objects
        """
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return []

        feedbacks = []
        for feedback_json in all_memories["raw_feedbacks"]:
            feedback = RawFeedback.model_validate_json(feedback_json)
            # If user_id is specified, filter by it
            if user_id is not None and feedback.user_id != user_id:
                continue
            # If feedback_name is specified, filter by it (skip if None or empty string)
            if feedback_name and feedback.feedback_name != feedback_name:
                continue
            # If agent_version is specified, filter by it
            if agent_version is not None and feedback.agent_version != agent_version:
                continue
            # If status_filter is specified, filter by it
            if status_filter is not None and feedback.status not in status_filter:
                continue
            # If start_time is specified, filter by it
            if start_time is not None and feedback.created_at < start_time:
                continue
            # If end_time is specified, filter by it
            if end_time is not None and feedback.created_at > end_time:
                continue
            feedbacks.append(feedback)
            if len(feedbacks) >= limit:
                break
        return feedbacks

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
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return 0

        count = 0
        for feedback_json in all_memories["raw_feedbacks"]:
            feedback = RawFeedback.model_validate_json(feedback_json)

            # Apply user_id filter if specified
            if user_id is not None and feedback.user_id != user_id:
                continue

            # Apply feedback_name filter if specified (skip if None or empty string)
            if feedback_name and feedback.feedback_name != feedback_name:
                continue

            # Apply min_raw_feedback_id filter if specified
            if (
                min_raw_feedback_id is not None
                and feedback.raw_feedback_id <= min_raw_feedback_id
            ):
                continue

            # Apply agent_version filter if specified
            if agent_version is not None and feedback.agent_version != agent_version:
                continue

            # Apply status filter if specified
            if status_filter is not None and feedback.status not in status_filter:
                continue

            count += 1

        return count

    def count_raw_feedbacks_by_session(self, session_id: str) -> int:
        """
        Count raw feedbacks linked to a session via request_id -> requests.session_id.

        Args:
            session_id (str): The session ID to count raw feedbacks for

        Returns:
            int: Count of raw feedbacks linked to the session
        """
        all_memories = self._load()

        # Get all request_ids for this session
        request_ids = set()
        for request_json in all_memories.get("requests", []):
            request = Request.model_validate_json(request_json)
            if request.session_id == session_id:
                request_ids.add(request.request_id)

        if not request_ids:
            return 0

        # Count raw feedbacks with those request_ids
        count = 0
        for feedback_json in all_memories.get("raw_feedbacks", []):
            feedback = RawFeedback.model_validate_json(feedback_json)
            if feedback.request_id in request_ids:
                count += 1

        return count

    def delete_all_raw_feedbacks(self):
        all_memories = self._load()
        if "raw_feedbacks" in all_memories:
            all_memories["raw_feedbacks"] = []
            self._save(all_memories)

    def delete_all_raw_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all raw feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        all_memories = self._load()
        if "raw_feedbacks" in all_memories:
            all_memories["raw_feedbacks"] = [
                feedback_json
                for feedback_json in all_memories["raw_feedbacks"]
                if not self._should_delete_feedback(
                    RawFeedback.model_validate_json(feedback_json),
                    feedback_name,
                    agent_version,
                )
            ]
            self._save(all_memories)

    def _should_delete_feedback(
        self, feedback, feedback_name: str, agent_version: Optional[str]
    ) -> bool:
        """Helper to determine if a feedback should be deleted."""
        if feedback.feedback_name != feedback_name:
            return False
        if agent_version is not None and feedback.agent_version != agent_version:
            return False
        return True

    def delete_all_feedbacks(self):
        all_memories = self._load()
        if "feedbacks" in all_memories:
            all_memories["feedbacks"] = []
            self._save(all_memories)

    def delete_feedback(self, feedback_id: int):
        """Delete a feedback by ID.

        Args:
            feedback_id (int): The ID of the feedback to delete
        """
        with self._lock:
            all_memories = self._load()
            if "feedbacks" not in all_memories:
                return
            all_memories["feedbacks"] = [
                feedback_json
                for feedback_json in all_memories["feedbacks"]
                if Feedback.model_validate_json(feedback_json).feedback_id
                != feedback_id
            ]
            self._save(all_memories)

    def delete_raw_feedback(self, raw_feedback_id: int):
        """Delete a raw feedback by ID.

        Args:
            raw_feedback_id (int): The ID of the raw feedback to delete
        """
        with self._lock:
            all_memories = self._load()
            if "raw_feedbacks" not in all_memories:
                return
            all_memories["raw_feedbacks"] = [
                feedback_json
                for feedback_json in all_memories["raw_feedbacks"]
                if RawFeedback.model_validate_json(feedback_json).raw_feedback_id
                != raw_feedback_id
            ]
            self._save(all_memories)

    def delete_all_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Delete all regular feedbacks by feedback name from storage.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        all_memories = self._load()
        if "feedbacks" in all_memories:
            all_memories["feedbacks"] = [
                feedback_json
                for feedback_json in all_memories["feedbacks"]
                if not self._should_delete_feedback(
                    Feedback.model_validate_json(feedback_json),
                    feedback_name,
                    agent_version,
                )
            ]
            self._save(all_memories)

    def save_feedbacks(self, feedbacks: list[Feedback]) -> list[Feedback]:
        """
        Save feedbacks to storage.

        Args:
            feedbacks (list[Feedback]): List of feedbacks to save

        Returns:
            list[Feedback]: Saved feedbacks with feedback_id populated
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            all_memories["feedbacks"] = []

        # Assign incremental feedback_ids for local storage
        existing_max_id = 0
        for fb_json in all_memories["feedbacks"]:
            fb = Feedback.model_validate_json(fb_json)
            if fb.feedback_id and fb.feedback_id > existing_max_id:
                existing_max_id = fb.feedback_id

        for i, feedback in enumerate(feedbacks):
            if not feedback.feedback_id:
                feedback.feedback_id = existing_max_id + i + 1

        all_memories["feedbacks"].extend(
            [feedback.model_dump_json() for feedback in feedbacks]
        )
        self._save(all_memories)
        return feedbacks

    def get_feedbacks(
        self,
        limit: int = 100,
        feedback_name: Optional[str] = None,
        status_filter: Optional[list[Optional[Status]]] = None,
        feedback_status_filter: Optional[list[FeedbackStatus]] = None,
    ) -> list[Feedback]:
        """
        Get feedbacks from storage.

        Args:
            limit (int): Maximum number of feedbacks to return
            feedback_name (str, optional): The feedback name to filter by. If None, returns all feedbacks.
            status_filter (list[Optional[Status]], optional): List of Status values to filter by. None in the list means CURRENT status.
            feedback_status_filter (Optional[list[FeedbackStatus]]): List of FeedbackStatus values to filter by.
                If None, returns all feedback statuses.

        Returns:
            list[Feedback]: List of feedback objects
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return []

        feedbacks = []
        for feedback_json in all_memories["feedbacks"]:
            feedback = Feedback.model_validate_json(feedback_json)

            # Apply status filter (for Status: CURRENT, ARCHIVED, PENDING, etc.)
            if status_filter is not None:
                if feedback.status not in status_filter:
                    continue
            else:
                # Default behavior: exclude archived (keep current feedbacks)
                if feedback.status == Status.ARCHIVED:
                    continue

            # Apply feedback_status filter (for FeedbackStatus: PENDING, APPROVED, REJECTED)
            # Only apply if specified; when None or empty, return all feedback statuses
            if (
                feedback_status_filter
                and feedback.feedback_status not in feedback_status_filter
            ):
                continue

            # If feedback_name is specified, filter by it (skip if None or empty string)
            if feedback_name and feedback.feedback_name != feedback_name:
                continue

            feedbacks.append(feedback)
            if len(feedbacks) >= limit:
                break
        return feedbacks

    def update_feedback_status(self, feedback_id: int, feedback_status: FeedbackStatus):
        """
        Update the status of a specific feedback.

        Args:
            feedback_id (int): The ID of the feedback to update
            feedback_status (FeedbackStatus): The new status to set

        Raises:
            ValueError: If feedback with the given ID is not found
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            raise ValueError(f"Feedback with ID {feedback_id} not found")

        feedbacks = all_memories["feedbacks"]
        feedback_found = False
        updated_feedbacks = []

        for feedback_json in feedbacks:
            feedback = Feedback.model_validate_json(feedback_json)
            if feedback.feedback_id == feedback_id:
                feedback.feedback_status = feedback_status
                feedback_found = True
            updated_feedbacks.append(feedback.model_dump_json())

        if not feedback_found:
            raise ValueError(f"Feedback with ID {feedback_id} not found")

        all_memories["feedbacks"] = updated_feedbacks
        self._save(all_memories)

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
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        updated_feedbacks = []
        for feedback_json in all_memories["feedbacks"]:
            feedback = Feedback.model_validate_json(feedback_json)
            # Only archive non-APPROVED feedbacks
            if (
                self._should_delete_feedback(feedback, feedback_name, agent_version)
                and feedback.feedback_status != FeedbackStatus.APPROVED
            ):
                feedback.status = "archived"
            updated_feedbacks.append(feedback.model_dump_json())

        all_memories["feedbacks"] = updated_feedbacks
        self._save(all_memories)

    def restore_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Restore archived feedbacks by setting their status field to null.

        Args:
            feedback_name (str): The feedback name to restore
            agent_version (str, optional): The agent version to filter by. If None, restores all agent versions.
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        updated_feedbacks = []
        for feedback_json in all_memories["feedbacks"]:
            feedback = Feedback.model_validate_json(feedback_json)
            if (
                self._should_delete_feedback(feedback, feedback_name, agent_version)
                and feedback.status == "archived"
            ):
                feedback.status = None
            updated_feedbacks.append(feedback.model_dump_json())

        all_memories["feedbacks"] = updated_feedbacks
        self._save(all_memories)

    def delete_archived_feedbacks_by_feedback_name(
        self, feedback_name: str, agent_version: Optional[str] = None
    ):
        """
        Permanently delete feedbacks that have status='archived'.

        Args:
            feedback_name (str): The feedback name to delete
            agent_version (str, optional): The agent version to filter by. If None, deletes all agent versions.
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        all_memories["feedbacks"] = [
            feedback_json
            for feedback_json in all_memories["feedbacks"]
            if not (
                self._should_delete_feedback(
                    Feedback.model_validate_json(feedback_json),
                    feedback_name,
                    agent_version,
                )
                and Feedback.model_validate_json(feedback_json).status == "archived"
            )
        ]
        self._save(all_memories)

    def archive_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Archive non-APPROVED feedbacks by IDs, setting their status field to 'archived'.
        APPROVED feedbacks are left untouched. No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to archive
        """
        if not feedback_ids:
            return
        feedback_id_set = set(feedback_ids)
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        updated_feedbacks = []
        for feedback_json in all_memories["feedbacks"]:
            feedback = Feedback.model_validate_json(feedback_json)
            if (
                feedback.feedback_id in feedback_id_set
                and feedback.feedback_status != FeedbackStatus.APPROVED
            ):
                feedback.status = "archived"
            updated_feedbacks.append(feedback.model_dump_json())

        all_memories["feedbacks"] = updated_feedbacks
        self._save(all_memories)

    def restore_archived_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Restore archived feedbacks by IDs, setting their status field to null.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to restore
        """
        if not feedback_ids:
            return
        feedback_id_set = set(feedback_ids)
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        updated_feedbacks = []
        for feedback_json in all_memories["feedbacks"]:
            feedback = Feedback.model_validate_json(feedback_json)
            if (
                feedback.feedback_id in feedback_id_set
                and feedback.status == "archived"
            ):
                feedback.status = None
            updated_feedbacks.append(feedback.model_dump_json())

        all_memories["feedbacks"] = updated_feedbacks
        self._save(all_memories)

    def delete_feedbacks_by_ids(self, feedback_ids: list[int]) -> None:
        """
        Permanently delete feedbacks by their IDs.
        No-op if feedback_ids is empty.

        Args:
            feedback_ids (list[int]): List of feedback IDs to delete
        """
        if not feedback_ids:
            return
        feedback_id_set = set(feedback_ids)
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return

        all_memories["feedbacks"] = [
            feedback_json
            for feedback_json in all_memories["feedbacks"]
            if Feedback.model_validate_json(feedback_json).feedback_id
            not in feedback_id_set
        ]
        self._save(all_memories)

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
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return 0

        updated_count = 0
        updated_feedbacks = []

        for feedback_json in all_memories["raw_feedbacks"]:
            feedback_obj = RawFeedback.model_validate_json(feedback_json)

            # Apply optional filters
            if (
                agent_version is not None
                and feedback_obj.agent_version != agent_version
            ):
                updated_feedbacks.append(feedback_json)
                continue
            if (
                feedback_name is not None
                and feedback_obj.feedback_name != feedback_name
            ):
                updated_feedbacks.append(feedback_json)
                continue

            # Check if feedback matches old_status
            status_matches = False
            if old_status is None or (
                hasattr(old_status, "value") and old_status.value is None
            ):
                # Looking for CURRENT raw feedbacks (status=None)
                if feedback_obj.status is None:
                    status_matches = True
            elif isinstance(old_status, Status):
                # Compare enum values
                if feedback_obj.status == old_status:
                    status_matches = True

            if status_matches:
                # Update the raw feedback status
                feedback_obj.status = new_status
                updated_feedbacks.append(feedback_obj.model_dump_json())
                updated_count += 1
            else:
                updated_feedbacks.append(feedback_json)

        all_memories["raw_feedbacks"] = updated_feedbacks
        self._save(all_memories)
        logger.info(
            f"Updated {updated_count} raw feedbacks from {old_status} to {new_status}"
        )
        return updated_count

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
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return 0

        deleted_count = 0
        new_feedbacks = []

        for feedback_json in all_memories["raw_feedbacks"]:
            feedback_obj = RawFeedback.model_validate_json(feedback_json)

            # Check if feedback matches the status to delete
            should_delete = False
            if isinstance(status, Status) and feedback_obj.status == status:
                # Apply optional filters
                if (
                    agent_version is not None
                    and feedback_obj.agent_version != agent_version
                ):
                    should_delete = False
                elif (
                    feedback_name is not None
                    and feedback_obj.feedback_name != feedback_name
                ):
                    should_delete = False
                else:
                    should_delete = True
                    deleted_count += 1

            if not should_delete:
                new_feedbacks.append(feedback_json)

        all_memories["raw_feedbacks"] = new_feedbacks
        self._save(all_memories)
        logger.info(f"Deleted {deleted_count} raw feedbacks with status {status}")
        return deleted_count

    def delete_raw_feedbacks_by_ids(self, raw_feedback_ids: list[int]) -> int:
        """Delete raw feedbacks by their IDs. No-op for local storage."""
        logger.warning("delete_raw_feedbacks_by_ids is not supported in local storage, skipping deletion of %d feedbacks", len(raw_feedback_ids))
        return 0

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
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return False

        for feedback_json in all_memories["raw_feedbacks"]:
            feedback_obj = RawFeedback.model_validate_json(feedback_json)

            # Apply optional filters
            if (
                agent_version is not None
                and feedback_obj.agent_version != agent_version
            ):
                continue
            if (
                feedback_name is not None
                and feedback_obj.feedback_name != feedback_name
            ):
                continue

            # Check if feedback matches the status
            status_matches = False
            if status is None or (hasattr(status, "value") and status.value is None):
                # Looking for CURRENT raw feedbacks (status=None)
                if feedback_obj.status is None:
                    status_matches = True
            elif isinstance(status, Status):
                # Compare enum values
                if feedback_obj.status == status:
                    status_matches = True

            if status_matches:
                return True

        return False

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
        Search raw feedbacks with advanced filtering (local storage uses text matching, not vector search).

        Args:
            query (str, optional): Text query for text search
            user_id (str, optional): Filter by user (resolved via request_id -> requests linkage)
            agent_version (str, optional): Filter by agent version
            feedback_name (str, optional): Filter by feedback name
            start_time (int, optional): Start timestamp (Unix) for created_at filter
            end_time (int, optional): End timestamp (Unix) for created_at filter
            status_filter (list[Optional[Status]], optional): List of status values to filter by
            match_threshold (float): Not used in local storage
            match_count (int): Maximum number of results to return

        Returns:
            list[RawFeedback]: List of matching raw feedback objects
        """
        all_memories = self._load()
        if "raw_feedbacks" not in all_memories:
            return []

        # Build request_id -> user_id map if user_id filter is provided
        request_user_map: dict[str, str] = {}
        if user_id:
            requests_data = all_memories.get("requests", {})
            for request_json in requests_data.values():
                req = Request.model_validate_json(request_json)
                request_user_map[req.request_id] = req.user_id

        results = []
        for feedback_json in all_memories["raw_feedbacks"]:
            rf = RawFeedback.model_validate_json(feedback_json)

            # Filter by user_id (via request_id)
            if user_id:
                req_user = request_user_map.get(rf.request_id)
                if req_user != user_id:
                    continue

            # Filter by query text
            if query and query.lower() not in rf.feedback_content.lower():
                continue

            # Filter by agent_version
            if agent_version and rf.agent_version != agent_version:
                continue

            # Filter by feedback_name
            if feedback_name and rf.feedback_name != feedback_name:
                continue

            # Filter by start_time
            if start_time and rf.created_at < start_time:
                continue

            # Filter by end_time
            if end_time and rf.created_at > end_time:
                continue

            # Filter by status
            if status_filter is not None:
                has_none = None in status_filter
                status_strings = [
                    s.value
                    for s in status_filter
                    if s is not None and hasattr(s, "value")
                ]
                rf_status_val = (
                    rf.status.value
                    if rf.status is not None and hasattr(rf.status, "value")
                    else rf.status
                )
                if has_none and rf.status is None:
                    pass  # Match
                elif rf_status_val in status_strings:
                    pass  # Match
                elif has_none and len(status_strings) == 0:
                    if rf.status is not None:
                        continue  # Only None allowed
                else:
                    continue  # No match

            results.append(rf)
            if len(results) >= match_count:
                break

        return results

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
        Search feedbacks with advanced filtering (local storage uses text matching, not vector search).

        Args:
            query (str, optional): Text query for text search
            agent_version (str, optional): Filter by agent version
            feedback_name (str, optional): Filter by feedback name
            start_time (int, optional): Start timestamp (Unix) for created_at filter
            end_time (int, optional): End timestamp (Unix) for created_at filter
            status_filter (list[Optional[Status]], optional): List of Status values to filter by
            feedback_status_filter (FeedbackStatus, optional): Filter by FeedbackStatus
            match_threshold (float): Not used in local storage
            match_count (int): Maximum number of results to return

        Returns:
            list[Feedback]: List of matching feedback objects
        """
        all_memories = self._load()
        if "feedbacks" not in all_memories:
            return []

        results = []
        for feedback_json in all_memories["feedbacks"]:
            f = Feedback.model_validate_json(feedback_json)

            # Filter by query text
            if query and query.lower() not in f.feedback_content.lower():
                continue

            # Filter by agent_version
            if agent_version and f.agent_version != agent_version:
                continue

            # Filter by feedback_name
            if feedback_name and f.feedback_name != feedback_name:
                continue

            # Filter by start_time
            if start_time and f.created_at < start_time:
                continue

            # Filter by end_time
            if end_time and f.created_at > end_time:
                continue

            # Filter by feedback_status
            if feedback_status_filter:
                f_status_val = (
                    f.feedback_status.value
                    if hasattr(f.feedback_status, "value")
                    else f.feedback_status
                )
                if f_status_val != feedback_status_filter.value:
                    continue

            # Filter by status
            if status_filter is not None:
                has_none = None in status_filter
                status_strings = [
                    s.value
                    for s in status_filter
                    if s is not None and hasattr(s, "value")
                ]
                f_status_val = (
                    f.status.value
                    if f.status is not None and hasattr(f.status, "value")
                    else f.status
                )
                if has_none and f.status is None:
                    pass  # Match
                elif f_status_val in status_strings:
                    pass  # Match
                elif has_none and len(status_strings) == 0:
                    if f.status is not None:
                        continue  # Only None allowed
                else:
                    continue  # No match

            results.append(f)
            if len(results) >= match_count:
                break

        return results

    # ==============================
    # Agent Success Evaluation methods
    # ==============================

    def save_agent_success_evaluation_results(
        self, results: list[AgentSuccessEvaluationResult]
    ):
        """
        Save agent success evaluation results to storage.

        Args:
            results (list[AgentSuccessEvaluationResult]): List of agent success evaluation result objects to save
        """
        all_memories = self._load()
        if "agent_success_evaluation_results" not in all_memories:
            all_memories["agent_success_evaluation_results"] = []
        all_memories["agent_success_evaluation_results"].extend(
            [result.model_dump_json() for result in results]
        )
        self._save(all_memories)

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
        all_memories = self._load()
        if "agent_success_evaluation_results" not in all_memories:
            return []

        results = []
        for result_json in all_memories["agent_success_evaluation_results"]:
            result = AgentSuccessEvaluationResult.model_validate_json(result_json)
            # If agent_version is specified, filter by it
            if agent_version is not None and result.agent_version != agent_version:
                continue
            results.append(result)
            if len(results) >= limit:
                break
        return results

    def delete_all_agent_success_evaluation_results(self):
        """Delete all agent success evaluation results from storage."""
        all_memories = self._load()
        if "agent_success_evaluation_results" in all_memories:
            all_memories["agent_success_evaluation_results"] = []
            self._save(all_memories)

    # ==============================
    # Dashboard methods
    # ==============================

    def get_dashboard_stats(self, days_back: int = 30) -> dict:
        """
        Get comprehensive dashboard statistics including counts and time-series data.
        Returns raw ungrouped time-series data for frontend grouping.

        Args:
            days_back (int): Number of days to include in time series data

        Returns:
            dict: Dictionary containing current_period, previous_period, and raw time_series data
        """
        all_memories = self._load()
        current_time = int(datetime.now(timezone.utc).timestamp())

        # Calculate time boundaries
        seconds_in_period = days_back * 24 * 60 * 60
        current_period_start = current_time - seconds_in_period
        previous_period_start = current_period_start - seconds_in_period

        # Initialize counters
        current_stats = {
            "total_profiles": 0,
            "total_interactions": 0,
            "total_feedbacks": 0,
            "success_rate": 0.0,
        }
        previous_stats = {
            "total_profiles": 0,
            "total_interactions": 0,
            "total_feedbacks": 0,
            "success_rate": 0.0,
        }

        # Time series data structures - store raw data points
        interactions_ts = []
        profiles_ts = []
        feedbacks_ts = []
        evaluations_ts = []

        # Process interactions (interactions are stored under each user bucket)
        for user_id, user_data in all_memories.items():
            if isinstance(user_data, dict) and "interactions" in user_data:
                for interaction_json in user_data["interactions"]:
                    interaction = Interaction.model_validate_json(interaction_json)
                    timestamp = interaction.created_at

                    # Count for periods
                    if timestamp >= current_period_start:
                        current_stats["total_interactions"] += 1
                        # Add raw timestamp for time series
                        interactions_ts.append({"timestamp": timestamp, "value": 1})
                    elif timestamp >= previous_period_start:
                        previous_stats["total_interactions"] += 1

        # Process profiles (profiles are stored under each user bucket)
        for user_id, user_data in all_memories.items():
            if isinstance(user_data, dict) and "profiles" in user_data:
                for profile_json in user_data["profiles"]:
                    profile = UserProfile.model_validate_json(profile_json)
                    timestamp = profile.last_modified_timestamp

                    # Count for periods
                    if timestamp >= current_period_start:
                        current_stats["total_profiles"] += 1
                        # Add raw timestamp for time series
                        profiles_ts.append({"timestamp": timestamp, "value": 1})
                    elif timestamp >= previous_period_start:
                        previous_stats["total_profiles"] += 1

        # Process feedbacks (both raw and aggregated)
        raw_feedback_count_current = 0
        raw_feedback_count_previous = 0
        if "raw_feedbacks" in all_memories:
            for feedback_json in all_memories["raw_feedbacks"]:
                feedback = RawFeedback.model_validate_json(feedback_json)
                timestamp = feedback.created_at

                if timestamp >= current_period_start:
                    raw_feedback_count_current += 1
                    # Add raw timestamp for time series
                    feedbacks_ts.append({"timestamp": timestamp, "value": 1})
                elif timestamp >= previous_period_start:
                    raw_feedback_count_previous += 1

        aggregated_feedback_count_current = 0
        aggregated_feedback_count_previous = 0
        if "feedbacks" in all_memories:
            for feedback_json in all_memories["feedbacks"]:
                feedback = Feedback.model_validate_json(feedback_json)
                timestamp = feedback.created_at

                if timestamp >= current_period_start:
                    aggregated_feedback_count_current += 1
                elif timestamp >= previous_period_start:
                    aggregated_feedback_count_previous += 1

        current_stats["total_feedbacks"] = (
            raw_feedback_count_current + aggregated_feedback_count_current
        )
        previous_stats["total_feedbacks"] = (
            raw_feedback_count_previous + aggregated_feedback_count_previous
        )

        # Process agent success evaluations
        success_count_current = 0
        total_eval_current = 0
        success_count_previous = 0
        total_eval_previous = 0

        if "agent_success_evaluation_results" in all_memories:
            for result_json in all_memories["agent_success_evaluation_results"]:
                result = AgentSuccessEvaluationResult.model_validate_json(result_json)
                timestamp = result.created_at

                if timestamp >= current_period_start:
                    total_eval_current += 1
                    if result.is_success:
                        success_count_current += 1

                    # Add raw timestamp with success rate value
                    success_value = 100 if result.is_success else 0
                    evaluations_ts.append(
                        {"timestamp": timestamp, "value": success_value}
                    )

                elif timestamp >= previous_period_start:
                    total_eval_previous += 1
                    if result.is_success:
                        success_count_previous += 1

        # Calculate success rates
        current_stats["success_rate"] = (
            (success_count_current / total_eval_current * 100)
            if total_eval_current > 0
            else 0.0
        )
        previous_stats["success_rate"] = (
            (success_count_previous / total_eval_previous * 100)
            if total_eval_previous > 0
            else 0.0
        )

        # Return raw time series data (frontend will group by granularity)
        return {
            "current_period": current_stats,
            "previous_period": previous_stats,
            "interactions_time_series": sorted(
                interactions_ts, key=lambda x: x["timestamp"]
            ),
            "profiles_time_series": sorted(profiles_ts, key=lambda x: x["timestamp"]),
            "feedbacks_time_series": sorted(feedbacks_ts, key=lambda x: x["timestamp"]),
            "evaluations_time_series": sorted(
                evaluations_ts, key=lambda x: x["timestamp"]
            ),
        }

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

    def create_operation_state(self, service_name: str, operation_state: dict):
        """
        Create operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        with self._lock:
            all_memories, operation_states = self._load_operation_states()
            if service_name in operation_states:
                raise StorageError(
                    f"Operation state already exists for service '{service_name}'"
                )

            operation_states[service_name] = {
                "service_name": service_name,
                "operation_state": operation_state,
                "updated_at": self._current_timestamp(),
            }
            self._save(all_memories)

    def upsert_operation_state(self, service_name: str, operation_state: dict):
        """
        Create or update operation state for a service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        with self._lock:
            all_memories, operation_states = self._load_operation_states()
            if service_name in operation_states:
                operation_states[service_name]["operation_state"] = operation_state
                operation_states[service_name]["updated_at"] = self._current_timestamp()
            else:
                operation_states[service_name] = {
                    "service_name": service_name,
                    "operation_state": operation_state,
                    "updated_at": self._current_timestamp(),
                }
            self._save(all_memories)

    def get_operation_state(self, service_name: str) -> Optional[dict]:
        """
        Get operation state for a specific service.

        Args:
            service_name (str): Name of the service

        Returns:
            Optional[dict]: Operation state data or None if not found
        """
        all_memories = self._load()
        if "operation_states" not in all_memories:
            return None
        return all_memories["operation_states"].get(service_name)

    # Reserved keys that are not user buckets
    _SYSTEM_KEYS = {
        "operation_states",
        "requests",
        "profile_change_logs",
        "feedback_aggregation_change_logs",
        "raw_feedbacks",
        "feedbacks",
        "agent_success_evaluation_results",
        "interactions",
    }

    def _get_user_ids(self, all_memories: dict) -> list[str]:
        """
        Get all user IDs from the storage (excluding system keys).

        Args:
            all_memories: The loaded memories dict

        Returns:
            list[str]: List of user IDs
        """
        return [key for key in all_memories.keys() if key not in self._SYSTEM_KEYS]

    def get_operation_state_with_new_request_interaction(
        self,
        service_name: str,
        user_id: Optional[str],
        sources: Optional[list[str]] = None,
    ) -> tuple[dict, list[RequestInteractionDataModel]]:
        """
        Retrieve operation state payload and interactions since last processing,
        grouped by request.

        Args:
            service_name (str): Name of the service
            user_id (Optional[str]): User identifier to filter interactions.
                If None, returns interactions across all users.
            sources (Optional[list[str]]): Optional list of sources to filter interactions by

        Returns:
            tuple[dict, list[RequestInteractionDataModel]]: Operation state payload and list of
                RequestInteractionDataModel objects containing new interactions grouped by request
        """
        with self._lock:
            all_memories = self._load()
        operation_states = all_memories.get("operation_states", {})
        state_entry = operation_states.get(service_name)
        operation_state: dict = state_entry if isinstance(state_entry, dict) else {}

        last_processed_ids = operation_state.get("last_processed_interaction_ids") or []
        if not isinstance(last_processed_ids, list):
            last_processed_ids = []
        processed_set = {str(item) for item in last_processed_ids}

        last_processed_timestamp = operation_state.get("last_processed_timestamp")
        if not isinstance(last_processed_timestamp, int):
            last_processed_timestamp = None

        # Get interaction payloads from specified user or all users
        all_interaction_payloads: list[tuple[str, str]] = (
            []
        )  # (user_id, interaction_json)
        if user_id is not None:
            user_bucket = all_memories.get(user_id, {})
            for interaction_json in user_bucket.get("interactions", []):
                all_interaction_payloads.append((user_id, interaction_json))
        else:
            # Get interactions from all users
            for uid in self._get_user_ids(all_memories):
                user_bucket = all_memories.get(uid, {})
                for interaction_json in user_bucket.get("interactions", []):
                    all_interaction_payloads.append((uid, interaction_json))

        # Collect new interactions
        new_interactions: list[Interaction] = []
        for _, interaction_json in all_interaction_payloads:
            interaction = Interaction.model_validate_json(interaction_json)
            created_at = interaction.created_at
            if last_processed_timestamp is not None and created_at is not None:
                if created_at > last_processed_timestamp:
                    new_interactions.append(interaction)
                    continue
                if (
                    created_at == last_processed_timestamp
                    and interaction.interaction_id not in processed_set
                ):
                    new_interactions.append(interaction)
                    continue
            elif interaction.interaction_id not in processed_set:
                new_interactions.append(interaction)

        new_interactions.sort(key=lambda item: item.created_at or 0)

        # Group interactions by request_id
        interactions_by_request: dict[str, list[Interaction]] = {}
        for interaction in new_interactions:
            request_id = interaction.request_id
            if request_id not in interactions_by_request:
                interactions_by_request[request_id] = []
            interactions_by_request[request_id].append(interaction)

        # Build RequestInteractionDataModel objects
        sessions: list[RequestInteractionDataModel] = []
        for request_id, interactions in interactions_by_request.items():
            # Fetch the Request object
            request = self.get_request(request_id)
            if request is None:
                # Create a minimal Request if not found
                # Use interaction's user_id since we may be aggregating across users
                request = Request(
                    request_id=request_id,
                    user_id=(
                        interactions[0].user_id if interactions else (user_id or "")
                    ),
                    created_at=interactions[0].created_at if interactions else 0,
                )

            # Filter by sources if specified
            if sources is not None and request.source not in sources:
                continue

            # Use session_id from Request, or request_id as fallback
            group_name = request.session_id or request_id

            sessions.append(
                RequestInteractionDataModel(
                    session_id=group_name,
                    request=request,
                    interactions=interactions,
                )
            )

        # Sort by the earliest interaction timestamp in each group
        sessions.sort(
            key=lambda g: (
                min(i.created_at or 0 for i in g.interactions) if g.interactions else 0
            )
        )

        return operation_state, sessions

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
        Get the last K interactions ordered by interaction_id (most recent first), grouped by request.

        Args:
            user_id (Optional[str]): User identifier to filter interactions.
                If None, returns interactions across all users.
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
                - Flat list of all interactions sorted by interaction_id DESC
        """
        with self._lock:
            all_memories = self._load()

        # Get interaction payloads from specified user or all users
        interaction_payloads: list[str] = []
        if user_id is not None:
            user_bucket = all_memories.get(user_id, {})
            interaction_payloads = user_bucket.get("interactions", [])
        else:
            # Get interactions from all users
            for uid in self._get_user_ids(all_memories):
                user_bucket = all_memories.get(uid, {})
                interaction_payloads.extend(user_bucket.get("interactions", []))

        # Parse all interactions and sort by interaction_id DESC (preserves insertion order)
        all_interactions: list[Interaction] = []
        for interaction_json in interaction_payloads:
            interaction = Interaction.model_validate_json(interaction_json)
            all_interactions.append(interaction)

        all_interactions.sort(key=lambda x: x.interaction_id or 0, reverse=True)

        # Filter by source and time range if specified, and take first K interactions
        flat_interactions: list[Interaction] = []
        for interaction in all_interactions:
            if len(flat_interactions) >= k:
                break
            # Check time range filter if specified
            if start_time is not None:
                if (
                    interaction.created_at is None
                    or interaction.created_at < start_time
                ):
                    continue
            if end_time is not None:
                if interaction.created_at is None or interaction.created_at > end_time:
                    continue
            # Check source or agent_version filter if specified
            if sources is not None or agent_version is not None:
                request = self.get_request(interaction.request_id)
                if sources is not None:
                    if request is None or request.source not in sources:
                        continue
                if agent_version is not None:
                    if request is None or request.agent_version != agent_version:
                        continue
            flat_interactions.append(interaction)

        # Group by request_id
        interactions_by_request: dict[str, list[Interaction]] = {}
        for interaction in flat_interactions:
            request_id = interaction.request_id
            if request_id not in interactions_by_request:
                interactions_by_request[request_id] = []
            interactions_by_request[request_id].append(interaction)

        # Build RequestInteractionDataModel objects
        sessions: list[RequestInteractionDataModel] = []
        for request_id, interactions in interactions_by_request.items():
            # Fetch the Request object
            request = self.get_request(request_id)
            if request is None:
                # Create a minimal Request if not found
                # Use interaction's user_id since we may be aggregating across users
                request = Request(
                    request_id=request_id,
                    user_id=(
                        interactions[0].user_id if interactions else (user_id or "")
                    ),
                    created_at=interactions[0].created_at if interactions else 0,
                )

            # Use session_id from Request, or request_id as fallback
            group_name = request.session_id or request_id

            # Sort interactions by interaction_id ASC within the group (preserves insertion order)
            interactions_sorted = sorted(
                interactions, key=lambda x: x.interaction_id or 0
            )

            sessions.append(
                RequestInteractionDataModel(
                    session_id=group_name,
                    request=request,
                    interactions=interactions_sorted,
                )
            )

        # Sort groups by earliest interaction_id (preserves insertion order)
        sessions.sort(
            key=lambda g: (
                min(i.interaction_id or 0 for i in g.interactions)
                if g.interactions
                else 0
            )
        )

        return sessions, flat_interactions

    def update_operation_state(self, service_name: str, operation_state: dict):
        """
        Update operation state for a specific service.

        Args:
            service_name (str): Name of the service
            operation_state (dict): Operation state data as a dictionary
        """
        all_memories, operation_states = self._load_operation_states()
        if service_name not in operation_states:
            raise StorageError(
                f"Operation state does not exist for service '{service_name}'"
            )

        operation_states[service_name]["operation_state"] = operation_state
        operation_states[service_name]["updated_at"] = self._current_timestamp()
        self._save(all_memories)

    def get_all_operation_states(self) -> list[dict]:
        """
        Get all operation states.

        Returns:
            list[dict]: List of all operation state records
        """
        all_memories = self._load()
        if "operation_states" not in all_memories:
            return []
        return list(all_memories["operation_states"].values())

    def delete_operation_state(self, service_name: str):
        """
        Delete operation state for a specific service.

        Args:
            service_name (str): Name of the service
        """
        all_memories = self._load()
        if "operation_states" in all_memories:
            all_memories["operation_states"].pop(service_name, None)
            self._save(all_memories)

    def delete_all_operation_states(self):
        """Delete all operation states."""
        all_memories = self._load()
        all_memories["operation_states"] = {}
        self._save(all_memories)

    def try_acquire_in_progress_lock(
        self, state_key: str, request_id: str, stale_lock_seconds: int = 300
    ) -> dict:
        """
        Atomically try to acquire an in-progress lock using threading lock.

        This method uses a class-level threading lock to ensure atomicity for
        file-based storage. It either:
        1. Acquires the lock if no active lock exists (or lock is stale)
        2. Updates pending_request_id if an active lock is held by another request

        Args:
            state_key (str): The operation state key (e.g., "profile_generation_in_progress::3::user_id")
            request_id (str): The current request's unique identifier
            stale_lock_seconds (int): Seconds after which a lock is considered stale (default 300)

        Returns:
            dict: Result with keys:
                - 'acquired' (bool): True if lock was acquired, False if blocked
                - 'state' (dict): The current operation state after the operation
        """
        current_time = int(time.time())

        with self._lock:
            all_memories, operation_states = self._load_operation_states()
            state_entry = operation_states.get(state_key)

            # Extract operation_state from the entry if it exists
            if state_entry and isinstance(state_entry, dict):
                current_state = state_entry.get("operation_state", {})
            else:
                current_state = {}

            in_progress = current_state.get("in_progress", False)
            started_at = current_state.get("started_at", 0)

            # Case 1: No lock or lock is not in_progress - acquire it
            # Case 2: Lock is stale (started > stale_lock_seconds ago) - acquire it
            if not in_progress or (current_time - started_at >= stale_lock_seconds):
                new_state = {
                    "in_progress": True,
                    "started_at": current_time,
                    "current_request_id": request_id,
                    "pending_request_id": None,
                }
                operation_states[state_key] = {
                    "service_name": state_key,
                    "operation_state": new_state,
                    "updated_at": self._current_timestamp(),
                }
                self._save(all_memories)
                return {"acquired": True, "state": new_state}

            # Case 3: Active lock exists - update pending_request_id
            current_state["pending_request_id"] = request_id
            operation_states[state_key] = {
                "service_name": state_key,
                "operation_state": current_state,
                "updated_at": self._current_timestamp(),
            }
            self._save(all_memories)
            return {"acquired": False, "state": current_state}

    # ==============================
    # Statistics methods
    # ==============================

    def get_profile_statistics(self) -> dict:
        """Get profile count statistics by status.

        Returns:
            dict with keys: current_count, pending_count, archived_count, expiring_soon_count
        """
        all_memories = self._load()
        current_timestamp = int(datetime.now(timezone.utc).timestamp())
        expiring_soon_timestamp = current_timestamp + (7 * 24 * 60 * 60)  # 7 days

        stats = {
            "current_count": 0,
            "pending_count": 0,
            "archived_count": 0,
            "expiring_soon_count": 0,
        }

        for user_id, user_data in all_memories.items():
            if isinstance(user_data, dict) and "profiles" in user_data:
                for profile_json in user_data["profiles"]:
                    profile = UserProfile.model_validate_json(profile_json)

                    # Count by status
                    if profile.status is None:
                        stats["current_count"] += 1
                    elif profile.status == Status.PENDING:
                        stats["pending_count"] += 1
                    elif profile.status == Status.ARCHIVED:
                        stats["archived_count"] += 1

                    # Count expiring soon (current profiles only, not expired)
                    if (
                        profile.status is None
                        and profile.expiration_timestamp > current_timestamp
                        and profile.expiration_timestamp <= expiring_soon_timestamp
                    ):
                        stats["expiring_soon_count"] += 1

        return stats

    # ==============================
    # Skill methods (stubs)
    # ==============================

    def _next_skill_id(self, all_memories: dict) -> int:
        """Get next available skill_id by finding the max existing ID."""
        max_id = 0
        for skill_json in all_memories.get("skills", []):
            s = Skill.model_validate_json(skill_json)
            if s.skill_id > max_id:
                max_id = s.skill_id
        return max_id + 1

    def save_skills(self, skills: list[Skill]):
        all_memories = self._load()
        if "skills" not in all_memories:
            all_memories["skills"] = []

        for skill in skills:
            if skill.skill_id:
                # Update existing skill: replace in-place
                all_memories["skills"] = [
                    (
                        skill.model_dump_json()
                        if Skill.model_validate_json(sj).skill_id == skill.skill_id
                        else sj
                    )
                    for sj in all_memories["skills"]
                ]
            else:
                # New skill: assign auto-incrementing ID
                skill.skill_id = self._next_skill_id(all_memories)
                all_memories["skills"].append(skill.model_dump_json())

        self._save(all_memories)

    def get_skills(
        self,
        limit: int = 100,
        feedback_name: Optional[str] = None,
        agent_version: Optional[str] = None,
        skill_status: Optional[SkillStatus] = None,
    ) -> list[Skill]:
        all_memories = self._load()
        if "skills" not in all_memories:
            return []

        results = []
        for skill_json in all_memories["skills"]:
            s = Skill.model_validate_json(skill_json)
            if feedback_name and s.feedback_name != feedback_name:
                continue
            if agent_version and s.agent_version != agent_version:
                continue
            if skill_status and s.skill_status != skill_status:
                continue
            results.append(s)
            if len(results) >= limit:
                break
        return results

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
        all_memories = self._load()
        if "skills" not in all_memories:
            return []

        results = []
        for skill_json in all_memories["skills"]:
            s = Skill.model_validate_json(skill_json)
            if query and query.lower() not in (s.instructions + s.description).lower():
                continue
            if feedback_name and s.feedback_name != feedback_name:
                continue
            if agent_version and s.agent_version != agent_version:
                continue
            if skill_status and s.skill_status != skill_status:
                continue
            results.append(s)
            if len(results) >= match_count:
                break
        return results

    def update_skill_status(self, skill_id: int, skill_status: SkillStatus):
        all_memories = self._load()
        if "skills" not in all_memories:
            return
        updated_skills = []
        for skill_json in all_memories["skills"]:
            s = Skill.model_validate_json(skill_json)
            if s.skill_id == skill_id:
                s.skill_status = skill_status
            updated_skills.append(s.model_dump_json())
        all_memories["skills"] = updated_skills
        self._save(all_memories)

    def delete_skill(self, skill_id: int):
        all_memories = self._load()
        if "skills" not in all_memories:
            return
        all_memories["skills"] = [
            skill_json
            for skill_json in all_memories["skills"]
            if Skill.model_validate_json(skill_json).skill_id != skill_id
        ]
        self._save(all_memories)

    def delete_all_skills(self):
        """Delete all skills for this organization."""
        all_memories = self._load()
        all_memories["skills"] = []
        self._save(all_memories)

    def get_interactions_by_request_ids(
        self, request_ids: list[str]
    ) -> list[Interaction]:
        if not request_ids:
            return []
        all_memories = self._load()
        results = []
        for user_data in all_memories.values():
            if isinstance(user_data, dict) and "interactions" in user_data:
                for interaction_json in user_data["interactions"]:
                    interaction = Interaction.model_validate_json(interaction_json)
                    if interaction.request_id in request_ids:
                        results.append(interaction)
        return results
