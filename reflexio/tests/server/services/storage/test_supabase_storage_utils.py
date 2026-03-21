"""
Unit tests for supabase_storage_utils serialization functions.

Tests blocking_issue serialization in raw_feedback_to_data and feedback_to_data,
plus converters, parsers, and utility functions.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from reflexio_commons.api_schema.service_schemas import (
    AgentSuccessEvaluationResult,
    BlockingIssue,
    BlockingIssueKind,
    Feedback,
    FeedbackAggregationChangeLog,
    FeedbackSnapshot,
    FeedbackStatus,
    FeedbackUpdateEntry,
    Interaction,
    ProfileChangeLog,
    ProfileTimeToLive,
    RawFeedback,
    RegularVsShadow,
    Request,
    Skill,
    SkillStatus,
    Status,
    ToolUsed,
    UserActionType,
    UserProfile,
)

from reflexio.server.services.storage.supabase_storage_utils import (
    _parse_iso_timestamp,
    agent_success_evaluation_result_to_data,
    check_migration_needed,
    execute_migration,
    execute_sql_file_direct,
    extract_db_url_from_config_json,
    feedback_aggregation_change_log_to_data,
    feedback_to_data,
    get_latest_migration_version,
    get_organization_config,
    interaction_to_data,
    is_localhost_url,
    profile_change_log_to_data,
    raw_feedback_to_data,
    request_to_data,
    response_list_to_feedback_aggregation_change_logs,
    response_list_to_interactions,
    response_list_to_profile_change_logs,
    response_list_to_requests,
    response_list_to_user_profiles,
    response_to_feedback_aggregation_change_log,
    response_to_interaction,
    response_to_profile_change_log,
    response_to_request,
    response_to_skill,
    response_to_user_profile,
    set_organization_config,
    skill_to_data,
    user_profile_to_data,
)


class TestRawFeedbackToData:
    """Tests for raw_feedback_to_data serialization."""

    def test_serializes_blocking_issue(self):
        """Test that blocking_issue is serialized to dict via model_dump."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.MISSING_TOOL,
                details="No database query tool",
            ),
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["blocking_issue"] is not None
        assert data["blocking_issue"]["kind"] == "missing_tool"
        assert data["blocking_issue"]["details"] == "No database query tool"

    def test_serializes_none_blocking_issue(self):
        """Test that None blocking_issue is serialized as None."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["blocking_issue"] is None

    def test_serializes_source_interaction_ids(self):
        """Test that source_interaction_ids list is serialized as-is."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
            source_interaction_ids=[10, 20, 30],
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["source_interaction_ids"] == [10, 20, 30]

    def test_serializes_empty_source_interaction_ids_as_none(self):
        """Test that empty source_interaction_ids is serialized as None for DB storage."""
        raw_feedback = RawFeedback(
            agent_version="1.0",
            request_id="req1",
            feedback_name="test",
            feedback_content="test content",
        )

        data = raw_feedback_to_data(raw_feedback)

        assert data["source_interaction_ids"] is None


class TestFeedbackToData:
    """Tests for feedback_to_data serialization."""

    def test_serializes_blocking_issue(self):
        """Test that blocking_issue is serialized to dict via model_dump."""
        feedback = Feedback(
            agent_version="1.0",
            feedback_name="test",
            feedback_content="test content",
            feedback_status=FeedbackStatus.PENDING,
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.PERMISSION_DENIED,
                details="Cannot access admin API",
            ),
        )

        data = feedback_to_data(feedback)

        assert data["blocking_issue"] is not None
        assert data["blocking_issue"]["kind"] == "permission_denied"
        assert data["blocking_issue"]["details"] == "Cannot access admin API"

    def test_serializes_none_blocking_issue(self):
        """Test that None blocking_issue is serialized as None."""
        feedback = Feedback(
            agent_version="1.0",
            feedback_name="test",
            feedback_content="test content",
            feedback_status=FeedbackStatus.PENDING,
        )

        data = feedback_to_data(feedback)

        assert data["blocking_issue"] is None


# ===============================
# Tests for _parse_iso_timestamp
# ===============================


class TestParseIsoTimestamp:
    """Tests for _parse_iso_timestamp utility."""

    def test_standard_iso_format(self):
        """Test parsing a standard ISO 8601 timestamp with timezone offset."""
        ts = "2024-01-15T10:30:00+00:00"
        result = _parse_iso_timestamp(ts)
        expected = int(datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC).timestamp())
        assert result == expected

    def test_z_suffix(self):
        """Test parsing a timestamp with Z suffix (UTC shorthand)."""
        ts = "2024-06-01T12:00:00Z"
        result = _parse_iso_timestamp(ts)
        expected = int(datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC).timestamp())
        assert result == expected

    def test_variable_fractional_seconds_5_digits(self):
        """Test parsing with 5-digit fractional seconds (Postgres quirk)."""
        ts = "2024-03-20T08:15:30.12345+00:00"
        result = _parse_iso_timestamp(ts)
        expected = int(
            datetime(2024, 3, 20, 8, 15, 30, 123450, tzinfo=UTC).timestamp()
        )
        assert result == expected

    def test_variable_fractional_seconds_3_digits(self):
        """Test parsing with 3-digit fractional seconds (milliseconds)."""
        ts = "2024-03-20T08:15:30.123+00:00"
        result = _parse_iso_timestamp(ts)
        expected = int(
            datetime(2024, 3, 20, 8, 15, 30, 123000, tzinfo=UTC).timestamp()
        )
        assert result == expected

    def test_fractional_seconds_6_digits(self):
        """Test parsing with 6-digit fractional seconds (standard microseconds)."""
        ts = "2024-03-20T08:15:30.123456+00:00"
        result = _parse_iso_timestamp(ts)
        expected = int(
            datetime(2024, 3, 20, 8, 15, 30, 123456, tzinfo=UTC).timestamp()
        )
        assert result == expected

    def test_z_suffix_with_fractional(self):
        """Test Z suffix combined with fractional seconds."""
        ts = "2024-01-01T00:00:00.5Z"
        result = _parse_iso_timestamp(ts)
        expected = int(
            datetime(2024, 1, 1, 0, 0, 0, 500000, tzinfo=UTC).timestamp()
        )
        assert result == expected


