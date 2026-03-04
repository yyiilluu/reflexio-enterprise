"""
Feedback deduplication service that merges duplicate feedbacks from multiple extractors using LLM.
"""

from datetime import datetime, timezone
import logging

from pydantic import BaseModel

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.deduplication_utils import (
    BaseDeduplicator,
    DeduplicationOutput,
)
from reflexio_commons.api_schema.service_schemas import RawFeedback

logger = logging.getLogger(__name__)


class FeedbackDeduplicator(BaseDeduplicator):
    """
    Deduplicates feedbacks from multiple extractors using LLM-based semantic matching.

    This class identifies duplicate feedbacks (e.g., feedbacks about the same issue from
    different extractors) and merges them into a single consolidated feedback.
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
        return "feedback_count"

    def _get_items_key(self) -> str:
        """Get the key name for items in prompt variables."""
        return "feedbacks"

    def _get_output_schema_class(self) -> type[BaseModel]:
        """Use the standard DeduplicationOutput (no TTL needed for feedbacks)."""
        return DeduplicationOutput

    def _format_items_for_prompt(self, feedbacks: list[RawFeedback]) -> str:
        """
        Format feedbacks list for LLM prompt.

        Args:
            feedbacks: List of feedbacks

        Returns:
            Formatted string representation
        """
        lines = []
        for idx, feedback in enumerate(feedbacks):
            feedback_name = feedback.feedback_name or "unknown"
            source = feedback.source or "unknown"
            lines.append(
                f'[{idx}] Content: "{feedback.feedback_content}" | Name: {feedback_name} | Source: {source}'
            )
        return "\n".join(lines)

    def deduplicate(
        self,
        results: list[list[RawFeedback]],
        request_id: str,
        agent_version: str,
    ) -> list[RawFeedback]:
        """
        Deduplicate feedbacks across multiple extractors.

        Args:
            results: List of feedback lists from extractors (each extractor returns list[RawFeedback])
            request_id: Request ID for context
            agent_version: Agent version for context

        Returns:
            list[RawFeedback]: Deduplicated feedbacks (flat list)
        """
        # Flatten all feedbacks
        all_feedbacks: list[RawFeedback] = []
        for result in results:
            if isinstance(result, list):
                all_feedbacks.extend(result)

        if len(all_feedbacks) < 2:
            # Not enough feedbacks to deduplicate
            return all_feedbacks

        # Call LLM to identify duplicates
        dedup_output = self._identify_duplicates(all_feedbacks)

        if not dedup_output or not dedup_output.duplicate_groups:
            # No duplicates found, return original feedbacks
            logger.info("No duplicate feedbacks found for request %s", request_id)
            return all_feedbacks

        logger.info(
            "Found %d duplicate feedback groups for request %s",
            len(dedup_output.duplicate_groups),
            request_id,
        )

        # Build deduplicated result
        return self._build_deduplicated_results(
            all_feedbacks=all_feedbacks,
            dedup_output=dedup_output,
            request_id=request_id,
            agent_version=agent_version,
        )

    def _build_deduplicated_results(
        self,
        all_feedbacks: list[RawFeedback],
        dedup_output: DeduplicationOutput,
        request_id: str,
        agent_version: str,
    ) -> list[RawFeedback]:
        """
        Build the deduplicated feedback list.

        Args:
            all_feedbacks: Flattened list of all feedbacks
            dedup_output: LLM deduplication output
            request_id: Request ID
            agent_version: Agent version

        Returns:
            Deduplicated feedback list
        """
        # Track which feedbacks have been handled
        handled_indices = set()

        # Create merged feedbacks list
        merged_feedbacks: list[RawFeedback] = []

        # Process duplicate groups - create merged feedbacks
        for group in dedup_output.duplicate_groups:
            handled_indices.update(group.item_indices)

            # Get the first feedback as template for metadata
            # (feedback_name, agent_version, status, source are taken from first)
            template_feedback = all_feedbacks[group.item_indices[0]]

            # Create merged feedback
            now_ts = int(datetime.now(timezone.utc).timestamp())

            # Combine source_interaction_ids from all feedbacks in the group
            combined_source_ids: list[int] = []
            seen_ids: set[int] = set()
            for idx in group.item_indices:
                for sid in all_feedbacks[idx].source_interaction_ids:
                    if sid not in seen_ids:
                        combined_source_ids.append(sid)
                        seen_ids.add(sid)

            merged_feedback = RawFeedback(
                raw_feedback_id=0,  # Will be assigned by storage
                user_id=template_feedback.user_id,
                agent_version=template_feedback.agent_version,
                request_id=request_id,
                feedback_name=template_feedback.feedback_name,  # Use first feedback's name
                created_at=now_ts,
                feedback_content=group.merged_content,
                status=template_feedback.status,
                source=template_feedback.source,
                source_interaction_ids=combined_source_ids,
            )
            merged_feedbacks.append(merged_feedback)

        # Add unique (non-duplicate) feedbacks
        for idx in dedup_output.unique_indices:
            if idx not in handled_indices:
                merged_feedbacks.append(all_feedbacks[idx])
                handled_indices.add(idx)

        # Add any feedbacks not mentioned by LLM (safety fallback)
        for idx, feedback in enumerate(all_feedbacks):
            if idx not in handled_indices:
                logger.warning(
                    "Feedback at index %d was not handled by LLM, adding as-is", idx
                )
                merged_feedbacks.append(feedback)

        return merged_feedbacks
