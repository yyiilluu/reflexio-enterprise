"""Tests for LocalJsonStorage covering CRUD, search, bulk, status, and edge cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from reflexio.server.services.storage.error import StorageError
from reflexio.server.services.storage.local_json_storage import LocalJsonStorage
from reflexio_commons.api_schema.retriever_schema import (
    SearchFeedbackRequest,
    SearchInteractionRequest,
    SearchRawFeedbackRequest,
    SearchSkillsRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    NEVER_EXPIRES_TIMESTAMP,
    AgentSuccessEvaluationResult,
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
    Feedback,
    FeedbackAggregationChangeLog,
    FeedbackStatus,
    Interaction,
    ProfileChangeLog,
    ProfileTimeToLive,
    RawFeedback,
    Request,
    Skill,
    SkillStatus,
    Status,
    UserActionType,
    UserProfile,
)
from reflexio_commons.config_schema import StorageConfigLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ts() -> int:
    return int(datetime.now(UTC).timestamp())


def _make_profile(
    user_id: str = "user1",
    profile_id: str = "p1",
    content: str = "likes sushi",
    *,
    status: Status | None = None,
    ttl: ProfileTimeToLive = ProfileTimeToLive.INFINITY,
    request_id: str = "req1",
    source: str = "test",
    timestamp: int | None = None,
) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        profile_id=profile_id,
        profile_content=content,
        last_modified_timestamp=timestamp or _now_ts(),
        generated_from_request_id=request_id,
        profile_time_to_live=ttl,
        expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
        source=source,
        status=status,
    )


def _make_interaction(
    user_id: str = "user1",
    request_id: str = "req1",
    content: str = "hello",
    interaction_id: int = 0,
    created_at: int | None = None,
) -> Interaction:
    return Interaction(
        interaction_id=interaction_id,
        user_id=user_id,
        request_id=request_id,
        content=content,
        created_at=created_at or _now_ts(),
        user_action=UserActionType.NONE,
    )


def _make_request(
    request_id: str = "req1",
    user_id: str = "user1",
    session_id: str | None = "session1",
    source: str = "api",
    agent_version: str = "v1",
    created_at: int | None = None,
) -> Request:
    return Request(
        request_id=request_id,
        user_id=user_id,
        created_at=created_at or _now_ts(),
        source=source,
        agent_version=agent_version,
        session_id=session_id,
    )


def _make_raw_feedback(
    request_id: str = "req1",
    feedback_name: str = "fb",
    agent_version: str = "v1",
    content: str = "feedback content",
    *,
    status: Status | None = None,
    user_id: str | None = "user1",
    created_at: int | None = None,
) -> RawFeedback:
    return RawFeedback(
        user_id=user_id,
        agent_version=agent_version,
        request_id=request_id,
        feedback_name=feedback_name,
        created_at=created_at or _now_ts(),
        feedback_content=content,
        status=status,
    )


def _make_feedback(
    feedback_name: str = "fb",
    agent_version: str = "v1",
    content: str = "do X when Y",
    *,
    feedback_status: FeedbackStatus = FeedbackStatus.PENDING,
    status: Status | None = None,
    created_at: int | None = None,
) -> Feedback:
    return Feedback(
        feedback_name=feedback_name,
        agent_version=agent_version,
        created_at=created_at or _now_ts(),
        feedback_content=content,
        feedback_status=feedback_status,
        status=status,
    )


def _make_skill(
    skill_name: str = "greet",
    feedback_name: str = "fb",
    agent_version: str = "v1",
    instructions: str = "Say hello to the user",
    description: str = "Greeting skill",
    skill_status: SkillStatus = SkillStatus.DRAFT,
) -> Skill:
    return Skill(
        skill_name=skill_name,
        feedback_name=feedback_name,
        agent_version=agent_version,
        instructions=instructions,
        description=description,
        skill_status=skill_status,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage(tmp_path):
    """Create a fresh LocalJsonStorage backed by a temporary directory."""
    return LocalJsonStorage(org_id="test_org", base_dir=str(tmp_path))


# ===========================================================================
# Constructor / initialisation
# ===========================================================================


class TestInit:
    def test_creates_json_file(self, tmp_path):
        LocalJsonStorage(org_id="org1", base_dir=str(tmp_path))
        json_file = tmp_path / "user_profiles_org1.json"
        assert json_file.exists()

    def test_config_with_absolute_dir(self, tmp_path):
        cfg = StorageConfigLocal(dir_path=str(tmp_path))
        s = LocalJsonStorage(org_id="org1", config=cfg)
        assert s.base_dir == str(tmp_path)

    def test_config_with_relative_dir_raises(self):
        cfg = StorageConfigLocal(dir_path="relative/path")
        with pytest.raises(StorageError):
            LocalJsonStorage(org_id="org1", config=cfg)

    def test_base_dir_not_a_dir_raises(self, tmp_path):
        file_path = tmp_path / "afile.txt"
        file_path.write_text("x")
        with pytest.raises(StorageError):
            LocalJsonStorage(org_id="org1", base_dir=str(file_path))


# ===========================================================================
# Profile CRUD
# ===========================================================================


class TestProfileCRUD:
    def test_add_and_get_user_profile(self, storage):
        p = _make_profile()
        storage.add_user_profile("user1", [p])
        profiles = storage.get_user_profile("user1")
        assert len(profiles) == 1
        assert profiles[0].profile_content == "likes sushi"
        assert profiles[0].source == "test"

    def test_get_user_profile_missing_user(self, storage):
        assert storage.get_user_profile("no_such_user") == []

    def test_get_all_profiles(self, storage):
        storage.add_user_profile("u1", [_make_profile(user_id="u1", profile_id="p1")])
        storage.add_user_profile(
            "u2", [_make_profile(user_id="u2", profile_id="p2", content="likes pizza")]
        )
        profiles = storage.get_all_profiles()
        assert len(profiles) == 2

    def test_get_all_profiles_limit(self, storage):
        for i in range(5):
            storage.add_user_profile(
                f"u{i}",
                [_make_profile(user_id=f"u{i}", profile_id=f"p{i}")],
            )
        assert len(storage.get_all_profiles(limit=3)) == 3

    def test_delete_user_profile(self, storage):
        storage.add_user_profile("user1", [_make_profile()])
        storage.delete_user_profile(
            DeleteUserProfileRequest(user_id="user1", profile_id="p1")
        )
        assert storage.get_user_profile("user1") == []

    def test_delete_user_profile_missing_user(self, storage):
        # Should not raise
        storage.delete_user_profile(
            DeleteUserProfileRequest(user_id="nope", profile_id="p1")
        )

    def test_update_user_profile_by_id(self, storage):
        storage.add_user_profile("user1", [_make_profile()])
        updated = _make_profile(content="likes ramen")
        storage.update_user_profile_by_id("user1", "p1", updated)
        profiles = storage.get_user_profile("user1")
        assert profiles[0].profile_content == "likes ramen"

    def test_update_user_profile_missing_user(self, storage):
        # Should not raise
        storage.update_user_profile_by_id("nope", "p1", _make_profile())

    def test_delete_all_profiles_for_user(self, storage):
        storage.add_user_profile(
            "user1", [_make_profile(), _make_profile(profile_id="p2")]
        )
        storage.delete_all_profiles_for_user("user1")
        assert storage.get_user_profile("user1") == []

    def test_delete_all_profiles_for_user_missing(self, storage):
        storage.delete_all_profiles_for_user("nope")

    def test_delete_all_profiles(self, storage):
        storage.add_user_profile("u1", [_make_profile(user_id="u1")])
        storage.add_user_profile("u2", [_make_profile(user_id="u2", profile_id="p2")])
        storage.delete_all_profiles()
        assert storage.get_all_profiles() == []

    def test_delete_profiles_by_ids(self, storage):
        storage.add_user_profile("u1", [_make_profile(user_id="u1", profile_id="p1")])
        storage.add_user_profile("u1", [_make_profile(user_id="u1", profile_id="p2")])
        deleted = storage.delete_profiles_by_ids(["p1"])
        assert deleted == 1
        remaining = storage.get_user_profile("u1")
        assert len(remaining) == 1
        assert remaining[0].profile_id == "p2"

    def test_delete_profiles_by_ids_empty(self, storage):
        assert storage.delete_profiles_by_ids([]) == 0


# ===========================================================================
# Profile status management
# ===========================================================================


class TestProfileStatus:
    def test_get_profiles_with_status_filter(self, storage):
        storage.add_user_profile("u1", [_make_profile(status=None)])
        storage.add_user_profile(
            "u1",
            [
                _make_profile(profile_id="p2", status=Status.PENDING),
            ],
        )
        current = storage.get_user_profile("u1", status_filter=[None])
        assert len(current) == 1
        pending = storage.get_user_profile("u1", status_filter=[Status.PENDING])
        assert len(pending) == 1

    def test_update_all_profiles_status(self, storage):
        storage.add_user_profile("u1", [_make_profile()])
        storage.add_user_profile("u2", [_make_profile(user_id="u2", profile_id="p2")])
        count = storage.update_all_profiles_status(
            old_status=None, new_status=Status.PENDING
        )
        assert count == 2
        pending = storage.get_all_profiles(status_filter=[Status.PENDING])
        assert len(pending) == 2

    def test_update_all_profiles_status_with_user_ids_filter(self, storage):
        storage.add_user_profile("u1", [_make_profile(user_id="u1")])
        storage.add_user_profile("u2", [_make_profile(user_id="u2", profile_id="p2")])
        count = storage.update_all_profiles_status(
            old_status=None,
            new_status=Status.PENDING,
            user_ids=["u1"],
        )
        assert count == 1
        # u2 unchanged
        current_u2 = storage.get_user_profile("u2", status_filter=[None])
        assert len(current_u2) == 1

    def test_delete_all_profiles_by_status(self, storage):
        storage.add_user_profile("u1", [_make_profile(status=Status.ARCHIVED)])
        storage.add_user_profile("u1", [_make_profile(profile_id="p2", status=None)])
        deleted = storage.delete_all_profiles_by_status(Status.ARCHIVED)
        assert deleted == 1
        assert len(storage.get_all_profiles(status_filter=[None, Status.ARCHIVED])) == 1

    def test_get_user_ids_with_status(self, storage):
        storage.add_user_profile("u1", [_make_profile(user_id="u1")])
        storage.add_user_profile(
            "u2", [_make_profile(user_id="u2", profile_id="p2", status=Status.PENDING)]
        )
        ids_current = storage.get_user_ids_with_status(None)
        assert "u1" in ids_current
        assert "u2" not in ids_current
        ids_pending = storage.get_user_ids_with_status(Status.PENDING)
        assert "u2" in ids_pending

    def test_get_profile_statistics(self, storage):
        storage.add_user_profile("u1", [_make_profile(status=None)])
        storage.add_user_profile(
            "u1", [_make_profile(profile_id="p2", status=Status.PENDING)]
        )
        storage.add_user_profile(
            "u1", [_make_profile(profile_id="p3", status=Status.ARCHIVED)]
        )
        stats = storage.get_profile_statistics()
        assert stats["current_count"] == 1
        assert stats["pending_count"] == 1
        assert stats["archived_count"] == 1


# ===========================================================================
# Interaction CRUD
# ===========================================================================


class TestInteractionCRUD:
    def test_add_and_get_user_interaction(self, storage):
        i = _make_interaction(interaction_id=1)
        storage.add_user_interaction("user1", i)
        interactions = storage.get_user_interaction("user1")
        assert len(interactions) == 1
        assert interactions[0].content == "hello"

    def test_get_user_interaction_missing(self, storage):
        assert storage.get_user_interaction("nope") == []

    def test_auto_increment_interaction_id(self, storage):
        storage.add_user_interaction("user1", _make_interaction(interaction_id=0))
        interactions = storage.get_user_interaction("user1")
        assert interactions[0].interaction_id == 1

    def test_get_all_interactions(self, storage):
        storage.add_user_interaction(
            "u1", _make_interaction(user_id="u1", interaction_id=1)
        )
        storage.add_user_interaction(
            "u2", _make_interaction(user_id="u2", interaction_id=2)
        )
        assert len(storage.get_all_interactions()) == 2

    def test_get_all_interactions_limit(self, storage):
        for i in range(5):
            storage.add_user_interaction("u1", _make_interaction(interaction_id=i + 1))
        assert len(storage.get_all_interactions(limit=3)) == 3

    def test_add_user_interactions_bulk(self, storage):
        interactions = [
            _make_interaction(content="a"),
            _make_interaction(content="b"),
        ]
        storage.add_user_interactions_bulk("user1", interactions)
        result = storage.get_user_interaction("user1")
        assert len(result) == 2

    def test_add_user_interactions_bulk_empty(self, storage):
        storage.add_user_interactions_bulk("user1", [])
        assert storage.get_user_interaction("user1") == []

    def test_delete_user_interaction(self, storage):
        storage.add_user_interaction("user1", _make_interaction(interaction_id=1))
        storage.delete_user_interaction(
            DeleteUserInteractionRequest(user_id="user1", interaction_id=1),
        )
        assert storage.get_user_interaction("user1") == []

    def test_delete_user_interaction_missing_user(self, storage):
        storage.delete_user_interaction(
            DeleteUserInteractionRequest(user_id="nope", interaction_id=1),
        )

    def test_delete_all_interactions_for_user(self, storage):
        storage.add_user_interaction("user1", _make_interaction(interaction_id=1))
        storage.add_user_interaction("user1", _make_interaction(interaction_id=2))
        storage.delete_all_interactions_for_user("user1")
        assert storage.get_user_interaction("user1") == []

    def test_delete_all_interactions_for_user_missing(self, storage):
        storage.delete_all_interactions_for_user("nope")

    def test_delete_all_interactions(self, storage):
        storage.add_user_interaction(
            "u1", _make_interaction(user_id="u1", interaction_id=1)
        )
        storage.add_user_interaction(
            "u2", _make_interaction(user_id="u2", interaction_id=2)
        )
        storage.delete_all_interactions()
        assert storage.get_all_interactions() == []

    def test_count_all_interactions(self, storage):
        assert storage.count_all_interactions() == 0
        storage.add_user_interaction("u1", _make_interaction(interaction_id=1))
        storage.add_user_interaction(
            "u2", _make_interaction(user_id="u2", interaction_id=2)
        )
        assert storage.count_all_interactions() == 2

    def test_delete_oldest_interactions(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=1, created_at=now - 100),
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=2, created_at=now - 50),
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=3, created_at=now),
        )
        deleted = storage.delete_oldest_interactions(2)
        assert deleted == 2
        remaining = storage.get_user_interaction("u1")
        assert len(remaining) == 1
        assert remaining[0].interaction_id == 3

    def test_delete_oldest_interactions_zero(self, storage):
        storage.add_user_interaction("u1", _make_interaction(interaction_id=1))
        assert storage.delete_oldest_interactions(0) == 0

    def test_delete_oldest_interactions_empty(self, storage):
        assert storage.delete_oldest_interactions(5) == 0

    def test_get_interactions_by_request_ids(self, storage):
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r1", interaction_id=1)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r2", interaction_id=2)
        )
        result = storage.get_interactions_by_request_ids(["r1"])
        assert len(result) == 1
        assert result[0].request_id == "r1"

    def test_get_interactions_by_request_ids_empty(self, storage):
        assert storage.get_interactions_by_request_ids([]) == []


# ===========================================================================
# Request CRUD
# ===========================================================================


class TestRequestCRUD:
    def test_add_and_get_request(self, storage):
        r = _make_request()
        storage.add_request(r)
        fetched = storage.get_request("req1")
        assert fetched is not None
        assert fetched.user_id == "user1"

    def test_get_request_missing(self, storage):
        assert storage.get_request("nope") is None

    def test_add_request_upsert(self, storage):
        storage.add_request(_make_request(source="api"))
        storage.add_request(_make_request(source="web"))
        fetched = storage.get_request("req1")
        assert fetched is not None
        assert fetched.source == "web"

    def test_delete_request(self, storage):
        storage.add_request(_make_request())
        storage.add_user_interaction(
            "user1", _make_interaction(request_id="req1", interaction_id=1)
        )
        storage.delete_request("req1")
        assert storage.get_request("req1") is None
        # Associated interactions also deleted
        assert storage.get_user_interaction("user1") == []

    def test_delete_session(self, storage):
        storage.add_request(_make_request(request_id="r1", session_id="s1"))
        storage.add_request(_make_request(request_id="r2", session_id="s1"))
        storage.add_request(_make_request(request_id="r3", session_id="s2"))
        storage.add_user_interaction(
            "user1", _make_interaction(request_id="r1", interaction_id=1)
        )
        storage.add_user_interaction(
            "user1", _make_interaction(request_id="r2", interaction_id=2)
        )
        deleted = storage.delete_session("s1")
        assert deleted == 2
        assert storage.get_request("r1") is None
        assert storage.get_request("r3") is not None
        # r1 and r2 interactions deleted, r3 kept unaffected
        remaining = storage.get_user_interaction("user1")
        assert all(i.request_id not in ("r1", "r2") for i in remaining)

    def test_delete_session_missing(self, storage):
        assert storage.delete_session("nope") == 0

    def test_delete_all_requests(self, storage):
        storage.add_request(_make_request())
        storage.add_user_interaction("user1", _make_interaction(interaction_id=1))
        storage.delete_all_requests()
        assert storage.get_request("req1") is None
        assert storage.get_user_interaction("user1") == []

    def test_delete_requests_by_ids(self, storage):
        storage.add_request(_make_request(request_id="r1"))
        storage.add_request(_make_request(request_id="r2"))
        storage.add_user_interaction(
            "user1", _make_interaction(request_id="r1", interaction_id=1)
        )
        deleted = storage.delete_requests_by_ids(["r1"])
        assert deleted == 1
        assert storage.get_request("r1") is None
        assert storage.get_request("r2") is not None

    def test_delete_requests_by_ids_empty(self, storage):
        assert storage.delete_requests_by_ids([]) == 0

    def test_get_requests_by_session(self, storage):
        storage.add_request(_make_request(request_id="r1", session_id="s1"))
        storage.add_request(_make_request(request_id="r2", session_id="s2"))
        results = storage.get_requests_by_session("user1", "s1")
        assert len(results) == 1
        assert results[0].request_id == "r1"

    def test_get_requests_by_session_empty(self, storage):
        assert storage.get_requests_by_session("u1", "none") == []

    def test_get_sessions(self, storage):
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id="s1", created_at=now)
        )
        storage.add_user_interaction(
            "user1", _make_interaction(request_id="r1", interaction_id=1)
        )
        sessions = storage.get_sessions(user_id="user1")
        assert "s1" in sessions
        assert len(sessions["s1"]) == 1

    def test_get_sessions_with_filters(self, storage):
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id="s1", created_at=now - 100)
        )
        storage.add_request(
            _make_request(request_id="r2", session_id="s1", created_at=now)
        )
        sessions = storage.get_sessions(
            user_id="user1",
            session_id="s1",
            start_time=now - 50,
            end_time=now + 50,
        )
        assert "s1" in sessions
        assert len(sessions["s1"]) == 1
        assert sessions["s1"][0].request.request_id == "r2"

    def test_get_sessions_empty(self, storage):
        assert storage.get_sessions(user_id="u1") == {}

    def test_get_rerun_user_ids(self, storage):
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", user_id="u1", source="api", created_at=now)
        )
        storage.add_request(
            _make_request(request_id="r2", user_id="u2", source="web", created_at=now)
        )
        result = storage.get_rerun_user_ids(source="api")
        assert result == ["u1"]

    def test_get_rerun_user_ids_empty(self, storage):
        assert storage.get_rerun_user_ids() == []


# ===========================================================================
# Raw Feedback CRUD
# ===========================================================================


class TestRawFeedbackCRUD:
    def test_save_and_get_raw_feedbacks(self, storage):
        fb = _make_raw_feedback()
        storage.save_raw_feedbacks([fb])
        result = storage.get_raw_feedbacks()
        assert len(result) == 1
        assert result[0].feedback_content == "feedback content"

    def test_raw_feedback_auto_id(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback()])
        result = storage.get_raw_feedbacks()
        assert result[0].raw_feedback_id == 1

    def test_get_raw_feedbacks_with_filters(self, storage):
        now = _now_ts()
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(
                    feedback_name="fb1",
                    agent_version="v1",
                    user_id="u1",
                    created_at=now - 100,
                ),
                _make_raw_feedback(
                    feedback_name="fb2",
                    agent_version="v2",
                    user_id="u2",
                    created_at=now,
                ),
            ]
        )
        # Filter by user_id
        result = storage.get_raw_feedbacks(user_id="u1")
        assert len(result) == 1

        # Filter by feedback_name
        result = storage.get_raw_feedbacks(feedback_name="fb2")
        assert len(result) == 1

        # Filter by agent_version
        result = storage.get_raw_feedbacks(agent_version="v1")
        assert len(result) == 1

        # Filter by time range
        result = storage.get_raw_feedbacks(start_time=now - 50, end_time=now + 50)
        assert len(result) == 1

    def test_get_raw_feedbacks_limit(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback() for _ in range(5)])
        assert len(storage.get_raw_feedbacks(limit=3)) == 3

    def test_get_raw_feedbacks_empty(self, storage):
        assert storage.get_raw_feedbacks() == []

    def test_get_raw_feedbacks_status_filter(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="current", status=None),
                _make_raw_feedback(content="pending", status=Status.PENDING),
            ]
        )
        result = storage.get_raw_feedbacks(status_filter=[None])
        assert len(result) == 1
        assert result[0].feedback_content == "current"

    def test_delete_raw_feedback(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback()])
        fb_id = storage.get_raw_feedbacks()[0].raw_feedback_id
        storage.delete_raw_feedback(fb_id)
        assert storage.get_raw_feedbacks() == []

    def test_delete_raw_feedback_missing(self, storage):
        # Should not raise
        storage.delete_raw_feedback(999)

    def test_delete_all_raw_feedbacks(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback(), _make_raw_feedback()])
        storage.delete_all_raw_feedbacks()
        assert storage.get_raw_feedbacks() == []

    def test_delete_all_raw_feedbacks_by_feedback_name(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(feedback_name="fb1"),
                _make_raw_feedback(feedback_name="fb2"),
            ]
        )
        storage.delete_all_raw_feedbacks_by_feedback_name("fb1")
        result = storage.get_raw_feedbacks()
        assert len(result) == 1
        assert result[0].feedback_name == "fb2"

    def test_delete_all_raw_feedbacks_by_feedback_name_with_version(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(feedback_name="fb1", agent_version="v1"),
                _make_raw_feedback(feedback_name="fb1", agent_version="v2"),
            ]
        )
        storage.delete_all_raw_feedbacks_by_feedback_name("fb1", agent_version="v1")
        result = storage.get_raw_feedbacks()
        assert len(result) == 1
        assert result[0].agent_version == "v2"

    def test_count_raw_feedbacks(self, storage):
        assert storage.count_raw_feedbacks() == 0
        storage.save_raw_feedbacks([_make_raw_feedback(), _make_raw_feedback()])
        assert storage.count_raw_feedbacks() == 2

    def test_count_raw_feedbacks_with_filters(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(
                    feedback_name="fb1", agent_version="v1", user_id="u1"
                ),
                _make_raw_feedback(
                    feedback_name="fb2", agent_version="v2", user_id="u2"
                ),
            ]
        )
        assert storage.count_raw_feedbacks(user_id="u1") == 1
        assert storage.count_raw_feedbacks(feedback_name="fb1") == 1
        assert storage.count_raw_feedbacks(agent_version="v1") == 1

    def test_count_raw_feedbacks_min_id(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback(), _make_raw_feedback()])
        assert storage.count_raw_feedbacks(min_raw_feedback_id=1) == 1

    def test_count_raw_feedbacks_by_session(self, storage):
        storage.add_request(_make_request(request_id="r1", session_id="s1"))
        storage.save_raw_feedbacks([_make_raw_feedback(request_id="r1")])
        assert storage.count_raw_feedbacks_by_session("s1") == 1
        assert storage.count_raw_feedbacks_by_session("s2") == 0

    def test_delete_raw_feedbacks_by_ids(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback()])
        fb_id = storage.get_raw_feedbacks()[0].raw_feedback_id
        # Local storage returns 0 (not supported)
        result = storage.delete_raw_feedbacks_by_ids([fb_id])
        assert result == 0


# ===========================================================================
# Raw Feedback status management
# ===========================================================================


class TestRawFeedbackStatus:
    def test_update_all_raw_feedbacks_status(self, storage):
        storage.save_raw_feedbacks([_make_raw_feedback(), _make_raw_feedback()])
        count = storage.update_all_raw_feedbacks_status(
            old_status=None, new_status=Status.PENDING
        )
        assert count == 2
        result = storage.get_raw_feedbacks(status_filter=[Status.PENDING])
        assert len(result) == 2

    def test_update_all_raw_feedbacks_status_with_filters(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(feedback_name="fb1", agent_version="v1"),
                _make_raw_feedback(feedback_name="fb2", agent_version="v2"),
            ]
        )
        count = storage.update_all_raw_feedbacks_status(
            old_status=None,
            new_status=Status.PENDING,
            agent_version="v1",
            feedback_name="fb1",
        )
        assert count == 1

    def test_delete_all_raw_feedbacks_by_status(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(status=Status.PENDING),
                _make_raw_feedback(status=None),
            ]
        )
        deleted = storage.delete_all_raw_feedbacks_by_status(Status.PENDING)
        assert deleted == 1
        assert len(storage.get_raw_feedbacks()) == 1

    def test_delete_all_raw_feedbacks_by_status_with_filters(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(status=Status.PENDING, agent_version="v1"),
                _make_raw_feedback(status=Status.PENDING, agent_version="v2"),
            ]
        )
        deleted = storage.delete_all_raw_feedbacks_by_status(
            Status.PENDING,
            agent_version="v1",
        )
        assert deleted == 1
        assert len(storage.get_raw_feedbacks()) == 1

    def test_has_raw_feedbacks_with_status(self, storage):
        assert storage.has_raw_feedbacks_with_status(None) is False
        storage.save_raw_feedbacks([_make_raw_feedback()])
        assert storage.has_raw_feedbacks_with_status(None) is True
        assert storage.has_raw_feedbacks_with_status(Status.PENDING) is False

    def test_has_raw_feedbacks_with_status_filters(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(agent_version="v1", feedback_name="fb1"),
            ]
        )
        assert storage.has_raw_feedbacks_with_status(None, agent_version="v1") is True
        assert storage.has_raw_feedbacks_with_status(None, agent_version="v2") is False
        assert storage.has_raw_feedbacks_with_status(None, feedback_name="fb1") is True
        assert (
            storage.has_raw_feedbacks_with_status(None, feedback_name="other") is False
        )


# ===========================================================================
# Feedback CRUD
# ===========================================================================


class TestFeedbackCRUD:
    def test_save_and_get_feedbacks(self, storage):
        fb = _make_feedback()
        saved = storage.save_feedbacks([fb])
        assert saved[0].feedback_id == 1
        result = storage.get_feedbacks()
        assert len(result) == 1
        assert result[0].feedback_content == "do X when Y"

    def test_get_feedbacks_empty(self, storage):
        assert storage.get_feedbacks() == []

    def test_get_feedbacks_excludes_archived_by_default(self, storage):
        storage.save_feedbacks([_make_feedback(content="current")])
        storage.save_feedbacks([_make_feedback(content="old", status=Status.ARCHIVED)])
        result = storage.get_feedbacks()
        assert len(result) == 1
        assert result[0].feedback_content == "current"

    def test_get_feedbacks_with_status_filter(self, storage):
        storage.save_feedbacks([_make_feedback(status=None)])
        storage.save_feedbacks([_make_feedback(status=Status.ARCHIVED)])
        result = storage.get_feedbacks(status_filter=[Status.ARCHIVED])
        assert len(result) == 1

    def test_get_feedbacks_with_feedback_status_filter(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_status=FeedbackStatus.PENDING)])
        storage.save_feedbacks(
            [_make_feedback(feedback_status=FeedbackStatus.APPROVED)]
        )
        result = storage.get_feedbacks(feedback_status_filter=[FeedbackStatus.APPROVED])
        assert len(result) == 1

    def test_get_feedbacks_with_name_filter(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_name="fb1")])
        storage.save_feedbacks([_make_feedback(feedback_name="fb2")])
        result = storage.get_feedbacks(feedback_name="fb1")
        assert len(result) == 1

    def test_get_feedbacks_limit(self, storage):
        storage.save_feedbacks([_make_feedback() for _ in range(5)])
        assert len(storage.get_feedbacks(limit=3)) == 3

    def test_delete_feedback(self, storage):
        storage.save_feedbacks([_make_feedback()])
        fb_id = storage.get_feedbacks()[0].feedback_id
        storage.delete_feedback(fb_id)
        assert storage.get_feedbacks() == []

    def test_delete_feedback_missing(self, storage):
        storage.delete_feedback(999)

    def test_delete_all_feedbacks(self, storage):
        storage.save_feedbacks([_make_feedback(), _make_feedback()])
        storage.delete_all_feedbacks()
        assert storage.get_feedbacks() == []

    def test_delete_all_feedbacks_by_feedback_name(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_name="fb1")])
        storage.save_feedbacks([_make_feedback(feedback_name="fb2")])
        storage.delete_all_feedbacks_by_feedback_name("fb1")
        result = storage.get_feedbacks()
        assert len(result) == 1
        assert result[0].feedback_name == "fb2"

    def test_delete_feedbacks_by_ids(self, storage):
        storage.save_feedbacks([_make_feedback(), _make_feedback()])
        fbs = storage.get_feedbacks()
        storage.delete_feedbacks_by_ids([fbs[0].feedback_id])
        assert len(storage.get_feedbacks()) == 1

    def test_delete_feedbacks_by_ids_empty(self, storage):
        storage.delete_feedbacks_by_ids([])

    def test_update_feedback_status(self, storage):
        storage.save_feedbacks([_make_feedback()])
        fb_id = storage.get_feedbacks()[0].feedback_id
        storage.update_feedback_status(fb_id, FeedbackStatus.APPROVED)
        result = storage.get_feedbacks()
        assert result[0].feedback_status == FeedbackStatus.APPROVED

    def test_update_feedback_status_not_found(self, storage):
        with pytest.raises(ValueError, match="not found"):
            storage.update_feedback_status(999, FeedbackStatus.APPROVED)

    def test_update_feedback_status_no_feedbacks_key(self, storage):
        with pytest.raises(ValueError, match="not found"):
            storage.update_feedback_status(1, FeedbackStatus.APPROVED)


# ===========================================================================
# Feedback archive/restore
# ===========================================================================


class TestFeedbackArchive:
    def test_archive_feedbacks_by_feedback_name(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_name="fb1")])
        storage.archive_feedbacks_by_feedback_name("fb1")
        # Archived should not appear in default get
        assert storage.get_feedbacks() == []
        archived = storage.get_feedbacks(status_filter=[Status.ARCHIVED, "archived"])
        assert len(archived) == 1

    def test_archive_skips_approved(self, storage):
        storage.save_feedbacks(
            [
                _make_feedback(
                    feedback_name="fb1", feedback_status=FeedbackStatus.APPROVED
                ),
            ]
        )
        storage.archive_feedbacks_by_feedback_name("fb1")
        # Approved feedback should still appear
        result = storage.get_feedbacks()
        assert len(result) == 1

    def test_restore_archived_feedbacks_by_feedback_name(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_name="fb1")])
        storage.archive_feedbacks_by_feedback_name("fb1")
        storage.restore_archived_feedbacks_by_feedback_name("fb1")
        result = storage.get_feedbacks()
        assert len(result) == 1

    def test_delete_archived_feedbacks_by_feedback_name(self, storage):
        storage.save_feedbacks([_make_feedback(feedback_name="fb1")])
        storage.archive_feedbacks_by_feedback_name("fb1")
        storage.delete_archived_feedbacks_by_feedback_name("fb1")
        # Gone entirely
        assert (
            storage.get_feedbacks(status_filter=[Status.ARCHIVED, "archived", None])
            == []
        )

    def test_archive_feedbacks_by_ids(self, storage):
        storage.save_feedbacks([_make_feedback(), _make_feedback()])
        fbs = storage.get_feedbacks()
        storage.archive_feedbacks_by_ids([fbs[0].feedback_id])
        remaining = storage.get_feedbacks()
        assert len(remaining) == 1

    def test_archive_feedbacks_by_ids_empty(self, storage):
        storage.archive_feedbacks_by_ids([])

    def test_restore_archived_feedbacks_by_ids(self, storage):
        storage.save_feedbacks([_make_feedback()])
        fbs = storage.get_feedbacks()
        storage.archive_feedbacks_by_ids([fbs[0].feedback_id])
        storage.restore_archived_feedbacks_by_ids([fbs[0].feedback_id])
        assert len(storage.get_feedbacks()) == 1

    def test_restore_archived_feedbacks_by_ids_empty(self, storage):
        storage.restore_archived_feedbacks_by_ids([])

    def test_archive_no_feedbacks_key(self, storage):
        storage.archive_feedbacks_by_feedback_name("fb1")

    def test_restore_no_feedbacks_key(self, storage):
        storage.restore_archived_feedbacks_by_feedback_name("fb1")

    def test_delete_archived_no_feedbacks_key(self, storage):
        storage.delete_archived_feedbacks_by_feedback_name("fb1")


# ===========================================================================
# Search operations
# ===========================================================================


class TestSearchOperations:
    def test_search_interaction_by_query(self, storage):
        storage.add_user_interaction(
            "u1", _make_interaction(content="I like sushi", interaction_id=1)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(content="I like pizza", interaction_id=2)
        )
        results = storage.search_interaction(
            SearchInteractionRequest(user_id="u1", query="sushi"),
        )
        assert len(results) == 1
        assert "sushi" in results[0].content

    def test_search_interaction_by_request_id(self, storage):
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r1", interaction_id=1)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r2", interaction_id=2)
        )
        results = storage.search_interaction(
            SearchInteractionRequest(user_id="u1", request_id="r1"),
        )
        assert len(results) == 1

    def test_search_interaction_by_time_range(self, storage):
        now = datetime.now(UTC)
        ts = int(now.timestamp())
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=1, created_at=ts - 200),
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=2, created_at=ts),
        )
        results = storage.search_interaction(
            SearchInteractionRequest(
                user_id="u1",
                start_time=now - timedelta(seconds=100),
                end_time=now + timedelta(seconds=100),
            ),
        )
        assert len(results) == 1

    def test_search_user_profile_by_query(self, storage):
        storage.add_user_profile("u1", [_make_profile(content="likes sushi")])
        storage.add_user_profile(
            "u1", [_make_profile(profile_id="p2", content="likes pizza")]
        )
        results = storage.search_user_profile(
            SearchUserProfileRequest(user_id="u1", query="sushi"),
        )
        assert len(results) == 1

    def test_search_user_profile_by_request_id(self, storage):
        storage.add_user_profile("u1", [_make_profile(request_id="req1")])
        results = storage.search_user_profile(
            SearchUserProfileRequest(user_id="u1", generated_from_request_id="req1"),
        )
        assert len(results) == 1

    def test_search_user_profile_by_time_range(self, storage):
        now = datetime.now(UTC)
        ts = int(now.timestamp())
        storage.add_user_profile("u1", [_make_profile(timestamp=ts - 200)])
        storage.add_user_profile("u1", [_make_profile(profile_id="p2", timestamp=ts)])
        results = storage.search_user_profile(
            SearchUserProfileRequest(
                user_id="u1",
                start_time=now - timedelta(seconds=100),
                end_time=now + timedelta(seconds=100),
            ),
        )
        assert len(results) == 1

    def test_search_user_profile_top_k(self, storage):
        for i in range(5):
            storage.add_user_profile(
                "u1",
                [_make_profile(profile_id=f"p{i}", content=f"likes item {i}")],
            )
        results = storage.search_user_profile(
            SearchUserProfileRequest(user_id="u1", top_k=3),
        )
        assert len(results) == 3

    def test_search_raw_feedbacks_by_query(self, storage):
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="user likes sushi"),
                _make_raw_feedback(content="user likes pizza"),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(query="sushi"),
        )
        assert len(results) == 1
        assert "sushi" in results[0].feedback_content

    def test_search_raw_feedbacks_with_filters(self, storage):
        now = datetime.now(UTC)
        ts = int(now.timestamp())
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(
                    agent_version="v1", feedback_name="fb1", created_at=ts
                ),
                _make_raw_feedback(
                    agent_version="v2", feedback_name="fb2", created_at=ts
                ),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(agent_version="v1"),
        )
        assert len(results) == 1

    def test_search_raw_feedbacks_empty(self, storage):
        assert storage.search_raw_feedbacks(SearchRawFeedbackRequest()) == []

    def test_search_feedbacks_by_query(self, storage):
        storage.save_feedbacks(
            [
                _make_feedback(content="always greet the user"),
                _make_feedback(content="never skip validation"),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(query="greet"),
        )
        assert len(results) == 1

    def test_search_feedbacks_with_filters(self, storage):
        storage.save_feedbacks(
            [
                _make_feedback(agent_version="v1", feedback_name="fb1"),
                _make_feedback(agent_version="v2", feedback_name="fb2"),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(agent_version="v1"),
        )
        assert len(results) == 1

    def test_search_feedbacks_empty(self, storage):
        assert storage.search_feedbacks(SearchFeedbackRequest()) == []

    def test_search_feedbacks_with_status_filter(self, storage):
        storage.save_feedbacks(
            [
                _make_feedback(status=None),
                _make_feedback(status=Status.ARCHIVED),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(status_filter=[None]),
        )
        assert len(results) == 1


# ===========================================================================
# Skill CRUD
# ===========================================================================


class TestSkillCRUD:
    def test_save_and_get_skills(self, storage):
        storage.save_skills([_make_skill()])
        skills = storage.get_skills()
        assert len(skills) == 1
        assert skills[0].skill_name == "greet"
        assert skills[0].skill_id == 1

    def test_get_skills_empty(self, storage):
        assert storage.get_skills() == []

    def test_get_skills_with_filters(self, storage):
        storage.save_skills(
            [
                _make_skill(skill_name="s1", feedback_name="fb1", agent_version="v1"),
                _make_skill(skill_name="s2", feedback_name="fb2", agent_version="v2"),
            ]
        )
        assert len(storage.get_skills(feedback_name="fb1")) == 1
        assert len(storage.get_skills(agent_version="v2")) == 1

    def test_get_skills_with_status_filter(self, storage):
        storage.save_skills(
            [
                _make_skill(skill_name="s1", skill_status=SkillStatus.DRAFT),
                _make_skill(skill_name="s2", skill_status=SkillStatus.PUBLISHED),
            ]
        )
        assert len(storage.get_skills(skill_status=SkillStatus.DRAFT)) == 1

    def test_get_skills_limit(self, storage):
        storage.save_skills([_make_skill(skill_name=f"s{i}") for i in range(5)])
        assert len(storage.get_skills(limit=3)) == 3

    def test_save_skills_update_existing(self, storage):
        storage.save_skills([_make_skill(skill_name="greet")])
        skill = storage.get_skills()[0]
        skill.instructions = "Updated instructions"
        storage.save_skills([skill])
        updated = storage.get_skills()
        assert len(updated) == 1
        assert updated[0].instructions == "Updated instructions"

    def test_search_skills_by_query(self, storage):
        storage.save_skills(
            [
                _make_skill(skill_name="greet", instructions="Say hello to the user"),
                _make_skill(
                    skill_name="farewell", instructions="Say goodbye to the user"
                ),
            ]
        )
        results = storage.search_skills(SearchSkillsRequest(query="hello"))
        assert len(results) == 1
        assert results[0].skill_name == "greet"

    def test_search_skills_with_filters(self, storage):
        storage.save_skills(
            [
                _make_skill(skill_name="s1", feedback_name="fb1", agent_version="v1"),
                _make_skill(skill_name="s2", feedback_name="fb2", agent_version="v2"),
            ]
        )
        results = storage.search_skills(
            SearchSkillsRequest(feedback_name="fb1", agent_version="v1"),
        )
        assert len(results) == 1

    def test_search_skills_empty(self, storage):
        assert storage.search_skills(SearchSkillsRequest()) == []

    def test_update_skill_status(self, storage):
        storage.save_skills([_make_skill()])
        skill_id = storage.get_skills()[0].skill_id
        storage.update_skill_status(skill_id, SkillStatus.PUBLISHED)
        result = storage.get_skills()
        assert result[0].skill_status == SkillStatus.PUBLISHED

    def test_update_skill_status_no_skills(self, storage):
        storage.update_skill_status(999, SkillStatus.PUBLISHED)

    def test_delete_skill(self, storage):
        storage.save_skills([_make_skill()])
        skill_id = storage.get_skills()[0].skill_id
        storage.delete_skill(skill_id)
        assert storage.get_skills() == []

    def test_delete_skill_no_skills(self, storage):
        storage.delete_skill(999)

    def test_delete_all_skills(self, storage):
        storage.save_skills([_make_skill(), _make_skill(skill_name="s2")])
        storage.delete_all_skills()
        assert storage.get_skills() == []


# ===========================================================================
# Profile Change Log
# ===========================================================================


class TestProfileChangeLog:
    def test_add_and_get_profile_change_logs(self, storage):
        log = ProfileChangeLog(
            id=1,
            user_id="u1",
            request_id="req1",
            created_at=_now_ts(),
            added_profiles=[_make_profile()],
            removed_profiles=[],
            mentioned_profiles=[],
        )
        storage.add_profile_change_log(log)
        logs = storage.get_profile_change_logs()
        assert len(logs) == 1
        assert logs[0].user_id == "u1"

    def test_get_profile_change_logs_empty(self, storage):
        assert storage.get_profile_change_logs() == []

    def test_delete_profile_change_log_for_user(self, storage):
        log = ProfileChangeLog(
            id=1,
            user_id="u1",
            request_id="req1",
            added_profiles=[],
            removed_profiles=[],
            mentioned_profiles=[],
        )
        storage.add_profile_change_log(log)
        storage.delete_profile_change_log_for_user("u1")
        assert storage.get_profile_change_logs() == []

    def test_delete_profile_change_log_for_user_empty(self, storage):
        storage.delete_profile_change_log_for_user("nope")

    def test_delete_all_profile_change_logs(self, storage):
        log = ProfileChangeLog(
            id=1,
            user_id="u1",
            request_id="req1",
            added_profiles=[],
            removed_profiles=[],
            mentioned_profiles=[],
        )
        storage.add_profile_change_log(log)
        storage.delete_all_profile_change_logs()
        assert storage.get_profile_change_logs() == []


# ===========================================================================
# Feedback Aggregation Change Log
# ===========================================================================


class TestFeedbackAggregationChangeLog:
    def test_add_and_get(self, storage):
        log = FeedbackAggregationChangeLog(
            id=1,
            feedback_name="fb",
            agent_version="v1",
            created_at=_now_ts(),
            run_mode="incremental",
        )
        storage.add_feedback_aggregation_change_log(log)
        result = storage.get_feedback_aggregation_change_logs("fb", "v1")
        assert len(result) == 1

    def test_get_empty(self, storage):
        assert storage.get_feedback_aggregation_change_logs("fb", "v1") == []

    def test_get_filters_by_name_and_version(self, storage):
        storage.add_feedback_aggregation_change_log(
            FeedbackAggregationChangeLog(
                id=1,
                feedback_name="fb1",
                agent_version="v1",
                run_mode="incremental",
            ),
        )
        storage.add_feedback_aggregation_change_log(
            FeedbackAggregationChangeLog(
                id=2,
                feedback_name="fb2",
                agent_version="v1",
                run_mode="full_archive",
            ),
        )
        assert len(storage.get_feedback_aggregation_change_logs("fb1", "v1")) == 1
        assert len(storage.get_feedback_aggregation_change_logs("fb2", "v1")) == 1
        assert len(storage.get_feedback_aggregation_change_logs("fb1", "v2")) == 0

    def test_delete_all(self, storage):
        storage.add_feedback_aggregation_change_log(
            FeedbackAggregationChangeLog(
                id=1,
                feedback_name="fb",
                agent_version="v1",
                run_mode="incremental",
            ),
        )
        storage.delete_all_feedback_aggregation_change_logs()
        assert storage.get_feedback_aggregation_change_logs("fb", "v1") == []


# ===========================================================================
# Agent Success Evaluation Results
# ===========================================================================


class TestAgentSuccessEvaluation:
    def test_save_and_get(self, storage):
        result = AgentSuccessEvaluationResult(
            agent_version="v1",
            session_id="s1",
            is_success=True,
        )
        storage.save_agent_success_evaluation_results([result])
        results = storage.get_agent_success_evaluation_results()
        assert len(results) == 1
        assert results[0].is_success is True

    def test_get_empty(self, storage):
        assert storage.get_agent_success_evaluation_results() == []

    def test_get_with_agent_version_filter(self, storage):
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1", session_id="s1", is_success=True
                ),
                AgentSuccessEvaluationResult(
                    agent_version="v2", session_id="s2", is_success=False
                ),
            ]
        )
        results = storage.get_agent_success_evaluation_results(agent_version="v1")
        assert len(results) == 1

    def test_get_with_limit(self, storage):
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1", session_id=f"s{i}", is_success=True
                )
                for i in range(5)
            ]
        )
        assert len(storage.get_agent_success_evaluation_results(limit=3)) == 3

    def test_delete_all(self, storage):
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1", session_id="s1", is_success=True
                ),
            ]
        )
        storage.delete_all_agent_success_evaluation_results()
        assert storage.get_agent_success_evaluation_results() == []


# ===========================================================================
# Operation State
# ===========================================================================


class TestOperationState:
    def test_create_and_get(self, storage):
        storage.create_operation_state("svc1", {"key": "value"})
        state = storage.get_operation_state("svc1")
        assert state is not None
        assert state["operation_state"]["key"] == "value"

    def test_create_duplicate_raises(self, storage):
        storage.create_operation_state("svc1", {"key": "value"})
        with pytest.raises(StorageError):
            storage.create_operation_state("svc1", {"key": "other"})

    def test_get_missing(self, storage):
        assert storage.get_operation_state("nope") is None

    def test_upsert_create(self, storage):
        storage.upsert_operation_state("svc1", {"k": "v"})
        state = storage.get_operation_state("svc1")
        assert state is not None
        assert state["operation_state"]["k"] == "v"

    def test_upsert_update(self, storage):
        storage.upsert_operation_state("svc1", {"k": "v1"})
        storage.upsert_operation_state("svc1", {"k": "v2"})
        state = storage.get_operation_state("svc1")
        assert state["operation_state"]["k"] == "v2"

    def test_update_operation_state(self, storage):
        storage.create_operation_state("svc1", {"k": "v1"})
        storage.update_operation_state("svc1", {"k": "v2"})
        state = storage.get_operation_state("svc1")
        assert state["operation_state"]["k"] == "v2"

    def test_update_operation_state_missing_raises(self, storage):
        with pytest.raises(StorageError):
            storage.update_operation_state("nope", {"k": "v"})

    def test_get_all_operation_states(self, storage):
        storage.create_operation_state("svc1", {"k": 1})
        storage.create_operation_state("svc2", {"k": 2})
        states = storage.get_all_operation_states()
        assert len(states) == 2

    def test_get_all_operation_states_empty(self, storage):
        assert storage.get_all_operation_states() == []

    def test_delete_operation_state(self, storage):
        storage.create_operation_state("svc1", {"k": "v"})
        storage.delete_operation_state("svc1")
        assert storage.get_operation_state("svc1") is None

    def test_delete_all_operation_states(self, storage):
        storage.create_operation_state("svc1", {"k": 1})
        storage.create_operation_state("svc2", {"k": 2})
        storage.delete_all_operation_states()
        assert storage.get_all_operation_states() == []

    def test_try_acquire_lock_fresh(self, storage):
        result = storage.try_acquire_in_progress_lock("key", "req1")
        assert result["acquired"] is True
        assert result["state"]["in_progress"] is True
        assert result["state"]["current_request_id"] == "req1"

    def test_try_acquire_lock_blocked(self, storage):
        storage.try_acquire_in_progress_lock("key", "req1")
        result = storage.try_acquire_in_progress_lock("key", "req2")
        assert result["acquired"] is False
        assert result["state"]["pending_request_id"] == "req2"

    def test_try_acquire_lock_stale(self, storage):
        storage.try_acquire_in_progress_lock("key", "req1", stale_lock_seconds=0)
        result = storage.try_acquire_in_progress_lock(
            "key", "req2", stale_lock_seconds=0
        )
        assert result["acquired"] is True


# ===========================================================================
# Dashboard stats
# ===========================================================================


class TestDashboardStats:
    def test_get_dashboard_stats_empty(self, storage):
        stats = storage.get_dashboard_stats()
        assert stats["current_period"]["total_interactions"] == 0
        assert stats["current_period"]["total_profiles"] == 0
        assert stats["current_period"]["total_feedbacks"] == 0

    def test_get_dashboard_stats_with_data(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        storage.add_user_profile("u1", [_make_profile(timestamp=now)])
        storage.save_raw_feedbacks([_make_raw_feedback(created_at=now)])
        storage.save_feedbacks([_make_feedback(created_at=now)])
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1", session_id="s1", is_success=True, created_at=now
                ),
            ]
        )
        stats = storage.get_dashboard_stats()
        assert stats["current_period"]["total_interactions"] == 1
        assert stats["current_period"]["total_profiles"] == 1
        assert stats["current_period"]["total_feedbacks"] == 2  # 1 raw + 1 aggregated
        assert stats["current_period"]["success_rate"] == 100.0


# ===========================================================================
# get_last_k_interactions_grouped
# ===========================================================================


class TestGetLastKInteractionsGrouped:
    def test_basic(self, storage):
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1"))
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r1", interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(request_id="r1", interaction_id=2, created_at=now + 1),
        )
        sessions, flat = storage.get_last_k_interactions_grouped(user_id="u1", k=10)
        assert len(flat) == 2
        assert len(sessions) == 1

    def test_with_time_range(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now - 200)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now)
        )
        _, flat = storage.get_last_k_interactions_grouped(
            user_id="u1",
            k=10,
            start_time=now - 100,
            end_time=now + 100,
        )
        assert len(flat) == 1

    def test_with_source_filter(self, storage):
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1", source="api"))
        storage.add_request(_make_request(request_id="r2", source="web"))
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r1", interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r2", interaction_id=2, created_at=now)
        )
        _, flat = storage.get_last_k_interactions_grouped(
            user_id="u1",
            k=10,
            sources=["api"],
        )
        assert len(flat) == 1

    def test_all_users(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(user_id="u1", interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u2", _make_interaction(user_id="u2", interaction_id=2, created_at=now)
        )
        _, flat = storage.get_last_k_interactions_grouped(user_id=None, k=10)
        assert len(flat) == 2


# ===========================================================================
# get_operation_state_with_new_request_interaction
# ===========================================================================


class TestGetOperationStateWithNewInteractions:
    def test_no_state_returns_all_interactions(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        state, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1",
            "u1",
        )
        assert len(sessions) == 1

    def test_with_state_returns_only_new(self, storage):
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now - 100)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now)
        )
        storage.upsert_operation_state(
            "svc1",
            {
                "service_name": "svc1",
                "operation_state": {
                    "last_processed_interaction_ids": ["1"],
                    "last_processed_timestamp": now - 100,
                },
                "updated_at": str(now),
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        # Should get the newer interaction
        assert len(sessions) >= 1


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_empty_storage_operations(self, storage):
        """Verify all read operations work on fresh empty storage."""
        assert storage.get_all_profiles() == []
        assert storage.get_all_interactions() == []
        assert storage.get_feedbacks() == []
        assert storage.get_raw_feedbacks() == []
        assert storage.get_skills() == []
        assert storage.get_profile_change_logs() == []
        assert storage.count_all_interactions() == 0
        assert storage.count_raw_feedbacks() == 0

    def test_save_delete_get_cycle(self, storage):
        """Save, delete, then verify get returns empty."""
        storage.add_user_profile("u1", [_make_profile()])
        storage.delete_all_profiles_for_user("u1")
        assert storage.get_user_profile("u1") == []

        storage.add_user_interaction("u1", _make_interaction(interaction_id=1))
        storage.delete_all_interactions_for_user("u1")
        assert storage.get_user_interaction("u1") == []

        storage.save_feedbacks([_make_feedback()])
        storage.delete_all_feedbacks()
        assert storage.get_feedbacks() == []

        storage.save_raw_feedbacks([_make_raw_feedback()])
        storage.delete_all_raw_feedbacks()
        assert storage.get_raw_feedbacks() == []

        storage.save_skills([_make_skill()])
        storage.delete_all_skills()
        assert storage.get_skills() == []

    def test_multiple_profiles_per_user(self, storage):
        storage.add_user_profile(
            "u1",
            [
                _make_profile(profile_id="p1", content="a"),
                _make_profile(profile_id="p2", content="b"),
            ],
        )
        profiles = storage.get_user_profile("u1")
        assert len(profiles) == 2

    def test_search_on_empty_storage(self, storage):
        assert (
            storage.search_interaction(
                SearchInteractionRequest(user_id="u1"),
            )
            == []
        )
        assert (
            storage.search_user_profile(
                SearchUserProfileRequest(user_id="u1"),
            )
            == []
        )
        assert storage.search_raw_feedbacks(SearchRawFeedbackRequest()) == []
        assert storage.search_feedbacks(SearchFeedbackRequest()) == []
        assert storage.search_skills(SearchSkillsRequest()) == []

    def test_migrate_returns_true(self, storage):
        assert storage.migrate() is True

    def test_check_migration_needed_returns_false(self, storage):
        assert storage.check_migration_needed() is False


# ===========================================================================
# Init validation edge cases (lines 68-87)
# ===========================================================================


class TestInitValidation:
    def test_config_with_nonexistent_absolute_dir_creates_it(self, tmp_path):
        new_dir = tmp_path / "new_sub" / "deep"
        cfg = StorageConfigLocal(dir_path=str(new_dir))
        s = LocalJsonStorage(org_id="org1", config=cfg)
        assert s.base_dir == str(new_dir)
        assert new_dir.is_dir()

    def test_config_mkdir_os_error_raises(self, tmp_path):
        """Covers lines 74-77: OSError during mkdir with config."""
        # Create a file where the directory would be
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        # Try to create a dir *inside* the file, which will OSError
        bad_path = str(blocker / "subdir")
        cfg = StorageConfigLocal(dir_path=bad_path)
        with pytest.raises(StorageError, match="cannot create directory"):
            LocalJsonStorage(org_id="org1", config=cfg)

    def test_base_dir_none_uses_default(self, tmp_path, monkeypatch):
        """Covers line 80: base_dir is None falls back to LOCAL_STORAGE_PATH."""
        monkeypatch.setattr(
            "reflexio.server.services.storage.local_json_storage.LOCAL_STORAGE_PATH",
            str(tmp_path),
        )
        s = LocalJsonStorage(org_id="org1")
        assert s.base_dir == str(tmp_path)

    def test_base_dir_mkdir_os_error_raises(self, tmp_path):
        """Covers lines 84-87: OSError during mkdir without config."""
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        bad_path = str(blocker / "subdir")
        with pytest.raises(StorageError, match="cannot create directory"):
            LocalJsonStorage(org_id="org1", base_dir=bad_path)


# ===========================================================================
# Legacy string status filter (lines 158-165, 225-232)
# ===========================================================================


class TestLegacyStringStatusFilter:
    def test_get_all_profiles_legacy_string_filter(self, storage):
        """Covers lines 158-165: legacy string comparison in get_all_profiles."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        # Pass a raw string that matches the enum's value
        profiles = storage.get_all_profiles(status_filter=["pending"])
        assert len(profiles) == 1

    def test_get_user_profile_legacy_string_filter(self, storage):
        """Covers lines 225-232: legacy string comparison in get_user_profile."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        profiles = storage.get_user_profile("u1", status_filter=["pending"])
        assert len(profiles) == 1


# ===========================================================================
# _get_next_interaction_id edge cases (lines 282, 293-294)
# ===========================================================================


class TestGetNextInteractionId:
    def test_skips_internal_keys_starting_with_underscore(self, storage):
        """Covers line 282: keys starting with _ are skipped."""
        import json
        from pathlib import Path

        all_memories = json.loads(Path(storage.file_path).read_text())
        all_memories["_internal"] = {"interactions": ["invalid_json"]}
        all_memories["user1"] = {"interactions": []}
        Path(storage.file_path).write_text(json.dumps(all_memories))
        # Should work without error (skips _internal)
        storage.add_user_interaction("user1", _make_interaction(interaction_id=0))
        interactions = storage.get_user_interaction("user1")
        assert len(interactions) == 1
        assert interactions[0].interaction_id == 1

    def test_skips_non_dict_entries(self, storage):
        """Covers lines 283-286: non-dict entries (e.g. list) are skipped."""
        import json
        from pathlib import Path

        all_memories = json.loads(Path(storage.file_path).read_text())
        all_memories["requests"] = ["some_request_json"]
        Path(storage.file_path).write_text(json.dumps(all_memories))
        storage.add_user_interaction("user1", _make_interaction(interaction_id=0))
        interactions = storage.get_user_interaction("user1")
        assert interactions[0].interaction_id == 1

    def test_skips_invalid_interaction_json(self, storage):
        """Covers lines 293-294: exception during interaction parsing is caught."""
        import json
        from pathlib import Path

        all_memories = json.loads(Path(storage.file_path).read_text())
        all_memories["user_bad"] = {"interactions": ["not_valid_json{{"]}
        Path(storage.file_path).write_text(json.dumps(all_memories))
        storage.add_user_interaction("user1", _make_interaction(interaction_id=0))
        interactions = storage.get_user_interaction("user1")
        assert interactions[0].interaction_id == 1


# ===========================================================================
# delete_request edge case (line 736)
# ===========================================================================


class TestDeleteRequestEdgeCases:
    def test_delete_request_no_requests_key(self, storage):
        """Covers line 736: early return when 'requests' key missing."""
        storage.add_user_interaction("u1", _make_interaction(interaction_id=1))
        # No requests stored yet, calling delete_request should not raise
        storage.delete_request("req_nonexistent")


# ===========================================================================
# delete_session edge case (line 769)
# ===========================================================================


class TestDeleteSessionEdgeCases:
    def test_delete_session_no_matching_requests(self, storage):
        """Covers line 769: request_ids is empty after filtering."""
        storage.add_request(_make_request(request_id="r1", session_id="s1"))
        deleted = storage.delete_session("s_nonexistent")
        assert deleted == 0


# ===========================================================================
# get_sessions filter paths (lines 923, 927, 931, 939)
# ===========================================================================


class TestGetSessionsFilters:
    def test_get_sessions_filter_by_request_id(self, storage):
        """Covers line 927: filter by request_id."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id="s1", created_at=now)
        )
        storage.add_request(
            _make_request(request_id="r2", session_id="s1", created_at=now)
        )
        sessions = storage.get_sessions(request_id="r1")
        assert "s1" in sessions
        assert len(sessions["s1"]) == 1
        assert sessions["s1"][0].request.request_id == "r1"

    def test_get_sessions_filter_by_end_time(self, storage):
        """Covers line 939: end_time filter applied."""
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1", created_at=now - 200))
        storage.add_request(_make_request(request_id="r2", created_at=now))
        sessions = storage.get_sessions(user_id="user1", end_time=now - 100)
        total = sum(len(v) for v in sessions.values())
        assert total == 1

    def test_get_sessions_no_user_id_collects_all_interactions(self, storage):
        """Covers lines 965-973: interaction collection when user_id is None."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", user_id="u1", created_at=now)
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(
                user_id="u1", request_id="r1", interaction_id=1, created_at=now
            ),
        )
        sessions = storage.get_sessions()
        total = sum(len(v) for v in sessions.values())
        assert total >= 1


# ===========================================================================
# get_rerun_user_ids filter paths (lines 1039, 1041, 1045)
# ===========================================================================


class TestGetRerunUserIdsFilters:
    def test_rerun_user_ids_filter_by_time_range(self, storage):
        """Covers lines 1039, 1041: start_time and end_time filters."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", user_id="u1", created_at=now - 200)
        )
        storage.add_request(
            _make_request(request_id="r2", user_id="u2", created_at=now)
        )
        result = storage.get_rerun_user_ids(start_time=now - 100, end_time=now + 100)
        assert "u2" in result
        assert "u1" not in result

    def test_rerun_user_ids_filter_by_agent_version(self, storage):
        """Covers line 1045: agent_version filter."""
        now = _now_ts()
        storage.add_request(
            _make_request(
                request_id="r1", user_id="u1", agent_version="v1", created_at=now
            )
        )
        storage.add_request(
            _make_request(
                request_id="r2", user_id="u2", agent_version="v2", created_at=now
            )
        )
        result = storage.get_rerun_user_ids(agent_version="v1")
        assert result == ["u1"]


