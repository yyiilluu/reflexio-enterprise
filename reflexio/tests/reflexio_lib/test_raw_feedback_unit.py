"""Unit tests for RawFeedbackMixin.

Tests get_raw_feedbacks, add_raw_feedback, search_raw_feedbacks,
delete_raw_feedback, upgrade_all_raw_feedbacks, and downgrade_all_raw_feedbacks
with mocked storage and services.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.retriever_schema import (
    GetRawFeedbacksRequest,
    SearchRawFeedbackRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    AddRawFeedbackRequest,
    DeleteRawFeedbackRequest,
    DeleteRawFeedbacksByIdsRequest,
    DowngradeRawFeedbacksResponse,
    RawFeedback,
    UpgradeRawFeedbacksResponse,
)

from reflexio.reflexio_lib._raw_feedback import RawFeedbackMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin(*, storage_configured: bool = True) -> RawFeedbackMixin:
    """Create a RawFeedbackMixin instance with mocked internals."""
    mixin = object.__new__(RawFeedbackMixin)
    mock_storage = MagicMock()

    mock_request_context = MagicMock()
    mock_request_context.org_id = "test_org"
    mock_request_context.storage = mock_storage if storage_configured else None
    mock_request_context.is_storage_configured.return_value = storage_configured

    mixin.request_context = mock_request_context
    mixin.llm_client = MagicMock()
    return mixin


def _get_storage(mixin: RawFeedbackMixin) -> MagicMock:
    return mixin.request_context.storage


def _sample_raw_feedback(**overrides) -> RawFeedback:
    defaults = {
        "agent_version": "v1",
        "request_id": "req-1",
        "feedback_name": "test_fb",
        "feedback_content": "test content",
    }
    defaults.update(overrides)
    return RawFeedback(**defaults)


# ---------------------------------------------------------------------------
# get_raw_feedbacks
# ---------------------------------------------------------------------------


class TestGetRawFeedbacks:
    def test_returns_list(self):
        """Successful retrieval returns raw feedbacks from storage."""
        mixin = _make_mixin()
        sample = _sample_raw_feedback()
        _get_storage(mixin).get_raw_feedbacks.return_value = [sample]

        request = GetRawFeedbacksRequest(limit=10)
        response = mixin.get_raw_feedbacks(request)

        assert response.success is True
        assert len(response.raw_feedbacks) == 1

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = GetRawFeedbacksRequest()
        response = mixin.get_raw_feedbacks(request)

        assert response.success is True
        assert response.raw_feedbacks == []
        assert response.msg is not None


# ---------------------------------------------------------------------------
# add_raw_feedback
# ---------------------------------------------------------------------------


class TestAddRawFeedback:
    def test_with_indexed_content(self):
        """Preserve user-provided indexed_content."""
        mixin = _make_mixin()
        rf = _sample_raw_feedback(indexed_content="custom index")
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is True
        assert response.added_count == 1
        saved = _get_storage(mixin).save_raw_feedbacks.call_args[0][0]
        assert saved[0].indexed_content == "custom index"

    def test_fallback_chain_when_condition(self):
        """Fallback to when_condition when indexed_content is absent."""
        mixin = _make_mixin()
        rf = _sample_raw_feedback(
            indexed_content=None,
            when_condition="when user asks",
            feedback_content="",
        )
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is True
        saved = _get_storage(mixin).save_raw_feedbacks.call_args[0][0]
        assert saved[0].indexed_content == "when user asks"

    def test_fallback_chain_feedback_content(self):
        """Fallback to feedback_content when higher-priority fields are absent."""
        mixin = _make_mixin()
        rf = _sample_raw_feedback(
            indexed_content=None,
            when_condition=None,
            feedback_content="some content",
        )
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is True
        saved = _get_storage(mixin).save_raw_feedbacks.call_args[0][0]
        assert saved[0].indexed_content == "some content"

    def test_fallback_chain_do_action(self):
        """Fallback to do_action when content fields are absent."""
        mixin = _make_mixin()
        rf = _sample_raw_feedback(
            indexed_content=None,
            when_condition=None,
            feedback_content="",
            do_action="do this",
        )
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is True
        saved = _get_storage(mixin).save_raw_feedbacks.call_args[0][0]
        assert saved[0].indexed_content == "do this"

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)
        rf = _sample_raw_feedback()
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# search_raw_feedbacks
# ---------------------------------------------------------------------------


class TestSearchRawFeedbacks:
    def test_basic_query(self):
        """Delegates search to storage and returns results."""
        mixin = _make_mixin()
        sample = _sample_raw_feedback()
        _get_storage(mixin).search_raw_feedbacks.return_value = [sample]

        request = SearchRawFeedbackRequest(query="test")
        response = mixin.search_raw_feedbacks(request)

        assert response.success is True
        assert len(response.raw_feedbacks) == 1
        _get_storage(mixin).search_raw_feedbacks.assert_called_once()

    def test_with_filters(self):
        """Passes filter parameters through to storage."""
        mixin = _make_mixin()
        _get_storage(mixin).search_raw_feedbacks.return_value = []

        request = SearchRawFeedbackRequest(
            query="test",
            feedback_name="my_feedback",
            agent_version="v2",
        )
        response = mixin.search_raw_feedbacks(request)

        assert response.success is True
        # Verify the request was passed through (possibly with rewritten query)
        call_args = _get_storage(mixin).search_raw_feedbacks.call_args[0][0]
        assert call_args.feedback_name == "my_feedback"
        assert call_args.agent_version == "v2"

    def test_storage_not_configured(self):
        """Returns empty list when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = SearchRawFeedbackRequest(query="test")
        response = mixin.search_raw_feedbacks(request)

        assert response.success is True
        assert response.raw_feedbacks == []


