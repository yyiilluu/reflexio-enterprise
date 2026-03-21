"""
Tests for Pydantic validators in reflexio_commons.

Covers:
1. SSRF prevention (SafeHttpUrl) — cloud metadata, private IPs, localhost
2. Prompt injection mitigation (SanitizedStr) — control character stripping
3. Data integrity (NonEmptyStr, EmbeddingVector, numeric constraints)
4. Time range validation
5. Email validation
6. Cross-field model validators
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from reflexio_commons.api_schema.login_schema import (
    ForgotPasswordRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    User,
    VerifyEmailRequest,
)
from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    GetDashboardStatsRequest,
    GetInteractionsRequest,
    GetRawFeedbacksRequest,
    GetRequestsRequest,
    PeriodStats,
    SearchInteractionRequest,
    SearchUserProfileRequest,
    TimeSeriesDataPoint,
)
from reflexio_commons.api_schema.service_schemas import (
    AddFeedbackRequest,
    AddRawFeedbackRequest,
    DeleteFeedbackRequest,
    DeleteRawFeedbackRequest,
    DeleteRequestRequest,
    DeleteSkillRequest,
    DeleteUserInteractionRequest,
    Feedback,
    Interaction,
    InteractionData,
    OperationStatus,
    OperationStatusInfo,
    PublishUserInteractionRequest,
    RerunFeedbackGenerationRequest,
    RerunProfileGenerationRequest,
    Skill,
    UpdateSkillStatusRequest,
    UserProfile,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    AgentSuccessConfig,
    AnthropicConfig,
    AzureOpenAIConfig,
    Config,
    CustomEndpointConfig,
    FeedbackAggregatorConfig,
    OpenAIConfig,
    ProfileExtractorConfig,
    SkillGeneratorConfig,
    StorageConfigLocal,
    ToolUseConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def strict_mode(monkeypatch):
    """Enable strict URL validation mode (blocks private IPs and localhost)."""
    monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "true")


@pytest.fixture
def non_strict_mode(monkeypatch):
    """Ensure strict URL validation mode is disabled."""
    monkeypatch.delenv("REFLEXIO_BLOCK_PRIVATE_URLS", raising=False)


# =============================================================================
# SSRF Prevention Tests — SafeHttpUrl
# =============================================================================


class TestSSRFPrevention:
    """Tests for SSRF prevention via SafeHttpUrl on config models."""

    def test_always_blocks_aws_metadata_ip(self):
        """Cloud metadata IP 169.254.169.254 is ALWAYS blocked."""
        with pytest.raises(ValidationError, match="cloud metadata"):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://169.254.169.254/latest"
            )

    def test_always_blocks_gcp_metadata_hostname(self):
        """GCP metadata hostname is ALWAYS blocked."""
        with pytest.raises(ValidationError, match="cloud metadata"):
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://metadata.google.internal/computeMetadata/v1",
            )

    def test_allows_public_urls(self):
        """Public URLs are always accepted."""
        config = CustomEndpointConfig(
            model="gpt-4", api_key="sk-test", api_base="https://api.openai.com/v1"
        )
        assert str(config.api_base).startswith("https://api.openai.com")

    def test_allows_localhost_by_default(self, non_strict_mode):
        """Localhost is allowed when REFLEXIO_BLOCK_PRIVATE_URLS is not set."""
        config = CustomEndpointConfig(
            model="local-model", api_key="k", api_base="http://localhost:8080/v1"
        )
        assert "localhost" in str(config.api_base)

    def test_allows_private_ip_by_default(self, non_strict_mode):
        """Private IPs are allowed when REFLEXIO_BLOCK_PRIVATE_URLS is not set."""
        config = CustomEndpointConfig(
            model="local-model", api_key="k", api_base="http://192.168.1.100:8080/v1"
        )
        assert "192.168.1.100" in str(config.api_base)

    def test_blocks_localhost_in_strict_mode(self, strict_mode):
        """Localhost is blocked when REFLEXIO_BLOCK_PRIVATE_URLS=true."""
        with pytest.raises(ValidationError, match="localhost"):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://localhost:8080/v1"
            )

    def test_blocks_private_ip_in_strict_mode(self, strict_mode):
        """Private IPs are blocked when REFLEXIO_BLOCK_PRIVATE_URLS=true."""
        with pytest.raises(ValidationError, match="private"):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://192.168.1.1/v1"
            )

    def test_blocks_loopback_ip_in_strict_mode(self, strict_mode):
        """Loopback IP 127.0.0.1 is blocked in strict mode."""
        with pytest.raises(ValidationError):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://127.0.0.1:8080/v1"
            )

    def test_azure_endpoint_ssrf_prevention(self):
        """AzureOpenAIConfig.endpoint is also protected against SSRF."""
        with pytest.raises(ValidationError, match="cloud metadata"):
            AzureOpenAIConfig(
                api_key="test-key",
                endpoint="http://169.254.169.254/latest/meta-data/",
            )

    def test_azure_endpoint_allows_valid_url(self):
        """Valid Azure endpoints are accepted."""
        config = AzureOpenAIConfig(
            api_key="test-key",
            endpoint="https://my-resource.openai.azure.com/",
        )
        assert "openai.azure.com" in str(config.endpoint)


# =============================================================================
# Image URL SSRF Tests
# =============================================================================


class TestImageURLSSRF:
    """Tests for SSRF prevention on interacted_image_url."""

    def test_empty_image_url_allowed(self):
        """Empty string is the default and should be allowed."""
        data = InteractionData(interacted_image_url="")
        assert data.interacted_image_url == ""

    def test_blocks_file_scheme(self):
        """file:// scheme is blocked."""
        with pytest.raises(ValidationError, match="scheme must be http"):
            InteractionData(interacted_image_url="file:///etc/passwd")

    def test_blocks_ftp_scheme(self):
        """ftp:// scheme is blocked."""
        with pytest.raises(ValidationError, match="scheme must be http"):
            InteractionData(interacted_image_url="ftp://evil.com/image.png")

    def test_allows_data_uri(self):
        """data: URIs are allowed for inline images."""
        data = InteractionData(
            interacted_image_url="data:image/png;base64,iVBORw0KGgo="
        )
        assert data.interacted_image_url.startswith("data:image/png")

    def test_allows_https_url(self):
        """Public HTTPS URLs are allowed."""
        data = InteractionData(interacted_image_url="https://example.com/image.png")
        assert "example.com" in data.interacted_image_url

    def test_blocks_metadata_ip_in_image_url(self):
        """Cloud metadata IP is blocked in image URLs."""
        with pytest.raises(ValidationError, match="cloud metadata"):
            InteractionData(
                interacted_image_url="http://169.254.169.254/latest/meta-data/"
            )

    def test_interaction_model_also_validates(self):
        """Interaction entity model also validates image URLs."""
        with pytest.raises(ValidationError, match="scheme must be http"):
            Interaction(
                user_id="test",
                request_id="req-1",
                interacted_image_url="file:///etc/passwd",
            )


