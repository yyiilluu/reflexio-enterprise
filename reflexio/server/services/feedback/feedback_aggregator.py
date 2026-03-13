import hashlib
import logging
import os

import hdbscan
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances

# Threshold for switching between clustering algorithms
# Below this, use Agglomerative (works better with small datasets)
# Above this, use HDBSCAN (scales better, handles noise)
CLUSTERING_ALGORITHM_THRESHOLD = 50

from reflexio_commons.api_schema.service_schemas import (
    Feedback,
    FeedbackAggregationChangeLog,
    FeedbackSnapshot,
    FeedbackStatus,
    FeedbackUpdateEntry,
    RawFeedback,
    feedback_to_snapshot,
)
from reflexio_commons.config_schema import (
    FeedbackAggregatorConfig,
)

from reflexio.server.api_endpoints.request_context import RequestContext
from reflexio.server.llm.litellm_client import LiteLLMClient
from reflexio.server.services.feedback.feedback_service_constants import (
    FeedbackServiceConstants,
)
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregationOutput,
    FeedbackAggregatorRequest,
    StructuredFeedbackContent,
    format_structured_feedback_content,
)
from reflexio.server.services.operation_state_utils import OperationStateManager
from reflexio.server.services.service_utils import log_model_response

logger = logging.getLogger(__name__)