# ---------------------------------------------------------------------------
# delete_raw_feedback
# ---------------------------------------------------------------------------


class TestDeleteRawFeedback:
    def test_by_id(self):
        """Deletes a raw feedback by ID."""
        mixin = _make_mixin()

        request = DeleteRawFeedbackRequest(raw_feedback_id=42)
        response = mixin.delete_raw_feedback(request)

        assert response.success is True
        _get_storage(mixin).delete_raw_feedback.assert_called_once_with(42)

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteRawFeedbackRequest(raw_feedback_id=42)
        response = mixin.delete_raw_feedback(request)

        assert response.success is False


# ---------------------------------------------------------------------------
# upgrade_all_raw_feedbacks / downgrade_all_raw_feedbacks
# ---------------------------------------------------------------------------


class TestUpgradeDowngradeRawFeedbacks:
    def test_upgrade_delegates_to_service(self):
        """Upgrade creates FeedbackGenerationService and delegates."""
        mixin = _make_mixin()

        mock_response = UpgradeRawFeedbacksResponse(
            success=True,
            raw_feedbacks_deleted=1,
            raw_feedbacks_archived=2,
            raw_feedbacks_promoted=3,
        )

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_upgrade.return_value = mock_response

            response = mixin.upgrade_all_raw_feedbacks()

        assert response.success is True
        assert response.raw_feedbacks_promoted == 3
        mock_svc_cls.return_value.run_upgrade.assert_called_once()

    def test_downgrade_delegates_to_service(self):
        """Downgrade creates FeedbackGenerationService and delegates."""
        mixin = _make_mixin()

        mock_response = DowngradeRawFeedbacksResponse(
            success=True,
            raw_feedbacks_demoted=2,
            raw_feedbacks_restored=3,
        )

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_downgrade.return_value = mock_response

            response = mixin.downgrade_all_raw_feedbacks()

        assert response.success is True
        assert response.raw_feedbacks_restored == 3
        mock_svc_cls.return_value.run_downgrade.assert_called_once()

    def test_upgrade_storage_not_configured(self):
        """Upgrade fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.upgrade_all_raw_feedbacks()

        assert response.success is False

    def test_downgrade_storage_not_configured(self):
        """Downgrade fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        response = mixin.downgrade_all_raw_feedbacks()

        assert response.success is False

    def test_upgrade_with_dict_input(self):
        """Upgrade accepts dict input and converts to request."""
        mixin = _make_mixin()

        mock_response = UpgradeRawFeedbacksResponse(success=True)

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_upgrade.return_value = mock_response

            response = mixin.upgrade_all_raw_feedbacks({"feedback_name": "my_feedback"})

        assert response.success is True

    def test_downgrade_with_dict_input(self):
        """Downgrade accepts dict input and converts to request."""
        mixin = _make_mixin()

        mock_response = DowngradeRawFeedbacksResponse(success=True)

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_downgrade.return_value = mock_response

            response = mixin.downgrade_all_raw_feedbacks(
                {"feedback_name": "my_feedback"}
            )

        assert response.success is True

    def test_upgrade_with_none_input(self):
        """Upgrade with None converts to default request (line 217->221)."""
        mixin = _make_mixin()

        mock_response = UpgradeRawFeedbacksResponse(success=True)

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_upgrade.return_value = mock_response

            response = mixin.upgrade_all_raw_feedbacks(None)

        assert response.success is True
        mock_svc_cls.return_value.run_upgrade.assert_called_once()

    def test_downgrade_with_none_input(self):
        """Downgrade with None converts to default request (line 255->259)."""
        mixin = _make_mixin()

        mock_response = DowngradeRawFeedbacksResponse(success=True)

        with patch(
            "reflexio.reflexio_lib._raw_feedback.FeedbackGenerationService"
        ) as mock_svc_cls:
            mock_svc_cls.return_value.run_downgrade.return_value = mock_response

            response = mixin.downgrade_all_raw_feedbacks(None)

        assert response.success is True
        mock_svc_cls.return_value.run_downgrade.assert_called_once()