# ===========================================================================
# save_raw_feedbacks auto-id from existing (lines 1251-1253)
# ===========================================================================


class TestSaveRawFeedbacksAutoId:
    def test_auto_id_continues_from_existing(self, storage):
        """Covers lines 1251-1253: finds max existing raw_feedback_id."""
        storage.save_raw_feedbacks([_make_raw_feedback()])
        # First one gets id=1
        storage.save_raw_feedbacks([_make_raw_feedback()])
        # Second one should get id=2
        all_fbs = storage.get_raw_feedbacks()
        assert len(all_fbs) == 2
        ids = {fb.raw_feedback_id for fb in all_fbs}
        assert ids == {1, 2}


# ===========================================================================
# get_raw_feedbacks end_time filter (line 1318)
# ===========================================================================


class TestGetRawFeedbacksEndTime:
    def test_end_time_filter(self, storage):
        """Covers line 1318: end_time filter excludes later feedbacks."""
        now = _now_ts()
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="old", created_at=now - 200),
                _make_raw_feedback(content="new", created_at=now),
            ]
        )
        result = storage.get_raw_feedbacks(end_time=now - 100)
        assert len(result) == 1
        assert result[0].feedback_content == "old"


# ===========================================================================
# count_raw_feedbacks with status_filter (line 1376)
# ===========================================================================


