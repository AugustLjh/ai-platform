from __future__ import annotations

import time

from ai_runtime.core.agent_runtime.runtime import AgentRuntime
from ai_runtime.core.agent_runtime.tools.providers.web import BrowserSession, WebToolProvider


class _FakePool:
    async def fetchrow(self, *args, **kwargs):
        raise RuntimeError("unexpected database access")

    async def fetch(self, *args, **kwargs):
        raise RuntimeError("unexpected database access")

    async def execute(self, *args, **kwargs):
        raise RuntimeError("unexpected database access")


def _readiness_case(*, scenarios: list[str], report: str) -> dict:
    return {
        "status": "passed",
        "case_count": len(scenarios),
        "generated_at": "2026-05-21T00:00:00+00:00",
        "report_uri": report,
        "scenarios": [{"key": item, "status": "passed"} for item in scenarios],
        "recovery_actions": ["review evidence report", "rerun drill after policy changes"],
    }


async def test_agent_runtime_start_and_shutdown_are_safe():
    runtime = AgentRuntime(_FakePool())

    await runtime.start()
    await runtime.shutdown()

    assert runtime.workspace_lifecycle.running is False


async def test_runtime_status_reports_registered_provider_names(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_WORKSPACE_ENABLED", "false")
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_WEB_ENABLED", "true")
    monkeypatch.setenv("AGENT_WEB_NETWORK_CONFIGURED", "true")

    runtime = AgentRuntime(_FakePool())
    status = runtime.runtime_status()

    assert "builtin" in status["providers"]["configured"]
    assert "knowledge" in status["providers"]["configured"]
    assert "sandbox-exec" in status["providers"]["configured"]
    assert "web" in status["providers"]["configured"]
    assert "observability" in status["providers"]["configured"]
    assert status["providers"]["sandbox"]["enabled"] is True
    assert status["providers"]["sandbox"]["limits"]["docker"]["network"] == "none"
    assert status["providers"]["sandbox"]["isolation"]["production_ready"] is True
    assert status["providers"]["sandbox"]["isolation"]["failed"] == 0
    assert status["providers"]["web"]["enabled"] is True
    assert status["providers"]["observability"]["available_tools"]
    assert "binding_policies" in status["providers"]["workspace"]
    assert status["ops"]["alerts"]["status"] == "healthy"
    assert status["ops"]["slo"]["status"] == "healthy"


async def test_runtime_lists_mcp_governance_tools():
    runtime = AgentRuntime(_FakePool())

    result = await runtime.list_tools(tenant_id="00000000-0000-0000-0000-000000000001")
    tool_names = {tool["name"] for tool in result["tools"]}

    assert "mcp_catalog_status" in tool_names
    assert "mcp_refresh_catalog" in tool_names
    assert "mcp_test_connection" in tool_names
    assert "mcp_recovery_plan" in tool_names
    assert "mcp_tool_result_normalize" in tool_names
    assert result["execution_mode"]["name"] == "context_only"


async def test_runtime_list_tools_applies_execution_mode_capability_filter(monkeypatch):
    runtime = AgentRuntime(_FakePool())

    async def fake_get_definition(agent_definition_id, tenant_id):
        return {
            "id": agent_definition_id,
            "tenant_id": tenant_id,
            "config": {"execution_mode": "context_only"},
        }

    async def fake_list_specs(context=None):
        return [
            {"name": "calculator", "description": "calc", "input_schema": {}, "kind": "builtin", "metadata": {}},
            {
                "name": "project_list_context",
                "description": "context",
                "input_schema": {},
                "kind": "project-context",
                "metadata": {"provider": "project-context", "capability": "project_context"},
            },
            {
                "name": "workspace_read_file",
                "description": "read file",
                "input_schema": {},
                "kind": "workspace",
                "metadata": {"provider": "workspace", "capability": "workspace", "access_level": "read"},
            },
            {
                "name": "run_tests",
                "description": "tests",
                "input_schema": {},
                "kind": "sandbox-exec",
                "metadata": {"provider": "sandbox-exec", "capability": "test"},
            },
        ]

    monkeypatch.setattr(runtime.agent_repository, "get_definition", fake_get_definition)
    monkeypatch.setattr(runtime.registry, "list_specs", fake_list_specs)

    result = await runtime.list_tools(
        tenant_id="00000000-0000-0000-0000-000000000001",
        agent_definition_id="agent-1",
    )
    tools = result["tools"]

    assert [tool["name"] for tool in tools] == ["calculator", "project_list_context"]
    assert all(tool["metadata"]["execution_mode"] == "context_only" for tool in tools)
    assert all(tool["metadata"]["execution_mode_allowed"] is True for tool in tools)
    assert result["execution_mode"]["blocked_tool_count"] == 2
    assert any(item["key"] == "workspace_read" and item["enabled"] is False for item in result["execution_mode"]["capability_details"])


async def test_runtime_evaluation_history_falls_back_to_memory():
    runtime = AgentRuntime(_FakePool())

    result = {
        "status": "healthy",
        "total": 2,
        "passed": 2,
        "warning": 0,
        "failed": 0,
        "average_score": 1.0,
        "summary": "all checks passed",
    }
    stored = await runtime._persist_evaluation_record(
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id=None,
        evaluation_type="web_search_quality",
        suite_name="runtime.web.search-quality",
        result=result,
    )
    history = await runtime.list_evaluation_history(
        tenant_id="00000000-0000-0000-0000-000000000001",
        evaluation_type="web_search_quality",
        limit=10,
    )

    assert stored["metadata"]["storage"] == "memory_fallback"
    assert history["count"] == 1
    assert history["history"][0]["evaluation_type"] == "web_search_quality"
    assert history["history_summary"]["comparison"]["current_score"] == 1.0
    assert history["history_comparison"]["delta"]["score"] == 0.0


async def test_runtime_evaluation_history_returns_comparison_for_recent_records():
    runtime = AgentRuntime(_FakePool())
    tenant_id = "00000000-0000-0000-0000-000000000001"

    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="subagent_quality",
        suite_name="runtime.subagents.quality",
        result={
            "status": "warning",
            "total": 2,
            "passed": 1,
            "warning": 1,
            "failed": 0,
            "average_score": 0.5,
            "summary": "baseline",
        },
    )
    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="subagent_quality",
        suite_name="runtime.subagents.quality",
        result={
            "status": "passed",
            "total": 3,
            "passed": 3,
            "warning": 0,
            "failed": 0,
            "average_score": 1.0,
            "summary": "improved",
            "readiness": "controlled_trial_ready",
            "blocking_checks": [],
            "evidence_summary": {
                "quality": {
                    "average_quality_score": 1.0,
                    "quality_failed_count": 0,
                }
            },
        },
    )

    history = await runtime.list_evaluation_history(
        tenant_id=tenant_id,
        evaluation_type="subagent_quality",
        limit=10,
    )

    assert history["count"] == 2
    assert history["history_summary"]["comparison"]["current_score"] == 1.0
    assert history["history_summary"]["comparison"]["current_total"] == 3
    assert history["history_summary"]["comparison"]["pass_ratio"] == 1.0
    assert history["history_summary"]["comparison"]["readiness"] == "controlled_trial_ready"
    assert history["history_summary"]["comparison"]["evidence_quality_score"] == 1.0
    assert history["history_comparison"]["delta"]["score"] == 0.5
    assert history["history_comparison"]["delta"]["passed"] == 2
    assert history["history_comparison"]["delta"]["pass_ratio"] == 0.5
    assert "score improved by +0.50" in history["history_comparison"]["summary"]
    assert history["history_summary"]["trend"]["direction"] == "improving"
    assert history["history_comparison"]["trend"]["window_size"] == 2
    assert history["history_comparison"]["trend"]["delta_from_baseline"]["score"] == 0.5