# ---------------------------------------------------------------------------
# get_raw_feedbacks - dict input and error paths (lines 51, 60-61)
# ---------------------------------------------------------------------------


class TestGetRawFeedbacksDictAndError:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 51)."""
        mixin = _make_mixin()
        _get_storage(mixin).get_raw_feedbacks.return_value = []

        response = mixin.get_raw_feedbacks({"limit": 5, "feedback_name": "my_fb"})

        assert response.success is True
        _get_storage(mixin).get_raw_feedbacks.assert_called_once()

    def test_storage_exception(self):
        """Returns failure on storage exception (lines 60-61)."""
        mixin = _make_mixin()
        _get_storage(mixin).get_raw_feedbacks.side_effect = RuntimeError("db error")

        request = GetRawFeedbacksRequest(limit=10)
        response = mixin.get_raw_feedbacks(request)

        assert response.success is False
        assert "db error" in (response.msg or "")


# ---------------------------------------------------------------------------
# add_raw_feedback - dict input and error path (lines 80, 118-119)
# ---------------------------------------------------------------------------


class TestAddRawFeedbackDictAndError:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 80)."""
        mixin = _make_mixin()
        rf = _sample_raw_feedback()

        response = mixin.add_raw_feedback({"raw_feedbacks": [rf.model_dump()]})

        assert response.success is True

    def test_storage_exception(self):
        """Returns failure on storage exception (lines 118-119)."""
        mixin = _make_mixin()
        _get_storage(mixin).save_raw_feedbacks.side_effect = RuntimeError("save error")

        rf = _sample_raw_feedback()
        request = AddRawFeedbackRequest(raw_feedbacks=[rf])

        response = mixin.add_raw_feedback(request)

        assert response.success is False
        assert "save error" in (response.message or "")


# ---------------------------------------------------------------------------
# search_raw_feedbacks - dict input and error path (lines 138, 148-149)
# ---------------------------------------------------------------------------


class TestSearchRawFeedbacksDictAndError:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 138)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_raw_feedbacks.return_value = []

        response = mixin.search_raw_feedbacks({"query": "test"})

        assert response.success is True

    def test_storage_exception(self):
        """Returns failure on storage exception (lines 148-149)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_raw_feedbacks.side_effect = RuntimeError(
            "search error"
        )

        request = SearchRawFeedbackRequest(query="test")
        response = mixin.search_raw_feedbacks(request)

        assert response.success is False
        assert "search error" in (response.msg or "")

    def test_query_rewrite_applied(self):
        """Query rewrite modifies the request when enabled (line 145)."""
        mixin = _make_mixin()
        _get_storage(mixin).search_raw_feedbacks.return_value = []

        # Mock the _rewrite_query to return a rewritten query
        mixin._rewrite_query = MagicMock(return_value="rewritten query")

        request = SearchRawFeedbackRequest(query="original", query_rewrite=True)
        response = mixin.search_raw_feedbacks(request)

        assert response.success is True
        # Verify the rewritten query was passed to storage
        call_arg = _get_storage(mixin).search_raw_feedbacks.call_args[0][0]
        assert call_arg.query == "rewritten query"


# ---------------------------------------------------------------------------
# delete_raw_feedback - dict input (line 167)
# ---------------------------------------------------------------------------


class TestDeleteRawFeedbackDict:
    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 167)."""
        mixin = _make_mixin()

        response = mixin.delete_raw_feedback({"raw_feedback_id": 99})

        assert response.success is True
        _get_storage(mixin).delete_raw_feedback.assert_called_once_with(99)


# ---------------------------------------------------------------------------
# delete_raw_feedbacks_by_ids_bulk - dict input and storage_not_configured (lines 184-189)
# ---------------------------------------------------------------------------


class TestDeleteRawFeedbacksByIdsBulk:
    def test_deletes_by_ids(self):
        """Deletes raw feedbacks by IDs and returns count."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_raw_feedbacks_by_ids.return_value = 3

        request = DeleteRawFeedbacksByIdsRequest(raw_feedback_ids=[1, 2, 3])
        response = mixin.delete_raw_feedbacks_by_ids_bulk(request)

        assert response.success is True
        assert response.deleted_count == 3

    def test_dict_input(self):
        """Accepts dict input and auto-converts (line 184)."""
        mixin = _make_mixin()
        _get_storage(mixin).delete_raw_feedbacks_by_ids.return_value = 2

        response = mixin.delete_raw_feedbacks_by_ids_bulk(
            {"raw_feedback_ids": [10, 20]}
        )

        assert response.success is True
        assert response.deleted_count == 2

    def test_storage_not_configured(self):
        """Fails when storage is not configured."""
        mixin = _make_mixin(storage_configured=False)

        request = DeleteRawFeedbacksByIdsRequest(raw_feedback_ids=[1])
        response = mixin.delete_raw_feedbacks_by_ids_bulk(request)

        assert response.success is False
