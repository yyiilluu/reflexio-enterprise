from __future__ import annotations

from unittest.mock import MagicMock

from reflexio_commons.api_schema.retriever_schema import (
    GetRawFeedbacksRequest,
    SearchRawFeedbackRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    AddRawFeedbackRequest,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbacksByIdsRequest,
    RawFeedback,
)

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_feedback(**overrides) -> RawFeedback:
    defaults = {
        "agent_version": "v1",
        "request_id": "req-1",
        "feedback_content": "some feedback",
    }
    defaults.update(overrides)
    return RawFeedback(**defaults)


# ---------------------------------------------------------------------------
# get_raw_feedbacks
# ---------------------------------------------------------------------------


def test_get_raw_feedbacks_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.get_raw_feedbacks(GetRawFeedbacksRequest())
    assert resp.success is True
    assert resp.raw_feedbacks == []
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


def test_get_raw_feedbacks_dict_input(reflexio_mock):
    reflexio_mock.request_context.storage.get_raw_feedbacks.return_value = []
    resp = reflexio_mock.get_raw_feedbacks({"limit": 50, "feedback_name": "test"})
    assert resp.success is True
    reflexio_mock.request_context.storage.get_raw_feedbacks.assert_called_once_with(
        limit=50,
        feedback_name="test",
        status_filter=None,
    )


def test_get_raw_feedbacks_success(reflexio_mock):
    fake_feedbacks = [_make_raw_feedback(), _make_raw_feedback(request_id="req-2")]
    reflexio_mock.request_context.storage.get_raw_feedbacks.return_value = (
        fake_feedbacks
    )
    resp = reflexio_mock.get_raw_feedbacks(GetRawFeedbacksRequest(limit=10))
    assert resp.success is True
    assert resp.raw_feedbacks == fake_feedbacks


def test_get_raw_feedbacks_exception(reflexio_mock):
    reflexio_mock.request_context.storage.get_raw_feedbacks.side_effect = RuntimeError(
        "db down"
    )
    resp = reflexio_mock.get_raw_feedbacks(GetRawFeedbacksRequest())
    assert resp.success is False
    assert "db down" in resp.msg


# ---------------------------------------------------------------------------
# add_raw_feedback
# ---------------------------------------------------------------------------


def test_add_raw_feedback_storage_not_configured(reflexio_no_storage):
    rf = _make_raw_feedback()
    resp = reflexio_no_storage.add_raw_feedback(
        AddRawFeedbackRequest(raw_feedbacks=[rf])
    )
    assert resp.success is False
    assert resp.message == STORAGE_NOT_CONFIGURED_MSG


def test_add_raw_feedback_dict_input(reflexio_mock):
    resp = reflexio_mock.add_raw_feedback(
        {
            "raw_feedbacks": [
                {
                    "agent_version": "v1",
                    "request_id": "r1",
                    "feedback_content": "content",
                },
            ],
        }
    )
    assert resp.success is True
    assert resp.added_count == 1
    reflexio_mock.request_context.storage.save_raw_feedbacks.assert_called_once()


def test_add_raw_feedback_indexed_content_fallback_chain(reflexio_mock):
    # Priority 1: explicit indexed_content
    rf1 = _make_raw_feedback(
        indexed_content="explicit", when_condition="cond", feedback_content="fb"
    )
    # Priority 2: when_condition (indexed_content not set)
    rf2 = _make_raw_feedback(
        indexed_content=None, when_condition="cond2", feedback_content="fb2"
    )
    # Priority 3: feedback_content (neither indexed_content nor when_condition)
    rf3 = _make_raw_feedback(
        indexed_content=None, when_condition=None, feedback_content="fb3"
    )
    # Priority 4: do_action + do_not_action joined
    rf4 = _make_raw_feedback(
        indexed_content=None,
        when_condition=None,
        feedback_content="",
        do_action="do this",
        do_not_action="not that",
    )

    req = AddRawFeedbackRequest(raw_feedbacks=[rf1, rf2, rf3, rf4])
    resp = reflexio_mock.add_raw_feedback(req)
    assert resp.success is True
    assert resp.added_count == 4

    saved = reflexio_mock.request_context.storage.save_raw_feedbacks.call_args[0][0]
    assert saved[0].indexed_content == "explicit"
    assert saved[1].indexed_content == "cond2"
    assert saved[2].indexed_content == "fb3"
    assert saved[3].indexed_content == "do this not that"


def test_add_raw_feedback_success(reflexio_mock):
    rf = _make_raw_feedback(do_action="act", when_condition="when")
    req = AddRawFeedbackRequest(raw_feedbacks=[rf])
    resp = reflexio_mock.add_raw_feedback(req)

    assert resp.success is True
    assert resp.added_count == 1

    saved = reflexio_mock.request_context.storage.save_raw_feedbacks.call_args[0][0]
    assert len(saved) == 1
    assert saved[0].do_action == "act"
    assert saved[0].when_condition == "when"


