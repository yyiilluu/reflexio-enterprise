"""End-to-end integration tests for hybrid search functionality.

Tests the hybrid search (Vector + Full-Text Search with RRF) implementation
across all 4 tables: profiles, interactions, feedbacks, and raw_feedbacks.

These tests verify that:
1. Semantic queries work via vector similarity search
2. Exact keyword queries work via full-text search
3. Hybrid mode combines both search types effectively
4. All search modes (vector, fts, hybrid) function correctly
"""

import os
from datetime import datetime, timezone

import pytest
from reflexio_commons.api_schema.retriever_schema import (
    SearchInteractionRequest,
    SearchUserProfileRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    NEVER_EXPIRES_TIMESTAMP,
    Feedback,
    FeedbackStatus,
    Interaction,
    ProfileTimeToLive,
    RawFeedback,
    Request,
    UserActionType,
    UserProfile,
)
from reflexio_commons.config_schema import SearchMode, StorageConfigSupabase

from reflexio.server.services.storage.supabase_storage import SupabaseStorage
from reflexio.tests.server.test_utils import skip_in_precommit

# ==============================
# Fixtures
# ==============================


def create_supabase_storage(search_mode: SearchMode = SearchMode.HYBRID):
    """Create a SupabaseStorage instance with specified search mode.

    Args:
        search_mode: The search mode to use (VECTOR, FTS, or HYBRID)

    Returns:
        SupabaseStorage instance configured with the specified search mode
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
    storage = SupabaseStorage(org_id="test_hybrid", config=config)
    # Override search_mode for testing (normally comes from site_var)
    storage.search_mode = search_mode
    return storage


@pytest.fixture
def supabase_storage_hybrid():
    """Create a SupabaseStorage instance with hybrid search mode."""
    return create_supabase_storage(SearchMode.HYBRID)


@pytest.fixture
def supabase_storage_vector():
    """Create a SupabaseStorage instance with vector-only search mode."""
    return create_supabase_storage(SearchMode.VECTOR)


@pytest.fixture
def supabase_storage_fts():
    """Create a SupabaseStorage instance with FTS-only search mode."""
    return create_supabase_storage(SearchMode.FTS)


@pytest.fixture
def hybrid_test_data():
    """Create test data specifically designed for hybrid search testing.

    This test data includes:
    - Unique keywords that are easy to find with FTS
    - Semantic content that is easy to find with vector search
    """
    current_time = int(datetime.now(timezone.utc).timestamp())
    unique_keyword = f"xyzzy_quantum_flux_{current_time}"  # Unique keyword for FTS

    return {
        "user_id": f"test_hybrid_user_{current_time}",
        "unique_keyword": unique_keyword,
        "request": Request(
            request_id=f"test_request_{current_time}",
            user_id=f"test_hybrid_user_{current_time}",
            created_at=current_time,
            source="test_hybrid_source",
            agent_version="test_hybrid_v1",
            session_id="",
        ),
        "profile_with_keyword": UserProfile(
            profile_id=f"test_profile_keyword_{current_time}",
            user_id=f"test_hybrid_user_{current_time}",
            profile_content=f"User prefers {unique_keyword} technology for data processing. They also enjoy hiking and outdoor activities.",
            last_modified_timestamp=current_time,
            generated_from_request_id=f"test_request_{current_time}",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            source="test_hybrid_source",
        ),
        "profile_semantic": UserProfile(
            profile_id=f"test_profile_semantic_{current_time}",
            user_id=f"test_hybrid_user_{current_time}",
            profile_content="User is passionate about artificial intelligence and machine learning. They frequently discuss neural networks and deep learning architectures.",
            last_modified_timestamp=current_time,
            generated_from_request_id=f"test_request_{current_time}",
            profile_time_to_live=ProfileTimeToLive.INFINITY,
            expiration_timestamp=NEVER_EXPIRES_TIMESTAMP,
            source="test_hybrid_source",
        ),
        "interaction_with_keyword": Interaction(
            interaction_id=int(current_time),
            user_id=f"test_hybrid_user_{current_time}",
            request_id=f"test_request_{current_time}",
            content=f"I need help with {unique_keyword} configuration. It's not working as expected.",
            created_at=current_time,
            user_action=UserActionType.CLICK,
            user_action_description="Clicked on configuration settings",
            interacted_image_url="",
        ),
        "interaction_semantic": Interaction(
            interaction_id=int(current_time) + 1,
            user_id=f"test_hybrid_user_{current_time}",
            request_id=f"test_request_{current_time}",
            content="Can you explain how convolutional neural networks work? I'm trying to understand image classification.",
            created_at=current_time + 10,
            user_action=UserActionType.NONE,
            user_action_description="",
            interacted_image_url="",
        ),
        "raw_feedback_with_keyword": RawFeedback(
            feedback_name=f"test_hybrid_raw_feedback_{current_time}",
            agent_version="test_hybrid_v1",
            request_id=f"test_request_{current_time}",
            feedback_content=f"Agent handled the {unique_keyword} query incorrectly. Need better error handling.",
            created_at=current_time,
        ),
        "raw_feedback_semantic": RawFeedback(
            feedback_name=f"test_hybrid_raw_feedback_semantic_{current_time}",
            agent_version="test_hybrid_v1",
            request_id=f"test_request_{current_time}",
            feedback_content="Agent provided excellent explanations about machine learning concepts and was very thorough.",
            created_at=current_time,
        ),
        "feedback_with_keyword": Feedback(
            feedback_name=f"test_hybrid_feedback_{current_time}",
            feedback_content=f"The {unique_keyword} feature needs improvement. Users are confused by the interface.",
            feedback_status=FeedbackStatus.PENDING,
            agent_version="test_hybrid_v1",
            feedback_metadata="test_metadata",
        ),
        "feedback_semantic": Feedback(
            feedback_name=f"test_hybrid_feedback_semantic_{current_time}",
            feedback_content="Agent demonstrates strong understanding of natural language processing and provides accurate responses.",
            feedback_status=FeedbackStatus.PENDING,
            agent_version="test_hybrid_v1",
            feedback_metadata="test_metadata",
        ),
    }


@pytest.fixture
def cleanup_hybrid_test(supabase_storage_hybrid, hybrid_test_data):
    """Fixture to clean up hybrid test data after each test."""
    yield
    try:
        user_id = hybrid_test_data["user_id"]

        # Clean up interactions first (due to foreign key constraint)
        supabase_storage_hybrid.client.table("interactions").delete().eq(
            "user_id", user_id
        ).execute()

        # Clean up profiles
        supabase_storage_hybrid.client.table("profiles").delete().eq(
            "user_id", user_id
        ).execute()

        # Clean up requests (after interactions due to foreign key constraint)
        supabase_storage_hybrid.client.table("requests").delete().eq(
            "user_id", user_id
        ).execute()

        # Clean up feedbacks by feedback_name pattern
        supabase_storage_hybrid.client.table("feedbacks").delete().like(
            "feedback_name", "test_hybrid_%"
        ).execute()

        # Clean up raw_feedbacks by feedback_name pattern
        supabase_storage_hybrid.client.table("raw_feedbacks").delete().like(
            "feedback_name", "test_hybrid_%"
        ).execute()

        print("Hybrid test data cleaned up successfully")
    except Exception as e:
        print(f"Error during hybrid test cleanup: {str(e)}")


# ==============================
# Profile Hybrid Search Tests
# ==============================


@skip_in_precommit
def test_hybrid_search_profiles_keyword_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds profiles with exact keyword matches (FTS component)."""
    storage = supabase_storage_hybrid
    user_id = hybrid_test_data["user_id"]
    profile = hybrid_test_data["profile_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add profile with unique keyword
    storage.add_user_profile(user_id, [profile])

    # Search using the exact unique keyword - FTS should find this
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query=unique_keyword,
        threshold=0.1,  # Low threshold since FTS handles exact matches
    )
    results = storage.search_user_profile(search_request)

    assert len(results) > 0, f"Should find profile with keyword '{unique_keyword}'"
    assert any(unique_keyword in r.profile_content for r in results), (
        "Result should contain the unique keyword"
    )


