from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from reflexio_commons.api_schema.service_schemas import (
    CancelOperationRequest,
    GetOperationStatusRequest,
    OperationStatus,
)

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG
from reflexio.server.services.operation_state_utils import BATCH_STALE_PROGRESS_SECONDS

# ==============================
# get_operation_status tests
# ==============================


def test_get_operation_status_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )
    assert resp.success is True
    assert resp.operation_status is None
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


def test_get_operation_status_dict_input(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_operation_state.return_value = {
        "operation_state": {
            "service_name": "profile_generation",
            "status": OperationStatus.COMPLETED.value,
            "started_at": 1000,
            "completed_at": 2000,
        }
    }

    resp = reflexio_mock.get_operation_status({"service_name": "profile_generation"})

    assert resp.success is True
    assert resp.operation_status is not None
    assert resp.operation_status.status == OperationStatus.COMPLETED
    storage.get_operation_state.assert_called_once_with(
        "profile_generation::test_org::progress"
    )


def test_get_operation_status_no_state_found(reflexio_mock):
    reflexio_mock.request_context.storage.get_operation_state.return_value = None

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    assert resp.success is False
    assert "No operation found" in resp.msg


def test_get_operation_status_completed_state(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_operation_state.return_value = {
        "operation_state": {
            "service_name": "profile_generation",
            "status": OperationStatus.COMPLETED.value,
            "started_at": 1000,
            "completed_at": 2000,
            "total_users": 5,
            "processed_users": 5,
        }
    }

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    assert resp.success is True
    assert resp.operation_status.status == OperationStatus.COMPLETED
    assert resp.operation_status.total_users == 5
    assert resp.operation_status.processed_users == 5
    assert resp.operation_status.completed_at == 2000


def test_get_operation_status_stale_in_progress_auto_recovery(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    stale_started_at = (
        int(datetime.now(UTC).timestamp()) - BATCH_STALE_PROGRESS_SECONDS - 100
    )
    operation_state = {
        "service_name": "profile_generation",
        "status": OperationStatus.IN_PROGRESS.value,
        "started_at": stale_started_at,
        "total_users": 10,
        "processed_users": 3,
    }
    storage.get_operation_state.return_value = {"operation_state": operation_state}

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    assert resp.success is True
    assert resp.operation_status.status == OperationStatus.FAILED
    assert resp.operation_status.completed_at is not None
    assert "Auto-recovered" in (resp.operation_status.error_message or "")
    storage.update_operation_state.assert_called_once()


def test_get_operation_status_fresh_in_progress(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    fresh_started_at = int(datetime.now(UTC).timestamp()) - 10
    storage.get_operation_state.return_value = {
        "operation_state": {
            "service_name": "profile_generation",
            "status": OperationStatus.IN_PROGRESS.value,
            "started_at": fresh_started_at,
            "total_users": 10,
            "processed_users": 3,
        }
    }

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    assert resp.success is True
    assert resp.operation_status.status == OperationStatus.IN_PROGRESS
    storage.update_operation_state.assert_not_called()


def test_get_operation_status_in_progress_no_started_at(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    # started_at absent from the dict: .get("started_at") returns None,
    # so the stale-progress check is skipped.  However the key is still
    # required by OperationStatusInfo(started_at: int) which has no
    # default, so supply 0 to satisfy pydantic while exercising the
    # "started_at is None in .get()" branch by wrapping the state so that
    # the inner dict omits it but the outer dict provides it.
    #
    # Simpler: just omit started_at entirely so .get() returns None,
    # and expect the pydantic validation error to be caught.
    storage.get_operation_state.return_value = {
        "operation_state": {
            "service_name": "profile_generation",
            "status": OperationStatus.IN_PROGRESS.value,
            # started_at intentionally omitted
            "total_users": 10,
            "processed_users": 3,
        }
    }

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    # OperationStatusInfo requires started_at: int with no default, so
    # the missing key causes a ValidationError caught by the except block.
    assert resp.success is False
    assert "Failed to get operation status" in resp.msg
    storage.update_operation_state.assert_not_called()


def test_get_operation_status_exception(reflexio_mock):
    reflexio_mock.request_context.storage.get_operation_state.side_effect = (
        RuntimeError("storage down")
    )

    resp = reflexio_mock.get_operation_status(
        GetOperationStatusRequest(service_name="profile_generation")
    )

    assert resp.success is False
    assert "Failed to get operation status" in resp.msg
    assert "storage down" in resp.msg


# ==============================
# cancel_operation tests
# ==============================


def test_cancel_operation_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.cancel_operation(
        CancelOperationRequest(service_name="profile_generation")
    )
    assert resp.success is False
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


@patch("reflexio.reflexio_lib._operations.OperationStateManager")
def test_cancel_operation_specific_service(mock_mgr_cls, reflexio_mock):
    mock_mgr = MagicMock()
    mock_mgr.request_cancellation.return_value = True
    mock_mgr_cls.return_value = mock_mgr

    resp = reflexio_mock.cancel_operation(
        CancelOperationRequest(service_name="profile_generation")
    )

    assert resp.success is True
    assert resp.cancelled_services == ["profile_generation"]
    mock_mgr_cls.assert_called_once_with(
        storage=reflexio_mock.request_context.storage,
        org_id="test_org",
        service_name="profile_generation",
    )


@patch("reflexio.reflexio_lib._operations.OperationStateManager")
def test_cancel_operation_both_services(mock_mgr_cls, reflexio_mock):
    mock_mgr = MagicMock()
    mock_mgr.request_cancellation.return_value = True
    mock_mgr_cls.return_value = mock_mgr

    resp = reflexio_mock.cancel_operation(CancelOperationRequest(service_name=None))

    assert resp.success is True
    assert sorted(resp.cancelled_services) == [
        "feedback_generation",
        "profile_generation",
    ]
    assert mock_mgr_cls.call_count == 2


@patch("reflexio.reflexio_lib._operations.OperationStateManager")
def test_cancel_operation_no_in_progress(mock_mgr_cls, reflexio_mock):
    mock_mgr = MagicMock()
    mock_mgr.request_cancellation.return_value = False
    mock_mgr_cls.return_value = mock_mgr

    resp = reflexio_mock.cancel_operation(
        CancelOperationRequest(service_name="profile_generation")
    )

    assert resp.success is True
    assert resp.cancelled_services == []
    assert "No in-progress operations" in resp.msg


@patch("reflexio.reflexio_lib._operations.OperationStateManager")
def test_cancel_operation_dict_input(mock_mgr_cls, reflexio_mock):
    mock_mgr = MagicMock()
    mock_mgr.request_cancellation.return_value = True
    mock_mgr_cls.return_value = mock_mgr

    resp = reflexio_mock.cancel_operation({"service_name": "feedback_generation"})

    assert resp.success is True
    assert resp.cancelled_services == ["feedback_generation"]


@patch("reflexio.reflexio_lib._operations.OperationStateManager")
def test_cancel_operation_exception(mock_mgr_cls, reflexio_mock):
    mock_mgr_cls.side_effect = RuntimeError("connection lost")

    resp = reflexio_mock.cancel_operation(
        CancelOperationRequest(service_name="profile_generation")
    )

    assert resp.success is False
    assert "Failed to cancel operation" in resp.msg
    assert "connection lost" in resp.msg