# =============================================================================
# Prompt Injection Mitigation Tests — SanitizedStr
# =============================================================================


class TestPromptInjectionMitigation:
    """Tests for control character stripping in prompt fields."""

    def test_strips_null_bytes(self):
        """NULL bytes (\x00) are stripped from prompt fields."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="Extract\x00preferences",
        )
        assert "\x00" not in config.profile_content_definition_prompt
        assert config.profile_content_definition_prompt == "Extractpreferences"

    def test_strips_escape_sequences(self):
        """Escape sequences (\x1b) are stripped from prompt fields."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="Hello\x1b[31mRED\x1b[0m",
        )
        assert "\x1b" not in config.profile_content_definition_prompt

    def test_preserves_tabs_and_newlines(self):
        """Tabs and newlines are legitimate and preserved."""
        prompt = "Step 1:\tDo this\nStep 2:\tDo that"
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt=prompt,
        )
        assert "\t" in config.profile_content_definition_prompt
        assert "\n" in config.profile_content_definition_prompt

    def test_strips_bell_character(self):
        """Bell character (\x07) is stripped."""
        config = AgentFeedbackConfig(
            feedback_name="test",
            feedback_definition_prompt="Alert\x07user",
        )
        assert "\x07" not in config.feedback_definition_prompt

    def test_agent_success_prompt_sanitized(self):
        """AgentSuccessConfig.success_definition_prompt is also sanitized."""
        config = AgentSuccessConfig(
            evaluation_name="test",
            success_definition_prompt="Check\x00success\x1b[0m",
        )
        assert "\x00" not in config.success_definition_prompt
        assert "\x1b" not in config.success_definition_prompt


