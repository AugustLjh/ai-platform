from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.observability import (
    ObservabilityToolProvider,
    build_observability_audit_report,
)


def _context(workspace_root: Path | None = None) -> ToolContext:
    return ToolContext(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        workspace_root=str(workspace_root) if workspace_root is not None else None,
    )


async def test_observability_provider_exposes_policy_metadata_when_configured(tmp_path):
    log_root = tmp_path / "logs"
    log_root.mkdir()
    provider = ObservabilityToolProvider(
        enabled_tool_names=[
            "db_query_readonly",
            "redis_inspect",
            "http_health_check",
            "service_logs",
            "metrics_query",
        ],
        db_configured=True,
        redis_configured=True,
        allowed_http_domains=("127.0.0.1",),
        default_health_url="http://127.0.0.1:8000/health",
        metrics_url="http://127.0.0.1:9100/metrics",
        log_roots=[log_root],
    )

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))
    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}

    assert set(metadata_by_name) == {
        "db_query_readonly",
        "redis_inspect",
        "http_health_check",
        "service_logs",
        "metrics_query",
    }
    assert metadata_by_name["db_query_readonly"]["provider"] == "observability"
    assert metadata_by_name["db_query_readonly"]["access_level"] == "read"
    assert metadata_by_name["redis_inspect"]["capability"] == "redis_inspect"
    assert metadata_by_name["http_health_check"]["side_effect"] == "network"
    assert metadata_by_name["service_logs"]["risk_level"] == "medium"


async def test_db_query_readonly_rejects_mutating_sql():
    provider = ObservabilityToolProvider(enabled_tool_names=["db_query_readonly"], db_configured=True)
    tool = await provider.get("db_query_readonly")
    assert tool is not None

    with pytest.raises(PermissionError):
        await tool.execute(_context(), {"query": "DELETE FROM runs"})

    with pytest.raises(PermissionError):
        await tool.execute(_context(), {"query": "SELECT * FROM runs -- comment"})


async def test_service_logs_redacts_sensitive_assignments(tmp_path):
    log_root = tmp_path / "logs"
    log_root.mkdir()
    log_file = log_root / "service.log"
    log_file.write_text("token=abc123\nplain line\n", encoding="utf-8")
    provider = ObservabilityToolProvider(
        enabled_tool_names=["service_logs"],
        db_configured=False,
        log_roots=[log_root],
    )
    tool = await provider.get("service_logs")
    assert tool is not None

    result = await tool.execute(_context(), {"path": str(log_file), "max_lines": 10})

    assert result["status"] == "completed"
    assert "[REDACTED]" in result["content"]


async def test_http_health_check_accepts_loopback_urls(monkeypatch, tmp_path):
    class _Response:
        status = 200
        headers = {"content-type": "text/plain"}

        async def text(self, errors="replace"):
            return "ok"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _Session:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def get(self, url):
            self.calls.append(url)
            return _Response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("ai_runtime.core.agent_runtime.tools.providers.observability.aiohttp.ClientSession", _Session)
    provider = ObservabilityToolProvider(
        enabled_tool_names=["http_health_check"],
        db_configured=False,
        allowed_http_domains=(),
        allow_loopback_http=True,
        default_health_url="http://127.0.0.1:8000/health",
    )
    tool = await provider.get("http_health_check")
    assert tool is not None

    result = await tool.execute(_context(tmp_path), {})

    assert result["status_code"] == 200
    assert result["url"] == "http://127.0.0.1:8000/health"


async def test_metrics_query_requires_configured_metrics_url(monkeypatch):
    class _Response:
        status = 200

        async def text(self, errors="replace"):
            return "# HELP runtime_requests_total\nruntime_requests_total 3\n"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _Session:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url):
            return _Response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("ai_runtime.core.agent_runtime.tools.providers.observability.aiohttp.ClientSession", _Session)
    provider = ObservabilityToolProvider(
        enabled_tool_names=["metrics_query"],
        db_configured=False,
        metrics_url="http://127.0.0.1:9100/metrics",
    )
    tool = await provider.get("metrics_query")
    assert tool is not None

    result = await tool.execute(_context(), {"metric": "runtime_requests_total"})

    assert result["sample_count"] == 1
    assert result["samples"][0]["name"] == "runtime_requests_total"
    assert result["budget"]["line_budget"] == 5000


async def test_metrics_query_enforces_metric_allowlist_and_budget(monkeypatch):
    class _Response:
        status = 200

        async def text(self, errors="replace"):
            return "\n".join(
                [
                    "# HELP runtime_requests_total requests",
                    "runtime_requests_total 3",
                    "process_cpu_seconds_total 1",
                    "runtime_latency_seconds 2",
                ]
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _Session:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url):
            return _Response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("ai_runtime.core.agent_runtime.tools.providers.observability.aiohttp.ClientSession", _Session)
    provider = ObservabilityToolProvider(
        enabled_tool_names=["metrics_query"],
        db_configured=False,
        metrics_url="http://127.0.0.1:9100/metrics",
        allowed_metric_names=("runtime_*",),
        max_metric_lines=3,
        max_metric_samples=10,
    )
    tool = await provider.get("metrics_query")
    assert tool is not None

    result = await tool.execute(_context(), {})

    assert [sample["name"] for sample in result["samples"]] == ["runtime_requests_total"]
    assert result["budget"]["skipped_by_allowlist"] == 1
    assert result["budget"]["line_budget_exhausted"] is True
    assert result["truncated"] is True

    with pytest.raises(PermissionError):
        await tool.execute(_context(), {"metric": "process_cpu_seconds_total"})


async def test_observability_provider_status_summary_reports_enabled_tools(tmp_path):
    log_root = tmp_path / "logs"
    log_root.mkdir()
    provider = ObservabilityToolProvider(
        enabled_tool_names=["service_logs"],
        db_configured=False,
        log_roots=[log_root],
    )

    summary = provider.status_summary()

    assert summary["enabled"] is True
    assert summary["enabled_tools"] == ["service_logs"]
    assert summary["available_tools"] == ["service_logs"]
    assert summary["audit_report"]["status"] in {"healthy", "warning"}
    assert any(check["key"] == "metrics_budget" for check in summary["audit_report"]["checks"])


async def test_observability_provider_does_not_expose_disallowed_default_urls():
    provider = ObservabilityToolProvider(
        enabled_tool_names=["http_health_check", "metrics_query"],
        db_configured=False,
        allow_loopback_http=False,
        allowed_http_domains=("internal.example.com",),
        default_health_url="http://127.0.0.1:8000/health",
        metrics_url="http://127.0.0.1:9100/metrics",
    )

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))
    summary = provider.status_summary()

    assert specs == []
    assert summary["available_tools"] == []


async def test_observability_audit_report_warns_without_metrics_allowlist(tmp_path):
    provider = ObservabilityToolProvider(
        enabled_tool_names=["metrics_query"],
        db_configured=False,
        metrics_url="http://127.0.0.1:9100/metrics",
    )

    report = build_observability_audit_report(provider.policy)

    assert report["status"] == "warning"
    assert any(check["key"] == "metrics_allowlist" and check["status"] == "warning" for check in report["checks"])
