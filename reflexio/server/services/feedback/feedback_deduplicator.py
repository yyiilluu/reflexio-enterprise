"""
Feedback deduplication service that merges duplicate feedbacks using LLM
and hybrid search against existing feedbacks in the database.
"""

import logging
import os
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from reflexio_commons.api_schema.service_schemas import RawFeedback
from reflexio_commons.config_schema import EMBEDDING_DIMENSIONS

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.deduplication_utils import (
    BaseDeduplicator,
    parse_item_id,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    StructuredFeedbackContent,
    format_structured_feedback_content,
)

logger = logging.getLogger(__name__)


# ===============================
# Feedback-specific Pydantic Output Schemas for LLM
# ===============================


class FeedbackDeduplicationDuplicateGroup(BaseModel):
    """A group of duplicate feedbacks to merge, with old feedbacks to delete."""

    item_ids: list[str] = Field(
        description="IDs of items in this group matching prompt format (e.g., 'NEW-0', 'EXISTING-1')"
    )
    merged_content: StructuredFeedbackContent = Field(
        description="Consolidated feedback in structured format (do_action, do_not_action, when_condition, blocking_issue)"
    )
    reasoning: str = Field(description="Brief explanation of the merge decision")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )


class FeedbackDeduplicationOutput(BaseModel):
    """Output schema for feedback deduplication with NEW vs EXISTING merge support."""

    duplicate_groups: list[FeedbackDeduplicationDuplicateGroup] = Field(
        default=[], description="Groups of duplicate feedbacks to merge"
    )
    unique_ids: list[str] = Field(
        default=[], description="IDs of unique NEW feedbacks (e.g., 'NEW-2')"
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
    )