# =============================================================================
# Data Integrity Tests — NonEmptyStr
# =============================================================================


class TestNonEmptyStr:
    """Tests for NonEmptyStr validation across models."""

    def test_rejects_empty_string(self):
        """Empty string is rejected."""
        with pytest.raises(ValidationError, match="empty"):
            DeleteRequestRequest(request_id="")

    def test_rejects_whitespace_only(self):
        """Whitespace-only string is rejected."""
        with pytest.raises(ValidationError, match="empty"):
            DeleteRequestRequest(request_id="   ")

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        req = DeleteRequestRequest(request_id="  req-123  ")
        assert req.request_id == "req-123"

    def test_accepts_valid_string(self):
        """Valid non-empty string is accepted."""
        req = DeleteRequestRequest(request_id="req-123")
        assert req.request_id == "req-123"

    def test_config_api_key_non_empty(self):
        """API key fields reject empty strings."""
        with pytest.raises(ValidationError, match="empty"):
            AnthropicConfig(api_key="")

    def test_storage_config_non_empty(self):
        """StorageConfigLocal.dir_path rejects empty string."""
        with pytest.raises(ValidationError, match="empty"):
            StorageConfigLocal(dir_path="")

    def test_tool_use_config_non_empty(self):
        """ToolUseConfig fields reject empty strings."""
        with pytest.raises(ValidationError):
            ToolUseConfig(tool_name="", tool_description="test")


# =============================================================================
# Data Integrity Tests — EmbeddingVector
# =============================================================================


class TestEmbeddingVector:
    """Tests for embedding dimension validation."""

    def test_empty_embedding_allowed(self):
        """Empty embedding is allowed (not yet computed)."""
        interaction = Interaction(user_id="test", request_id="req-1", embedding=[])
        assert interaction.embedding == []

    def test_correct_dimension_allowed(self):
        """512-dimension embedding is accepted."""
        embedding = [0.1] * 512
        interaction = Interaction(
            user_id="test", request_id="req-1", embedding=embedding
        )
        assert len(interaction.embedding) == 512

    def test_wrong_dimension_rejected(self):
        """Non-512 non-empty embedding is rejected."""
        with pytest.raises(ValidationError, match="512"):
            Interaction(user_id="test", request_id="req-1", embedding=[1.0, 2.0, 3.0])

    def test_user_profile_embedding_validation(self):
        """UserProfile also validates embedding dimensions."""
        with pytest.raises(ValidationError, match="512"):
            UserProfile(
                profile_id="p1",
                user_id="u1",
                profile_content="test",
                last_modified_timestamp=1000,
                generated_from_request_id="r1",
                embedding=[1.0] * 10,
            )

    def test_feedback_embedding_validation(self):
        """Feedback also validates embedding dimensions."""
        with pytest.raises(ValidationError, match="512"):
            Feedback(
                agent_version="v1",
                feedback_content="test",
                embedding=[1.0] * 100,
            )

    def test_skill_embedding_validation(self):
        """Skill also validates embedding dimensions."""
        with pytest.raises(ValidationError, match="512"):
            Skill(
                skill_name="test",
                embedding=[1.0] * 256,
            )


# =============================================================================
# Numeric Constraint Tests
# =============================================================================


