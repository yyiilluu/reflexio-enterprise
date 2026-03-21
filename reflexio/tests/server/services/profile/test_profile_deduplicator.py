"""
Unit tests for ProfileDeduplicator.

Tests the deduplicator's responsibilities for:
- Pydantic output schema validation
- Profile deduplication with LLM and hybrid search
- Profile formatting for prompts
- Building deduplicated results
- Merging custom features
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


# Disable mock mode for deduplicator tests so LLM mocks are actually used
@pytest.fixture(autouse=True)
def disable_mock_llm_response(monkeypatch):
    """Disable MOCK_LLM_RESPONSE env var so deduplicator tests use their own mocks."""
    monkeypatch.delenv("MOCK_LLM_RESPONSE", raising=False)


from reflexio_commons.api_schema.service_schemas import (
    ProfileTimeToLive,
    UserProfile,
)

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.deduplication_utils import parse_item_id
from reflexio.server.services.profile.profile_deduplicator import (
    ProfileDeduplicationOutput,
    ProfileDeduplicator,
    ProfileDuplicateGroup,
)

# ===============================
# Fixtures
# ===============================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock(spec=LiteLLMClient)
    client.get_embeddings.return_value = [[0.1] * 10, [0.2] * 10, [0.3] * 10]
    return client


@pytest.fixture
def mock_request_context():
    """Create a mock request context with prompt manager and storage."""
    context = MagicMock(spec=RequestContext)
    context.prompt_manager = MagicMock()
    context.prompt_manager.render_prompt.return_value = "test prompt"
    context.storage = MagicMock()
    context.storage.search_user_profile.return_value = []
    return context


@pytest.fixture
def mock_site_var_manager():
    """Mock the SiteVarManager to return model settings."""
    with patch("reflexio.server.services.deduplication_utils.SiteVarManager") as mock:
        instance = mock.return_value
        instance.get_site_var.return_value = {"default_generation_model_name": "gpt-4"}
        yield mock


@pytest.fixture
def sample_profiles():
    """Create sample UserProfile objects for testing."""
    timestamp = int(datetime.now(UTC).timestamp())
    return [
        UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id="test_user",
            profile_content="User prefers dark mode for coding",
            last_modified_timestamp=timestamp,
            generated_from_request_id="req_1",
            profile_time_to_live=ProfileTimeToLive.ONE_MONTH,
            source="extractor_a",
        ),
        UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id="test_user",
            profile_content="User likes dark theme in their IDE",
            last_modified_timestamp=timestamp,
            generated_from_request_id="req_2",
            profile_time_to_live=ProfileTimeToLive.ONE_WEEK,
            source="extractor_b",
        ),
        UserProfile(
            profile_id=str(uuid.uuid4()),
            user_id="test_user",
            profile_content="User is a Python developer",
            last_modified_timestamp=timestamp,
            generated_from_request_id="req_3",
            profile_time_to_live=ProfileTimeToLive.ONE_YEAR,
            source="extractor_a",
        ),
    ]


# ===============================
# Test: Pydantic Models
# ===============================


class TestPydanticModels:
    """Tests for the Pydantic output schema models."""

    def test_duplicate_group_creation(self):
        """Test that ProfileDuplicateGroup can be created with valid data."""
        group = ProfileDuplicateGroup(
            item_ids=["NEW-0", "NEW-1", "EXISTING-0"],
            merged_content="User prefers dark mode",
            merged_time_to_live="one_month",
            reasoning="Both profiles are about dark mode preferences",
        )
        assert group.item_ids == ["NEW-0", "NEW-1", "EXISTING-0"]
        assert group.merged_content == "User prefers dark mode"
        assert group.merged_time_to_live == "one_month"

    def test_duplicate_group_forbids_extra_fields(self):
        """Test that ProfileDuplicateGroup forbids extra fields."""
        with pytest.raises(Exception):  # noqa: B017
            ProfileDuplicateGroup(
                item_ids=["NEW-0"],
                merged_content="test",
                merged_time_to_live="one_day",
                reasoning="test",
                extra_field="not allowed",
            )

    def test_deduplication_output_creation(self):
        """Test that ProfileDeduplicationOutput can be created."""
        output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="merged",
                    merged_time_to_live="one_week",
                    reasoning="duplicates",
                )
            ],
            unique_ids=["NEW-2", "NEW-3"],
        )
        assert len(output.duplicate_groups) == 1
        assert output.unique_ids == ["NEW-2", "NEW-3"]

    def test_deduplication_output_empty_defaults(self):
        """Test that ProfileDeduplicationOutput has empty list defaults."""
        output = ProfileDeduplicationOutput()
        assert output.duplicate_groups == []
        assert output.unique_ids == []

    def test_deduplication_output_from_dict(self):
        """Test that ProfileDeduplicationOutput can be validated from dict."""
        data = {
            "duplicate_groups": [
                {
                    "item_ids": ["NEW-0", "NEW-1", "EXISTING-0"],
                    "merged_content": "test",
                    "merged_time_to_live": "one_day",
                    "reasoning": "reason",
                }
            ],
            "unique_ids": ["NEW-2"],
        }
        output = ProfileDeduplicationOutput.model_validate(data)
        assert len(output.duplicate_groups) == 1
        assert output.unique_ids == ["NEW-2"]

    def test_parse_item_id_valid(self):
        """Test parse_item_id with valid inputs."""
        assert parse_item_id("NEW-0") == ("NEW", 0)
        assert parse_item_id("EXISTING-1") == ("EXISTING", 1)
        assert parse_item_id("new-5") == ("NEW", 5)

    def test_parse_item_id_invalid(self):
        """Test parse_item_id returns None for invalid inputs."""
        assert parse_item_id("INVALID-0") is None
        assert parse_item_id("NOHYPHEN") is None
        assert parse_item_id("NEW-abc") is None


# ===============================
# Test: ProfileDeduplicator Init
# ===============================


class TestProfileDeduplicatorInit:
    """Tests for ProfileDeduplicator initialization."""

    def test_init_sets_attributes(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test that __init__ sets all required attributes."""
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        assert deduplicator.request_context == mock_request_context
        assert deduplicator.client == mock_llm_client
        assert deduplicator.model_name == "gpt-4"

    def test_init_uses_default_model_when_not_specified(
        self, mock_request_context, mock_llm_client
    ):
        """Test that init falls back to default model if not in site var."""
        with patch(
            "reflexio.server.services.deduplication_utils.SiteVarManager"
        ) as mock:
            instance = mock.return_value
            instance.get_site_var.return_value = {}
            deduplicator = ProfileDeduplicator(
                request_context=mock_request_context,
                llm_client=mock_llm_client,
            )
            assert deduplicator.model_name == "gpt-5-mini"


