from __future__ import annotations

from reflexio_commons.api_schema.retriever_schema import (
    GetProfileStatisticsResponse,
    GetUserProfilesRequest,
    GetUserProfilesResponse,
    SearchUserProfileRequest,
    SearchUserProfileResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    BulkDeleteResponse,
    DeleteProfilesByIdsRequest,
    DeleteUserProfileRequest,
    DeleteUserProfileResponse,
    DowngradeProfilesRequest,
    DowngradeProfilesResponse,
    ProfileChangeLogResponse,
    Status,
    UpgradeProfilesRequest,
    UpgradeProfilesResponse,
)

from reflexio.reflexio_lib._base import (
    STORAGE_NOT_CONFIGURED_MSG,
    ReflexioBase,
    _require_storage,
)
from reflexio.server.services.profile.profile_generation_service import (
    ProfileGenerationService,
)


class ProfilesMixin(ReflexioBase):
    def search_profiles(
        self,
        request: SearchUserProfileRequest | dict,
        status_filter: list[Status | None] | None = None,
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
        profiles = self._get_storage().search_user_profile(
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
        changelogs = self._get_storage().get_profile_change_logs()
        return ProfileChangeLogResponse(success=True, profile_change_logs=changelogs)

    @_require_storage(DeleteUserProfileResponse)
    def delete_profile(
        self,
        request: DeleteUserProfileRequest | dict,
    ) -> DeleteUserProfileResponse:
        """Delete user profiles.

        Args:
            request (DeleteUserProfileRequest): The delete request

        Returns:
            DeleteUserProfileResponse: Response containing success status and message
        """
        if isinstance(request, dict):
            request = DeleteUserProfileRequest(**request)
        self._get_storage().delete_user_profile(request)
        return DeleteUserProfileResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_all_profiles_bulk(self) -> BulkDeleteResponse:
        """Delete all profiles.

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        self._get_storage().delete_all_profiles()
        return BulkDeleteResponse(success=True)

    @_require_storage(BulkDeleteResponse)
    def delete_profiles_by_ids(
        self,
        request: DeleteProfilesByIdsRequest | dict,
    ) -> BulkDeleteResponse:
        """Delete profiles by their IDs.

        Args:
            request (DeleteProfilesByIdsRequest): The delete request containing profile_ids

        Returns:
            BulkDeleteResponse: Response containing success status and deleted count
        """
        if isinstance(request, dict):
            request = DeleteProfilesByIdsRequest(**request)
        deleted = self._get_storage().delete_profiles_by_ids(request.profile_ids)
        return BulkDeleteResponse(success=True, deleted_count=deleted)

    def get_profiles(
        self,
        request: GetUserProfilesRequest | dict,
        status_filter: list[Status | None] | None = None,
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

        profiles = self._get_storage().get_user_profile(
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
        status_filter: list[Status | None] | None = None,
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
        profiles = self._get_storage().get_all_profiles(
            limit=limit, status_filter=status_filter
        )
        profiles = sorted(
            profiles, key=lambda x: x.last_modified_timestamp, reverse=True
        )
        return GetUserProfilesResponse(success=True, user_profiles=profiles)

    def upgrade_all_profiles(
        self,
        request: UpgradeProfilesRequest | dict | None = None,
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
        return service.run_upgrade(request)  # type: ignore[reportArgumentType]

    def downgrade_all_profiles(
        self,
        request: DowngradeProfilesRequest | dict | None = None,
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
        return service.run_downgrade(request)  # type: ignore[reportArgumentType]

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
            stats = self._get_storage().get_profile_statistics()
            return GetProfileStatisticsResponse(success=True, **stats)
        except Exception as e:
            return GetProfileStatisticsResponse(
                success=False, msg=f"Failed to get profile statistics: {str(e)}"
            )
