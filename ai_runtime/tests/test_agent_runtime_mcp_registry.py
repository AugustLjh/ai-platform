from ai_runtime.core.agent_runtime.mcp.models import MCPServerDefinition
from ai_runtime.core.agent_runtime.mcp.registry import _sanitize_endpoint, _sanitize_error_message


def build_server(**kwargs):
    payload = {
        "id": "server-1",
        "tenant_id": "tenant-1",
        "name": "Test MCP",
        "transport": "http",
        "endpoint": "https://user:pass@example.com/mcp?api_key=top-secret&mode=demo",
        "metadata": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "X-Trace": "visible",
            }
        },
        "env": {
            "OPENAI_API_KEY": "runtime-secret",
            "LOG_LEVEL": "debug",
        },
    }
    payload.update(kwargs)
    return MCPServerDefinition.model_validate(payload)


def test_sanitize_endpoint_masks_userinfo_and_sensitive_query_values():
    sanitized = _sanitize_endpoint("https://user:pass@example.com/mcp?api_key=top-secret&mode=demo")

    assert "user" not in sanitized
    assert "pass" not in sanitized
    assert "top-secret" not in sanitized
    assert "mode=demo" in sanitized
    assert "********" in sanitized


def test_sanitize_error_message_masks_server_secrets():
    server = build_server()
    error = RuntimeError(
        "request to https://user:pass@example.com/mcp?api_key=top-secret&mode=demo failed "
        "with header Bearer secret-token and env runtime-secret"
    )

    sanitized = _sanitize_error_message(server, error)

    assert "top-secret" not in sanitized
    assert "secret-token" not in sanitized
    assert "runtime-secret" not in sanitized
    assert "********" in sanitized
    assert "mode=demo" in sanitized
