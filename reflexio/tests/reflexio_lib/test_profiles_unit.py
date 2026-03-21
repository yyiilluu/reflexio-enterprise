"""Unit tests for ProfilesMixin.

Tests get_profiles, get_all_profiles, search_profiles, delete_profile,
delete_all_profiles_bulk, delete_profiles_by_ids, get_profile_change_logs,
get_profile_statistics, upgrade_all_profiles, and downgrade_all_profiles
with mocked storage and services.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.retriever_schema import (
    GetUserProfilesRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    DeleteProfilesByIdsRequest,
    DeleteUserProfileRequest,
    DowngradeProfilesRequest,
    DowngradeProfilesResponse,
    ProfileChangeLog,
    Status,
    UpgradeProfilesRequest,
    UpgradeProfilesResponse,
    UserProfile,
)

from reflexio.reflexio_lib._profiles import ProfilesMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin(*, storage_configured: bool = True) -> ProfilesMixin:
    """Create a ProfilesMixin instance with mocked internals."""
    mixin = object.__new__(ProfilesMixin)
    mock_storage = MagicMock()

    mock_request_context = MagicMock()
    mock_request_context.org_id = "test_org"
    mock_request_context.storage = mock_storage if storage_configured else None
    mock_request_context.is_storage_configured.return_value = storage_configured

    mixin.request_context = mock_request_context
    mixin.llm_client = MagicMock()
    return mixin


def _get_storage(mixin: ProfilesMixin) -> MagicMock:
    return mixin.request_context.storage


def _sample_profile(**overrides) -> UserProfile:
    defaults = {
        "profile_id": "p1",
        "user_id": "user1",
        "profile_content": "likes sushi",
        "last_modified_timestamp": int(time.time()),
        "generated_from_request_id": "req1",
    }
    defaults.update(overrides)
    return UserProfile(**defaults)


# ---------------------------------------------------------------------------
# get_profiles
# ---------------------------------------------------------------------------


class TestGetProfiles:
    def test_returns_profiles(self):
        """Successful retrieval returns profiles from storage."""
        mixin = _make_mixin()
        sample = _sample_profile()
        _get_storage(mixin).get_user_profile.return_value = [sample]

        request = GetUserProfilesRequest(user_id="user1")
        response = mixin.get_profiles(request)

        assert response.success is True
        assert len(response.user_profiles) == 1

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = GetUserProfilesRequest(user_id="user1")
        response = mixin.get_profiles(request)

        assert response.success is True
        assert response.user_profiles == []
        assert response.msg is not None

    def test_dict_input(self):
        """Accepts dict input and auto-converts."""
        mixin = _make_mixin()
        _get_storage(mixin).get_user_profile.return_value = []

        response = mixin.get_profiles({"user_id": "user1"})

        assert response.success is True
        _get_storage(mixin).get_user_profile.assert_called_once()

    def test_top_k_limit(self):
        """Applies top_k limit to results."""
        mixin = _make_mixin()
        now = int(time.time())
        profiles = [
            _sample_profile(profile_id=f"p{i}", last_modified_timestamp=now - i)
            for i in range(5)
        ]
        _get_storage(mixin).get_user_profile.return_value = profiles

        request = GetUserProfilesRequest(user_id="user1", top_k=2)
        response = mixin.get_profiles(request)

        assert response.success is True
        assert len(response.user_profiles) == 2

    def test_sorted_by_last_modified_descending(self):
        """Results are sorted by last_modified_timestamp in descending order."""
        mixin = _make_mixin()
        now = int(time.time())
        profiles = [
            _sample_profile(profile_id="p1", last_modified_timestamp=now - 100),
            _sample_profile(profile_id="p2", last_modified_timestamp=now),
            _sample_profile(profile_id="p3", last_modified_timestamp=now - 50),
        ]
        _get_storage(mixin).get_user_profile.return_value = profiles

        request = GetUserProfilesRequest(user_id="user1")
        response = mixin.get_profiles(request)

        assert response.success is True
        timestamps = [p.last_modified_timestamp for p in response.user_profiles]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_status_filter_from_parameter(self):
        """Status filter passed as parameter takes precedence."""
        mixin = _make_mixin()
        _get_storage(mixin).get_user_profile.return_value = []

        request = GetUserProfilesRequest(user_id="user1")
        mixin.get_profiles(request, status_filter=[Status.ARCHIVED])

        call_kwargs = _get_storage(mixin).get_user_profile.call_args
        assert call_kwargs[1]["status_filter"] == [Status.ARCHIVED]

    def test_status_filter_from_request(self):
        """Uses request.status_filter when parameter not given."""
        mixin = _make_mixin()
        _get_storage(mixin).get_user_profile.return_value = []

        request = GetUserProfilesRequest(
            user_id="user1", status_filter=[Status.PENDING]
        )
        mixin.get_profiles(request)

        call_kwargs = _get_storage(mixin).get_user_profile.call_args
        assert call_kwargs[1]["status_filter"] == [Status.PENDING]

    def test_default_status_filter(self):
        """Defaults to [None] status filter for current profiles."""
        mixin = _make_mixin()
        _get_storage(mixin).get_user_profile.return_value = []

        request = GetUserProfilesRequest(user_id="user1")
        mixin.get_profiles(request)

        call_kwargs = _get_storage(mixin).get_user_profile.call_args
        assert call_kwargs[1]["status_filter"] == [None]


# ---------------------------------------------------------------------------
# get_all_profiles
# ---------------------------------------------------------------------------


class TestGetAllProfiles:
    def test_returns_all(self):
        """Returns all profiles across users."""
        mixin = _make_mixin()
        sample = _sample_profile()
        _get_storage(mixin).get_all_profiles.return_value = [sample]

        response = mixin.get_all_profiles(limit=50)

        assert response.success is True
        assert len(response.user_profiles) == 1
        _get_storage(mixin).get_all_profiles.assert_called_once_with(
            limit=50, status_filter=[None]
        )

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.get_all_profiles()

        assert response.success is True
        assert response.user_profiles == []
        assert response.msg is not None

    def test_custom_status_filter(self):
        """Passes custom status filter to storage."""
        mixin = _make_mixin()
        _get_storage(mixin).get_all_profiles.return_value = []

        mixin.get_all_profiles(status_filter=[Status.ARCHIVED])

        call_kwargs = _get_storage(mixin).get_all_profiles.call_args
        assert call_kwargs[1]["status_filter"] == [Status.ARCHIVED]


# ---------------------------------------------------------------------------
# search_profiles
# ---------------------------------------------------------------------------


class TestSearchProfiles:
    def test_query_delegation(self):
        """Delegates search to storage."""
        mixin = _make_mixin()
        sample = _sample_profile()
        _get_storage(mixin).search_user_profile.return_value = [sample]

        request = SearchUserProfileRequest(user_id="user1", query="sushi")
        response = mixin.search_profiles(request)

        assert response.success is True
        assert len(response.user_profiles) == 1
        _get_storage(mixin).search_user_profile.assert_called_once()

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = SearchUserProfileRequest(user_id="user1", query="sushi")
        response = mixin.search_profiles(request)

        assert response.success is True
        assert response.user_profiles == []
        assert response.msg is not None

    def test_dict_input(self):
        """Accepts dict input and auto-converts."""
        mixin = _make_mixin()
        _get_storage(mixin).search_user_profile.return_value = []

        response = mixin.search_profiles({"user_id": "user1", "query": "test"})

        assert response.success is True

    def test_default_status_filter(self):
        """Defaults to [None] status filter for current profiles."""
        mixin = _make_mixin()
        _get_storage(mixin).search_user_profile.return_value = []

        request = SearchUserProfileRequest(user_id="user1", query="test")
        mixin.search_profiles(request)

        call_kwargs = _get_storage(mixin).search_user_profile.call_args
        assert call_kwargs[1]["status_filter"] == [None]

    def test_custom_status_filter(self):
        """Uses provided status filter."""
        mixin = _make_mixin()
        _get_storage(mixin).search_user_profile.return_value = []

        request = SearchUserProfileRequest(user_id="user1", query="test")
        mixin.search_profiles(request, status_filter=[Status.PENDING])

        call_kwargs = _get_storage(mixin).search_user_profile.call_args
        assert call_kwargs[1]["status_filter"] == [Status.PENDING]


# ---------------------------------------------------------------------------
# delete_profile
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    def test_single_delete(self):
        """Deletes a profile by user_id and profile_id."""
        mixin = _make_mixin()

        request = DeleteUserProfileRequest(user_id="user1", profile_id="p1")
        response = mixin.delete_profile(request)

        assert response.success is True
        _get_storage(mixin).delete_user_profile.assert_called_once()

    def test_dict_input(self):
        """Accepts dict input."""
        mixin = _make_mixin()

        response = mixin.delete_profile({"user_id": "user1", "profile_id": "p1"})

        assert response.success is True

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteUserProfileRequest(user_id="user1", profile_id="p1")
        response = mixin.delete_profile(request)

        assert response.success is False

    def test_storage_exception(self):
        """Returns failure on storage exception."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_user_profile.side_effect = RuntimeError("db error")

        request = DeleteUserProfileRequest(user_id="user1", profile_id="p1")
        response = mixin.delete_profile(request)

        assert response.success is False
        assert "db error" in (response.message or "")


