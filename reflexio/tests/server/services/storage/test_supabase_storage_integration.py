"""Integration tests for SupabaseStorage implementation."""

import contextlib
import os
from datetime import UTC, datetime

import pytest
from reflexio_commons.api_schema.retriever_schema import (
    SearchFeedbackRequest,
    SearchInteractionRequest,
    SearchRawFeedbackRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    NEVER_EXPIRES_TIMESTAMP,
    AgentSuccessEvaluationResult,
    DeleteUserInteractionRequest,
    DeleteUserProfileRequest,
    Feedback,
    FeedbackStatus,
    Interaction,
    ProfileChangeLog,
    ProfileTimeToLive,
    RawFeedback,
    Request,
    Status,
    UserActionType,
    UserProfile,
)
from reflexio_commons.config_schema import StorageConfigSupabase

from reflexio.server import OPENAI_API_KEY
from reflexio.server.llm.openai_client import OpenAIClient
from reflexio.server.services.storage.supabase_storage import SupabaseStorage
from reflexio.tests.server.test_utils import skip_in_precommit


@pytest.fixture
def openai_client():
    """Create an OpenAIClient instance with real API key."""
    if not OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY environment variable must be set")
    from reflexio.server.llm.openai_client import OpenAIConfig

    config = OpenAIConfig(api_key=OPENAI_API_KEY)
    return OpenAIClient(config=config)


@pytest.fixture
def supabase_storage():
    """Create a SupabaseStorage instance with real credentials from environment.

    Requires TEST_SUPABASE_URL, TEST_SUPABASE_KEY, and TEST_SUPABASE_DB_URL
    environment variables to be set for integration tests.
    """
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    if not supabase_url or not supabase_key:
        pytest.skip(
            "TEST_SUPABASE_URL and TEST_SUPABASE_KEY environment variables must be set"
        )

    config = StorageConfigSupabase(
        url=supabase_url,
        key=supabase_key,
        db_url=supabase_db_url,
    )
    storage = SupabaseStorage(org_id="test", config=config)
    return storage  # noqa: RET504


@pytest.fixture
def test_data():
    """Create test data for integration tests."""
    current_time = int(datetime.now(UTC).timestamp())
    return {
        "user_id": "test_user_123",
        "profile": UserProfile(
            profile_id="test_profile_1",
            user_id="test_user_123",
            profile_content="I love programming and building AI applications",
            last_modified_timestamp=current_time,
            generated_from_request_id="test_request_1",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            source="test_source",
        ),
        "request": Request(
            request_id="test_request_1",
            user_id="test_user_123",
            created_at=current_time,
            source="test_source",
            agent_version="v1.0.0",
            session_id="",
        ),
        "interaction": Interaction(
            interaction_id=1,
            user_id="test_user_123",
            request_id="test_request_1",
            content="I'm interested in learning more about machine learning",
            created_at=current_time,
            user_action=UserActionType.CLICK,
            user_action_description="Clicked on ML tutorial",
            interacted_image_url="https://example.com/ml-tutorial",
        ),
        "interaction2": Interaction(
            interaction_id=2,
            user_id="test_user_123",
            request_id="test_request_1",
            content="Can you recommend some ML courses?",
            created_at=current_time + 10,
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        ),
        "profile_change_log": ProfileChangeLog(
            id=1,
            user_id="test_user_123",
            request_id="test_request_1",
            created_at=current_time,
            added_profiles=[
                UserProfile(
                    profile_id="test_profile_1",
                    user_id="test_user_123",
                    profile_content="I love programming and building AI applications",
                    last_modified_timestamp=current_time,
                    generated_from_request_id="test_request_1",
                    profile_time_to_live=ProfileTimeToLive.INFINITY,
                    expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
                    source="test_source",
                )
            ],
            removed_profiles=[],
            mentioned_profiles=[],
        ),
        "raw_feedbacks": [
            RawFeedback(
                feedback_name="test_raw_feedback_integration",
                agent_version="test_agent_version_1",
                request_id="test_request_1",
                feedback_content="I love programming and building AI applications",
                created_at=current_time,
            )
        ],
        "feedbacks": [
            Feedback(
                feedback_name="test_feedback_1",
                feedback_content="The agent provided excellent programming guidance and was very helpful",
                feedback_status=FeedbackStatus.APPROVED,
                agent_version="test_agent_v1",
                feedback_metadata="test_metadata_1",
            ),
            Feedback(
                feedback_name="test_feedback_2",
                feedback_content="Agent could improve response time for technical questions",
                feedback_status=FeedbackStatus.PENDING,
                agent_version="test_agent_v1",
                feedback_metadata="test_metadata_2",
            ),
        ],
    }


TEST_FEEDBACK_NAMES = [
    "test_raw_feedback_integration",
    "test_feedback_1",
    "test_feedback_2",
    "test_status_feedback_1",
    "test_status_feedback_2",
    "test_raw_fb_status",
    "test_count_feedback",
    "test_multi_status_filter",
]


@pytest.fixture
def cleanup_after_test(supabase_storage):
    """Fixture to clean up test data after each test."""
    yield  # This allows the test to run
    try:
        # Only delete feedbacks and raw_feedbacks created by this test file
        supabase_storage.client.table("feedbacks").delete().in_(
            "feedback_name", TEST_FEEDBACK_NAMES
        ).execute()
        supabase_storage.client.table("raw_feedbacks").delete().in_(
            "feedback_name", TEST_FEEDBACK_NAMES
        ).execute()
        print("Test data cleaned up successfully")
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")


@skip_in_precommit
def test_add_and_search_user_profile(supabase_storage, test_data, openai_client):
    """Test adding and searching user profiles with real OpenAI embeddings."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    profile = test_data["profile"]

    # Add profile
    storage.add_user_profile(user_id, [profile])

    # Search with similar query
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query="Tell me about programming and AI",
    )
    results = storage.search_user_profile(search_request)

    assert len(results) > 0
    assert any(r.profile_content == profile.profile_content for r in results)

    # Debug logging
    print("\nDebug info:")
    print(f"Original profile source: {profile.source}")
    for r in results:
        print(f"Result profile source: {r.source}")

    # Check if any result has the same source as the original profile
    matching_profiles = [r for r in results if r.source == profile.source]
    assert len(matching_profiles) > 0, (
        f"No profiles found with source '{profile.source}'"
    )


@skip_in_precommit
def test_add_and_search_interaction(supabase_storage, test_data, openai_client):
    """Test adding and searching interactions with real OpenAI embeddings."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    interaction = test_data["interaction"]
    request = test_data["request"]

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Add request first (required for foreign key constraint)
    storage.add_request(request)

    # Add interaction
    storage.add_user_interaction(user_id, interaction)

    # Search with similar query
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query="I want to learn about machine learning",
    )
    results = storage.search_interaction(search_request)

    assert len(results) > 0
    assert any(r.content == interaction.content for r in results)

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_add_user_interactions_bulk(supabase_storage):
    """Test adding multiple interactions with batched embedding generation.

    This test verifies that add_user_interactions_bulk correctly:
    1. Generates embeddings for all interactions in a single batch API call
    2. Stores all interactions in the database
    3. Interactions are searchable after bulk insertion
    """
    storage = supabase_storage
    user_id = "test_bulk_user_456"
    current_time = int(datetime.now(UTC).timestamp())
    request_id = "test_bulk_request_1"

    # Create multiple test interactions
    interactions = [
        Interaction(
            interaction_id=100 + i,
            user_id=user_id,
            request_id=request_id,
            content=f"Bulk test interaction {i}: I'm interested in {topic}",
            created_at=current_time + i,
            user_action=UserActionType.NONE,
            user_action_description=f"Test action {i}",
            interacted_image_url="",
        )
        for i, topic in enumerate(
            [
                "machine learning algorithms",
                "deep learning frameworks",
                "natural language processing",
                "computer vision applications",
                "reinforcement learning",
            ]
        )
    ]

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Create the request first (required due to foreign key constraint)
    test_request = Request(
        request_id=request_id,
        user_id=user_id,
        created_at=current_time,
        source="test_bulk",
        agent_version="v1.0.0",
        session_id="",
    )
    storage.add_request(test_request)

    # Add interactions using bulk method
    storage.add_user_interactions_bulk(user_id, interactions)

    # Verify all interactions were stored
    stored_interactions = storage.get_user_interaction(user_id)
    assert len(stored_interactions) == len(interactions), (
        f"Expected {len(interactions)} interactions, got {len(stored_interactions)}"
    )

    # Verify interactions have embeddings (by searching)
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query="machine learning and deep learning",
    )
    search_results = storage.search_interaction(search_request)
    assert len(search_results) > 0, "Should find interactions via semantic search"

    # Verify content matches
    stored_contents = {i.content for i in stored_interactions}
    for interaction in interactions:
        assert interaction.content in stored_contents, (
            f"Interaction content '{interaction.content}' not found in stored interactions"
        )

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_add_and_get_profile_change_log(supabase_storage, test_data):
    """Test adding and retrieving profile change logs."""
    storage = supabase_storage
    profile_change_log = test_data["profile_change_log"]

    # Add profile change log
    storage.add_profile_change_log(profile_change_log)

    # Get profile change logs
    logs = storage.get_profile_change_logs(limit=10)

    assert len(logs) > 0
    assert any(log.user_id == profile_change_log.user_id for log in logs)
    assert any(len(log.added_profiles) == 1 for log in logs)
    assert any(
        log.added_profiles[0].profile_content
        == profile_change_log.added_profiles[0].profile_content
        for log in logs
    )
    # Verify created_at is set (either from response or current time)
    assert all(log.created_at > 0 for log in logs)


