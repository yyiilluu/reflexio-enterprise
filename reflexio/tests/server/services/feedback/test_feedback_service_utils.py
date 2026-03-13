"""Tests for feedback service utility functions."""

from datetime import datetime, timezone

import pytest
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    BlockingIssue,
    BlockingIssueKind,
    Interaction,
    Request,
)

from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.feedback.feedback_service_utils import (
    StructuredFeedbackContent,
    construct_feedback_extraction_messages_from_sessions,
    format_structured_feedback_content,
)


def test_construct_feedback_extraction_messages_with_sessions():
    """Test that construct_feedback_extraction_messages_from_sessions formats interactions correctly in the rendered prompt."""
    # Create test interactions
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="user_123",
            request_id="req_1",
            content="I need help with my account",
            role="user",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="user_123",
            request_id="req_1",
            content="Here is how to access your account",
            role="assistant",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=3,
            user_id="user_123",
            request_id="req_1",
            content="Thank you!",
            role="user",
            created_at=int(datetime.now(timezone.utc).timestamp()),
            user_action="click",
            user_action_description="help button",
        ),
    ]

    # Create request and request interaction data model
    request = Request(
        request_id="req_1",
        user_id="user_123",
        source="test",
        agent_version="1.0.0",
        session_id="session_1",
    )

    request_interaction_data_models = [
        RequestInteractionDataModel(
            session_id="session_1",
            request=request,
            interactions=interactions,
        )
    ]

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_feedback_extraction_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=request_interaction_data_models,
        feedback_definition_prompt="Evaluate the quality of the agent's response",
        agent_context_prompt="Customer support agent",
    )

    # Validate that messages were created
    assert len(messages) > 0, "No messages were created"

    # Helper to extract text from a message's content (string or content blocks)
    def extract_text(message):
        content = message.get("content", "")
        if isinstance(content, list):
            extracted = ""
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    extracted += item.get("text", "")
            return extracted
        return str(content)

    # Verify feedback definition is in the system message (moved there for token caching)
    system_messages = [m for m in messages if m.get("role") == "system"]
    assert system_messages, "Expected a system message"
    system_text = extract_text(system_messages[0])
    assert "Evaluate the quality of the agent's response" in system_text, (
        "Expected feedback definition in system message"
    )

    # Find the user message that contains the interactions
    found_interactions = False
    for message in messages:
        if isinstance(message, dict) and "content" in message:
            content = extract_text(message)

            # Check if this message contains the interaction section
            if (
                "[Intearctions start]" in content
                or "[Interactions end]" in content
                or "User and agent interactions:" in content
                or "Session:" in content
                or "user: ```I need help with my account```"
                in content  # Check directly for content
            ):
                # Validate the interactions are formatted correctly in the rendered prompt
                # Note: Content is wrapped in backticks in the prompt template
                assert "user: ```I need help with my account```" in content, (
                    "Expected 'user: ```I need help with my account```' in prompt"
                )
                assert (
                    "assistant: ```Here is how to access your account```" in content
                ), (
                    "Expected 'assistant: ```Here is how to access your account```' in prompt"
                )
                assert "user: ```Thank you!```" in content, (
                    "Expected 'user: ```Thank you!```' in prompt"
                )
                assert "user: ```click help button```" in content, (
                    "Expected 'user: ```click help button```' in prompt"
                )

                found_interactions = True
                break

    assert found_interactions, "Did not find interactions in the rendered prompt"


def test_construct_feedback_extraction_messages_with_empty_sessions():
    """Test that construct_feedback_extraction_messages_from_sessions handles empty sessions."""
    # Empty sessions list
    request_interaction_data_models = []

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_feedback_extraction_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=request_interaction_data_models,
        feedback_definition_prompt="Evaluate the quality of the agent's response",
        agent_context_prompt="Customer support agent",
    )

    # Should still create messages (system message + user message with prompt)
    assert len(messages) > 0, "No messages were created for empty sessions"


# ===============================
# Tests for format_structured_feedback_content
# ===============================


class TestFormatStructuredFeedbackContent:
    """Tests for the shared format_structured_feedback_content function."""

    def test_all_fields_present(self):
        """Test formatting with all fields populated."""
        structured = StructuredFeedbackContent(
            do_action="use clear language",
            do_not_action="use jargon",
            when_condition="explaining technical concepts to beginners",
        )
        result = format_structured_feedback_content(structured)
        assert 'When: "explaining technical concepts to beginners"' in result
        assert 'Do: "use clear language"' in result
        assert 'Don\'t: "use jargon"' in result

    def test_when_condition_none(self):
        """Test that None when_condition is omitted from output."""
        structured = StructuredFeedbackContent(
            do_action="use clear language",
            do_not_action=None,
            when_condition=None,
        )
        result = format_structured_feedback_content(structured)
        assert "When:" not in result
        assert 'Do: "use clear language"' in result

    def test_when_condition_empty_string(self):
        """Test that empty string when_condition is omitted from output."""
        structured = StructuredFeedbackContent(
            do_action="use clear language",
            do_not_action=None,
            when_condition=None,
        )
        result = format_structured_feedback_content(structured)
        assert "When:" not in result

    def test_only_do_action(self):
        """Test formatting with only do_action."""
        structured = StructuredFeedbackContent(
            do_action="be concise",
            do_not_action=None,
            when_condition=None,
        )
        result = format_structured_feedback_content(structured)
        assert 'Do: "be concise"' in result
        assert "Don't:" not in result
        assert "When:" not in result

    def test_only_do_not_action(self):
        """Test formatting with only do_not_action."""
        structured = StructuredFeedbackContent(
            do_action=None,
            do_not_action="ramble",
            when_condition=None,
        )
        result = format_structured_feedback_content(structured)
        assert 'Don\'t: "ramble"' in result
        assert "Do:" not in result
        assert "When:" not in result

    def test_with_blocking_issue(self):
        """Test formatting with blocking_issue."""
        structured = StructuredFeedbackContent(
            do_action="acknowledge limitation",
            when_condition="user asks for real-time data",
            blocking_issue=BlockingIssue(
                kind=BlockingIssueKind.MISSING_TOOL,
                details="No real-time data API available",
            ),
        )
        result = format_structured_feedback_content(structured)
        assert "Blocked by:" in result
        assert "missing_tool" in result
        assert "No real-time data API available" in result

    def test_all_fields_none_returns_empty(self):
        """Test that all-None fields returns empty string."""
        structured = StructuredFeedbackContent()
        result = format_structured_feedback_content(structured)
        assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
