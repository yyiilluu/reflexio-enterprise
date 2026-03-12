from datetime import datetime, timezone
import logging
import time
from typing import Any, Optional, TYPE_CHECKING
import uuid
import os

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio_commons.api_schema.service_schemas import (
    UserProfile,
    ProfileChangeLog,
)
from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel

from reflexio_commons.config_schema import ProfileExtractorConfig
from reflexio.server.services.extractor_interaction_utils import (
    get_extractor_window_params,
    get_effective_source_filter,
)
from reflexio.server.services.operation_state_utils import OperationStateManager

if TYPE_CHECKING:
    from reflexio.server.services.profile.profile_generation_service import (
        ProfileGenerationServiceConfig,
    )
from reflexio.server.services.profile.profile_generation_service_utils import (
    ProfileUpdates,
    ProfileUpdateOutput,
    construct_profile_extraction_messages_from_sessions,
    calculate_expiration_timestamp,
    check_string_token_overlap,
)
from reflexio.server.services.service_utils import (
    format_messages_for_logging,
    format_sessions_to_history_string,
    extract_interactions_from_request_interaction_data_models,
    log_model_response,
)
from reflexio.server.services.profile.profile_generation_service_utils import (
    ProfileTimeToLive,
)
from reflexio.server.site_var.site_var_manager import SiteVarManager

logger = logging.getLogger(__name__)
PROFILE_EXTRACTION_TIMEOUT_SECONDS = 300
PROFILE_EXTRACTION_MAX_RETRIES = 2


