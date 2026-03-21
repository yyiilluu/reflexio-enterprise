"""
Unit tests for ProfileExtractor.

Tests the extractor's new responsibilities for:
- Operation state key generation
- Interaction collection with window/stride
- Source filtering
- Operation state updates
- Integration of run() method
- LLM-based profile extraction (_generate_raw_updates_from_sessions)
- Mock profile generation
- Init validation
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.profile.profile_extractor import ProfileExtractor
from reflexio.server.services.profile.profile_generation_service import (
    ProfileGenerationServiceConfig,
)
from reflexio.server.services.profile.profile_generation_service_utils import (
    ProfileAddItem,
    StructuredProfilesOutput,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.service_schemas import (
    Interaction,
    Request,
)
from reflexio_commons.config_schema import ProfileExtractorConfig

# ===============================
# Fixtures
# ===============================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock(spec=LiteLLMClient)
    # Return an empty StructuredProfilesOutput for profile extraction
    client.generate_chat_response.return_value = StructuredProfilesOutput()
    return client


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def request_context(temp_storage_dir):
    """Create a request context with mock storage."""
    context = RequestContext(org_id="test_org", storage_base_dir=temp_storage_dir)
    # Mock the storage
    context.storage = MagicMock()
    return context


@pytest.fixture
def extractor_config():
    """Create a profile extractor config."""
    return ProfileExtractorConfig(
        extractor_name="test_extractor",
        profile_content_definition_prompt="Extract user preferences",
    )


@pytest.fixture
def service_config():
    """Create a service config."""
    return ProfileGenerationServiceConfig(
        user_id="test_user",
        request_id="test_request",
        source="api",
    )


@pytest.fixture
def sample_interactions():
    """Create sample interactions for testing."""
    return [
        Interaction(
            interaction_id=1,
            user_id="test_user",
            content="I prefer dark mode",
            request_id="req1",
            created_at=1000,
            role="user",
        ),
        Interaction(
            interaction_id=2,
            user_id="test_user",
            content="Got it, I'll remember that preference",
            request_id="req1",
            created_at=1001,
            role="assistant",
        ),
    ]


@pytest.fixture
def sample_request_interaction_models(sample_interactions):
    """Create sample RequestInteractionDataModel objects."""
    request = Request(
        request_id="req1",
        user_id="test_user",
        created_at=1000,
        source="api",
    )
    return [
        RequestInteractionDataModel(
            session_id="req1",
            request=request,
            interactions=sample_interactions,
        )
    ]


# ===============================
# Test: Operation State Key
# ===============================


class TestOperationStateKey:
    """Tests for operation state key generation."""

    def test_state_manager_includes_user_id_in_bookmark_key(
        self, request_context, mock_llm_client, extractor_config, service_config
    ):
        """Test that profile extractor state manager builds keys with user_id (user-scoped)."""
        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        mgr = extractor._create_state_manager()

        assert mgr.service_name == "profile_extractor"
        assert mgr.org_id == "test_org"
        # Verify the bookmark key format includes user_id
        key = mgr._bookmark_key(name="test_extractor", scope_id=service_config.user_id)
        assert "profile_extractor" in key
        assert "test_org" in key
        assert "test_user" in key
        assert "test_extractor" in key
        assert key == "profile_extractor::test_org::test_user::test_extractor"

    def test_different_users_have_different_keys(
        self, request_context, mock_llm_client, extractor_config
    ):
        """Test that different users get different operation state keys."""
        config1 = ProfileGenerationServiceConfig(
            user_id="user1", request_id="req1", source="api"
        )
        config2 = ProfileGenerationServiceConfig(
            user_id="user2", request_id="req2", source="api"
        )

        extractor1 = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=config1,
            agent_context="Test agent",
        )
        extractor2 = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=config2,
            agent_context="Test agent",
        )

        mgr1 = extractor1._create_state_manager()
        mgr2 = extractor2._create_state_manager()
        key1 = mgr1._bookmark_key(name="test_extractor", scope_id=config1.user_id)
        key2 = mgr2._bookmark_key(name="test_extractor", scope_id=config2.user_id)
        assert key1 != key2


# ===============================
# Test: Get Interactions
# ===============================


class TestGetInteractions:
    """Tests for interaction collection logic.

    Note: Stride checking is handled upstream by BaseGenerationService._filter_configs_by_stride()
    before the extractor is created, so stride tests are at the service level.
    """

    def test_returns_interactions(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that interactions are returned from storage."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor._get_interactions()

        assert result is not None
        assert len(result) == 1  # One session

    def test_uses_window_size_when_configured(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that window size is used to fetch interactions."""
        # Configure extractor with window size
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
            extraction_window_size_override=50,
        )

        # Mock storage
        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._get_interactions()

        # Verify get_last_k_interactions_grouped was called with correct window size
        request_context.storage.get_last_k_interactions_grouped.assert_called_once()
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args
        assert call_kwargs[1]["k"] == 50

    def test_returns_none_when_source_filter_skips(
        self,
        request_context,
        mock_llm_client,
        sample_request_interaction_models,
    ):
        """Test that None is returned when source filter causes skip."""
        # Configure extractor with specific sources
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
            request_sources_enabled=["mobile", "desktop"],
        )

        # Service config has source="api" which is not in enabled list
        service_config = ProfileGenerationServiceConfig(
            user_id="test_user",
            request_id="test_request",
            source="api",  # Not in enabled list
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor._get_interactions()

        assert result is None

    def test_passes_correct_user_id_to_storage(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that user_id is passed to storage methods (user-scoped)."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._get_interactions()

        # Verify user_id was passed to get_last_k_interactions_grouped
        call_kwargs = request_context.storage.get_last_k_interactions_grouped.call_args[
            1
        ]
        assert call_kwargs["user_id"] == "test_user"


# ===============================
# Test: Update Operation State
# ===============================


class TestUpdateOperationState:
    """Tests for operation state update logic."""

    def test_updates_state_after_processing(
        self,
        request_context,
        mock_llm_client,
        extractor_config,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that operation state is updated with processed interactions."""
        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=extractor_config,
            service_config=service_config,
            agent_context="Test agent",
        )

        extractor._update_operation_state(sample_request_interaction_models)

        # Verify upsert was called
        request_context.storage.upsert_operation_state.assert_called_once()

        # Verify state contains interaction IDs
        call_args = request_context.storage.upsert_operation_state.call_args
        state_key = call_args[0][0]
        state = call_args[0][1]

        assert "profile_extractor" in state_key
        assert "last_processed_interaction_ids" in state
        assert 1 in state["last_processed_interaction_ids"]
        assert 2 in state["last_processed_interaction_ids"]


# ===============================
# Test: Run Integration
# ===============================


class TestRun:
    """Integration tests for the run() method."""

    def test_run_collects_own_interactions_when_not_provided(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that run() collects interactions when not provided in service config."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        # Enable mock mode for LLM responses
        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            extractor.run()

        # Verify storage was queried for interactions
        request_context.storage.get_last_k_interactions_grouped.assert_called()

    def test_run_returns_empty_when_no_interactions(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that run() returns None when no interactions available."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        # Return empty interactions
        request_context.storage.get_last_k_interactions_grouped.return_value = (
            [],
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        result = extractor.run()

        assert result is None

    def test_run_does_not_update_bookmark_when_extraction_fails(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Run should raise and leave bookmark unchanged when extraction fails."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )
        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )
        request_context.storage.get_user_profile.return_value = []

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )
        extractor._generate_raw_updates_from_sessions = MagicMock(
            side_effect=RuntimeError("llm timeout")
        )

        with pytest.raises(RuntimeError):
            extractor.run()

        request_context.storage.upsert_operation_state.assert_not_called()

    def test_run_updates_operation_state_on_success(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that operation state is updated after successful extraction."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )
        request_context.storage.get_user_profile.return_value = []

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

        with patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "true"}):
            result = extractor.run()

        # Verify operation state was updated
        if result is not None:
            request_context.storage.upsert_operation_state.assert_called()


# ===============================
# Test: Convert Raw to User Profiles
# ===============================


class TestConvertRawToUserProfiles:
    """Tests for converting raw profile dicts to UserProfile objects."""

    def _make_extractor(self, request_context, mock_llm_client, service_config):
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )
        return ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

    def test_converts_valid_profiles(
        self, request_context, mock_llm_client, service_config
    ):
        """Test converting valid raw profile dicts."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        raw_profiles = [
            {"content": "User prefers dark mode", "time_to_live": "one_month"},
            {"content": "User's name is John", "time_to_live": "infinity"},
        ]

        result = extractor._convert_raw_to_user_profiles(
            raw_profiles=raw_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(result) == 2
        assert result[0].profile_content == "User prefers dark mode"
        assert result[0].user_id == "test_user"
        assert result[0].extractor_names == ["test_extractor"]
        assert result[1].profile_content == "User's name is John"

    def test_skips_invalid_profiles(
        self, request_context, mock_llm_client, service_config
    ):
        """Test that invalid profile dicts are skipped."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        raw_profiles = [
            {"content": "Valid profile", "time_to_live": "one_month"},
            {"no_content_key": "Invalid"},
            "not_a_dict",
        ]

        result = extractor._convert_raw_to_user_profiles(
            raw_profiles=raw_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(result) == 1
        assert result[0].profile_content == "Valid profile"

    def test_custom_features_extracted(
        self, request_context, mock_llm_client, service_config
    ):
        """Test that extra fields become custom_features."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        raw_profiles = [
            {
                "content": "Likes pizza",
                "time_to_live": "one_month",
                "metadata": "pizza",
            },
        ]

        result = extractor._convert_raw_to_user_profiles(
            raw_profiles=raw_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(result) == 1
        assert result[0].custom_features == {"metadata": "pizza"}


# ===============================
# Test: Init Validation (line 88)
# ===============================


class TestInitValidation:
    """Tests for __init__ validation of llm_model_setting."""

    def test_raises_when_model_setting_not_dict(
        self, request_context, mock_llm_client, extractor_config, service_config
    ):
        """Test that ValueError is raised when llm_model_setting is not a dict (line 88)."""
        with patch(
            "reflexio.server.services.profile.profile_extractor.SiteVarManager"
        ) as mock_svm_cls:
            mock_svm_cls.return_value.get_site_var.return_value = "not_a_dict"
            with pytest.raises(ValueError, match="llm_model_setting must be a dict"):
                ProfileExtractor(
                    request_context=request_context,
                    llm_client=mock_llm_client,
                    extractor_config=extractor_config,
                    service_config=service_config,
                    agent_context="Test agent",
                )


# ===============================
# Test: Generate Raw Updates From Sessions (lines 317-450)
# ===============================


class TestGenerateRawUpdatesFromSessions:
    """Tests for _generate_raw_updates_from_sessions covering the LLM extraction path."""

    def _make_extractor(
        self,
        request_context,
        mock_llm_client,
        service_config,
        extractor_config=None,
    ):
        """Helper to build an extractor with optional config override."""
        config = extractor_config or ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )
        return ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

    def test_non_incremental_calls_construct_messages(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that non-incremental mode uses construct_profile_extraction_messages_from_sessions."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = (
                StructuredProfilesOutput(profiles=None)
            )

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            mock_construct.assert_called_once()
            assert result == []

    def test_incremental_calls_incremental_construct(
        self,
        request_context,
        mock_llm_client,
        sample_request_interaction_models,
    ):
        """Test that incremental mode uses construct_incremental_profile_extraction_messages."""
        inc_service_config = ProfileGenerationServiceConfig(
            user_id="test_user",
            request_id="test_request",
            source="api",
            is_incremental=True,
        )
        extractor = self._make_extractor(
            request_context, mock_llm_client, inc_service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_generation_service_utils.construct_incremental_profile_extraction_messages"
            ) as mock_inc_construct,
        ):
            mock_inc_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = (
                StructuredProfilesOutput(profiles=None)
            )

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            mock_inc_construct.assert_called_once()
            assert result == []

    def test_llm_exception_is_propagated(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that LLM call exceptions propagate from _generate_raw_updates_from_sessions."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.side_effect = RuntimeError(
                "LLM API timeout"
            )

            with pytest.raises(RuntimeError, match="LLM API timeout"):
                extractor._generate_raw_updates_from_sessions(
                    request_interaction_data_models=sample_request_interaction_models,
                    existing_profiles=[],
                )

    def test_returns_empty_when_response_not_structured_output(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that a non-StructuredProfilesOutput response returns empty list."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            # Return a plain string instead of StructuredProfilesOutput
            mock_llm_client.generate_chat_response.return_value = (
                "unexpected string response"
            )

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            assert result == []

    def test_returns_empty_when_response_is_none(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that a None response from LLM returns empty list."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = None

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            assert result == []

    def test_returns_profile_dicts_on_success(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that valid StructuredProfilesOutput is converted to list of dicts."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        profiles_output = StructuredProfilesOutput(
            profiles=[
                ProfileAddItem(
                    content="User prefers dark mode", time_to_live="one_month"
                ),
                ProfileAddItem(content="User likes Python", time_to_live="infinity"),
            ]
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = profiles_output

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            assert len(result) == 2
            assert result[0]["content"] == "User prefers dark mode"
            assert result[0]["time_to_live"] == "one_month"
            assert result[1]["content"] == "User likes Python"

    def test_returns_empty_when_profiles_list_is_empty(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that empty profiles list in StructuredProfilesOutput returns empty list."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = (
                StructuredProfilesOutput(profiles=[])
            )

            result = extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            assert result == []

    def test_context_prompt_stripped(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that context_prompt is stripped before passing to message construction."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="  Extract prefs  ",
            context_prompt="  Some context  ",
        )
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config, extractor_config=config
        )

        with (
            patch.dict(os.environ, {"MOCK_LLM_RESPONSE": "false"}),
            patch(
                "reflexio.server.services.profile.profile_extractor.construct_profile_extraction_messages_from_sessions"
            ) as mock_construct,
        ):
            mock_construct.return_value = [{"role": "system", "content": "test"}]
            mock_llm_client.generate_chat_response.return_value = (
                StructuredProfilesOutput(profiles=None)
            )

            extractor._generate_raw_updates_from_sessions(
                request_interaction_data_models=sample_request_interaction_models,
                existing_profiles=[],
            )

            call_kwargs = mock_construct.call_args[1]
            assert call_kwargs["context_prompt"] == "Some context"
            assert call_kwargs["profile_content_definition_prompt"] == "Extract prefs"


# ===============================
# Test: Run Returns None for Empty Raw Profiles (line 241)
# ===============================


class TestRunReturnsNoneForEmptyRawProfiles:
    """Tests for run() returning None when raw_profiles is empty (line 241)."""

    def test_run_returns_none_when_raw_profiles_empty(
        self,
        request_context,
        mock_llm_client,
        service_config,
        sample_request_interaction_models,
    ):
        """Test that run() returns None when extraction produces empty raw profiles."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )

        request_context.storage.get_last_k_interactions_grouped.return_value = (
            sample_request_interaction_models,
            [],
        )

        extractor = ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )
        # Mock _generate_raw_updates_from_sessions to return empty list
        extractor._generate_raw_updates_from_sessions = MagicMock(return_value=[])

        result = extractor.run()

        assert result is None
        # Operation state should not be updated when no profiles extracted
        request_context.storage.upsert_operation_state.assert_not_called()


# ===============================
# Test: Mock Profile Generation (lines 470, 501)
# ===============================


class TestGenerateMockProfiles:
    """Tests for _generate_mock_profiles covering edge cases."""

    def _make_extractor(
        self, request_context, mock_llm_client, service_config, extractor_config=None
    ):
        """Helper to build an extractor with optional config override."""
        config = extractor_config or ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
        )
        return ProfileExtractor(
            request_context=request_context,
            llm_client=mock_llm_client,
            extractor_config=config,
            service_config=service_config,
            agent_context="Test agent",
        )

    def test_returns_empty_when_no_interactions(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that _generate_mock_profiles returns [] when interactions are empty (line 470)."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=[],
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert result == []

    def test_appends_highlight_snippet_when_keyword_found(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that highlight snippet is appended when keyword matches (line 501)."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="test_user",
                content="I need help with my account",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
            Interaction(
                interaction_id=2,
                user_id="test_user",
                content="Our company uses this software product extensively for service automation",
                request_id="req1",
                created_at=1001,
                role="user",
            ),
        ]
        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=interactions,
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert len(result) == 1
        # The last interaction's first 50 chars as sample_content
        assert "User mentioned:" in result[0]["content"]
        # The keyword "company"/"software"/"product"/"service" should trigger highlight
        assert "Key context:" in result[0]["content"]

    def test_no_highlight_when_no_keyword_match(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that no highlight snippet when no keyword matches."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="test_user",
                content="Hello there, how are you?",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
        ]
        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=interactions,
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert len(result) == 1
        assert "Key context:" not in result[0]["content"]
        assert "User mentioned:" in result[0]["content"]

    def test_metadata_added_when_metadata_definition_exists(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that mock metadata is added when metadata_definition_prompt is set."""
        config = ProfileExtractorConfig(
            extractor_name="test_extractor",
            profile_content_definition_prompt="Extract user preferences",
            metadata_definition_prompt="Extract category",
        )
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config, extractor_config=config
        )

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="test_user",
                content="I like pizza",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
        ]
        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=interactions,
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert len(result) == 1
        assert result[0].get("metadata") == "mock_metadata_value"

    def test_no_metadata_when_no_metadata_definition(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test that no metadata key when metadata_definition_prompt is not set."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="test_user",
                content="I like pizza",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
        ]
        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=interactions,
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert len(result) == 1
        assert "metadata" not in result[0]

    def test_sample_content_fallback_when_content_is_empty(
        self,
        request_context,
        mock_llm_client,
        service_config,
    ):
        """Test fallback to 'sample interaction' when last interaction content is empty string."""
        extractor = self._make_extractor(
            request_context, mock_llm_client, service_config
        )

        interactions = [
            Interaction(
                interaction_id=1,
                user_id="test_user",
                content="",
                request_id="req1",
                created_at=1000,
                role="user",
            ),
        ]
        request_model = RequestInteractionDataModel(
            session_id="req1",
            request=Request(
                request_id="req1",
                user_id="test_user",
                created_at=1000,
                source="api",
            ),
            interactions=interactions,
        )

        result = extractor._generate_mock_profiles(
            request_interaction_data_models=[request_model],
        )

        assert len(result) == 1
        assert "sample interaction" in result[0]["content"]
