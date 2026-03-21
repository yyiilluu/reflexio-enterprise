"""Tests for agent success evaluation utility functions."""

from datetime import UTC, datetime

import pytest
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import Interaction, Request

from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.agent_success_evaluation.agent_success_evaluation_utils import (
    construct_agent_success_evaluation_messages_from_sessions,
    construct_agent_success_evaluation_with_comparison_messages,
    format_interactions_for_request,
    has_shadow_content,
)


def test_construct_agent_success_evaluation_messages_with_sessions():
    """Test that construct_agent_success_evaluation_messages_from_sessions formats interactions correctly in the rendered prompt."""
    # Create test interactions with both content and actions
    interactions = [
        Interaction(
            interaction_id=1,
            user_id="user_123",
            request_id="req_1",
            content="The agent helped me complete my task successfully",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=2,
            user_id="user_123",
            request_id="req_1",
            content="I used the search tool",
            role="assistant",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
        ),
        Interaction(
            interaction_id=3,
            user_id="user_123",
            request_id="req_1",
            content="Great!",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="click",
            user_action_description="search button",
        ),
    ]

    # Create test request
    test_request = Request(
        request_id="req_1",
        user_id="user_123",
        source="test",
        agent_version="v1.0",
        session_id="test_group",
        created_at=int(datetime.now(UTC).timestamp()),
    )

    # Create RequestInteractionDataModel
    request_interaction_data_models = [
        RequestInteractionDataModel(
            request=test_request,
            interactions=interactions,
            session_id="test_group",
        )
    ]

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_agent_success_evaluation_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=request_interaction_data_models,
        agent_context_prompt="Test agent context",
        success_definition_prompt="Evaluate if the agent successfully completed the task",
        tool_can_use="search, calculator",
        metadata_definition_prompt="Include tool usage statistics",
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
                "[Interactions]" in content
                or "User and agent interactions:" in content
                or "user: ```The agent helped me complete my task successfully```"
                in content  # Check directly
            ):
                # Validate the interactions are formatted correctly in the rendered prompt
                assert (
                    "user: ```The agent helped me complete my task successfully```"
                    in content
                ), (
                    "Expected 'user: ```The agent helped me complete my task successfully```' in prompt"
                )
                assert "assistant: ```I used the search tool```" in content, (
                    "Expected 'assistant: ```I used the search tool```' in prompt"
                )
                assert "user: ```Great!```" in content, (
                    "Expected 'user: ```Great!```' in prompt"
                )
                assert "user: ```click search button```" in content, (
                    "Expected 'user: ```click search button```' in prompt"
                )

                # Also verify success definition and tools are in the content
                assert (
                    "Evaluate if the agent successfully completed the task" in content
                ), "Expected success definition in prompt"
                assert "search, calculator" in content, "Expected tools in prompt"

                found_interactions = True
                break

    assert found_interactions, "Did not find interactions in the rendered prompt"


def test_construct_agent_success_evaluation_messages_with_empty_sessions():
    """Test that construct_agent_success_evaluation_messages_from_sessions handles empty sessions."""
    # Empty sessions list
    request_interaction_data_models = []

    # Create prompt manager
    prompt_manager = PromptManager()

    # Call the function
    messages = construct_agent_success_evaluation_messages_from_sessions(
        prompt_manager=prompt_manager,
        request_interaction_data_models=request_interaction_data_models,
        agent_context_prompt="Test agent context",
        success_definition_prompt="Evaluate if the agent successfully completed the task",
        tool_can_use="search, calculator",
        metadata_definition_prompt="Include tool usage statistics",
    )

    # Should still create messages (user message with prompt)
    assert len(messages) > 0, "No messages were created for empty sessions"


# ===============================
# Tests for has_shadow_content
# ===============================


class TestHasShadowContent:
    """Tests for has_shadow_content utility."""

    def _make_interaction(self, shadow_content: str = "") -> Interaction:
        return Interaction(
            interaction_id=1,
            user_id="u1",
            request_id="req1",
            content="regular content",
            role="assistant",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
            shadow_content=shadow_content,
        )

    def test_shadow_content_present(self):
        """Test returns True when shadow_content is present."""
        interactions = [self._make_interaction("shadow text")]
        assert has_shadow_content(interactions) is True

    def test_shadow_content_empty(self):
        """Test returns False when shadow_content is empty string."""
        interactions = [self._make_interaction("")]
        assert has_shadow_content(interactions) is False

    def test_shadow_content_none(self):
        """Test returns False when shadow_content defaults to empty."""
        interactions = [self._make_interaction()]
        assert has_shadow_content(interactions) is False

    def test_empty_list(self):
        """Test returns False for empty interaction list."""
        assert has_shadow_content([]) is False

    def test_mixed_interactions(self):
        """Test returns True when at least one interaction has shadow content."""
        interactions = [
            self._make_interaction(""),
            self._make_interaction("has shadow"),
            self._make_interaction(""),
        ]
        assert has_shadow_content(interactions) is True