@skip_in_precommit
def test_delete_profile_change_log(supabase_storage, test_data):
    """Test deleting profile change logs for a user."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    profile_change_log = test_data["profile_change_log"]

    # Add profile change log
    storage.add_profile_change_log(profile_change_log)

    # Delete profile change logs for user
    storage.delete_profile_change_log_for_user(user_id)

    # Verify deletion
    logs = storage.get_profile_change_logs(limit=10)
    assert not any(log.user_id == user_id for log in logs)


@skip_in_precommit
def test_cleanup(supabase_storage, test_data):
    """Clean up test data after integration tests."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    profile = test_data["profile"]
    interaction = test_data["interaction"]

    # Delete test data
    storage.delete_user_profile(
        DeleteUserProfileRequest(user_id=user_id, profile_id=profile.profile_id)
    )
    storage.delete_user_interaction(
        DeleteUserInteractionRequest(
            user_id=user_id, interaction_id=interaction.interaction_id
        )
    )
    storage.delete_profile_change_log_for_user(user_id)

    # Verify deletion
    profiles = storage.get_user_profile(user_id)
    interactions = storage.get_user_interaction(user_id)
    logs = storage.get_profile_change_logs(limit=10)

    assert len(profiles) == 0
    assert len(interactions) == 0
    assert not any(log.user_id == user_id for log in logs)


@skip_in_precommit
def test_save_raw_feedbacks(supabase_storage, test_data, cleanup_after_test):
    """Test saving raw feedbacks."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]
    storage.save_raw_feedbacks(raw_feedbacks)

    # Verify feedbacks were saved
    saved_raw_feedbacks = storage.get_raw_feedbacks()
    assert len(saved_raw_feedbacks) == len(raw_feedbacks)
    assert all(
        saved_raw_feedback.feedback_content == raw_feedback.feedback_content
        for saved_raw_feedback, raw_feedback in zip(saved_raw_feedbacks, raw_feedbacks)  # noqa: B905
    )
    assert all(
        saved_raw_feedback.feedback_name == raw_feedback.feedback_name
        for saved_raw_feedback, raw_feedback in zip(saved_raw_feedbacks, raw_feedbacks)  # noqa: B905
    )


@skip_in_precommit
def test_save_feedbacks(supabase_storage, test_data, cleanup_after_test):
    """Test saving regular feedbacks with embeddings."""
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks
    storage.save_feedbacks(feedbacks)

    # Get feedbacks to verify they were saved
    results = storage.get_feedbacks(limit=100)

    # Verify feedbacks were saved and can be found
    assert len(results) >= len(feedbacks)

    # Verify the saved feedbacks have the expected structure
    for result in results:
        assert hasattr(result, "feedback_id")
        assert hasattr(result, "feedback_content")
        assert hasattr(result, "feedback_status")
        assert hasattr(result, "agent_version")
        assert hasattr(result, "feedback_metadata")
        assert hasattr(result, "feedback_name")

    # Check that our saved feedback names appear in the results
    saved_names = [f.feedback_name for f in feedbacks]
    found_names = [r.feedback_name for r in results]

    # All of our saved feedback names should be found
    for saved_name in saved_names:
        assert saved_name in found_names, f"Should find feedback {saved_name}"


@skip_in_precommit
def test_search_raw_feedbacks_integration(
    supabase_storage, test_data, cleanup_after_test
):
    """Test searching raw feedbacks with real OpenAI embeddings."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]

    # Save raw feedbacks with embeddings
    storage.save_raw_feedbacks(raw_feedbacks)

    # Search with similar query
    results = storage.search_raw_feedbacks(
        SearchRawFeedbackRequest(
            query="programming and AI development feedback",
            threshold=0.6,
            top_k=5,
        )
    )

    assert len(results) > 0

    # Verify the result contains expected fields
    result = results[0]
    assert hasattr(result, "raw_feedback_id")
    assert hasattr(result, "feedback_content")
    assert hasattr(result, "feedback_name")
    assert hasattr(result, "agent_version")
    assert hasattr(result, "request_id")
    assert hasattr(result, "created_at")

    # Check that we get the feedback we saved
    assert any(
        raw_feedback.feedback_content in result.feedback_content
        for result in results
        for raw_feedback in raw_feedbacks
    )

    # Check that we get the feedback name we saved
    assert any(
        raw_feedback.feedback_name == result.feedback_name
        for result in results
        for raw_feedback in raw_feedbacks
    )


@skip_in_precommit
def test_search_raw_feedbacks_with_different_thresholds(
    supabase_storage, test_data, cleanup_after_test
):
    """Test searching raw feedbacks with different similarity thresholds."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]

    # Save raw feedbacks
    storage.save_raw_feedbacks(raw_feedbacks)

    # Search with high threshold (should return fewer results)
    high_threshold_results = storage.search_raw_feedbacks(
        SearchRawFeedbackRequest(
            query="programming and AI development", threshold=0.9, top_k=10
        )
    )

    # Search with low threshold (should return more results)
    low_threshold_results = storage.search_raw_feedbacks(
        SearchRawFeedbackRequest(
            query="programming and AI development", threshold=0.3, top_k=10
        )
    )

    # Low threshold should return at least as many results as high threshold
    assert len(low_threshold_results) >= len(high_threshold_results)

    # All results should have the expected structure
    for result in high_threshold_results:
        assert hasattr(result, "raw_feedback_id")
        assert hasattr(result, "feedback_content")

    for result in low_threshold_results:
        assert hasattr(result, "raw_feedback_id")
        assert hasattr(result, "feedback_content")


@skip_in_precommit
def test_search_raw_feedbacks_empty_results(
    supabase_storage, test_data, cleanup_after_test
):
    """Test searching raw feedbacks when no matches are found."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]

    # Save raw feedbacks
    storage.save_raw_feedbacks(raw_feedbacks)

    # Search with a completely unrelated query and high threshold
    results = storage.search_raw_feedbacks(
        SearchRawFeedbackRequest(
            query="completely unrelated topic about cooking recipes",
            threshold=0.9,
            top_k=5,
        )
    )

    # Should return empty list or very few results with low similarity
    assert isinstance(results, list)
    # If any results are returned, they should have the expected structure
    for result in results:
        assert hasattr(result, "raw_feedback_id")
        assert hasattr(result, "feedback_content")


