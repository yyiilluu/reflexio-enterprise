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