def test_add_raw_feedback_exception(reflexio_mock):
    reflexio_mock.request_context.storage.save_raw_feedbacks.side_effect = RuntimeError(
        "write fail"
    )
    rf = _make_raw_feedback()
    resp = reflexio_mock.add_raw_feedback(AddRawFeedbackRequest(raw_feedbacks=[rf]))
    assert resp.success is False
    assert "write fail" in resp.message


# ---------------------------------------------------------------------------
# search_raw_feedbacks
# ---------------------------------------------------------------------------


def test_search_raw_feedbacks_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.search_raw_feedbacks(
        SearchRawFeedbackRequest(query="test")
    )
    assert resp.success is True
    assert resp.raw_feedbacks == []
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


def test_search_raw_feedbacks_dict_input(reflexio_mock):
    reflexio_mock.request_context.storage.search_raw_feedbacks.return_value = []
    resp = reflexio_mock.search_raw_feedbacks({"query": "hello"})
    assert resp.success is True
    reflexio_mock.request_context.storage.search_raw_feedbacks.assert_called_once()


def test_search_raw_feedbacks_with_query_rewrite(reflexio_mock):
    reflexio_mock._rewrite_query = MagicMock(return_value="rewritten query")
    fake_results = [_make_raw_feedback()]
    reflexio_mock.request_context.storage.search_raw_feedbacks.return_value = (
        fake_results
    )

    req = SearchRawFeedbackRequest(query="original", query_rewrite=True)
    resp = reflexio_mock.search_raw_feedbacks(req)

    assert resp.success is True
    assert resp.raw_feedbacks == fake_results
    reflexio_mock._rewrite_query.assert_called_once_with("original", enabled=True)
    # Verify the storage was called with the rewritten query
    passed_req = reflexio_mock.request_context.storage.search_raw_feedbacks.call_args[
        0
    ][0]
    assert passed_req.query == "rewritten query"


def test_search_raw_feedbacks_exception(reflexio_mock):
    reflexio_mock.request_context.storage.search_raw_feedbacks.side_effect = (
        RuntimeError("search fail")
    )
    resp = reflexio_mock.search_raw_feedbacks(SearchRawFeedbackRequest(query="boom"))
    assert resp.success is False
    assert "search fail" in resp.msg


# ---------------------------------------------------------------------------
# delete_raw_feedback (_require_storage decorator)
# ---------------------------------------------------------------------------


def test_delete_raw_feedback_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.delete_raw_feedback(
        DeleteRawFeedbackRequest(raw_feedback_id=1)
    )
    assert resp.success is False
    assert resp.message == STORAGE_NOT_CONFIGURED_MSG


def test_delete_raw_feedback_success(reflexio_mock):
    resp = reflexio_mock.delete_raw_feedback(
        DeleteRawFeedbackRequest(raw_feedback_id=42)
    )
    assert resp.success is True
    reflexio_mock.request_context.storage.delete_raw_feedback.assert_called_once_with(
        42
    )


# ---------------------------------------------------------------------------
# delete_raw_feedbacks_by_ids_bulk (_require_storage decorator)
# ---------------------------------------------------------------------------


def test_delete_raw_feedbacks_by_ids_bulk_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.delete_raw_feedbacks_by_ids_bulk(
        DeleteRawFeedbacksByIdsRequest(raw_feedback_ids=[1, 2]),
    )
    assert resp.success is False
    assert resp.message == STORAGE_NOT_CONFIGURED_MSG


def test_delete_raw_feedbacks_by_ids_bulk_success(reflexio_mock):
    reflexio_mock.request_context.storage.delete_raw_feedbacks_by_ids.return_value = 3
    resp = reflexio_mock.delete_raw_feedbacks_by_ids_bulk(
        DeleteRawFeedbacksByIdsRequest(raw_feedback_ids=[10, 20, 30]),
    )
    assert resp.success is True
    assert resp.deleted_count == 3
    reflexio_mock.request_context.storage.delete_raw_feedbacks_by_ids.assert_called_once_with(
        [10, 20, 30],
    )


# ---------------------------------------------------------------------------
# upgrade / downgrade (storage-not-configured paths only)
# ---------------------------------------------------------------------------


def test_upgrade_all_raw_feedbacks_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.upgrade_all_raw_feedbacks()
    assert resp.success is False
    assert resp.message == STORAGE_NOT_CONFIGURED_MSG


def test_downgrade_all_raw_feedbacks_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.downgrade_all_raw_feedbacks()
    assert resp.success is False
    assert resp.message == STORAGE_NOT_CONFIGURED_MSG