class TestCountRawFeedbacksStatusFilter:
    def test_count_with_status_filter(self, storage):
        """Covers line 1376: status_filter in count_raw_feedbacks."""
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="a", status=None),
                _make_raw_feedback(content="b", status=Status.PENDING),
            ]
        )
        assert storage.count_raw_feedbacks(status_filter=[None]) == 1
        assert storage.count_raw_feedbacks(status_filter=[Status.PENDING]) == 1


# ===========================================================================
# update_feedback_status not found (line 1634)
# ===========================================================================


class TestUpdateFeedbackStatusNotFound:
    def test_feedback_id_not_found_in_existing_feedbacks(self, storage):
        """Covers line 1634: feedback exists but target ID not among them."""
        storage.save_feedbacks([_make_feedback()])
        with pytest.raises(ValueError, match="not found"):
            storage.update_feedback_status(999, FeedbackStatus.APPROVED)


# ===========================================================================
# Feedback archive/restore with no feedbacks key (lines 1736, 1764, 1792)
# ===========================================================================


class TestFeedbackArchiveEdgeCases:
    def test_archive_by_ids_no_feedbacks_key(self, storage):
        """Covers line 1736: archive_feedbacks_by_ids when no feedbacks stored."""
        storage.archive_feedbacks_by_ids([1, 2])

    def test_restore_by_ids_no_feedbacks_key(self, storage):
        """Covers line 1764: restore_archived_feedbacks_by_ids when no feedbacks stored."""
        storage.restore_archived_feedbacks_by_ids([1, 2])

    def test_delete_by_ids_no_feedbacks_key(self, storage):
        """Covers line 1792: delete_feedbacks_by_ids when no feedbacks stored."""
        storage.delete_feedbacks_by_ids([1, 2])


