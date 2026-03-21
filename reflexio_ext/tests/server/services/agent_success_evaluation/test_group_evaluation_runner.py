"""Tests for group_evaluation_runner behavior."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from reflexio.server.services.agent_success_evaluation.group_evaluation_runner import (
    _build_state_key,
    run_group_evaluation,
)
from reflexio_commons.api_schema.service_schemas import Interaction, Request


def _make_request(request_id: str, user_id: str, session_id: str) -> Request:
    """Create a request object old enough to pass completion delay checks."""
    now = int(datetime.now(UTC).timestamp())
    return Request(
        request_id=request_id,
        user_id=user_id,
        session_id=session_id,
        created_at=now - 10000,
    )


def _make_interaction(request_id: str, user_id: str) -> Interaction:
    """Create an interaction object tied to a request."""
    now = int(datetime.now(UTC).timestamp())
    return Interaction(
        interaction_id=1,
        user_id=user_id,
        request_id=request_id,
        content="test content",
        role="user",
        created_at=now - 9999,
    )


def test_build_state_key_includes_user_id() -> None:
    """Ensure state keys are scoped to org + user + session_id."""
    key = _build_state_key("org_a", "user_a", "group_a")
    assert key == "agent_success_group_eval::org_a::user_a::group_a"


def test_run_group_evaluation_skips_mark_when_service_has_failures() -> None:
    """Do not mark evaluated=true when evaluation run reports failures."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"
    state_key = _build_state_key(org_id, user_id, session_id)

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [
        _make_request("req_1", user_id, session_id)
    ]
    storage.get_interactions_by_request_ids.return_value = [
        _make_interaction("req_1", user_id)
    ]

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    with patch(
        "reflexio.server.services.agent_success_evaluation.group_evaluation_runner.AgentSuccessEvaluationService"
    ) as service_cls:
        service = MagicMock()
        service.has_run_failures.return_value = True
        service._last_extractor_run_stats = {"failed": 1}
        service.last_run_save_failed = False
        service.last_run_saved_result_count = 0
        service_cls.return_value = service

        run_group_evaluation(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            agent_version="1.0.0",
            source="api",
            request_context=request_context,
            llm_client=llm_client,
        )

    storage.get_operation_state.assert_called_once_with(state_key)
    storage.upsert_operation_state.assert_not_called()


def test_run_group_evaluation_marks_state_when_service_succeeds() -> None:
    """Mark evaluated=true only when evaluation run succeeds."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"
    state_key = _build_state_key(org_id, user_id, session_id)

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [
        _make_request("req_1", user_id, session_id)
    ]
    storage.get_interactions_by_request_ids.return_value = [
        _make_interaction("req_1", user_id)
    ]

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    with patch(
        "reflexio.server.services.agent_success_evaluation.group_evaluation_runner.AgentSuccessEvaluationService"
    ) as service_cls:
        service = MagicMock()
        service.has_run_failures.return_value = False
        service.last_run_saved_result_count = 1
        service_cls.return_value = service

        run_group_evaluation(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            agent_version="1.0.0",
            source="api",
            request_context=request_context,
            llm_client=llm_client,
        )

    storage.get_operation_state.assert_called_once_with(state_key)
    storage.upsert_operation_state.assert_called_once()
    upsert_key, upsert_payload = storage.upsert_operation_state.call_args[0]
    assert upsert_key == state_key
    assert upsert_payload["evaluated"] is True


def test_run_group_evaluation_skips_mark_when_nothing_saved() -> None:
    """Do not mark evaluated=true when evaluation produced no persisted results."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"
    state_key = _build_state_key(org_id, user_id, session_id)

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [
        _make_request("req_1", user_id, session_id)
    ]
    storage.get_interactions_by_request_ids.return_value = [
        _make_interaction("req_1", user_id)
    ]

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    with patch(
        "reflexio.server.services.agent_success_evaluation.group_evaluation_runner.AgentSuccessEvaluationService"
    ) as service_cls:
        service = MagicMock()
        service.has_run_failures.return_value = False
        service.last_run_saved_result_count = 0
        service_cls.return_value = service

        run_group_evaluation(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            agent_version="1.0.0",
            source="api",
            request_context=request_context,
            llm_client=llm_client,
        )

    storage.get_operation_state.assert_called_once_with(state_key)
    storage.upsert_operation_state.assert_not_called()