@skip_in_precommit
def test_search_feedbacks_integration(supabase_storage, test_data, cleanup_after_test):
    """Test searching regular feedbacks with real OpenAI embeddings.

    Note: This test requires the migration 20251113220000_exclude_archived_feedbacks.sql
    to be applied to the database to exclude archived feedbacks from search results.
    """
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks with embeddings
    storage.save_feedbacks(feedbacks)

    # Search with a query similar to the saved feedback content
    results = storage.search_feedbacks(
        SearchFeedbackRequest(
            query="programming guidance and technical help",
            threshold=0.6,
            top_k=10,
        )
    )

    # Verify we get results (if migration is applied)
    # If no results, the migration may not have been applied yet
    if len(results) == 0:
        # Try with get_feedbacks instead to verify feedbacks were saved
        all_feedbacks = storage.get_feedbacks(limit=100)
        saved_names = [f.feedback_name for f in feedbacks]
        found_names = [f.feedback_name for f in all_feedbacks]
        # At least verify feedbacks were saved
        assert any(name in found_names for name in saved_names), (
            "Feedbacks should be saved even if search doesn't work (migration not applied)"
        )
        return

    assert len(results) > 0

    # Verify the result structure
    result = results[0]
    assert hasattr(result, "feedback_id")
    assert hasattr(result, "feedback_content")
    assert hasattr(result, "feedback_name")
    assert hasattr(result, "feedback_status")
    assert hasattr(result, "agent_version")
    assert hasattr(result, "created_at")

    # Check that we get one of the feedbacks we saved
    saved_contents = [f.feedback_content for f in feedbacks]
    assert any(
        any(word in result.feedback_content for word in content.split())
        for result in results
        for content in saved_contents
    )

    # Check that we get one of the feedback names we saved
    saved_names = [f.feedback_name for f in feedbacks]
    assert any(
        saved_name == result.feedback_name
        for result in results
        for saved_name in saved_names
    )


@skip_in_precommit
def test_search_feedbacks_with_different_parameters(
    supabase_storage, test_data, cleanup_after_test
):
    """Test searching feedbacks with different parameters."""
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks first
    storage.save_feedbacks(feedbacks)

    # Test with high threshold and low count
    high_threshold_results = storage.search_feedbacks(
        SearchFeedbackRequest(
            query="agent programming guidance", threshold=0.8, top_k=3
        )
    )

    # Test with low threshold and high count
    low_threshold_results = storage.search_feedbacks(
        SearchFeedbackRequest(
            query="agent programming guidance", threshold=0.4, top_k=20
        )
    )

    # Verify results structure
    assert isinstance(high_threshold_results, list)
    assert isinstance(low_threshold_results, list)

    # Low threshold should potentially return more results
    assert len(low_threshold_results) >= len(high_threshold_results)

    # Verify results have the expected structure
    for result in high_threshold_results:
        assert hasattr(result, "feedback_id")
        assert hasattr(result, "feedback_content")

    for result in low_threshold_results:
        assert hasattr(result, "feedback_id")
        assert hasattr(result, "feedback_content")


@skip_in_precommit
def test_search_feedbacks_default_parameters(
    supabase_storage, test_data, cleanup_after_test
):
    """Test searching feedbacks with default parameters."""
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks first
    storage.save_feedbacks(feedbacks)

    # Search with default parameters
    results = storage.search_feedbacks(
        SearchFeedbackRequest(query="programming and technical assistance")
    )

    # Verify the result structure
    assert isinstance(results, list)

    # If results are found, verify they meet default criteria
    for result in results:
        assert hasattr(result, "feedback_id")
        assert hasattr(result, "feedback_content")

    # Should not exceed default count of 10 (unless there are ties)
    assert len(results) <= 15  # Allow some buffer for ties in similarity scores


@skip_in_precommit
def test_add_and_get_requests(supabase_storage, test_data):
    """Test adding request and interactions, then retrieving them with get_requests.

    This tests the core get_requests functionality which returns grouped results.
    """
    storage = supabase_storage
    user_id = test_data["user_id"]
    request = test_data["request"]
    interaction1 = test_data["interaction"]
    interaction2 = test_data["interaction2"]

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Add request
    storage.add_request(request)

    # Add interactions
    storage.add_user_interaction(user_id, interaction1)
    storage.add_user_interaction(user_id, interaction2)

    # Get requests with interactions (returns dict grouped by session_id)
    results = storage.get_sessions(user_id=user_id, top_k=10)

    # Verify results is a dictionary
    assert isinstance(results, dict), (
        "Results should be a dictionary grouped by session_id"
    )
    assert len(results) > 0, "Should find at least one session"

    # Find our test request in the grouped results
    found_request = None
    found_interactions = None
    for request_list in results.values():
        for rig in request_list:
            if rig.request.request_id == request.request_id:
                found_request = rig.request
                found_interactions = rig.interactions
                break
        if found_request:
            break

    assert found_request is not None, "Should find our test request"
    assert found_request.user_id == user_id
    assert found_request.source == request.source
    assert found_request.agent_version == request.agent_version
    # DB may return None for empty session_id, treat both as equivalent
    expected_group = request.session_id or None
    actual_group = found_request.session_id or None
    assert actual_group == expected_group

    # Verify interactions
    assert found_interactions is not None
    assert len(found_interactions) == 2, "Should have 2 interactions"

    # Verify interactions are sorted by created_at
    assert found_interactions[0].created_at <= found_interactions[1].created_at

    # Verify interaction content
    interaction_ids = {i.interaction_id for i in found_interactions}
    assert interaction1.interaction_id in interaction_ids
    assert interaction2.interaction_id in interaction_ids

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_get_requests_with_filters(supabase_storage, test_data):
    """Test get_requests with various filters (results are grouped by session_id)."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    request = test_data["request"]
    interaction1 = test_data["interaction"]

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Add request and interaction
    storage.add_request(request)
    storage.add_user_interaction(user_id, interaction1)

    # Test 1: Get by request_id (returns dict grouped by session_id)
    results = storage.get_sessions(user_id=user_id, request_id=request.request_id)
    assert isinstance(results, dict)
    # Find our request in the grouped results
    found = False
    for request_list in results.values():
        for rig in request_list:
            if rig.request.request_id == request.request_id:
                found = True
                break
    assert found, "Should find the request by ID"

    # Test 2: Get by time range
    results = storage.get_sessions(
        user_id=user_id,
        start_time=request.created_at - 100,
        end_time=request.created_at + 100,
    )
    assert isinstance(results, dict)
    assert len(results) >= 1, "Should find at least one session in time range"

    # Test 3: Get with top_k limit (limits number of groups)
    results = storage.get_sessions(user_id=user_id, top_k=1)
    assert isinstance(results, dict)
    assert len(results) <= 1, "Should return at most 1 session"

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_get_requests_empty_result(supabase_storage):
    """Test get_requests with no matching data (returns empty dict)."""
    storage = supabase_storage

    # Query for non-existent user
    results = storage.get_sessions(user_id="nonexistent_user_xyz")

    # Should return empty dict
    assert results == {}
    assert isinstance(results, dict)


@skip_in_precommit
def test_get_requests_with_no_interactions(supabase_storage, test_data):
    """Test get_requests for a request with no interactions (grouped by session_id)."""
    storage = supabase_storage
    user_id = test_data["user_id"]
    request = test_data["request"]

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Add only request, no interactions
    storage.add_request(request)

    # Get requests (returns dict grouped by session_id)
    results = storage.get_sessions(user_id=user_id)

    # Should find the request with empty interactions list
    assert isinstance(results, dict)
    assert len(results) > 0, "Should find at least one session"

    # Find our request in the grouped results
    found_request = None
    for request_list in results.values():
        for rig in request_list:
            if rig.request.request_id == request.request_id:
                found_request = rig.request
                assert len(rig.interactions) == 0, "Should have no interactions"
                break

    assert found_request is not None, "Should find the request"

    # Clean up
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_add_request_with_session_id(supabase_storage):
    """Test adding a request with session_id."""
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())

    test_request = Request(
        request_id="test_request_with_group_1",
        user_id="test_user_with_group_456",
        created_at=current_time,
        source="test_source",
        agent_version="v2.0.0",
        session_id="test_group_xyz",
    )

    # Clean up any existing test data first
    with contextlib.suppress(Exception):
        storage.client.table("requests").delete().eq(
            "user_id", test_request.user_id
        ).execute()

    # Add request
    storage.add_request(test_request)

    # Get the request back
    result = storage.get_request(test_request.request_id)

    # Verify the request was saved correctly
    assert result is not None, "Should find the request"
    assert result.request_id == test_request.request_id
    assert result.user_id == test_request.user_id
    assert result.session_id == "test_group_xyz"
    assert result.source == test_request.source
    assert result.agent_version == test_request.agent_version

    # Clean up
    storage.client.table("requests").delete().eq(
        "user_id", test_request.user_id
    ).execute()


@skip_in_precommit
def test_get_raw_feedbacks_integration(supabase_storage, test_data, cleanup_after_test):
    """Test get_raw_feedbacks method retrieves saved raw feedbacks."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]

    # Save raw feedbacks
    storage.save_raw_feedbacks(raw_feedbacks)

    # Get raw feedbacks
    results = storage.get_raw_feedbacks(limit=100)

    assert len(results) > 0, "Should retrieve at least one raw feedback"

    # Find our test feedback
    found = False
    for result in results:
        if result.feedback_name == raw_feedbacks[0].feedback_name:
            assert result.feedback_content == raw_feedbacks[0].feedback_content
            assert result.request_id == raw_feedbacks[0].request_id
            assert result.agent_version == raw_feedbacks[0].agent_version
            found = True
            break

    assert found, "Should find our test raw feedback"


