"""Tests for SupabaseStorage implementation."""

from datetime import datetime, timezone
from unittest.mock import Mock, call, patch

import pytest
from reflexio_commons.api_schema.retriever_schema import (
    Interaction,
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    NEVER_EXPIRES_TIMESTAMP,
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
    FeedbackStatus,
    ProfileChangeLog,
    ProfileTimeToLive,
    RawFeedback,
    Status,
    UserActionType,
    UserProfile,
)
from reflexio_commons.config_schema import StorageConfigSupabase


@pytest.fixture
def mock_supabase_client():
    with patch(
        "reflexio.server.services.storage.supabase_storage.create_client"
    ) as mock_create_client:
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_openai():
    with patch(
        "reflexio.server.services.storage.supabase_storage.LiteLLMClient"
    ) as mock_llm:
        mock_client = Mock()
        mock_client.get_embedding.return_value = [0.1] * 512  # Mock embedding vector
        mock_llm.return_value = mock_client
        yield mock_client


@pytest.fixture
def supabase_storage(mock_supabase_client, mock_openai):
    with patch("reflexio.server.OPENAI_API_KEY", "test-openai-key"):
        from reflexio.server.services.storage.supabase_storage import SupabaseStorage

        config = StorageConfigSupabase(
            url="https://test.supabase.co",
            key="test-key",
            db_url="postgresql://test:test@localhost:5432/test",
        )
        storage = SupabaseStorage(org_id="test", config=config)
        return storage  # noqa: RET504


@pytest.fixture
def user_profile_data():
    return {
        "user_id": "1@123",
        "profile": UserProfile(
            profile_id="profile_id_1",
            user_id="1@123",
            profile_content="I like sushi",
            last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
            generated_from_request_id="request_id_1",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            source="test_source",
        ),
        "expired_profile": UserProfile(
            profile_id="profile_id_2",
            user_id="1@123",
            profile_content="I like pizza",
            last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
            generated_from_request_id="request_id_2",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=int(datetime(1999, 1, 1).timestamp()),
            source="test_source",
        ),
        "interaction": Interaction(
            interaction_id=1,
            user_id="1@123",
            request_id="request_id_1",
            content="I like sushi",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="I clicked on the sushi image",
            interacted_image_url="https://example.com/sushi.jpg",
        ),
    }


@pytest.fixture
def profile_change_log_data():
    current_time = int(datetime.now(timezone.utc).timestamp())
    return {
        "id": 1,
        "user_id": "1@123",
        "request_id": "request_id_1",
        "created_at": current_time,
        "added_profiles": [
            UserProfile(
                profile_id="profile_id_1",
                user_id="1@123",
                profile_content="I like sushi",
                last_modified_timestamp=current_time,
                generated_from_request_id="request_id_1",
                profile_time_to_live=ProfileTimeToLive.INFINITY,
                expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            )
        ],
        "removed_profiles": [],
        "mentioned_profiles": [],
    }


@pytest.fixture
def feedback_data():
    current_time = int(datetime.now(timezone.utc).timestamp())
    return {
        "raw_feedback": RawFeedback(
            raw_feedback_id=1,
            feedback_name="test_raw_feedback",
            request_id="request_id_1",
            agent_version="test_agent_v1",
            feedback_content="The agent was very helpful and provided accurate information",
            created_at=current_time,
            embedding=[0.1] * 512,
        ),
        "feedback_dict": {
            "feedback_id": 1,
            "feedback_name": "test_feedback",
            "feedback_content": "The agent response was clear and concise",
            "feedback_status": "approved",
            "agent_version": "test_agent_v1",
            "feedback_metadata": "metadata_content",
            "created_at": datetime.fromtimestamp(current_time).isoformat(),
            "similarity": 0.85,
            "embedding": str([0.1] * 512),
        },
        "raw_feedback_dict": {
            "raw_feedback_id": 1,
            "feedback_name": "test_raw_feedback",
            "request_id": "request_id_1",
            "agent_version": "test_agent_v1",
            "feedback_content": "The agent was very helpful and provided accurate information",
            "created_at": datetime.fromtimestamp(current_time).isoformat(),
            "similarity": 0.90,
            "embedding": str([0.1] * 512),
        },
    }


