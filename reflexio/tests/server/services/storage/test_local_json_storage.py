import tempfile
from datetime import datetime, timezone

from reflexio_commons.api_schema.retriever_schema import (
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    NEVER_EXPIRES_TIMESTAMP,
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
    Interaction,
    ProfileChangeLog,
    ProfileTimeToLive,
    Request,
    UserActionType,
    UserProfile,
)

from reflexio.server.services.storage.local_json_storage import LocalJsonStorage


def test_get_user_profile():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)
        storage.add_user_profile(
            "test_user_id",
            [
                UserProfile(
                    user_id="test_user_id",
                    profile_id="1",
                    profile_content="I like sushi",
                    last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
                    generated_from_request_id="request_id_1",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    source="test_source",
                )
            ],
        )

        profiles = storage.get_user_profile("test_user_id")
        assert len(profiles) == 1
        assert profiles[0].profile_content == "I like sushi"
        assert profiles[0].generated_from_request_id == "request_id_1"
        assert profiles[0].profile_time_to_live == ProfileTimeToLive.INFINITY
        assert profiles[0].source == "test_source"


def test_get_all_profiles():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)

        # Add profiles for two different users
        storage.add_user_profile(
            "user1",
            [
                UserProfile(
                    user_id="user1",
                    profile_id="1",
                    profile_content="I like sushi",
                    last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
                    generated_from_request_id="request_id_1",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    source="test_source",
                )
            ],
        )

        storage.add_user_profile(
            "user2",
            [
                UserProfile(
                    user_id="user2",
                    profile_id="2",
                    profile_content="I like pizza",
                    last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
                    generated_from_request_id="request_id_2",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    source="test_source",
                )
            ],
        )

        profiles = storage.get_all_profiles()
        assert len(profiles) == 2
        # Sort by profile_id to ensure consistent order
        profiles = sorted(profiles, key=lambda x: x.profile_id)
        assert profiles[0].profile_content == "I like sushi"
        assert profiles[1].profile_content == "I like pizza"
        assert profiles[0].source == "test_source"
        assert profiles[1].source == "test_source"


def test_get_all_interactions():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)

        # Add interactions for a user
        interaction1 = Interaction(
            interaction_id=1,
            user_id="user1",
            request_id="request1",
            content="I like sushi",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="Clicked sushi",
            interacted_image_url="https://example.com/sushi.jpg",
        )

        interaction2 = Interaction(
            interaction_id=2,
            user_id="user1",
            request_id="request2",
            content="I like pizza",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="Clicked pizza",
            interacted_image_url="https://example.com/pizza.jpg",
        )

        storage.add_user_interaction("user1", interaction1)
        storage.add_user_interaction("user1", interaction2)

        interactions = storage.get_all_interactions()
        assert len(interactions) == 2
        # Sort by interaction_id to ensure consistent order
        interactions = sorted(interactions, key=lambda x: x.interaction_id)
        assert interactions[0].content == "I like sushi"
        assert interactions[1].content == "I like pizza"


def test_get_rerun_user_ids_with_filters():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)
        now = int(datetime.now(timezone.utc).timestamp())

        storage.add_request(
            Request(
                request_id="req1",
                user_id="user1",
                created_at=now - 30,
                source="api",
                agent_version="v1",
                session_id="group1",
            )
        )
        storage.add_request(
            Request(
                request_id="req2",
                user_id="user1",
                created_at=now - 20,
                source="api",
                agent_version="v1",
                session_id="group1",
            )
        )
        storage.add_request(
            Request(
                request_id="req3",
                user_id="user2",
                created_at=now - 10,
                source="web",
                agent_version="v1",
                session_id="group2",
            )
        )

        result = storage.get_rerun_user_ids(
            start_time=now - 40,
            end_time=now - 5,
            source="api",
            agent_version="v1",
        )

        assert result == ["user1"]


def test_search_user_profile():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)
        timestamp = int(datetime.now(timezone.utc).timestamp())

        storage.add_user_profile(
            "user1",
            [
                UserProfile(
                    user_id="user1",
                    profile_id="1",
                    profile_content="I like sushi and ramen",
                    last_modified_timestamp=timestamp,
                    generated_from_request_id="request_id_1",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    source="test_source",
                )
            ],
        )

        # Search by content
        search_request = SearchUserProfileRequest(
            user_id="user1",
            query="sushi",
        )
        profiles = storage.search_user_profile(search_request)
        assert len(profiles) == 1
        assert "sushi" in profiles[0].profile_content
        assert profiles[0].source == "test_source"

        # Search by request_id
        search_request = SearchUserProfileRequest(
            user_id="user1",
            generated_from_request_id="request_id_1",
        )
        profiles = storage.search_user_profile(search_request)
        assert len(profiles) == 1
        assert profiles[0].generated_from_request_id == "request_id_1"