class TestNumericConstraints:
    """Tests for numeric field constraints."""

    def test_threshold_lower_bound(self):
        """Threshold cannot be below 0.0."""
        with pytest.raises(ValidationError):
            SearchUserProfileRequest(user_id="test", threshold=-0.1)

    def test_threshold_upper_bound(self):
        """Threshold cannot exceed 1.0."""
        with pytest.raises(ValidationError):
            SearchUserProfileRequest(user_id="test", threshold=1.1)

    def test_threshold_boundary_values(self):
        """Threshold boundary values 0.0 and 1.0 are accepted."""
        r1 = SearchUserProfileRequest(user_id="test", threshold=0.0)
        assert r1.threshold == 0.0
        r2 = SearchUserProfileRequest(user_id="test", threshold=1.0)
        assert r2.threshold == 1.0

    def test_top_k_must_be_positive(self):
        """top_k must be > 0."""
        with pytest.raises(ValidationError):
            SearchUserProfileRequest(user_id="test", top_k=0)

    def test_top_k_negative_rejected(self):
        """Negative top_k is rejected."""
        with pytest.raises(ValidationError):
            GetInteractionsRequest(user_id="test", top_k=-5)

    def test_limit_must_be_positive(self):
        """limit must be > 0."""
        with pytest.raises(ValidationError):
            GetRawFeedbacksRequest(limit=0)

    def test_offset_non_negative(self):
        """offset must be >= 0."""
        with pytest.raises(ValidationError):
            GetRequestsRequest(offset=-1)

    def test_offset_zero_allowed(self):
        """offset=0 is allowed."""
        req = GetRequestsRequest(offset=0)
        assert req.offset == 0

    def test_days_back_must_be_positive(self):
        """days_back must be > 0."""
        with pytest.raises(ValidationError):
            GetDashboardStatsRequest(days_back=0)

    def test_delete_id_must_be_positive(self):
        """Delete request IDs must be > 0."""
        with pytest.raises(ValidationError):
            DeleteFeedbackRequest(feedback_id=0)
        with pytest.raises(ValidationError):
            DeleteRawFeedbackRequest(raw_feedback_id=-1)
        with pytest.raises(ValidationError):
            DeleteUserInteractionRequest(user_id="test", interaction_id=0)

    def test_skill_id_must_be_positive(self):
        """Skill IDs in requests must be > 0."""
        with pytest.raises(ValidationError):
            UpdateSkillStatusRequest(skill_id=0, skill_status="published")
        with pytest.raises(ValidationError):
            DeleteSkillRequest(skill_id=-1)

    def test_progress_percentage_range(self):
        """progress_percentage must be 0-100."""
        with pytest.raises(ValidationError):
            OperationStatusInfo(
                service_name="test",
                status=OperationStatus.IN_PROGRESS,
                started_at=1000,
                progress_percentage=101.0,
            )

    def test_sampling_rate_range(self):
        """sampling_rate must be 0.0-1.0."""
        with pytest.raises(ValidationError):
            AgentSuccessConfig(
                evaluation_name="test",
                success_definition_prompt="Check success",
                sampling_rate=1.5,
            )

    def test_period_stats_non_negative(self):
        """PeriodStats counts must be >= 0."""
        with pytest.raises(ValidationError):
            PeriodStats(
                total_profiles=-1,
                total_interactions=0,
                total_feedbacks=0,
                success_rate=50.0,
            )

    def test_success_rate_percentage(self):
        """success_rate must be 0-100."""
        with pytest.raises(ValidationError):
            PeriodStats(
                total_profiles=0,
                total_interactions=0,
                total_feedbacks=0,
                success_rate=150.0,
            )

    def test_timeseries_value_non_negative(self):
        """TimeSeriesDataPoint.value must be >= 0."""
        with pytest.raises(ValidationError):
            TimeSeriesDataPoint(timestamp=1000, value=-1)

    def test_timeseries_timestamp_positive(self):
        """TimeSeriesDataPoint.timestamp must be > 0."""
        with pytest.raises(ValidationError):
            TimeSeriesDataPoint(timestamp=0, value=5)

    def test_feedback_aggregator_config_constraints(self):
        """FeedbackAggregatorConfig thresholds must be >= 1."""
        with pytest.raises(ValidationError):
            FeedbackAggregatorConfig(min_feedback_threshold=0)
        with pytest.raises(ValidationError):
            FeedbackAggregatorConfig(refresh_count=0)

    def test_skill_generator_config_constraints(self):
        """SkillGeneratorConfig numeric fields have valid constraints."""
        with pytest.raises(ValidationError):
            SkillGeneratorConfig(min_feedback_per_cluster=0)
        with pytest.raises(ValidationError):
            SkillGeneratorConfig(cooldown_hours=-1)
        with pytest.raises(ValidationError):
            SkillGeneratorConfig(max_interactions_per_skill=0)
        # cooldown_hours=0 is valid (no cooldown)
        config = SkillGeneratorConfig(cooldown_hours=0)
        assert config.cooldown_hours == 0

    def test_window_override_must_be_positive(self):
        """Window size/stride overrides must be > 0 when set."""
        with pytest.raises(ValidationError):
            ProfileExtractorConfig(
                extractor_name="test",
                profile_content_definition_prompt="test",
                extraction_window_size_override=0,
            )
        with pytest.raises(ValidationError):
            ProfileExtractorConfig(
                extractor_name="test",
                profile_content_definition_prompt="test",
                extraction_window_stride_override=-1,
            )
        # None is allowed (use global setting)
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="test",
            extraction_window_size_override=None,
        )
        assert config.extraction_window_size_override is None


