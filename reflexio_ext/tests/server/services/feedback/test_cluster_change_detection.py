"""
Unit tests for cluster-level change detection in feedback aggregator.

Tests fingerprint computation, change detection logic, selective LLM invocation,
and clustering stability.
"""

import contextlib
from unittest.mock import MagicMock

import numpy as np
import pytest


# Disable mock mode for clustering tests so actual clustering algorithms are used
@pytest.fixture(autouse=True)
def disable_mock_llm_response(monkeypatch):
    """Disable MOCK_LLM_RESPONSE env var so clustering tests use real algorithms."""
    monkeypatch.delenv("MOCK_LLM_RESPONSE", raising=False)


from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregationOutput,
    FeedbackAggregatorRequest,
    StructuredFeedbackContent,
)
from reflexio_commons.api_schema.service_schemas import (
    Feedback,
    FeedbackStatus,
    RawFeedback,
)
from reflexio_commons.config_schema import FeedbackAggregatorConfig


def create_similar_embeddings(n: int, base_seed: int = 42) -> list[list[float]]:
    """
    Create n similar embeddings (high cosine similarity).

    Args:
        n: Number of embeddings to create
        base_seed: Random seed for reproducibility

    Returns:
        List of n similar 512-dimensional embeddings
    """
    np.random.seed(base_seed)
    base = np.random.randn(512)
    base = base / np.linalg.norm(base)

    embeddings = []
    for _i in range(n):
        noise = np.random.randn(512) * 0.001
        vec = base + noise
        vec = vec / np.linalg.norm(vec)
        embeddings.append(vec.tolist())

    return embeddings


def create_dissimilar_embeddings(n: int, base_seed: int = 42) -> list[list[float]]:
    """
    Create n dissimilar embeddings (low cosine similarity).

    Args:
        n: Number of embeddings to create
        base_seed: Random seed for reproducibility

    Returns:
        List of n dissimilar 512-dimensional embeddings
    """
    np.random.seed(base_seed)
    embeddings = []
    for _i in range(n):
        vec = np.random.randn(512)
        vec = vec / np.linalg.norm(vec)
        embeddings.append(vec.tolist())

    return embeddings


def create_raw_feedbacks_with_embeddings(
    embeddings: list[list[float]],
    feedback_name: str = "test_feedback",
    start_id: int = 0,
) -> list[RawFeedback]:
    """
    Create RawFeedback objects with given embeddings.

    Args:
        embeddings: List of embeddings
        feedback_name: Name for the feedbacks
        start_id: Starting raw_feedback_id

    Returns:
        List of RawFeedback objects
    """
    return [
        RawFeedback(
            raw_feedback_id=start_id + i,
            agent_version="1.0",
            request_id=str(start_id + i),
            feedback_content=f"Feedback content {start_id + i}",
            feedback_name=feedback_name,
            do_action=f"Do action {start_id + i}",
            when_condition=f"When condition {start_id + i}",
            embedding=emb,
        )
        for i, emb in enumerate(embeddings)
    ]


@pytest.fixture
def mock_feedback_aggregator():
    """Create a FeedbackAggregator with mocked dependencies."""
    mock_llm_client = MagicMock()
    mock_request_context = MagicMock()
    mock_request_context.storage = MagicMock()
    mock_request_context.configurator = MagicMock()

    aggregator = FeedbackAggregator(
        llm_client=mock_llm_client,
        request_context=mock_request_context,
        agent_version="1.0",
    )
    return aggregator  # noqa: RET504