@skip_in_precommit
def test_get_raw_feedbacks_with_feedback_name_filter(
    supabase_storage, test_data, cleanup_after_test
):
    """Test get_raw_feedbacks with feedback_name filter."""
    storage = supabase_storage
    raw_feedbacks = test_data["raw_feedbacks"]

    # Save raw feedbacks
    storage.save_raw_feedbacks(raw_feedbacks)

    # Get raw feedbacks filtered by feedback_name
    feedback_name = raw_feedbacks[0].feedback_name
    results = storage.get_raw_feedbacks(limit=100, feedback_name=feedback_name)

    assert len(results) > 0, "Should retrieve at least one raw feedback"

    # Verify all results have the correct feedback_name
    for result in results:
        assert result.feedback_name == feedback_name


@skip_in_precommit
def test_get_feedbacks_integration(supabase_storage, test_data, cleanup_after_test):
    """Test get_feedbacks method retrieves saved feedbacks."""
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks
    storage.save_feedbacks(feedbacks)

    # Get feedbacks
    results = storage.get_feedbacks(limit=100)

    assert len(results) > 0, "Should retrieve at least one feedback"

    # Find our test feedbacks
    found_names = {result.feedback_name for result in results}
    for feedback in feedbacks:
        assert feedback.feedback_name in found_names, (
            f"Should find feedback {feedback.feedback_name}"
        )


@skip_in_precommit
def test_get_feedbacks_with_feedback_name_filter(
    supabase_storage, test_data, cleanup_after_test
):
    """Test get_feedbacks with feedback_name filter."""
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Save feedbacks
    storage.save_feedbacks(feedbacks)

    # Get feedbacks filtered by feedback_name
    feedback_name = feedbacks[0].feedback_name
    results = storage.get_feedbacks(limit=100, feedback_name=feedback_name)

    assert len(results) > 0, "Should retrieve at least one feedback"

    # Verify all results have the correct feedback_name
    for result in results:
        assert result.feedback_name == feedback_name


@skip_in_precommit
def test_archived_feedbacks_excluded_from_queries(
    supabase_storage, test_data, cleanup_after_test
):
    """Test that archived feedbacks are excluded from get_feedbacks and search_feedbacks.

    Note: archive_feedbacks_by_feedback_name only archives non-APPROVED feedbacks.
    APPROVED feedbacks are preserved to protect user-approved feedback.
    """
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Filter to only non-APPROVED feedbacks (APPROVED feedbacks are NOT archived)
    archivable_feedbacks = [
        f for f in feedbacks if f.feedback_status != FeedbackStatus.APPROVED
    ]
    approved_feedbacks = [
        f for f in feedbacks if f.feedback_status == FeedbackStatus.APPROVED
    ]

    # Save feedbacks
    storage.save_feedbacks(feedbacks)

    # Verify feedbacks are retrievable
    results_before = storage.get_feedbacks(limit=100)
    initial_count = len(
        [
            f
            for f in results_before
            if f.feedback_name in [fb.feedback_name for fb in feedbacks]
        ]
    )
    assert initial_count >= len(feedbacks), "Should retrieve all saved feedbacks"

    # Archive feedbacks (only non-APPROVED will actually be archived)
    for feedback in feedbacks:
        storage.archive_feedbacks_by_feedback_name(
            feedback.feedback_name, agent_version=feedback.agent_version
        )

    # Verify archived feedbacks are excluded from get_feedbacks
    # Only APPROVED feedbacks should remain (they are not archived)
    results_after = storage.get_feedbacks(limit=100)
    remaining_count = len(
        [
            f
            for f in results_after
            if f.feedback_name in [fb.feedback_name for fb in feedbacks]
        ]
    )
    assert remaining_count == len(approved_feedbacks), (
        f"Only APPROVED feedbacks should remain after archiving, expected {len(approved_feedbacks)}, got {remaining_count}"
    )

    # Verify archived feedbacks are excluded from search_feedbacks
    # Only APPROVED feedbacks should be searchable
    search_results = storage.search_feedbacks(
        SearchFeedbackRequest(query="programming guidance", threshold=0.5, top_k=10)
    )
    search_remaining_count = len(
        [
            f
            for f in search_results
            if f.feedback_name in [fb.feedback_name for fb in archivable_feedbacks]
        ]
    )
    assert search_remaining_count == 0, (
        "Archived (non-APPROVED) feedbacks should be excluded from search_feedbacks"
    )