# =============================================================================
# List Minimum Length Tests
# =============================================================================


class TestListMinLength:
    """Tests for minimum list length constraints on request models."""

    def test_publish_interaction_requires_data(self):
        """PublishUserInteractionRequest requires at least one interaction."""
        with pytest.raises(ValidationError):
            PublishUserInteractionRequest(user_id="test", interaction_data_list=[])

    def test_add_raw_feedback_requires_data(self):
        """AddRawFeedbackRequest requires at least one raw feedback."""
        with pytest.raises(ValidationError):
            AddRawFeedbackRequest(raw_feedbacks=[])

    def test_add_feedback_requires_data(self):
        """AddFeedbackRequest requires at least one feedback."""
        with pytest.raises(ValidationError):
            AddFeedbackRequest(feedbacks=[])


# =============================================================================
# Time Range Validation Tests
# =============================================================================


class TestTimeRangeValidation:
    """Tests for time range validation on request models."""

    def test_end_before_start_rejected(self):
        """end_time before start_time is rejected."""
        with pytest.raises(ValidationError, match="end_time must be after"):
            RerunProfileGenerationRequest(
                start_time=datetime(2024, 6, 1, tzinfo=UTC),
                end_time=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_equal_times_rejected(self):
        """Equal start_time and end_time is rejected."""
        same_time = datetime(2024, 6, 1, tzinfo=UTC)
        with pytest.raises(ValidationError, match="end_time must be after"):
            RerunProfileGenerationRequest(start_time=same_time, end_time=same_time)

    def test_valid_time_range_accepted(self):
        """Valid time range (end > start) is accepted."""
        req = RerunProfileGenerationRequest(
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 6, 1, tzinfo=UTC),
        )
        assert req.start_time < req.end_time

    def test_none_times_accepted(self):
        """None values for both times are accepted."""
        req = RerunProfileGenerationRequest()
        assert req.start_time is None
        assert req.end_time is None

    def test_only_start_time_accepted(self):
        """Only start_time without end_time is accepted."""
        req = SearchInteractionRequest(
            user_id="test",
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert req.start_time is not None
        assert req.end_time is None

    def test_rerun_feedback_time_range(self):
        """RerunFeedbackGenerationRequest also validates time range."""
        with pytest.raises(ValidationError, match="end_time must be after"):
            RerunFeedbackGenerationRequest(
                agent_version="v1",
                start_time=datetime(2024, 6, 1, tzinfo=UTC),
                end_time=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_search_interaction_time_range(self):
        """SearchInteractionRequest validates time range."""
        with pytest.raises(ValidationError, match="end_time must be after"):
            SearchInteractionRequest(
                user_id="test",
                start_time=datetime(2024, 6, 1, tzinfo=UTC),
                end_time=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_get_requests_time_range(self):
        """GetRequestsRequest validates time range."""
        with pytest.raises(ValidationError, match="end_time must be after"):
            GetRequestsRequest(
                start_time=datetime(2024, 6, 1, tzinfo=UTC),
                end_time=datetime(2024, 1, 1, tzinfo=UTC),
            )


# =============================================================================
# Cross-Field Model Validator Tests
# =============================================================================


class TestCrossFieldValidators:
    """Tests for model-level cross-field validators."""

    def test_openai_config_requires_at_least_one_auth(self):
        """OpenAIConfig requires at least api_key or azure_config."""
        with pytest.raises(ValidationError, match="(?i)at least one"):
            OpenAIConfig()

    def test_openai_config_with_api_key(self):
        """OpenAIConfig with only api_key is valid."""
        config = OpenAIConfig(api_key="sk-test")
        assert config.api_key == "sk-test"

    def test_openai_config_with_azure(self):
        """OpenAIConfig with only azure_config is valid."""
        config = OpenAIConfig(
            azure_config=AzureOpenAIConfig(
                api_key="test",
                endpoint="https://my-resource.openai.azure.com/",
            )
        )
        assert config.azure_config is not None

    def test_config_stride_le_window(self):
        """Config: stride must be <= window_size."""
        with pytest.raises(ValidationError, match="stride"):
            Config(
                storage_config=None,
                extraction_window_size=10,
                extraction_window_stride=20,
            )

    def test_config_stride_equal_window_ok(self):
        """Config: stride == window_size is OK."""
        config = Config(
            storage_config=None,
            extraction_window_size=10,
            extraction_window_stride=10,
        )
        assert config.extraction_window_stride == 10

    def test_config_stride_none_ok(self):
        """Config: stride=None (use default) is OK."""
        config = Config(
            storage_config=None,
            extraction_window_size=10,
            extraction_window_stride=None,
        )
        assert config.extraction_window_stride is None


# =============================================================================
# Email Validation Tests
# =============================================================================


class TestEmailValidation:
    """Tests for email validation on login models."""

    def test_valid_email_accepted(self):
        """Valid email addresses are accepted."""
        user = User(email="test@example.com")
        assert user.email == "test@example.com"

    def test_invalid_email_rejected(self):
        """Invalid email addresses are rejected."""
        with pytest.raises(ValidationError):
            User(email="not-an-email")

    def test_email_missing_at_rejected(self):
        """Email without @ is rejected."""
        with pytest.raises(ValidationError):
            User(email="testexample.com")

    def test_resend_verification_email(self):
        """ResendVerificationRequest validates email."""
        with pytest.raises(ValidationError):
            ResendVerificationRequest(email="invalid")

    def test_forgot_password_email(self):
        """ForgotPasswordRequest validates email."""
        with pytest.raises(ValidationError):
            ForgotPasswordRequest(email="")


# =============================================================================
# Login Schema Tests
# =============================================================================


class TestLoginSchema:
    """Tests for login schema validators."""

    def test_token_non_empty(self):
        """Token.api_key and token_type must be non-empty."""
        with pytest.raises(ValidationError):
            Token(api_key="", token_type="bearer")  # noqa: S106
        with pytest.raises(ValidationError):
            Token(api_key="test-key", token_type="")

    def test_verify_token_non_empty(self):
        """VerifyEmailRequest.token must be non-empty."""
        with pytest.raises(ValidationError):
            VerifyEmailRequest(token="  ")  # noqa: S106

    def test_reset_password_min_length(self):
        """ResetPasswordRequest.new_password must have min_length=1."""
        with pytest.raises(ValidationError):
            ResetPasswordRequest(token="valid-token", new_password="")  # noqa: S106


# =============================================================================
# ConversationTurn Tests
# =============================================================================


class TestConversationTurn:
    """Tests for ConversationTurn validation."""

    def test_empty_role_rejected(self):
        """ConversationTurn.role must be non-empty."""
        with pytest.raises(ValidationError):
            ConversationTurn(role="", content="hello")

    def test_empty_content_rejected(self):
        """ConversationTurn.content must be non-empty."""
        with pytest.raises(ValidationError):
            ConversationTurn(role="user", content="")

    def test_valid_turn_accepted(self):
        """Valid ConversationTurn is accepted."""
        turn = ConversationTurn(role="user", content="Hello, how are you?")
        assert turn.role == "user"


# =============================================================================
# SafeHttpUrl — IPv6 and Link-Local IP Tests
# =============================================================================


class TestSSRFIPv6AndLinkLocal:
    """Tests for SSRF prevention with IPv6 addresses and link-local IPs."""

    def test_always_blocks_aws_metadata_ipv6(self):
        """IPv6 cloud metadata address fd00:ec2::254 is ALWAYS blocked."""
        with pytest.raises(ValidationError, match="cloud metadata"):
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://[fd00:ec2::254]/latest",
            )

    def test_blocks_ipv6_loopback_in_strict_mode(self, strict_mode):
        """IPv6 loopback ::1 is blocked in strict mode."""
        with pytest.raises(ValidationError, match="private"):
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://[::1]:8000/v1",
            )

    def test_allows_ipv6_loopback_by_default(self, non_strict_mode):
        """IPv6 loopback ::1 is allowed when strict mode is off."""
        config = CustomEndpointConfig(
            model="x",
            api_key="k",
            api_base="http://[::1]:8000/v1",
        )
        assert config.api_base is not None

    def test_blocks_ipv6_link_local_in_strict_mode(self, strict_mode):
        """IPv6 link-local address (fe80::) is blocked in strict mode."""
        with pytest.raises(ValidationError, match="private"):
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://[fe80::1]:8080/v1",
            )

    def test_blocks_ipv4_link_local_in_strict_mode(self, strict_mode):
        """IPv4 link-local address (169.254.x.x, non-metadata) is blocked in strict mode."""
        with pytest.raises(ValidationError, match="private"):
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://169.254.1.1:8080/v1",
            )

    def test_blocks_zero_address_in_strict_mode(self, strict_mode):
        """0.0.0.0 is blocked in strict mode."""
        with pytest.raises(ValidationError, match="0.0.0.0"):  # noqa: S104
            CustomEndpointConfig(
                model="x",
                api_key="k",
                api_base="http://0.0.0.0:8080/v1",  # noqa: S104
            )