# ===========================================================================
# update_all_raw_feedbacks_status with filters (lines 1842-1843, 1863)
# ===========================================================================


class TestUpdateRawFeedbacksStatusFilters:
    def test_update_skips_non_matching_feedback_name(self, storage):
        """Covers lines 1842-1843: feedback_name filter skip."""
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(feedback_name="fb1"),
                _make_raw_feedback(feedback_name="fb2"),
            ]
        )
        count = storage.update_all_raw_feedbacks_status(
            old_status=None,
            new_status=Status.PENDING,
            feedback_name="fb1",
        )
        assert count == 1
        # fb2 should still be current
        remaining = storage.get_raw_feedbacks(status_filter=[None])
        assert len(remaining) == 1
        assert remaining[0].feedback_name == "fb2"

    def test_update_no_raw_feedbacks_key(self, storage):
        """Covers line 1823: early return when no raw_feedbacks key."""
        result = storage.update_all_raw_feedbacks_status(
            old_status=None,
            new_status=Status.PENDING,
        )
        assert result == 0

    def test_update_non_matching_status_kept(self, storage):
        """Covers line 1863: non-matching status feedbacks are preserved as-is."""
        storage.save_raw_feedbacks([_make_raw_feedback(status=Status.PENDING)])
        count = storage.update_all_raw_feedbacks_status(
            old_status=None,
            new_status=Status.ARCHIVED,
        )
        assert count == 0
        # Feedback unchanged
        remaining = storage.get_raw_feedbacks(status_filter=[Status.PENDING])
        assert len(remaining) == 1