class ProfileExtractor:
    """
    Extract user profile information from interactions.

    This class analyzes user interactions to identify, update, and manage user profiles,
    including adding new information, removing outdated information, and tracking mentions.
    """

    def __init__(
        self,
        request_context: RequestContext,
        llm_client: LiteLLMClient,
        extractor_config: ProfileExtractorConfig,
        service_config: "ProfileGenerationServiceConfig",
        agent_context: str,
    ):
        """
        Initialize the profile extractor.

        Args:
            request_context: Request context with storage and prompt manager
            llm_client: Unified LLM client supporting both OpenAI and Claude
            extractor_config: Profile extractor configuration from YAML
            service_config: Runtime service configuration with request data
            agent_context: Context about the agent
        """
        self.request_context = request_context
        self.client = llm_client
        self.config: ProfileExtractorConfig = extractor_config
        self.service_config: "ProfileGenerationServiceConfig" = service_config
        self.agent_context = agent_context

        # Get LLM config overrides from configuration
        config = self.request_context.configurator.get_config()
        llm_config = config.llm_config if config else None

        # Get site var as fallback
        self.model_setting = SiteVarManager().get_site_var("llm_model_setting")
        assert isinstance(self.model_setting, dict), "llm_model_setting must be a dict"

        # Use override if present, otherwise fallback to site var
        self.should_run_model_name = (
            llm_config.should_run_model_name
            if llm_config and llm_config.should_run_model_name
            else self.model_setting.get("should_run_model_name", "gpt-5-mini")
        )
        self.default_generation_model_name = (
            llm_config.generation_model_name
            if llm_config and llm_config.generation_model_name
            else self.model_setting.get("default_generation_model_name", "gpt-5-mini")
        )

    def _create_state_manager(self) -> OperationStateManager:
        """
        Create an OperationStateManager for this extractor.

        Returns:
            OperationStateManager configured for profile_extractor
        """
        return OperationStateManager(
            self.request_context.storage,
            self.request_context.org_id,
            "profile_extractor",
        )

    def _get_interactions(self) -> Optional[list[RequestInteractionDataModel]]:
        """
        Get interactions for this extractor based on its config.

        Handles:
        - Getting window parameters (extractor override or global fallback)
        - Source filtering based on extractor config
        - Time range filtering for rerun flows

        Note: Stride checking is handled upstream by BaseGenerationService._filter_configs_by_stride()
        before the extractor is created.

        Returns:
            List of request interaction data models, or None if source filter skips this extractor
        """
        # Get global config values
        config = self.request_context.configurator.get_config()
        global_window_size = (
            getattr(config, "extraction_window_size", None) if config else None
        )
        global_stride = (
            getattr(config, "extraction_window_stride", None) if config else None
        )

        # Get effective window size for this extractor
        window_size, _ = get_extractor_window_params(
            self.config,
            global_window_size,
            global_stride,
        )

        # Get effective source filter (None = get ALL sources)
        should_skip, effective_source = get_effective_source_filter(
            self.config,
            self.service_config.source,
        )
        if should_skip:
            return None

        storage = self.request_context.storage

        # Get window interactions with time range filter
        session_data_models, _ = storage.get_last_k_interactions_grouped(
            user_id=self.service_config.user_id,
            k=window_size,
            sources=effective_source,
            start_time=self.service_config.rerun_start_time,
            end_time=self.service_config.rerun_end_time,
        )
        return session_data_models

    def _update_operation_state(
        self, request_interaction_data_models: list[RequestInteractionDataModel]
    ) -> None:
        """
        Update operation state after processing interactions.

        Args:
            request_interaction_data_models: The interactions that were processed
        """
        all_interactions = extract_interactions_from_request_interaction_data_models(
            request_interaction_data_models
        )
        mgr = self._create_state_manager()
        mgr.update_extractor_bookmark(
            extractor_name=self.config.extractor_name,
            processed_interactions=all_interactions,
            user_id=self.service_config.user_id,
        )

    def run(self) -> Optional[ProfileUpdates]:
        """
        Extract profile updates from request interaction groups.

        This extractor handles its own data collection:
        1. Gets interactions based on its config (window size, source filtering)
        2. Applies time range filter for rerun flows
        3. Updates operation state after processing

        Returns:
            Optional[ProfileUpdates]: Profile updates/changes log, or None if no updates
        """
        # Collect interactions using extractor's own window/stride settings
        request_interaction_data_models = self._get_interactions()
        if not request_interaction_data_models:
            # No interactions or stride not met
            return None

        existing_profiles = self.service_config.existing_data

        # should_extract check is handled at the service level (consolidated across all extractors)

        try:
            raw_updates = self._generate_raw_updates_from_sessions(
                request_interaction_data_models=request_interaction_data_models,
                existing_profiles=existing_profiles,
            )
        except Exception as e:
            logger.error(
                "event=profile_extract_failed user_id=%s extractor_name=%s error_type=%s error=%s",
                self.service_config.user_id,
                self.config.extractor_name,
                type(e).__name__,
                str(e),
            )
            # Do not advance bookmark on extraction failure.
            # Keeping the bookmark unchanged allows the same interactions to be
            # retried on subsequent runs after transient LLM/provider issues.
            raise RuntimeError(
                f"Profile extraction failed for user {self.service_config.user_id}"
            ) from e

        logger.info("Generated raw updates: %s", raw_updates)
        if raw_updates:
            profile_updates = self._get_profile_updates_from_existing_profiles(
                user_id=self.service_config.user_id,
                request_id=self.service_config.request_id,
                existing_profiles=existing_profiles,
                profile_updates=raw_updates,
            )

            # Update operation state after successful processing
            self._update_operation_state(request_interaction_data_models)

            return profile_updates
        return None

    def _get_profile_updates_from_existing_profiles(
        self,
        user_id: str,
        request_id: str,
        existing_profiles: list[UserProfile],
        profile_updates: dict[str, Any],
    ) -> ProfileUpdates | None:
        """get profile updates from existing profiles

        Args:
            user_id (str): user id
            request_id (str): request id
            existing_profiles (list[UserProfile]): existing profiles
            profile_updates (dict[str, Any]): profile updates

        Returns:
            ProfileUpdates | None: profile updates/changes log
        """
        new_profiles = []
        tobe_removed_profiles = []
        mention_profiles = []
        for update_type, update_content in profile_updates.items():
            if update_type == "add":
                for profile_content in update_content:
                    if (
                        not isinstance(profile_content, dict)
                        or "content" not in profile_content
                    ):
                        logger.warning("Invalid profile content: %s", profile_content)
                        continue

                    # Get all custom features by excluding content and time_to_live
                    custom_features = {
                        k: v
                        for k, v in profile_content.items()
                        if k not in ["content", "time_to_live"]
                    }

                    added_profile = UserProfile(
                        profile_id=str(uuid.uuid4()),
                        user_id=user_id,
                        profile_content=profile_content["content"],
                        last_modified_timestamp=int(
                            datetime.now(timezone.utc).timestamp()
                        ),
                        generated_from_request_id=request_id,
                        profile_time_to_live=ProfileTimeToLive(
                            profile_content.get("time_to_live", "infinity")
                        ),
                        expiration_timestamp=calculate_expiration_timestamp(
                            int(
                                datetime.now(timezone.utc).timestamp()
                            ),  # Convert float to int
                            ProfileTimeToLive(
                                profile_content.get("time_to_live", "infinity")
                            ),
                        ),
                        custom_features=custom_features,
                        extractor_names=[self.config.extractor_name],
                    )

                    new_profiles.append(added_profile)
            elif update_type == "delete":
                if not update_content:
                    continue
                tobe_removed_profiles = [
                    profile
                    for profile in existing_profiles
                    if any(
                        check_string_token_overlap(profile.profile_content, content)
                        for content in update_content
                    )
                ]
            elif update_type == "mention":
                if not update_content:
                    continue
                for profile in existing_profiles:
                    if any(
                        check_string_token_overlap(profile.profile_content, content)
                        for content in update_content
                    ):
                        profile.last_modified_timestamp = int(
                            datetime.now(timezone.utc).timestamp()
                        )
                        profile.generated_from_request_id = request_id
                        profile.expiration_timestamp = calculate_expiration_timestamp(
                            profile.last_modified_timestamp,
                            profile.profile_time_to_live,
                        )
                        mention_profiles.append(profile)

        if not new_profiles and not tobe_removed_profiles and not mention_profiles:
            return None

        # Rename variable to avoid confusion with parameter name
        profile_updates_result = ProfileUpdates(
            add_profiles=new_profiles,
            delete_profiles=tobe_removed_profiles,
            mention_profiles=mention_profiles,
        )

        # update profile change log to db
        profile_change_log = ProfileChangeLog(
            id=0,  # This will be auto-generated by the storage
            user_id=user_id,
            request_id=request_id,
            created_at=int(datetime.now(timezone.utc).timestamp()),
            added_profiles=new_profiles,
            removed_profiles=tobe_removed_profiles,
            mentioned_profiles=mention_profiles,
        )

        self.request_context.storage.add_profile_change_log(profile_change_log)

        return profile_updates_result

    def _generate_raw_updates_from_sessions(
        self,
        request_interaction_data_models: list[RequestInteractionDataModel],
        existing_profiles: list[UserProfile],
    ) -> dict[str, Any]:
        """
        Generate raw profile updates from request interaction groups.

        Args:
            request_interaction_data_models: List of request interaction groups
            existing_profiles: List of existing user profiles

        Returns:
            dict[str, Any]: Raw profile updates with add/delete/mention operations
        """
        # Check if mock mode is enabled
        mock_env_for_raw = os.getenv("MOCK_LLM_RESPONSE", "")
        if mock_env_for_raw.lower() == "true":
            # Return mock profile updates based on interactions
            return self._generate_profile_updates_from_sessions(
                request_interaction_data_models=request_interaction_data_models,
                existing_profiles=existing_profiles,
            )

        # get user profile prompt from configurator or use the default prompt
        if self.service_config.is_incremental:
            from reflexio.server.services.profile.profile_generation_service_utils import (
                construct_incremental_profile_extraction_messages,
            )

            messages = construct_incremental_profile_extraction_messages(
                prompt_manager=self.request_context.prompt_manager,
                request_interaction_data_models=request_interaction_data_models,
                existing_profiles=existing_profiles,
                agent_context_prompt=self.agent_context,
                context_prompt=(
                    self.config.context_prompt.strip()
                    if self.config.context_prompt
                    else ""
                ),
                profile_content_definition_prompt=self.config.profile_content_definition_prompt.strip(),
                previously_extracted=self.service_config.previously_extracted,
                metadata_definition_prompt=(
                    self.config.metadata_definition_prompt.strip()
                    if self.config.metadata_definition_prompt
                    else None
                ),
            )
        else:
            messages = construct_profile_extraction_messages_from_sessions(
                prompt_manager=self.request_context.prompt_manager,
                request_interaction_data_models=request_interaction_data_models,
                agent_context_prompt=self.agent_context,
                context_prompt=(
                    self.config.context_prompt.strip()
                    if self.config.context_prompt
                    else ""
                ),
                profile_content_definition_prompt=self.config.profile_content_definition_prompt.strip(),
                metadata_definition_prompt=(
                    self.config.metadata_definition_prompt.strip()
                    if self.config.metadata_definition_prompt
                    else None
                ),
                existing_profiles=existing_profiles,
            )
        # Messages are already in dict format from construct_messages_from_interactions
        messages_dict = messages
        session_count = len(request_interaction_data_models)
        interaction_count = sum(
            len(data_model.interactions)
            for data_model in request_interaction_data_models
        )
        history_chars = len(
            format_sessions_to_history_string(request_interaction_data_models)
        )
        logger.info(
            "event=profile_extract_llm_start user_id=%s extractor_name=%s sessions=%d interactions=%d history_chars=%d existing_profiles=%d model=%s timeout=%d max_retries=%d response_format=%s",
            self.service_config.user_id,
            self.config.extractor_name,
            session_count,
            interaction_count,
            history_chars,
            len(existing_profiles),
            self.default_generation_model_name,
            PROFILE_EXTRACTION_TIMEOUT_SECONDS,
            PROFILE_EXTRACTION_MAX_RETRIES,
            True,
        )

        logger.info(
            "Profile extraction messages: %s",
            format_messages_for_logging(messages_dict),
        )

        # Use ProfileUpdateOutput schema for structured output
        extract_start = time.perf_counter()
        try:
            update_response = self.client.generate_chat_response(
                messages=messages_dict,
                model=self.default_generation_model_name,
                response_format=ProfileUpdateOutput,
                timeout=PROFILE_EXTRACTION_TIMEOUT_SECONDS,
                max_retries=PROFILE_EXTRACTION_MAX_RETRIES,
            )
        except Exception as exc:
            elapsed_seconds = time.perf_counter() - extract_start
            logger.error(
                "event=profile_extract_llm_end user_id=%s extractor_name=%s model=%s timeout=%d max_retries=%d elapsed_seconds=%.3f success=%s error_type=%s error=%s",
                self.service_config.user_id,
                self.config.extractor_name,
                self.default_generation_model_name,
                PROFILE_EXTRACTION_TIMEOUT_SECONDS,
                PROFILE_EXTRACTION_MAX_RETRIES,
                elapsed_seconds,
                False,
                type(exc).__name__,
                str(exc),
            )
            raise

        log_model_response(logger, "Profile updates model response", update_response)
        if not update_response or not isinstance(update_response, ProfileUpdateOutput):
            elapsed_seconds = time.perf_counter() - extract_start
            logger.info(
                "event=profile_extract_llm_end user_id=%s extractor_name=%s model=%s timeout=%d max_retries=%d elapsed_seconds=%.3f success=%s response_type=%s add_count=%d delete_count=%d mention_count=%d",
                self.service_config.user_id,
                self.config.extractor_name,
                self.default_generation_model_name,
                PROFILE_EXTRACTION_TIMEOUT_SECONDS,
                PROFILE_EXTRACTION_MAX_RETRIES,
                elapsed_seconds,
                False,
                type(update_response).__name__,
                0,
                0,
                0,
            )
            return {}

        elapsed_seconds = time.perf_counter() - extract_start
        logger.info(
            "event=profile_extract_llm_end user_id=%s extractor_name=%s model=%s timeout=%d max_retries=%d elapsed_seconds=%.3f success=%s response_type=%s add_count=%d delete_count=%d mention_count=%d",
            self.service_config.user_id,
            self.config.extractor_name,
            self.default_generation_model_name,
            PROFILE_EXTRACTION_TIMEOUT_SECONDS,
            PROFILE_EXTRACTION_MAX_RETRIES,
            elapsed_seconds,
            True,
            type(update_response).__name__,
            len(update_response.add or []),
            len(update_response.delete or []),
            len(update_response.mention or []),
        )

        # Convert Pydantic model to dict for downstream processing
        update_response = update_response.model_dump()

        if self._has_profile_update_actions(update_response):
            return update_response
        else:
            logger.warning(
                "Profile extraction response could not be parsed into actions"
            )
            return {}

    def _has_profile_update_actions(self, updates: dict[str, Any]) -> bool:
        """
        Determine whether the parsed updates contain any actionable profile operations.
        """
        if not updates:
            return False

        actionable_keys = {"add", "delete", "mention"}
        for key in actionable_keys:
            if key in updates and updates.get(key):
                return True
        return False

    def _generate_profile_updates_from_sessions(
        self,
        request_interaction_data_models: list[RequestInteractionDataModel],
        existing_profiles: list[UserProfile],
    ) -> dict[str, Any]:
        """
        Generate heuristic profile updates based on recent request interaction groups.

        This is used both in mock mode and as a fallback when LLM responses are not
        parseable. The content mirrors the expected structure from the prompt.

        Args:
            request_interaction_data_models: List of request interaction groups
            existing_profiles: List of existing user profiles

        Returns:
            dict[str, Any]: Mock profile updates in the expected format
        """
        # Extract flat interactions from sessions
        interactions = extract_interactions_from_request_interaction_data_models(
            request_interaction_data_models
        )

        # Analyze interactions to generate realistic mock updates
        mock_updates = {}

        # Extract some sample content from interactions for realistic mocks
        if interactions:
            sample_content = (
                interactions[-1].content[:50]
                if interactions[-1].content
                else "sample interaction"
            )

            # Capture additional context that contains helpful keywords (e.g. product mentions)
            highlight_keywords = {
                "software",
                "solution",
                "product",
                "company",
                "service",
            }
            highlighted_snippet = next(
                (
                    interaction.content[:80]
                    for interaction in reversed(interactions)
                    if interaction.content
                    and any(
                        keyword in interaction.content.lower()
                        for keyword in highlight_keywords
                    )
                ),
                "",
            )

            summary_parts = [f"User mentioned: {sample_content}"]
            if highlighted_snippet and highlighted_snippet not in sample_content:
                summary_parts.append(f"Key context: {highlighted_snippet}")

            # Add a new profile based on the interaction
            mock_updates["add"] = [
                {
                    "content": " ".join(summary_parts),
                    "time_to_live": "one_month",
                }
            ]

            # If metadata definition exists, add mock metadata
            if self.config.metadata_definition_prompt:
                mock_updates["add"][0]["metadata"] = "mock_metadata_value"

        # Check for profile mentions (if existing profiles exist)
        if existing_profiles and len(existing_profiles) > 0:
            # Mock a mention of an existing profile
            mock_updates["mention"] = [existing_profiles[0].profile_content]

        return mock_updates