# ===============================
# Test: Format Profiles For Prompt
# ===============================


class TestFormatProfilesForPrompt:
    """Tests for profile formatting for LLM prompt."""

    def test_format_profiles_basic(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that profiles are formatted correctly with NEW prefix."""
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._format_items_for_prompt(sample_profiles)

        assert "[NEW-0]" in result
        assert "[NEW-1]" in result
        assert "[NEW-2]" in result
        assert "User prefers dark mode for coding" in result
        assert "User likes dark theme in their IDE" in result
        assert "one_month" in result
        assert "one_week" in result
        assert "extractor_a" in result
        assert "extractor_b" in result

    def test_format_profiles_uses_ttl_value(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test formatting shows TTL value from profile."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="1",
                user_id="user",
                profile_content="test content",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                profile_time_to_live=ProfileTimeToLive.ONE_QUARTER,
            )
        ]
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._format_items_for_prompt(profiles)
        assert "TTL: one_quarter" in result

    def test_format_profiles_with_missing_source(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test formatting with profiles that have no source."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="1",
                user_id="user",
                profile_content="test content",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                source=None,
            )
        ]
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._format_items_for_prompt(profiles)
        assert "Source: unknown" in result

    def test_format_existing_profiles(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that existing profiles are formatted with EXISTING prefix."""
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._format_profiles_with_prefix(sample_profiles, "EXISTING")
        assert "[EXISTING-0]" in result
        assert "[EXISTING-1]" in result

    def test_format_empty_profiles(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test formatting empty profile list returns (None)."""
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._format_profiles_with_prefix([], "NEW")
        assert result == "(None)"


# ===============================
# Test: Merge Custom Features
# ===============================


class TestMergeCustomFeatures:
    """Tests for custom features merging."""

    def test_merge_custom_features_empty(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test merging when no profiles have custom features."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="1",
                user_id="user",
                profile_content="test",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features=None,
            ),
            UserProfile(
                profile_id="2",
                user_id="user",
                profile_content="test2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features=None,
            ),
        ]
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._merge_custom_features(profiles)
        assert result is None

    def test_merge_custom_features_single(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test merging when only one profile has custom features."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="1",
                user_id="user",
                profile_content="test",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features={"key1": "value1"},
            ),
            UserProfile(
                profile_id="2",
                user_id="user",
                profile_content="test2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features=None,
            ),
        ]
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._merge_custom_features(profiles)
        assert result == {"key1": "value1"}

    def test_merge_custom_features_multiple(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test merging custom features from multiple profiles."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="1",
                user_id="user",
                profile_content="test",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features={"key1": "value1", "key2": "old_value"},
            ),
            UserProfile(
                profile_id="2",
                user_id="user",
                profile_content="test2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req",
                custom_features={"key2": "new_value", "key3": "value3"},
            ),
        ]
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._merge_custom_features(profiles)
        assert result == {"key1": "value1", "key2": "new_value", "key3": "value3"}


# ===============================
# Test: Build Deduplicated Results
# ===============================


class TestBuildDeduplicatedResults:
    """Tests for building deduplicated profile results."""

    def test_build_deduplicated_results_merges_duplicates(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that duplicates are merged into a single profile."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="User prefers dark mode in their IDE",
                    merged_time_to_live="one_month",
                    reasoning="Both about dark mode preferences",
                )
            ],
            unique_ids=["NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        assert len(result_profiles) == 2  # 1 merged + 1 unique
        assert len(delete_ids) == 0
        assert len(superseded) == 0

        # Find the merged profile
        merged_profile = next(
            (
                p
                for p in result_profiles
                if p.profile_content == "User prefers dark mode in their IDE"
            ),
            None,
        )
        assert merged_profile is not None
        assert merged_profile.profile_time_to_live == ProfileTimeToLive.ONE_MONTH

    def test_build_deduplicated_results_preserves_unique(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that unique profiles are preserved."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-0", "NEW-1", "NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        assert len(result_profiles) == 3

    def test_build_deduplicated_results_handles_invalid_ttl(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that invalid TTL from LLM falls back to template TTL."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="merged content",
                    merged_time_to_live="invalid_ttl",
                    reasoning="test",
                )
            ],
            unique_ids=["NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=sample_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        merged_profile = next(
            (p for p in result_profiles if p.profile_content == "merged content"),
            None,
        )
        assert merged_profile is not None
        # Should fall back to template profile's TTL (first profile in group)
        assert merged_profile.profile_time_to_live == ProfileTimeToLive.ONE_MONTH

    def test_build_deduplicated_results_handles_unmentioned_profiles(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that profiles not mentioned by LLM are added as-is."""
        # LLM only mentions indices 0 and 1, not 2
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="merged",
                    merged_time_to_live="one_week",
                    reasoning="test",
                )
            ],
            unique_ids=[],  # LLM forgot to mention index 2
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=sample_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        # Should still include all profiles (1 merged + 1 unmentioned)
        assert len(result_profiles) == 2

    def test_build_deduplicated_results_collects_existing_to_delete(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that existing profiles marked for deletion are collected."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="test_user",
            profile_content="Old dark mode preference",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
        )

        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "EXISTING-0"],
                    merged_content="User prefers dark mode (updated)",
                    merged_time_to_live="one_month",
                    reasoning="New profile supersedes existing",
                )
            ],
            unique_ids=["NEW-1", "NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[existing_profile],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        assert len(delete_ids) == 1
        assert delete_ids[0] == "existing_1"
        assert len(superseded) == 1
        assert superseded[0].profile_id == "existing_1"


# ===============================
# Test: Deduplicate Main Method
# ===============================


class TestDeduplicate:
    """Tests for the main deduplicate() method."""

    def test_deduplicate_returns_original_when_empty(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that empty input returns empty output."""
        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=[],
            user_id="test_user",
            request_id="test_request",
        )

        assert profiles == []
        assert delete_ids == []
        assert superseded == []

    def test_deduplicate_returns_original_when_no_duplicates_found(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that original profiles are returned when LLM finds no duplicates."""
        mock_llm_client.generate_chat_response.return_value = (
            ProfileDeduplicationOutput(
                duplicate_groups=[],
                unique_ids=["NEW-0", "NEW-1", "NEW-2"],
            )
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=sample_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert profiles == sample_profiles
        assert delete_ids == []
        assert superseded == []

    def test_deduplicate_returns_original_when_llm_fails(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that original profiles are returned when LLM call fails."""
        mock_llm_client.generate_chat_response.side_effect = Exception("LLM Error")

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=sample_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert profiles == sample_profiles
        assert delete_ids == []
        assert superseded == []

    def test_deduplicate_merges_duplicates(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that duplicates are properly merged."""
        mock_llm_client.generate_chat_response.return_value = (
            ProfileDeduplicationOutput(
                duplicate_groups=[
                    ProfileDuplicateGroup(
                        item_ids=["NEW-0", "NEW-1"],
                        merged_content="User prefers dark mode",
                        merged_time_to_live="one_month",
                        reasoning="Both about dark mode",
                    )
                ],
                unique_ids=["NEW-2"],
            )
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=sample_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        # Should have 2 profiles: 1 merged + 1 unique
        assert len(profiles) == 2
        assert len(delete_ids) == 0

    def test_deduplicate_with_existing_profiles_to_delete(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test deduplication that supersedes existing profiles."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="test_user",
            profile_content="Old dark mode preference",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
        )

        # Mock storage to return existing profile via hybrid search
        mock_request_context.storage.search_user_profile.return_value = [
            existing_profile
        ]

        mock_llm_client.generate_chat_response.return_value = (
            ProfileDeduplicationOutput(
                duplicate_groups=[
                    ProfileDuplicateGroup(
                        item_ids=["NEW-0", "EXISTING-0"],
                        merged_content="User prefers dark mode (updated)",
                        merged_time_to_live="one_month",
                        reasoning="New supersedes existing",
                    )
                ],
                unique_ids=["NEW-1", "NEW-2"],
            )
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=sample_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(profiles) == 3  # 1 merged + 2 unique
        assert len(delete_ids) == 1
        assert delete_ids[0] == "existing_1"
        assert len(superseded) == 1


# ===============================
# Test: Integration
# ===============================


class TestIntegration:
    """Integration tests for the complete deduplication flow."""

    def test_full_deduplication_flow(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test a complete deduplication flow with realistic data."""
        timestamp = int(datetime.now(UTC).timestamp())

        # Create profiles from different extractors with duplicates
        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="User works in finance industry",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
                profile_time_to_live=ProfileTimeToLive.ONE_YEAR,
                source="industry_extractor",
                custom_features={"sector": "finance"},
            ),
            UserProfile(
                profile_id="p2",
                user_id="user",
                profile_content="User is in the financial services sector",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
                profile_time_to_live=ProfileTimeToLive.ONE_MONTH,
                source="job_extractor",
                custom_features={"job_type": "analyst"},
            ),
            UserProfile(
                profile_id="p3",
                user_id="user",
                profile_content="User prefers Python programming",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req3",
                profile_time_to_live=ProfileTimeToLive.INFINITY,
                source="tech_extractor",
            ),
        ]

        mock_llm_client.generate_chat_response.return_value = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="User works in the financial services industry",
                    merged_time_to_live="one_year",
                    reasoning="Both profiles describe the user's industry as finance/financial services",
                )
            ],
            unique_ids=["NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=new_profiles,
            user_id="user",
            request_id="test_request",
        )

        # Verify structure
        assert len(result_profiles) == 2
        assert len(delete_ids) == 0

        # Find merged profile
        merged = next(
            (
                p
                for p in result_profiles
                if "financial services industry" in p.profile_content
            ),
            None,
        )
        assert merged is not None
        assert merged.user_id == "user"
        assert merged.profile_time_to_live == ProfileTimeToLive.ONE_YEAR
        # Custom features should be merged
        assert merged.custom_features == {"sector": "finance", "job_type": "analyst"}

        # Find unique profile
        unique = next(
            (p for p in result_profiles if "Python" in p.profile_content), None
        )
        assert unique is not None
        assert unique.profile_content == "User prefers Python programming"


# ===============================
# Test: _build_deduplicated_results edge cases
# ===============================


class TestBuildDeduplicatedResultsEdgeCases:
    """Tests for edge cases in _build_deduplicated_results."""

    def test_empty_duplicate_groups_and_empty_unique_ids(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test with no groups and no unique_ids -- all profiles fall through to safety fallback."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=[],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # All 3 profiles should be added via the safety fallback path
        assert len(result_profiles) == 3
        assert delete_ids == []
        assert superseded == []
        # The profiles returned should be the originals (not copies/merged)
        for original in sample_profiles:
            assert original in result_profiles

    def test_all_profiles_are_duplicates_single_group(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test when all new profiles are grouped as duplicates in one group."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1", "NEW-2"],
                    merged_content="User prefers dark mode and is a Python dev",
                    merged_time_to_live="one_year",
                    reasoning="All related user preferences",
                )
            ],
            unique_ids=[],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # Only 1 merged profile, no unique, no safety fallback
        assert len(result_profiles) == 1
        assert result_profiles[0].profile_content == "User prefers dark mode and is a Python dev"
        assert result_profiles[0].profile_time_to_live == ProfileTimeToLive.ONE_YEAR
        assert delete_ids == []
        assert superseded == []

    def test_template_profile_none_when_only_existing_in_group(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that group is skipped when template_profile is None (no NEW indices in group)."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="test_user",
            profile_content="Existing profile content",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
            profile_time_to_live=ProfileTimeToLive.ONE_WEEK,
        )

        # Group contains only EXISTING indices, no NEW indices
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["EXISTING-0"],
                    merged_content="Should be skipped",
                    merged_time_to_live="one_week",
                    reasoning="Only existing profiles",
                )
            ],
            unique_ids=["NEW-0", "NEW-1", "NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[existing_profile],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # The group with only EXISTING should be skipped (template_profile is None)
        # All 3 new profiles should be added via unique_ids
        assert len(result_profiles) == 3
        # No merged profile with "Should be skipped" content
        assert all(
            p.profile_content != "Should be skipped" for p in result_profiles
        )

    def test_template_profile_none_with_out_of_range_new_index(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that group is skipped when NEW index is out of range (template stays None)."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-99"],  # Out of range
                    merged_content="Should be skipped",
                    merged_time_to_live="one_week",
                    reasoning="Out of range index",
                )
            ],
            unique_ids=["NEW-0", "NEW-1", "NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # Group skipped because template_profile is None (out-of-range NEW index)
        assert len(result_profiles) == 3
        assert all(
            p.profile_content != "Should be skipped" for p in result_profiles
        )

    def test_invalid_ttl_falls_back_to_template_ttl(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that invalid TTL from LLM falls back to the template profile's TTL."""
        timestamp = int(datetime.now(UTC).timestamp())
        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="test_user",
                profile_content="Profile A",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
                profile_time_to_live=ProfileTimeToLive.ONE_QUARTER,
                source="extractor_a",
            ),
            UserProfile(
                profile_id="p2",
                user_id="test_user",
                profile_content="Profile B",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
                profile_time_to_live=ProfileTimeToLive.ONE_WEEK,
                source="extractor_b",
            ),
        ]

        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="Merged A and B",
                    merged_time_to_live="totally_bogus_ttl",
                    reasoning="test invalid ttl",
                )
            ],
            unique_ids=[],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=new_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(result_profiles) == 1
        merged = result_profiles[0]
        assert merged.profile_content == "Merged A and B"
        # Falls back to the template profile's TTL (first NEW in group = ONE_QUARTER)
        assert merged.profile_time_to_live == ProfileTimeToLive.ONE_QUARTER

    def test_safety_fallback_for_partially_unhandled_profiles(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that profiles not mentioned by LLM at all (neither in groups nor unique_ids) are added via safety fallback."""
        # LLM only mentions index 0, leaving indices 1 and 2 unhandled
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[],
            unique_ids=["NEW-0"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=[],
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # 1 from unique_ids + 2 from safety fallback
        assert len(result_profiles) == 3
        assert delete_ids == []
        # The unhandled profiles should be the originals
        assert sample_profiles[1] in result_profiles
        assert sample_profiles[2] in result_profiles

    def test_duplicate_existing_ids_are_deduplicated_in_delete_list(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that the same existing profile appearing in multiple groups is only deleted once."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profiles = [
            UserProfile(
                profile_id="existing_1",
                user_id="test_user",
                profile_content="Existing content",
                last_modified_timestamp=timestamp,
                generated_from_request_id="old_req",
                profile_time_to_live=ProfileTimeToLive.ONE_MONTH,
            ),
        ]

        # Two groups both reference the same EXISTING-0
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "EXISTING-0"],
                    merged_content="Merged group 1",
                    merged_time_to_live="one_month",
                    reasoning="group 1",
                ),
                ProfileDuplicateGroup(
                    item_ids=["NEW-1", "EXISTING-0"],
                    merged_content="Merged group 2",
                    merged_time_to_live="one_week",
                    reasoning="group 2",
                ),
            ],
            unique_ids=["NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, delete_ids, superseded = (
            deduplicator._build_deduplicated_results(
                new_profiles=sample_profiles,
                existing_profiles=existing_profiles,
                dedup_output=dedup_output,
                user_id="test_user",
                request_id="test_request",
            )
        )

        # existing_1 should appear only once in delete_ids (seen_delete_ids dedup)
        assert delete_ids == ["existing_1"]
        assert len(superseded) == 1


# ===============================
# Test: _retrieve_existing_profiles edge cases
# ===============================


class TestRetrieveExistingProfiles:
    """Tests for _retrieve_existing_profiles edge cases."""

    def test_retrieve_with_user_id_filter(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that user_id is passed correctly to the search request."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="specific_user",
            profile_content="Existing profile",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
        )
        mock_request_context.storage.search_user_profile.return_value = [
            existing_profile
        ]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._retrieve_existing_profiles(
            new_profiles=sample_profiles,
            user_id="specific_user",
        )

        # Verify search was called and user_id was used in the request
        assert mock_request_context.storage.search_user_profile.called
        call_args = mock_request_context.storage.search_user_profile.call_args
        search_request = call_args[0][0]
        assert search_request.user_id == "specific_user"
        assert len(result) == 1
        assert result[0].profile_id == "existing_1"

    def test_retrieve_deduplicates_existing_by_profile_id(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that duplicate existing profiles (same profile_id) are deduplicated."""
        timestamp = int(datetime.now(UTC).timestamp())
        profile_a = UserProfile(
            profile_id="dup_id",
            user_id="user",
            profile_content="Profile A",
            last_modified_timestamp=timestamp,
            generated_from_request_id="req",
        )
        # The same profile returned for two different queries
        mock_request_context.storage.search_user_profile.return_value = [profile_a]

        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="Query text 1",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
            ),
            UserProfile(
                profile_id="p2",
                user_id="user",
                profile_content="Query text 2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
            ),
        ]

        mock_llm_client.get_embeddings.return_value = [[0.1] * 10, [0.2] * 10]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._retrieve_existing_profiles(
            new_profiles=new_profiles,
            user_id="user",
        )

        # Same profile_id returned for both queries, should be deduplicated to 1
        assert len(result) == 1
        assert result[0].profile_id == "dup_id"

    def test_retrieve_embedding_generation_failure(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that embedding failure falls back to None embeddings and search still proceeds."""
        mock_llm_client.get_embeddings.side_effect = Exception("Embedding service down")

        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="test_user",
            profile_content="Existing profile",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
        )
        mock_request_context.storage.search_user_profile.return_value = [
            existing_profile
        ]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._retrieve_existing_profiles(
            new_profiles=sample_profiles,
            user_id="test_user",
        )

        # Even with embedding failure, search should proceed with None embeddings
        assert mock_request_context.storage.search_user_profile.called
        # Verify None embeddings were passed in the SearchOptions
        call_args = mock_request_context.storage.search_user_profile.call_args
        options = call_args[1]["options"] if "options" in call_args[1] else call_args[0][2]
        assert options.query_embedding is None
        assert len(result) == 1

    def test_retrieve_empty_profile_content_skipped(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that profiles with empty/whitespace content are skipped during retrieval."""
        timestamp = int(datetime.now(UTC).timestamp())
        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
            ),
            UserProfile(
                profile_id="p2",
                user_id="user",
                profile_content="   ",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
            ),
        ]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._retrieve_existing_profiles(
            new_profiles=new_profiles,
            user_id="user",
        )

        # No valid query texts, should return empty without calling embeddings or search
        assert result == []
        mock_llm_client.get_embeddings.assert_not_called()
        mock_request_context.storage.search_user_profile.assert_not_called()

    def test_retrieve_with_status_filter(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that status_filter is passed through to search_user_profile."""
        from reflexio_commons.api_schema.service_schemas import Status

        timestamp = int(datetime.now(UTC).timestamp())
        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="Valid content",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
            ),
        ]
        mock_llm_client.get_embeddings.return_value = [[0.1] * 10]
        mock_request_context.storage.search_user_profile.return_value = []

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        deduplicator._retrieve_existing_profiles(
            new_profiles=new_profiles,
            user_id="user",
            status_filter=[Status.ARCHIVED],
        )

        # Verify status_filter was passed to search_user_profile
        call_args = mock_request_context.storage.search_user_profile.call_args
        assert call_args[1]["status_filter"] == [Status.ARCHIVED]

    def test_retrieve_search_failure_for_individual_query(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that a search failure for one profile query doesn't break the whole retrieval."""
        timestamp = int(datetime.now(UTC).timestamp())
        existing_profile = UserProfile(
            profile_id="existing_1",
            user_id="user",
            profile_content="Existing profile",
            last_modified_timestamp=timestamp,
            generated_from_request_id="old_req",
        )

        # First call fails, second call succeeds
        mock_request_context.storage.search_user_profile.side_effect = [
            Exception("Search failed"),
            [existing_profile],
        ]

        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="Query 1",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
            ),
            UserProfile(
                profile_id="p2",
                user_id="user",
                profile_content="Query 2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
            ),
        ]
        mock_llm_client.get_embeddings.return_value = [[0.1] * 10, [0.2] * 10]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._retrieve_existing_profiles(
            new_profiles=new_profiles,
            user_id="user",
        )

        # Only the second query succeeded, so 1 profile returned
        assert len(result) == 1
        assert result[0].profile_id == "existing_1"