# ===========================================================================
# delete_all_raw_feedbacks_by_status (line 1894)
# ===========================================================================


class TestDeleteRawFeedbacksByStatus:
    def test_delete_by_status_no_raw_feedbacks_key(self, storage):
        """Covers line 1894: early return when no raw_feedbacks key."""
        result = storage.delete_all_raw_feedbacks_by_status(Status.PENDING)
        assert result == 0


# ===========================================================================
# has_raw_feedbacks_with_status Status enum match (line 1978)
# ===========================================================================


class TestHasRawFeedbacksStatusEnum:
    def test_has_status_enum_match(self, storage):
        """Covers line 1978: Status enum comparison returns True."""
        storage.save_raw_feedbacks([_make_raw_feedback(status=Status.PENDING)])
        assert storage.has_raw_feedbacks_with_status(Status.PENDING) is True
        assert storage.has_raw_feedbacks_with_status(Status.ARCHIVED) is False


# ===========================================================================
# search_raw_feedbacks filter paths (lines 2016-2019, 2027-2029, 2041, 2045, 2049, 2055, 2059)
# ===========================================================================


class TestSearchRawFeedbacksFilters:
    def test_search_raw_feedbacks_filter_by_feedback_name(self, storage):
        """Covers line 2041: feedback_name filter."""
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="a", feedback_name="fb1"),
                _make_raw_feedback(content="b", feedback_name="fb2"),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(feedback_name="fb1"),
        )
        assert len(results) == 1
        assert results[0].feedback_content == "a"

    def test_search_raw_feedbacks_filter_by_time_range(self, storage):
        """Covers lines 2045, 2049: start_time and end_time filters."""
        now = datetime.now(UTC)
        ts = int(now.timestamp())
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="old", created_at=ts - 200),
                _make_raw_feedback(content="mid", created_at=ts),
                _make_raw_feedback(content="new", created_at=ts + 200),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(
                start_time=now - timedelta(seconds=100),
                end_time=now + timedelta(seconds=100),
            ),
        )
        assert len(results) == 1
        assert results[0].feedback_content == "mid"

    def test_search_raw_feedbacks_filter_by_status(self, storage):
        """Covers line 2055: status_filter."""
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="current", status=None),
                _make_raw_feedback(content="pending", status=Status.PENDING),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(status_filter=[Status.PENDING]),
        )
        assert len(results) == 1
        assert results[0].feedback_content == "pending"

    def test_search_raw_feedbacks_top_k_limit(self, storage):
        """Covers line 2059: match_count limit."""
        storage.save_raw_feedbacks([_make_raw_feedback() for _ in range(5)])
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(top_k=2),
        )
        assert len(results) == 2


