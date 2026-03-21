"""Unit tests for FeedbackMixin.

Tests get_feedbacks, add_feedback, delete_feedback, search_feedbacks,
delete_all_feedbacks_bulk, and update_feedback_status with mocked storage.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from reflexio_commons.api_schema.retriever_schema import (
    GetFeedbacksRequest,
    SearchFeedbackRequest,
    UpdateFeedbackStatusRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    AddFeedbackRequest,
    DeleteFeedbackRequest,
    DeleteFeedbacksByIdsRequest,
    Feedback,
    FeedbackStatus,
)

from reflexio.reflexio_lib._feedback import FeedbackMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin(*, storage_configured: bool = True) -> FeedbackMixin:
    """Create a FeedbackMixin instance with mocked internals."""
    mixin = object.__new__(FeedbackMixin)
    mock_storage = MagicMock()

    mock_request_context = MagicMock()
    mock_request_context.org_id = "test_org"
    mock_request_context.storage = mock_storage if storage_configured else None
    mock_request_context.is_storage_configured.return_value = storage_configured

    mixin.request_context = mock_request_context
    return mixin


def _get_storage(mixin: FeedbackMixin) -> MagicMock:
    return mixin.request_context.storage


def _sample_feedback(**overrides) -> Feedback:
    defaults = {
        "agent_version": "v1",
        "feedback_name": "test_fb",
        "feedback_content": "test feedback content",
    }
    defaults.update(overrides)
    return Feedback(**defaults)


# ---------------------------------------------------------------------------
# get_feedbacks
# ---------------------------------------------------------------------------


class TestGetFeedbacks:
    def test_returns_feedbacks(self):
        """Successful retrieval returns feedbacks from storage."""
        mixin = _make_mixin()
        sample = _sample_feedback()
        _get_storage(mixin).get_feedbacks.return_value = [sample]

        request = GetFeedbacksRequest(limit=10)
        response = mixin.get_feedbacks(request)

        assert response.success is True
        assert len(response.feedbacks) == 1

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = GetFeedbacksRequest()
        response = mixin.get_feedbacks(request)

        assert response.success is True
        assert response.feedbacks == []
        assert response.msg is not None

    def test_dict_input(self):
        """Accepts dict input and auto-converts."""
        mixin = _make_mixin()
        _get_storage(mixin).get_feedbacks.return_value = []

        response = mixin.get_feedbacks({"limit": 5, "feedback_name": "my_fb"})

        assert response.success is True
        _get_storage(mixin).get_feedbacks.assert_called_once()


# ---------------------------------------------------------------------------
# get_feedback_aggregation_change_logs
# ---------------------------------------------------------------------------


class TestGetFeedbackAggregationChangeLogs:
    def test_returns_change_logs(self):
        """Returns change logs from storage."""
        from reflexio_commons.api_schema.service_schemas import (
            FeedbackAggregationChangeLog,
        )

        mixin = _make_mixin()
        sample_log = FeedbackAggregationChangeLog(
            feedback_name="test_fb",
            agent_version="v1",
            run_mode="incremental",
        )
        _get_storage(mixin).get_feedback_aggregation_change_logs.return_value = [
            sample_log
        ]

        response = mixin.get_feedback_aggregation_change_logs(
            feedback_name="test_fb", agent_version="v1"
        )

        assert response.success is True
        assert len(response.change_logs) == 1

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.get_feedback_aggregation_change_logs(
            feedback_name="test_fb", agent_version="v1"
        )

        assert response.success is True
        assert response.change_logs == []


# ---------------------------------------------------------------------------
# add_feedback
# ---------------------------------------------------------------------------


class TestAddFeedback:
    def test_normalization(self):
        """Normalizes feedbacks and saves them."""
        mixin = _make_mixin()
        fb = _sample_feedback(feedback_metadata="meta info")
        request = AddFeedbackRequest(feedbacks=[fb])

        response = mixin.add_feedback(request)

        assert response.success is True
        assert response.added_count == 1
        saved = _get_storage(mixin).save_feedbacks.call_args[0][0]
        assert saved[0].feedback_metadata == "meta info"
        assert saved[0].feedback_content == "test feedback content"

    def test_metadata_defaults_to_empty(self):
        """feedback_metadata defaults to empty string when not provided."""
        mixin = _make_mixin()
        # Create a Feedback without feedback_metadata; the mixin normalizes it to ""
        fb = _sample_feedback()  # no metadata provided => defaults to ""
        request = AddFeedbackRequest(feedbacks=[fb])

        response = mixin.add_feedback(request)

        assert response.success is True
        saved = _get_storage(mixin).save_feedbacks.call_args[0][0]
        assert saved[0].feedback_metadata == ""

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)
        fb = _sample_feedback()
        request = AddFeedbackRequest(feedbacks=[fb])

        response = mixin.add_feedback(request)

        assert response.success is False

    def test_storage_exception(self):
        """Returns failure on storage exception."""
        mixin = _make_mixin()
        _get_storage(mixin).save_feedbacks.side_effect = RuntimeError("db error")

        fb = _sample_feedback()
        request = AddFeedbackRequest(feedbacks=[fb])

        response = mixin.add_feedback(request)

        assert response.success is False
        assert "db error" in (response.message or "")


# ---------------------------------------------------------------------------
# delete_feedback
# ---------------------------------------------------------------------------


class TestDeleteFeedback:
    def test_single_delete(self):
        """Deletes a feedback by ID."""
        mixin = _make_mixin()

        request = DeleteFeedbackRequest(feedback_id=99)
        response = mixin.delete_feedback(request)

        assert response.success is True
        _get_storage(mixin).delete_feedback.assert_called_once_with(99)

    def test_dict_input(self):
        """Accepts dict input."""
        mixin = _make_mixin()

        response = mixin.delete_feedback({"feedback_id": 42})

        assert response.success is True
        _get_storage(mixin).delete_feedback.assert_called_once_with(42)

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteFeedbackRequest(feedback_id=99)
        response = mixin.delete_feedback(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# search_feedbacks
# ---------------------------------------------------------------------------


class TestSearchFeedbacks:
    def test_query_delegation(self):
        """Delegates search to storage."""
        mixin = _make_mixin()
        sample = _sample_feedback()
        _get_storage(mixin).search_feedbacks.return_value = [sample]

        request = SearchFeedbackRequest(query="test")
        response = mixin.search_feedbacks(request)

        assert response.success is True
        assert len(response.feedbacks) == 1
        _get_storage(mixin).search_feedbacks.assert_called_once()

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = SearchFeedbackRequest(query="test")
        response = mixin.search_feedbacks(request)

        assert response.success is True
        assert response.feedbacks == []


# ---------------------------------------------------------------------------
# delete_all_feedbacks_bulk (cascading delete)
# ---------------------------------------------------------------------------


class TestDeleteAllFeedbacksBulk:
    def test_cascading_delete(self):
        """Deletes both feedbacks and raw feedbacks."""
        mixin = _make_mixin()

        response = mixin.delete_all_feedbacks_bulk()

        assert response.success is True
        _get_storage(mixin).delete_all_feedbacks.assert_called_once()
        _get_storage(mixin).delete_all_raw_feedbacks.assert_called_once()

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.delete_all_feedbacks_bulk()

        assert response.success is False


# ---------------------------------------------------------------------------
# update_feedback_status
# ---------------------------------------------------------------------------


class TestUpdateFeedbackStatus:
    def test_update_status(self):
        """Updates the feedback status via storage."""
        mixin = _make_mixin()

        request = UpdateFeedbackStatusRequest(
            feedback_id=10, feedback_status=FeedbackStatus.APPROVED
        )
        response = mixin.update_feedback_status(request)

        assert response.success is True
        _get_storage(mixin).update_feedback_status.assert_called_once_with(
            feedback_id=10, feedback_status=FeedbackStatus.APPROVED
        )

    def test_dict_input(self):
        """Accepts dict input."""
        mixin = _make_mixin()

        response = mixin.update_feedback_status(
            {"feedback_id": 5, "feedback_status": "rejected"}
        )

        assert response.success is True

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = UpdateFeedbackStatusRequest(
            feedback_id=10, feedback_status=FeedbackStatus.APPROVED
        )
        response = mixin.update_feedback_status(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# delete_feedbacks_by_ids_bulk - dict input (lines 93-96)
# ---------------------------------------------------------------------------


class TestDeleteFeedbacksByIdsBulk:
    def test_deletes_by_ids(self):
        """Deletes feedbacks by IDs and returns count."""
        mixin = _make_mixin()

        request = DeleteFeedbacksByIdsRequest(feedback_ids=[1, 2, 3])
        response = mixin.delete_feedbacks_by_ids_bulk(request)

        assert response.success is True
        assert response.deleted_count == 3
        _get_storage(mixin).delete_feedbacks_by_ids.assert_called_once_with([1, 2, 3])

    def test_dict_input(self):
        """Accepts dict input and auto-converts (lines 93-94)."""
        mixin = _make_mixin()

        response = mixin.delete_feedbacks_by_ids_bulk({"feedback_ids": [10, 20]})

        assert response.success is True
        assert response.deleted_count == 2
        _get_storage(mixin).delete_feedbacks_by_ids.assert_called_once_with([10, 20])

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteFeedbacksByIdsRequest(feedback_ids=[1])
        response = mixin.delete_feedbacks_by_ids_bulk(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# add_feedback - dict input (line 115)
# ---------------------------------------------------------------------------


class TestAddFeedbackDict:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 115)."""
        mixin = _make_mixin()
        fb = _sample_feedback()

        response = mixin.add_feedback({"feedbacks": [fb.model_dump()]})

        assert response.success is True
        assert response.added_count == 1