# ===============================
# Tests for response_to_* converters
# ===============================


class TestResponseToUserProfile:
    """Tests for response_to_user_profile converter."""

    def test_converts_complete_item(self):
        """Test converting a complete response item to UserProfile."""
        item = {
            "profile_id": "p1",
            "user_id": "u1",
            "content": "likes coffee",
            "last_modified_timestamp": 1700000000,
            "generated_from_request_id": "req1",
            "profile_time_to_live": "one_month",
            "expiration_timestamp": 1703000000,
            "custom_features": {"key": "val"},
            "source": "chat",
            "status": None,
            "extractor_names": ["extractor_a"],
        }

        profile = response_to_user_profile(item)

        assert profile.profile_id == "p1"
        assert profile.user_id == "u1"
        assert profile.profile_content == "likes coffee"
        assert profile.profile_time_to_live == ProfileTimeToLive.ONE_MONTH
        assert profile.source == "chat"
        assert profile.status is None
        assert profile.extractor_names == ["extractor_a"]

    def test_missing_optional_fields_default(self):
        """Test that missing optional fields get defaults."""
        item = {
            "profile_id": "p2",
            "user_id": "u2",
            "content": "test",
            "last_modified_timestamp": 0,
            "generated_from_request_id": "req2",
            "profile_time_to_live": "infinity",
            "expiration_timestamp": 0,
            "custom_features": None,
            "status": None,
        }

        profile = response_to_user_profile(item)

        assert profile.source == ""
        assert profile.extractor_names is None


class TestResponseToInteraction:
    """Tests for response_to_interaction converter."""

    def test_converts_complete_item(self):
        """Test converting a complete response item to Interaction."""
        item = {
            "interaction_id": 42,
            "user_id": "u1",
            "content": "hello",
            "request_id": "req1",
            "created_at": "2024-06-01T12:00:00+00:00",
            "role": "user",
            "user_action": "click",
            "user_action_description": "submit button",
            "interacted_image_url": "http://img.test/1.png",
            "shadow_content": "shadow text",
            "tools_used": [{"tool_name": "search", "tool_input": {"query": "q"}}],
        }

        interaction = response_to_interaction(item)

        assert interaction.interaction_id == 42
        assert interaction.content == "hello"
        assert interaction.role == "user"
        assert interaction.user_action == UserActionType.CLICK
        assert interaction.shadow_content == "shadow text"
        assert len(interaction.tools_used) == 1
        assert interaction.tools_used[0].tool_name == "search"

    def test_missing_optional_fields(self):
        """Test handling missing optional fields in interaction data."""
        item = {
            "interaction_id": 1,
            "user_id": "u1",
            "content": "test",
            "request_id": "req1",
            "created_at": "2024-06-01T12:00:00Z",
            "user_action": "none",
            "user_action_description": "",
            "interacted_image_url": "",
            "tools_used": None,
            "shadow_content": None,
        }

        interaction = response_to_interaction(item)

        assert interaction.role == "User"
        assert interaction.shadow_content == ""
        assert interaction.tools_used == []


class TestResponseToRequest:
    """Tests for response_to_request converter."""

    def test_converts_complete_item(self):
        """Test converting a complete response item to Request."""
        item = {
            "request_id": "req1",
            "user_id": "u1",
            "created_at": "2024-06-01T12:00:00+00:00",
            "source": "api",
            "agent_version": "v2.0",
            "session_id": "sess_1",
        }

        request = response_to_request(item)

        assert request.request_id == "req1"
        assert request.source == "api"
        assert request.agent_version == "v2.0"
        assert request.session_id == "sess_1"

    def test_missing_optional_fields(self):
        """Test that missing optional fields get defaults."""
        item = {
            "request_id": "req2",
            "user_id": "u2",
            "created_at": "2024-06-01T00:00:00Z",
        }

        request = response_to_request(item)

        assert request.source == ""
        assert request.agent_version == ""
        assert request.session_id is None


# ===============================
# Tests for *_to_data converters
# ===============================


class TestSkillToData:
    """Tests for skill_to_data converter."""

    def test_converts_skill_with_all_fields(self):
        """Test converting a Skill with all fields to data dict."""
        now_ts = int(datetime.now(UTC).timestamp())
        skill = Skill(
            skill_id=5,
            skill_name="greeting_skill",
            description="Greets users",
            version="2.0.0",
            agent_version="v1",
            feedback_name="feedback_greet",
            instructions="Say hello",
            allowed_tools=["search", "calc"],
            blocking_issues=[
                BlockingIssue(
                    kind=BlockingIssueKind.MISSING_TOOL, details="no db tool"
                )
            ],
            raw_feedback_ids=[1, 2, 3],
            skill_status=SkillStatus.PUBLISHED,
            updated_at=now_ts,
        )

        data = skill_to_data(skill)

        assert data["skill_id"] == 5
        assert data["skill_name"] == "greeting_skill"
        assert data["skill_status"] == "published"
        assert data["allowed_tools"] == ["search", "calc"]
        assert len(data["blocking_issues"]) == 1
        assert data["blocking_issues"][0]["kind"] == "missing_tool"

    def test_skill_without_id_omits_it(self):
        """Test that a skill with skill_id=0 omits skill_id from data."""
        skill = Skill(
            skill_id=0,
            skill_name="test",
            updated_at=int(datetime.now(UTC).timestamp()),
        )

        data = skill_to_data(skill)

        assert "skill_id" not in data


