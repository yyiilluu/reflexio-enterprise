"""Tests for service_utils module."""

from datetime import UTC, datetime

import pytest
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
    UserActionType,
)

from reflexio.server.services.service_utils import (
    extract_json_from_string,
    format_interactions_to_history_string,
    format_messages_for_logging,
    format_sessions_to_history_string,
)


def test_format_interactions_to_history_string_with_content():
    """Test formatting interactions with text content."""
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            request_id="test_request",
            content="I love Italian food",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.NONE,
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="test_user",
            request_id="test_request",
            content="I also enjoy sushi",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.NONE,
            user_action_description="",
        ),
    ]

    result = format_interactions_to_history_string(interactions)
    expected = "user: ```I love Italian food```\nuser: ```I also enjoy sushi```"
    assert result == expected


def test_format_interactions_to_history_string_with_actions():
    """Test formatting interactions with user actions."""
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            request_id="test_request",
            content="",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="menu item",
        ),
        Interaction(
            interaction_id=2,
            user_id="test_user",
            request_id="test_request",
            content="",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.SCROLL,
            user_action_description="to bottom",
        ),
    ]

    result = format_interactions_to_history_string(interactions)
    expected = "user: ```click menu item```\nuser: ```scroll to bottom```"
    assert result == expected


def test_format_interactions_to_history_string_mixed():
    """Test formatting interactions with both content and actions."""
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            request_id="test_request",
            content="I love sushi",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.NONE,
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="test_user",
            request_id="test_request",
            content="",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="menu item",
        ),
    ]

    result = format_interactions_to_history_string(interactions)
    expected = "user: ```I love sushi```\nuser: ```click menu item```"
    assert result == expected


def test_format_interactions_to_history_string_with_content_and_action():
    """Test formatting interaction with both content and action in same interaction."""
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            request_id="test_request",
            content="I love sushi",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.CLICK,
            user_action_description="sushi restaurant",
        ),
    ]

    result = format_interactions_to_history_string(interactions)
    expected = "user: ```I love sushi```\nuser: ```click sushi restaurant```"
    assert result == expected


def test_format_interactions_to_history_string_empty():
    """Test formatting empty interactions list."""
    interactions = []
    result = format_interactions_to_history_string(interactions)
    assert result == ""


def test_format_interactions_to_history_string_multiple_roles():
    """Test formatting interactions with different roles."""
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            request_id="test_request",
            content="Can you help me?",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.NONE,
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="test_user",
            request_id="test_request",
            content="Of course, I can help!",
            role="assistant",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=UserActionType.NONE,
            user_action_description="",
        ),
    ]

    result = format_interactions_to_history_string(interactions)
    expected = "user: ```Can you help me?```\nassistant: ```Of course, I can help!```"
    assert result == expected


def _create_request(request_id: str, created_at: int) -> Request:
    """Helper function to create a Request object for testing."""
    return Request(
        request_id=request_id,
        user_id="test_user",
        created_at=created_at,
        app_id="test_app",
        agent_id="test_agent",
    )


def _create_interaction(
    interaction_id: int, content: str, role: str, created_at: int
) -> Interaction:
    """Helper function to create an Interaction object for testing."""
    return Interaction(
        interaction_id=interaction_id,
        user_id="test_user",
        request_id="test_request",
        content=content,
        role=role,
        created_at=created_at,
        user_action=UserActionType.NONE,
        user_action_description="",
    )


def test_format_sessions_to_history_string_empty():
    """Test formatting empty sessions list."""
    result = format_sessions_to_history_string([])
    assert result == ""


def test_format_sessions_to_history_string_single_group():
    """Test formatting a single session."""
    base_time = int(datetime.now(UTC).timestamp())

    session_data = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_1", base_time),
        interactions=[
            _create_interaction(1, "Hello", "user", base_time),
            _create_interaction(2, "Hi there!", "assistant", base_time + 1),
        ],
    )

    result = format_sessions_to_history_string([session_data])
    expected = "=== Session: group_1 ===\nuser: ```Hello```\nassistant: ```Hi there!```"
    assert result == expected


