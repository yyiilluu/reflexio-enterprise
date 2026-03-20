from __future__ import annotations

from reflexio_commons.api_schema.internal_schema import RequestInteractionDataModel
from reflexio_commons.api_schema.retriever_schema import (
    GetAgentSuccessEvaluationResultsRequest,
    GetRequestsRequest,
    UnifiedSearchRequest,
)
from reflexio_commons.api_schema.service_schemas import (
    AgentSuccessEvaluationResult,
    Interaction,
    Request,
)

from reflexio.reflexio_lib._base import STORAGE_NOT_CONFIGURED_MSG


def _make_request(request_id: str = "req1", user_id: str = "user1") -> Request:
    return Request(request_id=request_id, user_id=user_id)


def _make_interaction(request_id: str = "req1", user_id: str = "user1") -> Interaction:
    return Interaction(request_id=request_id, user_id=user_id, content="hello")


def _make_ridm(
    session_id: str = "session1",
) -> RequestInteractionDataModel:
    return RequestInteractionDataModel(
        session_id=session_id,
        request=_make_request(),
        interactions=[_make_interaction()],
    )


def _make_eval_result(
    agent_version: str = "v1", session_id: str = "sess1"
) -> AgentSuccessEvaluationResult:
    return AgentSuccessEvaluationResult(
        agent_version=agent_version,
        session_id=session_id,
        is_success=True,
    )


# ==============================
# get_agent_success_evaluation_results tests
# ==============================


def test_get_agent_success_evaluation_results_storage_not_configured(
    reflexio_no_storage,
):
    resp = reflexio_no_storage.get_agent_success_evaluation_results(
        GetAgentSuccessEvaluationResultsRequest()
    )
    assert resp.success is True
    assert resp.agent_success_evaluation_results == []
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


def test_get_agent_success_evaluation_results_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    results = [_make_eval_result("v2", "s1"), _make_eval_result("v2", "s2")]
    storage.get_agent_success_evaluation_results.return_value = results

    resp = reflexio_mock.get_agent_success_evaluation_results(
        GetAgentSuccessEvaluationResultsRequest(limit=50, agent_version="v2")
    )

    assert resp.success is True
    assert resp.agent_success_evaluation_results == results
    storage.get_agent_success_evaluation_results.assert_called_once_with(
        limit=50, agent_version="v2"
    )


def test_get_agent_success_evaluation_results_dict_input(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_agent_success_evaluation_results.return_value = []

    resp = reflexio_mock.get_agent_success_evaluation_results(
        {"limit": 25, "agent_version": "v1"}
    )

    assert resp.success is True
    storage.get_agent_success_evaluation_results.assert_called_once_with(
        limit=25, agent_version="v1"
    )


def test_get_agent_success_evaluation_results_exception(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_agent_success_evaluation_results.side_effect = RuntimeError(
        "db connection failed"
    )

    resp = reflexio_mock.get_agent_success_evaluation_results(
        GetAgentSuccessEvaluationResultsRequest()
    )

    assert resp.success is False
    assert resp.agent_success_evaluation_results == []
    assert "db connection failed" in resp.msg


# ==============================
# get_requests tests
# ==============================


def test_get_requests_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.get_requests(GetRequestsRequest())
    assert resp.success is True
    assert resp.sessions == []
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG


def test_get_requests_success(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    ridm = _make_ridm("session1")
    storage.get_sessions.return_value = {"session1": [ridm]}

    resp = reflexio_mock.get_requests(GetRequestsRequest(top_k=100))

    assert resp.success is True
    assert len(resp.sessions) == 1
    assert resp.sessions[0].session_id == "session1"
    assert len(resp.sessions[0].requests) == 1
    assert resp.sessions[0].requests[0].request == ridm.request
    assert resp.sessions[0].requests[0].interactions == ridm.interactions


def test_get_requests_has_more_true(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    ridms = [_make_ridm() for _ in range(5)]
    storage.get_sessions.return_value = {"s1": ridms}

    resp = reflexio_mock.get_requests(GetRequestsRequest(top_k=5))

    assert resp.success is True
    assert resp.has_more is True


def test_get_requests_has_more_false(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_sessions.return_value = {"s1": [_make_ridm()]}

    resp = reflexio_mock.get_requests(GetRequestsRequest(top_k=10))

    assert resp.success is True
    assert resp.has_more is False


def test_get_requests_exception(reflexio_mock):
    storage = reflexio_mock.request_context.storage
    storage.get_sessions.side_effect = RuntimeError("timeout")

    resp = reflexio_mock.get_requests(GetRequestsRequest())

    assert resp.success is False
    assert resp.sessions == []
    assert "timeout" in resp.msg


# ==============================
# unified_search tests
# ==============================


def test_unified_search_storage_not_configured(reflexio_no_storage):
    resp = reflexio_no_storage.unified_search(
        UnifiedSearchRequest(query="test"), org_id="test_org"
    )
    assert resp.success is True
    assert resp.msg == STORAGE_NOT_CONFIGURED_MSG