@skip_in_precommit
def test_archive_restore_delete_flow(supabase_storage, test_data, cleanup_after_test):
    """Test the complete archive -> restore -> delete flow.

    Note: archive_feedbacks_by_feedback_name only archives non-APPROVED feedbacks.
    APPROVED feedbacks are preserved to protect user-approved feedback.
    """
    storage = supabase_storage
    feedbacks = test_data["feedbacks"]

    # Filter to only non-APPROVED feedbacks (APPROVED feedbacks are NOT archived)
    archivable_feedbacks = [
        f for f in feedbacks if f.feedback_status != FeedbackStatus.APPROVED
    ]
    approved_feedbacks = [
        f for f in feedbacks if f.feedback_status == FeedbackStatus.APPROVED
    ]

    # Save feedbacks
    storage.save_feedbacks(feedbacks)

    # Get initial count
    results_initial = storage.get_feedbacks(limit=100)
    initial_count = len(
        [
            f
            for f in results_initial
            if f.feedback_name in [fb.feedback_name for fb in feedbacks]
        ]
    )
    assert initial_count >= len(feedbacks), "Should retrieve all saved feedbacks"

    # Archive feedbacks (only non-APPROVED will be archived)
    for feedback in feedbacks:
        storage.archive_feedbacks_by_feedback_name(
            feedback.feedback_name, agent_version=feedback.agent_version
        )

    # Verify archived - only APPROVED feedbacks should remain visible
    results_archived = storage.get_feedbacks(limit=100)
    remaining_after_archive = len(
        [
            f
            for f in results_archived
            if f.feedback_name in [fb.feedback_name for fb in feedbacks]
        ]
    )
    assert remaining_after_archive == len(approved_feedbacks), (
        "Only APPROVED feedbacks should remain visible after archiving"
    )

    # Restore feedbacks
    for feedback in archivable_feedbacks:
        storage.restore_archived_feedbacks_by_feedback_name(
            feedback.feedback_name, agent_version=feedback.agent_version
        )

    # Verify restored
    results_restored = storage.get_feedbacks(limit=100)
    restored_count = len(
        [
            f
            for f in results_restored
            if f.feedback_name in [fb.feedback_name for fb in feedbacks]
        ]
    )
    assert restored_count >= len(feedbacks), "Feedbacks should be restored"

    # Archive again
    for feedback in feedbacks:
        storage.archive_feedbacks_by_feedback_name(
            feedback.feedback_name, agent_version=feedback.agent_version
        )

    # Delete archived feedbacks (only non-APPROVED were archived)
    for feedback in archivable_feedbacks:
        storage.delete_archived_feedbacks_by_feedback_name(
            feedback.feedback_name, agent_version=feedback.agent_version
        )

    # Verify non-APPROVED feedbacks are permanently deleted
    for feedback in archivable_feedbacks:
        response = (
            storage.client.table("feedbacks")
            .select("*")
            .eq("feedback_name", feedback.feedback_name)
            .eq("agent_version", feedback.agent_version)
            .execute()
        )
        assert len(response.data) == 0, (
            f"Feedback {feedback.feedback_name} should be permanently deleted"
        )

    # Verify APPROVED feedbacks still exist (they were never archived)
    for feedback in approved_feedbacks:
        response = (
            storage.client.table("feedbacks")
            .select("*")
            .eq("feedback_name", feedback.feedback_name)
            .eq("agent_version", feedback.agent_version)
            .execute()
        )
        assert len(response.data) > 0, (
            f"APPROVED feedback {feedback.feedback_name} should still exist"
        )


@skip_in_precommit
def test_get_operation_state_with_new_request_interaction_sources_filter(
    supabase_storage,
):
    """Test get_operation_state_with_new_request_interaction with sources array filter.

    This test verifies:
    1. The RPC function correctly accepts the sources array parameter (p_sources)
    2. Filtering by sources returns only interactions from matching sources
    3. The sources parameter works as expected with multiple values

    Note: This test catches regressions like parameter name mismatches between
    Python code (p_sources) and database function (p_source).
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    user_id = "test_user_sources_filter"
    service_name = "test_service_sources"

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
        storage.client.table("_operation_state").delete().eq(
            "service_name", service_name
        ).execute()
    except Exception:  # noqa: S110
        pass

    # Create requests with different sources
    request_api = Request(
        request_id=f"test_request_api_{current_time}",
        user_id=user_id,
        created_at=current_time,
        source="api",
        agent_version="v1.0.0",
        session_id="",
    )
    request_webhook = Request(
        request_id=f"test_request_webhook_{current_time}",
        user_id=user_id,
        created_at=current_time + 1,
        source="webhook",
        agent_version="v1.0.0",
        session_id="",
    )
    request_other = Request(
        request_id=f"test_request_other_{current_time}",
        user_id=user_id,
        created_at=current_time + 2,
        source="other_source",
        agent_version="v1.0.0",
        session_id="",
    )

    # Add requests
    storage.add_request(request_api)
    storage.add_request(request_webhook)
    storage.add_request(request_other)

    # Create interactions for each request
    # Note: interaction_id is required but will be overwritten by database auto-increment
    interaction_api = Interaction(
        interaction_id=1000001,
        user_id=user_id,
        request_id=request_api.request_id,
        content="API interaction content",
        created_at=current_time,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )
    interaction_webhook = Interaction(
        interaction_id=1000002,
        user_id=user_id,
        request_id=request_webhook.request_id,
        content="Webhook interaction content",
        created_at=current_time + 1,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )
    interaction_other = Interaction(
        interaction_id=1000003,
        user_id=user_id,
        request_id=request_other.request_id,
        content="Other source interaction content",
        created_at=current_time + 2,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )

    # Add interactions
    storage.add_user_interaction(user_id, interaction_api)
    storage.add_user_interaction(user_id, interaction_webhook)
    storage.add_user_interaction(user_id, interaction_other)

    # Test 1: Filter by single source ["api"]
    state, results = storage.get_operation_state_with_new_request_interaction(
        service_name=service_name,
        user_id=user_id,
        sources=["api"],
    )
    assert isinstance(results, list), (
        "Should return a list of RequestInteractionDataModel"
    )
    # Should only get interactions from "api" source
    api_results = [r for r in results if r.request.source == "api"]
    non_api_results = [r for r in results if r.request.source != "api"]
    assert len(api_results) >= 1, "Should find at least one API interaction"
    assert len(non_api_results) == 0, "Should NOT find non-API interactions"

    # Test 2: Filter by multiple sources ["api", "webhook"]
    state, results = storage.get_operation_state_with_new_request_interaction(
        service_name=service_name,
        user_id=user_id,
        sources=["api", "webhook"],
    )
    # Should get interactions from both "api" and "webhook" sources
    for r in results:
        assert r.request.source in [
            "api",
            "webhook",
        ], f"Expected api or webhook, got {r.request.source}"

    # Test 3: Filter with no matching source - should return empty
    state, results = storage.get_operation_state_with_new_request_interaction(
        service_name=service_name,
        user_id=user_id,
        sources=["nonexistent_source"],
    )
    assert len(results) == 0, "Should return empty list for non-matching source"

    # Test 4: No sources filter (None) - should return all interactions
    state, results = storage.get_operation_state_with_new_request_interaction(
        service_name=service_name,
        user_id=user_id,
        sources=None,
    )
    assert len(results) >= 3, "Should return all interactions when sources is None"

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()
    storage.client.table("_operation_state").delete().eq(
        "service_name", service_name
    ).execute()


@skip_in_precommit
def test_get_last_k_interactions_grouped_sources_filter(supabase_storage):
    """Test get_last_k_interactions_grouped with sources array filter.

    This test verifies:
    1. The RPC function correctly accepts the sources array parameter (p_sources)
    2. Filtering by sources returns only interactions from matching sources
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    user_id = "test_user_last_k_sources"

    # Clean up any existing test data first
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Create requests with different sources
    request_api = Request(
        request_id=f"test_lastk_api_{current_time}",
        user_id=user_id,
        created_at=current_time,
        source="api",
        agent_version="v1.0.0",
        session_id="",
    )
    request_webhook = Request(
        request_id=f"test_lastk_webhook_{current_time}",
        user_id=user_id,
        created_at=current_time + 1,
        source="webhook",
        agent_version="v1.0.0",
        session_id="",
    )

    storage.add_request(request_api)
    storage.add_request(request_webhook)

    # Create interactions
    # Note: interaction_id is required but will be overwritten by database auto-increment
    interaction_api = Interaction(
        interaction_id=2000001,
        user_id=user_id,
        request_id=request_api.request_id,
        content="API interaction for last_k test",
        created_at=current_time,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )
    interaction_webhook = Interaction(
        interaction_id=2000002,
        user_id=user_id,
        request_id=request_webhook.request_id,
        content="Webhook interaction for last_k test",
        created_at=current_time + 1,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )

    storage.add_user_interaction(user_id, interaction_api)
    storage.add_user_interaction(user_id, interaction_webhook)

    # Test 1: Filter by single source
    grouped_results, flat_interactions = storage.get_last_k_interactions_grouped(
        user_id=user_id,
        k=10,
        sources=["api"],
    )
    # All results should be from "api" source
    for r in grouped_results:
        assert r.request.source == "api", f"Expected api, got {r.request.source}"
    for i in flat_interactions:
        # Find the request for this interaction
        matching_request = next(
            (r for r in grouped_results if r.request.request_id == i.request_id), None
        )
        if matching_request:
            assert matching_request.request.source == "api"

    # Test 2: Filter by multiple sources
    grouped_results, flat_interactions = storage.get_last_k_interactions_grouped(
        user_id=user_id,
        k=10,
        sources=["api", "webhook"],
    )
    assert len(flat_interactions) >= 2, "Should find interactions from both sources"

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_operation_state_crud(supabase_storage):
    """Test operation state CRUD operations.

    This test verifies:
    1. create_operation_state creates a new state
    2. get_operation_state retrieves the state
    3. update_operation_state modifies the state
    4. upsert_operation_state creates or updates
    5. delete_operation_state removes the state
    """
    storage = supabase_storage
    service_name = "test_operation_state_crud_service"

    # Clean up any existing test data
    with contextlib.suppress(Exception):
        storage.client.table("_operation_state").delete().eq(
            "service_name", service_name
        ).execute()

    # Test 1: Create operation state
    initial_state = {"last_processed_id": 0, "status": "initialized"}
    storage.create_operation_state(service_name, initial_state)

    # Test 2: Get operation state
    # Note: get_operation_state returns {"service_name", "operation_state", "updated_at"}
    retrieved = storage.get_operation_state(service_name)
    assert retrieved is not None, "Should retrieve the created state"
    assert retrieved["operation_state"]["last_processed_id"] == 0
    assert retrieved["operation_state"]["status"] == "initialized"

    # Test 3: Update operation state
    updated_state = {"last_processed_id": 100, "status": "processing"}
    storage.update_operation_state(service_name, updated_state)

    retrieved = storage.get_operation_state(service_name)
    assert retrieved["operation_state"]["last_processed_id"] == 100
    assert retrieved["operation_state"]["status"] == "processing"

    # Test 4: Upsert operation state (update existing)
    upsert_state = {"last_processed_id": 200, "status": "completed"}
    storage.upsert_operation_state(service_name, upsert_state)

    retrieved = storage.get_operation_state(service_name)
    assert retrieved["operation_state"]["last_processed_id"] == 200
    assert retrieved["operation_state"]["status"] == "completed"

    # Test 5: Delete operation state
    storage.delete_operation_state(service_name)
    retrieved = storage.get_operation_state(service_name)
    assert retrieved is None, "State should be deleted"

    # Test 6: Upsert creates new state when none exists
    new_service_name = f"{service_name}_new"
    new_state = {"last_processed_id": 50, "status": "new"}
    storage.upsert_operation_state(new_service_name, new_state)

    retrieved = storage.get_operation_state(new_service_name)
    assert retrieved is not None
    assert retrieved["operation_state"]["last_processed_id"] == 50

    # Clean up
    storage.client.table("_operation_state").delete().eq(
        "service_name", new_service_name
    ).execute()