async def test_runtime_evaluation_history_preserves_type_specific_metrics():
    runtime = AgentRuntime(_FakePool())
    tenant_id = "00000000-0000-0000-0000-000000000001"

    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="web_search_quality",
        suite_name="runtime.web.search_quality",
        result={
            "status": "warning",
            "total": 2,
            "passed": 1,
            "warning": 1,
            "failed": 0,
            "average_score": 0.6,
            "summary": "baseline",
            "total_results": 10,
            "accepted_count": 6,
            "rejected_count": 4,
            "check_count": 12,
            "passed_check_count": 9,
            "failed_check_count": 3,
        },
    )
    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="web_search_quality",
        suite_name="runtime.web.search_quality",
        result={
            "status": "passed",
            "total": 2,
            "passed": 2,
            "warning": 0,
            "failed": 0,
            "average_score": 0.9,
            "summary": "improved",
            "total_results": 10,
            "accepted_count": 8,
            "rejected_count": 2,
            "check_count": 12,
            "passed_check_count": 11,
            "failed_check_count": 1,
        },
    )

    history = await runtime.list_evaluation_history(
        tenant_id=tenant_id,
        evaluation_type="web_search_quality",
        limit=10,
    )

    assert history["history_summary"]["comparison"]["accepted_ratio"] == 0.8
    assert history["history_summary"]["comparison"]["check_pass_ratio"] == 0.9167
    assert history["history_comparison"]["delta"]["accepted_ratio"] == 0.2
    assert history["history_comparison"]["delta"]["check_pass_ratio"] == 0.1667
    assert "accepted ratio +0.20" in history["history_comparison"]["summary"]
    assert history["history_summary"]["trend"]["average_accepted_ratio"] == 0.7
    assert history["history_summary"]["trend"]["average_check_pass_ratio"] == 0.8334


