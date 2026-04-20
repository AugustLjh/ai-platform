import asyncio

from starlette.requests import Request

from ai_runtime.core.chat.service import ChatRuntimeService
from ai_runtime.core.dependencies import DEV_DEFAULT_TENANT_ID, get_current_tenant_id


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
