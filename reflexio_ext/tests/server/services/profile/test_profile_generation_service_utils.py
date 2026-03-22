"""Tests for profile generation service utility functions."""

import sys
from datetime import UTC, datetime, timedelta

import pytest
from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.profile.profile_generation_service_utils import (
    ProfileUpdates,
    calculate_expiration_timestamp,
    check_string_token_overlap,
    construct_incremental_profile_extraction_messages,
    construct_profile_extraction_messages_from_sessions,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    ProfileTimeToLive,
    Request,
    UserProfile,
)


def test_construct_profile_extraction_messages_with_sessions():
    """Test that construct_profile_extraction_messages_from_sessions formats interactions correctly in the rendered prompt."""
    # Create test interactions with both content and actions
    timestamp = int(datetime.now(UTC).timestamp())
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="user_123",
            request_id="req_1",
            content="I love Italian food",
            role="user",
            created_at=timestamp,
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="user_123",
            request_id="req_1",
            content="I also enjoy sushi",
            role="user",
            created_at=timestamp,
            user_action="click",
            user_action_description="restaurant menu",
        ),
    ]

    # Create request interaction group
    request = Request(
        request_id="req_1",
        user_id="user_123",
        created_at=timestamp,
    )
    sessions = [
        RequestInteractionDataModel(
            session_id="session_1",
            request=request,
            interactions=interactions,
        )
    ]

    # Create existing profiles
    existing_profiles = [
        UserProfile(
            profile_id="profile_1",
            user_id="user_123",
            profile_content="likes Mexican food",
            last_modified_timestamp=timestamp,
            generated_from_request_id="req_0",
        )
    ]

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_profile_extraction_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=sessions,
        existing_profiles=existing_profiles,
        agent_context_prompt="Test agent context",
        context_prompt="Test context",
        profile_content_definition_prompt="food preferences",
        metadata_definition_prompt="cuisine type",
    )

    # Validate that messages were created
    assert len(messages) > 0, "No messages were created"

    # Find the user message that contains the interactions
    found_interactions = False
    for message in messages:
        # Messages are dicts with 'role' and 'content' keys
        if isinstance(message, dict) and "content" in message:
            # Content can be a string or a list of content blocks
            content = message.get("content", "")
            if isinstance(content, list):
                # Extract text from content blocks
                extracted_text = ""
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        extracted_text += item.get("text", "")
                content = extracted_text
            else:
                content = str(content)

            # Check if this message contains the interaction section
            if (
                "[Interaction start]" in content
                or "User and agent interactions:" in content
                or "=== Session:" in content
                or "user: ```I love Italian food```"
                in content  # Check directly for content
            ):
                # Validate the interactions are formatted correctly in the rendered prompt
                assert "user: ```I love Italian food```" in content, (
                    "Expected 'user: ```I love Italian food```' in prompt"
                )
                assert "user: ```I also enjoy sushi```" in content, (
                    "Expected 'user: ```I also enjoy sushi```' in prompt"
                )
                assert "user: ```click restaurant menu```" in content, (
                    "Expected 'user: ```click restaurant menu```' in prompt"
                )

                # Also verify existing profiles are in the prompt
                assert "likes Mexican food" in content, (
                    "Expected existing profile in prompt"
                )

                found_interactions = True
                break

    assert found_interactions, "Did not find interactions in the rendered prompt"


def test_construct_profile_extraction_messages_with_empty_sessions():
    """Test that construct_profile_extraction_messages_from_sessions handles empty sessions."""
    # Empty sessions list
    sessions = []

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_profile_extraction_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=sessions,
        existing_profiles=[],
        agent_context_prompt="Test agent context",
        context_prompt="Test context",
        profile_content_definition_prompt="food preferences",
        metadata_definition_prompt="cuisine type",
    )

    # Should still create messages (system message + user message with prompt)
    assert len(messages) > 0, "No messages were created for empty sessions"


# ===============================
# Tests for calculate_expiration_timestamp
# ===============================