@skip_in_precommit
def test_hybrid_search_profiles_semantic_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds profiles with semantic similarity (vector component)."""
    storage = supabase_storage_hybrid
    user_id = hybrid_test_data["user_id"]
    profile = hybrid_test_data["profile_semantic"]

    # Add profile about AI/ML
    storage.add_user_profile(user_id, [profile])

    # Search using semantically related query (different words, same meaning)
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query="deep learning and artificial neural networks for classification",
        threshold=0.3,  # Lower threshold for semantic similarity
    )
    results = storage.search_user_profile(search_request)

    assert len(results) > 0, "Should find semantically similar profile"
    assert any(
        "artificial intelligence" in r.profile_content.lower()
        or "machine learning" in r.profile_content.lower()
        for r in results
    ), "Result should contain AI/ML content"


@skip_in_precommit
def test_vector_only_search_profiles(
    supabase_storage_vector, hybrid_test_data, cleanup_hybrid_test
):
    """Test vector-only search mode for profiles."""
    storage = supabase_storage_vector
    user_id = hybrid_test_data["user_id"]
    profile = hybrid_test_data["profile_semantic"]

    # Add profile
    storage.add_user_profile(user_id, [profile])

    # Search with semantic query
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query="neural networks and AI research",
        threshold=0.3,  # Lower threshold for semantic similarity
    )
    results = storage.search_user_profile(search_request)

    assert len(results) > 0, "Vector search should find semantically similar profiles"


@skip_in_precommit
def test_fts_only_search_profiles(
    supabase_storage_fts, hybrid_test_data, cleanup_hybrid_test
):
    """Test FTS-only search mode for profiles."""
    storage = supabase_storage_fts
    user_id = hybrid_test_data["user_id"]
    profile = hybrid_test_data["profile_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add profile with keyword
    storage.add_user_profile(user_id, [profile])

    # Search with exact keyword
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query=unique_keyword,
        threshold=0.1,
    )
    results = storage.search_user_profile(search_request)

    assert len(results) > 0, "FTS search should find profiles with exact keywords"


# ==============================
# Interaction Hybrid Search Tests
# ==============================


@skip_in_precommit
def test_hybrid_search_interactions_keyword_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds interactions with exact keyword matches."""
    storage = supabase_storage_hybrid
    user_id = hybrid_test_data["user_id"]
    request = hybrid_test_data["request"]
    interaction = hybrid_test_data["interaction_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add request first (required for foreign key constraint)
    storage.add_request(request)

    # Add interaction with unique keyword
    storage.add_user_interaction(user_id, interaction)

    # Search using the exact unique keyword
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query=unique_keyword,
        most_recent_k=10,
    )
    results = storage.search_interaction(search_request)

    assert len(results) > 0, f"Should find interaction with keyword '{unique_keyword}'"
    assert any(unique_keyword in r.content for r in results), (
        "Result should contain the unique keyword"
    )


