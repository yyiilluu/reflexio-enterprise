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
    FeedbackAggregationChangeLog,
    FeedbackStatus,
)

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG


def _make_feedback(**overrides: object) -> Feedback:
    defaults = {"agent_version": "v1", "feedback_content": "test content"}
    defaults.update(overrides)
    return Feedback(**defaults)


# ---------------------------------------------------------------------------
# get_feedback_aggregation_change_logs
# ---------------------------------------------------------------------------


def test_get_feedback_aggregation_change_logs_storage_not_configured(
    reflexio_no_storage,
):
    resp = reflexio_no_storage.get_feedback_aggregation_change_logs("fb", "v1")
    assert resp.success is True
    assert resp.change_logs == []


def test_get_feedback_aggregation_change_logs_success(reflexio_mock):
    log = FeedbackAggregationChangeLog(
        feedback_name="fb", agent_version="v1", run_mode="incremental"
    )
    reflexio_mock.request_context.storage.get_feedback_aggregation_change_logs.return_value = [
        log
    ]

    resp = reflexio_mock.get_feedback_aggregation_change_logs("fb", "v1")

    assert resp.success is True
    assert len(resp.change_logs) == 1
    assert resp.change_logs[0].feedback_name == "fb"
    reflexio_mock.request_context.storage.get_feedback_aggregation_change_logs.assert_called_once_with(
        feedback_name="fb", agent_version="v1"
    )


# ---------------------------------------------------------------------------
# delete_feedback
# ---------------------------------------------------------------------------


def test_delete_feedback_storage_not_configured(reflexio_no_storage):
    req = DeleteFeedbackRequest(feedback_id=1)
    resp = reflexio_no_storage.delete_feedback(req)
    assert resp.success is False
    assert STORAGE_NOT_CONFIGURED_MSG in resp.message


def test_delete_feedback_success(reflexio_mock):
    req = DeleteFeedbackRequest(feedback_id=42)
    resp = reflexio_mock.delete_feedback(req)
    assert resp.success is True
    reflexio_mock.request_context.storage.delete_feedback.assert_called_once_with(42)


def test_delete_feedback_dict_input(reflexio_mock):
    resp = reflexio_mock.delete_feedback({"feedback_id": 7})
    assert resp.success is True
    reflexio_mock.request_context.storage.delete_feedback.assert_called_once_with(7)


def test_delete_feedback_exception(reflexio_mock):
    reflexio_mock.request_context.storage.delete_feedback.side_effect = RuntimeError(
        "db error"
    )
    req = DeleteFeedbackRequest(feedback_id=1)
    resp = reflexio_mock.delete_feedback(req)
    assert resp.success is False
    assert "db error" in resp.message


# ---------------------------------------------------------------------------
# delete_all_feedbacks_bulk
# ---------------------------------------------------------------------------


def test_delete_all_feedbacks_bulk_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.delete_all_feedbacks_bulk()
    assert resp.success is False
    assert STORAGE_NOT_CONFIGURED_MSG in resp.message


def test_delete_all_feedbacks_bulk_success(reflexio_mock):
    resp = reflexio_mock.delete_all_feedbacks_bulk()
    assert resp.success is True
    reflexio_mock.request_context.storage.delete_all_feedbacks.assert_called_once()
    reflexio_mock.request_context.storage.delete_all_raw_feedbacks.assert_called_once()


# ---------------------------------------------------------------------------
# delete_feedbacks_by_ids_bulk
# ---------------------------------------------------------------------------


def test_delete_feedbacks_by_ids_bulk_storage_not_configured(reflexio_no_storage):
    req = DeleteFeedbacksByIdsRequest(feedback_ids=[1])
    resp = reflexio_no_storage.delete_feedbacks_by_ids_bulk(req)
    assert resp.success is False
    assert STORAGE_NOT_CONFIGURED_MSG in resp.message


def test_delete_feedbacks_by_ids_bulk_success(reflexio_mock):
    req = DeleteFeedbacksByIdsRequest(feedback_ids=[10, 20, 30])
    resp = reflexio_mock.delete_feedbacks_by_ids_bulk(req)
    assert resp.success is True
    assert resp.deleted_count == 3
    reflexio_mock.request_context.storage.delete_feedbacks_by_ids.assert_called_once_with(
        [10, 20, 30]
    )


# ---------------------------------------------------------------------------
# add_feedback
# ---------------------------------------------------------------------------


def test_add_feedback_storage_not_configured(reflexio_no_storage):
    req = AddFeedbackRequest(feedbacks=[_make_feedback()])
    resp = reflexio_no_storage.add_feedback(req)
    assert resp.success is False
    assert STORAGE_NOT_CONFIGURED_MSG in resp.message