def test_search_interaction():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)
        timestamp = int(datetime.now(timezone.utc).timestamp())

        interaction = Interaction(
            interaction_id=1,
            user_id="user1",
            request_id="request1",
            content="I like sushi",
            created_at=timestamp,
            user_action=UserActionType.CLICK,
            user_action_description="Clicked sushi",
            interacted_image_url="https://example.com/sushi.jpg",
        )

        storage.add_user_interaction("user1", interaction)

        # Search by content
        search_request = SearchInteractionRequest(
            user_id="user1",
            query="sushi",
        )
        interactions = storage.search_interaction(search_request)
        assert len(interactions) == 1
        assert "sushi" in interactions[0].content

        # Search by request_id
        search_request = SearchInteractionRequest(
            user_id="user1",
            request_id="request1",
        )
        interactions = storage.search_interaction(search_request)
        assert len(interactions) == 1
        assert interactions[0].request_id == "request1"


def test_delete_user_profile():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)

        profile = UserProfile(
            user_id="user1",
            profile_id="1",
            profile_content="I like sushi",
            last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
            generated_from_request_id="request_id_1",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            source="test_source",
        )

        storage.add_user_profile("user1", [profile])

        # Verify profile exists
        profiles = storage.get_user_profile("user1")
        assert len(profiles) == 1

        # Delete profile
        delete_request = DeleteUserProfileRequest(
            user_id="user1",
            profile_id="1",
        )
        storage.delete_user_profile(delete_request)

        # Verify profile was deleted
        profiles = storage.get_user_profile("user1")
        assert len(profiles) == 0


def test_delete_user_interaction():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)

        interaction = Interaction(
            interaction_id=1,
            user_id="user1",
            request_id="request1",
            content="I like sushi",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="Clicked sushi",
            interacted_image_url="https://example.com/sushi.jpg",
        )

        storage.add_user_interaction("user1", interaction)

        # Verify interaction exists
        interactions = storage.get_user_interaction("user1")
        assert len(interactions) == 1

        # Delete interaction
        delete_request = DeleteUserInteractionRequest(
            user_id="user1",
            interaction_id=1,
        )
        storage.delete_user_interaction(delete_request)

        # Verify interaction was deleted
        interactions = storage.get_user_interaction("user1")
        assert len(interactions) == 0


def test_update_user_profile_by_id():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="0", base_dir=temp_dir)

        original_profile = UserProfile(
            user_id="user1",
            profile_id="1",
            profile_content="I like sushi",
            last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
            generated_from_request_id="request_id_1",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            source="test_source",
        )

        storage.add_user_profile("user1", [original_profile])

        # Create updated profile
        updated_profile = UserProfile(
            user_id="user1",
            profile_id="1",
            profile_content="I now prefer ramen",
            last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
            generated_from_request_id="request_id_1",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            source="test_source",
        )

        # Update profile
        storage.update_user_profile_by_id(
            user_id="user1",
            profile_id="1",
            new_profile=updated_profile,
        )

        # Verify profile was updated
        profiles = storage.get_user_profile("user1")
        assert len(profiles) == 1
        assert profiles[0].profile_content == "I now prefer ramen"
        assert profiles[0].source == "test_source"


def test_profile_change_log_operations():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalJsonStorage(org_id="test_org", base_dir=temp_dir)
        current_time = int(datetime.now(timezone.utc).timestamp())

        # Create a profile change log
        profile_change_log = ProfileChangeLog(
            id=1,
            user_id="test_user",
            request_id="test_request",
            created_at=current_time,
            added_profiles=[
                UserProfile(
                    profile_id="test_profile",
                    user_id="test_user",
                    profile_content="Test content",
                    last_modified_timestamp=current_time,
                    generated_from_request_id="test_request",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
                    source="test_source",
                )
            ],
            removed_profiles=[],
            mentioned_profiles=[],
        )

        # Test adding profile change log
        storage.add_profile_change_log(profile_change_log)

        # Test getting profile change logs
        logs = storage.get_profile_change_logs(limit=10)
        assert len(logs) == 1
        assert logs[0].id == profile_change_log.id
        assert logs[0].user_id == profile_change_log.user_id
        assert logs[0].request_id == profile_change_log.request_id
        assert len(logs[0].added_profiles) == 1
        assert logs[0].added_profiles[0].profile_content == "Test content"

        # Test deleting profile change log for user
        storage.delete_profile_change_log_for_user("test_user")
        logs = storage.get_profile_change_logs(limit=10)
        assert len(logs) == 0

        # Test deleting profile change logs for org
        storage.add_profile_change_log(profile_change_log)
        storage.delete_all_profile_change_logs()
        logs = storage.get_profile_change_logs(limit=10)
        assert len(logs) == 0


if __name__ == "__main__":
    test_get_user_profile()
    test_profile_change_log_operations()