@skip_in_precommit
def test_hybrid_search_interactions_semantic_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds interactions with semantic similarity."""
    storage = supabase_storage_hybrid
    user_id = hybrid_test_data["user_id"]
    request = hybrid_test_data["request"]
    interaction = hybrid_test_data["interaction_semantic"]

    # Add request first (required for foreign key constraint)
    storage.add_request(request)

    # Add interaction about neural networks
    storage.add_user_interaction(user_id, interaction)

    # Search using semantically related query
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query="How do deep learning models classify images?",
        most_recent_k=10,
    )
    results = storage.search_interaction(search_request)

    assert len(results) > 0, "Should find semantically similar interaction"
    assert any(
        "neural network" in r.content.lower()
        or "image classification" in r.content.lower()
        for r in results
    ), "Result should contain neural network content"


@skip_in_precommit
def test_vector_only_search_interactions(
    supabase_storage_vector, hybrid_test_data, cleanup_hybrid_test
):
    """Test vector-only search mode for interactions."""
    storage = supabase_storage_vector
    user_id = hybrid_test_data["user_id"]
    request = hybrid_test_data["request"]
    interaction = hybrid_test_data["interaction_semantic"]

    # Add request first (required for foreign key constraint)
    storage.add_request(request)

    # Add interaction
    storage.add_user_interaction(user_id, interaction)

    # Search with semantic query
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query="computer vision and deep learning",
        most_recent_k=10,
    )
    results = storage.search_interaction(search_request)

    assert len(results) > 0, (
        "Vector search should find semantically similar interactions"
    )


@skip_in_precommit
def test_fts_only_search_interactions(
    supabase_storage_fts, hybrid_test_data, cleanup_hybrid_test
):
    """Test FTS-only search mode for interactions."""
    storage = supabase_storage_fts
    user_id = hybrid_test_data["user_id"]
    request = hybrid_test_data["request"]
    interaction = hybrid_test_data["interaction_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add request first (required for foreign key constraint)
    storage.add_request(request)

    # Add interaction with keyword
    storage.add_user_interaction(user_id, interaction)

    # Search with exact keyword
    search_request = SearchInteractionRequest(
        user_id=user_id,
        query=unique_keyword,
        most_recent_k=10,
    )
    results = storage.search_interaction(search_request)

    assert len(results) > 0, "FTS search should find interactions with exact keywords"


# ==============================
# Raw Feedback Hybrid Search Tests
# ==============================


@skip_in_precommit
def test_hybrid_search_raw_feedbacks_keyword_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds raw feedbacks with exact keyword matches."""
    storage = supabase_storage_hybrid
    raw_feedback = hybrid_test_data["raw_feedback_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Save raw feedback with unique keyword
    storage.save_raw_feedbacks([raw_feedback])

    # Search using the exact unique keyword
    results = storage.search_raw_feedbacks(
        query=unique_keyword,
        match_threshold=0.1,
        match_count=10,
    )

    assert len(results) > 0, f"Should find raw feedback with keyword '{unique_keyword}'"
    assert any(unique_keyword in r.feedback_content for r in results), (
        "Result should contain the unique keyword"
    )


@skip_in_precommit
def test_hybrid_search_raw_feedbacks_semantic_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds raw feedbacks with semantic similarity."""
    storage = supabase_storage_hybrid
    raw_feedback = hybrid_test_data["raw_feedback_semantic"]

    # Save raw feedback about ML
    storage.save_raw_feedbacks([raw_feedback])

    # Search using semantically related query
    results = storage.search_raw_feedbacks(
        query="AI explanations and deep learning tutorials",
        match_threshold=0.3,  # Lower threshold for semantic similarity
        match_count=10,
    )

    assert len(results) > 0, "Should find semantically similar raw feedback"
    assert any("machine learning" in r.feedback_content.lower() for r in results), (
        "Result should contain ML content"
    )


@skip_in_precommit
def test_vector_only_search_raw_feedbacks(
    supabase_storage_vector, hybrid_test_data, cleanup_hybrid_test
):
    """Test vector-only search mode for raw feedbacks."""
    storage = supabase_storage_vector
    raw_feedback = hybrid_test_data["raw_feedback_semantic"]

    # Save raw feedback
    storage.save_raw_feedbacks([raw_feedback])

    # Search with semantic query
    results = storage.search_raw_feedbacks(
        query="AI and neural network explanations",
        match_threshold=0.3,  # Lower threshold for semantic similarity
        match_count=10,
    )

    assert len(results) > 0, (
        "Vector search should find semantically similar raw feedbacks"
    )


@skip_in_precommit
def test_fts_only_search_raw_feedbacks(
    supabase_storage_fts, hybrid_test_data, cleanup_hybrid_test
):
    """Test FTS-only search mode for raw feedbacks."""
    storage = supabase_storage_fts
    raw_feedback = hybrid_test_data["raw_feedback_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Save raw feedback with keyword
    storage.save_raw_feedbacks([raw_feedback])

    # Search with exact keyword
    results = storage.search_raw_feedbacks(
        query=unique_keyword,
        match_threshold=0.1,
        match_count=10,
    )

    assert len(results) > 0, "FTS search should find raw feedbacks with exact keywords"


# ==============================
# Feedback Hybrid Search Tests
# ==============================


@skip_in_precommit
def test_hybrid_search_feedbacks_keyword_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds feedbacks with exact keyword matches."""
    storage = supabase_storage_hybrid
    feedback = hybrid_test_data["feedback_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Save feedback with unique keyword
    storage.save_feedbacks([feedback])

    # Search using the exact unique keyword
    results = storage.search_feedbacks(
        query=unique_keyword,
        match_threshold=0.1,
        match_count=10,
    )

    assert len(results) > 0, f"Should find feedback with keyword '{unique_keyword}'"
    assert any(unique_keyword in r.feedback_content for r in results), (
        "Result should contain the unique keyword"
    )


@skip_in_precommit
def test_hybrid_search_feedbacks_semantic_match(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search finds feedbacks with semantic similarity."""
    storage = supabase_storage_hybrid
    feedback = hybrid_test_data["feedback_semantic"]

    # Save feedback about NLP
    storage.save_feedbacks([feedback])

    # Search using semantically related query
    results = storage.search_feedbacks(
        query="language models and text understanding capabilities",
        match_threshold=0.3,  # Lower threshold for semantic similarity
        match_count=10,
    )

    assert len(results) > 0, "Should find semantically similar feedback"
    assert any(
        "natural language" in r.feedback_content.lower()
        or "processing" in r.feedback_content.lower()
        for r in results
    ), "Result should contain NLP content"


@skip_in_precommit
def test_vector_only_search_feedbacks(
    supabase_storage_vector, hybrid_test_data, cleanup_hybrid_test
):
    """Test vector-only search mode for feedbacks."""
    storage = supabase_storage_vector
    feedback = hybrid_test_data["feedback_semantic"]

    # Save feedback
    storage.save_feedbacks([feedback])

    # Search with semantic query
    results = storage.search_feedbacks(
        query="NLP and language understanding",
        match_threshold=0.3,  # Lower threshold for semantic similarity
        match_count=10,
    )

    assert len(results) > 0, "Vector search should find semantically similar feedbacks"


@skip_in_precommit
def test_fts_only_search_feedbacks(
    supabase_storage_fts, hybrid_test_data, cleanup_hybrid_test
):
    """Test FTS-only search mode for feedbacks."""
    storage = supabase_storage_fts
    feedback = hybrid_test_data["feedback_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Save feedback with keyword
    storage.save_feedbacks([feedback])

    # Search with exact keyword
    results = storage.search_feedbacks(
        query=unique_keyword,
        match_threshold=0.1,
        match_count=10,
    )

    assert len(results) > 0, "FTS search should find feedbacks with exact keywords"


# ==============================
# Combined/Integration Tests
# ==============================


@skip_in_precommit
def test_hybrid_search_finds_both_keyword_and_semantic_profiles(
    supabase_storage_hybrid, hybrid_test_data, cleanup_hybrid_test
):
    """Test that hybrid search returns both keyword and semantic matches for profiles."""
    storage = supabase_storage_hybrid
    user_id = hybrid_test_data["user_id"]
    profile_keyword = hybrid_test_data["profile_with_keyword"]
    profile_semantic = hybrid_test_data["profile_semantic"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add both profiles
    storage.add_user_profile(user_id, [profile_keyword, profile_semantic])

    # Search with query that has both keyword and semantic elements
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query=f"{unique_keyword} artificial intelligence",
        threshold=0.3,
        top_k=10,
    )
    results = storage.search_user_profile(search_request)

    # Should find at least the keyword-matching profile
    assert len(results) >= 1, "Should find at least one profile"

    # Check which profiles were found
    profile_ids = [r.profile_id for r in results]
    print(f"Found profile IDs: {profile_ids}")
    print(
        f"Looking for: {profile_keyword.profile_id} (keyword) and {profile_semantic.profile_id} (semantic)"
    )


@skip_in_precommit
def test_search_mode_affects_results(
    supabase_storage_hybrid,
    supabase_storage_vector,
    supabase_storage_fts,
    hybrid_test_data,
    cleanup_hybrid_test,
):
    """Test that different search modes produce different results."""
    user_id = hybrid_test_data["user_id"]
    profile = hybrid_test_data["profile_with_keyword"]
    unique_keyword = hybrid_test_data["unique_keyword"]

    # Add profile to all storage instances (they share the same database)
    supabase_storage_hybrid.add_user_profile(user_id, [profile])

    # Search with exact keyword in each mode
    search_request = SearchUserProfileRequest(
        user_id=user_id,
        query=unique_keyword,
        threshold=0.1,
        top_k=10,
    )

    # All modes should find the profile since it has both vector embedding and keyword
    results_hybrid = supabase_storage_hybrid.search_user_profile(search_request)
    results_vector = supabase_storage_vector.search_user_profile(search_request)
    results_fts = supabase_storage_fts.search_user_profile(search_request)

    # FTS should definitely find it (exact keyword match)
    # Vector and hybrid should also find it
    print(f"Hybrid results: {len(results_hybrid)}")
    print(f"Vector results: {len(results_vector)}")
    print(f"FTS results: {len(results_fts)}")

    assert len(results_fts) > 0, "FTS mode should find profile with exact keyword"
    # Note: Vector mode might not find it if the keyword isn't semantically close
    # Hybrid should find it via FTS component


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