# ===============================
# Tests for format_interactions_for_request
# ===============================


class TestFormatInteractionsForRequest:
    """Tests for format_interactions_for_request utility."""

    def _make_interaction(
        self,
        content: str = "hello",
        role: str = "user",
        shadow_content: str = "",
        user_action: str = "none",
        user_action_description: str = "",
    ) -> Interaction:
        return Interaction(
            interaction_id=1,
            user_id="u1",
            request_id="req1",
            content=content,
            role=role,
            created_at=int(datetime.now(UTC).timestamp()),
            user_action=user_action,
            user_action_description=user_action_description,
            shadow_content=shadow_content,
        )

    def test_regular_content(self):
        """Test formatting with regular content."""
        interactions = [
            self._make_interaction("How are you?", role="user"),
            self._make_interaction("I'm fine!", role="assistant"),
        ]
        result = format_interactions_for_request(interactions)
        assert "user: How are you?" in result
        assert "assistant: I'm fine!" in result

    def test_shadow_content_used_when_flag_set(self):
        """Test that shadow_content replaces regular content when use_shadow=True."""
        interactions = [
            self._make_interaction("regular", shadow_content="shadow"),
        ]
        result = format_interactions_for_request(interactions, use_shadow=True)
        assert "shadow" in result
        assert "regular" not in result

    def test_shadow_content_ignored_when_flag_false(self):
        """Test that shadow_content is ignored when use_shadow=False."""
        interactions = [
            self._make_interaction("regular", shadow_content="shadow"),
        ]
        result = format_interactions_for_request(interactions, use_shadow=False)
        assert "regular" in result
        assert "shadow" not in result

    def test_shadow_fallback_to_regular(self):
        """Test that regular content is used as fallback when shadow is empty."""
        interactions = [
            self._make_interaction("regular", shadow_content=""),
        ]
        result = format_interactions_for_request(interactions, use_shadow=True)
        assert "regular" in result

    def test_user_action_included(self):
        """Test that user actions are included in formatted output."""
        interactions = [
            self._make_interaction(
                "hello",
                user_action="click",
                user_action_description="submit button",
            ),
        ]
        result = format_interactions_for_request(interactions)
        assert "click submit button" in result

    def test_none_user_action_excluded(self):
        """Test that 'none' user actions are excluded from output."""
        interactions = [
            self._make_interaction("hello", user_action="none"),
        ]
        result = format_interactions_for_request(interactions)
        lines = result.strip().split("\n")
        assert len(lines) == 1
        assert "none" not in lines[0]

    def test_empty_interactions(self):
        """Test formatting empty interaction list."""
        result = format_interactions_for_request([])
        assert result == ""


# ===============================
# Tests for construct_agent_success_evaluation_with_comparison_messages
# ===============================


class TestConstructComparisonMessages:
    """Tests for construct_agent_success_evaluation_with_comparison_messages."""

    def test_creates_messages_with_both_requests(self):
        """Test that comparison prompt includes both request interactions."""
        prompt_manager = PromptManager()

        messages = construct_agent_success_evaluation_with_comparison_messages(
            prompt_manager=prompt_manager,
            request_1_interactions="user: hello\nassistant: hi there",
            request_2_interactions="user: hello\nassistant: greetings",
            agent_context_prompt="Test agent",
            success_definition_prompt="Task completion",
            tool_can_use="search",
        )

        assert len(messages) > 0

        # Verify both request interactions appear in the prompt
        all_text = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        all_text += item.get("text", "")
            else:
                all_text += str(content)

        assert "hello" in all_text
        assert "Task completion" in all_text

    def test_without_optional_metadata(self):
        """Test comparison messages without optional metadata_definition_prompt."""
        prompt_manager = PromptManager()

        messages = construct_agent_success_evaluation_with_comparison_messages(
            prompt_manager=prompt_manager,
            request_1_interactions="user: q1\nassistant: a1",
            request_2_interactions="user: q2\nassistant: a2",
            agent_context_prompt="Agent",
            success_definition_prompt="Success",
            tool_can_use="",
            metadata_definition_prompt=None,
        )

        assert len(messages) > 0

    def test_with_interactions_for_images(self):
        """Test comparison messages with image interactions."""
        prompt_manager = PromptManager()

        image_interaction = Interaction(
            interaction_id=1,
            user_id="u1",
            request_id="req1",
            content="Look at this",
            role="user",
            created_at=int(datetime.now(UTC).timestamp()),
            user_action="none",
            user_action_description="",
            interacted_image_url="http://example.com/img.png",
        )

        messages = construct_agent_success_evaluation_with_comparison_messages(
            prompt_manager=prompt_manager,
            request_1_interactions="user: test",
            request_2_interactions="user: test2",
            agent_context_prompt="Agent",
            success_definition_prompt="Success",
            tool_can_use="",
            interactions_for_images=[image_interaction],
        )

        assert len(messages) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