def test_format_sessions_to_history_string_consolidates_same_group():
    """Test that multiple requests with the same group name are consolidated under one header."""
    base_time = int(datetime.now(UTC).timestamp())

    # Three separate requests, all with the same session_id name
    session_id_1 = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_1", base_time),
        interactions=[
            _create_interaction(1, "First message", "user", base_time),
            _create_interaction(2, "First response", "assistant", base_time + 1),
        ],
    )

    session_id_2 = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_2", base_time + 100),
        interactions=[
            _create_interaction(3, "Second message", "user", base_time + 100),
            _create_interaction(4, "Second response", "assistant", base_time + 101),
        ],
    )

    session_id_3 = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_3", base_time + 200),
        interactions=[
            _create_interaction(5, "Third message", "user", base_time + 200),
            _create_interaction(6, "Third response", "assistant", base_time + 201),
        ],
    )

    result = format_sessions_to_history_string(
        [session_id_1, session_id_2, session_id_3]
    )

    # All interactions should be under a single header
    expected = (
        "=== Session: group_1 ===\n"
        "user: ```First message```\n"
        "assistant: ```First response```\n"
        "user: ```Second message```\n"
        "assistant: ```Second response```\n"
        "user: ```Third message```\n"
        "assistant: ```Third response```"
    )
    assert result == expected


def test_format_sessions_to_history_string_multiple_groups():
    """Test formatting multiple different sessions."""
    base_time = int(datetime.now(UTC).timestamp())

    group_a = RequestInteractionDataModel(
        session_id="session_a",
        request=_create_request("req_a", base_time),
        interactions=[
            _create_interaction(1, "Message A", "user", base_time),
        ],
    )

    group_b = RequestInteractionDataModel(
        session_id="session_b",
        request=_create_request("req_b", base_time + 100),
        interactions=[
            _create_interaction(2, "Message B", "user", base_time + 100),
        ],
    )

    result = format_sessions_to_history_string([group_a, group_b])
    expected = (
        "=== Session: session_a ===\n"
        "user: ```Message A```\n\n"
        "=== Session: session_b ===\n"
        "user: ```Message B```"
    )
    assert result == expected


def test_format_sessions_to_history_string_mixed_groups():
    """Test multiple sessions with some sharing the same name."""
    base_time = int(datetime.now(UTC).timestamp())

    # Two requests in group_1
    group_1_req_1 = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_1", base_time),
        interactions=[
            _create_interaction(1, "Group 1 - Request 1", "user", base_time),
        ],
    )

    group_1_req_2 = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_2", base_time + 100),
        interactions=[
            _create_interaction(2, "Group 1 - Request 2", "user", base_time + 100),
        ],
    )

    # One request in group_2 (comes between the two group_1 requests in terms of time)
    group_2_req = RequestInteractionDataModel(
        session_id="group_2",
        request=_create_request("req_3", base_time + 50),
        interactions=[
            _create_interaction(3, "Group 2 - Request 1", "user", base_time + 50),
        ],
    )

    result = format_sessions_to_history_string(
        [group_1_req_1, group_2_req, group_1_req_2]
    )

    # Groups should be sorted by earliest request timestamp
    # group_1 (base_time) should come before group_2 (base_time + 50)
    expected = (
        "=== Session: group_1 ===\n"
        "user: ```Group 1 - Request 1```\n"
        "user: ```Group 1 - Request 2```\n\n"
        "=== Session: group_2 ===\n"
        "user: ```Group 2 - Request 1```"
    )
    assert result == expected


def test_format_sessions_to_history_string_preserves_order_within_group():
    """Test that requests within the same group are ordered by created_at."""
    base_time = int(datetime.now(UTC).timestamp())

    # Create requests out of order
    late_request = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_late", base_time + 200),
        interactions=[
            _create_interaction(3, "Late message", "user", base_time + 200),
        ],
    )

    early_request = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_early", base_time),
        interactions=[
            _create_interaction(1, "Early message", "user", base_time),
        ],
    )

    middle_request = RequestInteractionDataModel(
        session_id="group_1",
        request=_create_request("req_middle", base_time + 100),
        interactions=[
            _create_interaction(2, "Middle message", "user", base_time + 100),
        ],
    )

    # Pass them out of order
    result = format_sessions_to_history_string(
        [late_request, early_request, middle_request]
    )

    # Should be sorted by created_at within the group
    expected = (
        "=== Session: group_1 ===\n"
        "user: ```Early message```\n"
        "user: ```Middle message```\n"
        "user: ```Late message```"
    )
    assert result == expected


# ===============================
# Tests for fix_unescaped_inner_quotes (via extract_json_from_string)
# ===============================