class FeedbackDeduplicator(BaseDeduplicator):
    """
    Deduplicates new feedbacks against each other and against existing feedbacks
    in the database using hybrid search (vector + FTS) and LLM-based merging.
    """

    DEDUPLICATION_PROMPT_ID = "feedback_deduplication"

    def __init__(
        self,
        request_context: RequestContext,
        llm_client: LiteLLMClient,
    ):
        """
        Initialize the feedback deduplicator.

        Args:
            request_context: Request context with storage and prompt manager
            llm_client: Unified LLM client for LLM calls
        """
        super().__init__(request_context, llm_client)

    def _get_prompt_id(self) -> str:
        """Get the prompt ID for feedback deduplication."""
        return self.DEDUPLICATION_PROMPT_ID

    def _get_item_count_key(self) -> str:
        """Get the key name for item count in prompt variables."""
        return "new_feedback_count"

    def _get_items_key(self) -> str:
        """Get the key name for items in prompt variables."""
        return "new_feedbacks"

    def _get_output_schema_class(self) -> type[BaseModel]:
        """Return FeedbackDeduplicationOutput for new/existing merge."""
        return FeedbackDeduplicationOutput

    def _format_items_for_prompt(self, feedbacks: list[RawFeedback]) -> str:
        """
        Format feedbacks list for LLM prompt with NEW-N prefix.

        Args:
            feedbacks: List of feedbacks

        Returns:
            Formatted string representation
        """
        return self._format_feedbacks_with_prefix(feedbacks, "NEW")

    def _format_feedbacks_with_prefix(
        self, feedbacks: list[RawFeedback], prefix: str
    ) -> str:
        """
        Format feedbacks with a given prefix (NEW or EXISTING).

        Args:
            feedbacks: List of feedbacks to format
            prefix: Prefix string for indices

        Returns:
            Formatted string
        """
        if not feedbacks:
            return "(None)"
        lines = []
        for idx, feedback in enumerate(feedbacks):
            feedback_name = feedback.feedback_name or "unknown"
            source = feedback.source or "unknown"
            lines.append(
                f'[{prefix}-{idx}] Content: "{feedback.feedback_content}" | Name: {feedback_name} | Source: {source}'
            )
        return "\n".join(lines)

    def _retrieve_existing_feedbacks(
        self,
        new_feedbacks: list[RawFeedback],
        user_id: str | None = None,
        agent_version: str | None = None,
    ) -> list[RawFeedback]:
        """
        Retrieve existing feedbacks from the database using hybrid search.

        For each new feedback, uses its when_condition as the query with
        pre-computed embeddings for vector search.

        Args:
            new_feedbacks: List of new feedbacks to search against
            user_id: Optional user ID to scope the search
            agent_version: Optional agent version to scope the search

        Returns:
            Deduplicated list of existing RawFeedback objects from the database
        """
        storage = self.request_context.storage

        # Collect when_condition strings for embedding
        query_texts = []
        for feedback in new_feedbacks:
            when_condition = feedback.when_condition or feedback.feedback_content
            if when_condition and when_condition.strip():
                query_texts.append(when_condition.strip())

        if not query_texts:
            return []

        # Batch-generate embeddings
        try:
            embeddings = self.client.get_embeddings(
                query_texts, dimensions=EMBEDDING_DIMENSIONS
            )
        except Exception as e:
            logger.warning("Failed to generate embeddings for dedup search: %s", e)
            # Fall back to text-only search
            embeddings = [None] * len(query_texts)

        # Search for each new feedback
        seen_ids: set[int] = set()
        existing_feedbacks: list[RawFeedback] = []

        for i, query_text in enumerate(query_texts):
            try:
                results = storage.search_raw_feedbacks(  # type: ignore[reportOptionalMemberAccess]
                    query=query_text,
                    query_embedding=embeddings[i],
                    user_id=user_id,
                    agent_version=agent_version,
                    status_filter=[None],  # Only current feedbacks
                    match_threshold=0.4,
                    match_count=5,
                )
                for fb in results:
                    if fb.raw_feedback_id and fb.raw_feedback_id not in seen_ids:
                        seen_ids.add(fb.raw_feedback_id)
                        existing_feedbacks.append(fb)
            except Exception as e:  # noqa: PERF203
                logger.warning(
                    "Failed to search existing feedbacks for query %d: %s", i, e
                )

        logger.info(
            "Retrieved %d unique existing feedbacks for deduplication",
            len(existing_feedbacks),
        )
        return existing_feedbacks

    def _format_new_and_existing_for_prompt(
        self,
        new_feedbacks: list[RawFeedback],
        existing_feedbacks: list[RawFeedback],
    ) -> tuple[str, str]:
        """
        Format new and existing feedbacks for the deduplication prompt.

        Args:
            new_feedbacks: New feedbacks to deduplicate
            existing_feedbacks: Existing feedbacks from the database

        Returns:
            Tuple of (new_feedbacks_text, existing_feedbacks_text)
        """
        new_text = self._format_feedbacks_with_prefix(new_feedbacks, "NEW")
        existing_text = self._format_feedbacks_with_prefix(
            existing_feedbacks, "EXISTING"
        )
        return new_text, existing_text

    def deduplicate(
        self,
        results: list[list[RawFeedback]],
        request_id: str,
        agent_version: str,
        user_id: str | None = None,
    ) -> tuple[list[RawFeedback], list[int]]:
        """
        Deduplicate feedbacks across extractors and against existing feedbacks in DB.

        Args:
            results: List of feedback lists from extractors (each extractor returns list[RawFeedback])
            request_id: Request ID for context
            agent_version: Agent version for context
            user_id: Optional user ID to scope the existing feedback search

        Returns:
            Tuple of (deduplicated feedbacks, list of existing feedback IDs to delete after save)
        """
        # Check if mock mode is enabled
        if os.getenv("MOCK_LLM_RESPONSE", "").lower() == "true":
            logger.info("Mock mode: skipping deduplication")
            all_feedbacks: list[RawFeedback] = []
            for result in results:
                if isinstance(result, list):
                    all_feedbacks.extend(result)
            return all_feedbacks, []

        # Flatten all new feedbacks
        new_feedbacks: list[RawFeedback] = []
        for result in results:
            if isinstance(result, list):
                new_feedbacks.extend(result)

        if not new_feedbacks:
            return [], []

        # Retrieve existing feedbacks via hybrid search
        existing_feedbacks = self._retrieve_existing_feedbacks(
            new_feedbacks, user_id=user_id, agent_version=agent_version
        )

        # Format for prompt
        new_text, existing_text = self._format_new_and_existing_for_prompt(
            new_feedbacks, existing_feedbacks
        )

        # Build and call LLM
        prompt = self.request_context.prompt_manager.render_prompt(
            self._get_prompt_id(),
            {
                "new_feedback_count": len(new_feedbacks),
                "new_feedbacks": new_text,
                "existing_feedback_count": len(existing_feedbacks),
                "existing_feedbacks": existing_text,
            },
        )

        output_schema_class = self._get_output_schema_class()

        try:
            from reflexio.server.services.service_utils import log_model_response

            logger.info("Deduplication prompt: %s", prompt)

            response = self.client.generate_chat_response(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                response_format=output_schema_class,
            )

            log_model_response(logger, "Deduplication response", response)

            if not isinstance(response, FeedbackDeduplicationOutput):
                logger.warning(
                    "Unexpected response type from deduplication LLM: %s",
                    type(response),
                )
                return new_feedbacks, []

            dedup_output = response
        except Exception as e:
            logger.error("Failed to identify duplicates: %s", str(e))
            return new_feedbacks, []

        if not dedup_output.duplicate_groups:
            logger.info("No duplicate feedbacks found for request %s", request_id)
            return new_feedbacks, []

        logger.info(
            "Found %d duplicate feedback groups for request %s",
            len(dedup_output.duplicate_groups),
            request_id,
        )

        # Build deduplicated result
        return self._build_deduplicated_results(
            new_feedbacks=new_feedbacks,
            existing_feedbacks=existing_feedbacks,
            dedup_output=dedup_output,
            request_id=request_id,
            agent_version=agent_version,
        )

    def _build_deduplicated_results(  # noqa: C901
        self,
        new_feedbacks: list[RawFeedback],
        existing_feedbacks: list[RawFeedback],
        dedup_output: FeedbackDeduplicationOutput,
        request_id: str,
        agent_version: str,  # noqa: ARG002
    ) -> tuple[list[RawFeedback], list[int]]:
        """
        Build the deduplicated feedback list from LLM output.

        Handles merged groups (creating new feedbacks from merged content)
        and unique feedbacks. Returns IDs of existing feedbacks to delete
        so the caller can delete them after save succeeds.

        Args:
            new_feedbacks: Flattened list of new feedbacks
            existing_feedbacks: List of existing feedbacks from DB
            dedup_output: LLM deduplication output
            request_id: Request ID
            agent_version: Agent version

        Returns:
            Tuple of (feedbacks ready to save, existing feedback IDs to delete)
        """
        handled_new_indices: set[int] = set()
        result_feedbacks: list[RawFeedback] = []
        existing_ids_to_delete: list[int] = []
        seen_delete_ids: set[int] = set()

        now_ts = int(datetime.now(timezone.utc).timestamp())

        # Process duplicate groups
        for group in dedup_output.duplicate_groups:
            group_new_indices: list[int] = []
            group_existing_indices: list[int] = []

            for item_id in group.item_ids:
                parsed = parse_item_id(item_id)
                if parsed is None:
                    continue
                prefix, idx = parsed
                if prefix == "NEW":
                    group_new_indices.append(idx)
                    handled_new_indices.add(idx)
                elif prefix == "EXISTING":
                    group_existing_indices.append(idx)

            # Collect existing feedback IDs to delete (deduplicated)
            for eidx in group_existing_indices:
                if 0 <= eidx < len(existing_feedbacks):
                    fb_id = existing_feedbacks[eidx].raw_feedback_id
                    if fb_id and fb_id not in seen_delete_ids:
                        seen_delete_ids.add(fb_id)
                        existing_ids_to_delete.append(fb_id)

            # Get template from first NEW feedback in group (for metadata)
            template_feedback: RawFeedback | None = None
            if group_new_indices:
                first_new_idx = group_new_indices[0]
                if 0 <= first_new_idx < len(new_feedbacks):
                    template_feedback = new_feedbacks[first_new_idx]

            if template_feedback is None:
                # Fallback: use first existing feedback as template
                if group_existing_indices:
                    for eidx in group_existing_indices:
                        if 0 <= eidx < len(existing_feedbacks):
                            template_feedback = existing_feedbacks[eidx]
                            break
                if template_feedback is None:
                    logger.warning(
                        "Could not find template feedback for group, skipping"
                    )
                    continue

            # Combine source_interaction_ids from all NEW feedbacks in group
            combined_source_ids: list[int] = []
            seen_ids: set[int] = set()
            for idx in group_new_indices:
                if 0 <= idx < len(new_feedbacks):
                    for sid in new_feedbacks[idx].source_interaction_ids:
                        if sid not in seen_ids:
                            combined_source_ids.append(sid)
                            seen_ids.add(sid)

            # Also include source_interaction_ids from existing feedbacks being merged
            for eidx in group_existing_indices:
                if 0 <= eidx < len(existing_feedbacks):
                    for sid in existing_feedbacks[eidx].source_interaction_ids:
                        if sid not in seen_ids:
                            combined_source_ids.append(sid)
                            seen_ids.add(sid)

            # Format feedback_content from merged structured content
            merged_content = group.merged_content
            feedback_content = format_structured_feedback_content(merged_content)

            merged_feedback = RawFeedback(
                raw_feedback_id=0,  # Will be assigned by storage
                user_id=template_feedback.user_id,
                agent_version=template_feedback.agent_version,
                request_id=request_id,
                feedback_name=template_feedback.feedback_name,
                created_at=now_ts,
                feedback_content=feedback_content,
                do_action=merged_content.do_action,
                do_not_action=merged_content.do_not_action,
                when_condition=merged_content.when_condition,
                blocking_issue=merged_content.blocking_issue,
                indexed_content=merged_content.when_condition,
                status=template_feedback.status,
                source=template_feedback.source,
                source_interaction_ids=combined_source_ids,
            )
            result_feedbacks.append(merged_feedback)

        # Add unique NEW feedbacks
        for uid in dedup_output.unique_ids:
            parsed = parse_item_id(uid)
            if parsed is None:
                continue
            prefix, idx = parsed
            if (
                prefix == "NEW"
                and idx not in handled_new_indices
                and 0 <= idx < len(new_feedbacks)
            ):
                result_feedbacks.append(new_feedbacks[idx])
                handled_new_indices.add(idx)

        # Safety fallback: add any NEW feedbacks not mentioned by LLM
        for idx, feedback in enumerate(new_feedbacks):
            if idx not in handled_new_indices:
                logger.warning(
                    "New feedback at index %d was not handled by LLM, adding as-is",
                    idx,
                )
                result_feedbacks.append(feedback)

        return result_feedbacks, existing_ids_to_delete