# ===============================
# Tests for response_list_to_* batch converters
# ===============================


class TestResponseListConverters:
    """Tests for batch list converters."""

    def _make_profile_item(self, profile_id: str) -> dict:
        return {
            "profile_id": profile_id,
            "user_id": "u1",
            "content": f"content_{profile_id}",
            "last_modified_timestamp": 0,
            "generated_from_request_id": "req1",
            "profile_time_to_live": "infinity",
            "expiration_timestamp": 0,
            "custom_features": None,
            "status": None,
        }

    def _make_interaction_item(self, interaction_id: int) -> dict:
        return {
            "interaction_id": interaction_id,
            "user_id": "u1",
            "content": f"msg_{interaction_id}",
            "request_id": "req1",
            "created_at": "2024-01-01T00:00:00Z",
            "user_action": "none",
            "user_action_description": "",
            "interacted_image_url": "",
            "tools_used": None,
            "shadow_content": None,
        }

    def _make_request_item(self, request_id: str) -> dict:
        return {
            "request_id": request_id,
            "user_id": "u1",
            "created_at": "2024-01-01T00:00:00Z",
        }

    def test_response_list_to_user_profiles(self):
        """Test batch conversion of response items to UserProfile list."""
        items = [self._make_profile_item("p1"), self._make_profile_item("p2")]
        profiles = response_list_to_user_profiles(items)
        assert len(profiles) == 2
        assert profiles[0].profile_id == "p1"
        assert profiles[1].profile_id == "p2"

    def test_response_list_to_user_profiles_empty(self):
        """Test batch conversion with empty list."""
        assert response_list_to_user_profiles([]) == []

    def test_response_list_to_interactions(self):
        """Test batch conversion of response items to Interaction list."""
        items = [self._make_interaction_item(1), self._make_interaction_item(2)]
        interactions = response_list_to_interactions(items)
        assert len(interactions) == 2
        assert interactions[0].interaction_id == 1

    def test_response_list_to_interactions_empty(self):
        """Test batch conversion with empty list."""
        assert response_list_to_interactions([]) == []

    def test_response_list_to_requests(self):
        """Test batch conversion of response items to Request list."""
        items = [self._make_request_item("r1"), self._make_request_item("r2")]
        requests = response_list_to_requests(items)
        assert len(requests) == 2
        assert requests[0].request_id == "r1"

    def test_response_list_to_requests_empty(self):
        """Test batch conversion with empty list."""
        assert response_list_to_requests([]) == []


# ===============================
# Tests for is_localhost_url
# ===============================


class TestIsLocalhostUrl:
    """Tests for is_localhost_url utility."""

    def test_localhost_hostname(self):
        """Test detection of 'localhost' hostname."""
        assert is_localhost_url("postgresql://user:pass@localhost:5432/db") is True

    def test_ipv4_loopback(self):
        """Test detection of 127.0.0.1 loopback address."""
        assert is_localhost_url("postgresql://user:pass@127.0.0.1:5432/db") is True

    def test_ipv6_loopback(self):
        """Test detection of ::1 IPv6 loopback address."""
        assert is_localhost_url("postgresql://user:pass@[::1]:5432/db") is True

    def test_remote_host(self):
        """Test that a remote host is not detected as localhost."""
        assert is_localhost_url("postgresql://user:pass@db.example.com:5432/db") is False

    def test_empty_string(self):
        """Test that an empty string returns False."""
        assert is_localhost_url("") is False

    def test_invalid_url(self):
        """Test that an invalid URL returns False."""
        assert is_localhost_url("not-a-url") is False


# ===============================
# Tests for user_profile_to_data
# ===============================


class TestUserProfileToData:
    """Tests for user_profile_to_data converter."""

    def test_converts_profile_with_all_fields(self):
        """Test converting a UserProfile with all fields to data dict."""
        profile = UserProfile(
            profile_id="p1",
            user_id="u1",
            profile_content="likes coffee",
            last_modified_timestamp=1700000000,
            generated_from_request_id="req1",
            profile_time_to_live=ProfileTimeToLive.ONE_MONTH,
            expiration_timestamp=1703000000,
            custom_features={"key": "val"},
            source="chat",
            status=Status.PENDING,
            extractor_names=["extractor_a"],
        )

        data = user_profile_to_data(profile)

        assert data["profile_id"] == "p1"
        assert data["user_id"] == "u1"
        assert data["content"] == "likes coffee"
        assert data["last_modified_timestamp"] == 1700000000
        assert data["generated_from_request_id"] == "req1"
        assert data["profile_time_to_live"] == "one_month"
        assert data["expiration_timestamp"] == 1703000000
        assert data["custom_features"] == {"key": "val"}
        assert data["source"] == "chat"
        assert data["status"] == "pending"
        assert data["extractor_names"] == ["extractor_a"]
        assert data["embedding"] == []

    def test_converts_profile_with_none_status(self):
        """Test that None status is serialized as None."""
        profile = UserProfile(
            profile_id="p2",
            user_id="u2",
            profile_content="test",
            last_modified_timestamp=0,
            generated_from_request_id="req2",
        )

        data = user_profile_to_data(profile)

        assert data["status"] is None