# ===========================================================================
# search_feedbacks filter paths (lines 2105, 2109, 2113, 2117-2123, 2133)
# ===========================================================================


class TestSearchFeedbacksFilters:
    def test_search_feedbacks_filter_by_feedback_name(self, storage):
        """Covers line 2105: feedback_name filter."""
        storage.save_feedbacks(
            [
                _make_feedback(content="a", feedback_name="fb1"),
                _make_feedback(content="b", feedback_name="fb2"),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(feedback_name="fb1"),
        )
        assert len(results) == 1

    def test_search_feedbacks_filter_by_time_range(self, storage):
        """Covers lines 2109, 2113: start_time and end_time filters."""
        now = datetime.now(UTC)
        ts = int(now.timestamp())
        storage.save_feedbacks(
            [
                _make_feedback(content="old", created_at=ts - 200),
                _make_feedback(content="new", created_at=ts + 200),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(
                start_time=now - timedelta(seconds=100),
                end_time=now + timedelta(seconds=100),
            ),
        )
        assert len(results) == 0

    def test_search_feedbacks_filter_by_feedback_status(self, storage):
        """Covers lines 2117-2123: feedback_status_filter."""
        storage.save_feedbacks(
            [
                _make_feedback(
                    content="approved", feedback_status=FeedbackStatus.APPROVED
                ),
                _make_feedback(
                    content="pending", feedback_status=FeedbackStatus.PENDING
                ),
            ]
        )
        results = storage.search_feedbacks(
            SearchFeedbackRequest(feedback_status_filter=FeedbackStatus.APPROVED),
        )
        assert len(results) == 1
        assert results[0].feedback_content == "approved"

    def test_search_feedbacks_top_k_limit(self, storage):
        """Covers line 2133: match_count limit."""
        storage.save_feedbacks([_make_feedback() for _ in range(5)])
        results = storage.search_feedbacks(
            SearchFeedbackRequest(top_k=2),
        )
        assert len(results) == 2


# ===========================================================================
# Dashboard stats with previous period data (lines 2248-2249, 2263-2264, 2278-2279, 2290-2291, 2322-2325)
# ===========================================================================


class TestDashboardStatsPreviousPeriod:
    def test_previous_period_counts(self, storage):
        """Covers lines 2248-2249, 2263-2264, 2278-2279, 2290-2291, 2322-2325."""
        now = _now_ts()
        days_back = 30
        seconds = days_back * 24 * 60 * 60
        prev_ts = now - seconds - 100  # In previous period

        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=1, created_at=prev_ts),
        )
        storage.add_user_profile("u1", [_make_profile(timestamp=prev_ts)])
        storage.save_raw_feedbacks([_make_raw_feedback(created_at=prev_ts)])
        storage.save_feedbacks([_make_feedback(created_at=prev_ts)])
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1",
                    session_id="s1",
                    is_success=True,
                    created_at=prev_ts,
                ),
            ]
        )

        stats = storage.get_dashboard_stats(days_back=days_back)
        assert stats["previous_period"]["total_interactions"] == 1
        assert stats["previous_period"]["total_profiles"] == 1
        assert stats["previous_period"]["total_feedbacks"] == 2
        assert stats["previous_period"]["success_rate"] == 100.0


# ===========================================================================
# _get_time_bucket (lines 2370-2386)
# ===========================================================================


class TestGetTimeBucket:
    def test_daily_bucket(self, storage):
        """Covers line 2373: daily granularity."""
        ts = int(datetime(2025, 6, 15, 14, 30, tzinfo=UTC).timestamp())
        bucket = storage._get_time_bucket(ts, 0, "daily")
        expected = int(datetime(2025, 6, 15, 0, 0, tzinfo=UTC).timestamp())
        assert bucket == expected

    def test_weekly_bucket(self, storage):
        """Covers lines 2374-2379: weekly granularity (start of week = Monday)."""
        # June 15, 2025 is a Sunday
        ts = int(datetime(2025, 6, 15, 14, 30, tzinfo=UTC).timestamp())
        bucket = storage._get_time_bucket(ts, 0, "weekly")
        # Monday before June 15 is June 9
        expected = int(datetime(2025, 6, 9, 0, 0, tzinfo=UTC).timestamp())
        assert bucket == expected

    def test_monthly_bucket(self, storage):
        """Covers lines 2380-2381: monthly granularity."""
        ts = int(datetime(2025, 6, 15, 14, 30, tzinfo=UTC).timestamp())
        bucket = storage._get_time_bucket(ts, 0, "monthly")
        expected = int(datetime(2025, 6, 1, 0, 0, tzinfo=UTC).timestamp())
        assert bucket == expected

    def test_unknown_granularity_defaults_to_daily(self, storage):
        """Covers lines 2383-2384: unknown granularity defaults to daily."""
        ts = int(datetime(2025, 6, 15, 14, 30, tzinfo=UTC).timestamp())
        bucket = storage._get_time_bucket(ts, 0, "quarterly")
        expected = int(datetime(2025, 6, 15, 0, 0, tzinfo=UTC).timestamp())
        assert bucket == expected


# ===========================================================================
# get_operation_state_with_new_request_interaction edge cases (lines 2502, 2522-2523, 2534-2542, 2574)
# ===========================================================================