def test_add_feedback_normalization(reflexio_mock):
    fb = _make_feedback(
        feedback_name="name",
        feedback_content="content",
        feedback_status=FeedbackStatus.APPROVED,
    )
    req = AddFeedbackRequest(feedbacks=[fb])
    resp = reflexio_mock.add_feedback(req)

    assert resp.success is True
    assert resp.added_count == 1
    saved = reflexio_mock.request_context.storage.save_feedbacks.call_args[0][0]
    assert len(saved) == 1
    assert saved[0].feedback_metadata == ""
    assert saved[0].feedback_name == "name"


def test_add_feedback_exception(reflexio_mock):
    reflexio_mock.request_context.storage.save_feedbacks.side_effect = RuntimeError(
        "save failed"
    )
    req = AddFeedbackRequest(feedbacks=[_make_feedback()])
    resp = reflexio_mock.add_feedback(req)
    assert resp.success is False
    assert "save failed" in resp.message


# ---------------------------------------------------------------------------
# get_feedbacks
# ---------------------------------------------------------------------------


def test_get_feedbacks_storage_not_configured(reflexio_no_storage):
    req = GetFeedbacksRequest()
    resp = reflexio_no_storage.get_feedbacks(req)
    assert resp.success is True
    assert resp.feedbacks == []
    assert STORAGE_NOT_CONFIGURED_MSG in resp.msg


def test_get_feedbacks_success(reflexio_mock):
    fb = _make_feedback(feedback_name="fb1")
    reflexio_mock.request_context.storage.get_feedbacks.return_value = [fb]
    req = GetFeedbacksRequest(limit=50, feedback_name="fb1")
    resp = reflexio_mock.get_feedbacks(req)

    assert resp.success is True
    assert len(resp.feedbacks) == 1
    assert resp.feedbacks[0].feedback_name == "fb1"
    reflexio_mock.request_context.storage.get_feedbacks.assert_called_once_with(
        limit=50,
        feedback_name="fb1",
        status_filter=None,
        feedback_status_filter=None,
    )


def test_get_feedbacks_with_feedback_status_filter(reflexio_mock):
    reflexio_mock.request_context.storage.get_feedbacks.return_value = []
    req = GetFeedbacksRequest(feedback_status_filter="approved")
    reflexio_mock.get_feedbacks(req)

    reflexio_mock.request_context.storage.get_feedbacks.assert_called_once_with(
        limit=100,
        feedback_name=None,
        status_filter=None,
        feedback_status_filter=["approved"],
    )


def test_get_feedbacks_dict_input(reflexio_mock):
    reflexio_mock.request_context.storage.get_feedbacks.return_value = []
    resp = reflexio_mock.get_feedbacks({"limit": 10})
    assert resp.success is True
    reflexio_mock.request_context.storage.get_feedbacks.assert_called_once()


def test_get_feedbacks_exception(reflexio_mock):
    reflexio_mock.request_context.storage.get_feedbacks.side_effect = RuntimeError(
        "query failed"
    )
    req = GetFeedbacksRequest()
    resp = reflexio_mock.get_feedbacks(req)
    assert resp.success is False
    assert "query failed" in resp.msg


# ---------------------------------------------------------------------------
# search_feedbacks
# ---------------------------------------------------------------------------


def test_search_feedbacks_storage_not_configured(reflexio_no_storage):
    req = SearchFeedbackRequest()
    resp = reflexio_no_storage.search_feedbacks(req)
    assert resp.success is True
    assert resp.feedbacks == []
    assert STORAGE_NOT_CONFIGURED_MSG in resp.msg


def test_search_feedbacks_with_query_rewrite(reflexio_mock):
    reflexio_mock._rewrite_query = MagicMock(return_value="rewritten")
    reflexio_mock.request_context.storage.search_feedbacks.return_value = []

    req = SearchFeedbackRequest(query="original", query_rewrite=True)
    resp = reflexio_mock.search_feedbacks(req)

    assert resp.success is True
    reflexio_mock._rewrite_query.assert_called_once_with("original", enabled=True)
    called_req = reflexio_mock.request_context.storage.search_feedbacks.call_args[0][0]
    assert called_req.query == "rewritten"


# ---------------------------------------------------------------------------
# update_feedback_status
# ---------------------------------------------------------------------------


def test_update_feedback_status_storage_not_configured(reflexio_no_storage):
    req = UpdateFeedbackStatusRequest(feedback_id=1, feedback_status="approved")
    resp = reflexio_no_storage.update_feedback_status(req)
    assert resp.success is False
    assert STORAGE_NOT_CONFIGURED_MSG in resp.msg


def test_update_feedback_status_success(reflexio_mock):
    req = UpdateFeedbackStatusRequest(feedback_id=5, feedback_status="approved")
    resp = reflexio_mock.update_feedback_status(req)
    assert resp.success is True
    reflexio_mock.request_context.storage.update_feedback_status.assert_called_once_with(
        feedback_id=5, feedback_status="approved"
    )