# ===============================
# Tests for interaction_to_data
# ===============================


class TestInteractionToData:
    """Tests for interaction_to_data converter."""

    def test_converts_interaction_with_id(self):
        """Test converting an Interaction with a set interaction_id."""
        interaction = Interaction(
            interaction_id=42,
            user_id="u1",
            request_id="req1",
            created_at=1717243200,
            role="user",
            content="hello",
            user_action=UserActionType.CLICK,
            user_action_description="submit button",
            interacted_image_url="http://img.test/1.png",
            shadow_content="shadow text",
            tools_used=[ToolUsed(tool_name="search", tool_input={"query": "q"})],
        )

        data = interaction_to_data(interaction)

        assert data["interaction_id"] == 42
        assert data["user_id"] == "u1"
        assert data["request_id"] == "req1"
        assert data["role"] == "user"
        assert data["content"] == "hello"
        assert data["user_action"] == "click"
        assert data["user_action_description"] == "submit button"
        assert data["shadow_content"] == "shadow text"
        assert len(data["tools_used"]) == 1
        assert data["tools_used"][0]["tool_name"] == "search"
        assert data["embedding"] == []
        # created_at should be an ISO string
        assert isinstance(data["created_at"], str)

    def test_omits_interaction_id_when_zero(self):
        """Test that interaction_id=0 is omitted from data."""
        interaction = Interaction(
            interaction_id=0,
            user_id="u1",
            request_id="req1",
        )

        data = interaction_to_data(interaction)

        assert "interaction_id" not in data


# ===============================
# Tests for request_to_data
# ===============================


class TestRequestToData:
    """Tests for request_to_data converter."""

    def test_converts_request_with_all_fields(self):
        """Test converting a Request with all fields to data dict."""
        request = Request(
            request_id="req1",
            user_id="u1",
            created_at=1717243200,
            source="api",
            agent_version="v2.0",
            session_id="sess_1",
        )

        data = request_to_data(request)

        assert data["request_id"] == "req1"
        assert data["user_id"] == "u1"
        assert data["source"] == "api"
        assert data["agent_version"] == "v2.0"
        assert data["session_id"] == "sess_1"
        assert isinstance(data["created_at"], str)

    def test_converts_request_with_none_session(self):
        """Test that None session_id is serialized as None."""
        request = Request(
            request_id="req2",
            user_id="u2",
            created_at=0,
        )

        data = request_to_data(request)

        assert data["session_id"] is None


# ===============================
# Tests for response_to_profile_change_log
# ===============================


class TestResponseToProfileChangeLog:
    """Tests for response_to_profile_change_log converter."""

    def _make_profile_dict(self, profile_id: str) -> dict:
        return {
            "profile_id": profile_id,
            "user_id": "u1",
            "profile_content": "content",
            "last_modified_timestamp": 1700000000,
            "generated_from_request_id": "req1",
        }

    def test_converts_complete_item(self):
        """Test converting a complete response item to ProfileChangeLog."""
        item = {
            "id": 1,
            "user_id": "u1",
            "request_id": "req1",
            "created_at": 1700000000,
            "added_profiles": [self._make_profile_dict("p1")],
            "removed_profiles": [self._make_profile_dict("p2")],
            "mentioned_profiles": [self._make_profile_dict("p3")],
        }

        change_log = response_to_profile_change_log(item)

        assert change_log.id == 1
        assert change_log.user_id == "u1"
        assert change_log.request_id == "req1"
        assert change_log.created_at == 1700000000
        assert len(change_log.added_profiles) == 1
        assert change_log.added_profiles[0].profile_id == "p1"
        assert len(change_log.removed_profiles) == 1
        assert change_log.removed_profiles[0].profile_id == "p2"
        assert len(change_log.mentioned_profiles) == 1
        assert change_log.mentioned_profiles[0].profile_id == "p3"

    def test_converts_with_empty_profile_lists(self):
        """Test converting an item with empty profile lists."""
        item = {
            "id": 2,
            "user_id": "u2",
            "request_id": "req2",
            "created_at": 0,
            "added_profiles": [],
            "removed_profiles": [],
            "mentioned_profiles": [],
        }

        change_log = response_to_profile_change_log(item)

        assert change_log.added_profiles == []
        assert change_log.removed_profiles == []
        assert change_log.mentioned_profiles == []


# ===============================
# Tests for profile_change_log_to_data
# ===============================


class TestProfileChangeLogToData:
    """Tests for profile_change_log_to_data converter."""

    def test_converts_change_log_to_data(self):
        """Test converting a ProfileChangeLog to data dict."""
        profile = UserProfile(
            profile_id="p1",
            user_id="u1",
            profile_content="content",
            last_modified_timestamp=1700000000,
            generated_from_request_id="req1",
        )
        change_log = ProfileChangeLog(
            id=1,
            user_id="u1",
            request_id="req1",
            created_at=1700000000,
            added_profiles=[profile],
            removed_profiles=[],
            mentioned_profiles=[profile],
        )

        data = profile_change_log_to_data(change_log)

        assert data["user_id"] == "u1"
        assert data["request_id"] == "req1"
        assert data["created_at"] == 1700000000
        assert len(data["added_profiles"]) == 1
        assert data["added_profiles"][0]["profile_id"] == "p1"
        assert data["removed_profiles"] == []
        assert len(data["mentioned_profiles"]) == 1
        # id should not be in data (auto-generated by DB)
        assert "id" not in data