async def test_runtime_evaluation_history_builds_recent_trend_window_summary():
    runtime = AgentRuntime(_FakePool())
    tenant_id = "00000000-0000-0000-0000-000000000001"

    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="subagent_quality",
        suite_name="runtime.subagents.quality",
        result={
            "status": "warning",
            "total": 4,
            "passed": 2,
            "warning": 1,
            "failed": 1,
            "average_score": 0.4,
            "summary": "baseline",
        },
    )
    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="subagent_quality",
        suite_name="runtime.subagents.quality",
        result={
            "status": "warning",
            "total": 4,
            "passed": 3,
            "warning": 1,
            "failed": 0,
            "average_score": 0.7,
            "summary": "midpoint",
        },
    )
    await runtime._persist_evaluation_record(
        tenant_id=tenant_id,
        user_id=None,
        evaluation_type="subagent_quality",
        suite_name="runtime.subagents.quality",
        result={
            "status": "passed",
            "total": 4,
            "passed": 4,
            "warning": 0,
            "failed": 0,
            "average_score": 0.95,
            "summary": "current",
        },
    )

    history = await runtime.list_evaluation_history(
        tenant_id=tenant_id,
        evaluation_type="subagent_quality",
        limit=10,
    )

    trend = history["history_comparison"]["trend"]
    assert trend["window_size"] == 3
    assert trend["direction"] == "improving"
    assert trend["best_score"] == 0.95
    assert trend["worst_score"] == 0.4
    assert trend["average_score"] == 0.6833
    assert trend["delta_from_baseline"]["score"] == 0.55
    assert trend["status_counts"] == {"passed": 1, "warning": 2, "failed": 0}
    assert "recent 3-run trend improving" in trend["summary"]


async def test_runtime_status_reports_sandbox_isolation_failures(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_WORKSPACE_ENABLED", "false")
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_BACKEND", "docker")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_NETWORK", "bridge")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_PIDS_LIMIT", "2048")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_READ_ONLY_ROOTFS", "false")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_CAP_DROP", "NET_RAW")

    runtime = AgentRuntime(_FakePool())
    status = runtime.runtime_status()
    sandbox = status["providers"]["sandbox"]
    checks_by_key = {check["key"]: check for check in sandbox["isolation"]["checks"]}

    assert sandbox["isolation"]["status"] == "failed"
    assert sandbox["isolation"]["production_ready"] is False
    assert checks_by_key["docker_network"]["status"] == "fail"
    assert checks_by_key["docker_pids_limit"]["status"] == "fail"
    assert checks_by_key["docker_read_only_rootfs"]["status"] == "warn"


async def test_runtime_status_reports_workspace_lifecycle_telemetry():
    runtime = AgentRuntime(_FakePool())

    await runtime._handle_workspace_lifecycle_alert(
        {
            "type": "expired_workspaces",
            "severity": "warning",
            "count": 3,
            "threshold": 2,
        }
    )
    await runtime._handle_workspace_lifecycle_inspection(
        {
            "generated_at": "2026-05-16T00:00:00+00:00",
            "inspection": {
                "workspace_count": 4,
                "expired_count": 3,
                "quota_exceeded_count": 1,
                "total_size_bytes": 1024,
                "total_file_count": 12,
            },
            "cleanup": {
                "status": "completed",
                "dry_run": True,
                "candidate_count": 3,
                "selected_count": 2,
                "deleted_count": 0,
                "failed_count": 0,
            },
            "alerts": [
                {
                    "type": "expired_workspaces",
                    "severity": "warning",
                    "count": 3,
                    "threshold": 2,
                }
            ],
        }
    )

    status = runtime.runtime_status()
    lifecycle = status["workspace_lifecycle"]

    assert lifecycle["last_run"]["inspection"]["workspace_count"] == 4
    assert lifecycle["last_run"]["cleanup"]["candidate_count"] == 3
    assert lifecycle["last_run"]["alerts"][0]["type"] == "expired_workspaces"
    assert lifecycle["recent_alerts"][0]["count"] == 3
    assert status["ops"]["slo"]["slo_count"] > 0