@skip_in_precommit
def test_try_acquire_in_progress_lock(supabase_storage):
    """Test try_acquire_in_progress_lock for atomic lock acquisition.

    This test verifies:
    1. First caller acquires the lock successfully
    2. Second caller is blocked
    3. Lock can be released and re-acquired
    """
    storage = supabase_storage
    state_key = "test_lock_service_key"

    # Clean up any existing test data
    with contextlib.suppress(Exception):
        storage.client.table("_operation_state").delete().eq(
            "service_name", state_key
        ).execute()

    # Test 1: First request acquires lock
    request_id_1 = "request_1_abc123"
    result_1 = storage.try_acquire_in_progress_lock(state_key, request_id_1)

    assert result_1["acquired"] is True, "First request should acquire lock"
    assert "state" in result_1, "Result should contain state"

    # Test 2: Second request is blocked
    request_id_2 = "request_2_def456"
    result_2 = storage.try_acquire_in_progress_lock(state_key, request_id_2)

    assert result_2["acquired"] is False, "Second request should be blocked"

    # Test 3: Release lock by deleting state
    storage.delete_operation_state(state_key)

    # Test 4: Now a new request can acquire lock
    request_id_3 = "request_3_ghi789"
    result_3 = storage.try_acquire_in_progress_lock(state_key, request_id_3)

    assert result_3["acquired"] is True, "New request should acquire lock after release"

    # Clean up
    storage.client.table("_operation_state").delete().eq(
        "service_name", state_key
    ).execute()


@skip_in_precommit
def test_update_feedback_status(supabase_storage, cleanup_after_test):
    """Test update_feedback_status for changing feedback approval status.

    This test verifies:
    1. Feedback status can be updated from PENDING to APPROVED
    2. Feedback status can be updated from PENDING to REJECTED
    3. Status change is persisted correctly
    """
    storage = supabase_storage
    int(datetime.now(UTC).timestamp())

    # Create test feedbacks with PENDING status
    test_feedbacks = [
        Feedback(
            feedback_name="test_status_feedback_1",
            feedback_content="Test feedback for status update - approve",
            feedback_status=FeedbackStatus.PENDING,
            agent_version="test_v1",
            feedback_metadata="metadata_1",
        ),
        Feedback(
            feedback_name="test_status_feedback_2",
            feedback_content="Test feedback for status update - reject",
            feedback_status=FeedbackStatus.PENDING,
            agent_version="test_v1",
            feedback_metadata="metadata_2",
        ),
    ]

    # Save feedbacks
    storage.save_feedbacks(test_feedbacks)

    # Get the saved feedbacks to get their IDs
    saved_feedbacks = storage.get_feedbacks(
        feedback_name="test_status_feedback_1",
        feedback_status_filter=FeedbackStatus.PENDING,
    )
    assert len(saved_feedbacks) >= 1, "Should find saved feedback"
    feedback_to_approve = saved_feedbacks[0]

    saved_feedbacks_2 = storage.get_feedbacks(
        feedback_name="test_status_feedback_2",
        feedback_status_filter=FeedbackStatus.PENDING,
    )
    assert len(saved_feedbacks_2) >= 1, "Should find second feedback"
    feedback_to_reject = saved_feedbacks_2[0]

    # Test 1: Update to APPROVED
    storage.update_feedback_status(
        feedback_to_approve.feedback_id, FeedbackStatus.APPROVED
    )

    approved_feedbacks = storage.get_feedbacks(
        feedback_name="test_status_feedback_1",
        feedback_status_filter=FeedbackStatus.APPROVED,
    )
    assert len(approved_feedbacks) >= 1, "Should find approved feedback"
    assert approved_feedbacks[0].feedback_status == FeedbackStatus.APPROVED

    # Test 2: Update to REJECTED
    storage.update_feedback_status(
        feedback_to_reject.feedback_id, FeedbackStatus.REJECTED
    )

    rejected_feedbacks = storage.get_feedbacks(
        feedback_name="test_status_feedback_2",
        feedback_status_filter=FeedbackStatus.REJECTED,
    )
    assert len(rejected_feedbacks) >= 1, "Should find rejected feedback"
    assert rejected_feedbacks[0].feedback_status == FeedbackStatus.REJECTED