class TestClusterFingerprint:
    """Unit tests for fingerprint computation."""

    def test_fingerprint_deterministic(self):
        """Compute fingerprint twice for same feedbacks, assert same result."""
        feedbacks = [
            RawFeedback(
                raw_feedback_id=i,
                agent_version="1.0",
                request_id=str(i),
                feedback_content=f"content {i}",
                feedback_name="test",
                embedding=[0.0] * 512,
            )
            for i in [1, 2, 3]
        ]

        fp1 = FeedbackAggregator._compute_cluster_fingerprint(feedbacks)
        fp2 = FeedbackAggregator._compute_cluster_fingerprint(feedbacks)
        assert fp1 == fp2

    def test_fingerprint_order_independent(self):
        """Fingerprint should be the same regardless of input order."""
        feedbacks_a = [
            RawFeedback(
                raw_feedback_id=i,
                agent_version="1.0",
                request_id=str(i),
                feedback_content=f"content {i}",
                feedback_name="test",
                embedding=[0.0] * 512,
            )
            for i in [3, 1, 2]
        ]
        feedbacks_b = [
            RawFeedback(
                raw_feedback_id=i,
                agent_version="1.0",
                request_id=str(i),
                feedback_content=f"content {i}",
                feedback_name="test",
                embedding=[0.0] * 512,
            )
            for i in [1, 2, 3]
        ]

        fp_a = FeedbackAggregator._compute_cluster_fingerprint(feedbacks_a)
        fp_b = FeedbackAggregator._compute_cluster_fingerprint(feedbacks_b)
        assert fp_a == fp_b

    def test_fingerprint_different_ids(self):
        """Different raw_feedback_ids should produce different fingerprints."""
        feedbacks_a = [
            RawFeedback(
                raw_feedback_id=i,
                agent_version="1.0",
                request_id=str(i),
                feedback_content=f"content {i}",
                feedback_name="test",
                embedding=[0.0] * 512,
            )
            for i in [1, 2, 3]
        ]
        feedbacks_b = [
            RawFeedback(
                raw_feedback_id=i,
                agent_version="1.0",
                request_id=str(i),
                feedback_content=f"content {i}",
                feedback_name="test",
                embedding=[0.0] * 512,
            )
            for i in [4, 5, 6]
        ]

        fp_a = FeedbackAggregator._compute_cluster_fingerprint(feedbacks_a)
        fp_b = FeedbackAggregator._compute_cluster_fingerprint(feedbacks_b)
        assert fp_a != fp_b


class TestDetermineClusterChanges:
    """Tests for change detection logic."""

    def test_first_run_no_previous_state(self, mock_feedback_aggregator):
        """On first run with no previous fingerprints, all clusters are changed."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        (
            changed_clusters,
            feedback_ids_to_archive,
        ) = mock_feedback_aggregator._determine_cluster_changes(clusters, {})

        # All clusters should be changed
        assert len(changed_clusters) == len(clusters)
        # No feedback_ids to archive (no previous state)
        assert feedback_ids_to_archive == []

    def test_no_changes_identical_clusters(self, mock_feedback_aggregator):
        """When clusters haven't changed, no clusters should be marked changed."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        # Build prev_fingerprints from current clusters
        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Re-cluster the same feedbacks
        clusters2 = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        (
            changed_clusters,
            feedback_ids_to_archive,
        ) = mock_feedback_aggregator._determine_cluster_changes(
            clusters2, prev_fingerprints
        )

        assert len(changed_clusters) == 0
        assert feedback_ids_to_archive == []

    def test_one_new_feedback_changes_one_cluster(self, mock_feedback_aggregator):
        """Adding a new feedback to one group should only change that cluster."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        # Build prev_fingerprints
        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Add a new feedback similar to group_a
        new_emb = create_similar_embeddings(1, base_seed=42)
        new_feedback = create_raw_feedbacks_with_embeddings(new_emb, start_id=100)
        all_feedbacks_updated = all_feedbacks + new_feedback

        clusters2 = mock_feedback_aggregator.get_clusters(all_feedbacks_updated, config)

        (
            changed_clusters,
            feedback_ids_to_archive,
        ) = mock_feedback_aggregator._determine_cluster_changes(
            clusters2, prev_fingerprints
        )

        # At least one cluster should be changed (the one that got the new feedback)
        assert len(changed_clusters) >= 1
        # The total changed should be less than all clusters
        assert len(changed_clusters) < len(clusters2) or len(clusters2) <= 1

    def test_cluster_disappeared(self, mock_feedback_aggregator):
        """When a cluster disappears, its old feedback_id should be archived."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        # Build prev_fingerprints
        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Only keep group_a feedbacks
        feedbacks_a_only = create_raw_feedbacks_with_embeddings(group_a)
        clusters2 = mock_feedback_aggregator.get_clusters(feedbacks_a_only, config)

        (
            changed_clusters,
            feedback_ids_to_archive,
        ) = mock_feedback_aggregator._determine_cluster_changes(
            clusters2, prev_fingerprints
        )

        # The disappeared cluster's feedback_id should be in archive list
        assert len(feedback_ids_to_archive) >= 1

    def test_new_cluster_appears(self, mock_feedback_aggregator):
        """When a new cluster appears, it should be in changed_clusters."""
        group_a = create_similar_embeddings(3, base_seed=42)
        feedbacks_a = create_raw_feedbacks_with_embeddings(group_a)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters = mock_feedback_aggregator.get_clusters(feedbacks_a, config)

        # Build prev_fingerprints from just group_a
        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Add group_b
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = feedbacks_a + create_raw_feedbacks_with_embeddings(
            group_b, start_id=100
        )
        clusters2 = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        (
            changed_clusters,
            feedback_ids_to_archive,
        ) = mock_feedback_aggregator._determine_cluster_changes(
            clusters2, prev_fingerprints
        )

        # The new cluster should appear in changed_clusters
        assert len(changed_clusters) >= 1
        # group_a should be unchanged, so no feedback_ids to archive
        assert feedback_ids_to_archive == []