# =============================================================================
# _is_strict_mode Env Var Edge Cases
# =============================================================================


class TestStrictModeEnvVar:
    """Tests for _is_strict_mode with various env var values."""

    def test_strict_mode_true(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=true enables strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "true")
        with pytest.raises(ValidationError):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://localhost:8080/v1"
            )

    def test_strict_mode_one(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=1 enables strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "1")
        with pytest.raises(ValidationError):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://localhost:8080/v1"
            )

    def test_strict_mode_yes(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=yes enables strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "yes")
        with pytest.raises(ValidationError):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://localhost:8080/v1"
            )

    def test_strict_mode_true_uppercase(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=TRUE (uppercase) enables strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "TRUE")
        with pytest.raises(ValidationError):
            CustomEndpointConfig(
                model="x", api_key="k", api_base="http://localhost:8080/v1"
            )

    def test_strict_mode_false_does_not_block(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=false does NOT enable strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "false")
        config = CustomEndpointConfig(
            model="x", api_key="k", api_base="http://localhost:8080/v1"
        )
        assert "localhost" in str(config.api_base)

    def test_strict_mode_empty_string_does_not_block(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS='' does NOT enable strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "")
        config = CustomEndpointConfig(
            model="x", api_key="k", api_base="http://localhost:8080/v1"
        )
        assert "localhost" in str(config.api_base)

    def test_strict_mode_unset_does_not_block(self, monkeypatch):
        """Unset REFLEXIO_BLOCK_PRIVATE_URLS does NOT enable strict mode."""
        monkeypatch.delenv("REFLEXIO_BLOCK_PRIVATE_URLS", raising=False)
        config = CustomEndpointConfig(
            model="x", api_key="k", api_base="http://localhost:8080/v1"
        )
        assert "localhost" in str(config.api_base)

    def test_strict_mode_arbitrary_value_does_not_block(self, monkeypatch):
        """REFLEXIO_BLOCK_PRIVATE_URLS=foobar does NOT enable strict mode."""
        monkeypatch.setenv("REFLEXIO_BLOCK_PRIVATE_URLS", "foobar")
        config = CustomEndpointConfig(
            model="x", api_key="k", api_base="http://localhost:8080/v1"
        )
        assert "localhost" in str(config.api_base)