# ---------------------------------------------------------------------------
# get_feedbacks - error path (lines 166-167)
# ---------------------------------------------------------------------------


class TestGetFeedbacksError:
    def test_storage_exception(self):
        """Returns failure on storage exception (lines 166-167)."""
        mixin = _make_mixin()
        _get_storage(mixin).get_feedbacks.side_effect = RuntimeError("db error")

        request = GetFeedbacksRequest(limit=10)
        response = mixin.get_feedbacks(request)

        assert response.success is False
        assert "db error" in (response.msg or "")

    def test_with_feedback_status_filter(self):
        """Passes feedback_status_filter when provided."""
        mixin = _make_mixin()
        _get_storage(mixin).get_feedbacks.return_value = []

        request = GetFeedbacksRequest(
            limit=10,
            feedback_status_filter=FeedbackStatus.APPROVED,
        )
        response = mixin.get_feedbacks(request)

        assert response.success is True
        _get_storage(mixin).get_feedbacks.assert_called_once_with(
            limit=10,
            feedback_name=None,
            status_filter=None,
            feedback_status_filter=[FeedbackStatus.APPROVED],
        )


# ---------------------------------------------------------------------------
# search_feedbacks - dict input, error path, query rewrite (lines 186, 193, 196-197)
# ---------------------------------------------------------------------------