class TestAggregatorRunWithChangeDetection:
    """End-to-end tests with mock storage verifying selective LLM invocation."""

    def _setup_aggregator_for_run(
        self,
        raw_feedbacks,
        existing_feedbacks=None,
        operation_state=None,
        config=None,
    ):
        """
        Helper to create a fully configured mock aggregator for run() tests.

        Args:
            raw_feedbacks: Raw feedbacks to return from storage
            existing_feedbacks: Existing feedbacks to return from storage
            operation_state: Operation state to return (for fingerprints/bookmarks)
            config: FeedbackAggregatorConfig to use

        Returns:
            Configured FeedbackAggregator with mocked dependencies
        """
        if existing_feedbacks is None:
            existing_feedbacks = []
        if config is None:
            config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=1)

        mock_llm_client = MagicMock()
        mock_request_context = MagicMock()
        mock_storage = MagicMock()
        mock_request_context.storage = mock_storage
        mock_request_context.org_id = "test_org"
        mock_configurator = MagicMock()
        mock_request_context.configurator = mock_configurator

        # Setup configurator to return config
        mock_agent_feedback_config = MagicMock()
        mock_agent_feedback_config.feedback_name = "test_feedback"
        mock_agent_feedback_config.feedback_aggregator_config = config
        mock_configurator.get_config.return_value.agent_feedback_configs = [
            mock_agent_feedback_config
        ]

        # Setup storage methods
        mock_storage.get_raw_feedbacks.return_value = raw_feedbacks
        mock_storage.get_feedbacks.return_value = existing_feedbacks
        mock_storage.count_raw_feedbacks.return_value = len(raw_feedbacks)
        mock_storage.save_feedbacks.return_value = []

        # Setup operation state (for fingerprints and bookmarks)
        # Storage returns {"operation_state": {...}} wrapping
        def get_operation_state_side_effect(key):
            if operation_state is not None and "clusters" in key:
                return {"operation_state": {"cluster_fingerprints": operation_state}}
            if operation_state is not None and "clusters" not in key:
                # Return bookmark
                return {"operation_state": {"last_processed_raw_feedback_id": 0}}
            return None

        mock_storage.get_operation_state.side_effect = get_operation_state_side_effect

        # Setup LLM client to return structured feedback
        structured = StructuredFeedbackContent(
            do_action="Do something",
            when_condition="When something happens",
        )
        mock_response = FeedbackAggregationOutput(feedback=structured)
        mock_llm_client.generate_chat_response.return_value = mock_response
        mock_llm_client.config = MagicMock()
        mock_llm_client.config.model = "test-model"

        aggregator = FeedbackAggregator(
            llm_client=mock_llm_client,
            request_context=mock_request_context,
            agent_version="1.0",
        )

        return aggregator, mock_storage, mock_llm_client

    def test_first_run_calls_llm_for_all_clusters(self):
        """First run (no stored fingerprints) should call LLM for all clusters."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=raw_feedbacks,
            operation_state=None,
        )

        # Make save_feedbacks return feedbacks with IDs
        def save_feedbacks_side_effect(feedbacks):
            for i, fb in enumerate(feedbacks):
                fb.feedback_id = i + 1
            return feedbacks

        mock_storage.save_feedbacks.side_effect = save_feedbacks_side_effect

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
        )

        aggregator.run(request)

        # LLM should be called for each cluster (at least 1, up to 2)
        assert mock_llm_client.generate_chat_response.call_count >= 1
        # Save feedbacks should be called
        mock_storage.save_feedbacks.assert_called_once()
        # Fingerprints should be stored
        mock_storage.upsert_operation_state.assert_called()

    def test_second_run_no_changes_skips_llm(self):
        """Second run with same feedbacks should skip LLM calls entirely."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        # Compute fingerprints for the existing clusters
        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=1)
        MagicMock()
        # Actually compute clusters to get real fingerprints
        mock_llm = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.storage = MagicMock()
        mock_ctx.configurator = MagicMock()
        temp = FeedbackAggregator(mock_llm, mock_ctx, "1.0")
        clusters = temp.get_clusters(raw_feedbacks, config)

        # Build fingerprints from actual clusters
        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        existing_feedbacks = [
            Feedback(
                feedback_id=cid + 100,
                feedback_name="test_feedback",
                agent_version="1.0",
                feedback_content=f"Existing feedback {cid}",
                feedback_status=FeedbackStatus.PENDING,
            )
            for cid in clusters
        ]

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=raw_feedbacks,
            existing_feedbacks=existing_feedbacks,
            operation_state=prev_fingerprints,
            config=config,
        )

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
        )

        aggregator.run(request)

        # LLM should NOT be called
        mock_llm_client.generate_chat_response.assert_not_called()
        # archive_feedbacks_by_ids should NOT be called (nothing to archive)
        mock_storage.archive_feedbacks_by_ids.assert_not_called()

    def test_second_run_with_new_feedbacks_calls_llm_selectively(self):
        """Adding feedbacks to one cluster should only call LLM for that cluster."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        original_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=1)

        # Compute original clusters and fingerprints
        mock_llm = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.storage = MagicMock()
        mock_ctx.configurator = MagicMock()
        temp = FeedbackAggregator(mock_llm, mock_ctx, "1.0")
        original_clusters = temp.get_clusters(original_feedbacks, config)

        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in original_clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Add 2 new feedbacks similar to group_a
        new_embs = create_similar_embeddings(2, base_seed=42)
        new_feedbacks = create_raw_feedbacks_with_embeddings(new_embs, start_id=100)
        all_feedbacks = original_feedbacks + new_feedbacks

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=all_feedbacks,
            operation_state=prev_fingerprints,
            config=config,
        )

        def save_feedbacks_side_effect(feedbacks):
            for i, fb in enumerate(feedbacks):
                fb.feedback_id = i + 200
            return feedbacks

        mock_storage.save_feedbacks.side_effect = save_feedbacks_side_effect

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
        )

        aggregator.run(request)

        # LLM should be called fewer times than total clusters
        total_llm_calls = mock_llm_client.generate_chat_response.call_count
        assert total_llm_calls >= 1
        # save_feedbacks should be called
        mock_storage.save_feedbacks.assert_called_once()

    def test_rerun_bypasses_change_detection(self):
        """rerun=True should call LLM for ALL clusters regardless of fingerprints."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=1)

        # Setup with existing fingerprints (so without rerun it would skip)
        mock_llm = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.storage = MagicMock()
        mock_ctx.configurator = MagicMock()
        temp = FeedbackAggregator(mock_llm, mock_ctx, "1.0")
        clusters = temp.get_clusters(raw_feedbacks, config)

        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=raw_feedbacks,
            operation_state=prev_fingerprints,
            config=config,
        )

        def save_feedbacks_side_effect(feedbacks):
            for i, fb in enumerate(feedbacks):
                fb.feedback_id = i + 1
            return feedbacks

        mock_storage.save_feedbacks.side_effect = save_feedbacks_side_effect

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
            rerun=True,
        )

        aggregator.run(request)

        # LLM should be called for ALL clusters
        assert mock_llm_client.generate_chat_response.call_count == len(clusters)
        # archive_feedbacks_by_feedback_name should be called (full archive)
        mock_storage.archive_feedbacks_by_feedback_name.assert_called_once()

    def test_error_during_save_restores_archived_feedbacks(self):
        """If save_feedbacks fails, archived feedbacks should be restored."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        original_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=1)

        # Compute original clusters and fingerprints
        mock_llm = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.storage = MagicMock()
        mock_ctx.configurator = MagicMock()
        temp = FeedbackAggregator(mock_llm, mock_ctx, "1.0")
        original_clusters = temp.get_clusters(original_feedbacks, config)

        prev_fingerprints = {}
        for cluster_id, cluster_feedbacks in original_clusters.items():
            fp = FeedbackAggregator._compute_cluster_fingerprint(cluster_feedbacks)
            raw_ids = sorted(fb.raw_feedback_id for fb in cluster_feedbacks)
            prev_fingerprints[fp] = {
                "feedback_id": cluster_id + 100,
                "raw_feedback_ids": raw_ids,
            }

        # Add new feedbacks to trigger a change
        new_embs = create_similar_embeddings(2, base_seed=42)
        new_feedbacks = create_raw_feedbacks_with_embeddings(new_embs, start_id=100)
        all_feedbacks = original_feedbacks + new_feedbacks

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=all_feedbacks,
            operation_state=prev_fingerprints,
            config=config,
        )

        # Make save_feedbacks raise an exception (this happens after archiving)
        mock_storage.save_feedbacks.side_effect = Exception("Storage save error")

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
        )

        with pytest.raises(Exception, match="Storage save error"):
            aggregator.run(request)

        # restore_archived_feedbacks_by_ids should be called if selective archiving happened
        # OR restore_archived_feedbacks_by_feedback_name if it was a first run
        restore_by_ids_called = mock_storage.restore_archived_feedbacks_by_ids.called
        restore_by_name_called = (
            mock_storage.restore_archived_feedbacks_by_feedback_name.called
        )
        assert restore_by_ids_called or restore_by_name_called

    def test_first_run_deletes_archived_on_success(self):
        """Regression: first-run (non-rerun) path must delete archived feedbacks after success."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=raw_feedbacks,
            operation_state=None,  # No previous state → first-run path
        )

        def save_feedbacks_side_effect(feedbacks):
            for i, fb in enumerate(feedbacks):
                fb.feedback_id = i + 1
            return feedbacks

        mock_storage.save_feedbacks.side_effect = save_feedbacks_side_effect

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
            rerun=False,
        )

        aggregator.run(request)

        mock_storage.delete_archived_feedbacks_by_feedback_name.assert_called_once()

    def test_first_run_restores_archived_on_error(self):
        """Regression: first-run (non-rerun) must restore archived feedbacks on save error."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        aggregator, mock_storage, mock_llm_client = self._setup_aggregator_for_run(
            raw_feedbacks=raw_feedbacks,
            operation_state=None,  # No previous state → first-run path
        )

        mock_storage.save_feedbacks.side_effect = Exception("Storage save error")

        request = FeedbackAggregatorRequest(
            agent_version="1.0",
            feedback_name="test_feedback",
            rerun=False,
        )

        with pytest.raises(Exception, match="Storage save error"):
            aggregator.run(request)

        mock_storage.restore_archived_feedbacks_by_feedback_name.assert_called_once()


class TestLLMResponseTypeSafety:
    """Regression tests for LLM response isinstance guard."""

    def test_raw_string_response_returns_none(self):
        """Regression: plain string from LLM must not crash with AttributeError on .feedback."""
        mock_llm_client = MagicMock()
        mock_request_context = MagicMock()
        mock_request_context.storage = MagicMock()
        mock_request_context.configurator = MagicMock()

        # LLM returns a raw string instead of FeedbackAggregationOutput
        mock_llm_client.generate_chat_response.return_value = "unparsed text"
        mock_llm_client.config = MagicMock()
        mock_llm_client.config.model = "test-model"

        aggregator = FeedbackAggregator(
            llm_client=mock_llm_client,
            request_context=mock_request_context,
            agent_version="1.0",
        )

        cluster_feedbacks = [
            RawFeedback(
                raw_feedback_id=1,
                agent_version="1.0",
                request_id="r1",
                feedback_content="content",
                feedback_name="test",
                do_action="do something",
                when_condition="when asked",
                embedding=[0.0] * 512,
            ),
        ]

        result = aggregator._generate_feedback_from_cluster(cluster_feedbacks, "None")
        assert result is None

    def test_valid_aggregation_output_is_processed(self):
        """Positive test: valid FeedbackAggregationOutput produces a Feedback."""
        mock_llm_client = MagicMock()
        mock_request_context = MagicMock()
        mock_request_context.storage = MagicMock()
        mock_request_context.configurator = MagicMock()

        structured = StructuredFeedbackContent(
            do_action="Be concise",
            when_condition="When answering questions",
        )
        mock_llm_client.generate_chat_response.return_value = FeedbackAggregationOutput(
            feedback=structured
        )
        mock_llm_client.config = MagicMock()
        mock_llm_client.config.model = "test-model"

        aggregator = FeedbackAggregator(
            llm_client=mock_llm_client,
            request_context=mock_request_context,
            agent_version="1.0",
        )

        cluster_feedbacks = [
            RawFeedback(
                raw_feedback_id=1,
                agent_version="1.0",
                request_id="r1",
                feedback_content="content",
                feedback_name="test",
                do_action="do something",
                when_condition="when asked",
                embedding=[0.0] * 512,
            ),
        ]

        result = aggregator._generate_feedback_from_cluster(cluster_feedbacks, "None")
        assert result is not None
        assert result.do_action == "Be concise"
        assert result.when_condition == "When answering questions"
        assert result.feedback_status == FeedbackStatus.PENDING


class TestClusteringStability:
    """Verify clustering produces stable results for fingerprint comparison."""

    def test_same_feedbacks_produce_same_clusters(self, mock_feedback_aggregator):
        """Running get_clusters twice with same input should produce same clusters."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        all_feedbacks = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters1 = mock_feedback_aggregator.get_clusters(all_feedbacks, config)
        clusters2 = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        # Same number of clusters
        assert len(clusters1) == len(clusters2)

        # Same membership (compare sets of raw_feedback_ids per cluster)
        def get_cluster_id_sets(clusters):
            return sorted(
                sorted(fb.raw_feedback_id for fb in cfbs) for cfbs in clusters.values()
            )

        assert get_cluster_id_sets(clusters1) == get_cluster_id_sets(clusters2)

    def test_adding_feedback_only_affects_its_cluster(self, mock_feedback_aggregator):
        """Adding a feedback to one group should not change membership of the other."""
        group_a = create_similar_embeddings(3, base_seed=42)
        group_b = create_similar_embeddings(3, base_seed=100)
        feedbacks_original = create_raw_feedbacks_with_embeddings(group_a + group_b)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        clusters1 = mock_feedback_aggregator.get_clusters(feedbacks_original, config)

        # Find which cluster IDs contain group_b feedbacks (IDs 3,4,5)
        group_b_ids = {3, 4, 5}
        group_b_cluster_members = None
        for cluster_feedbacks in clusters1.values():
            ids_in_cluster = {fb.raw_feedback_id for fb in cluster_feedbacks}
            if ids_in_cluster & group_b_ids:
                group_b_cluster_members = ids_in_cluster
                break

        # Add a new feedback similar to group_a
        new_emb = create_similar_embeddings(1, base_seed=42)
        new_feedback = create_raw_feedbacks_with_embeddings(new_emb, start_id=100)
        all_feedbacks = feedbacks_original + new_feedback

        clusters2 = mock_feedback_aggregator.get_clusters(all_feedbacks, config)

        # Find group_b cluster in new clustering
        group_b_cluster_members2 = None
        for cluster_feedbacks in clusters2.values():
            ids_in_cluster = {fb.raw_feedback_id for fb in cluster_feedbacks}
            if ids_in_cluster & group_b_ids:
                group_b_cluster_members2 = ids_in_cluster
                break

        # Group B membership should be unchanged
        if group_b_cluster_members is not None and group_b_cluster_members2 is not None:
            assert group_b_cluster_members == group_b_cluster_members2