# ---------------------------------------------------------------------------
# delete_all_profiles_bulk
# ---------------------------------------------------------------------------


class TestDeleteAllProfilesBulk:
    def test_bulk_delete(self):
        """Deletes all profiles."""
        mixin = _make_mixin()

        response = mixin.delete_all_profiles_bulk()

        assert response.success is True
        _get_storage(mixin).delete_all_profiles.assert_called_once()

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.delete_all_profiles_bulk()

        assert response.success is False


# ---------------------------------------------------------------------------
# delete_profiles_by_ids
# ---------------------------------------------------------------------------


class TestDeleteProfilesByIds:
    def test_delete_by_ids(self):
        """Deletes profiles by their IDs."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_profiles_by_ids.return_value = 3

        request = DeleteProfilesByIdsRequest(profile_ids=["p1", "p2", "p3"])
        response = mixin.delete_profiles_by_ids(request)

        assert response.success is True
        assert response.deleted_count == 3

    def test_dict_input(self):
        """Accepts dict input."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_profiles_by_ids.return_value = 1

        response = mixin.delete_profiles_by_ids({"profile_ids": ["p1"]})

        assert response.success is True

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteProfilesByIdsRequest(profile_ids=["p1"])
        response = mixin.delete_profiles_by_ids(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# get_profile_change_logs
# ---------------------------------------------------------------------------


class TestGetProfileChangeLogs:
    def test_returns_change_logs(self):
        """Returns change logs from storage."""
        mixin = _make_mixin()
        sample_log = ProfileChangeLog(
            id=1,
            user_id="user1",
            request_id="req1",
            added_profiles=[_sample_profile()],
            removed_profiles=[],
            mentioned_profiles=[],
        )
        _get_storage(mixin).get_profile_change_logs.return_value = [sample_log]

        response = mixin.get_profile_change_logs()

        assert response.success is True
        assert len(response.profile_change_logs) == 1

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.get_profile_change_logs()

        assert response.success is True
        assert response.profile_change_logs == []


# ---------------------------------------------------------------------------
# get_profile_statistics
# ---------------------------------------------------------------------------


class TestGetProfileStatistics:
    def test_returns_statistics(self):
        """Returns profile statistics from storage."""
        mixin = _make_mixin()
        _get_storage(mixin).get_profile_statistics.return_value = {
            "current_count": 10,
            "pending_count": 5,
            "archived_count": 3,
            "expiring_soon_count": 1,
        }

        response = mixin.get_profile_statistics()

        assert response.success is True
        assert response.current_count == 10
        assert response.pending_count == 5
        assert response.archived_count == 3
        assert response.expiring_soon_count == 1

    def test_storage_not_configured(self):
        """Returns zero counts when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.get_profile_statistics()

        assert response.success is True
        assert response.current_count == 0
        assert response.pending_count == 0
        assert response.msg is not None

    def test_exception_returns_failure(self):
        """Returns failure on storage exception."""
        mixin = _make_mixin()
        _get_storage(mixin).get_profile_statistics.side_effect = RuntimeError(
            "db error"
        )

        response = mixin.get_profile_statistics()

        assert response.success is False
        assert "db error" in (response.msg or "")


# ---------------------------------------------------------------------------
# upgrade_all_profiles
# ---------------------------------------------------------------------------


class TestUpgradeAllProfiles:
    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_success(self, mock_service_cls):
        """Successful upgrade delegates to service."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_upgrade.return_value = UpgradeProfilesResponse(
            success=True, profiles_archived=2, profiles_promoted=3
        )
        mock_service_cls.return_value = mock_service

        response = mixin.upgrade_all_profiles()

        assert response.success is True
        assert response.profiles_archived == 2
        assert response.profiles_promoted == 3
        mock_service.run_upgrade.assert_called_once()

    def test_storage_not_configured(self):
        """Returns failure when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.upgrade_all_profiles()

        assert response.success is False
        assert response.message is not None

    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_dict_input(self, mock_service_cls):
        """Accepts dict input and auto-converts."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_upgrade.return_value = UpgradeProfilesResponse(success=True)
        mock_service_cls.return_value = mock_service

        response = mixin.upgrade_all_profiles({"only_affected_users": True})

        assert response.success is True

    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_none_input(self, mock_service_cls):
        """None request creates default UpgradeProfilesRequest."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_upgrade.return_value = UpgradeProfilesResponse(success=True)
        mock_service_cls.return_value = mock_service

        response = mixin.upgrade_all_profiles(None)

        assert response.success is True
        call_arg = mock_service.run_upgrade.call_args[0][0]
        assert isinstance(call_arg, UpgradeProfilesRequest)
        assert call_arg.only_affected_users is False


# ---------------------------------------------------------------------------
# downgrade_all_profiles
# ---------------------------------------------------------------------------


class TestDowngradeAllProfiles:
    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_success(self, mock_service_cls):
        """Successful downgrade delegates to service."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_downgrade.return_value = DowngradeProfilesResponse(
            success=True, profiles_demoted=2, profiles_restored=3
        )
        mock_service_cls.return_value = mock_service

        response = mixin.downgrade_all_profiles()

        assert response.success is True
        assert response.profiles_demoted == 2
        assert response.profiles_restored == 3
        mock_service.run_downgrade.assert_called_once()

    def test_storage_not_configured(self):
        """Returns failure when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.downgrade_all_profiles()

        assert response.success is False
        assert response.message is not None

    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_dict_input(self, mock_service_cls):
        """Accepts dict input and auto-converts."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_downgrade.return_value = DowngradeProfilesResponse(
            success=True
        )
        mock_service_cls.return_value = mock_service

        response = mixin.downgrade_all_profiles({"only_affected_users": True})

        assert response.success is True

    @patch("reflexio.reflexio_lib._profiles.ProfileGenerationService")
    def test_none_input(self, mock_service_cls):
        """None request creates default DowngradeProfilesRequest."""
        mixin = _make_mixin()
        mock_service = MagicMock()
        mock_service.run_downgrade.return_value = DowngradeProfilesResponse(
            success=True
        )
        mock_service_cls.return_value = mock_service

        response = mixin.downgrade_all_profiles(None)

        assert response.success is True
        call_arg = mock_service.run_downgrade.call_args[0][0]
        assert isinstance(call_arg, DowngradeProfilesRequest)
        assert call_arg.only_affected_users is False
