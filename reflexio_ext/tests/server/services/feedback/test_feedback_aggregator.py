"""
Unit tests for FeedbackAggregator private helpers and run() orchestration.

Targets coverage gaps in:
- _should_run_aggregation (refresh_count defaults, threshold logic)
- _determine_cluster_changes (no previous clusters, fingerprint match/mismatch)
- _build_change_log (empty changes, full archive, incremental with updates/removals)
- _update_operation_state (empty list, normal update)
- _get_feedback_aggregator_config (match, no match, no configs)
- _compute_cluster_fingerprint (deterministic, order-independent)
- run() (rerun mode, no raw feedbacks, incremental no changes, save exception,
         change log exception, full archive delete path, incremental archive delete)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from reflexio.server.services.feedback.feedback_aggregator import FeedbackAggregator
from reflexio.server.services.feedback.feedback_service_utils import (
    FeedbackAggregatorRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    Feedback,
    FeedbackStatus,
    RawFeedback,
)
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    FeedbackAggregatorConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_aggregator(
    storage: MagicMock | None = None,
    configurator: MagicMock | None = None,
) -> FeedbackAggregator:
    """Build an aggregator with fully mocked dependencies."""
    llm = MagicMock()
    ctx = MagicMock()
    ctx.storage = storage or MagicMock()
    ctx.configurator = configurator or MagicMock()
    ctx.org_id = "test-org"
    return FeedbackAggregator(
        llm_client=llm,
        request_context=ctx,
        agent_version="v1",
    )


def _raw(
    rid: int = 1,
    name: str = "test_fb",
    when: str | None = "when cond",
    do: str | None = "do action",
    dont: str | None = None,
) -> RawFeedback:
    return RawFeedback(
        raw_feedback_id=rid,
        agent_version="v1",
        request_id=f"req-{rid}",
        feedback_name=name,
        feedback_content=f"content-{rid}",
        when_condition=when,
        do_action=do,
        do_not_action=dont,
    )


def _feedback(fid: int = 1, name: str = "test_fb", content: str = "c") -> Feedback:
    return Feedback(
        feedback_id=fid,
        feedback_name=name,
        agent_version="v1",
        feedback_content=content,
        do_action="do",
        feedback_status=FeedbackStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# _should_run_aggregation
# ---------------------------------------------------------------------------


class TestShouldRunAggregation:
    """Tests for _should_run_aggregation."""

    def test_refresh_count_zero_defaults_to_two(self):
        """When refresh_count <= 0 the method should default to 2."""
        agg = _make_aggregator()
        # Bypass Pydantic ge=1 validation to hit the <= 0 guard in source
        config = FeedbackAggregatorConfig.model_construct(
            min_feedback_threshold=2, refresh_count=0
        )
        agg.storage.count_raw_feedbacks.return_value = 2

        result = agg._should_run_aggregation("fb", config)

        assert result is True
        # count >= default(2) -> True

    def test_refresh_count_negative_defaults_to_two(self):
        """Negative refresh_count also defaults to 2."""
        agg = _make_aggregator()
        # Bypass Pydantic ge=1 validation to hit the <= 0 guard in source
        config = FeedbackAggregatorConfig.model_construct(
            min_feedback_threshold=2, refresh_count=-1
        )
        agg.storage.count_raw_feedbacks.return_value = 2

        result = agg._should_run_aggregation("fb", config)

        assert result is True

    def test_enough_new_feedbacks_returns_true(self):
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=3)
        agg.storage.count_raw_feedbacks.return_value = 5

        assert agg._should_run_aggregation("fb", config) is True

    def test_not_enough_new_feedbacks_returns_false(self):
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=3)
        agg.storage.count_raw_feedbacks.return_value = 1

        assert agg._should_run_aggregation("fb", config) is False

    def test_rerun_flag_passed_to_count(self):
        """rerun=True should be forwarded so all feedbacks are counted."""
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=2)
        agg.storage.count_raw_feedbacks.return_value = 10

        agg._should_run_aggregation("fb", config, rerun=True)

        # rerun=True -> last_processed_id=0
        call_kwargs = agg.storage.count_raw_feedbacks.call_args
        assert (
            call_kwargs.kwargs.get("min_raw_feedback_id") == 0
            or call_kwargs[1].get("min_raw_feedback_id") == 0
        )


# ---------------------------------------------------------------------------
# _get_new_raw_feedbacks_count
# ---------------------------------------------------------------------------


class TestGetNewRawFeedbacksCount:
    def test_rerun_uses_zero_as_last_processed(self):
        agg = _make_aggregator()
        agg.storage.count_raw_feedbacks.return_value = 7

        result = agg._get_new_raw_feedbacks_count("fb", rerun=True)

        assert result == 7
        assert (
            agg.storage.count_raw_feedbacks.call_args.kwargs["min_raw_feedback_id"] == 0
        )

    def test_non_rerun_reads_bookmark(self):
        agg = _make_aggregator()
        agg.storage.count_raw_feedbacks.return_value = 3

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_aggregator_bookmark.return_value = 42
            mock_csm.return_value = mgr

            result = agg._get_new_raw_feedbacks_count("fb", rerun=False)

        assert result == 3
        assert (
            agg.storage.count_raw_feedbacks.call_args.kwargs["min_raw_feedback_id"]
            == 42
        )

    def test_non_rerun_bookmark_none_defaults_to_zero(self):
        agg = _make_aggregator()
        agg.storage.count_raw_feedbacks.return_value = 5

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_aggregator_bookmark.return_value = None
            mock_csm.return_value = mgr

            result = agg._get_new_raw_feedbacks_count("fb", rerun=False)

        assert result == 5
        assert (
            agg.storage.count_raw_feedbacks.call_args.kwargs["min_raw_feedback_id"] == 0
        )


# ---------------------------------------------------------------------------
# _update_operation_state
# ---------------------------------------------------------------------------


class TestUpdateOperationState:
    def test_empty_list_returns_early(self):
        agg = _make_aggregator()
        agg._update_operation_state("fb", [])
        # No state manager interaction expected

    def test_updates_with_max_id(self):
        agg = _make_aggregator()
        raws = [_raw(rid=3), _raw(rid=10), _raw(rid=7)]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mock_csm.return_value = mgr

            agg._update_operation_state("fb", raws)

        mgr.update_aggregator_bookmark.assert_called_once_with(
            name="fb", version="v1", last_processed_id=10
        )


# ---------------------------------------------------------------------------
# _compute_cluster_fingerprint
# ---------------------------------------------------------------------------


class TestComputeClusterFingerprint:
    def test_deterministic(self):
        raws = [_raw(rid=1), _raw(rid=2), _raw(rid=3)]
        fp1 = FeedbackAggregator._compute_cluster_fingerprint(raws)
        fp2 = FeedbackAggregator._compute_cluster_fingerprint(raws)
        assert fp1 == fp2

    def test_order_independent(self):
        raws_a = [_raw(rid=1), _raw(rid=3), _raw(rid=2)]
        raws_b = [_raw(rid=3), _raw(rid=1), _raw(rid=2)]
        assert FeedbackAggregator._compute_cluster_fingerprint(
            raws_a
        ) == FeedbackAggregator._compute_cluster_fingerprint(raws_b)

    def test_different_ids_produce_different_fingerprint(self):
        fp_a = FeedbackAggregator._compute_cluster_fingerprint([_raw(rid=1)])
        fp_b = FeedbackAggregator._compute_cluster_fingerprint([_raw(rid=2)])
        assert fp_a != fp_b

    def test_fingerprint_length(self):
        fp = FeedbackAggregator._compute_cluster_fingerprint([_raw(rid=1)])
        assert len(fp) == 16


# ---------------------------------------------------------------------------
# _determine_cluster_changes
# ---------------------------------------------------------------------------


class TestDetermineClusterChanges:
    def test_no_previous_fingerprints(self):
        """Empty prev_fingerprints => all clusters are changed, none to archive."""
        agg = _make_aggregator()
        clusters = {0: [_raw(rid=1), _raw(rid=2)]}

        changed, to_archive = agg._determine_cluster_changes(clusters, {})

        assert changed == clusters
        assert to_archive == []

    def test_fingerprint_match_no_changes(self):
        """Matching fingerprint => no changed clusters, none to archive."""
        agg = _make_aggregator()
        raws = [_raw(rid=1), _raw(rid=2)]
        clusters = {0: raws}
        fp = FeedbackAggregator._compute_cluster_fingerprint(raws)
        prev = {fp: {"feedback_id": 10, "raw_feedback_ids": [1, 2]}}

        changed, to_archive = agg._determine_cluster_changes(clusters, prev)

        assert changed == {}
        assert to_archive == []

    def test_fingerprint_mismatch_detects_change(self):
        """New fingerprint => cluster is changed; old fingerprint archived."""
        agg = _make_aggregator()
        raws_new = [_raw(rid=1), _raw(rid=2), _raw(rid=3)]
        clusters = {0: raws_new}
        prev = {"old_fp_hash": {"feedback_id": 5, "raw_feedback_ids": [1, 2]}}

        changed, to_archive = agg._determine_cluster_changes(clusters, prev)

        assert 0 in changed
        assert 5 in to_archive

    def test_disappeared_cluster_with_no_feedback_id(self):
        """Disappeared fingerprint with feedback_id=None should not be archived."""
        agg = _make_aggregator()
        clusters = {0: [_raw(rid=99)]}
        prev = {"gone_fp": {"feedback_id": None, "raw_feedback_ids": [1]}}

        changed, to_archive = agg._determine_cluster_changes(clusters, prev)

        assert 0 in changed
        assert to_archive == []

    def test_multiple_clusters_mixed(self):
        """Some clusters match, some do not."""
        agg = _make_aggregator()
        raws_unchanged = [_raw(rid=1)]
        raws_new = [_raw(rid=5), _raw(rid=6)]
        clusters = {0: raws_unchanged, 1: raws_new}

        fp_unchanged = FeedbackAggregator._compute_cluster_fingerprint(raws_unchanged)
        prev = {
            fp_unchanged: {"feedback_id": 10, "raw_feedback_ids": [1]},
            "vanished_fp": {"feedback_id": 20, "raw_feedback_ids": [2, 3]},
        }

        changed, to_archive = agg._determine_cluster_changes(clusters, prev)

        assert 0 not in changed
        assert 1 in changed
        assert 20 in to_archive


# ---------------------------------------------------------------------------
# _build_change_log
# ---------------------------------------------------------------------------


class TestBuildChangeLog:
    def test_full_archive_empty_before_and_saved(self):
        """Full archive with no previous or new feedbacks."""
        agg = _make_aggregator()
        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=True,
            before_feedbacks_by_id={},
            saved_feedbacks=[],
            archived_feedback_ids=[],
            prev_fingerprints={},
        )
        assert log.run_mode == "full_archive"
        assert log.added_feedbacks == []
        assert log.removed_feedbacks == []
        assert log.updated_feedbacks == []

    def test_full_archive_all_new_clusters(self):
        """Full archive: old feedbacks are removed, new ones added."""
        agg = _make_aggregator()
        old_fb = _feedback(fid=1, content="old")
        new_fb = _feedback(fid=2, content="new")

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=True,
            before_feedbacks_by_id={1: old_fb},
            saved_feedbacks=[new_fb],
            archived_feedback_ids=[],
            prev_fingerprints={},
        )

        assert len(log.removed_feedbacks) == 1
        assert log.removed_feedbacks[0].feedback_id == 1
        assert len(log.added_feedbacks) == 1
        assert log.added_feedbacks[0].feedback_id == 2

    def test_full_archive_filters_none_saved(self):
        """None entries in saved_feedbacks should be filtered out."""
        agg = _make_aggregator()
        fb = _feedback(fid=3)

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=True,
            before_feedbacks_by_id={},
            saved_feedbacks=[None, fb, None],  # type: ignore[list-item]
            archived_feedback_ids=[],
            prev_fingerprints={},
        )

        assert len(log.added_feedbacks) == 1

    def test_incremental_update_pairs_old_and_new(self):
        """Incremental mode pairs archived old feedbacks with saved new ones."""
        agg = _make_aggregator()
        old_fb = _feedback(fid=10, content="old")
        new_fb = _feedback(fid=20, content="new")

        prev_fps = {"fp1": {"feedback_id": 10, "raw_feedback_ids": [1]}}

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={10: old_fb},
            saved_feedbacks=[new_fb],
            archived_feedback_ids=[10],
            prev_fingerprints=prev_fps,
        )

        assert len(log.updated_feedbacks) == 1
        assert log.updated_feedbacks[0].before.feedback_id == 10
        assert log.updated_feedbacks[0].after.feedback_id == 20
        assert log.added_feedbacks == []
        assert log.removed_feedbacks == []

    def test_incremental_unmatched_archived_becomes_removed(self):
        """Archived feedback not paired with a new one should be a removal."""
        agg = _make_aggregator()
        old_fb = _feedback(fid=10, content="old")

        prev_fps = {"fp1": {"feedback_id": 10, "raw_feedback_ids": [1]}}

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={10: old_fb},
            saved_feedbacks=[],
            archived_feedback_ids=[10],
            prev_fingerprints=prev_fps,
        )

        assert len(log.removed_feedbacks) == 1
        assert log.removed_feedbacks[0].feedback_id == 10
        assert log.updated_feedbacks == []
        assert log.added_feedbacks == []

    def test_incremental_saved_with_no_archived_becomes_added(self):
        """Saved feedback with nothing archived -> addition."""
        agg = _make_aggregator()
        new_fb = _feedback(fid=20, content="new")

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={},
            saved_feedbacks=[new_fb],
            archived_feedback_ids=[],
            prev_fingerprints={},
        )

        assert len(log.added_feedbacks) == 1
        assert log.added_feedbacks[0].feedback_id == 20

    def test_incremental_filters_none_saved_feedbacks(self):
        """None entries in saved_feedbacks should be skipped in incremental mode."""
        agg = _make_aggregator()
        new_fb = _feedback(fid=20, content="new")

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={},
            saved_feedbacks=[None, new_fb],  # type: ignore[list-item]
            archived_feedback_ids=[],
            prev_fingerprints={},
        )

        assert len(log.added_feedbacks) == 1

    def test_incremental_paired_old_id_not_in_before_becomes_added(self):
        """If paired old_id exists but not in before_feedbacks_by_id, treat as added."""
        agg = _make_aggregator()
        new_fb = _feedback(fid=20, content="new")

        prev_fps = {"fp1": {"feedback_id": 10, "raw_feedback_ids": [1]}}

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={},  # 10 not present
            saved_feedbacks=[new_fb],
            archived_feedback_ids=[10],
            prev_fingerprints=prev_fps,
        )

        assert len(log.added_feedbacks) == 1
        assert log.added_feedbacks[0].feedback_id == 20

    def test_incremental_multiple_saved_skip_already_matched(self):
        """Branch 349->348: second saved_fb skips already-matched old_id."""
        agg = _make_aggregator()
        old_fb1 = _feedback(fid=10, content="old1")
        old_fb2 = _feedback(fid=11, content="old2")
        new_fb1 = _feedback(fid=20, content="new1")
        new_fb2 = _feedback(fid=21, content="new2")

        prev_fps = {
            "fp1": {"feedback_id": 10, "raw_feedback_ids": [1]},
            "fp2": {"feedback_id": 11, "raw_feedback_ids": [2]},
        }

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={10: old_fb1, 11: old_fb2},
            saved_feedbacks=[new_fb1, new_fb2],
            archived_feedback_ids=[10, 11],
            prev_fingerprints=prev_fps,
        )

        assert len(log.updated_feedbacks) == 2
        assert log.added_feedbacks == []
        assert log.removed_feedbacks == []

    def test_incremental_archived_not_in_before_ignored(self):
        """Archived id not present in before_feedbacks_by_id should be ignored for removals."""
        agg = _make_aggregator()

        log = agg._build_change_log(
            feedback_name="fb",
            full_archive=False,
            before_feedbacks_by_id={},
            saved_feedbacks=[],
            archived_feedback_ids=[999],
            prev_fingerprints={"fp1": {"feedback_id": 999, "raw_feedback_ids": [1]}},
        )

        assert log.removed_feedbacks == []


# ---------------------------------------------------------------------------
# _get_feedback_aggregator_config
# ---------------------------------------------------------------------------


class TestGetFeedbackAggregatorConfig:
    def test_returns_matching_config(self):
        agg = _make_aggregator()
        fac = FeedbackAggregatorConfig(min_feedback_threshold=3, refresh_count=5)
        afc = AgentFeedbackConfig(
            feedback_name="my_fb",
            feedback_definition_prompt="prompt",
            feedback_aggregator_config=fac,
        )
        agg.configurator.get_config.return_value.agent_feedback_configs = [afc]

        result = agg._get_feedback_aggregator_config("my_fb")

        assert result is fac

    def test_returns_none_when_no_match(self):
        agg = _make_aggregator()
        afc = AgentFeedbackConfig(
            feedback_name="other",
            feedback_definition_prompt="prompt",
        )
        agg.configurator.get_config.return_value.agent_feedback_configs = [afc]

        assert agg._get_feedback_aggregator_config("missing") is None

    def test_returns_none_when_no_agent_feedback_configs(self):
        agg = _make_aggregator()
        agg.configurator.get_config.return_value.agent_feedback_configs = None

        assert agg._get_feedback_aggregator_config("any") is None


# ---------------------------------------------------------------------------
# run() orchestration
# ---------------------------------------------------------------------------


class TestRun:
    """Tests for the top-level run() method using mocks."""

    def _make_runnable_aggregator(self):
        """Return an aggregator wired for a successful run()."""
        agg = _make_aggregator()
        # config
        fac = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=2)
        afc = AgentFeedbackConfig(
            feedback_name="fb",
            feedback_definition_prompt="prompt",
            feedback_aggregator_config=fac,
        )
        agg.configurator.get_config.return_value.agent_feedback_configs = [afc]
        # storage returns
        agg.storage.count_raw_feedbacks.return_value = 5
        agg.storage.get_feedbacks.return_value = []
        agg.storage.get_raw_feedbacks.return_value = [_raw(rid=1), _raw(rid=2)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=100)]
        return agg

    def test_no_config_returns_early(self):
        agg = _make_aggregator()
        agg.configurator.get_config.return_value.agent_feedback_configs = None

        req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
        agg.run(req)

        agg.storage.get_raw_feedbacks.assert_not_called()

    def test_min_threshold_below_two_returns_early(self):
        agg = _make_aggregator()
        fac = FeedbackAggregatorConfig(min_feedback_threshold=1, refresh_count=2)
        afc = AgentFeedbackConfig(
            feedback_name="fb",
            feedback_definition_prompt="prompt",
            feedback_aggregator_config=fac,
        )
        agg.configurator.get_config.return_value.agent_feedback_configs = [afc]

        req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
        agg.run(req)

        agg.storage.get_raw_feedbacks.assert_not_called()

    def test_not_enough_new_feedbacks_skips(self):
        agg = _make_aggregator()
        fac = FeedbackAggregatorConfig(min_feedback_threshold=2, refresh_count=10)
        afc = AgentFeedbackConfig(
            feedback_name="fb",
            feedback_definition_prompt="prompt",
            feedback_aggregator_config=fac,
        )
        agg.configurator.get_config.return_value.agent_feedback_configs = [afc]
        agg.storage.count_raw_feedbacks.return_value = 1

        req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
        agg.run(req)

        agg.storage.get_raw_feedbacks.assert_not_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_rerun_mode_archives_all(self, mock_gen, mock_clust):
        """rerun=True should call archive_feedbacks_by_feedback_name."""
        agg = self._make_runnable_aggregator()
        mock_clust.return_value = {0: [_raw(rid=1)]}
        mock_gen.return_value = [_feedback(fid=100)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=100)]

        req = FeedbackAggregatorRequest(
            agent_version="v1", feedback_name="fb", rerun=True
        )
        agg.run(req)

        agg.storage.archive_feedbacks_by_feedback_name.assert_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_rerun_deletes_archived_feedbacks_after_success(self, mock_gen, mock_clust):
        """After successful rerun, delete_archived_feedbacks_by_feedback_name is called."""
        agg = self._make_runnable_aggregator()
        mock_clust.return_value = {0: [_raw(rid=1)]}
        mock_gen.return_value = [_feedback(fid=100)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=100)]

        req = FeedbackAggregatorRequest(
            agent_version="v1", feedback_name="fb", rerun=True
        )
        agg.run(req)

        agg.storage.delete_archived_feedbacks_by_feedback_name.assert_called_once()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_first_run_no_prev_fingerprints_full_archive(self, mock_gen, mock_clust):
        """First run (no previous fingerprints) triggers full archive."""
        agg = self._make_runnable_aggregator()
        mock_clust.return_value = {0: [_raw(rid=1), _raw(rid=2)]}
        mock_gen.return_value = [_feedback(fid=100)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=100)]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        agg.storage.archive_feedbacks_by_feedback_name.assert_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    def test_incremental_no_changes_updates_bookmark_only(self, mock_clust):
        """When no cluster changes detected, update bookmark and return."""
        agg = self._make_runnable_aggregator()
        raws = [_raw(rid=1)]
        agg.storage.get_raw_feedbacks.return_value = raws
        mock_clust.return_value = {0: raws}
        fp = FeedbackAggregator._compute_cluster_fingerprint(raws)

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {
                fp: {"feedback_id": 10, "raw_feedback_ids": [1]}
            }
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        # Should NOT call _generate_feedback_from_clusters
        agg.storage.save_feedbacks.assert_not_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_incremental_with_changes_archives_selectively(self, mock_gen, mock_clust):
        """Incremental mode with changed clusters archives only affected feedback_ids."""
        agg = self._make_runnable_aggregator()
        raws_new = [_raw(rid=5), _raw(rid=6)]
        agg.storage.get_raw_feedbacks.return_value = raws_new
        mock_clust.return_value = {0: raws_new}
        mock_gen.return_value = [_feedback(fid=200)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=200)]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {
                "old_fp": {"feedback_id": 50, "raw_feedback_ids": [1, 2]}
            }
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        agg.storage.archive_feedbacks_by_ids.assert_called_once_with([50])
        agg.storage.delete_feedbacks_by_ids.assert_called_once_with([50])

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_save_exception_restores_full_archive(self, mock_gen, mock_clust):
        """Exception during save_feedbacks in full-archive mode restores feedbacks."""
        agg = self._make_runnable_aggregator()
        mock_clust.return_value = {0: [_raw(rid=1)]}
        mock_gen.side_effect = RuntimeError("LLM failed")

        req = FeedbackAggregatorRequest(
            agent_version="v1", feedback_name="fb", rerun=True
        )

        with pytest.raises(RuntimeError, match="LLM failed"):
            agg.run(req)

        agg.storage.restore_archived_feedbacks_by_feedback_name.assert_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_save_exception_restores_incremental_archive(self, mock_gen, mock_clust):
        """Exception during save_feedbacks in incremental mode restores by ids."""
        agg = self._make_runnable_aggregator()
        raws_new = [_raw(rid=5)]
        agg.storage.get_raw_feedbacks.return_value = raws_new
        mock_clust.return_value = {0: raws_new}
        mock_gen.side_effect = RuntimeError("Boom")

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {
                "old_fp": {"feedback_id": 50, "raw_feedback_ids": [1]}
            }
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")

            with pytest.raises(RuntimeError, match="Boom"):
                agg.run(req)

        agg.storage.restore_archived_feedbacks_by_ids.assert_called_once_with([50])

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_change_log_exception_is_caught(self, mock_gen, mock_clust):
        """Exception in add_feedback_aggregation_change_log should be caught, not raised."""
        agg = self._make_runnable_aggregator()
        mock_clust.return_value = {0: [_raw(rid=1)]}
        mock_gen.return_value = [_feedback(fid=100)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=100)]
        agg.storage.add_feedback_aggregation_change_log.side_effect = RuntimeError(
            "DB down"
        )

        req = FeedbackAggregatorRequest(
            agent_version="v1", feedback_name="fb", rerun=True
        )

        # Should NOT raise
        agg.run(req)

        # Despite the exception, delete should still proceed
        agg.storage.delete_archived_feedbacks_by_feedback_name.assert_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_run_fingerprint_state_updated(self, mock_gen, mock_clust):
        """Fingerprint state should be updated after a successful run."""
        agg = self._make_runnable_aggregator()
        raws = [_raw(rid=1), _raw(rid=2)]
        mock_clust.return_value = {0: raws}
        saved = _feedback(fid=100)
        saved.feedback_id = 100
        mock_gen.return_value = [saved]
        agg.storage.save_feedbacks.return_value = [saved]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        mgr.update_cluster_fingerprints.assert_called_once()
        call_kwargs = mgr.update_cluster_fingerprints.call_args
        fingerprints_arg = call_kwargs.kwargs.get("fingerprints") or call_kwargs[1].get(
            "fingerprints"
        )
        assert fingerprints_arg is not None
        # The fingerprint for the cluster should have feedback_id=100 assigned
        for fp_data in fingerprints_arg.values():
            if fp_data["feedback_id"] is not None:
                assert fp_data["feedback_id"] == 100

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_incremental_changed_clusters_but_no_archived_ids(
        self, mock_gen, mock_clust
    ):
        """Branch 508->511: changed clusters exist but archived_feedback_ids is empty."""
        agg = self._make_runnable_aggregator()
        raws_new = [_raw(rid=5), _raw(rid=6)]
        agg.storage.get_raw_feedbacks.return_value = raws_new
        mock_clust.return_value = {0: raws_new}
        mock_gen.return_value = [_feedback(fid=200)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=200)]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            # prev fingerprints exist but the new cluster fingerprint is different,
            # and the old fingerprint has feedback_id=None so nothing to archive
            mgr.get_cluster_fingerprints.return_value = {
                "old_fp": {"feedback_id": None, "raw_feedback_ids": [1, 2]}
            }
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        # archive_feedbacks_by_ids should NOT be called (no ids to archive)
        agg.storage.archive_feedbacks_by_ids.assert_not_called()
        # delete_feedbacks_by_ids should NOT be called either (branch 627->exit)
        agg.storage.delete_feedbacks_by_ids.assert_not_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_saved_fb_without_feedback_id_skipped_in_fingerprint_assignment(
        self, mock_gen, mock_clust
    ):
        """Branch 577->576: saved_fb with falsy feedback_id skipped during fp assignment."""
        agg = self._make_runnable_aggregator()
        raws = [_raw(rid=1)]
        mock_clust.return_value = {0: raws}
        # Feedback with feedback_id=0 (falsy)
        fb_no_id = _feedback(fid=0, content="no id")
        fb_no_id.feedback_id = 0
        mock_gen.return_value = [fb_no_id]
        agg.storage.save_feedbacks.return_value = [fb_no_id]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        mgr.update_cluster_fingerprints.assert_called_once()
        call_kwargs = mgr.update_cluster_fingerprints.call_args
        new_fps = call_kwargs.kwargs.get("fingerprints") or call_kwargs[1].get(
            "fingerprints"
        )
        # The fingerprint should still have feedback_id=None since fb_no_id.feedback_id was falsy
        for fp_data in new_fps.values():
            assert fp_data["feedback_id"] is None

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_exception_in_incremental_no_archived_ids_still_raises(
        self, mock_gen, mock_clust
    ):
        """Branch 641->644: exception in incremental mode with empty archived_feedback_ids."""
        agg = self._make_runnable_aggregator()
        raws_new = [_raw(rid=5)]
        agg.storage.get_raw_feedbacks.return_value = raws_new
        mock_clust.return_value = {0: raws_new}
        mock_gen.side_effect = RuntimeError("Kaboom")

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            # prev fingerprints with no feedback_id => no archived_feedback_ids
            mgr.get_cluster_fingerprints.return_value = {
                "old_fp": {"feedback_id": None, "raw_feedback_ids": [1]}
            }
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")

            with pytest.raises(RuntimeError, match="Kaboom"):
                agg.run(req)

        # Neither restore method should be called since archived_feedback_ids is empty
        # and full_archive is False
        agg.storage.restore_archived_feedbacks_by_feedback_name.assert_not_called()
        agg.storage.restore_archived_feedbacks_by_ids.assert_not_called()

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_run_with_none_saved_feedbacks_in_list(self, mock_gen, mock_clust):
        """saved_feedbacks list containing None entries should not cause errors."""
        agg = self._make_runnable_aggregator()
        raws = [_raw(rid=1)]
        mock_clust.return_value = {0: raws}
        mock_gen.return_value = [None]
        agg.storage.save_feedbacks.return_value = [None]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            # Should not raise
            agg.run(req)

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_multiple_saved_feedbacks_assigned_to_multiple_fingerprints(
        self, mock_gen, mock_clust
    ):
        """Branch 580->579: second saved_fb skips first fp (already assigned) and finds second."""
        agg = self._make_runnable_aggregator()
        raws_a = [_raw(rid=1)]
        raws_b = [_raw(rid=2)]
        mock_clust.return_value = {0: raws_a, 1: raws_b}
        fb1 = _feedback(fid=100, content="a")
        fb1.feedback_id = 100
        fb2 = _feedback(fid=200, content="b")
        fb2.feedback_id = 200
        mock_gen.return_value = [fb1, fb2]
        agg.storage.save_feedbacks.return_value = [fb1, fb2]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        mgr.update_cluster_fingerprints.assert_called_once()
        call_kwargs = mgr.update_cluster_fingerprints.call_args
        new_fps = call_kwargs.kwargs.get("fingerprints") or call_kwargs[1].get(
            "fingerprints"
        )
        # Both fingerprints should have feedback_ids assigned
        assigned_ids = [
            v["feedback_id"] for v in new_fps.values() if v["feedback_id"] is not None
        ]
        assert len(assigned_ids) == 2
        assert set(assigned_ids) == {100, 200}

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_saved_fb_no_matching_fingerprint_exhausts_loop(self, mock_gen, mock_clust):
        """Branch 579->576: inner loop exhausts without finding a match (all fps have ids)."""
        agg = self._make_runnable_aggregator()
        raws = [_raw(rid=1)]
        mock_clust.return_value = {0: raws}
        fb1 = _feedback(fid=100, content="a")
        fb1.feedback_id = 100
        # Two saved feedbacks but only one cluster fingerprint
        fb2 = _feedback(fid=200, content="b")
        fb2.feedback_id = 200
        mock_gen.return_value = [fb1, fb2]
        agg.storage.save_feedbacks.return_value = [fb1, fb2]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            mgr.get_cluster_fingerprints.return_value = {}
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        mgr.update_cluster_fingerprints.assert_called_once()
        call_kwargs = mgr.update_cluster_fingerprints.call_args
        new_fps = call_kwargs.kwargs.get("fingerprints") or call_kwargs[1].get(
            "fingerprints"
        )
        # Only one fingerprint exists, should have first fb's id
        assigned_ids = [
            v["feedback_id"] for v in new_fps.values() if v["feedback_id"] is not None
        ]
        assert len(assigned_ids) == 1
        assert assigned_ids[0] == 100

    @patch.object(FeedbackAggregator, "get_clusters")
    @patch.object(FeedbackAggregator, "_generate_feedback_from_clusters")
    def test_incremental_carries_forward_unchanged_fingerprints(
        self, mock_gen, mock_clust
    ):
        """Unchanged cluster fingerprints are carried forward in incremental mode."""
        agg = self._make_runnable_aggregator()
        # Two clusters: one unchanged, one new
        raws_unchanged = [_raw(rid=1)]
        raws_new = [_raw(rid=5), _raw(rid=6)]
        fp_unchanged = FeedbackAggregator._compute_cluster_fingerprint(raws_unchanged)

        all_raws = raws_unchanged + raws_new
        agg.storage.get_raw_feedbacks.return_value = all_raws
        mock_clust.return_value = {0: raws_unchanged, 1: raws_new}
        mock_gen.return_value = [_feedback(fid=200)]
        agg.storage.save_feedbacks.return_value = [_feedback(fid=200)]

        with patch.object(FeedbackAggregator, "_create_state_manager") as mock_csm:
            mgr = MagicMock()
            prev_fps = {
                fp_unchanged: {"feedback_id": 10, "raw_feedback_ids": [1]},
                "vanished_fp": {"feedback_id": 20, "raw_feedback_ids": [2]},
            }
            mgr.get_cluster_fingerprints.return_value = prev_fps
            mock_csm.return_value = mgr

            req = FeedbackAggregatorRequest(agent_version="v1", feedback_name="fb")
            agg.run(req)

        mgr.update_cluster_fingerprints.assert_called_once()
        call_kwargs = mgr.update_cluster_fingerprints.call_args
        new_fps = call_kwargs.kwargs.get("fingerprints") or call_kwargs[1].get(
            "fingerprints"
        )
        # Unchanged fingerprint should be carried forward
        assert fp_unchanged in new_fps
        assert new_fps[fp_unchanged]["feedback_id"] == 10


# ---------------------------------------------------------------------------
# _format_structured_cluster_input
# ---------------------------------------------------------------------------


class TestFormatStructuredClusterInput:
    def test_all_fields_present(self):
        agg = _make_aggregator()
        raws = [
            _raw(rid=1, when="cond1", do="action1", dont="avoid1"),
            _raw(rid=2, when="cond2", do="action2", dont="avoid2"),
        ]

        result = agg._format_structured_cluster_input(raws)

        assert "WHEN conditions (to be consolidated):" in result
        assert "- cond1" in result
        assert "- cond2" in result
        assert "DO actions:" in result
        assert "- action1" in result
        assert "DON'T actions:" in result
        assert "- avoid1" in result

    def test_no_when_conditions(self):
        agg = _make_aggregator()
        raws = [_raw(rid=1, when=None, do="action1")]

        result = agg._format_structured_cluster_input(raws)

        assert "WHEN conditions: (none specified)" in result

    def test_no_do_actions(self):
        agg = _make_aggregator()
        raws = [_raw(rid=1, when="cond", do=None, dont="avoid")]

        result = agg._format_structured_cluster_input(raws)

        assert "DO actions:" not in result
        assert "DON'T actions:" in result

    def test_no_dont_actions(self):
        agg = _make_aggregator()
        raws = [_raw(rid=1, when="cond", do="action", dont=None)]

        result = agg._format_structured_cluster_input(raws)

        assert "DON'T actions:" not in result
        assert "DO actions:" in result


# ---------------------------------------------------------------------------
# get_clusters
# ---------------------------------------------------------------------------


class TestGetClusters:
    def test_no_config_returns_empty(self):
        agg = _make_aggregator()
        result = agg.get_clusters([_raw()], None)  # type: ignore[arg-type]
        assert result == {}

    def test_no_raw_feedbacks_returns_empty(self):
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        result = agg.get_clusters([], config)
        assert result == {}

    def test_fewer_than_min_returns_empty(self):
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=5)
        raws = [_raw(rid=i) for i in range(3)]
        # Need real embeddings for len check
        for r in raws:
            r.embedding = [0.0] * 10

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": ""}):
            result = agg.get_clusters(raws, config)

        assert result == {}

    def test_mock_mode_clusters_by_when_condition(self):
        agg = _make_aggregator()
        config = FeedbackAggregatorConfig(min_feedback_threshold=2)
        raws = [
            _raw(rid=1, when="cond_a"),
            _raw(rid=2, when="cond_a"),
            _raw(rid=3, when="cond_b"),
        ]

        with patch.dict("os.environ", {"MOCK_LLM_RESPONSE": "true"}):
            result = agg.get_clusters(raws, config)

        # Only cond_a has 2 feedbacks (meets threshold)
        assert len(result) == 1
        assert len(list(result.values())[0]) == 2


# ---------------------------------------------------------------------------
# _process_aggregation_response
# ---------------------------------------------------------------------------


class TestProcessAggregationResponse:
    def test_none_response_returns_none(self):
        agg = _make_aggregator()
        assert agg._process_aggregation_response(None, [_raw()]) is None  # type: ignore[arg-type]

    def test_null_feedback_returns_none(self):
        from reflexio.server.services.feedback.feedback_service_utils import (
            FeedbackAggregationOutput,
        )

        agg = _make_aggregator()
        response = FeedbackAggregationOutput(feedback=None)
        assert agg._process_aggregation_response(response, [_raw()]) is None

    def test_valid_response_returns_feedback(self):
        from reflexio.server.services.feedback.feedback_service_utils import (
            FeedbackAggregationOutput,
            StructuredFeedbackContent,
        )

        agg = _make_aggregator()
        structured = StructuredFeedbackContent(
            do_action="do something",
            when_condition="when testing",
        )
        response = FeedbackAggregationOutput(feedback=structured)

        result = agg._process_aggregation_response(response, [_raw()])

        assert result is not None
        assert result.do_action == "do something"
        assert result.when_condition == "when testing"
        assert result.feedback_status == FeedbackStatus.PENDING