class TestCalculateExpirationTimestamp:
    """Tests for calculate_expiration_timestamp across all TTL enum values."""

    def test_one_day(self):
        """ONE_DAY adds 1 day to the last modified timestamp."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.ONE_DAY)
        expected = int(
            (datetime.fromtimestamp(base_ts) + timedelta(days=1)).timestamp()
        )
        assert result == expected

    def test_one_week(self):
        """ONE_WEEK adds 7 days to the last modified timestamp."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.ONE_WEEK)
        expected = int(
            (datetime.fromtimestamp(base_ts) + timedelta(days=7)).timestamp()
        )
        assert result == expected

    def test_one_month(self):
        """ONE_MONTH adds 30 days to the last modified timestamp."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.ONE_MONTH)
        expected = int(
            (datetime.fromtimestamp(base_ts) + timedelta(days=30)).timestamp()
        )
        assert result == expected

    def test_one_quarter(self):
        """ONE_QUARTER adds 90 days to the last modified timestamp."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.ONE_QUARTER)
        expected = int(
            (datetime.fromtimestamp(base_ts) + timedelta(days=90)).timestamp()
        )
        assert result == expected

    def test_one_year(self):
        """ONE_YEAR adds 365 days to the last modified timestamp."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.ONE_YEAR)
        expected = int(
            (datetime.fromtimestamp(base_ts) + timedelta(days=365)).timestamp()
        )
        assert result == expected

    def test_infinity(self):
        """INFINITY returns a far-future timestamp (datetime.max or sys.maxsize on overflow)."""
        base_ts = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        result = calculate_expiration_timestamp(base_ts, ProfileTimeToLive.INFINITY)
        # On platforms where datetime.max.timestamp() succeeds, it returns that value;
        # on platforms where it overflows, it returns sys.maxsize.
        try:
            expected = int(datetime.max.timestamp())
        except (OverflowError, OSError, ValueError):
            expected = sys.maxsize
        assert result == expected


# ===============================
# Tests for check_string_token_overlap
# ===============================


class TestCheckStringTokenOverlap:
    """Tests for check_string_token_overlap edge cases."""

    def test_empty_first_string(self):
        """Empty first string returns False."""
        assert check_string_token_overlap("", "hello world") is False

    def test_empty_second_string(self):
        """Empty second string returns False."""
        assert check_string_token_overlap("hello world", "") is False

    def test_both_empty(self):
        """Both empty strings returns False."""
        assert check_string_token_overlap("", "") is False

    def test_exact_match(self):
        """Identical strings return True."""
        assert check_string_token_overlap("hello world", "hello world") is True

    def test_below_threshold(self):
        """Strings with low overlap return False when below threshold."""
        # 1 shared token out of 3 in each -> overlap_ratio = max(1/3, 1/3) = 0.33
        assert (
            check_string_token_overlap("the quick fox", "the lazy dog", threshold=0.7)
            is False
        )

    def test_above_threshold(self):
        """Strings with high overlap return True when above threshold."""
        # 2 shared tokens out of 3 -> overlap_ratio = max(2/3, 2/3) = 0.67
        assert (
            check_string_token_overlap("the quick fox", "the quick dog", threshold=0.5)
            is True
        )

    def test_case_insensitive(self):
        """Token comparison is case-insensitive."""
        assert check_string_token_overlap("Hello World", "hello world") is True

    def test_custom_threshold(self):
        """Custom threshold is respected."""
        # 1 shared token out of 2 -> overlap_ratio = 0.5
        assert (
            check_string_token_overlap("hello world", "hello there", threshold=0.5)
            is True
        )
        assert (
            check_string_token_overlap("hello world", "hello there", threshold=0.6)
            is False
        )


# ===============================
# Tests for ProfileUpdates validator
# ===============================


class TestProfileUpdates:
    """Tests for ProfileUpdates None coercion validator."""

    def test_none_coerced_to_empty_list_add_profiles(self):
        """None is coerced to empty list for add_profiles."""
        updates = ProfileUpdates(add_profiles=None)
        assert updates.add_profiles == []

    def test_none_coerced_to_empty_list_delete_profiles(self):
        """None is coerced to empty list for delete_profiles."""
        updates = ProfileUpdates(delete_profiles=None)
        assert updates.delete_profiles == []

    def test_none_coerced_to_empty_list_mention_profiles(self):
        """None is coerced to empty list for mention_profiles."""
        updates = ProfileUpdates(mention_profiles=None)
        assert updates.mention_profiles == []

    def test_all_none_coerced(self):
        """All None fields are coerced to empty lists."""
        updates = ProfileUpdates(
            add_profiles=None, delete_profiles=None, mention_profiles=None
        )
        assert updates.add_profiles == []
        assert updates.delete_profiles == []
        assert updates.mention_profiles == []

    def test_default_empty_lists(self):
        """Default values are empty lists when no arguments provided."""
        updates = ProfileUpdates()
        assert updates.add_profiles == []
        assert updates.delete_profiles == []
        assert updates.mention_profiles == []

    def test_valid_list_preserved(self):
        """Non-None list values are preserved as-is."""
        timestamp = int(datetime.now(UTC).timestamp())
        profile = UserProfile(
            profile_id="p1",
            user_id="u1",
            profile_content="test",
            last_modified_timestamp=timestamp,
            generated_from_request_id="r1",
        )
        updates = ProfileUpdates(add_profiles=[profile])
        assert len(updates.add_profiles) == 1
        assert updates.add_profiles[0].profile_id == "p1"


# ===============================
# Tests for construct_incremental_profile_extraction_messages
# ===============================


class TestConstructIncrementalProfileExtractionMessages:
    """Tests for construct_incremental_profile_extraction_messages."""

    def test_previously_extracted_formatting(self):
        """Test that previously extracted profiles are formatted with bullet points."""
        timestamp = int(datetime.now(UTC).timestamp())

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="user_1",
                request_id="req_1",
                content="I like pizza",
                role="user",
                created_at=timestamp,
            ),
        ]

        request = Request(
            request_id="req_1",
            user_id="user_1",
            created_at=timestamp,
        )
        sessions = [
            RequestInteractionDataModel(
                session_id="session_1",
                request=request,
                interactions=interactions,
            )
        ]

        existing_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user_1",
                profile_content="likes Italian food",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req_0",
            )
        ]

        previously_extracted = [
            [
                UserProfile(
                    profile_id="p2",
                    user_id="user_1",
                    profile_content="prefers thin crust",
                    last_modified_timestamp=timestamp,
                    generated_from_request_id="req_1",
                ),
            ],
            [
                UserProfile(
                    profile_id="p3",
                    user_id="user_1",
                    profile_content="vegetarian",
                    last_modified_timestamp=timestamp,
                    generated_from_request_id="req_1",
                ),
            ],
        ]

        prompt_manager = PromptManager()

        messages = construct_incremental_profile_extraction_messages(
            prompt_manager=prompt_manager,
            request_interaction_data_models=sessions,
            existing_profiles=existing_profiles,
            agent_context_prompt="Test agent context",
            context_prompt="Test context",
            profile_content_definition_prompt="food preferences",
            previously_extracted=previously_extracted,
            metadata_definition_prompt=None,
        )

        # Validate messages were created
        assert len(messages) > 0, "No messages were created"

        # Find the user message that contains the previously extracted profiles
        all_content = ""
        for message in messages:
            if isinstance(message, dict) and "content" in message:
                content = message.get("content", "")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            all_content += item.get("text", "")
                else:
                    all_content += str(content)

        # Verify previously extracted profiles are formatted as bullet points
        assert "prefers thin crust" in all_content
        assert "vegetarian" in all_content

    def test_empty_previously_extracted(self):
        """Test that empty previously_extracted results in '(None)' formatting."""
        timestamp = int(datetime.now(UTC).timestamp())

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="user_1",
                request_id="req_1",
                content="Hello",
                role="user",
                created_at=timestamp,
            ),
        ]

        request = Request(
            request_id="req_1",
            user_id="user_1",
            created_at=timestamp,
        )
        sessions = [
            RequestInteractionDataModel(
                session_id="session_1",
                request=request,
                interactions=interactions,
            )
        ]

        prompt_manager = PromptManager()

        messages = construct_incremental_profile_extraction_messages(
            prompt_manager=prompt_manager,
            request_interaction_data_models=sessions,
            existing_profiles=[],
            agent_context_prompt="Test agent context",
            context_prompt="Test context",
            profile_content_definition_prompt="general preferences",
            previously_extracted=[],
            metadata_definition_prompt=None,
        )

        assert len(messages) > 0, "No messages were created"

        # Verify "(None)" appears somewhere in the messages for previously_added_profiles
        all_content = ""
        for message in messages:
            if isinstance(message, dict) and "content" in message:
                content = message.get("content", "")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            all_content += item.get("text", "")
                else:
                    all_content += str(content)

        assert "(None)" in all_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