def test_fix_unescaped_inner_quotes_repairs_apostrophe():
    """Test that inner double-quotes between word chars are fixed (line 375)."""
    # The LLM returned customer"s instead of customer's inside a JSON value
    text = '{"feedback": "The customer"s request was handled well"}'
    result = extract_json_from_string(text)

    assert result == {"feedback": "The customer's request was handled well"}


def test_fix_unescaped_inner_quotes_multiple():
    """Test multiple inner quotes are all repaired."""
    text = '{"a": "it"s fine", "b": "she"s done"}'
    result = extract_json_from_string(text)

    assert result == {"a": "it's fine", "b": "she's done"}


# ===============================
# Tests for extract_json_from_string: ast.literal_eval fallback
# ===============================


def test_extract_json_literal_eval_fallback_single_quotes():
    """Test ast.literal_eval fallback for Python-style dicts with single quotes (lines 391-395)."""
    text = "{'key': 'value', 'count': 42}"
    result = extract_json_from_string(text)

    assert result == {"key": "value", "count": 42}


def test_extract_json_literal_eval_fallback_in_code_block():
    """Test ast.literal_eval fallback when inside a code block with single quotes."""
    text = "```json\n{'do_action': 'be polite', 'when_condition': 'greeting'}\n```"
    result = extract_json_from_string(text)

    assert result == {"do_action": "be polite", "when_condition": "greeting"}


# ===============================
# Tests for extract_json_from_string: warnings on parse failure
# ===============================


def test_extract_json_code_block_warning_then_braces_fallback():
    """Test JSON parse warning from code block (lines 409-410) followed by braces fallback."""
    # Code block has invalid JSON, but the text outside also contains valid JSON
    # The braces extraction will find the valid JSON after code block fails
    text = '```json\nnot valid json at all\n```\n\n{"fallback": true}'
    result = extract_json_from_string(text)

    assert result == {"fallback": True}


def test_extract_json_braces_warning_returns_empty():
    """Test JSON parse warning from braces (lines 420-421) returns empty dict."""
    text = "{this is definitely not json}"
    result = extract_json_from_string(text)

    assert result == {}


def test_extract_json_no_json_at_all():
    """Test that extract_json_from_string returns empty dict when no JSON anywhere."""
    text = "This is plain text with no JSON content"
    result = extract_json_from_string(text)

    assert result == {}


def test_extract_json_python_booleans():
    """Test that Python-style True/False/None are converted to JSON equivalents."""
    text = '{"active": True, "deleted": False, "value": None}'
    result = extract_json_from_string(text)

    assert result == {"active": True, "deleted": False, "value": None}


# ===============================
# Tests for format_messages_for_logging: multimodal content/images
# ===============================


def test_format_messages_for_logging_multimodal_with_image_url():
    """Test format_messages_for_logging with multimodal content including image URL (lines 473-476)."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What do you see?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/img.png"},
                },
            ],
        }
    ]

    result = format_messages_for_logging(messages)

    assert "Message 1:" in result
    assert "role: user" in result
    assert "type: text" in result
    assert "What do you see?" in result
    assert "image_url" in result
    assert "https://example.com/img.png" in result


def test_format_messages_for_logging_multimodal_with_base64():
    """Test format_messages_for_logging with base64-encoded image content."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,/9j/abc123"},
                },
            ],
        }
    ]

    result = format_messages_for_logging(messages)

    assert "Describe this image" in result
    assert "image_url" in result


def test_format_messages_for_logging_string_content():
    """Test format_messages_for_logging with simple string content."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!\nHow are you?"},
    ]

    result = format_messages_for_logging(messages)

    assert "Message 1:" in result
    assert "role: system" in result
    assert "You are a helpful assistant." in result
    assert "Message 2:" in result
    assert "Hello!" in result
    assert "How are you?" in result


def test_format_messages_for_logging_non_standard_content():
    """Test format_messages_for_logging with non-string, non-list content (lines 475-476)."""
    messages = [
        {"role": "user", "content": 42},
    ]

    result = format_messages_for_logging(messages)

    assert "content: 42" in result


def test_format_messages_for_logging_empty_messages():
    """Test format_messages_for_logging with empty message list."""
    result = format_messages_for_logging([])

    assert result == ""


def test_format_messages_for_logging_multimodal_non_dict_items():
    """Test format_messages_for_logging with non-dict items in content list (line 473)."""
    messages = [
        {
            "role": "user",
            "content": [
                "plain string item",
            ],
        }
    ]

    result = format_messages_for_logging(messages)

    assert "plain string item" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