async def test_runtime_production_readiness_blocks_without_pressure_evidence(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_WEB_ENABLED", "true")
    monkeypatch.setenv("AGENT_WEB_NETWORK_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "true")

    runtime = AgentRuntime(_FakePool())

    result = runtime.evaluate_production_readiness()

    assert result["protocol_version"] == "managed-runtime.production-readiness.v1"
    assert result["status"] == "failed"
    assert result["readiness"] == "blocked"
    assert any(item["subsystem"] == "sandbox" and item["key"] == "escape_drill" for item in result["blocking_checks"])
    assert result["subsystems"]["subagents"]["checks"][0]["status"] == "pass"


async def test_runtime_production_readiness_accepts_complete_trial_evidence(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_BACKEND", "docker")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_NETWORK", "none")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_PIDS_LIMIT", "256")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_CAP_DROP", "ALL")
    monkeypatch.setenv("AGENT_WEB_ENABLED", "true")
    monkeypatch.setenv("AGENT_WEB_NETWORK_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "true")

    runtime = AgentRuntime(_FakePool())

    def fake_inspect_workspaces():
        return {
            "workspace_count": 0,
            "expired_count": 0,
            "quota_exceeded_count": 0,
            "total_size_bytes": 0,
            "total_file_count": 0,
            "workspaces": [],
            "lock_summary": {"stale_lock_count": 0, "orphan_lock_count": 0},
        }

    monkeypatch.setattr(runtime.workspace_manager, "inspect_workspaces", fake_inspect_workspaces)
    await runtime._handle_workspace_lifecycle_inspection(
        {
            "generated_at": "2026-05-21T00:00:00+00:00",
            "inspection": {
                "workspace_count": 0,
                "expired_count": 0,
                "quota_exceeded_count": 0,
                "total_size_bytes": 0,
                "total_file_count": 0,
                "health": {"status": "healthy", "score": 100, "summary": "clean"},
                "lock_summary": {"stale_lock_count": 0, "orphan_lock_count": 0},
            },
            "cleanup": {
                "status": "completed",
                "dry_run": True,
                "candidate_count": 0,
                "selected_count": 0,
                "deleted_count": 0,
                "failed_count": 0,
            },
            "alerts": [],
        }
    )
    evidence = {
        "sandbox": {
            "escape_drill": _readiness_case(
                scenarios=["path_escape", "network_disabled", "capabilities_dropped", "readonly_rootfs"],
                report="artifact://readiness/sandbox-escape",
            ),
            "resource_exhaustion_drill": _readiness_case(
                scenarios=["cpu_limit", "memory_limit", "pid_limit", "timeout"],
                report="artifact://readiness/sandbox-resource",
            ),
            "concurrent_dev_server_drill": _readiness_case(
                scenarios=["concurrent_startup", "log_collection", "process_cleanup"],
                report="artifact://readiness/sandbox-dev-server",
            ),
        },
        "workspace": {
            "large_repo_pressure_drill": _readiness_case(
                scenarios=["indexing", "search", "bounded_output", "quota"],
                report="artifact://readiness/workspace-large-repo",
            ),
            "writeback_rehearsal": _readiness_case(
                scenarios=["dry_run", "confirmed", "protected_path", "audit_artifact"],
                report="artifact://readiness/workspace-writeback",
            ),
        },
        "web_browser_pdf": {
            "long_session_drill": _readiness_case(
                scenarios=["ttl_cleanup", "stale_session_cleanup", "browser_verify"],
                report="artifact://readiness/web-long-session",
            ),
            "download_safety_drill": _readiness_case(
                scenarios=["mime_block", "size_block", "domain_policy", "artifact_redaction"],
                report="artifact://readiness/web-download",
            ),
        },
        "observability": {
            "readonly_account_drill": _readiness_case(
                scenarios=["allowed_select", "blocked_write", "blocked_multi_statement", "statement_timeout"],
                report="artifact://readiness/observability-readonly",
            ),
            "redaction_drill": _readiness_case(
                scenarios=["logs", "db_output", "tool_call_payload"],
                report="artifact://readiness/observability-redaction",
            ),
        },
        "subagents": {
            "multi_worker_replay": _readiness_case(
                scenarios=["successful_sibling", "failed_child", "failure_strategy", "recovery_actions"],
                report="artifact://readiness/subagents-multi-worker",
            ),
            "complex_write_scope_replay": _readiness_case(
                scenarios=["overlap", "rename", "delete", "writeback_confirmation"],
                report="artifact://readiness/subagents-write-scope",
            ),
            "resume_waiting_user_replay": _readiness_case(
                scenarios=["waiting_user_visible", "resume_boundary", "stale_child_hidden"],
                report="artifact://readiness/subagents-resume",
            ),
        },
    }

    result = runtime.evaluate_production_readiness(evidence=evidence)

    assert result["status"] == "passed"
    assert result["readiness"] == "controlled_trial_ready"
    assert result["failed"] == 0
    assert result["warning"] == 0
    assert result["subsystems"]["sandbox"]["status"] == "ready"
    assert result["subsystems"]["workspace"]["status"] == "ready"
    assert result["evidence_summary"]["subsystems"] == [
        "observability",
        "sandbox",
        "subagents",
        "web_browser_pdf",
        "workspace",
    ]
    assert result["evidence_summary"]["quality"]["quality_failed_count"] == 0
    assert result["evidence_summary"]["quality"]["average_quality_score"] == 1.0


async def test_runtime_production_readiness_rejects_thin_pressure_evidence(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_ENABLED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_BACKEND", "docker")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_NETWORK", "none")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_PIDS_LIMIT", "256")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_READ_ONLY_ROOTFS", "true")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_CAP_DROP", "ALL")

    runtime = AgentRuntime(_FakePool())
    evidence = {
        "sandbox": {
            "escape_drill": {
                "status": "passed",
                "case_count": 1,
                "scenarios": [{"key": "path_escape", "status": "passed"}],
            }
        }
    }

    result = runtime.evaluate_production_readiness(evidence=evidence)
    escape_check = next(
        item for item in result["subsystems"]["sandbox"]["checks"] if item["key"] == "escape_drill"
    )

    assert result["readiness"] == "blocked"
    assert escape_check["status"] == "fail"
    assert escape_check["evidence"]["quality"]["passed"] is False
    assert "network_disabled" in escape_check["evidence"]["quality"]["missing_scenarios"]
    assert result["evidence_summary"]["quality"]["quality_failed_count"] >= 1


async def test_runtime_ops_status_exposes_alerts_slo_and_runbooks():
    runtime = AgentRuntime(_FakePool())
    await runtime._handle_workspace_lifecycle_alert(
        {
            "type": "expired_workspaces",
            "severity": "warning",
            "expired_count": 15,
            "count": 15,
            "threshold": 10,
        }
    )

    status = await runtime.ops_status()

    assert status["alerts"]["active_alert_count"] >= 1
    assert status["slo"]["slo_count"] > 0
    assert status["monitoring"]["prometheus"]["path"] == "/api/v1/agents/ops-status/metrics"
    assert status["monitoring"]["grafana"]["dashboard_uid"] == "agent-runtime-ops"
    assert status["subsystems"]["workspace"]["runbooks"]


async def test_runtime_ops_status_exposes_tenant_governance_snapshot(monkeypatch):
    monkeypatch.setenv("AGENT_TENANT_MAX_ACTIVE_RUNS", "2")
    monkeypatch.setenv("AGENT_TENANT_MAX_RUNS_PER_WINDOW", "5")
    monkeypatch.setenv("AGENT_TENANT_MAX_TOOL_CALLS_PER_WINDOW", "9")
    monkeypatch.setenv("AGENT_TENANT_MAX_NETWORK_TOOL_CALLS_PER_WINDOW", "3")
    monkeypatch.setenv("AGENT_TENANT_MAX_WORKSPACE_BYTES", "1024")
    monkeypatch.setenv("AGENT_TENANT_MAX_WORKSPACE_COUNT", "1")
    monkeypatch.setenv("AGENT_TENANT_QUOTA_ENFORCEMENT_ENABLED", "true")

    runtime = AgentRuntime(_FakePool())

    async def fake_fetch_tenant_runtime_usage(*args, **kwargs):
        return (
            {"active_runs": 3, "runs_in_window": 7},
            {"tool_calls_in_window": 10, "network_tool_calls_in_window": 4},
            {"invocations_in_window": 2},
        )

    def fake_inspect_workspaces():
        return {
            "workspaces": [
                {
                    "tenant_id": "tenant-1",
                    "expired": False,
                    "quota_exceeded": False,
                    "size_bytes": 2048,
                    "file_count": 8,
                }
            ]
        }

    monkeypatch.setattr("ai_runtime.core.agent_runtime.runtime.fetch_tenant_runtime_usage", fake_fetch_tenant_runtime_usage)
    monkeypatch.setattr(runtime.workspace_manager, "inspect_workspaces", fake_inspect_workspaces)

    status = await runtime.ops_status(tenant_id="tenant-1")
    governance = status["tenant_governance"]

    assert governance["tenant_id"] == "tenant-1"
    assert governance["status"] == "blocked"
    assert governance["blocking_metrics"][0]["key"] == "active_runs"
    assert governance["metrics"][0]["status"] == "exceeded"


async def test_runtime_evaluate_health_fires_workspace_alert():
    runtime = AgentRuntime(_FakePool())
    status = {
        "providers": {
            "workspace": {
                "inspection": {
                    "expired_count": 15,
                    "quota_exceeded_count": 0,
                    "total_size_bytes": 0,
                    "lock_summary": {"stale_lock_count": 0},
                }
            },
            "sandbox": {"isolation": {"status": "ready"}},
            "web": {"browser_sessions": {"session_count": 0, "active_session_count": 0, "network_error_count": 0}},
            "observability": {"db_configured": False, "redis_configured": False},
        }
    }

    result = await runtime.evaluate_runtime_health(status)

    assert any(alert["rule_name"] == "workspace_expired_count_high" for alert in result["fired"])
    assert result["alerts"]["active_alert_count"] >= 1
    assert result["monitoring"]["grafana"]["path"] == "/api/v1/agents/ops-status/grafana-dashboard"


async def test_runtime_exports_prometheus_metrics_and_grafana_dashboard():
    runtime = AgentRuntime(_FakePool())
    await runtime._handle_workspace_lifecycle_alert(
        {
            "type": "expired_workspaces",
            "severity": "warning",
            "expired_count": 15,
            "count": 15,
            "threshold": 10,
        }
    )
    runtime.slo_tracker.record("workspace_cleanup_success_rate", good=False)

    metrics = runtime.ops_prometheus_metrics()
    dashboard = runtime.ops_grafana_dashboard()

    assert "agent_runtime_alerts_active" in metrics
    assert "workspace_expired_count_high" in metrics
    assert "agent_runtime_slo_breached" in metrics
    assert dashboard["uid"] == "agent-runtime-ops"


async def test_runtime_status_reports_workspace_health_and_recovery_actions():
    runtime = AgentRuntime(_FakePool())
    runtime._workspace_lifecycle_last_run = {
        "generated_at": "2026-05-16T00:00:00+00:00",
        "inspection": {
            "workspace_count": 2,
            "expired_count": 1,
            "quota_exceeded_count": 1,
            "total_size_bytes": 1024,
            "total_file_count": 8,
            "health": {
                "status": "warning",
                "score": 72,
                "summary": "workspace lifecycle needs attention",
                "issues": [{"code": "expired_workspaces", "count": 1}],
                "recovery_actions": [{"key": "cleanup_expired_workspaces", "label": "清理过期 workspace"}],
            },
            "lock_summary": {
                "lock_count": 1,
                "active_lock_count": 0,
                "stale_lock_count": 1,
                "orphan_lock_count": 0,
                "oldest_lock_age_seconds": 7200,
                "locks": [{"workspace_id": "tenant-1/run-1"}],
            },
        },
        "cleanup": None,
        "alerts": [],
    }

    status = runtime.runtime_status()
    lifecycle = status["workspace_lifecycle"]

    assert lifecycle["last_run"]["inspection"]["health"]["score"] == 72
    assert lifecycle["last_run"]["inspection"]["lock_summary"]["stale_lock_count"] == 1
    assert lifecycle["recovery_actions"][0]["key"] == "cleanup_expired_workspaces"


async def test_runtime_status_reports_workspace_lifecycle_history_and_trend():
    runtime = AgentRuntime(_FakePool())
    await runtime._handle_workspace_lifecycle_inspection(
        {
            "generated_at": "2026-05-16T00:00:00+00:00",
            "inspection": {
                "workspace_count": 2,
                "expired_count": 1,
                "quota_exceeded_count": 0,
                "total_size_bytes": 100,
                "total_file_count": 4,
                "health": {
                    "status": "warning",
                    "score": 88,
                    "summary": "baseline",
                    "issues": [],
                    "recovery_actions": [],
                },
                "lock_summary": {
                    "lock_count": 0,
                    "active_lock_count": 0,
                    "stale_lock_count": 0,
                    "orphan_lock_count": 0,
                    "oldest_lock_age_seconds": None,
                    "locks": [],
                },
            },
            "cleanup": None,
            "alerts": [],
        }
    )
    await runtime._handle_workspace_lifecycle_inspection(
        {
            "generated_at": "2026-05-16T01:00:00+00:00",
            "inspection": {
                "workspace_count": 3,
                "expired_count": 2,
                "quota_exceeded_count": 1,
                "total_size_bytes": 200,
                "total_file_count": 8,
                "health": {
                    "status": "critical",
                    "score": 70,
                    "summary": "worse",
                    "issues": [{"code": "expired_workspaces", "count": 2}],
                    "recovery_actions": [{"key": "cleanup_expired_workspaces", "label": "清理过期 workspace"}],
                },
                "lock_summary": {
                    "lock_count": 1,
                    "active_lock_count": 0,
                    "stale_lock_count": 1,
                    "orphan_lock_count": 0,
                    "oldest_lock_age_seconds": 7200,
                    "locks": [{"workspace_id": "tenant-1/run-1"}],
                },
            },
            "cleanup": {
                "status": "completed",
                "dry_run": True,
                "candidate_count": 2,
                "selected_count": 1,
                "deleted_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
            },
            "alerts": [],
        }
    )

    status = runtime.runtime_status()
    lifecycle = status["workspace_lifecycle"]

    assert lifecycle["history"][0]["generated_at"] == "2026-05-16T00:00:00+00:00"
    assert lifecycle["history"][1]["generated_at"] == "2026-05-16T01:00:00+00:00"
    assert lifecycle["trend"]["status"] == "worsening"
    assert lifecycle["trend"]["window_size"] == 2
    assert lifecycle["trend"]["delta"]["expired_count"] == 1
    assert lifecycle["trend"]["delta"]["health_score"] == -18


async def test_runtime_status_reports_browser_session_health_alerts_and_trend(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_WORKSPACE_ENABLED", "false")

    runtime = AgentRuntime(_FakePool())
    provider = WebToolProvider(
        enabled_tool_names=["browser_open"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
        browser_session_ttl_seconds=60,
    )
    runtime.registry.register_provider(provider, name="web")

    healthy_status = runtime.runtime_status()
    healthy_sessions = healthy_status["providers"]["web"]["browser_sessions"]

    assert healthy_sessions["health"]["status"] == "healthy"
    assert healthy_sessions["trend"]["status"] == "baseline"

    provider.browser_sessions["browser-session-expired"] = BrowserSession(
        session_id="browser-session-expired",
        url="https://app.example.com/old",
        title="Old App",
        playwright=None,
        browser=None,
        context=None,
        page=None,
        created_at=time.monotonic() - 120,
        updated_at=time.monotonic() - 120,
        viewport={"width": 1280, "height": 720},
        console_messages=[{"level": "error", "text": "boom"}],
        network_errors=[{"url": "https://app.example.com/api", "text": "failed"}],
    )

    status = runtime.runtime_status()
    sessions = status["providers"]["web"]["browser_sessions"]

    assert sessions["expired_session_count"] == 1
    assert sessions["network_error_count"] == 1
    assert sessions["health"]["status"] == "warning"
    assert sessions["health"]["recovery_actions"][0]["key"] == "close_stale_browser_sessions"
    assert sessions["alerts"][0]["type"] == "expired_browser_sessions"
    assert sessions["trend"]["status"] == "worsening"
    assert sessions["trend"]["delta"]["expired_session_count"] == 1