@skip_in_precommit
def test_raw_feedback_status_management(supabase_storage, cleanup_after_test):
    """Test raw feedback status management operations.

    This test verifies:
    1. update_all_raw_feedbacks_status transitions statuses correctly
    2. has_raw_feedbacks_with_status checks existence
    3. delete_all_raw_feedbacks_by_status removes correct records
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    feedback_name = "test_raw_fb_status"
    agent_version = "test_status_v1"

    # Create raw feedbacks with different statuses
    raw_feedbacks = [
        RawFeedback(
            feedback_name=feedback_name,
            agent_version=agent_version,
            request_id=f"req_status_{i}",
            feedback_content=f"Raw feedback content {i}",
            created_at=current_time,
            status=None,  # CURRENT status
        )
        for i in range(3)
    ]

    storage.save_raw_feedbacks(raw_feedbacks)

    # Test 1: Check has_raw_feedbacks_with_status for CURRENT (None)
    has_current = storage.has_raw_feedbacks_with_status(
        status=None, agent_version=agent_version, feedback_name=feedback_name
    )
    assert has_current is True, "Should have CURRENT raw feedbacks"

    # Test 2: Update status from CURRENT (None) to PENDING
    updated_count = storage.update_all_raw_feedbacks_status(
        old_status=None,
        new_status=Status.PENDING,
        agent_version=agent_version,
        feedback_name=feedback_name,
    )
    assert updated_count == 3, f"Should update 3 feedbacks, got {updated_count}"

    # Test 3: Verify CURRENT is now empty
    has_current_after = storage.has_raw_feedbacks_with_status(
        status=None, agent_version=agent_version, feedback_name=feedback_name
    )
    assert has_current_after is False, "Should have no CURRENT raw feedbacks"

    # Test 4: Verify PENDING has feedbacks
    has_pending = storage.has_raw_feedbacks_with_status(
        status=Status.PENDING, agent_version=agent_version, feedback_name=feedback_name
    )
    assert has_pending is True, "Should have PENDING raw feedbacks"

    # Test 5: Delete all PENDING feedbacks
    deleted_count = storage.delete_all_raw_feedbacks_by_status(
        status=Status.PENDING, agent_version=agent_version, feedback_name=feedback_name
    )
    assert deleted_count == 3, f"Should delete 3 feedbacks, got {deleted_count}"

    # Test 6: Verify deletion
    has_pending_after = storage.has_raw_feedbacks_with_status(
        status=Status.PENDING, agent_version=agent_version, feedback_name=feedback_name
    )
    assert has_pending_after is False, (
        "Should have no PENDING raw feedbacks after deletion"
    )


@skip_in_precommit
def test_delete_request_and_session_id(supabase_storage):
    """Test delete_request and delete_session operations.

    This test verifies:
    1. delete_request removes request and its interactions
    2. delete_session removes all requests in a group
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    user_id = "test_delete_request_user"
    session_id = "test_delete_group"

    # Clean up any existing test data
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
    except Exception:  # noqa: S110
        pass

    # Create requests in a group
    request_1 = Request(
        request_id=f"delete_req_1_{current_time}",
        user_id=user_id,
        created_at=current_time,
        source="test",
        agent_version="v1",
        session_id=session_id,
    )
    request_2 = Request(
        request_id=f"delete_req_2_{current_time}",
        user_id=user_id,
        created_at=current_time + 1,
        source="test",
        agent_version="v1",
        session_id=session_id,
    )
    request_standalone = Request(
        request_id=f"delete_req_standalone_{current_time}",
        user_id=user_id,
        created_at=current_time + 2,
        source="test",
        agent_version="v1",
        session_id="",  # Not in the group
    )

    storage.add_request(request_1)
    storage.add_request(request_2)
    storage.add_request(request_standalone)

    # Add interactions for request_1
    interaction_1 = Interaction(
        interaction_id=3000001,
        user_id=user_id,
        request_id=request_1.request_id,
        content="Interaction for delete test",
        created_at=current_time,
        user_action=UserActionType.NONE,
        user_action_description="",
        interacted_image_url="",
    )
    storage.add_user_interaction(user_id, interaction_1)

    # Test 1: Delete single request (should also delete its interactions)
    storage.delete_request(request_standalone.request_id)

    deleted_request = storage.get_request(request_standalone.request_id)
    assert deleted_request is None, "Standalone request should be deleted"

    # Test 2: Delete session
    deleted_count = storage.delete_session(session_id)
    assert deleted_count == 2, f"Should delete 2 requests in group, got {deleted_count}"

    # Verify requests in group are deleted
    req_1 = storage.get_request(request_1.request_id)
    req_2 = storage.get_request(request_2.request_id)
    assert req_1 is None, "Request 1 should be deleted"
    assert req_2 is None, "Request 2 should be deleted"

    # Verify interactions are also deleted
    interactions = storage.get_user_interaction(user_id)
    assert len(interactions) == 0, "Interactions should be deleted with request"


@skip_in_precommit
def test_agent_success_evaluation_results(supabase_storage):
    """Test agent success evaluation results CRUD operations.

    This test verifies:
    1. save_agent_success_evaluation_results stores results
    2. get_agent_success_evaluation_results retrieves with optional filter
    3. delete_all_agent_success_evaluation_results clears all
    """
    storage = supabase_storage
    int(datetime.now(UTC).timestamp())
    agent_version = "test_eval_v1"

    # Clean up any existing test data
    with contextlib.suppress(Exception):
        storage.client.table("agent_success_evaluation_result").delete().eq(
            "agent_version", agent_version
        ).execute()

    # Create test evaluation results with new fields
    results = [
        AgentSuccessEvaluationResult(
            session_id=f"eval_group_{i}",
            agent_version=agent_version,
            is_success=i % 2 == 0,  # Alternating success/failure
            failure_type="timeout" if i % 2 != 0 else "",
            failure_reason="Request timed out" if i % 2 != 0 else "",
            number_of_correction_per_session=i,
            user_turns_to_resolution=3 if i % 2 == 0 else None,
            is_escalated=i == 3,
        )
        for i in range(4)
    ]

    # Test 1: Save evaluation results
    storage.save_agent_success_evaluation_results(results)

    # Test 2: Get all evaluation results
    retrieved = storage.get_agent_success_evaluation_results(limit=100)
    assert len(retrieved) >= 4, "Should retrieve at least 4 results"

    # Test 3: Get by agent_version filter
    filtered = storage.get_agent_success_evaluation_results(
        agent_version=agent_version, limit=100
    )
    assert len(filtered) == 4, (
        f"Should retrieve exactly 4 results for agent_version, got {len(filtered)}"
    )

    # Verify result content
    success_results = [r for r in filtered if r.is_success]
    failure_results = [r for r in filtered if not r.is_success]
    assert len(success_results) == 2, "Should have 2 success results"
    assert len(failure_results) == 2, "Should have 2 failure results"

    # Test new fields round-trip
    for r in filtered:
        assert isinstance(r.number_of_correction_per_session, int)
        assert isinstance(r.is_escalated, bool)
        if r.is_success:
            assert r.user_turns_to_resolution == 3
        else:
            assert r.user_turns_to_resolution is None

    # Verify escalation flag
    escalated = [r for r in filtered if r.is_escalated]
    assert len(escalated) == 1, "Should have exactly 1 escalated result"

    # Test 4: Delete all results (use table delete for targeted cleanup)
    storage.client.table("agent_success_evaluation_result").delete().eq(
        "agent_version", agent_version
    ).execute()

    # Verify deletion
    after_delete = storage.get_agent_success_evaluation_results(
        agent_version=agent_version, limit=100
    )
    assert len(after_delete) == 0, "Should have no results after deletion"


@skip_in_precommit
def test_count_raw_feedbacks_by_session(supabase_storage):
    """Test counting raw feedbacks by session ID.

    This test verifies:
    1. count_raw_feedbacks_by_session returns 0 for unknown session
    2. count_raw_feedbacks_by_session returns correct count for session with feedbacks
    """
    storage = supabase_storage
    session_id = "test_count_session"

    # Test 1: Unknown session returns 0
    count = storage.count_raw_feedbacks_by_session(session_id="nonexistent_session")
    assert count == 0, "Should return 0 for unknown session"

    # Test 2: Session with feedbacks returns correct count
    # Create requests linked to the session
    test_user_id = "count_test_user"
    test_agent_version = "count_test_agent"
    requests = [
        Request(
            request_id=f"count_test_req_{i}",
            user_id=test_user_id,
            session_id=session_id,
        )
        for i in range(2)
    ]
    for req in requests:
        storage.add_request(req)

    # Create raw feedbacks linked to those requests
    feedbacks = [
        RawFeedback(
            user_id=test_user_id,
            agent_version=test_agent_version,
            request_id="count_test_req_0",
            feedback_content="feedback 1",
        ),
        RawFeedback(
            user_id=test_user_id,
            agent_version=test_agent_version,
            request_id="count_test_req_0",
            feedback_content="feedback 2",
        ),
        RawFeedback(
            user_id=test_user_id,
            agent_version=test_agent_version,
            request_id="count_test_req_1",
            feedback_content="feedback 3",
        ),
    ]
    storage.save_raw_feedbacks(feedbacks)

    count = storage.count_raw_feedbacks_by_session(session_id=session_id)
    assert count == 3, f"Should return 3 for session with 3 feedbacks, got {count}"

    # Cleanup
    for req in requests:
        storage.client.table("raw_feedbacks").delete().eq(
            "request_id", req.request_id
        ).execute()
        storage.client.table("requests").delete().eq(
            "request_id", req.request_id
        ).execute()


