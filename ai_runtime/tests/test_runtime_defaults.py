import asyncio

from starlette.requests import Request

from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig
from ai_runtime.core.chat.service import ChatRuntimeService
from ai_runtime.core.dependencies import DEV_DEFAULT_TENANT_ID, get_current_tenant_id
from ai_runtime.core.services.knowledge_base_service import DEFAULT_GOVERNANCE_SETTINGS


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _build_request(query_string: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": query_string,
        "state": {},
    }
    return Request(scope, receive=_empty_receive)


def test_get_current_tenant_id_uses_valid_development_uuid():
    request = _build_request()

    tenant_id = asyncio.run(get_current_tenant_id(request, x_tenant_id=None))

    assert tenant_id == DEV_DEFAULT_TENANT_ID


def test_parse_request_uses_valid_development_uuid():
    service = ChatRuntimeService()
    request = type(
        "ChatRequest",
        (),
        {
            "session_id": "session-1",
            "message": "what is rag",
            "config": None,
            "metadata": {},
        },
    )()

    parsed = service.parse_request(request)

    assert parsed["tenant_id"] == DEV_DEFAULT_TENANT_ID


def test_agent_runtime_optimization_defaults_favor_shorter_runs():
    config = AgentRuntimeOptimizationConfig()

    assert config.default_max_iterations == 5
    assert config.planner_max_tokens == 500
    assert config.disable_planner_repair is False


def test_default_governance_routes_include_agent_planning_and_synthesis():
    routes = DEFAULT_GOVERNANCE_SETTINGS["routes"]

    assert "agent_planning" in routes
    assert "agent_synthesis" in routes