class TestSearchFeedbacksDictAndError:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 186)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_feedbacks.return_value = []

        response = mixin.search_feedbacks({"query": "test"})

        assert response.success is True

    def test_storage_exception(self):
        """Returns failure on storage exception (lines 196-197)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_feedbacks.side_effect = RuntimeError("search error")

        request = SearchFeedbackRequest(query="test")
        response = mixin.search_feedbacks(request)

        assert response.success is False
        assert "search error" in (response.msg or "")

    def test_query_rewrite_applied(self):
        """Query rewrite modifies the request when enabled (line 193)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_feedbacks.return_value = []

        # Mock the _rewrite_query to return a rewritten query
        mixin._rewrite_query = MagicMock(return_value="rewritten query")

        request = SearchFeedbackRequest(query="original", query_rewrite=True)
        response = mixin.search_feedbacks(request)

        assert response.success is True
        # Verify the rewritten query was passed to storage
        call_arg = _get_storage(mixin).search_feedbacks.call_args[0][0]
        assert call_arg.query == "rewritten query"


# ---------------------------------------------------------------------------
# delete_feedback - dict edge case
# ---------------------------------------------------------------------------


class TestDeleteFeedbackDict:
    def test_dict_input_via_require_storage(self):
        """dict input through _require_storage decorator with error handling."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_feedback.side_effect = RuntimeError("not found")

        response = mixin.delete_feedback({"feedback_id": 999})

        # _require_storage catches exception and returns failure
        assert response.success is False
        assert "not found" in (response.message or "")


# ---------------------------------------------------------------------------
# update_feedback_status - error path via _require_storage
# ---------------------------------------------------------------------------


class TestUpdateFeedbackStatusError:
    def test_storage_exception(self):
        """_require_storage catches storage exception and returns failure."""
        mixin = _make_mixin()
        _get_storage(mixin).update_feedback_status.side_effect = RuntimeError(
            "update error"
        )

        request = UpdateFeedbackStatusRequest(
            feedback_id=10, feedback_status=FeedbackStatus.APPROVED
        )
        response = mixin.update_feedback_status(request)

        assert response.success is False
        assert "update error" in (response.msg or "")