# ===============================
# Test: _merge_extractor_names
# ===============================


class TestMergeExtractorNames:
    """Tests for merging extractor names from profiles."""

    def test_merge_extractor_names_with_values(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test merging extractor_names from multiple profiles preserves order and removes duplicates."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="content1",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
                extractor_names=["extractor_a", "extractor_b"],
            ),
            UserProfile(
                profile_id="p2",
                user_id="user",
                profile_content="content2",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
                extractor_names=["extractor_b", "extractor_c"],
            ),
        ]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._merge_extractor_names(profiles)

        assert result == ["extractor_a", "extractor_b", "extractor_c"]

    def test_merge_extractor_names_none_returns_none(
        self, mock_request_context, mock_llm_client, mock_site_var_manager
    ):
        """Test that merging profiles with no extractor_names returns None."""
        timestamp = int(datetime.now(UTC).timestamp())
        profiles = [
            UserProfile(
                profile_id="p1",
                user_id="user",
                profile_content="content",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
                extractor_names=None,
            ),
        ]

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result = deduplicator._merge_extractor_names(profiles)
        assert result is None


# ===============================
# Test: deduplicate() uncovered branches
# ===============================


class TestDeduplicateEdgeCases:
    """Tests for uncovered branches in the deduplicate() method."""

    def test_deduplicate_unexpected_response_type(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that unexpected response type from LLM returns original profiles."""
        # Return a string instead of ProfileDeduplicationOutput
        mock_llm_client.generate_chat_response.return_value = "unexpected string"

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        profiles, delete_ids, superseded = deduplicator.deduplicate(
            new_profiles=sample_profiles,
            user_id="test_user",
            request_id="test_request",
        )

        assert profiles == sample_profiles
        assert delete_ids == []
        assert superseded == []

    def test_build_results_invalid_item_id_in_group_skipped(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that invalid item IDs in duplicate groups are gracefully skipped."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "GARBAGE", "NEW-1"],
                    merged_content="Merged despite invalid ID",
                    merged_time_to_live="one_month",
                    reasoning="group with bad id",
                )
            ],
            unique_ids=["NEW-2"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=sample_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        # 1 merged (from valid NEW-0 + NEW-1) + 1 unique (NEW-2)
        assert len(result_profiles) == 2

    def test_build_results_invalid_item_id_in_unique_ids_skipped(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
        sample_profiles,
    ):
        """Test that invalid item IDs in unique_ids are gracefully skipped."""
        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="Merged content",
                    merged_time_to_live="one_month",
                    reasoning="group",
                )
            ],
            unique_ids=["NEW-2", "BADFORMAT", "INVALID-5"],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=sample_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        # 1 merged + 1 valid unique (NEW-2); invalid IDs skipped
        assert len(result_profiles) == 2

    def test_build_results_extractor_names_merged_in_group(
        self,
        mock_request_context,
        mock_llm_client,
        mock_site_var_manager,
    ):
        """Test that extractor_names are properly merged for grouped profiles (covers lines 508-511)."""
        timestamp = int(datetime.now(UTC).timestamp())
        new_profiles = [
            UserProfile(
                profile_id="p1",
                user_id="test_user",
                profile_content="Content A",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req1",
                profile_time_to_live=ProfileTimeToLive.ONE_MONTH,
                source="src_a",
                extractor_names=["ext_a", "ext_b"],
            ),
            UserProfile(
                profile_id="p2",
                user_id="test_user",
                profile_content="Content B",
                last_modified_timestamp=timestamp,
                generated_from_request_id="req2",
                profile_time_to_live=ProfileTimeToLive.ONE_WEEK,
                source="src_b",
                extractor_names=["ext_b", "ext_c"],
            ),
        ]

        dedup_output = ProfileDeduplicationOutput(
            duplicate_groups=[
                ProfileDuplicateGroup(
                    item_ids=["NEW-0", "NEW-1"],
                    merged_content="Merged content",
                    merged_time_to_live="one_month",
                    reasoning="duplicates",
                )
            ],
            unique_ids=[],
        )

        deduplicator = ProfileDeduplicator(
            request_context=mock_request_context,
            llm_client=mock_llm_client,
        )
        result_profiles, _, _ = deduplicator._build_deduplicated_results(
            new_profiles=new_profiles,
            existing_profiles=[],
            dedup_output=dedup_output,
            user_id="test_user",
            request_id="test_request",
        )

        assert len(result_profiles) == 1
        merged = result_profiles[0]
        # extractor_names merged and deduplicated, preserving order
        assert merged.extractor_names == ["ext_a", "ext_b", "ext_c"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