class TestOpStateWithNewInteractionsEdgeCases:
    def test_all_users_interaction_collection(self, storage):
        """Covers lines 2522-2523: user_id=None collects from all users."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(user_id="u1", interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u2", _make_interaction(user_id="u2", interaction_id=2, created_at=now)
        )
        state, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", None
        )
        total_interactions = sum(len(s.interactions) for s in sessions)
        assert total_interactions == 2

    def test_timestamp_equal_but_different_id(self, storage):
        """Covers lines 2537-2542: same timestamp but different interaction_id."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now)
        )
        storage.upsert_operation_state(
            "svc1",
            {
                "service_name": "svc1",
                "operation_state": {
                    "last_processed_interaction_ids": ["1"],
                    "last_processed_timestamp": now,
                },
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        # interaction_id=2 has same timestamp but was not processed
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        assert 2 in all_ids

    def test_source_filter_excludes_non_matching(self, storage):
        """Covers line 2574: sources filter skips non-matching requests."""
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1", source="api"))
        storage.add_request(_make_request(request_id="r2", source="web"))
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r1", interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(request_id="r2", interaction_id=2, created_at=now)
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1",
            "u1",
            sources=["api"],
        )
        all_request_ids = [s.request.request_id for s in sessions]
        assert "r1" in all_request_ids
        assert "r2" not in all_request_ids


# ===========================================================================
# get_last_k_interactions_grouped edge cases (lines 2650, 2659)
# ===========================================================================


class TestGetLastKInteractionsGroupedEdgeCases:
    def test_k_limit_applied(self, storage):
        """Covers line 2650: k limit stops early."""
        now = _now_ts()
        for i in range(5):
            storage.add_user_interaction(
                "u1",
                _make_interaction(interaction_id=i + 1, created_at=now + i),
            )
        _, flat = storage.get_last_k_interactions_grouped(user_id="u1", k=2)
        assert len(flat) == 2

    def test_end_time_filter(self, storage):
        """Covers line 2659: end_time filter excludes newer interactions."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now - 200)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now + 200)
        )
        _, flat = storage.get_last_k_interactions_grouped(
            user_id="u1",
            k=10,
            end_time=now,
        )
        assert len(flat) == 1
        assert flat[0].interaction_id == 1


# ===========================================================================
# get_profile_statistics expiring_soon (line 2875)
# ===========================================================================


class TestProfileStatisticsExpiringSoon:
    def test_expiring_soon_count(self, storage):
        """Covers line 2875: profiles expiring within 7 days counted."""
        now = _now_ts()
        three_days = 3 * 24 * 60 * 60
        profile = _make_profile(timestamp=now)
        profile.expiration_timestamp = now + three_days  # Expires in 3 days
        storage.add_user_profile("u1", [profile])
        stats = storage.get_profile_statistics()
        assert stats["expiring_soon_count"] == 1


# ===========================================================================
# search_skills filter paths (lines 2963, 2965, 2968)
# ===========================================================================


class TestSearchSkillsFilters:
    def test_search_skills_filter_by_agent_version(self, storage):
        """Covers line 2963: agent_version filter."""
        storage.save_skills(
            [
                _make_skill(skill_name="s1", agent_version="v1"),
                _make_skill(skill_name="s2", agent_version="v2"),
            ]
        )
        results = storage.search_skills(
            SearchSkillsRequest(agent_version="v1"),
        )
        assert len(results) == 1
        assert results[0].skill_name == "s1"

    def test_search_skills_filter_by_skill_status(self, storage):
        """Covers line 2965: skill_status filter."""
        storage.save_skills(
            [
                _make_skill(skill_name="s1", skill_status=SkillStatus.DRAFT),
                _make_skill(skill_name="s2", skill_status=SkillStatus.PUBLISHED),
            ]
        )
        results = storage.search_skills(
            SearchSkillsRequest(skill_status=SkillStatus.PUBLISHED),
        )
        assert len(results) == 1
        assert results[0].skill_name == "s2"

    def test_search_skills_top_k_limit(self, storage):
        """Covers line 2968: match_count limit."""
        storage.save_skills([_make_skill(skill_name=f"s{i}") for i in range(5)])
        results = storage.search_skills(
            SearchSkillsRequest(top_k=2),
        )
        assert len(results) == 2


# ===========================================================================
# Status filter branch coverage: profile status mismatch paths
# (lines 145->167, 150->145, 155->145, 158->145 in get_all_profiles)
# (same in get_user_profile)
# ===========================================================================


class TestStatusFilterBranches:
    def test_get_all_profiles_none_filter_skips_non_null_status(self, storage):
        """Covers 150->145 branch: filter is None but profile has status, skip."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        # Default filter is [None], which only matches profiles with status=None
        profiles = storage.get_all_profiles(status_filter=[None])
        assert len(profiles) == 0

    def test_get_all_profiles_enum_filter_skips_non_matching(self, storage):
        """Covers 155->145 branch: filter is Status.ARCHIVED but profile is PENDING."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        profiles = storage.get_all_profiles(status_filter=[Status.ARCHIVED])
        assert len(profiles) == 0

    def test_get_all_profiles_string_filter_skips_none_status(self, storage):
        """Covers 158->145 branch: legacy string filter with profile status=None."""
        storage.add_user_profile("u1", [_make_profile(status=None)])
        profiles = storage.get_all_profiles(status_filter=["pending"])
        assert len(profiles) == 0

    def test_get_all_profiles_multiple_status_filters(self, storage):
        """Covers 145->167 branch: iterate multiple filters before match."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        storage.add_user_profile("u1", [_make_profile(profile_id="p2", status=None)])
        storage.add_user_profile(
            "u1", [_make_profile(profile_id="p3", status=Status.ARCHIVED)]
        )
        profiles = storage.get_all_profiles(
            status_filter=[None, Status.PENDING, Status.ARCHIVED]
        )
        assert len(profiles) == 3

    def test_get_user_profile_none_filter_skips_non_null_status(self, storage):
        """Covers get_user_profile 150->145 branch."""
        storage.add_user_profile("u1", [_make_profile(status=Status.ARCHIVED)])
        profiles = storage.get_user_profile("u1", status_filter=[None])
        assert len(profiles) == 0

    def test_get_user_profile_enum_filter_skips_non_matching(self, storage):
        """Covers get_user_profile 155->145 branch."""
        storage.add_user_profile("u1", [_make_profile(status=Status.PENDING)])
        profiles = storage.get_user_profile("u1", status_filter=[Status.ARCHIVED])
        assert len(profiles) == 0

    def test_get_user_profile_string_filter_skips_none_status(self, storage):
        """Covers get_user_profile 158->145 branch."""
        storage.add_user_profile("u1", [_make_profile(status=None)])
        profiles = storage.get_user_profile("u1", status_filter=["archived"])
        assert len(profiles) == 0


# ===========================================================================
# Time range filter branches in sessions/interactions
# (lines 826->836, 849->848, 979->981)
# ===========================================================================


class TestTimeRangeFilterBranches:
    def test_delete_requests_by_ids_no_requests_key(self, storage):
        """Covers line 826->836: 'requests' key absent in delete_requests_by_ids."""
        # Storage has no requests, but we pass request_ids.
        # The deletion should still work (deleted=0 because nothing to delete).
        deleted = storage.delete_requests_by_ids(["r1"])
        assert deleted == 0

    def test_delete_profiles_by_ids_no_user_profiles(self, storage):
        """Covers line 849->848: user has no 'profiles' key."""
        # Add an interaction so user exists but with no profiles
        storage.add_user_interaction("u1", _make_interaction(interaction_id=1))
        deleted = storage.delete_profiles_by_ids(["p1"])
        assert deleted == 0

    def test_get_sessions_interaction_grouping(self, storage):
        """Covers line 979->981: interactions grouped by request_id."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id="s1", created_at=now)
        )
        storage.add_user_interaction(
            "user1",
            _make_interaction(request_id="r1", interaction_id=1, created_at=now),
        )
        storage.add_user_interaction(
            "user1",
            _make_interaction(request_id="r1", interaction_id=2, created_at=now + 1),
        )
        sessions = storage.get_sessions(user_id="user1")
        assert "s1" in sessions
        assert len(sessions["s1"]) == 1
        assert len(sessions["s1"][0].interactions) == 2

    def test_get_sessions_start_time_filter(self, storage):
        """Covers line 934: start_time filter excludes older requests."""
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1", created_at=now - 200))
        storage.add_request(_make_request(request_id="r2", created_at=now))
        sessions = storage.get_sessions(user_id="user1", start_time=now - 50)
        total = sum(len(v) for v in sessions.values())
        assert total == 1


# ===========================================================================
# Empty request collection and session/request filter branches
# (lines 923, 931)
# ===========================================================================


class TestEmptyRequestCollection:
    def test_get_sessions_user_id_filter_skips_requests(self, storage):
        """Covers line 922-923: user_id filter causes request to be skipped."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", user_id="other_user", created_at=now)
        )
        sessions = storage.get_sessions(user_id="missing_user")
        assert sessions == {}

    def test_get_sessions_session_id_filter_skips_requests(self, storage):
        """Covers line 929-931: session_id filter causes request to be skipped."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id="s1", created_at=now)
        )
        sessions = storage.get_sessions(
            user_id="user1", session_id="nonexistent_session"
        )
        assert sessions == {}

    def test_get_sessions_offset_pagination(self, storage):
        """Covers line 948: offset + limit pagination on requests."""
        now = _now_ts()
        for i in range(5):
            storage.add_request(
                _make_request(
                    request_id=f"r{i}",
                    session_id=f"s{i}",
                    created_at=now + i,
                )
            )
        # top_k=2, offset=2 -> should skip first 2 (most recent) and get next 2
        sessions = storage.get_sessions(user_id="user1", top_k=2, offset=2)
        total = sum(len(v) for v in sessions.values())
        assert total == 2


# ===========================================================================
# Search with no results (lines 1090->exit, 1135->exit)
# ===========================================================================


class TestSearchNoResults:
    def test_search_interaction_query_no_match(self, storage):
        """Covers search_interaction returning empty when query doesn't match."""
        storage.add_user_interaction(
            "u1", _make_interaction(content="hello world", interaction_id=1)
        )
        results = storage.search_interaction(
            SearchInteractionRequest(user_id="u1", query="nonexistent_query"),
        )
        assert results == []

    def test_search_user_profile_query_no_match(self, storage):
        """Covers search_user_profile returning empty when query doesn't match."""
        storage.add_user_profile("u1", [_make_profile(content="likes sushi")])
        results = storage.search_user_profile(
            SearchUserProfileRequest(user_id="u1", query="nonexistent_query"),
        )
        assert results == []

    def test_search_raw_feedbacks_query_no_match(self, storage):
        """Covers search_raw_feedbacks returning empty when query doesn't match."""
        storage.save_raw_feedbacks([_make_raw_feedback(content="user likes sushi")])
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(query="nonexistent_query"),
        )
        assert results == []

    def test_search_feedbacks_query_no_match(self, storage):
        """Covers search_feedbacks returning empty when query doesn't match."""
        storage.save_feedbacks([_make_feedback(content="always greet users")])
        results = storage.search_feedbacks(
            SearchFeedbackRequest(query="nonexistent_query"),
        )
        assert results == []

    def test_search_skills_query_no_match(self, storage):
        """Covers search_skills returning empty when query doesn't match."""
        storage.save_skills(
            [_make_skill(instructions="Say hello", description="Greeting")]
        )
        results = storage.search_skills(
            SearchSkillsRequest(query="nonexistent_query"),
        )
        assert results == []


# ===========================================================================
# Dashboard stats: items outside both current and previous period
# (lines 2248->2239, 2263->2254, 2278->2270, 2290->2284)
# ===========================================================================


class TestDashboardStatsNoPreviousPeriod:
    def test_data_older_than_both_periods_not_counted(self, storage):
        """Covers branches where timestamp < previous_period_start (neither period)."""
        now = _now_ts()
        days_back = 7
        seconds = days_back * 24 * 60 * 60
        # Place data far outside both periods
        ancient_ts = now - (3 * seconds)

        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=1, created_at=ancient_ts),
        )
        storage.add_user_profile("u1", [_make_profile(timestamp=ancient_ts)])
        storage.save_raw_feedbacks([_make_raw_feedback(created_at=ancient_ts)])
        storage.save_feedbacks([_make_feedback(created_at=ancient_ts)])
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1",
                    session_id="s1",
                    is_success=True,
                    created_at=ancient_ts,
                ),
            ]
        )

        stats = storage.get_dashboard_stats(days_back=days_back)
        assert stats["current_period"]["total_interactions"] == 0
        assert stats["current_period"]["total_profiles"] == 0
        assert stats["current_period"]["total_feedbacks"] == 0
        assert stats["current_period"]["success_rate"] == 0.0
        assert stats["previous_period"]["total_interactions"] == 0
        assert stats["previous_period"]["total_profiles"] == 0
        assert stats["previous_period"]["total_feedbacks"] == 0
        assert stats["previous_period"]["success_rate"] == 0.0

    def test_aggregated_feedback_previous_period(self, storage):
        """Covers line 2290->2284: aggregated feedback in previous period."""
        now = _now_ts()
        days_back = 30
        seconds = days_back * 24 * 60 * 60
        prev_ts = now - seconds - 100

        storage.save_feedbacks([_make_feedback(created_at=prev_ts)])
        stats = storage.get_dashboard_stats(days_back=days_back)
        assert stats["previous_period"]["total_feedbacks"] == 1

    def test_mixed_current_previous_and_ancient_data(self, storage):
        """Covers all period branches with mixed timestamps."""
        now = _now_ts()
        days_back = 7
        seconds = days_back * 24 * 60 * 60
        current_ts = now - 100
        prev_ts = now - seconds - 100
        ancient_ts = now - (3 * seconds)

        # Current period data
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=1, created_at=current_ts),
        )
        # Previous period data
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=2, created_at=prev_ts),
        )
        # Ancient data (neither period)
        storage.add_user_interaction(
            "u1",
            _make_interaction(interaction_id=3, created_at=ancient_ts),
        )

        stats = storage.get_dashboard_stats(days_back=days_back)
        assert stats["current_period"]["total_interactions"] == 1
        assert stats["previous_period"]["total_interactions"] == 1

    def test_evaluation_previous_period_success_rate(self, storage):
        """Covers line 2322-2325: evaluations in previous period."""
        now = _now_ts()
        days_back = 30
        seconds = days_back * 24 * 60 * 60
        prev_ts = now - seconds - 100

        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1",
                    session_id="s1",
                    is_success=True,
                    created_at=prev_ts,
                ),
                AgentSuccessEvaluationResult(
                    agent_version="v1",
                    session_id="s2",
                    is_success=False,
                    created_at=prev_ts,
                ),
            ]
        )

        stats = storage.get_dashboard_stats(days_back=days_back)
        assert stats["previous_period"]["success_rate"] == 50.0
        assert stats["current_period"]["success_rate"] == 0.0


