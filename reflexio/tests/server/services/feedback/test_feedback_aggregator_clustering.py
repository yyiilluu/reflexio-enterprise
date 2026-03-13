"""
Unit tests for feedback aggregator clustering algorithms.

Tests both Agglomerative Clustering (small datasets) and HDBSCAN (large datasets)
to ensure the hybrid approach works correctly.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# Disable mock mode for clustering tests so actual clustering algorithms are used
@pytest.fixture(autouse=True)
def disable_mock_llm_response(monkeypatch):
    """Disable MOCK_LLM_RESPONSE env var so clustering tests use real algorithms."""
    monkeypatch.delenv("MOCK_LLM_RESPONSE", raising=False)


from reflexio_commons.api_schema.service_schemas import RawFeedback
from reflexio_commons.config_schema import FeedbackAggregatorConfig

from reflexio.server.services.feedback.feedback_aggregator import (
    CLUSTERING_ALGORITHM_THRESHOLD,
    FeedbackAggregator,
)


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
        # Small noise to create similar but not identical vectors
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
    embeddings: list[list[float]], feedback_name: str = "test_feedback"
) -> list[RawFeedback]:
    """
    Create RawFeedback objects with given embeddings.

    Args:
        embeddings: List of embeddings
        feedback_name: Name for the feedbacks

    Returns:
        List of RawFeedback objects
    """
    return [
        RawFeedback(
            raw_feedback_id=i,
            agent_version="1.0",
            request_id=str(i),
            feedback_content=f"Feedback content {i}",
            feedback_name=feedback_name,
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


class TestAgglomerativeClustering:
    """Tests for Agglomerative Clustering (small datasets < 50)."""

    def test_clusters_similar_feedbacks_small_dataset(self, mock_feedback_aggregator):
        """Test that similar feedbacks are clustered together with small dataset."""
        # Create 4 similar embeddings (should form 1 cluster)
        embeddings = create_similar_embeddings(4)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # All 4 similar feedbacks should be in one cluster
        assert len(clusters) == 1
        assert len(list(clusters.values())[0]) == 4

    def test_separates_dissimilar_feedbacks_small_dataset(
        self, mock_feedback_aggregator
    ):
        """Test that dissimilar feedbacks are not clustered together."""
        # Create 4 dissimilar embeddings
        embeddings = create_dissimilar_embeddings(4)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # Dissimilar feedbacks should not form clusters meeting min threshold
        # Each will be in its own cluster of size 1, filtered out
        assert len(clusters) == 0

    def test_mixed_similar_dissimilar_small_dataset(self, mock_feedback_aggregator):
        """Test clustering with a mix of similar and dissimilar feedbacks."""
        np.random.seed(42)

        # Create 2 groups of similar feedbacks + 2 dissimilar ones
        group1 = create_similar_embeddings(3, base_seed=42)
        group2 = create_similar_embeddings(3, base_seed=100)
        dissimilar = create_dissimilar_embeddings(2, base_seed=200)

        all_embeddings = group1 + group2 + dissimilar
        raw_feedbacks = create_raw_feedbacks_with_embeddings(all_embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # Should have 2 clusters (one for each similar group)
        # The 2 dissimilar ones should be filtered out or in separate small clusters
        assert len(clusters) >= 1

        # Verify each cluster has at least min_feedback_threshold feedbacks
        for cluster_feedbacks in clusters.values():
            assert len(cluster_feedbacks) >= 2

    def test_uses_agglomerative_for_small_dataset(self, mock_feedback_aggregator):
        """Test that Agglomerative Clustering is used for small datasets."""
        embeddings = create_similar_embeddings(10)  # < 50 threshold
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        with (
            patch.object(
                mock_feedback_aggregator,
                "_cluster_with_agglomerative",
                wraps=mock_feedback_aggregator._cluster_with_agglomerative,
            ) as mock_agg,
            patch.object(
                mock_feedback_aggregator,
                "_cluster_with_hdbscan",
                wraps=mock_feedback_aggregator._cluster_with_hdbscan,
            ) as mock_hdb,
        ):
            mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

            # Should use Agglomerative, not HDBSCAN
            mock_agg.assert_called_once()
            mock_hdb.assert_not_called()


class TestHDBSCANClustering:
    """Tests for HDBSCAN (large datasets >= 50)."""

    def test_clusters_similar_feedbacks_large_dataset(self, mock_feedback_aggregator):
        """Test that similar feedbacks are clustered together with large dataset."""
        # Create 60 similar embeddings (should form 1 cluster)
        embeddings = create_similar_embeddings(60)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # Similar feedbacks should form clusters
        total_clustered = sum(len(c) for c in clusters.values())
        assert (
            total_clustered >= 15
        )  # HDBSCAN clusters a subset; exact count depends on dimensions

    def test_identifies_noise_in_large_dataset(self, mock_feedback_aggregator):
        """Test that HDBSCAN identifies noise/outliers in large dataset."""
        # Create 55 similar embeddings + 5 outliers
        similar = create_similar_embeddings(55, base_seed=42)
        outliers = create_dissimilar_embeddings(5, base_seed=200)

        all_embeddings = similar + outliers
        raw_feedbacks = create_raw_feedbacks_with_embeddings(all_embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # The 55 similar should mostly be clustered, outliers may be noise
        total_clustered = sum(len(c) for c in clusters.values())
        assert total_clustered >= 45  # Most similar ones should be clustered

    def test_uses_hdbscan_for_large_dataset(self, mock_feedback_aggregator):
        """Test that HDBSCAN is used for large datasets."""
        embeddings = create_similar_embeddings(60)  # >= 50 threshold
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        with (
            patch.object(
                mock_feedback_aggregator,
                "_cluster_with_agglomerative",
                wraps=mock_feedback_aggregator._cluster_with_agglomerative,
            ) as mock_agg,
            patch.object(
                mock_feedback_aggregator,
                "_cluster_with_hdbscan",
                wraps=mock_feedback_aggregator._cluster_with_hdbscan,
            ) as mock_hdb,
        ):
            mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

            # Should use HDBSCAN, not Agglomerative
            mock_hdb.assert_called_once()
            mock_agg.assert_not_called()


class TestClusteringThreshold:
    """Tests for the clustering algorithm threshold."""

    def test_threshold_boundary_below(self, mock_feedback_aggregator):
        """Test that datasets just below threshold use Agglomerative."""
        n = CLUSTERING_ALGORITHM_THRESHOLD - 1
        embeddings = create_similar_embeddings(n)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        with patch.object(
            mock_feedback_aggregator,
            "_cluster_with_agglomerative",
            wraps=mock_feedback_aggregator._cluster_with_agglomerative,
        ) as mock_agg:
            mock_feedback_aggregator.get_clusters(raw_feedbacks, config)
            mock_agg.assert_called_once()

    def test_threshold_boundary_at(self, mock_feedback_aggregator):
        """Test that datasets at threshold use HDBSCAN."""
        n = CLUSTERING_ALGORITHM_THRESHOLD
        embeddings = create_similar_embeddings(n)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        with patch.object(
            mock_feedback_aggregator,
            "_cluster_with_hdbscan",
            wraps=mock_feedback_aggregator._cluster_with_hdbscan,
        ) as mock_hdb:
            mock_feedback_aggregator.get_clusters(raw_feedbacks, config)
            mock_hdb.assert_called_once()


class TestEdgeCases:
    """Tests for edge cases in clustering."""

    def test_empty_feedbacks(self, mock_feedback_aggregator):
        """Test clustering with empty feedback list."""
        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters([], config)

        assert clusters == {}

    def test_single_feedback(self, mock_feedback_aggregator):
        """Test clustering with single feedback (below min threshold)."""
        embeddings = create_similar_embeddings(1)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        assert clusters == {}

    def test_exactly_min_threshold_similar(self, mock_feedback_aggregator):
        """Test clustering with exactly min_threshold similar feedbacks."""
        embeddings = create_similar_embeddings(2)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=2)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # Should form exactly 1 cluster with 2 feedbacks
        assert len(clusters) == 1
        assert len(list(clusters.values())[0]) == 2

    def test_min_threshold_of_three(self, mock_feedback_aggregator):
        """Test clustering with min_threshold=3."""
        # Create 5 similar embeddings
        embeddings = create_similar_embeddings(5)
        raw_feedbacks = create_raw_feedbacks_with_embeddings(embeddings)

        config = FeedbackAggregatorConfig(min_feedback_threshold=3)

        clusters = mock_feedback_aggregator.get_clusters(raw_feedbacks, config)

        # All 5 should be in one cluster (>= 3)
        assert len(clusters) == 1
        assert len(list(clusters.values())[0]) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