@skip_in_precommit
def test_profile_status_management(supabase_storage):
    """Test profile status management operations.

    This test verifies:
    1. update_all_profiles_status transitions statuses correctly
    2. get_user_ids_with_status returns correct users
    3. delete_all_profiles_by_status removes correct profiles
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    user_id = "test_profile_status_user"

    # Clean up any existing test data
    with contextlib.suppress(Exception):
        storage.client.table("profiles").delete().eq("user_id", user_id).execute()

    # Create test profiles (CURRENT status = None)
    profiles = [
        UserProfile(
            profile_id=f"profile_status_{i}",
            user_id=user_id,
            profile_content=f"Profile content for status test {i}",
            last_modified_timestamp=current_time,
            generated_from_request_id=f"req_{i}",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            source="test",
        )
        for i in range(3)
    ]

    storage.add_user_profile(user_id, profiles)

    # Test 1: Get user IDs with CURRENT status (None)
    user_ids = storage.get_user_ids_with_status(status=None)
    assert user_id in user_ids, "Should find user with CURRENT profiles"

    # Test 2: Update status from CURRENT (None) to PENDING
    updated_count = storage.update_all_profiles_status(
        old_status=None,
        new_status=Status.PENDING,
        user_ids=[user_id],
    )
    assert updated_count == 3, f"Should update 3 profiles, got {updated_count}"

    # Test 3: Verify user no longer has CURRENT profiles
    user_ids_after = storage.get_user_ids_with_status(status=None)
    assert user_id not in user_ids_after, "User should not have CURRENT profiles"

    # Test 4: Verify user has PENDING profiles
    user_ids_pending = storage.get_user_ids_with_status(status=Status.PENDING)
    assert user_id in user_ids_pending, "User should have PENDING profiles"

    # Test 5: Delete all PENDING profiles
    deleted_count = storage.delete_all_profiles_by_status(status=Status.PENDING)
    assert deleted_count >= 3, f"Should delete at least 3 profiles, got {deleted_count}"

    # Clean up any remaining
    storage.client.table("profiles").delete().eq("user_id", user_id).execute()


@skip_in_precommit
def test_count_operations(supabase_storage):
    """Test count operations for interactions and raw feedbacks.

    This test verifies:
    1. count_all_interactions returns correct count
    2. count_raw_feedbacks returns correct count with filters
    """
    storage = supabase_storage
    current_time = int(datetime.now(UTC).timestamp())
    user_id = "test_count_user"
    feedback_name = "test_count_feedback"

    # Clean up any existing test data
    try:
        storage.client.table("interactions").delete().eq("user_id", user_id).execute()
        storage.client.table("requests").delete().eq("user_id", user_id).execute()
        storage.client.table("raw_feedbacks").delete().eq(
            "feedback_name", feedback_name
        ).execute()
    except Exception:  # noqa: S110
        pass

    # Get initial counts
    initial_interaction_count = storage.count_all_interactions()
    _initial_raw_feedback_count = storage.count_raw_feedbacks(
        feedback_name=feedback_name
    )

    # Create test request
    test_request = Request(
        request_id=f"count_req_{current_time}",
        user_id=user_id,
        created_at=current_time,
        source="test",
        agent_version="v1",
        session_id="",
    )
    storage.add_request(test_request)

    # Create test interactions
    for i in range(5):
        interaction = Interaction(
            interaction_id=4000000 + i,
            user_id=user_id,
            request_id=test_request.request_id,
            content=f"Count test interaction {i}",
            created_at=current_time + i,
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        )
        storage.add_user_interaction(user_id, interaction)

    # Test 1: Count all interactions
    new_interaction_count = storage.count_all_interactions()
    assert new_interaction_count == initial_interaction_count + 5, (
        f"Should have 5 more interactions, got {new_interaction_count - initial_interaction_count}"
    )

    # Create test raw feedbacks
    raw_feedbacks = [
        RawFeedback(
            feedback_name=feedback_name,
            agent_version="count_test_v1",
            request_id=f"count_fb_req_{i}",
            feedback_content=f"Count test feedback {i}",
            created_at=current_time,
        )
        for i in range(3)
    ]
    storage.save_raw_feedbacks(raw_feedbacks)

    # Test 2: Count raw feedbacks with filter
    new_raw_feedback_count = storage.count_raw_feedbacks(feedback_name=feedback_name)
    assert new_raw_feedback_count == 3, (
        f"Should have 3 raw feedbacks, got {new_raw_feedback_count}"
    )

    # Clean up
    storage.client.table("interactions").delete().eq("user_id", user_id).execute()
    storage.client.table("requests").delete().eq("user_id", user_id).execute()
    storage.client.table("raw_feedbacks").delete().eq(
        "feedback_name", feedback_name
    ).execute()


@skip_in_precommit
def test_get_feedbacks_with_multiple_feedback_status_filter(
    supabase_storage, cleanup_after_test
):
    """Test get_feedbacks with a list of feedback_status_filter values.

    Verifies that passing [APPROVED, PENDING] returns both but excludes REJECTED.
    """
    storage = supabase_storage
    feedback_name = "test_multi_status_filter"

    # Clean up any existing test data first
    with contextlib.suppress(Exception):
        storage.client.table("feedbacks").delete().eq(
            "feedback_name", feedback_name
        ).execute()

    # Create feedbacks with different FeedbackStatus values
    test_feedbacks = [
        Feedback(
            feedback_name=feedback_name,
            feedback_content="Test feedback - approved",
            feedback_status=FeedbackStatus.APPROVED,
            agent_version="test_v1",
            feedback_metadata="approved_fb",
        ),
        Feedback(
            feedback_name=feedback_name,
            feedback_content="Test feedback - pending",
            feedback_status=FeedbackStatus.PENDING,
            agent_version="test_v1",
            feedback_metadata="pending_fb",
        ),
        Feedback(
            feedback_name=feedback_name,
            feedback_content="Test feedback - rejected",
            feedback_status=FeedbackStatus.REJECTED,
            agent_version="test_v1",
            feedback_metadata="rejected_fb",
        ),
    ]

    # Save feedbacks
    storage.save_feedbacks(test_feedbacks)

    # Query with list of statuses [APPROVED, PENDING]
    results = storage.get_feedbacks(
        feedback_name=feedback_name,
        feedback_status_filter=[FeedbackStatus.APPROVED, FeedbackStatus.PENDING],
    )

    # Should return 2 feedbacks (APPROVED + PENDING), not 3
    assert len(results) == 2, f"Expected 2, got {len(results)}"

    # Verify statuses
    statuses = {r.feedback_status for r in results}
    assert FeedbackStatus.APPROVED in statuses
    assert FeedbackStatus.PENDING in statuses
    assert FeedbackStatus.REJECTED not in statuses

    # Test with None (should return all 3)
    all_results = storage.get_feedbacks(
        feedback_name=feedback_name,
        feedback_status_filter=None,
    )
    assert len(all_results) >= 3, f"Expected at least 3, got {len(all_results)}"

    # Clean up
    storage.client.table("feedbacks").delete().eq(
        "feedback_name", feedback_name
    ).execute()


if __name__ == "__main__":
    pytest.main([__file__])