# ===========================================================================
# Remaining CRUD edge cases: delete interaction no-op (line 333),
# raw feedback edge cases (lines 1853-1855),
# search skills with all filters (lines 2534-2542)
# ===========================================================================


class TestRemainingCRUDEdgeCases:
    def test_delete_interaction_no_op_no_interactions_key(self, storage):
        """Covers line 333: user exists but has no 'interactions' key."""
        # Add a profile so user exists, but no interactions
        storage.add_user_profile("u1", [_make_profile(user_id="u1")])
        storage.delete_user_interaction(
            DeleteUserInteractionRequest(user_id="u1", interaction_id=999),
        )
        # Should not raise

    def test_raw_feedback_status_enum_match_in_update(self, storage):
        """Covers lines 1853-1855: Status enum comparison in update_all_raw_feedbacks_status."""
        storage.save_raw_feedbacks([_make_raw_feedback(status=Status.PENDING)])
        count = storage.update_all_raw_feedbacks_status(
            old_status=Status.PENDING,
            new_status=Status.ARCHIVED,
        )
        assert count == 1
        result = storage.get_raw_feedbacks(status_filter=[Status.ARCHIVED])
        assert len(result) == 1

    def test_search_skills_with_all_filters(self, storage):
        """Covers lines 2960-2965: search_skills with query + feedback_name + agent_version + skill_status."""
        storage.save_skills(
            [
                _make_skill(
                    skill_name="greet",
                    feedback_name="fb1",
                    agent_version="v1",
                    instructions="Say hello to user",
                    skill_status=SkillStatus.PUBLISHED,
                ),
                _make_skill(
                    skill_name="farewell",
                    feedback_name="fb2",
                    agent_version="v2",
                    instructions="Say goodbye to user",
                    skill_status=SkillStatus.DRAFT,
                ),
            ]
        )
        results = storage.search_skills(
            SearchSkillsRequest(
                query="hello",
                feedback_name="fb1",
                agent_version="v1",
                skill_status=SkillStatus.PUBLISHED,
            ),
        )
        assert len(results) == 1
        assert results[0].skill_name == "greet"

    def test_search_skills_all_filters_no_match(self, storage):
        """Covers search_skills with filters that exclude all skills."""
        storage.save_skills([_make_skill(skill_name="greet", agent_version="v1")])
        results = storage.search_skills(
            SearchSkillsRequest(agent_version="v99"),
        )
        assert results == []

    def test_add_user_interactions_bulk_auto_id(self, storage):
        """Covers bulk add with auto-increment interaction_id."""
        interactions = [
            _make_interaction(content="a", interaction_id=0),
            _make_interaction(content="b", interaction_id=0),
        ]
        storage.add_user_interactions_bulk("user1", interactions)
        result = storage.get_user_interaction("user1")
        assert len(result) == 2
        ids = {i.interaction_id for i in result}
        assert 1 in ids
        assert 2 in ids

    def test_get_sessions_no_requests_returns_empty(self, storage):
        """Covers line 914: early return when no 'requests' key."""
        result = storage.get_sessions(user_id="u1")
        assert result == {}

    def test_get_sessions_null_session_id_grouped_as_empty_string(self, storage):
        """Covers line 953: request with session_id=None grouped as ''."""
        now = _now_ts()
        storage.add_request(
            _make_request(request_id="r1", session_id=None, created_at=now)
        )
        sessions = storage.get_sessions(user_id="user1")
        assert "" in sessions
        assert len(sessions[""]) == 1

    def test_search_interaction_empty_user(self, storage):
        """Covers search_interaction on user with no interactions."""
        results = storage.search_interaction(
            SearchInteractionRequest(user_id="nonexistent"),
        )
        assert results == []

    def test_dashboard_time_series_data_present(self, storage):
        """Covers time series data points being included in dashboard stats."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        storage.add_user_profile("u1", [_make_profile(timestamp=now)])
        storage.save_raw_feedbacks([_make_raw_feedback(created_at=now)])
        storage.save_agent_success_evaluation_results(
            [
                AgentSuccessEvaluationResult(
                    agent_version="v1",
                    session_id="s1",
                    is_success=False,
                    created_at=now,
                ),
            ]
        )
        stats = storage.get_dashboard_stats()
        assert len(stats["interactions_time_series"]) == 1
        assert len(stats["profiles_time_series"]) == 1
        assert len(stats["feedbacks_time_series"]) == 1
        assert len(stats["evaluations_time_series"]) == 1
        assert (
            stats["evaluations_time_series"][0]["value"] == 0
        )  # is_success=False -> 0


# ===========================================================================
# Operation state with new request interaction: timestamp-based filtering
# (lines 2534-2542, 2502, 2506->2510, 2543->2530)
# ===========================================================================


class TestOpStateTimestampFiltering:
    def _set_op_state_directly(self, storage, service_name, state_data):
        """Write operation state directly into storage JSON for precise control."""
        import json
        from pathlib import Path

        all_memories = json.loads(Path(storage.file_path).read_text())
        if "operation_states" not in all_memories:
            all_memories["operation_states"] = {}
        all_memories["operation_states"][service_name] = state_data
        Path(storage.file_path).write_text(json.dumps(all_memories))

    def test_newer_timestamp_collected(self, storage):
        """Covers line 2534: created_at > last_processed_timestamp."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now - 200)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now)
        )
        # Write operation state directly with last_processed_timestamp at top level
        self._set_op_state_directly(
            storage,
            "svc1",
            {
                "last_processed_interaction_ids": ["1"],
                "last_processed_timestamp": now - 100,
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        assert 2 in all_ids
        assert 1 not in all_ids

    def test_same_timestamp_not_in_processed_set(self, storage):
        """Covers lines 2537-2542: same timestamp, id not in processed set triggers collection."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=10, created_at=now)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=20, created_at=now)
        )
        # processed_set contains string "10"; interaction_id=10 (int) won't match
        # so interactions at same timestamp with ids NOT in processed_set are collected
        self._set_op_state_directly(
            storage,
            "svc1",
            {
                "last_processed_interaction_ids": [],
                "last_processed_timestamp": now,
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        # Both have same timestamp as last_processed and ids not in empty processed set
        assert 10 in all_ids
        assert 20 in all_ids

    def test_older_timestamp_skipped(self, storage):
        """Covers implicit skip: created_at < last_processed_timestamp and created_at != last_processed_timestamp."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now - 200)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now + 100)
        )
        self._set_op_state_directly(
            storage,
            "svc1",
            {
                "last_processed_interaction_ids": [],
                "last_processed_timestamp": now,
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        # interaction 1 is older than last_processed_timestamp and not == timestamp -> skipped
        assert 1 not in all_ids
        # interaction 2 is newer -> collected
        assert 2 in all_ids

    def test_last_processed_ids_not_list_normalized(self, storage):
        """Covers line 2502: last_processed_interaction_ids is not a list."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        self._set_op_state_directly(
            storage,
            "svc1",
            {
                "last_processed_interaction_ids": "not_a_list",
                "last_processed_timestamp": now - 100,
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        assert 1 in all_ids

    def test_no_processed_timestamp_uses_id_check(self, storage):
        """Covers line 2543: no last_processed_timestamp, falls to id-based check."""
        now = _now_ts()
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=1, created_at=now)
        )
        storage.add_user_interaction(
            "u1", _make_interaction(interaction_id=2, created_at=now)
        )
        # No last_processed_timestamp -> goes to elif branch (line 2543)
        # processed_set = {"1"}, but interaction_id is int, so int not in set of strings
        # Both interactions collected
        self._set_op_state_directly(
            storage,
            "svc1",
            {
                "last_processed_interaction_ids": ["1"],
            },
        )
        _, sessions = storage.get_operation_state_with_new_request_interaction(
            "svc1", "u1"
        )
        all_ids = [i.interaction_id for s in sessions for i in s.interactions]
        # Both collected because int ids don't match string processed set
        assert 1 in all_ids
        assert 2 in all_ids


# ===========================================================================
# get_last_k_interactions_grouped: agent_version filter (line 2670)
# ===========================================================================


class TestGetLastKAgentVersionFilter:
    def test_agent_version_filter_excludes_non_matching(self, storage):
        """Covers line 2667-2670: agent_version filter."""
        now = _now_ts()
        storage.add_request(_make_request(request_id="r1", agent_version="v1"))
        storage.add_request(_make_request(request_id="r2", agent_version="v2"))
        storage.add_user_interaction(
            "u1",
            _make_interaction(request_id="r1", interaction_id=1, created_at=now),
        )
        storage.add_user_interaction(
            "u1",
            _make_interaction(request_id="r2", interaction_id=2, created_at=now),
        )
        _, flat = storage.get_last_k_interactions_grouped(
            user_id="u1",
            k=10,
            agent_version="v1",
        )
        assert len(flat) == 1
        assert flat[0].request_id == "r1"

    def test_agent_version_filter_no_request_found(self, storage):
        """Covers line 2668: agent_version filter with request=None."""
        now = _now_ts()
        # Add interaction without a corresponding request
        storage.add_user_interaction(
            "u1",
            _make_interaction(
                request_id="nonexistent", interaction_id=1, created_at=now
            ),
        )
        _, flat = storage.get_last_k_interactions_grouped(
            user_id="u1",
            k=10,
            agent_version="v1",
        )
        assert len(flat) == 0


# ===========================================================================
# add_user_interactions_bulk: missing interactions key (line 332-333)
# ===========================================================================


class TestBulkInteractionsMissingKey:
    def test_bulk_add_user_exists_no_interactions_key(self, storage):
        """Covers line 332-333: user exists but no 'interactions' key."""
        import json
        from pathlib import Path

        all_memories = json.loads(Path(storage.file_path).read_text())
        all_memories["u1"] = {"profiles": []}  # user exists but no interactions
        Path(storage.file_path).write_text(json.dumps(all_memories))

        interactions = [_make_interaction(content="a", interaction_id=0)]
        storage.add_user_interactions_bulk("u1", interactions)
        result = storage.get_user_interaction("u1")
        assert len(result) == 1


# ===========================================================================
# search_raw_feedbacks user_id filter via request_id map (lines 2016-2019, 2027-2029)
# ===========================================================================


class TestSearchRawFeedbacksUserIdFilter:
    def test_search_raw_feedbacks_user_id_no_requests_stored(self, storage):
        """Covers line 2016: user_id filter with no stored requests -> empty map."""
        storage.save_raw_feedbacks(
            [_make_raw_feedback(request_id="r1", content="orphan feedback")]
        )
        # user_id is set but no requests exist -> request_user_map is empty
        # -> feedback's request not in map -> skipped
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(user_id="u1"),
        )
        assert results == []

    def test_search_raw_feedbacks_no_user_id_returns_all(self, storage):
        """Covers search_raw_feedbacks without user_id filter returns all."""
        storage.save_raw_feedbacks(
            [
                _make_raw_feedback(content="fb1", user_id="u1"),
                _make_raw_feedback(content="fb2", user_id="u2"),
            ]
        )
        results = storage.search_raw_feedbacks(
            SearchRawFeedbackRequest(),
        )
        assert len(results) == 2