# =============================================================================
# _strip_control_chars — Specific Control Characters
# =============================================================================


class TestStripControlCharsDetailed:
    """Tests for _strip_control_chars with specific control characters."""

    def test_strips_null_byte(self):
        """NULL byte (\\x00) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="a\x00b",
        )
        assert config.profile_content_definition_prompt == "ab"

    def test_strips_backspace(self):
        """Backspace (\\x08) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="pass\x08word",
        )
        assert config.profile_content_definition_prompt == "password"

    def test_strips_vertical_tab(self):
        """Vertical tab (\\x0b) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="line1\x0bline2",
        )
        assert config.profile_content_definition_prompt == "line1line2"

    def test_strips_form_feed(self):
        """Form feed (\\x0c) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="page1\x0cpage2",
        )
        assert config.profile_content_definition_prompt == "page1page2"

    def test_strips_shift_out(self):
        """Shift Out (\\x0e) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="data\x0emore",
        )
        assert config.profile_content_definition_prompt == "datamore"

    def test_strips_delete_character(self):
        """DEL character (\\x7f) is stripped."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="keep\x7fthis",
        )
        assert config.profile_content_definition_prompt == "keepthis"

    def test_preserves_tab(self):
        """Tab (\\x09) is preserved — it is a legitimate whitespace character."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="col1\tcol2",
        )
        assert "\t" in config.profile_content_definition_prompt

    def test_preserves_newline(self):
        """Newline (\\x0a) is preserved."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="line1\nline2",
        )
        assert "\n" in config.profile_content_definition_prompt

    def test_preserves_carriage_return(self):
        """Carriage return (\\x0d) is preserved."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="line1\r\nline2",
        )
        assert "\r" in config.profile_content_definition_prompt

    def test_strips_multiple_control_chars_at_once(self):
        """Multiple different control characters are all stripped in one pass."""
        config = ProfileExtractorConfig(
            extractor_name="test",
            profile_content_definition_prompt="\x00hello\x07\x08world\x1b\x7f",
        )
        assert config.profile_content_definition_prompt == "helloworld"


# =============================================================================
# EmbeddingVector — Boundary Dimension Tests
# =============================================================================


class TestEmbeddingVectorBoundary:
    """Tests for embedding dimension boundary values (off-by-one)."""

    def test_511_dimensions_rejected(self):
        """511 dimensions (one less than 512) is rejected."""
        with pytest.raises(ValidationError, match="512"):
            Interaction(
                user_id="test", request_id="req-1", embedding=[0.1] * 511
            )

    def test_513_dimensions_rejected(self):
        """513 dimensions (one more than 512) is rejected."""
        with pytest.raises(ValidationError, match="512"):
            Interaction(
                user_id="test", request_id="req-1", embedding=[0.1] * 513
            )

    def test_single_dimension_rejected(self):
        """Single-element embedding (length 1) is rejected."""
        with pytest.raises(ValidationError, match="512"):
            Interaction(
                user_id="test", request_id="req-1", embedding=[0.5]
            )
