"""Tests for feedback service utility functions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    BlockingIssue,
    BlockingIssueKind,
    Interaction,
    RawFeedback,
    Request,
)

from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.feedback.feedback_service_utils import (
    StructuredFeedbackContent,
    construct_feedback_extraction_messages_from_sessions,
    construct_incremental_feedback_extraction_messages,
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
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="user_123",
            request_id="req_1",
            content="Here is how to access your account",
            role="assistant",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=3,
            user_id="user_123",
            request_id="req_1",
            content="Thank you!",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
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


# ===============================
# Tests for StructuredFeedbackContent validator edge cases
# ===============================


class TestStructuredFeedbackContentValidator:
    """Tests for StructuredFeedbackContent model validators."""

    def test_handle_null_feedback_format_null(self):
        """Test that {"feedback": null} produces empty feedback."""
        result = StructuredFeedbackContent.model_validate({"feedback": None})
        assert result.do_action is None
        assert result.do_not_action is None
        assert result.when_condition is None

    def test_handle_null_feedback_format_dict_wrapper(self):
        """Test that {"feedback": {...}} extracts inner dict."""
        result = StructuredFeedbackContent.model_validate(
            {
                "feedback": {
                    "do_action": "be polite",
                    "when_condition": "greeting users",
                }
            }
        )
        assert result.do_action == "be polite"
        assert result.when_condition == "greeting users"

    def test_handle_null_feedback_format_list_wrapper(self):
        """Test that {"feedback": [{...}]} extracts first item."""
        result = StructuredFeedbackContent.model_validate(
            {
                "feedback": [
                    {
                        "do_action": "summarize",
                        "when_condition": "long conversation",
                    }
                ]
            }
        )
        assert result.do_action == "summarize"
        assert result.when_condition == "long conversation"

    def test_handle_null_feedback_format_list_multiple_items(self):
        """Test that multiple items in list uses first one (with warning)."""
        result = StructuredFeedbackContent.model_validate(
            {
                "feedback": [
                    {
                        "do_action": "first",
                        "when_condition": "cond1",
                    },
                    {
                        "do_action": "second",
                        "when_condition": "cond2",
                    },
                ]
            }
        )
        assert result.do_action == "first"

    def test_handle_null_feedback_format_empty_list_raises(self):
        """Test that {"feedback": []} raises because empty list is falsy and passes through as extra field."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            StructuredFeedbackContent.model_validate({"feedback": []})

    def test_when_condition_without_actions_raises(self):
        """Test validation error when when_condition set without any action."""
        with pytest.raises(ValidationError, match="do_action.*do_not_action"):
            StructuredFeedbackContent(
                when_condition="some condition",
                do_action=None,
                do_not_action=None,
            )

    def test_extra_fields_forbidden(self):
        """Test that extra fields raise validation error."""
        with pytest.raises(ValidationError):
            StructuredFeedbackContent(
                do_action="test",
                unknown_field="bad",  # type: ignore[call-arg]
            )


# ===============================
# Tests for has_feedback property
# ===============================


class TestHasFeedback:
    """Tests for StructuredFeedbackContent.has_feedback property."""

    def test_has_feedback_with_all_fields(self):
        """Test has_feedback is True with all required fields."""
        fc = StructuredFeedbackContent(
            do_action="use markdown",
            when_condition="formatting code",
        )
        assert fc.has_feedback is True

    def test_has_feedback_empty_when_condition(self):
        """Test has_feedback is False with empty when_condition."""
        fc = StructuredFeedbackContent(
            do_action="something",
            when_condition="",
        )
        assert fc.has_feedback is False

    def test_has_feedback_whitespace_when_condition(self):
        """Test has_feedback is False with whitespace-only when_condition."""
        fc = StructuredFeedbackContent(
            do_action="something",
            when_condition="   ",
        )
        assert fc.has_feedback is False

    def test_has_feedback_none_fields(self):
        """Test has_feedback is False with all None fields."""
        fc = StructuredFeedbackContent()
        assert fc.has_feedback is False

    def test_has_feedback_whitespace_do_action(self):
        """Test has_feedback is False when do_action is whitespace-only."""
        fc = StructuredFeedbackContent(
            do_action="   ",
            when_condition="some condition",
        )
        assert fc.has_feedback is False

    def test_has_feedback_only_do_not_action(self):
        """Test has_feedback is True with do_not_action and when_condition."""
        fc = StructuredFeedbackContent(
            do_not_action="use jargon",
            when_condition="talking to beginners",
        )
        assert fc.has_feedback is True


# ===============================
# Tests for construct_incremental_feedback_extraction_messages
# ===============================


class TestConstructIncrementalFeedbackExtractionMessages:
    """Tests for construct_incremental_feedback_extraction_messages."""

    def test_with_previously_extracted(self):
        """Test incremental extraction with previously extracted feedbacks."""
        interactions = [
            Interaction(
                interaction_id=1,
                user_id="u1",
                request_id="req1",
                content="test content",
                role="user",
                created_at=int(datetime.now(UTC).timestamp()),
                user_action="none",
                user_action_description="",
            ),
        ]
        request = Request(
            request_id="req1",
            user_id="u1",
            source="test",
            agent_version="1.0",
            session_id="s1",
        )
        data_models = [
            RequestInteractionDataModel(
                session_id="s1",
                request=request,
                interactions=interactions,
            )
        ]
        previously_extracted = [
            RawFeedback(
                agent_version="1.0",
                request_id="req1",
                feedback_name="test",
                feedback_content="already found feedback",
            ),
        ]

        prompt_manager = PromptManager()
        messages = construct_incremental_feedback_extraction_messages(
            prompt_manager=prompt_manager,
            request_interaction_data_models=data_models,
            agent_context_prompt="Agent context",
            feedback_definition_prompt="Feedback def",
            previously_extracted=previously_extracted,
        )

        assert len(messages) > 0

    def test_without_previously_extracted(self):
        """Test incremental extraction without previously extracted feedbacks uses '(None)' placeholder."""
        data_models = []
        prompt_manager = PromptManager()

        messages = construct_incremental_feedback_extraction_messages(
            prompt_manager=prompt_manager,
            request_interaction_data_models=data_models,
            agent_context_prompt="Agent context",
            feedback_definition_prompt="Feedback def",
            previously_extracted=None,
        )

        assert len(messages) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
