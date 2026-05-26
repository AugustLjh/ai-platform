from ai_runtime.core.agent_runtime.mcp.models import MCPServerDefinition
from ai_runtime.core.agent_runtime.mcp.registry import (
    MCPRegistry,
    _mask_sensitive_object,
    _sanitize_endpoint,
    _sanitize_error_message,
)


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


def test_mask_sensitive_object_masks_headers_and_env_values():
    masked = _mask_sensitive_object(
        {
            "headers": {"Authorization": "Bearer secret-token", "X-Trace": "ok"},
            "env": {"OPENAI_API_KEY": "runtime-secret"},
            "summary": "safe",
        }
    )

    assert masked["headers"]["Authorization"] == "********"
    assert masked["env"]["OPENAI_API_KEY"] == "********"
    assert masked["summary"] == "safe"


def test_build_audit_report_summarizes_risk_distribution():
    registry = MCPRegistry(db_pool=None)
    report = registry._build_audit_report(
        tenant_id="tenant-1",
        servers=[
            {
                "server": {"id": "server-1", "name": "Docs MCP", "transport": "http", "status": "active"},
                "security_score": {
                    "score": 35,
                    "risk_level": "critical",
                    "summary": "critical risk",
                    "evaluated_at": "2026-05-19T00:00:00+00:00",
                    "breakdown": [],
                },
                "recovery": {"status": "blocked", "recoverable": True, "failure_mode": "connection_failed"},
                "catalog": {"is_stale": True},
                "connection": {"status": "untested"},
                "binding_usage": {"agent_count": 2, "active_agent_count": 1},
                "events": [],
            }
        ],
        recent_events=[{"action_type": "test", "failure_mode": "connection_failed"}],
        limit=12,
    )

    assert report["overview"]["critical_risk_count"] == 1
    assert report["overview"]["blocked_count"] == 1
    assert report["score_distribution"]["critical"] == 1
    assert report["recommended_actions"][0].startswith("先处理 critical/blocked")