def test_get_user_profile(supabase_storage, user_profile_data, mock_supabase_client):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    profile = user_profile_data["profile"]

    # Mock the response from Supabase
    mock_response = Mock()
    mock_response.data = [
        {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "content": profile.profile_content,
            "last_modified_timestamp": profile.last_modified_timestamp,
            "generated_from_request_id": profile.generated_from_request_id,
            "profile_time_to_live": profile.profile_time_to_live.value,
            "expiration_timestamp": profile.expiration_timestamp,
            "custom_features": None,
            "source": profile.source,
        }
    ]
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.gte.return_value.is_.return_value.execute.return_value = mock_response

    profiles = storage.get_user_profile(user_id)
    assert len(profiles) == 1
    assert profiles[0].profile_content == "I like sushi"
    assert profiles[0].generated_from_request_id == "request_id_1"
    assert profiles[0].profile_time_to_live == ProfileTimeToLive.INFINITY
    assert profiles[0].source == "test_source"


def test_get_user_profile_with_expired_profile(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    user_profile_data["expired_profile"]

    # Mock empty response for expired profile
    mock_response = Mock()
    mock_response.data = []
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.gte.return_value.is_.return_value.execute.return_value = mock_response

    profiles = storage.get_user_profile(user_id)
    assert len(profiles) == 0


def test_search_user_profile(
    supabase_storage, user_profile_data, mock_supabase_client, mock_openai
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    profile = user_profile_data["profile"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [
        {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "content": profile.profile_content,
            "last_modified_timestamp": profile.last_modified_timestamp,
            "generated_from_request_id": profile.generated_from_request_id,
            "profile_time_to_live": profile.profile_time_to_live.value,
            "expiration_timestamp": profile.expiration_timestamp,
            "custom_features": None,
            "source": profile.source,
        }
    ]

    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query="I like sushi",
    )
    profiles = storage.search_user_profile(search_request)
    assert len(profiles) == 1
    assert profiles[0].profile_content == "I like sushi"
    assert profiles[0].generated_from_request_id == "request_id_1"
    assert profiles[0].profile_time_to_live == ProfileTimeToLive.INFINITY
    assert profiles[0].source == "test_source"


def test_search_interaction(
    supabase_storage, user_profile_data, mock_supabase_client, mock_openai
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    interaction = user_profile_data["interaction"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [
        {
            "interaction_id": interaction.interaction_id,
            "user_id": interaction.user_id,
            "content": interaction.content,
            "request_id": interaction.request_id,
            "created_at": datetime.fromtimestamp(interaction.created_at).isoformat(),
            "user_action": interaction.user_action.value,
            "user_action_description": interaction.user_action_description,
            "interacted_image_url": interaction.interacted_image_url,
        }
    ]

    search_request = SearchInteractionRequest(
        user_id=user_id,
        query="I like sushi",
    )
    interactions = storage.search_interaction(search_request)
    assert len(interactions) == 1
    assert interactions[0].content == "I like sushi"
    assert interactions[0].user_action == UserActionType.CLICK
    assert interactions[0].user_action_description == "I clicked on the sushi image"
    assert interactions[0].interacted_image_url == "https://example.com/sushi.jpg"


def test_get_all_profiles(supabase_storage, user_profile_data, mock_supabase_client):
    storage = supabase_storage
    profile = user_profile_data["profile"]
    expired_profile = user_profile_data["expired_profile"]

    # Mock the response from Supabase
    mock_response = Mock()
    mock_response.data = [
        {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "content": profile.profile_content,
            "last_modified_timestamp": profile.last_modified_timestamp,
            "generated_from_request_id": profile.generated_from_request_id,
            "profile_time_to_live": profile.profile_time_to_live.value,
            "expiration_timestamp": profile.expiration_timestamp,
            "custom_features": None,
            "source": profile.source,
        },
        {
            "profile_id": expired_profile.profile_id,
            "user_id": expired_profile.user_id,
            "content": expired_profile.profile_content,
            "last_modified_timestamp": expired_profile.last_modified_timestamp,
            "generated_from_request_id": expired_profile.generated_from_request_id,
            "profile_time_to_live": expired_profile.profile_time_to_live.value,
            "expiration_timestamp": expired_profile.expiration_timestamp,
            "custom_features": None,
            "source": expired_profile.source,
        },
    ]
    mock_supabase_client.table.return_value.select.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

    profiles = storage.get_all_profiles()
    assert len(profiles) == 2
    # Sort by profile_id to ensure consistent order
    profiles = sorted(profiles, key=lambda x: x.profile_id)
    assert profiles[0].profile_content == "I like sushi"
    assert profiles[1].profile_content == "I like pizza"
    assert profiles[0].source == "test_source"
    assert profiles[1].source == "test_source"


def test_get_all_interactions(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    interaction = user_profile_data["interaction"]

    # Mock the response from Supabase
    mock_supabase_client.table().select().order().limit().execute.return_value.data = [
        {
            "interaction_id": interaction.interaction_id,
            "user_id": interaction.user_id,
            "content": interaction.content,
            "request_id": interaction.request_id,
            "created_at": datetime.fromtimestamp(interaction.created_at).isoformat(),
            "user_action": interaction.user_action.value,
            "user_action_description": interaction.user_action_description,
            "interacted_image_url": interaction.interacted_image_url,
        }
    ]

    interactions = storage.get_all_interactions()
    assert len(interactions) == 1
    assert interactions[0].content == "I like sushi"
    assert interactions[0].user_action == UserActionType.CLICK


def test_get_user_interaction(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    interaction = user_profile_data["interaction"]

    # Mock the response from Supabase
    mock_supabase_client.table().select().eq().execute.return_value.data = [
        {
            "interaction_id": interaction.interaction_id,
            "user_id": interaction.user_id,
            "content": interaction.content,
            "request_id": interaction.request_id,
            "created_at": datetime.fromtimestamp(interaction.created_at).isoformat(),
            "user_action": interaction.user_action.value,
            "user_action_description": interaction.user_action_description,
            "interacted_image_url": interaction.interacted_image_url,
        }
    ]

    interactions = storage.get_user_interaction(user_id)
    assert len(interactions) == 1
    assert interactions[0].content == "I like sushi"
    assert interactions[0].user_action == UserActionType.CLICK


def test_delete_user_interaction(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    interaction = user_profile_data["interaction"]

    # Mock empty response after deletion
    mock_supabase_client.table().select().eq().execute.return_value.data = []

    delete_request = DeleteUserInteractionRequest(
        user_id=user_id, interaction_id=interaction.interaction_id
    )
    storage.delete_user_interaction(delete_request)

    # Verify the delete method was called with correct parameters
    mock_supabase_client.table().delete().eq().eq().execute.assert_called_once()


def test_delete_user_profile(supabase_storage, user_profile_data, mock_supabase_client):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    profile = user_profile_data["profile"]

    # Mock empty response after deletion
    mock_supabase_client.table().select().eq().eq().gte().execute.return_value.data = []

    delete_request = DeleteUserProfileRequest(
        user_id=user_id, profile_id=profile.profile_id
    )
    storage.delete_user_profile(delete_request)

    # Verify the delete method was called with correct parameters
    mock_supabase_client.table().delete().eq().eq().execute.assert_called_once()


def test_update_user_profile_by_id(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]
    original_profile = user_profile_data["profile"]

    # Mock the response for profile existence check
    mock_supabase_client.table().select().eq().eq().gte().execute.return_value.data = [
        {"id": original_profile.profile_id}
    ]

    # Create updated profile
    updated_profile = UserProfile(
        profile_id=original_profile.profile_id,
        user_id=user_id,
        profile_content="I like ramen",
        last_modified_timestamp=int(datetime.now(timezone.utc).timestamp()),
        generated_from_request_id="request_id_2",
        profile_time_to_live=ProfileTimeToLive.INFINITY,
        expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
        source="test_source",
    )

    storage.update_user_profile_by_id(
        user_id, original_profile.profile_id, updated_profile
    )

    # Verify the update method was called with correct parameters
    mock_supabase_client.table().update().eq().execute.assert_called_once()


def test_delete_all_interactions_for_user(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]

    storage.delete_all_interactions_for_user(user_id)

    # Verify the delete method was called with correct parameters
    mock_supabase_client.table().delete().eq().execute.assert_called_once()


def test_delete_all_profiles_for_user(
    supabase_storage, user_profile_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = user_profile_data["user_id"]

    storage.delete_all_profiles_for_user(user_id)

    # Verify the delete method was called with correct parameters
    mock_supabase_client.table().delete().eq().execute.assert_called_once()


def test_add_profile_change_log(
    supabase_storage, profile_change_log_data, mock_supabase_client
):
    storage = supabase_storage
    profile_change_log = ProfileChangeLog(**profile_change_log_data)

    storage.add_profile_change_log(profile_change_log)

    # Verify the upsert method was called with correct parameters
    mock_supabase_client.table().upsert().execute.assert_called_once()


def test_get_profile_change_logs(
    supabase_storage, profile_change_log_data, mock_supabase_client
):
    storage = supabase_storage
    profile_change_log = ProfileChangeLog(**profile_change_log_data)

    # Mock the response from Supabase
    mock_supabase_client.table().select().order().limit().execute.return_value.data = [
        {
            "id": profile_change_log.id,
            "user_id": profile_change_log.user_id,
            "request_id": profile_change_log.request_id,
            "created_at": profile_change_log.created_at,  # Keep as integer timestamp
            "added_profiles": [
                profile.model_dump() for profile in profile_change_log.added_profiles
            ],
            "removed_profiles": [
                profile.model_dump() for profile in profile_change_log.removed_profiles
            ],
            "mentioned_profiles": [
                profile.model_dump()
                for profile in profile_change_log.mentioned_profiles
            ],
        }
    ]

    logs = storage.get_profile_change_logs(limit=10)
    assert len(logs) == 1
    assert logs[0].id == profile_change_log.id
    assert logs[0].user_id == profile_change_log.user_id
    assert logs[0].request_id == profile_change_log.request_id
    assert logs[0].created_at == profile_change_log.created_at
    assert len(logs[0].added_profiles) == len(profile_change_log.added_profiles)
    assert len(logs[0].removed_profiles) == len(profile_change_log.removed_profiles)
    assert len(logs[0].mentioned_profiles) == len(profile_change_log.mentioned_profiles)


def test_delete_profile_change_log_for_user(
    supabase_storage, profile_change_log_data, mock_supabase_client
):
    storage = supabase_storage
    user_id = profile_change_log_data["user_id"]

    storage.delete_profile_change_log_for_user(user_id)

    # Verify the delete method was called with correct parameters
    mock_supabase_client.table().delete().eq().execute.assert_called_once()


def test_search_feedbacks(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching feedbacks using vector embedding similarity."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [feedback_dict]

    results = storage.search_feedbacks(
        query="agent performance feedback", match_threshold=0.8, match_count=5
    )

    assert len(results) == 1
    result = results[0]
    assert result.feedback_content == "The agent response was clear and concise"
    assert result.feedback_status == "approved"
    assert result.agent_version == "test_agent_v1"

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "agent performance feedback",
            "p_match_threshold": 0.8,
            "p_match_count": 50,  # 5 * 10 for filtering overhead
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_raw_feedbacks(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching raw feedbacks using vector embedding similarity."""
    storage = supabase_storage
    raw_feedback_dict = feedback_data["raw_feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [raw_feedback_dict]

    results = storage.search_raw_feedbacks(
        query="helpful agent response", match_threshold=0.7, match_count=10
    )

    assert len(results) == 1
    result = results[0]
    assert (
        result.feedback_content
        == "The agent was very helpful and provided accurate information"
    )
    assert result.request_id == "request_id_1"
    assert result.agent_version == "test_agent_v1"

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_raw_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "helpful agent response",
            "p_match_threshold": 0.7,
            "p_match_count": 100,  # 10 * 10 for filtering overhead
            "p_filter_user_id": None,
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_feedbacks_with_default_parameters(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching feedbacks with default parameters."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [feedback_dict]

    results = storage.search_feedbacks(query="agent feedback")

    assert len(results) == 1

    # Verify the RPC was called with default parameters (now uses hybrid function)
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "agent feedback",
            "p_match_threshold": 0.5,  # Default threshold
            "p_match_count": 100,  # Get more results for filtering
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_raw_feedbacks_with_default_parameters(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching raw feedbacks with default parameters."""
    storage = supabase_storage
    raw_feedback_dict = feedback_data["raw_feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [raw_feedback_dict]

    results = storage.search_raw_feedbacks(query="helpful feedback")

    assert len(results) == 1

    # Verify the RPC was called with default parameters (now uses hybrid function)
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_raw_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "helpful feedback",
            "p_match_threshold": 0.5,  # Default threshold
            "p_match_count": 100,  # Get more results for filtering
            "p_filter_user_id": None,
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_feedbacks_empty_results(
    supabase_storage, mock_supabase_client, mock_openai
):
    """Test searching feedbacks when no results are found."""
    storage = supabase_storage

    # Mock empty response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = []

    results = storage.search_feedbacks(
        query="completely unrelated query", match_threshold=0.9, match_count=5
    )

    assert len(results) == 0
    assert isinstance(results, list)

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "completely unrelated query",
            "p_match_threshold": 0.9,
            "p_match_count": 50,  # 5 * 10 for filtering overhead
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_raw_feedbacks_empty_results(
    supabase_storage, mock_supabase_client, mock_openai
):
    """Test searching raw feedbacks when no results are found."""
    storage = supabase_storage

    # Mock empty response from Supabase
    mock_supabase_client.rpc().execute.return_value.data = []

    results = storage.search_raw_feedbacks(
        query="completely unrelated query", match_threshold=0.95, match_count=3
    )

    assert len(results) == 0
    assert isinstance(results, list)

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_raw_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "completely unrelated query",
            "p_match_threshold": 0.95,
            "p_match_count": 30,  # 3 * 10 for filtering overhead
            "p_filter_user_id": None,
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_feedbacks_multiple_results(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching feedbacks with multiple results."""
    storage = supabase_storage
    feedback_dict_1 = feedback_data["feedback_dict"]
    feedback_dict_2 = {
        "feedback_id": 2,
        "feedback_name": "test_feedback_2",
        "feedback_content": "The agent could be more responsive",
        "feedback_status": "pending",
        "agent_version": "test_agent_v2",
        "feedback_metadata": "metadata_content_2",
        "created_at": "2023-01-02T00:00:00Z",
        "similarity": 0.75,
        "embedding": str([0.1] * 512),
    }

    # Mock multiple results from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [
        feedback_dict_1,
        feedback_dict_2,
    ]

    results = storage.search_feedbacks(
        query="agent feedback analysis", match_threshold=0.7, match_count=5
    )

    assert len(results) == 2

    # Verify first result
    assert results[0].feedback_content == "The agent response was clear and concise"
    assert results[0].feedback_status == "approved"
    assert results[0].feedback_name == "test_feedback"

    # Verify second result
    assert results[1].feedback_content == "The agent could be more responsive"
    assert results[1].feedback_status == "pending"
    assert results[1].feedback_name == "test_feedback_2"

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "agent feedback analysis",
            "p_match_threshold": 0.7,
            "p_match_count": 50,  # 5 * 10 for filtering overhead
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_search_raw_feedbacks_multiple_results(
    supabase_storage, feedback_data, mock_supabase_client, mock_openai
):
    """Test searching raw feedbacks with multiple results."""
    storage = supabase_storage
    raw_feedback_dict_1 = feedback_data["raw_feedback_dict"]
    raw_feedback_dict_2 = {
        "raw_feedback_id": 2,
        "feedback_name": "test_raw_feedback_2",
        "request_id": "request_id_2",
        "agent_version": "test_agent_v2",
        "feedback_content": "The agent needs improvement in understanding context",
        "created_at": "2023-01-02T00:00:00Z",
        "similarity": 0.72,
        "embedding": str([0.1] * 512),
    }

    # Mock multiple results from Supabase
    mock_supabase_client.rpc().execute.return_value.data = [
        raw_feedback_dict_1,
        raw_feedback_dict_2,
    ]

    results = storage.search_raw_feedbacks(
        query="agent performance feedback", match_threshold=0.6, match_count=10
    )

    assert len(results) == 2

    # Verify first result
    assert (
        results[0].feedback_content
        == "The agent was very helpful and provided accurate information"
    )
    assert results[0].feedback_name == "test_raw_feedback"

    # Verify second result
    assert (
        results[1].feedback_content
        == "The agent needs improvement in understanding context"
    )
    assert results[1].feedback_name == "test_raw_feedback_2"

    # Verify the RPC was called with correct parameters (now uses hybrid function)
    # Note: match_count is multiplied by 10 to fetch more results for Python-side filtering
    mock_supabase_client.rpc.assert_called_with(
        "hybrid_match_raw_feedbacks",
        {
            "p_query_embedding": [0.1] * 512,  # Mock embedding
            "p_query_text": "agent performance feedback",
            "p_match_threshold": 0.6,
            "p_match_count": 100,  # 10 * 10 for filtering overhead
            "p_filter_user_id": None,
            "p_search_mode": "hybrid",
            "p_rrf_k": 60,
        },
    )


def test_get_raw_feedbacks(supabase_storage, feedback_data, mock_supabase_client):
    """Test retrieving raw feedbacks with get_raw_feedbacks."""
    storage = supabase_storage
    raw_feedback_dict = feedback_data["raw_feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.table().select().order().limit().execute.return_value.data = [
        raw_feedback_dict
    ]

    results = storage.get_raw_feedbacks(limit=100)

    assert len(results) == 1
    assert (
        results[0].feedback_content
        == "The agent was very helpful and provided accurate information"
    )
    assert results[0].feedback_name == "test_raw_feedback"
    assert results[0].request_id == "request_id_1"


def test_get_raw_feedbacks_with_feedback_name(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving raw feedbacks filtered by feedback_name."""
    storage = supabase_storage
    raw_feedback_dict = feedback_data["raw_feedback_dict"]

    # Mock the response from Supabase
    mock_supabase_client.table().select().order().limit().eq().execute.return_value.data = [
        raw_feedback_dict
    ]

    results = storage.get_raw_feedbacks(limit=100, feedback_name="test_raw_feedback")

    assert len(results) == 1
    assert results[0].feedback_name == "test_raw_feedback"


def test_get_feedbacks(supabase_storage, feedback_data, mock_supabase_client):
    """Test retrieving feedbacks with get_feedbacks."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase - no .eq() because feedback_status_filter is None
    mock_supabase_client.table().select().order().limit().is_().execute.return_value.data = [
        feedback_dict
    ]

    results = storage.get_feedbacks(limit=100)

    assert len(results) == 1
    assert results[0].feedback_content == "The agent response was clear and concise"
    assert results[0].feedback_name == "test_feedback"
    assert results[0].feedback_status == "approved"


def test_get_feedbacks_with_feedback_name(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving feedbacks filtered by feedback_name."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase - .eq() for feedback_name, .is_() for status, no final .eq() because feedback_status_filter is None
    mock_supabase_client.table().select().order().limit().eq().is_().execute.return_value.data = [
        feedback_dict
    ]

    results = storage.get_feedbacks(limit=100, feedback_name="test_feedback")

    assert len(results) == 1
    assert results[0].feedback_name == "test_feedback"


def test_get_feedbacks_with_feedback_status_filter(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving feedbacks filtered by feedback_status_filter."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase - using .in_() for list-based filter
    mock_supabase_client.table().select().order().limit().is_().in_().execute.return_value.data = [
        feedback_dict
    ]

    # Test with approved filter
    results = storage.get_feedbacks(
        limit=100, feedback_status_filter=[FeedbackStatus.APPROVED]
    )

    assert len(results) == 1
    assert results[0].feedback_status == "approved"


def test_get_feedbacks_with_pending_status_filter(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving feedbacks filtered by pending feedback_status_filter."""
    storage = supabase_storage
    pending_feedback_dict = {
        **feedback_data["feedback_dict"],
        "feedback_status": "pending",
    }

    # Mock the response from Supabase - using .in_() for list-based filter
    mock_supabase_client.table().select().order().limit().is_().in_().execute.return_value.data = [
        pending_feedback_dict
    ]

    results = storage.get_feedbacks(
        limit=100, feedback_status_filter=[FeedbackStatus.PENDING]
    )

    assert len(results) == 1
    assert results[0].feedback_status == "pending"


def test_get_feedbacks_with_rejected_status_filter(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving feedbacks filtered by rejected feedback_status_filter."""
    storage = supabase_storage
    rejected_feedback_dict = {
        **feedback_data["feedback_dict"],
        "feedback_status": "rejected",
    }

    # Mock the response from Supabase - using .in_() for list-based filter
    mock_supabase_client.table().select().order().limit().is_().in_().execute.return_value.data = [
        rejected_feedback_dict
    ]

    results = storage.get_feedbacks(
        limit=100, feedback_status_filter=[FeedbackStatus.REJECTED]
    )

    assert len(results) == 1
    assert results[0].feedback_status == "rejected"


def test_get_feedbacks_with_status_filter(
    supabase_storage, feedback_data, mock_supabase_client
):
    """Test retrieving feedbacks filtered by status_filter (Status enum)."""
    storage = supabase_storage
    feedback_dict = feedback_data["feedback_dict"]

    # Mock the response from Supabase - with status_filter, we use or_() instead of is_(), no .eq() because feedback_status_filter is None
    mock_supabase_client.table().select().order().limit().or_().execute.return_value.data = [
        feedback_dict
    ]

    # Test with status_filter including None (current) and archived
    results = storage.get_feedbacks(limit=100, status_filter=[None, Status.ARCHIVED])

    assert len(results) == 1


def test_get_feedbacks_default_returns_approved_only(
    supabase_storage, mock_supabase_client
):
    """Test that get_feedbacks defaults to returning all feedback statuses (no filter)."""
    storage = supabase_storage
    current_time = int(datetime.now(timezone.utc).timestamp())

    approved_feedback = {
        "feedback_id": 1,
        "feedback_name": "test_feedback",
        "feedback_content": "Approved feedback",
        "feedback_status": "approved",
        "agent_version": "v1",
        "feedback_metadata": "",
        "created_at": datetime.fromtimestamp(current_time).isoformat(),
        "embedding": str([0.1] * 512),
    }

    # Mock the response - no .eq() because feedback_status_filter is None (returns all statuses)
    mock_supabase_client.table().select().order().limit().is_().execute.return_value.data = [
        approved_feedback
    ]

    # Call without specifying feedback_status_filter - returns all feedback statuses
    results = storage.get_feedbacks(limit=100)

    assert len(results) == 1
    assert results[0].feedback_status == "approved"


class TestParseDatetimeToTimestamp:
    """Tests for _parse_datetime_to_timestamp method."""

    def test_parse_datetime_with_5_digit_fractional_seconds(self, supabase_storage):
        """Test parsing datetime with 5-digit fractional seconds (PostgreSQL variable precision)."""
        storage = supabase_storage
        # This is the format that was causing the warning
        datetime_str = "2026-01-03T01:40:53.47232"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        # Should parse successfully and return a valid timestamp
        assert isinstance(result, int)
        assert result > 0
        # Verify the parsed timestamp is approximately correct (within 1 second)
        expected = datetime(2026, 1, 3, 1, 40, 53, 472320).timestamp()
        assert abs(result - expected) < 1

    def test_parse_datetime_with_6_digit_fractional_seconds(self, supabase_storage):
        """Test parsing datetime with standard 6-digit fractional seconds."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53.472320"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_with_3_digit_fractional_seconds(self, supabase_storage):
        """Test parsing datetime with 3-digit fractional seconds (milliseconds)."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53.472"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_with_z_suffix(self, supabase_storage):
        """Test parsing datetime with Z (UTC) suffix."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53.472320Z"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_with_timezone_offset(self, supabase_storage):
        """Test parsing datetime with timezone offset."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53.472320+00:00"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_without_fractional_seconds(self, supabase_storage):
        """Test parsing datetime without fractional seconds."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_space_separated(self, supabase_storage):
        """Test parsing datetime with space separator instead of T."""
        storage = supabase_storage
        datetime_str = "2026-01-03 01:40:53.472320"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0

    def test_parse_datetime_empty_string(self, supabase_storage):
        """Test parsing empty datetime string returns current timestamp."""
        storage = supabase_storage
        result = storage._parse_datetime_to_timestamp("")
        assert isinstance(result, int)
        # Should return current timestamp
        current_time = int(datetime.now(timezone.utc).timestamp())
        assert abs(result - current_time) < 2  # Within 2 seconds

    def test_parse_datetime_none_value(self, supabase_storage):
        """Test parsing None datetime returns current timestamp."""
        storage = supabase_storage
        result = storage._parse_datetime_to_timestamp(None)
        assert isinstance(result, int)
        current_time = int(datetime.now(timezone.utc).timestamp())
        assert abs(result - current_time) < 2

    def test_parse_datetime_with_7_digit_fractional_seconds(self, supabase_storage):
        """Test parsing datetime with 7-digit fractional seconds (truncated to 6)."""
        storage = supabase_storage
        datetime_str = "2026-01-03T01:40:53.4723201"
        result = storage._parse_datetime_to_timestamp(datetime_str)
        assert isinstance(result, int)
        assert result > 0


def test_get_requests_grouped_by_session_id(supabase_storage, mock_supabase_client):
    """Test get_requests returns results grouped by session_id."""
    storage = supabase_storage
    current_time = int(datetime.now(timezone.utc).timestamp())

    # Mock response for getting requests with interactions
    mock_supabase_client.table().select().order().eq().limit().execute.return_value.data = [
        {
            "request_id": "req1",
            "user_id": "user1",
            "created_at": datetime.fromtimestamp(current_time).isoformat(),
            "source": "test",
            "agent_version": "v1",
            "session_id": "group1",
            "interactions": [
                {
                    "interaction_id": 1,
                    "user_id": "user1",
                    "request_id": "req1",
                    "content": "test content",
                    "created_at": datetime.fromtimestamp(current_time).isoformat(),
                    "user_action": "none",
                    "user_action_description": "",
                    "interacted_image_url": "",
                }
            ],
        },
        {
            "request_id": "req2",
            "user_id": "user1",
            "created_at": datetime.fromtimestamp(current_time).isoformat(),
            "source": "test",
            "agent_version": "v1",
            "session_id": "group2",
            "interactions": [],
        },
    ]

    results = storage.get_sessions(user_id="user1", top_k=10)

    # Results should be a dictionary grouped by session_id
    assert isinstance(results, dict)
    assert "group1" in results
    assert "group2" in results
    assert len(results["group1"]) == 1
    assert len(results["group2"]) == 1

    # Verify structure
    rig1 = results["group1"][0]
    assert rig1.request.request_id == "req1"
    assert len(rig1.interactions) == 1
    assert rig1.interactions[0].interaction_id == 1

    rig2 = results["group2"][0]
    assert rig2.request.request_id == "req2"
    assert len(rig2.interactions) == 0


def test_get_rerun_user_ids_applies_filters(supabase_storage, mock_supabase_client):
    """Test get_rerun_user_ids applies DB-side filters and deduplicates users."""
    storage = supabase_storage

    query = Mock()
    query.select.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.eq.return_value = query
    query.gte.return_value = query
    query.lte.return_value = query

    now = int(datetime.now(timezone.utc).timestamp())
    start_time = now - 3600
    end_time = now

    response = Mock()
    response.data = [{"user_id": "user1"}, {"user_id": "user1"}]
    query.execute.return_value = response
    mock_supabase_client.table.return_value = query

    result = storage.get_rerun_user_ids(
        user_id="user1",
        start_time=start_time,
        end_time=end_time,
        source="api",
        agent_version="v1",
    )

    assert result == ["user1"]
    assert call("user_id", "user1") in query.eq.call_args_list
    assert call("source", "api") in query.eq.call_args_list
    assert call("agent_version", "v1") in query.eq.call_args_list
    assert (
        call(
            "created_at",
            datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
        )
        in query.gte.call_args_list
    )
    assert (
        call(
            "created_at", datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()
        )
        in query.lte.call_args_list
    )


def test_get_rerun_user_ids_paginates(supabase_storage, mock_supabase_client):
    """Test get_rerun_user_ids paginates through requests beyond one page."""
    storage = supabase_storage

    query = Mock()
    query.select.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.eq.return_value = query
    query.gte.return_value = query
    query.lte.return_value = query

    response_page_1 = Mock()
    response_page_1.data = [{"user_id": "user1"} for _ in range(1000)]
    response_page_2 = Mock()
    response_page_2.data = [{"user_id": "user2"}]
    query.execute.side_effect = [response_page_1, response_page_2]
    mock_supabase_client.table.return_value = query

    result = storage.get_rerun_user_ids()

    assert result == ["user1", "user2"]
    assert query.offset.call_args_list == [call(0), call(1000)]