# ===============================
# Tests for response_list_to_profile_change_logs
# ===============================


class TestResponseListToProfileChangeLogs:
    """Tests for response_list_to_profile_change_logs batch converter."""

    def _make_change_log_item(self, log_id: int) -> dict:
        return {
            "id": log_id,
            "user_id": "u1",
            "request_id": f"req{log_id}",
            "created_at": 1700000000,
            "added_profiles": [],
            "removed_profiles": [],
            "mentioned_profiles": [],
        }

    def test_converts_list(self):
        """Test batch conversion of response items to ProfileChangeLog list."""
        items = [self._make_change_log_item(1), self._make_change_log_item(2)]
        logs = response_list_to_profile_change_logs(items)
        assert len(logs) == 2
        assert logs[0].id == 1
        assert logs[1].id == 2

    def test_empty_list(self):
        """Test batch conversion with empty list."""
        assert response_list_to_profile_change_logs([]) == []


# ===============================
# Tests for feedback_aggregation_change_log_to_data
# ===============================


class TestFeedbackAggregationChangeLogToData:
    """Tests for feedback_aggregation_change_log_to_data converter."""

    def test_converts_change_log_with_all_entries(self):
        """Test converting a FeedbackAggregationChangeLog with added, removed, and updated entries."""
        snapshot_added = FeedbackSnapshot(
            feedback_id=1,
            feedback_name="test",
            feedback_content="new content",
        )
        snapshot_removed = FeedbackSnapshot(
            feedback_id=2,
            feedback_name="test",
            feedback_content="old content",
        )
        snapshot_before = FeedbackSnapshot(
            feedback_id=3,
            feedback_name="test",
            feedback_content="before content",
        )
        snapshot_after = FeedbackSnapshot(
            feedback_id=3,
            feedback_name="test",
            feedback_content="after content",
        )
        change_log = FeedbackAggregationChangeLog(
            id=1,
            created_at=1700000000,
            feedback_name="test",
            agent_version="v1",
            run_mode="full_archive",
            added_feedbacks=[snapshot_added],
            removed_feedbacks=[snapshot_removed],
            updated_feedbacks=[
                FeedbackUpdateEntry(before=snapshot_before, after=snapshot_after)
            ],
        )

        data = feedback_aggregation_change_log_to_data(change_log)

        assert data["feedback_name"] == "test"
        assert data["agent_version"] == "v1"
        assert data["run_mode"] == "full_archive"
        assert data["created_at"] == 1700000000
        assert len(data["added_feedbacks"]) == 1
        assert data["added_feedbacks"][0]["feedback_content"] == "new content"
        assert len(data["removed_feedbacks"]) == 1
        assert data["removed_feedbacks"][0]["feedback_content"] == "old content"
        assert len(data["updated_feedbacks"]) == 1
        assert data["updated_feedbacks"][0]["before"]["feedback_content"] == "before content"
        assert data["updated_feedbacks"][0]["after"]["feedback_content"] == "after content"
        # id should not be in data
        assert "id" not in data

    def test_converts_empty_change_log(self):
        """Test converting a FeedbackAggregationChangeLog with no entries."""
        change_log = FeedbackAggregationChangeLog(
            feedback_name="test",
            agent_version="v1",
            run_mode="incremental",
        )

        data = feedback_aggregation_change_log_to_data(change_log)

        assert data["added_feedbacks"] == []
        assert data["removed_feedbacks"] == []
        assert data["updated_feedbacks"] == []


# ===============================
# Tests for response_to_feedback_aggregation_change_log
# ===============================


class TestResponseToFeedbackAggregationChangeLog:
    """Tests for response_to_feedback_aggregation_change_log converter."""

    def test_converts_complete_item(self):
        """Test converting a complete response item to FeedbackAggregationChangeLog."""
        item = {
            "id": 10,
            "created_at": 1700000000,
            "feedback_name": "test_feedback",
            "agent_version": "v2",
            "run_mode": "full_archive",
            "added_feedbacks": [
                {"feedback_id": 1, "feedback_name": "test_feedback", "feedback_content": "added"},
            ],
            "removed_feedbacks": [
                {"feedback_id": 2, "feedback_name": "test_feedback", "feedback_content": "removed"},
            ],
            "updated_feedbacks": [
                {
                    "before": {"feedback_id": 3, "feedback_name": "test_feedback", "feedback_content": "old"},
                    "after": {"feedback_id": 3, "feedback_name": "test_feedback", "feedback_content": "new"},
                }
            ],
        }

        result = response_to_feedback_aggregation_change_log(item)

        assert result.id == 10
        assert result.created_at == 1700000000
        assert result.feedback_name == "test_feedback"
        assert result.agent_version == "v2"
        assert result.run_mode == "full_archive"
        assert len(result.added_feedbacks) == 1
        assert result.added_feedbacks[0].feedback_content == "added"
        assert len(result.removed_feedbacks) == 1
        assert result.removed_feedbacks[0].feedback_content == "removed"
        assert len(result.updated_feedbacks) == 1
        assert result.updated_feedbacks[0].before.feedback_content == "old"
        assert result.updated_feedbacks[0].after.feedback_content == "new"

    def test_converts_item_with_none_lists(self):
        """Test converting an item where list fields are None."""
        item = {
            "id": 11,
            "created_at": 0,
            "feedback_name": "test",
            "agent_version": "v1",
            "run_mode": "incremental",
            "added_feedbacks": None,
            "removed_feedbacks": None,
            "updated_feedbacks": None,
        }

        result = response_to_feedback_aggregation_change_log(item)

        assert result.added_feedbacks == []
        assert result.removed_feedbacks == []
        assert result.updated_feedbacks == []