def test_already_evaluated_session_returns_early() -> None:
    """Session with existing evaluated state should skip all processing."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"
    state_key = _build_state_key(org_id, user_id, session_id)

    storage = MagicMock()
    storage.get_operation_state.return_value = {
        "operation_state": {"evaluated": True, "evaluated_at": 1700000000},
    }

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    run_group_evaluation(
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        agent_version="1.0.0",
        source="api",
        request_context=request_context,
        llm_client=llm_client,
    )

    storage.get_operation_state.assert_called_once_with(state_key)
    # Should not proceed to fetch requests
    storage.get_requests_by_session.assert_not_called()
    storage.upsert_operation_state.assert_not_called()


def test_no_requests_found_returns_early() -> None:
    """When no requests exist for the session, should return early."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = []

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    run_group_evaluation(
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        agent_version="1.0.0",
        source="api",
        request_context=request_context,
        llm_client=llm_client,
    )

    storage.get_requests_by_session.assert_called_once_with(user_id, session_id)
    # Should not proceed to fetch interactions
    storage.get_interactions_by_request_ids.assert_not_called()
    storage.upsert_operation_state.assert_not_called()


def test_elapsed_time_below_threshold_returns_early() -> None:
    """When the latest request is too recent, should return early."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"

    # Create a request that was just created (now)
    now = int(datetime.now(UTC).timestamp())
    recent_request = Request(
        request_id="req_recent",
        user_id=user_id,
        session_id=session_id,
        created_at=now,
    )

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [recent_request]

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    run_group_evaluation(
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        agent_version="1.0.0",
        source="api",
        request_context=request_context,
        llm_client=llm_client,
    )

    # Should not proceed to fetch interactions
    storage.get_interactions_by_request_ids.assert_not_called()
    storage.upsert_operation_state.assert_not_called()


def test_requests_with_no_matching_interactions() -> None:
    """When requests exist but have no matching interactions, should return early."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [
        _make_request("req_1", user_id, session_id),
        _make_request("req_2", user_id, session_id),
    ]
    # Return interactions that belong to a different request_id
    storage.get_interactions_by_request_ids.return_value = []

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    run_group_evaluation(
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        agent_version="1.0.0",
        source="api",
        request_context=request_context,
        llm_client=llm_client,
    )

    # No interactions means no data models built, so no evaluation
    storage.upsert_operation_state.assert_not_called()


def test_requests_with_interactions_for_only_some_requests() -> None:
    """When interactions exist for only some requests, only those become data models."""
    org_id = "org_a"
    user_id = "user_a"
    session_id = "group_a"

    storage = MagicMock()
    storage.get_operation_state.return_value = None
    storage.get_requests_by_session.return_value = [
        _make_request("req_1", user_id, session_id),
        _make_request("req_2", user_id, session_id),
    ]
    # Only return interaction for req_1, not req_2
    storage.get_interactions_by_request_ids.return_value = [
        _make_interaction("req_1", user_id)
    ]

    request_context = MagicMock()
    request_context.storage = storage
    llm_client = MagicMock()

    with patch(
        "reflexio.server.services.agent_success_evaluation.group_evaluation_runner.AgentSuccessEvaluationService"
    ) as service_cls:
        service = MagicMock()
        service.has_run_failures.return_value = False
        service.last_run_saved_result_count = 1
        service_cls.return_value = service

        run_group_evaluation(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            agent_version="1.0.0",
            source="api",
            request_context=request_context,
            llm_client=llm_client,
        )

        # Evaluation service should have been called
        service.run.assert_called_once()
        eval_request = service.run.call_args[0][0]
        # Only req_1 should have a data model (req_2 had no interactions)
        assert len(eval_request.request_interaction_data_models) == 1
        assert (
            eval_request.request_interaction_data_models[0].request.request_id
            == "req_1"
        )