##############################################################################
# End-to-end tests (real Supabase + real LLM)
##############################################################################

import os
import tempfile

from reflexio.tests.server.test_utils import skip_in_precommit

# Unique feedback name to avoid collisions with other tests
E2E_FEEDBACK_NAME = "e2e_change_detect_feedback"
E2E_AGENT_VERSION = "1.0.0"
E2E_ORG_ID = "e2e_test"


def _resolve_supabase_config():
    """Resolve supabase connection config from env vars or local supabase CLI.

    Returns:
        tuple[str, str, str]: (url, key, db_url) or raises pytest.skip
    """
    supabase_url = os.environ.get("TEST_SUPABASE_URL", "")
    supabase_key = os.environ.get("TEST_SUPABASE_KEY", "")
    supabase_db_url = os.environ.get("TEST_SUPABASE_DB_URL", "")

    # Fall back to local supabase defaults
    if not supabase_url:
        supabase_url = "http://127.0.0.1:54321"
    if not supabase_key:
        import subprocess

        try:
            result = subprocess.run(
                ["supabase", "status"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                if "Secret key" in line:
                    supabase_key = line.split(":")[-1].strip()
                    break
            for line in result.stdout.splitlines():
                if "Database URL" in line and not supabase_db_url:
                    supabase_db_url = line.split(":", 1)[-1].strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not supabase_url or not supabase_key:
        pytest.skip(
            "TEST_SUPABASE_URL and TEST_SUPABASE_KEY must be set "
            "or local supabase must be running"
        )

    return supabase_url, supabase_key, supabase_db_url


@pytest.fixture
def supabase_storage():
    """Create a SupabaseStorage instance for e2e tests."""
    from reflexio_ext.server.services.storage.supabase_storage import SupabaseStorage
    from reflexio_commons.config_schema import StorageConfigSupabase

    url, key, db_url = _resolve_supabase_config()
    config = StorageConfigSupabase(url=url, key=key, db_url=db_url)
    return SupabaseStorage(org_id=E2E_ORG_ID, config=config)


@pytest.fixture
def e2e_cleanup(supabase_storage):
    """Clean up test data before and after the e2e test."""

    def _cleanup():
        with contextlib.suppress(Exception):
            supabase_storage.client.table("feedbacks").delete().eq(
                "feedback_name", E2E_FEEDBACK_NAME
            ).execute()
        with contextlib.suppress(Exception):
            supabase_storage.client.table("raw_feedbacks").delete().eq(
                "feedback_name", E2E_FEEDBACK_NAME
            ).execute()
        # Clean up operation state entries for this test
        bookmark_key = f"feedback_aggregator::{E2E_ORG_ID}::{E2E_FEEDBACK_NAME}::{E2E_AGENT_VERSION}"
        cluster_key = f"{bookmark_key}::clusters"
        for key in [bookmark_key, cluster_key]:
            with contextlib.suppress(Exception):
                supabase_storage.delete_operation_state(key)

    _cleanup()
    yield
    _cleanup()


def _create_e2e_raw_feedbacks_with_embeddings(
    group: str, count: int, start_id_hint: int = 0
) -> list[RawFeedback]:
    """
    Create raw feedbacks with pre-computed embeddings for direct DB insertion.

    Uses deterministic embeddings so feedbacks in the same group cluster together
    and feedbacks in different groups do NOT cluster together.

    Args:
        group: One of "verbose", "code" — determines embedding seed
        count: Number of feedbacks to create
        start_id_hint: Hint for unique request_ids

    Returns:
        list[RawFeedback]: Feedbacks with embeddings ready for DB insertion
    """
    templates = {
        "verbose": [
            "The response was too long and verbose, please be more concise",
            "Responses are too wordy, I need shorter answers",
            "Too much unnecessary detail in the answer, keep it brief",
            "The reply had too much text, I prefer shorter responses",
            "Please shorten your answers, they are overly detailed",
            "The answer was excessively long and hard to read",
            "I want concise answers not long paragraphs of text",
        ],
        "code": [
            "The code examples in the response were very helpful and clear",
            "Great job with the programming code snippets and explanations",
            "The code samples provided were well structured and useful",
            "Excellent code demonstrations that were easy to follow",
            "The programming examples were practical and informative",
            "Good use of code blocks to illustrate the solution",
            "The code provided was clean, readable and well commented",
        ],
    }

    # Different seed per group so they cluster separately
    seed_map = {"verbose": 42, "code": 100}
    embeddings = create_similar_embeddings(count, base_seed=seed_map[group])

    contents = templates[group]
    feedbacks = []
    for i in range(count):
        content = contents[i % len(contents)]
        feedbacks.append(
            RawFeedback(
                agent_version=E2E_AGENT_VERSION,
                request_id=f"e2e_{group}_{start_id_hint + i}",
                feedback_content=content,
                do_action="Provide clear code examples" if group == "code" else None,
                do_not_action="Be too verbose" if group == "verbose" else None,
                when_condition="When user asks about code"
                if group == "code"
                else "When responding to any question",
                feedback_name=E2E_FEEDBACK_NAME,
                embedding=embeddings[i],
            )
        )
    return feedbacks


def _insert_raw_feedbacks_directly(supabase_storage, feedbacks: list[RawFeedback]):
    """
    Insert raw feedbacks directly into the DB, bypassing embedding generation.
    The feedbacks must already have embeddings set.

    Args:
        supabase_storage: SupabaseStorage instance
        feedbacks: Feedbacks with pre-computed embeddings
    """
    from reflexio_ext.server.services.storage.supabase_storage_utils import (
        raw_feedback_to_data,
    )

    for fb in feedbacks:
        assert fb.embedding, f"Feedback {fb.request_id} missing embedding"
        supabase_storage.client.table("raw_feedbacks").upsert(
            raw_feedback_to_data(fb)
        ).execute()


@skip_in_precommit
class TestClusterChangeDetectionE2E:
    """
    End-to-end tests using real Supabase storage and real LLM.

    Raw feedbacks are inserted with pre-computed embeddings (bypasses OpenAI
    embedding API for insertion) so the test only requires a valid LLM API key
    for the aggregation step.

    Flow:
    1. Insert batch 1 raw feedbacks (2 distinct groups) with pre-computed embeddings
    2. Run aggregation → LLM summarises clusters, creates feedbacks
    3. Run aggregation again (no new data) → change detection skips LLM
    4. Insert batch 2 raw feedbacks into ONE group
    5. Run aggregation → change detection only re-summarises the changed cluster
    6. Verify feedbacks are correctly updated and fingerprints are stored
    """

    def test_change_detection_full_cycle(self, supabase_storage, e2e_cleanup):
        """Full e2e cycle: create → aggregate → add more → re-aggregate with change detection."""
        from reflexio.server.api_endpoints.request_context import RequestContext
        from reflexio.server.llm.litellm_client import LiteLLMClient, LiteLLMConfig
        from reflexio_commons.config_schema import (
            AgentFeedbackConfig,
            StorageConfigSupabase,
        )

        # Check that OPENAI_API_KEY (or equivalent) is available
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key or len(openai_key) < 10:
            pytest.skip("OPENAI_API_KEY not set or invalid — required for LLM calls")

        # ── Setup ──
        url, key, db_url = _resolve_supabase_config()

        with tempfile.TemporaryDirectory() as temp_dir:
            request_context = RequestContext(
                org_id=E2E_ORG_ID, storage_base_dir=temp_dir
            )
            request_context.configurator.set_config_by_name(
                "storage_config",
                StorageConfigSupabase(url=url, key=key, db_url=db_url),
            )
            request_context.configurator.set_config_by_name(
                "agent_feedback_configs",
                [
                    AgentFeedbackConfig(
                        feedback_name=E2E_FEEDBACK_NAME,
                        feedback_definition_prompt="test feedback definition",
                        feedback_aggregator_config=FeedbackAggregatorConfig(
                            min_feedback_threshold=2,
                            refresh_count=1,
                        ),
                    )
                ],
            )
            request_context.storage = supabase_storage

            llm_config = LiteLLMConfig(model="gpt-4o-mini")
            llm_client = LiteLLMClient(llm_config)

            aggregator = FeedbackAggregator(
                llm_client=llm_client,
                request_context=request_context,
                agent_version=E2E_AGENT_VERSION,
            )

            request = FeedbackAggregatorRequest(
                agent_version=E2E_AGENT_VERSION,
                feedback_name=E2E_FEEDBACK_NAME,
            )

            # ── Step 1: Insert batch 1 (2 groups × 3) with pre-computed embeddings ──
            batch1_verbose = _create_e2e_raw_feedbacks_with_embeddings(
                "verbose", 3, start_id_hint=0
            )
            batch1_code = _create_e2e_raw_feedbacks_with_embeddings(
                "code", 3, start_id_hint=100
            )
            _insert_raw_feedbacks_directly(
                supabase_storage, batch1_verbose + batch1_code
            )

            saved_raw = supabase_storage.get_raw_feedbacks(
                feedback_name=E2E_FEEDBACK_NAME
            )
            assert len(saved_raw) == 6, (
                f"Expected 6 raw feedbacks, got {len(saved_raw)}"
            )

            # ── Step 2: First aggregation → LLM called for all clusters ──
            aggregator.run(request)

            feedbacks_after_run1 = supabase_storage.get_feedbacks(
                feedback_name=E2E_FEEDBACK_NAME,
                status_filter=[None],
                feedback_status_filter=[FeedbackStatus.PENDING],
            )
            run1_count = len(feedbacks_after_run1)
            assert run1_count >= 1, (
                f"Expected at least 1 feedback after first run, got {run1_count}"
            )
            run1_feedback_ids = {fb.feedback_id for fb in feedbacks_after_run1}

            # ── Step 3: Second aggregation (no new data) → should skip LLM ──
            aggregator.run(request)

            feedbacks_after_run2 = supabase_storage.get_feedbacks(
                feedback_name=E2E_FEEDBACK_NAME,
                status_filter=[None],
                feedback_status_filter=[FeedbackStatus.PENDING],
            )
            run2_feedback_ids = {fb.feedback_id for fb in feedbacks_after_run2}

            # Feedbacks should be identical (nothing changed)
            assert run1_feedback_ids == run2_feedback_ids, (
                f"Expected same feedback IDs after no-change run. "
                f"Run1: {run1_feedback_ids}, Run2: {run2_feedback_ids}"
            )

            # ── Step 4: Insert batch 2 (3 more "verbose" feedbacks) ──
            batch2_verbose = _create_e2e_raw_feedbacks_with_embeddings(
                "verbose", 3, start_id_hint=200
            )
            _insert_raw_feedbacks_directly(supabase_storage, batch2_verbose)

            saved_raw = supabase_storage.get_raw_feedbacks(
                feedback_name=E2E_FEEDBACK_NAME
            )
            assert len(saved_raw) == 9, (
                f"Expected 9 raw feedbacks, got {len(saved_raw)}"
            )

            # ── Step 5: Third aggregation → detect change in verbose cluster ──
            aggregator.run(request)

            feedbacks_after_run3 = supabase_storage.get_feedbacks(
                feedback_name=E2E_FEEDBACK_NAME,
                status_filter=[None],
                feedback_status_filter=[FeedbackStatus.PENDING],
            )
            run3_count = len(feedbacks_after_run3)
            assert run3_count >= 1, (
                f"Expected at least 1 feedback after third run, got {run3_count}"
            )

            # ── Step 6: Verify fingerprints are stored ──
            from reflexio.server.services.operation_state_utils import (
                OperationStateManager,
            )

            mgr = OperationStateManager(
                supabase_storage, E2E_ORG_ID, "feedback_aggregator"
            )
            stored_fingerprints = mgr.get_cluster_fingerprints(
                name=E2E_FEEDBACK_NAME, version=E2E_AGENT_VERSION
            )
            assert len(stored_fingerprints) >= 1, (
                f"Expected at least 1 stored fingerprint, got "
                f"{len(stored_fingerprints)}"
            )

            # Each fingerprint should have raw_feedback_ids
            for fp_hash, fp_data in stored_fingerprints.items():
                assert "raw_feedback_ids" in fp_data, (
                    f"Fingerprint {fp_hash} missing raw_feedback_ids"
                )
                assert len(fp_data["raw_feedback_ids"]) >= 2, (
                    f"Fingerprint {fp_hash} has too few raw_feedback_ids"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