# ===============================
# Tests for response_list_to_feedback_aggregation_change_logs
# ===============================


class TestResponseListToFeedbackAggregationChangeLogs:
    """Tests for response_list_to_feedback_aggregation_change_logs batch converter."""

    def _make_item(self, item_id: int) -> dict:
        return {
            "id": item_id,
            "created_at": 0,
            "feedback_name": "test",
            "agent_version": "v1",
            "run_mode": "incremental",
            "added_feedbacks": [],
            "removed_feedbacks": [],
            "updated_feedbacks": [],
        }

    def test_converts_list(self):
        """Test batch conversion of response items."""
        items = [self._make_item(1), self._make_item(2)]
        logs = response_list_to_feedback_aggregation_change_logs(items)
        assert len(logs) == 2
        assert logs[0].id == 1
        assert logs[1].id == 2

    def test_empty_list(self):
        """Test batch conversion with empty list."""
        assert response_list_to_feedback_aggregation_change_logs([]) == []


# ===============================
# Tests for response_to_skill
# ===============================


class TestResponseToSkill:
    """Tests for response_to_skill converter."""

    def test_converts_complete_item(self):
        """Test converting a complete response item to Skill."""
        item = {
            "skill_id": 5,
            "skill_name": "greeting_skill",
            "description": "Greets users",
            "version": "2.0.0",
            "agent_version": "v1",
            "feedback_name": "feedback_greet",
            "instructions": "Say hello",
            "allowed_tools": ["search", "calc"],
            "blocking_issues": [
                {"kind": "missing_tool", "details": "no db tool"},
            ],
            "raw_feedback_ids": [1, 2, 3],
            "skill_status": "published",
            "created_at": "2024-06-01T12:00:00+00:00",
            "updated_at": "2024-06-02T12:00:00+00:00",
        }

        skill = response_to_skill(item)

        assert skill.skill_id == 5
        assert skill.skill_name == "greeting_skill"
        assert skill.description == "Greets users"
        assert skill.version == "2.0.0"
        assert skill.agent_version == "v1"
        assert skill.feedback_name == "feedback_greet"
        assert skill.instructions == "Say hello"
        assert skill.allowed_tools == ["search", "calc"]
        assert len(skill.blocking_issues) == 1
        assert skill.blocking_issues[0].kind == BlockingIssueKind.MISSING_TOOL
        assert skill.blocking_issues[0].details == "no db tool"
        assert skill.raw_feedback_ids == [1, 2, 3]
        assert skill.skill_status == SkillStatus.PUBLISHED
        assert skill.created_at != 0
        assert skill.updated_at != 0

    def test_converts_item_with_none_timestamps(self):
        """Test converting an item with None timestamps defaults to 0."""
        item = {
            "skill_id": 1,
            "skill_name": "test",
            "created_at": None,
            "updated_at": None,
        }

        skill = response_to_skill(item)

        assert skill.created_at == 0
        assert skill.updated_at == 0

    def test_converts_item_with_none_optional_lists(self):
        """Test converting an item where optional list fields are None."""
        item = {
            "skill_id": 1,
            "skill_name": "test",
            "allowed_tools": None,
            "blocking_issues": None,
            "raw_feedback_ids": None,
            "skill_status": None,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        skill = response_to_skill(item)

        assert skill.allowed_tools == []
        assert skill.blocking_issues == []
        assert skill.raw_feedback_ids == []
        assert skill.skill_status == SkillStatus.DRAFT

    def test_blocking_issues_skips_non_dict_entries(self):
        """Test that non-dict entries in blocking_issues are skipped."""
        item = {
            "skill_name": "test",
            "blocking_issues": [
                {"kind": "missing_tool", "details": "valid"},
                "invalid_entry",
                42,
            ],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        skill = response_to_skill(item)

        assert len(skill.blocking_issues) == 1
        assert skill.blocking_issues[0].kind == BlockingIssueKind.MISSING_TOOL

    def test_converts_integer_timestamps_untouched(self):
        """Test that integer timestamps are passed through without parsing."""
        item = {
            "skill_name": "test",
            "created_at": 1700000000,
            "updated_at": 1700000001,
        }

        skill = response_to_skill(item)

        assert skill.created_at == 1700000000
        assert skill.updated_at == 1700000001


# ===============================
# Tests for agent_success_evaluation_result_to_data
# ===============================


class TestAgentSuccessEvaluationResultToData:
    """Tests for agent_success_evaluation_result_to_data converter."""

    def test_converts_result_with_all_fields(self):
        """Test converting an AgentSuccessEvaluationResult with all fields."""
        result = AgentSuccessEvaluationResult(
            session_id="sess1",
            agent_version="v1",
            evaluation_name="eval1",
            is_success=True,
            failure_type="timeout",
            failure_reason="took too long",
            regular_vs_shadow=RegularVsShadow.REGULAR_IS_BETTER,
            number_of_correction_per_session=2,
            user_turns_to_resolution=3,
            is_escalated=True,
        )

        data = agent_success_evaluation_result_to_data(result)

        assert data["session_id"] == "sess1"
        assert data["agent_version"] == "v1"
        assert data["evaluation_name"] == "eval1"
        assert data["is_success"] is True
        assert data["failure_type"] == "timeout"
        assert data["failure_reason"] == "took too long"
        assert data["regular_vs_shadow"] == "regular_is_better"
        assert data["number_of_correction_per_session"] == 2
        assert data["user_turns_to_resolution"] == 3
        assert data["is_escalated"] is True
        assert data["embedding"] is None  # empty list -> None
        # result_id should not be in data
        assert "result_id" not in data

    def test_converts_result_with_none_optional_fields(self):
        """Test converting a result with None optional fields."""
        result = AgentSuccessEvaluationResult(
            session_id="sess2",
            agent_version="v1",
            is_success=False,
        )

        data = agent_success_evaluation_result_to_data(result)

        assert data["failure_type"] is None
        assert data["failure_reason"] is None
        assert data["regular_vs_shadow"] is None
        assert data["user_turns_to_resolution"] is None
        assert data["embedding"] is None  # empty list -> None


# ===============================
# Tests for extract_db_url_from_config_json
# ===============================


class TestExtractDbUrlFromConfigJson:
    """Tests for extract_db_url_from_config_json utility."""

    def test_extracts_valid_db_url(self):
        """Test extracting a valid db_url from config JSON."""
        config = '{"storage_config": {"db_url": "postgresql://user:pass@host:5432/db"}}'
        result = extract_db_url_from_config_json(config)
        assert result == "postgresql://user:pass@host:5432/db"

    def test_returns_none_for_missing_storage_config(self):
        """Test that missing storage_config returns None."""
        config = '{"other_config": {}}'
        result = extract_db_url_from_config_json(config)
        assert result is None

    def test_returns_none_for_missing_db_url(self):
        """Test that missing db_url in storage_config returns None."""
        config = '{"storage_config": {"other_key": "val"}}'
        result = extract_db_url_from_config_json(config)
        assert result is None

    def test_returns_none_for_empty_db_url(self):
        """Test that empty string db_url returns None."""
        config = '{"storage_config": {"db_url": ""}}'
        result = extract_db_url_from_config_json(config)
        assert result is None

    def test_returns_none_for_null_db_url(self):
        """Test that null db_url returns None."""
        config = '{"storage_config": {"db_url": null}}'
        result = extract_db_url_from_config_json(config)
        assert result is None

    def test_returns_none_for_invalid_json(self):
        """Test that invalid JSON returns None."""
        result = extract_db_url_from_config_json("not valid json")
        assert result is None

    def test_returns_none_for_empty_string(self):
        """Test that an empty string input returns None."""
        result = extract_db_url_from_config_json("")
        assert result is None


# ===============================
# Tests for get_latest_migration_version
# ===============================


class TestGetLatestMigrationVersion:
    """Tests for get_latest_migration_version utility."""

    def test_returns_version_string(self):
        """Test returning a numeric version prefix from actual migration files."""
        result = get_latest_migration_version()

        # Migration files exist in the repo, so we should get a version string
        assert result is not None
        # Version prefix should be all digits (e.g., "20240601120000")
        assert result.isdigit()
        assert len(result) == 14  # YYYYMMDDHHmmSS format


# ===============================
# Tests for check_migration_needed
# ===============================


class TestCheckMigrationNeeded:
    """Tests for check_migration_needed utility."""

    @patch("reflexio.server.services.storage.supabase_storage_utils.get_latest_migration_version")
    def test_returns_false_when_no_latest_version(self, mock_get_version):
        """Test returning False when there is no latest migration version."""
        mock_get_version.return_value = None
        assert check_migration_needed("postgresql://localhost/db") is False

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    @patch("reflexio.server.services.storage.supabase_storage_utils.get_latest_migration_version")
    def test_returns_true_when_migration_not_applied(self, mock_get_version, mock_psycopg2):
        """Test returning True when the latest migration is not in the DB."""
        mock_get_version.return_value = "20240601120000"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # migration not found
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        result = check_migration_needed("postgresql://localhost/db")

        assert result is True
        mock_conn.close.assert_called_once()

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    @patch("reflexio.server.services.storage.supabase_storage_utils.get_latest_migration_version")
    def test_returns_false_when_migration_applied(self, mock_get_version, mock_psycopg2):
        """Test returning False when the latest migration is already applied."""
        mock_get_version.return_value = "20240601120000"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # migration found
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        result = check_migration_needed("postgresql://localhost/db")

        assert result is False
        mock_conn.close.assert_called_once()

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    @patch("reflexio.server.services.storage.supabase_storage_utils.get_latest_migration_version")
    def test_returns_false_on_connection_error(self, mock_get_version, mock_psycopg2):
        """Test returning False when DB connection fails (fail-safe)."""
        mock_get_version.return_value = "20240601120000"
        mock_psycopg2.connect.side_effect = Exception("connection refused")

        result = check_migration_needed("postgresql://localhost/db")

        assert result is False


# ===============================
# Tests for execute_sql_file_direct
# ===============================


class TestExecuteSqlFileDirect:
    """Tests for execute_sql_file_direct utility."""

    def test_raises_on_empty_db_url(self):
        """Test that an empty db_url raises ValueError."""
        with pytest.raises(ValueError, match="Database URL is required"):
            execute_sql_file_direct("", "/path/to/file.sql")

    @patch("reflexio.server.services.storage.supabase_storage_utils.Path")
    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_executes_select_statements(self, mock_psycopg2, mock_path_cls):
        """Test executing SQL file with SELECT statements that return results."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("row1",), ("row2",)]
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        mock_file = MagicMock()
        mock_file.read.return_value = "SELECT 1; SELECT 2;"
        mock_path_cls.return_value.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_path_cls.return_value.open.return_value.__exit__ = MagicMock(return_value=False)

        results = execute_sql_file_direct("postgresql://localhost/db", "/path/to/file.sql")

        assert len(results) == 2
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("reflexio.server.services.storage.supabase_storage_utils.Path")
    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_non_select_statements(self, mock_psycopg2, mock_path_cls):
        """Test executing SQL file with INSERT/UPDATE statements that have no results."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = psycopg2.ProgrammingError("no results to fetch")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn
        mock_psycopg2.ProgrammingError = psycopg2.ProgrammingError

        mock_file = MagicMock()
        mock_file.read.return_value = "INSERT INTO t VALUES (1);"
        mock_path_cls.return_value.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_path_cls.return_value.open.return_value.__exit__ = MagicMock(return_value=False)

        results = execute_sql_file_direct("postgresql://localhost/db", "/path/to/file.sql")

        assert len(results) == 1
        assert "Executed:" in results[0]

    @patch("reflexio.server.services.storage.supabase_storage_utils.Path")
    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_raises_and_rolls_back_on_error(self, mock_psycopg2, mock_path_cls):
        """Test that errors cause rollback and re-raise."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("syntax error")
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        mock_file = MagicMock()
        mock_file.read.return_value = "BAD SQL;"
        mock_path_cls.return_value.open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_path_cls.return_value.open.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(Exception, match="syntax error"):
            execute_sql_file_direct("postgresql://localhost/db", "/path/to/file.sql")


# ===============================
# Tests for execute_migration
# ===============================


class TestExecuteMigration:
    """Tests for execute_migration utility."""

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_skips_already_applied_migrations(self, mock_psycopg2):
        """Test that already-applied migrations are skipped, returning success."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Every fetchone returns a row -> all migrations already applied
        mock_cursor.fetchone.return_value = ("some_version",)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is True
        assert "All migrations already applied" in msg
        mock_conn.commit.assert_called_once()

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_executes_pending_migrations(self, mock_psycopg2):
        """Test executing pending migrations (not yet applied)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # fetchone returns None -> migration not applied, needs execution
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is True
        assert "Executed migrations:" in msg
        mock_conn.commit.assert_called_once()

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_dns_resolution_error(self, mock_psycopg2):
        """Test handling DNS resolution failure."""
        mock_psycopg2.connect.side_effect = psycopg2.OperationalError(
            "could not translate host name"
        )
        mock_psycopg2.OperationalError = psycopg2.OperationalError

        success, msg = execute_migration("postgresql://bad-host/db")

        assert success is False
        assert "DNS resolution failed" in msg

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_connection_refused_error(self, mock_psycopg2):
        """Test handling connection refused error."""
        mock_psycopg2.connect.side_effect = psycopg2.OperationalError(
            "Connection refused"
        )
        mock_psycopg2.OperationalError = psycopg2.OperationalError

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is False
        assert "Connection refused" in msg

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_generic_operational_error(self, mock_psycopg2):
        """Test handling a generic OperationalError."""
        mock_psycopg2.connect.side_effect = psycopg2.OperationalError(
            "some other error"
        )
        mock_psycopg2.OperationalError = psycopg2.OperationalError

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is False
        assert "Database connection error" in msg

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_generic_exception(self, mock_psycopg2):
        """Test handling a generic Exception during migration."""
        mock_psycopg2.connect.side_effect = RuntimeError("unexpected")
        mock_psycopg2.OperationalError = psycopg2.OperationalError

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is False
        assert "unexpected" in msg

    @patch("reflexio.server.services.storage.supabase_storage_utils.psycopg2")
    def test_handles_migration_execution_failure(self, mock_psycopg2):
        """Test handling a failure during migration SQL execution."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # fetchone returns None -> migration not yet applied
        mock_cursor.fetchone.return_value = None
        call_count = 0

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First two calls: CREATE SCHEMA, CREATE TABLE
            # Third: version check SELECT
            # Fourth: actual migration SQL -> fail
            if call_count >= 4:
                raise Exception("syntax error in SQL")

        mock_cursor.execute.side_effect = execute_side_effect
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        success, msg = execute_migration("postgresql://localhost/db")

        assert success is False
        assert "Failed to execute" in msg
        mock_conn.rollback.assert_called_once()


# ===============================
# Tests for get_organization_config
# ===============================


class TestGetOrganizationConfig:
    """Tests for get_organization_config utility."""

    def test_returns_config_json_string(self):
        """Test returning the configuration_json for a found organization."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"configuration_json": "encrypted_data"}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_organization_config(mock_client, "org1")

        assert result == "encrypted_data"

    def test_returns_none_when_no_data(self):
        """Test returning None when organization is not found."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_organization_config(mock_client, "nonexistent")

        assert result is None

    def test_returns_none_when_row_not_dict(self):
        """Test returning None when the row is not a dict."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = ["not_a_dict"]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_organization_config(mock_client, "org1")

        assert result is None

    def test_returns_none_when_config_value_is_none(self):
        """Test returning None when configuration_json value is None."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"configuration_json": None}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_organization_config(mock_client, "org1")

        assert result is None


# ===============================
# Tests for set_organization_config
# ===============================


class TestSetOrganizationConfig:
    """Tests for set_organization_config utility."""

    def test_updates_existing_organization(self):
        """Test updating the configuration_json for an existing organization."""
        mock_client = MagicMock()
        # First call: check if org exists
        mock_check_response = MagicMock()
        mock_check_response.data = [{"id": "org1"}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_check_response

        result = set_organization_config(mock_client, "org1", "new_config")

        assert result is True

    def test_returns_false_when_org_not_found(self):
        """Test returning False when the organization does not exist."""
        mock_client = MagicMock()
        mock_check_response = MagicMock()
        mock_check_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_check_response

        result = set_organization_config(mock_client, "nonexistent", "config")

        assert result is False