class FeedbackAggregator:
    def __init__(
        self,
        llm_client: LiteLLMClient,
        request_context: RequestContext,
        agent_version: str,
    ) -> None:
        self.client = llm_client
        self.storage = request_context.storage
        self.configurator = request_context.configurator
        self.request_context = request_context
        self.agent_version = agent_version

    # ===============================
    # private methods - operation state
    # ===============================

    def _create_state_manager(self) -> OperationStateManager:
        """
        Create an OperationStateManager for the feedback aggregator.

        Returns:
            OperationStateManager configured for feedback_aggregator
        """
        return OperationStateManager(
            self.storage,  # type: ignore[reportArgumentType]
            self.request_context.org_id,
            "feedback_aggregator",
        )

    def _get_new_raw_feedbacks_count(
        self, feedback_name: str, rerun: bool = False
    ) -> int:
        """
        Count how many new raw feedbacks exist since last aggregation.
        Uses efficient SQL COUNT query instead of fetching all feedbacks.

        Args:
            feedback_name: Name of the feedback type
            rerun: If True, count all raw feedbacks (use last_processed_id=0)

        Returns:
            int: Count of new raw feedbacks
        """
        # For rerun, use 0 to process all raw feedbacks
        if rerun:
            last_processed_id = 0
        else:
            mgr = self._create_state_manager()
            bookmark = mgr.get_aggregator_bookmark(
                name=feedback_name, version=self.agent_version
            )
            last_processed_id = bookmark if bookmark is not None else 0

        # Count feedbacks with ID greater than last processed using efficient count query
        # Only count current raw feedbacks (status=None), not archived or pending ones
        new_count = self.storage.count_raw_feedbacks(  # type: ignore[reportOptionalMemberAccess]
            feedback_name=feedback_name,
            min_raw_feedback_id=last_processed_id,
            agent_version=self.agent_version,
            status_filter=[None],
        )

        logger.info(
            "Found %d new raw feedbacks for '%s' (last processed ID: %d)",
            new_count,
            feedback_name,
            last_processed_id,
        )

        return new_count

    def _should_run_aggregation(
        self,
        feedback_name: str,
        feedback_aggregator_config: FeedbackAggregatorConfig,
        rerun: bool = False,
    ) -> bool:
        """
        Check if aggregation should run based on new feedbacks count.

        Args:
            feedback_name: Name of the feedback type
            feedback_aggregator_config: Configuration for feedback aggregator
            rerun: If True, count all raw feedbacks to determine if aggregation is needed

        Returns:
            bool: True if aggregation should run, False otherwise
        """
        # Get refresh_count, default to 2 if not set or 0
        refresh_count = feedback_aggregator_config.refresh_count
        if refresh_count <= 0:
            refresh_count = 2

        # Check new feedbacks count (uses all feedbacks if rerun=True)
        new_count = self._get_new_raw_feedbacks_count(feedback_name, rerun=rerun)

        return new_count >= refresh_count

    def _update_operation_state(
        self, feedback_name: str, raw_feedbacks: list[RawFeedback]
    ) -> None:
        """
        Update operation state with the highest raw_feedback_id processed.

        Args:
            feedback_name: Name of the feedback type
            raw_feedbacks: List of raw feedbacks that were processed
        """
        if not raw_feedbacks:
            return

        # Find max raw_feedback_id
        max_id = max(feedback.raw_feedback_id for feedback in raw_feedbacks)

        mgr = self._create_state_manager()
        mgr.update_aggregator_bookmark(
            name=feedback_name,
            version=self.agent_version,
            last_processed_id=max_id,
        )

    def _format_structured_cluster_input(
        self, cluster_feedbacks: list[RawFeedback]
    ) -> str:
        """
        Format a cluster of feedbacks for structured aggregation prompt.

        Collects all do_action, do_not_action, and when_condition values
        from the cluster. Since clustering may not be perfect, all when_conditions
        are passed to the LLM to generate a consolidated condition.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster

        Returns:
            str: Formatted input for the aggregation prompt
        """
        # Collect all values (including duplicates to show frequency)
        do_actions = []
        do_not_actions = []
        when_conditions = []

        for fb in cluster_feedbacks:
            if fb.do_action:
                do_actions.append(fb.do_action)
            if fb.do_not_action:
                do_not_actions.append(fb.do_not_action)
            if fb.when_condition:
                when_conditions.append(fb.when_condition)

        # Format the output - pass all when_conditions for LLM to consolidate
        lines = []

        # List all when_conditions for LLM to generate a consolidated one
        if when_conditions:
            lines.append("WHEN conditions (to be consolidated):")
            lines.extend(f"- {condition}" for condition in when_conditions)
        else:
            lines.append("WHEN conditions: (none specified)")

        if do_actions:
            lines.append("DO actions:")
            lines.extend(f"- {action}" for action in do_actions)

        if do_not_actions:
            lines.append("DON'T actions:")
            lines.extend(f"- {action}" for action in do_not_actions)

        # Collect blocking issues from cluster feedbacks
        blocking_issues = [
            f"[{fb.blocking_issue.kind.value}] {fb.blocking_issue.details}"
            for fb in cluster_feedbacks
            if fb.blocking_issue
        ]
        if blocking_issues:
            lines.append("BLOCKED BY issues:")
            lines.extend(f"- {issue}" for issue in blocking_issues)

        return "\n".join(lines)

    # ===============================
    # private methods - cluster change detection
    # ===============================

    @staticmethod
    def _compute_cluster_fingerprint(cluster_feedbacks: list[RawFeedback]) -> str:
        """
        Compute a fingerprint for a cluster based on its raw_feedback_ids.
        The fingerprint is deterministic and order-independent.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster

        Returns:
            str: SHA-256 hash (truncated to 16 hex chars) of sorted raw_feedback_ids
        """
        sorted_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
        id_str = ",".join(str(id) for id in sorted_ids)
        return hashlib.sha256(id_str.encode()).hexdigest()[:16]

    def _determine_cluster_changes(
        self,
        clusters: dict[int, list[RawFeedback]],
        prev_fingerprints: dict,
    ) -> tuple[dict[int, list[RawFeedback]], list[int]]:
        """
        Compare current cluster fingerprints against stored fingerprints to determine changes.

        Args:
            clusters: Current clusters (cluster_id -> list of RawFeedback)
            prev_fingerprints: Previous fingerprint state
                (fingerprint_hash -> {"feedback_id": int, "raw_feedback_ids": list})

        Returns:
            tuple of:
                - changed_clusters: Only clusters needing new LLM calls
                - feedback_ids_to_archive: Old feedback_ids from changed/disappeared clusters
        """
        # Compute fingerprints for current clusters
        current_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = self._compute_cluster_fingerprint(cluster_feedbacks)
            current_fingerprints[cluster_id] = fp

        current_fp_set = set(current_fingerprints.values())
        prev_fp_set = set(prev_fingerprints.keys())

        # Changed clusters: fingerprints that are new (not in previous state)
        changed_clusters = {}
        for cluster_id, fp in current_fingerprints.items():
            if fp not in prev_fp_set:
                changed_clusters[cluster_id] = clusters[cluster_id]

        # Feedback IDs to archive: from fingerprints that disappeared or changed
        feedback_ids_to_archive = []
        for fp, fp_data in prev_fingerprints.items():
            if fp not in current_fp_set:
                feedback_id = fp_data.get("feedback_id")
                if feedback_id is not None:
                    feedback_ids_to_archive.append(feedback_id)

        return changed_clusters, feedback_ids_to_archive

    def _build_change_log(
        self,
        feedback_name: str,
        full_archive: bool,
        before_feedbacks_by_id: dict[int, Feedback],
        saved_feedbacks: list[Feedback],
        archived_feedback_ids: list[int],
        prev_fingerprints: dict,
    ) -> FeedbackAggregationChangeLog:
        """Build a FeedbackAggregationChangeLog from the aggregation run results.

        Args:
            feedback_name: The feedback name being aggregated
            full_archive: Whether this was a full archive (rerun/first run)
            before_feedbacks_by_id: Snapshot of feedbacks before archiving, keyed by feedback_id
            saved_feedbacks: Newly saved feedbacks from this run
            archived_feedback_ids: Feedback IDs that were selectively archived (incremental mode)
            prev_fingerprints: Previous cluster fingerprints (empty for full archive)

        Returns:
            FeedbackAggregationChangeLog with added/removed/updated lists populated
        """
        added: list[FeedbackSnapshot] = []
        removed: list[FeedbackSnapshot] = []
        updated: list[FeedbackUpdateEntry] = []

        if full_archive:
            # No 1:1 mapping — all old feedbacks are removed, all new are added
            removed = [
                feedback_to_snapshot(fb) for fb in before_feedbacks_by_id.values()
            ]
            added = [feedback_to_snapshot(fb) for fb in saved_feedbacks if fb]
        else:
            # Incremental mode: map old feedback_ids to new feedbacks via fingerprints
            # Build a set of old feedback_ids that were archived
            archived_id_set = set(archived_feedback_ids)

            # Build mapping: old_feedback_id -> new_feedback_id via fingerprint changes
            # prev_fingerprints maps fp_hash -> {feedback_id, raw_feedback_ids}
            # new_fingerprints maps fp_hash -> {feedback_id, raw_feedback_ids}
            # If an old fingerprint disappeared and a new one appeared, and
            # the old fp had a feedback_id in archived_id_set, we can try to pair them.
            # However, without a direct cluster-level old->new mapping, we use a simpler approach:
            # archived feedbacks that have a corresponding new feedback (by position in saved list) are updates.

            # Collect old feedback_ids from disappeared fingerprints
            old_fp_feedback_ids = {}
            for fp, fp_data in prev_fingerprints.items():
                fid = fp_data.get("feedback_id")
                if fid is not None and fid in archived_id_set:
                    old_fp_feedback_ids[fid] = fp

            # For each saved feedback, try to match with an archived old feedback
            matched_old_ids: set[int] = set()
            for saved_fb in saved_feedbacks:
                if not saved_fb:
                    continue
                # Try to find an old feedback from the archived set to pair with
                paired_old_id = None
                for old_id in list(old_fp_feedback_ids.keys()):
                    if old_id not in matched_old_ids:
                        paired_old_id = old_id
                        matched_old_ids.add(old_id)
                        break

                if (
                    paired_old_id is not None
                    and paired_old_id in before_feedbacks_by_id
                ):
                    updated.append(
                        FeedbackUpdateEntry(
                            before=feedback_to_snapshot(
                                before_feedbacks_by_id[paired_old_id]
                            ),
                            after=feedback_to_snapshot(saved_fb),
                        )
                    )
                else:
                    added.append(feedback_to_snapshot(saved_fb))

            # Remaining archived feedbacks that weren't paired are removals
            for old_id in archived_id_set:
                if old_id not in matched_old_ids and old_id in before_feedbacks_by_id:
                    removed.append(feedback_to_snapshot(before_feedbacks_by_id[old_id]))

        return FeedbackAggregationChangeLog(
            feedback_name=feedback_name,
            agent_version=self.agent_version,
            run_mode="full_archive" if full_archive else "incremental",
            added_feedbacks=added,
            removed_feedbacks=removed,
            updated_feedbacks=updated,
        )

    # ===============================
    # public methods
    # ===============================

    def run(self, feedback_aggregator_request: FeedbackAggregatorRequest) -> None:  # noqa: C901
        # get feedback aggregator config
        feedback_aggregator_config = self._get_feedback_aggregator_config(
            feedback_aggregator_request.feedback_name
        )
        if (
            not feedback_aggregator_config
            or feedback_aggregator_config.min_feedback_threshold < 2
        ):
            logger.info(
                "No feedback aggregator config found or min feedback threshold is less than 2, skipping feedback aggregation, config: %s",
                feedback_aggregator_config,
            )
            return

        # Check if we should run aggregation based on new feedbacks count
        # For rerun, use all raw feedbacks (last_processed_id=0) to determine if aggregation is needed
        if not self._should_run_aggregation(
            feedback_aggregator_request.feedback_name,
            feedback_aggregator_config,
            rerun=feedback_aggregator_request.rerun,
        ):
            new_count = self._get_new_raw_feedbacks_count(
                feedback_aggregator_request.feedback_name,
                rerun=feedback_aggregator_request.rerun,
            )
            refresh_count = (
                feedback_aggregator_config.refresh_count
                if feedback_aggregator_config.refresh_count > 0
                else 2
            )
            logger.info(
                "Skipping aggregation for '%s' - only %d new feedbacks (need %d)",
                feedback_aggregator_request.feedback_name,
                new_count,
                refresh_count,
            )
            return

        logger.info(
            "Running aggregation for '%s'",
            feedback_aggregator_request.feedback_name,
        )

        # Get existing APPROVED and PENDING feedbacks before archiving (to pass to LLM for deduplication)
        existing_feedbacks = self.storage.get_feedbacks(  # type: ignore[reportOptionalMemberAccess]
            feedback_name=feedback_aggregator_request.feedback_name,
            status_filter=[None],  # Current feedbacks only
            feedback_status_filter=[FeedbackStatus.APPROVED, FeedbackStatus.PENDING],
        )
        logger.info(
            "Found %s existing feedbacks (approved + pending) to preserve",
            len(existing_feedbacks),
        )

        # get all raw feedbacks and generate clusters
        raw_feedbacks = self.storage.get_raw_feedbacks(  # type: ignore[reportOptionalMemberAccess]
            feedback_name=feedback_aggregator_request.feedback_name,
            agent_version=self.agent_version,
            include_embedding=True,
        )
        clusters = self.get_clusters(raw_feedbacks, feedback_aggregator_config)

        # Capture all current feedbacks before archiving (for change log)
        before_feedbacks_by_id: dict[int, Feedback] = {
            fb.feedback_id: fb for fb in existing_feedbacks
        }

        # Determine which clusters changed (skip for rerun)
        mgr = self._create_state_manager()
        feedback_name = feedback_aggregator_request.feedback_name
        archived_feedback_ids = []
        full_archive = False  # True when archive_feedbacks_by_feedback_name was used
        prev_fingerprints: dict = {}  # Populated for incremental mode

        if feedback_aggregator_request.rerun:
            # Full rerun: archive all non-APPROVED feedbacks, regenerate everything
            logger.info("Rerun requested: bypassing cluster change detection")
            self.storage.archive_feedbacks_by_feedback_name(  # type: ignore[reportOptionalMemberAccess]
                feedback_name, agent_version=self.agent_version
            )
            changed_clusters = clusters
            full_archive = True
        else:
            # Load previous fingerprints and detect changes
            prev_fingerprints = mgr.get_cluster_fingerprints(
                name=feedback_name, version=self.agent_version
            )

            if not prev_fingerprints:
                # First run: treat all clusters as changed, archive all existing
                logger.info(
                    "No previous cluster fingerprints found, treating all clusters as changed"
                )
                self.storage.archive_feedbacks_by_feedback_name(  # type: ignore[reportOptionalMemberAccess]
                    feedback_name, agent_version=self.agent_version
                )
                changed_clusters = clusters
                full_archive = True
            else:
                (
                    changed_clusters,
                    archived_feedback_ids,
                ) = self._determine_cluster_changes(clusters, prev_fingerprints)

                if not changed_clusters and not archived_feedback_ids:
                    logger.info(
                        "No cluster changes detected for '%s', skipping LLM calls",
                        feedback_name,
                    )
                    # Still update bookmark
                    self._update_operation_state(feedback_name, raw_feedbacks)
                    return

                logger.info(
                    "Detected %d changed clusters, %d feedbacks to archive",
                    len(changed_clusters),
                    len(archived_feedback_ids),
                )

                # Selectively archive only feedbacks from changed/disappeared clusters
                if archived_feedback_ids:
                    self.storage.archive_feedbacks_by_ids(archived_feedback_ids)  # type: ignore[reportOptionalMemberAccess]

        try:
            # Generate new feedbacks only for changed clusters
            feedbacks = self._generate_feedback_from_clusters(
                changed_clusters, existing_feedbacks
            )

            # Save feedbacks (returns feedbacks with feedback_id populated)
            saved_feedbacks = self.storage.save_feedbacks(feedbacks)  # type: ignore[reportOptionalMemberAccess]

            # Build new fingerprint state
            new_fingerprints = {}

            if not feedback_aggregator_request.rerun:
                # Carry forward unchanged fingerprints from previous state
                prev_fps = mgr.get_cluster_fingerprints(
                    name=feedback_name, version=self.agent_version
                )
                current_fp_set = set()
                for cluster_feedbacks in clusters.values():
                    fp = self._compute_cluster_fingerprint(cluster_feedbacks)
                    current_fp_set.add(fp)

                changed_fp_set = set()
                for cluster_feedbacks in changed_clusters.values():
                    changed_fp_set.add(
                        self._compute_cluster_fingerprint(cluster_feedbacks)
                    )

                # Carry forward unchanged clusters (still exist and not changed)
                new_fingerprints.update(
                    {
                        fp: fp_data
                        for fp, fp_data in prev_fps.items()
                        if fp in current_fp_set and fp not in changed_fp_set
                    }
                )

            # Map saved feedbacks back to changed clusters by order
            # _generate_feedback_from_clusters iterates clusters in order and
            # filters out None results, so we need to track which feedbacks
            # correspond to which clusters
            for cluster_feedbacks in changed_clusters.values():
                fp = self._compute_cluster_fingerprint(cluster_feedbacks)
                raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)

                # Try to match saved feedback - the LLM may return None for some
                # clusters (duplicates), so not every cluster has a saved feedback
                feedback_id = None
                # We can't perfectly map without changing _generate_feedback_from_clusters,
                # so store the fingerprint with whatever feedback_id we have
                new_fingerprints[fp] = {
                    "feedback_id": feedback_id,
                    "raw_feedback_ids": raw_ids,
                }

            # Now assign feedback_ids from saved feedbacks to fingerprints
            # Since both iterate in cluster order, match by position
            saved_feedback_list = list(saved_feedbacks)
            fp_keys_from_changed = [
                self._compute_cluster_fingerprint(cluster_feedbacks)
                for cluster_feedbacks in changed_clusters.values()
            ]

            # saved_feedbacks only contains non-None results, so we just
            # assign feedback_ids to fingerprints that got valid feedbacks
            for saved_fb in saved_feedback_list:
                if saved_fb and saved_fb.feedback_id:
                    # Find matching fingerprint by when_condition/content matching
                    for fp_key in fp_keys_from_changed:
                        if (
                            fp_key in new_fingerprints
                            and new_fingerprints[fp_key]["feedback_id"] is None
                        ):
                            new_fingerprints[fp_key]["feedback_id"] = (
                                saved_fb.feedback_id
                            )
                            break

            # Store fingerprints in operation state
            mgr.update_cluster_fingerprints(
                name=feedback_name,
                version=self.agent_version,
                fingerprints=new_fingerprints,
            )

            # Update operation state with the highest raw_feedback_id processed
            self._update_operation_state(feedback_name, raw_feedbacks)

            # Build and save change log
            try:
                change_log = self._build_change_log(
                    feedback_name=feedback_name,
                    full_archive=full_archive,
                    before_feedbacks_by_id=before_feedbacks_by_id,
                    saved_feedbacks=saved_feedback_list,
                    archived_feedback_ids=archived_feedback_ids,
                    prev_fingerprints=(prev_fingerprints if not full_archive else {}),
                )
                self.storage.add_feedback_aggregation_change_log(change_log)  # type: ignore[reportOptionalMemberAccess]
                logger.info(
                    "Saved feedback aggregation change log: %d added, %d removed, %d updated",
                    len(change_log.added_feedbacks),
                    len(change_log.removed_feedbacks),
                    len(change_log.updated_feedbacks),
                )
            except Exception:
                logger.exception(
                    "Failed to save feedback aggregation change log for '%s', continuing",
                    feedback_name,
                )

            # Delete archived feedbacks after successful aggregation
            if full_archive:
                self.storage.delete_archived_feedbacks_by_feedback_name(  # type: ignore[reportOptionalMemberAccess]
                    feedback_name, agent_version=self.agent_version
                )
            elif archived_feedback_ids:
                self.storage.delete_feedbacks_by_ids(archived_feedback_ids)  # type: ignore[reportOptionalMemberAccess]

        except Exception as e:
            # Restore archived feedbacks if any error occurs during aggregation
            logger.error(
                "Error during feedback aggregation for '%s': %s. Restoring archived feedbacks.",
                feedback_name,
                str(e),
            )
            if full_archive:
                self.storage.restore_archived_feedbacks_by_feedback_name(  # type: ignore[reportOptionalMemberAccess]
                    feedback_name, agent_version=self.agent_version
                )
            elif archived_feedback_ids:
                self.storage.restore_archived_feedbacks_by_ids(archived_feedback_ids)  # type: ignore[reportOptionalMemberAccess]
            # Re-raise the exception after restoring
            raise

    def get_clusters(
        self,
        raw_feedbacks: list[RawFeedback],
        feedback_aggregator_config: FeedbackAggregatorConfig,
    ) -> dict[int, list[RawFeedback]]:
        """
        Cluster raw feedbacks based on their embeddings (when_condition indexed).

        Args:
            raw_feedbacks: Contains raw feedbacks to cluster
            feedback_aggregator_config: Feedback aggregator config

        Returns:
            dict[int, list[RawFeedback]]: Dictionary mapping cluster IDs to lists of raw feedbacks
        """
        if not feedback_aggregator_config:
            logger.info(
                "No feedback aggregator config found, skipping feedback aggregation"
            )
            return {}

        min_cluster_size = feedback_aggregator_config.min_feedback_threshold

        if not raw_feedbacks:
            logger.info("No raw feedbacks to cluster")
            return {}

        # Mock mode: cluster by when_condition
        if os.getenv("MOCK_LLM_RESPONSE", "").lower() == "true":
            logger.info("Mock mode: clustering by when_condition")
            return self._cluster_by_when_condition_mock(raw_feedbacks, min_cluster_size)

        # Extract embeddings from raw feedbacks
        embeddings = np.array([feedback.embedding for feedback in raw_feedbacks])

        if len(embeddings) < min_cluster_size:
            logger.info(
                "Not enough feedbacks to cluster (got %d, need %d)",
                len(embeddings),
                min_cluster_size,
            )
            return {}

        # Compute cosine distance matrix for better text embedding clustering
        distance_matrix = cosine_distances(embeddings)

        # Choose algorithm based on dataset size
        if len(embeddings) < CLUSTERING_ALGORITHM_THRESHOLD:
            cluster_labels = self._cluster_with_agglomerative(
                distance_matrix, min_cluster_size
            )
        else:
            cluster_labels = self._cluster_with_hdbscan(
                distance_matrix, min_cluster_size
            )

        # Group feedbacks by cluster
        clusters: dict[int, list[RawFeedback]] = {}
        for idx, label in enumerate(cluster_labels):
            if label == -1:  # Skip noise points from HDBSCAN
                continue
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(raw_feedbacks[idx])

        # Filter out clusters smaller than min_cluster_size
        clusters = {
            label: feedbacks
            for label, feedbacks in clusters.items()
            if len(feedbacks) >= min_cluster_size
        }

        logger.info(
            "Found %d clusters from %d feedbacks", len(clusters), len(raw_feedbacks)
        )
        for cluster_id, cluster_feedbacks in clusters.items():
            logger.info("Cluster %d: %d feedbacks", cluster_id, len(cluster_feedbacks))

        return clusters

    def _cluster_by_when_condition_mock(
        self, raw_feedbacks: list[RawFeedback], min_cluster_size: int
    ) -> dict[int, list[RawFeedback]]:
        """
        Simple mock clustering by exact when_condition match.

        Args:
            raw_feedbacks: List of raw feedbacks with when_condition
            min_cluster_size: Minimum number of feedbacks per cluster

        Returns:
            dict[int, list[RawFeedback]]: Clusters grouped by when_condition
        """
        # Group by when_condition
        condition_groups: dict[str, list[RawFeedback]] = {}
        for fb in raw_feedbacks:
            condition = fb.when_condition or ""
            if condition not in condition_groups:
                condition_groups[condition] = []
            condition_groups[condition].append(fb)

        # Convert to cluster format, filtering by min_cluster_size
        clusters: dict[int, list[RawFeedback]] = {}
        cluster_id = 0
        for feedbacks in condition_groups.values():
            if len(feedbacks) >= min_cluster_size:
                clusters[cluster_id] = feedbacks
                cluster_id += 1

        logger.info(
            "Mock mode: created %d when_condition clusters from %d feedbacks",
            len(clusters),
            len(raw_feedbacks),
        )
        return clusters

    def _cluster_with_agglomerative(
        self,
        distance_matrix: np.ndarray,
        min_cluster_size: int,  # noqa: ARG002
    ) -> np.ndarray:
        """
        Cluster using Agglomerative Clustering - best for small datasets.

        Args:
            distance_matrix: Precomputed cosine distance matrix
            min_cluster_size: Minimum cluster size (used for logging only,
                              filtering happens in get_clusters)

        Returns:
            np.ndarray: Cluster labels for each point
        """
        logger.info(
            "Using Agglomerative Clustering for %d feedbacks (< %d threshold)",
            len(distance_matrix),
            CLUSTERING_ALGORITHM_THRESHOLD,
        )

        clusterer = AgglomerativeClustering(
            n_clusters=None,  # type: ignore[reportArgumentType]
            distance_threshold=0.3,  # ~70% cosine similarity
            metric="precomputed",
            linkage="average",
        )

        return clusterer.fit_predict(distance_matrix)

    def _cluster_with_hdbscan(
        self, distance_matrix: np.ndarray, min_cluster_size: int
    ) -> np.ndarray:
        """
        Cluster using HDBSCAN - best for large datasets with potential noise.

        Args:
            distance_matrix: Precomputed cosine distance matrix
            min_cluster_size: Minimum number of points to form a cluster

        Returns:
            np.ndarray: Cluster labels for each point (-1 indicates noise)
        """
        logger.info(
            "Using HDBSCAN for %d feedbacks (>= %d threshold)",
            len(distance_matrix),
            CLUSTERING_ALGORITHM_THRESHOLD,
        )

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            metric="precomputed",
            cluster_selection_epsilon=0.3,  # ~70% cosine similarity
        )

        return clusterer.fit_predict(distance_matrix)

    def _generate_feedback_from_clusters(
        self,
        clusters: dict[int, list[RawFeedback]],
        existing_approved_feedbacks: list[Feedback],
    ) -> list[Feedback]:
        """
        Generate feedback from clusters, considering existing approved feedbacks.

        Args:
            clusters: Dictionary mapping cluster IDs to lists of raw feedbacks
            existing_approved_feedbacks: List of existing approved feedbacks to avoid duplication

        Returns:
            list[Feedback]: List of newly generated feedbacks (excludes duplicates)
        """
        # Format existing approved feedbacks for the prompt
        approved_feedbacks_str = (
            "\n".join(
                [f"- {fb.feedback_content}" for fb in existing_approved_feedbacks]
            )
            if existing_approved_feedbacks
            else "None"
        )

        feedbacks = []
        for cluster_feedbacks in clusters.values():
            feedback = self._generate_feedback_from_cluster(
                cluster_feedbacks, approved_feedbacks_str
            )
            if feedback is not None:
                feedbacks.append(feedback)
        return feedbacks

    def _generate_feedback_from_cluster(
        self,
        cluster_feedbacks: list[RawFeedback],
        existing_approved_feedbacks_str: str,
    ) -> Feedback | None:
        """
        Generate feedback from a cluster using structured JSON output.

        Args:
            cluster_feedbacks: List of raw feedbacks in this cluster
            existing_approved_feedbacks_str: Formatted string of existing approved feedbacks

        Returns:
            Feedback | None: Generated feedback, or None if no new feedback needed
        """
        if not cluster_feedbacks:
            return None

        if os.getenv("MOCK_LLM_RESPONSE", "").lower() == "true":
            # Extract structured fields directly from cluster
            do_actions = [fb.do_action for fb in cluster_feedbacks if fb.do_action]
            do_not_actions = [
                fb.do_not_action for fb in cluster_feedbacks if fb.do_not_action
            ]
            when_conditions = [
                fb.when_condition for fb in cluster_feedbacks if fb.when_condition
            ]

            do_action = do_actions[0] if do_actions else None
            do_not_action = do_not_actions[0] if do_not_actions else None
            when_condition = when_conditions[0] if when_conditions else "in general"

            # At least one of do_action or do_not_action is required for valid feedback
            if do_action is None and do_not_action is None:
                # Fall back to using feedback_content from first feedback if available
                first_content = cluster_feedbacks[0].feedback_content
                if first_content:
                    do_action = first_content
                else:
                    logger.info("No valid structured fields in cluster, skipping")
                    return None

            # Create structured content and format to string
            structured = StructuredFeedbackContent(
                do_action=do_action,
                do_not_action=do_not_action,
                when_condition=when_condition,
            )
            feedback_content = format_structured_feedback_content(structured)

            return Feedback(
                feedback_name=cluster_feedbacks[0].feedback_name,
                agent_version=cluster_feedbacks[0].agent_version,
                feedback_content=feedback_content,
                do_action=do_action,
                do_not_action=do_not_action,
                when_condition=when_condition,
                feedback_status=FeedbackStatus.PENDING,
                feedback_metadata="mock_generated",
            )

        # Format raw feedbacks for prompt using structured format
        raw_feedbacks_str = self._format_structured_cluster_input(cluster_feedbacks)

        messages = [
            {
                "role": "user",
                "content": self.request_context.prompt_manager.render_prompt(
                    FeedbackServiceConstants.FEEDBACK_GENERATION_PROMPT_ID,
                    {
                        "raw_feedbacks": raw_feedbacks_str,
                        "existing_approved_feedbacks": existing_approved_feedbacks_str,
                    },
                ),
            }
        ]

        try:
            response = self.client.generate_chat_response(
                messages=messages,
                model=self.client.config.model,
                response_format=FeedbackAggregationOutput,
                parse_structured_output=True,
            )
            log_model_response(logger, "Aggregation structured response", response)

            if not isinstance(response, FeedbackAggregationOutput):
                logger.warning(
                    "LLM response was not parsed as FeedbackAggregationOutput (got %s), returning None.",
                    type(response).__name__,
                )
                return None

            return self._process_aggregation_response(response, cluster_feedbacks)
        except Exception as exc:
            logger.error(
                "Feedback aggregation failed due to %s, returning None.",
                str(exc),
            )
            return None

    def _process_aggregation_response(
        self, response: FeedbackAggregationOutput, cluster_feedbacks: list[RawFeedback]
    ) -> Feedback | None:
        """
        Process structured response from LLM into Feedback.

        Args:
            response: Parsed FeedbackAggregationOutput from LLM
            cluster_feedbacks: Original cluster feedbacks for metadata

        Returns:
            Feedback or None if no feedback should be generated
        """
        if not response:
            return None

        structured = response.feedback
        if structured is None:
            logger.info("LLM returned null feedback (duplicate of existing)")
            return None

        # Format to canonical string
        feedback_content = format_structured_feedback_content(structured)

        return Feedback(
            feedback_name=cluster_feedbacks[0].feedback_name,
            agent_version=cluster_feedbacks[0].agent_version,
            feedback_content=feedback_content,
            do_action=structured.do_action,
            do_not_action=structured.do_not_action,
            when_condition=structured.when_condition,
            blocking_issue=structured.blocking_issue,
            feedback_status=FeedbackStatus.PENDING,
            feedback_metadata="",
        )

    def _get_feedback_aggregator_config(
        self, feedback_name: str
    ) -> FeedbackAggregatorConfig | None:
        agent_feedback_configs = self.configurator.get_config().agent_feedback_configs
        if not agent_feedback_configs:
            return None
        for agent_feedback_config in agent_feedback_configs:
            if agent_feedback_config.feedback_name == feedback_name:
                return agent_feedback_config.feedback_aggregator_config
        return None
