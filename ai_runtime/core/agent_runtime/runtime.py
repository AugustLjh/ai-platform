from __future__ import annotations

import asyncio
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from ai_runtime.core.agent_runtime.executor import AgentExecutor
from ai_runtime.core.agent_runtime.execution_modes import (
    annotate_tool_spec_for_execution_mode,
    build_execution_mode_surface,
    filter_tool_specs_for_execution_mode,
    normalize_execution_mode,
)
from ai_runtime.core.agent_runtime.alerting import (
    AlertManager,
    SLOTracker,
    build_alert_sinks_from_env,
    build_grafana_dashboard,
    export_ops_prometheus_metrics,
    get_all_runbook_entries,
    get_runbook_entries,
    monitoring_export_status,
)
from ai_runtime.core.agent_runtime.events import sanitize_runtime_payload
from ai_runtime.core.agent_runtime.llm_service import AgentLLMService
from ai_runtime.core.agent_runtime.memory import RuntimeStateStore
from ai_runtime.core.agent_runtime.mcp.registry import MCPRegistry
from ai_runtime.core.agent_runtime.models import (
    AgentArtifact,
    AgentRun,
    AgentRunEvent,
    AgentRunEventListResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    AgentRunTreeEdge,
    AgentRunTreeNode,
    AgentRunTreeResponse,
    AgentRunTreeRunSummary,
    AgentSubagentInvocation,
    AgentSubagentInvocationListResponse,
    RuntimeArtifactReviewDecisionRequest,
    RuntimeCreateRunRequest,
    RuntimeWorkspaceWritebackRequest,
)
from ai_runtime.core.agent_runtime.orchestrator import AgentOrchestrator
from ai_runtime.core.agent_runtime.skills.registry import SkillRegistry
from ai_runtime.core.agent_runtime.planner import AgentPlanner
from ai_runtime.core.agent_runtime.production_readiness import evaluate_production_readiness
from ai_runtime.contracts import hydrate_legacy_result, merge_artifacts
from ai_runtime.core.agent_runtime.subagents.governance import prune_runtime_governance_ledger_for_resume
from ai_runtime.core.agent_runtime.summarizer import AgentSummarizer
from ai_runtime.core.agent_runtime.tenant_governance import (
    TenantGovernanceConfig,
    build_tenant_governance_snapshot,
    fetch_tenant_runtime_usage,
)
from ai_runtime.core.agent_runtime.repositories.agent_repository import AgentRepository
from ai_runtime.core.agent_runtime.repositories.evaluation_repository import EvaluationRepository
from ai_runtime.core.agent_runtime.repositories.run_repository import RunRepository
from ai_runtime.core.agent_runtime.repositories.subagent_invocation_repository import SubagentInvocationRepository
from ai_runtime.core.agent_runtime.subagents.handoff import SubagentHandoff
from ai_runtime.core.agent_runtime.subagents.registry import SubagentRegistry
from ai_runtime.core.agent_runtime.subagents.router import SubagentRouter
from ai_runtime.core.agent_runtime.repositories.tool_call_repository import ToolCallRepository
from ai_runtime.core.agent_runtime.tools.base import ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.bootstrap import configure_tool_registry
from ai_runtime.core.agent_runtime.tools.providers.sandbox_exec import SandboxExecToolProvider, build_sandbox_isolation_profile
from ai_runtime.core.agent_runtime.tools.providers.observability import ObservabilityToolProvider
from ai_runtime.core.agent_runtime.tools.registry import ToolRegistry
from ai_runtime.core.agent_runtime.tracing import AgentTracer
from ai_runtime.core.agent_runtime.web_quality import evaluate_default_web_search_quality_suite
from ai_runtime.core.agent_runtime.workspace_lifecycle import (
    WorkspaceLifecyclePolicy,
    WorkspaceLifecycleScheduler,
)
from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager
from ai_runtime.core.uploads.bundle_store import get_attachment_bundle_store, normalize_bundle_ids


class AgentRuntime:
    _instance: "AgentRuntime | None" = None

    def __init__(self, db_pool) -> None:
        AgentRuntime._instance = self
        self.agent_repository = AgentRepository(db_pool)
        self.evaluation_repository = EvaluationRepository(db_pool)
        self.run_repository = RunRepository(db_pool)
        self.tool_call_repository = ToolCallRepository(db_pool)
        self.subagent_invocation_repository = SubagentInvocationRepository(db_pool)
        self.state_store = RuntimeStateStore()
        self.registry = ToolRegistry()
        self.mcp_registry = MCPRegistry(db_pool)
        configure_tool_registry(self.registry, mcp_registry=self.mcp_registry, db_pool=db_pool)
        self.skill_registry = SkillRegistry(db_pool)
        self.subagent_registry = SubagentRegistry(db_pool, self.agent_repository)
        self.llm_service = AgentLLMService()
        self.workspace_manager = WorkspaceManager()
        self.workspace_lifecycle = WorkspaceLifecycleScheduler(
            self.workspace_manager,
            WorkspaceLifecyclePolicy(
                enabled=os.getenv("AGENT_WORKSPACE_LIFECYCLE_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                interval_seconds=int(os.getenv("AGENT_WORKSPACE_LIFECYCLE_INTERVAL_SECONDS", "3600")),
                dry_run=os.getenv("AGENT_WORKSPACE_LIFECYCLE_DRY_RUN", "false").lower() in {"1", "true", "yes", "on"},
                max_delete_per_cycle=int(os.getenv("AGENT_WORKSPACE_LIFECYCLE_MAX_DELETE", "100")),
                quota_alert_threshold_bytes=int(os.getenv("AGENT_WORKSPACE_LIFECYCLE_ALERT_BYTES", str(500 * 1024 * 1024))),
                quota_alert_threshold_count=int(os.getenv("AGENT_WORKSPACE_LIFECYCLE_ALERT_COUNT", "200")),
                expired_alert_threshold=int(os.getenv("AGENT_WORKSPACE_LIFECYCLE_ALERT_EXPIRED", "20")),
            ),
            alert_callback=self._handle_workspace_lifecycle_alert,
            inspection_callback=self._handle_workspace_lifecycle_inspection,
        )
        self._started = False
        self._workspace_lifecycle_alerts: list[dict[str, Any]] = []
        self._workspace_lifecycle_last_run: dict[str, Any] | None = None
        self._workspace_lifecycle_history: list[dict[str, Any]] = []
        self._browser_session_history: list[dict[str, Any]] = []
        self._evaluation_history: dict[str, list[dict[str, Any]]] = {}
        self.observability_provider = ObservabilityToolProvider.from_env(db_pool=db_pool)
        self.alert_manager = AlertManager(sinks=build_alert_sinks_from_env())
        self.slo_tracker = SLOTracker()
        self.tenant_governance_config = TenantGovernanceConfig.from_env()

        self.tracer = AgentTracer(
            self.run_repository,
            self.tool_call_repository,
            self.state_store,
        )
        self.subagent_handoff = SubagentHandoff(
            self.run_repository,
            self.tracer,
            self.state_store,
            start_run=self.start_run,
            invocation_repository=self.subagent_invocation_repository,
        )
        self.orchestrator = AgentOrchestrator(
            planner=AgentPlanner(),
            executor=AgentExecutor(self.registry),
            summarizer=AgentSummarizer(),
            llm_service=self.llm_service,
            tracer=self.tracer,
            agent_repository=self.agent_repository,
            run_repository=self.run_repository,
            tool_call_repository=self.tool_call_repository,
            state_store=self.state_store,
            skill_registry=self.skill_registry,
            subagent_registry=self.subagent_registry,
            subagent_router=SubagentRouter(),
            subagent_handoff=self.subagent_handoff,
            workspace_manager=self.workspace_manager,
        )

    async def _handle_workspace_lifecycle_alert(self, payload: dict) -> None:
        # Keep lifecycle telemetry in service logs rather than user-visible run streams.
        self._workspace_lifecycle_alerts.append(dict(payload))
        self._workspace_lifecycle_alerts = self._workspace_lifecycle_alerts[-20:]
        alert_type = str(payload.get("type") or "").strip()
        count = int(payload.get("count") or 0)
        metrics = {
            "expired_count": int(payload.get("expired_count") or (count if alert_type == "expired_workspaces" else 0)),
            "quota_exceeded_count": int(payload.get("quota_exceeded_count") or (count if alert_type == "quota_exceeded_workspaces" else 0)),
            "stale_lock_count": int(payload.get("stale_lock_count") or (count if alert_type == "stale_cleanup_locks" else 0)),
            "total_size_bytes": int(payload.get("total_size_bytes") or payload.get("bytes") or 0),
        }
        await self.alert_manager.evaluate("workspace", metrics)
        return None

    async def _handle_workspace_lifecycle_inspection(self, payload: dict) -> None:
        cleanup = payload.get("cleanup") if isinstance(payload.get("cleanup"), dict) else None
        inspection = payload.get("inspection") if isinstance(payload.get("inspection"), dict) else {}
        lock_summary = inspection.get("lock_summary") if isinstance(inspection.get("lock_summary"), dict) else {}
        health = inspection.get("health") if isinstance(inspection.get("health"), dict) else {}
        run_summary = {
            "generated_at": payload.get("generated_at"),
            "inspection": {
                "workspace_count": int(inspection.get("workspace_count") or 0),
                "expired_count": int(inspection.get("expired_count") or 0),
                "quota_exceeded_count": int(inspection.get("quota_exceeded_count") or 0),
                "total_size_bytes": int(inspection.get("total_size_bytes") or 0),
                "total_file_count": int(inspection.get("total_file_count") or 0),
                "health": {
                    "status": health.get("status"),
                    "score": int(health.get("score") or 0),
                    "summary": health.get("summary"),
                    "issues": [dict(issue) for issue in health.get("issues", []) if isinstance(issue, dict)],
                    "recovery_actions": [dict(action) for action in health.get("recovery_actions", []) if isinstance(action, dict)],
                },
                "lock_summary": {
                    "lock_count": int(lock_summary.get("lock_count") or 0),
                    "active_lock_count": int(lock_summary.get("active_lock_count") or 0),
                    "stale_lock_count": int(lock_summary.get("stale_lock_count") or 0),
                    "orphan_lock_count": int(lock_summary.get("orphan_lock_count") or 0),
                    "oldest_lock_age_seconds": lock_summary.get("oldest_lock_age_seconds"),
                    "locks": [dict(item) for item in lock_summary.get("locks", []) if isinstance(item, dict)],
                },
            },
            "cleanup": (
                {
                    "status": cleanup.get("status"),
                    "dry_run": bool(cleanup.get("dry_run")),
                    "candidate_count": int(cleanup.get("candidate_count") or 0),
                    "selected_count": int(cleanup.get("selected_count") or 0),
                    "deleted_count": int(cleanup.get("deleted_count") or 0),
                    "failed_count": int(cleanup.get("failed_count") or 0),
                    "skipped_count": int(cleanup.get("skipped_count") or 0),
                }
                if cleanup is not None
                else None
            ),
            "alerts": [dict(alert) for alert in payload.get("alerts", []) if isinstance(alert, dict)],
        }
        self._workspace_lifecycle_last_run = run_summary
        self._workspace_lifecycle_history.append(deepcopy(run_summary))
        self._workspace_lifecycle_history = self._workspace_lifecycle_history[-12:]
        if cleanup is not None:
            self.slo_tracker.record("workspace_cleanup_success_rate", good=int(cleanup.get("failed_count") or 0) == 0)
        return None

    def _build_workspace_lifecycle_trend(self) -> dict[str, Any]:
        history = self._workspace_lifecycle_history[-12:]
        if not history:
            return {
                "status": "insufficient_data",
                "window_size": 0,
                "summary": "workspace lifecycle trend has no completed inspections",
                "delta": {},
            }

        first = history[0].get("inspection", {}) if isinstance(history[0].get("inspection"), dict) else {}
        last = history[-1].get("inspection", {}) if isinstance(history[-1].get("inspection"), dict) else {}
        first_health = first.get("health") if isinstance(first.get("health"), dict) else {}
        last_health = last.get("health") if isinstance(last.get("health"), dict) else {}
        first_locks = first.get("lock_summary") if isinstance(first.get("lock_summary"), dict) else {}
        last_locks = last.get("lock_summary") if isinstance(last.get("lock_summary"), dict) else {}

        def _delta(key: str) -> int:
            return int(last.get(key) or 0) - int(first.get(key) or 0)

        delta = {
            "workspace_count": _delta("workspace_count"),
            "expired_count": _delta("expired_count"),
            "quota_exceeded_count": _delta("quota_exceeded_count"),
            "total_size_bytes": _delta("total_size_bytes"),
            "total_file_count": _delta("total_file_count"),
            "health_score": int(last_health.get("score") or 0) - int(first_health.get("score") or 0),
            "stale_lock_count": int(last_locks.get("stale_lock_count") or 0) - int(first_locks.get("stale_lock_count") or 0),
            "orphan_lock_count": int(last_locks.get("orphan_lock_count") or 0) - int(first_locks.get("orphan_lock_count") or 0),
        }

        risk_deltas = [
            delta["expired_count"],
            delta["quota_exceeded_count"],
            delta["stale_lock_count"],
            delta["orphan_lock_count"],
        ]
        if len(history) == 1:
            status = "baseline"
            summary = "workspace lifecycle trend baseline captured"
        elif any(value > 0 for value in risk_deltas) or delta["health_score"] < 0:
            status = "worsening"
            summary = "workspace lifecycle risk is increasing"
        elif any(value < 0 for value in risk_deltas) or delta["health_score"] > 0:
            status = "improving"
            summary = "workspace lifecycle risk is decreasing"
        else:
            status = "stable"
            summary = "workspace lifecycle trend is stable"

        return {
            "status": status,
            "window_size": len(history),
            "first_generated_at": history[0].get("generated_at"),
            "last_generated_at": history[-1].get("generated_at"),
            "summary": summary,
            "delta": delta,
        }

    def _build_browser_session_health(self, session_summary: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(session_summary, dict):
            return {
                "status": "unknown",
                "score": 0,
                "summary": "browser session telemetry is unavailable",
                "issues": [],
                "recovery_actions": [],
            }

        session_count = int(session_summary.get("session_count") or 0)
        expired_session_count = int(session_summary.get("expired_session_count") or 0)
        session_ttl_seconds = int(session_summary.get("session_ttl_seconds") or 0)
        oldest_session_age_seconds = session_summary.get("oldest_session_age_seconds")
        oldest_age = int(oldest_session_age_seconds or 0)
        sessions = [item for item in session_summary.get("sessions", []) if isinstance(item, dict)]
        console_message_count = sum(int(item.get("console_message_count") or 0) for item in sessions)
        network_error_count = sum(int(item.get("network_error_count") or 0) for item in sessions)

        issues: list[dict[str, Any]] = []
        if expired_session_count > 0:
            issues.append(
                {
                    "code": "expired_browser_sessions",
                    "severity": "warning" if expired_session_count < 3 else "critical",
                    "count": expired_session_count,
                    "message": "Browser sessions have exceeded their TTL",
                }
            )
        if session_ttl_seconds > 0 and oldest_age >= session_ttl_seconds:
            issues.append(
                {
                    "code": "stale_browser_session_age",
                    "severity": "warning",
                    "age_seconds": oldest_age,
                    "threshold_seconds": session_ttl_seconds,
                    "message": "Oldest browser session has reached the TTL",
                }
            )
        if network_error_count > 0:
            issues.append(
                {
                    "code": "browser_network_errors",
                    "severity": "warning" if network_error_count < 10 else "critical",
                    "count": network_error_count,
                    "message": "Browser sessions recorded network failures",
                }
            )
        if console_message_count >= 20:
            issues.append(
                {
                    "code": "browser_console_noise",
                    "severity": "warning",
                    "count": console_message_count,
                    "message": "Browser sessions recorded many console messages",
                }
            )

        if not issues:
            status = "healthy"
        elif any(issue["severity"] == "critical" for issue in issues):
            status = "critical"
        else:
            status = "warning"

        score = 100
        score -= min(35, expired_session_count * 12)
        score -= min(25, network_error_count * 3)
        score -= min(10, console_message_count // 5)
        if session_ttl_seconds > 0 and oldest_age >= session_ttl_seconds:
            score -= 15
        score = max(0, min(100, score))

        if not issues:
            summary = "browser sessions are healthy" if session_count else "no active browser sessions"
        else:
            summary = "browser sessions need attention: " + ", ".join(
                f"{issue['code']}={issue.get('count', issue.get('age_seconds', 0))}"
                for issue in issues[:3]
            )

        recovery_actions: list[dict[str, Any]] = []
        if expired_session_count > 0 or (session_ttl_seconds > 0 and oldest_age >= session_ttl_seconds):
            recovery_actions.append(
                {
                    "key": "close_stale_browser_sessions",
                    "label": "关闭陈旧 Browser 会话",
                    "category": "browser_session_cleanup",
                    "priority": "medium",
                    "requires_confirmation": False,
                    "tenant_scoped": False,
                }
            )
        if network_error_count > 0:
            recovery_actions.append(
                {
                    "key": "inspect_browser_network_errors",
                    "label": "检查 Browser 网络错误",
                    "category": "browser_diagnostics",
                    "priority": "medium",
                    "requires_confirmation": False,
                    "tenant_scoped": False,
                }
            )

        return {
            "status": status,
            "score": score,
            "summary": summary,
            "issues": issues,
            "recovery_actions": recovery_actions,
        }

    def _build_browser_session_alerts(self, session_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(session_summary, dict):
            return []
        alerts: list[dict[str, Any]] = []
        expired_count = int(session_summary.get("expired_session_count") or 0)
        if expired_count > 0:
            alerts.append(
                {
                    "type": "expired_browser_sessions",
                    "severity": "warning" if expired_count < 3 else "critical",
                    "count": expired_count,
                    "threshold": 0,
                }
            )
        sessions = [item for item in session_summary.get("sessions", []) if isinstance(item, dict)]
        network_error_count = sum(int(item.get("network_error_count") or 0) for item in sessions)
        if network_error_count > 0:
            alerts.append(
                {
                    "type": "browser_network_errors",
                    "severity": "warning" if network_error_count < 10 else "critical",
                    "count": network_error_count,
                    "threshold": 0,
                }
            )
        return alerts

    def _build_browser_session_trend(self) -> dict[str, Any]:
        history = self._browser_session_history[-12:]
        if not history:
            return {
                "status": "insufficient_data",
                "window_size": 0,
                "summary": "browser session trend has no samples",
                "delta": {},
            }

        first = history[0]
        last = history[-1]
        first_health = first.get("health") if isinstance(first.get("health"), dict) else {}
        last_health = last.get("health") if isinstance(last.get("health"), dict) else {}

        def _delta(key: str) -> int:
            return int(last.get(key) or 0) - int(first.get(key) or 0)

        delta = {
            "session_count": _delta("session_count"),
            "active_session_count": _delta("active_session_count"),
            "expired_session_count": _delta("expired_session_count"),
            "network_error_count": _delta("network_error_count"),
            "console_message_count": _delta("console_message_count"),
            "health_score": int(last_health.get("score") or 0) - int(first_health.get("score") or 0),
        }
        risk_deltas = [delta["expired_session_count"], delta["network_error_count"]]
        if len(history) == 1:
            status = "baseline"
            summary = "browser session trend baseline captured"
        elif any(value > 0 for value in risk_deltas) or delta["health_score"] < 0:
            status = "worsening"
            summary = "browser session risk is increasing"
        elif any(value < 0 for value in risk_deltas) or delta["health_score"] > 0:
            status = "improving"
            summary = "browser session risk is decreasing"
        else:
            status = "stable"
            summary = "browser session trend is stable"
        return {
            "status": status,
            "window_size": len(history),
            "first_sampled_at": history[0].get("sampled_at"),
            "last_sampled_at": history[-1].get("sampled_at"),
            "summary": summary,
            "delta": delta,
        }

    def _enrich_browser_session_summary(self, session_summary: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(session_summary, dict):
            return None
        enriched = deepcopy(session_summary)
        sessions = [item for item in enriched.get("sessions", []) if isinstance(item, dict)]
        network_error_count = sum(int(item.get("network_error_count") or 0) for item in sessions)
        console_message_count = sum(int(item.get("console_message_count") or 0) for item in sessions)
        enriched["network_error_count"] = network_error_count
        enriched["console_message_count"] = console_message_count
        enriched["health"] = self._build_browser_session_health(enriched)
        enriched["alerts"] = self._build_browser_session_alerts(enriched)
        sample = {
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "session_count": int(enriched.get("session_count") or 0),
            "active_session_count": int(enriched.get("active_session_count") or 0),
            "expired_session_count": int(enriched.get("expired_session_count") or 0),
            "network_error_count": network_error_count,
            "console_message_count": console_message_count,
            "health": {
                "status": enriched["health"].get("status"),
                "score": int(enriched["health"].get("score") or 0),
            },
        }
        self._browser_session_history.append(sample)
        self._browser_session_history = self._browser_session_history[-12:]
        enriched["history"] = deepcopy(self._browser_session_history[-12:])
        enriched["trend"] = self._build_browser_session_trend()
        return enriched

    async def evaluate_runtime_health(self, status: dict[str, Any] | None = None) -> dict[str, Any]:
        status = status or self.runtime_status()
        providers = status.get("providers") if isinstance(status.get("providers"), dict) else {}
        workspace = providers.get("workspace") if isinstance(providers.get("workspace"), dict) else {}
        workspace_inspection = workspace.get("inspection") if isinstance(workspace.get("inspection"), dict) else {}
        workspace_locks = (
            workspace_inspection.get("lock_summary")
            if isinstance(workspace_inspection.get("lock_summary"), dict)
            else {}
        )
        sandbox = providers.get("sandbox") if isinstance(providers.get("sandbox"), dict) else {}
        sandbox_isolation = sandbox.get("isolation") if isinstance(sandbox.get("isolation"), dict) else {}
        web = providers.get("web") if isinstance(providers.get("web"), dict) else {}
        browser_sessions = web.get("browser_sessions") if isinstance(web.get("browser_sessions"), dict) else {}
        observability = providers.get("observability") if isinstance(providers.get("observability"), dict) else {}

        fired = []
        fired.extend(await self.alert_manager.evaluate("workspace", {
            "expired_count": int(workspace_inspection.get("expired_count") or 0),
            "quota_exceeded_count": int(workspace_inspection.get("quota_exceeded_count") or 0),
            "stale_lock_count": int(workspace_locks.get("stale_lock_count") or 0),
            "total_size_bytes": int(workspace_inspection.get("total_size_bytes") or 0),
        }))
        fired.extend(await self.alert_manager.evaluate("sandbox", {
            "isolation_status": sandbox_isolation.get("status") or "unknown",
            "active_session_count": int(sandbox.get("active_session_count") or 0),
        }))
        browser_session_count = int(browser_sessions.get("session_count") or 0)
        browser_network_errors = int(browser_sessions.get("network_error_count") or 0)
        fired.extend(await self.alert_manager.evaluate("browser", {
            "active_session_count": int(browser_sessions.get("active_session_count") or browser_session_count),
            "network_error_rate": (browser_network_errors / browser_session_count) if browser_session_count else 0,
        }))
        fired.extend(await self.alert_manager.evaluate("web", {
            "timeout_rate": float(web.get("timeout_rate") or 0),
        }))
        fired.extend(await self.alert_manager.evaluate("observability", {
            "db_configured": bool(observability.get("db_configured")),
            "db_reachable": bool(observability.get("db_reachable", observability.get("db_configured"))),
            "redis_configured": bool(observability.get("redis_configured")),
            "redis_reachable": bool(observability.get("redis_reachable", observability.get("redis_configured"))),
        }))
        return {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "fired": [alert.snapshot() for alert in fired],
            "alerts": self.alert_manager.snapshot(),
            "slo": self.slo_tracker.snapshot(),
            "runbooks": get_all_runbook_entries(),
            "monitoring": monitoring_export_status(),
        }

    async def tenant_governance_status(self, tenant_id: str) -> dict[str, Any]:
        run_usage, tool_usage, subagent_usage = await fetch_tenant_runtime_usage(
            self.run_repository.db_pool,
            tenant_id=tenant_id,
            window_hours=self.tenant_governance_config.window_hours,
        )
        workspace_inspection = self.workspace_manager.inspect_workspaces()
        workspaces = [
            item
            for item in workspace_inspection.get("workspaces", [])
            if str(item.get("tenant_id") or "") == tenant_id
        ]
        workspace_usage = {
            "workspace_count": len(workspaces),
            "expired_count": sum(1 for item in workspaces if item.get("expired")),
            "quota_exceeded_count": sum(1 for item in workspaces if item.get("quota_exceeded")),
            "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in workspaces),
            "total_file_count": sum(int(item.get("file_count") or 0) for item in workspaces),
        }
        return build_tenant_governance_snapshot(
            tenant_id=tenant_id,
            config=self.tenant_governance_config,
            run_usage=run_usage,
            tool_usage=tool_usage,
            subagent_usage=subagent_usage,
            workspace_usage=workspace_usage,
        )

    async def ops_status(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        tenant_governance = await self.tenant_governance_status(tenant_id) if tenant_id else None
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "alerts": self.alert_manager.snapshot(),
            "slo": self.slo_tracker.snapshot(),
            "runbooks": get_all_runbook_entries(),
            "monitoring": monitoring_export_status(),
            "tenant_governance": tenant_governance,
            "subsystems": {
                subsystem: {
                    "slo": self.slo_tracker.subsystem_snapshot(subsystem),
                    "runbooks": get_runbook_entries(subsystem),
                }
                for subsystem in ("workspace", "sandbox", "web", "browser", "observability")
            },
        }

    def ops_prometheus_metrics(self) -> str:
        return export_ops_prometheus_metrics(
            alert_manager=self.alert_manager,
            slo_tracker=self.slo_tracker,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def ops_grafana_dashboard(self) -> dict[str, Any]:
        datasource_uid = os.getenv("AGENT_GRAFANA_DATASOURCE_UID", "${DS_PROMETHEUS}").strip() or "${DS_PROMETHEUS}"
        return build_grafana_dashboard(datasource_uid=datasource_uid)

    def evaluate_production_readiness(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        return evaluate_production_readiness(self.runtime_status(), evidence=evidence or {})

    def runtime_status(self) -> dict[str, Any]:
        workspace_inspection = self.workspace_manager.inspect_workspaces()
        lifecycle_policy = self.workspace_lifecycle.policy
        browser_runtime_available = False
        browser_runtime_reason = "browser runtime is not configured"
        try:
            from ai_runtime.core.agent_runtime.tools.providers.web import _browser_runtime_status

            browser_runtime_available, browser_runtime_reason = _browser_runtime_status()
        except Exception as exc:  # pragma: no cover - defensive, runtime status must stay available
            browser_runtime_reason = str(exc)

        provider_names = sorted(self.registry.provider_names)
        provider_name_set = set(provider_names)
        sandbox_provider = SandboxExecToolProvider.from_env()
        sandbox_profile = build_sandbox_isolation_profile(sandbox_provider.policy)
        web_provider = self.registry.get_provider("web")
        observability_provider = self.registry.get_provider("observability")
        web_session_summary = None
        if web_provider is not None and hasattr(web_provider, "browser_session_snapshot"):
            try:
                web_session_summary = web_provider.browser_session_snapshot()
            except Exception:
                web_session_summary = None
        web_session_summary = self._enrich_browser_session_summary(web_session_summary)
        observability_summary = (
            observability_provider.status_summary(enabled=True)
            if observability_provider is not None and hasattr(observability_provider, "status_summary")
            else self.observability_provider.status_summary(enabled=False)
        )
        status = {
            "status": "ready" if self._started else "idle",
            "started": self._started,
            "providers": {
                "configured": provider_names,
                "workspace": {
                    "enabled": self.workspace_manager.config.enabled,
                    "base_root": str(self.workspace_manager.config.base_root),
                    "source_roots": [str(path) for path in self.workspace_manager.config.source_roots],
                    "max_files": self.workspace_manager.config.max_files,
                    "max_bytes": self.workspace_manager.config.max_bytes,
                    "retention_hours": self.workspace_manager.config.retention_hours,
                    "inspection": workspace_inspection,
                    "binding_policies": self.workspace_manager.list_available_sources(max_entries=1, max_depth=0).get("binding_policies", {}),
                },
                "sandbox": {
                    "enabled": "sandbox-exec" in provider_name_set,
                    "configured": os.getenv("AGENT_SANDBOX_EXEC_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                    "runner_configured": sandbox_provider.policy.runner_configured,
                    "runner_backend": sandbox_provider.policy.runner_backend,
                    "docker_image": sandbox_provider.policy.docker_image,
                    "network_mode": sandbox_provider.policy.docker_network,
                    "limits": sandbox_profile["limits"],
                    "isolation": {
                        "status": sandbox_profile["status"],
                        "production_ready": sandbox_profile["production_ready"],
                        "passed": sandbox_profile["passed"],
                        "failed": sandbox_profile["failed"],
                        "warning": sandbox_profile["warning"],
                        "checks": sandbox_profile["checks"],
                        "recovery_actions": sandbox_profile["recovery_actions"],
                    },
                },
                "web": {
                    "enabled": "web" in provider_name_set,
                    "configured": os.getenv("AGENT_WEB_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                    "network_configured": os.getenv("AGENT_WEB_NETWORK_CONFIGURED", "false").lower() in {"1", "true", "yes", "on"},
                    "allowed_domains": [
                        item.strip()
                        for item in os.getenv("AGENT_WEB_ALLOWED_DOMAINS", "").split(",")
                        if item.strip()
                    ],
                    "denied_domains": [
                        item.strip()
                        for item in os.getenv("AGENT_WEB_DENIED_DOMAINS", "").split(",")
                        if item.strip()
                    ],
                    "search_endpoint": os.getenv("AGENT_WEB_SEARCH_ENDPOINT", "").strip() or None,
                    "search_quality": {
                        "require_url": os.getenv("AGENT_WEB_SEARCH_REQUIRE_URL", "true").lower() in {"1", "true", "yes", "on"},
                        "require_title": os.getenv("AGENT_WEB_SEARCH_REQUIRE_TITLE", "true").lower() in {"1", "true", "yes", "on"},
                        "require_snippet": os.getenv("AGENT_WEB_SEARCH_REQUIRE_SNIPPET", "false").lower() in {"1", "true", "yes", "on"},
                        "allowed_schemes": [
                            item.strip().lower()
                            for item in os.getenv("AGENT_WEB_SEARCH_ALLOWED_SCHEMES", "https").split(",")
                            if item.strip()
                        ],
                        "reject_disallowed_domains": os.getenv("AGENT_WEB_SEARCH_REJECT_DISALLOWED_DOMAINS", "true").lower() in {"1", "true", "yes", "on"},
                        "reject_duplicates": os.getenv("AGENT_WEB_SEARCH_REJECT_DUPLICATES", "true").lower() in {"1", "true", "yes", "on"},
                        "evaluation": evaluate_default_web_search_quality_suite([]),
                        "evaluation_protocol_version": "managed-web.search-quality-suite.v1",
                    },
                    "browser_sessions": web_session_summary,
                },
                "browser": {
                    "enabled": os.getenv("AGENT_BROWSER_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                    "configured": os.getenv("AGENT_BROWSER_CONFIGURED", "false").lower() in {"1", "true", "yes", "on"},
                    "backend": os.getenv("AGENT_BROWSER_BACKEND", "playwright"),
                    "name": os.getenv("AGENT_BROWSER_NAME", "chromium"),
                    "runtime_available": browser_runtime_available,
                    "runtime_reason": browser_runtime_reason,
                    "session_ttl_seconds": int(os.getenv("AGENT_BROWSER_SESSION_TTL_SECONDS", "900")),
                },
                "observability": observability_summary,
            },
            "workspace_lifecycle": {
                "enabled": lifecycle_policy.enabled,
                "running": self.workspace_lifecycle.running,
                "interval_seconds": lifecycle_policy.interval_seconds,
                "dry_run": lifecycle_policy.dry_run,
                "max_delete_per_cycle": lifecycle_policy.max_delete_per_cycle,
                "quota_alert_threshold_bytes": lifecycle_policy.quota_alert_threshold_bytes,
                "quota_alert_threshold_count": lifecycle_policy.quota_alert_threshold_count,
                "expired_alert_threshold": lifecycle_policy.expired_alert_threshold,
                "last_run_at_monotonic": self.workspace_lifecycle.last_run_at,
                "last_completed_at": self.workspace_lifecycle.last_completed_at,
                "last_run": deepcopy(self._workspace_lifecycle_last_run),
                "history": deepcopy(self._workspace_lifecycle_history[-12:]),
                "trend": self._build_workspace_lifecycle_trend(),
                "recent_alerts": deepcopy(self._workspace_lifecycle_alerts[-5:]),
                "recovery_actions": deepcopy(
                    self._workspace_lifecycle_last_run.get("inspection", {}).get("health", {}).get("recovery_actions", [])
                    if self._workspace_lifecycle_last_run
                    else []
                ),
            },
        }
        status["ops"] = {
            "alerts": self.alert_manager.status_summary(),
            "slo": self.slo_tracker.snapshot(),
        }
        return status

    async def _persist_evaluation_record(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        evaluation_type: str,
        suite_name: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        summary = {
            "status": result.get("status"),
            "total": int(result.get("total") or 0),
            "passed": int(result.get("passed") or 0),
            "warning": int(result.get("warning") or 0),
            "failed": int(result.get("failed") or 0),
            "average_score": float(result.get("average_score") or result.get("averageScore") or 0),
            "summary": result.get("summary") or "",
        }
        if result.get("readiness"):
            summary["readiness"] = result.get("readiness")
        if isinstance(result.get("blocking_checks"), list):
            summary["blocking_check_count"] = len(result.get("blocking_checks") or [])
        evidence_quality = (
            result.get("evidence_summary", {}).get("quality")
            if isinstance(result.get("evidence_summary"), dict)
            else None
        )
        if isinstance(evidence_quality, dict):
            summary["evidence_quality_score"] = float(evidence_quality.get("average_quality_score") or 0)
            summary["evidence_quality_failed_count"] = int(evidence_quality.get("quality_failed_count") or 0)
        record = {
            "tenant_id": tenant_id,
            "evaluation_type": evaluation_type,
            "suite_name": suite_name,
            "status": str(result.get("status") or "unknown"),
            "actor_user_id": user_id,
            "summary": summary,
            "payload": result,
            "metadata": {"source": "agent_runtime"},
        }
        try:
            stored = await self.evaluation_repository.create_evaluation(record)
        except Exception:
            stored = {
                "id": "",
                "tenant_id": tenant_id,
                "evaluation_type": evaluation_type,
                "suite_name": suite_name,
                "status": summary["status"],
                "actor_user_id": user_id,
                "summary": summary,
                "payload": result,
                "metadata": {"source": "agent_runtime", "storage": "memory_fallback"},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        bucket = self._evaluation_history.setdefault(evaluation_type, [])
        bucket.insert(0, stored)
        self._evaluation_history[evaluation_type] = bucket[:10]
        return stored

    def _summarize_evaluation_record(self, record: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        comparison = self._build_evaluation_comparison(summary=summary, payload=payload)
        if not comparison:
            return {}
        return {
            "evaluation_type": record.get("evaluation_type"),
            "suite_name": record.get("suite_name"),
            "status": record.get("status") or summary.get("status") or "unknown",
            "created_at": record.get("created_at"),
            "comparison": comparison,
        }

    def _build_evaluation_comparison(self, *, summary: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        def _number(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _int(value: Any) -> int:
            return int(_number(value))

        current_score = _number(summary.get("average_score") or summary.get("averageScore") or payload.get("average_score") or payload.get("averageScore") or 0)
        current_status = str(summary.get("status") or payload.get("status") or "unknown")
        current_total = _int(summary.get("total") or payload.get("total") or 0)
        current_passed = _int(summary.get("passed") or payload.get("passed") or 0)
        current_warning = _int(summary.get("warning") or payload.get("warning") or 0)
        current_failed = _int(summary.get("failed") or payload.get("failed") or 0)
        comparison = {
            "current_score": round(current_score, 4),
            "current_status": current_status,
            "current_total": current_total,
            "current_passed": current_passed,
            "current_warning": current_warning,
            "current_failed": current_failed,
            "pass_ratio": round((current_passed / current_total), 4) if current_total else 1.0,
        }
        optional_metrics = {
            "total_results": _int(payload.get("total_results")),
            "accepted_count": _int(payload.get("accepted_count")),
            "rejected_count": _int(payload.get("rejected_count")),
            "check_count": _int(payload.get("check_count")),
            "passed_check_count": _int(payload.get("passed_check_count")),
            "failed_check_count": _int(payload.get("failed_check_count")),
            "false_positive_count": _int(payload.get("false_positive_count")),
            "false_negative_count": _int(payload.get("false_negative_count")),
            "blocking_check_count": _int(summary.get("blocking_check_count") or len(payload.get("blocking_checks") or [])),
            "evidence_quality_failed_count": _int(summary.get("evidence_quality_failed_count")),
        }
        if optional_metrics["total_results"] > 0:
            comparison["accepted_ratio"] = round(optional_metrics["accepted_count"] / optional_metrics["total_results"], 4)
        if optional_metrics["check_count"] > 0:
            comparison["check_pass_ratio"] = round(optional_metrics["passed_check_count"] / optional_metrics["check_count"], 4)
        for key, value in optional_metrics.items():
            if value > 0 or key in {"false_positive_count", "false_negative_count"}:
                comparison[key] = value
        readiness = str(summary.get("readiness") or payload.get("readiness") or "").strip()
        if readiness:
            comparison["readiness"] = readiness
        evidence_quality_score = _number(summary.get("evidence_quality_score"))
        payload_evidence_summary = payload.get("evidence_summary") if isinstance(payload.get("evidence_summary"), dict) else {}
        if evidence_quality_score or isinstance(payload_evidence_summary.get("quality"), dict):
            comparison["evidence_quality_score"] = round(evidence_quality_score, 4)

        summary_text = str(summary.get("summary") or payload.get("summary") or "").strip()
        if summary_text:
            comparison["summary"] = summary_text
        return comparison

    def _describe_evaluation_comparison_delta(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> str:
        if not current:
            return ""

        score_delta = round(float(current.get("current_score") or 0) - float(previous.get("current_score") or 0), 4) if previous else 0.0
        passed_delta = int(current.get("current_passed") or 0) - int(previous.get("current_passed") or 0) if previous else 0
        failed_delta = int(current.get("current_failed") or 0) - int(previous.get("current_failed") or 0) if previous else 0
        warning_delta = int(current.get("current_warning") or 0) - int(previous.get("current_warning") or 0) if previous else 0

        parts: list[str] = []
        if not previous:
            parts.append("baseline captured")
        else:
            if score_delta > 0:
                parts.append(f"score improved by +{score_delta:.2f}")
            elif score_delta < 0:
                parts.append(f"score regressed by {score_delta:.2f}")
            else:
                parts.append("score unchanged")

            if failed_delta < 0:
                parts.append(f"{abs(failed_delta)} fewer failed cases")
            elif failed_delta > 0:
                parts.append(f"{failed_delta} more failed cases")

            if warning_delta < 0:
                parts.append(f"{abs(warning_delta)} fewer warnings")
            elif warning_delta > 0:
                parts.append(f"{warning_delta} more warnings")

            if passed_delta > 0:
                parts.append(f"{passed_delta} more passed cases")
            elif passed_delta < 0:
                parts.append(f"{abs(passed_delta)} fewer passed cases")

            accepted_ratio_delta = round(
                float(current.get("accepted_ratio") or 0) - float(previous.get("accepted_ratio") or 0),
                4,
            ) if previous and ("accepted_ratio" in current or "accepted_ratio" in previous) else 0.0
            if accepted_ratio_delta > 0:
                parts.append(f"accepted ratio +{accepted_ratio_delta:.2f}")
            elif accepted_ratio_delta < 0:
                parts.append(f"accepted ratio {accepted_ratio_delta:.2f}")

            false_negative_delta = int(current.get("false_negative_count") or 0) - int(previous.get("false_negative_count") or 0) if previous else 0
            if false_negative_delta < 0:
                parts.append(f"{abs(false_negative_delta)} fewer false negatives")
            elif false_negative_delta > 0:
                parts.append(f"{false_negative_delta} more false negatives")

            blocker_delta = int(current.get("blocking_check_count") or 0) - int(previous.get("blocking_check_count") or 0) if previous else 0
            if blocker_delta < 0:
                parts.append(f"{abs(blocker_delta)} fewer readiness blockers")
            elif blocker_delta > 0:
                parts.append(f"{blocker_delta} more readiness blockers")

            quality_delta = round(
                float(current.get("evidence_quality_score") or 0) - float(previous.get("evidence_quality_score") or 0),
                4,
            ) if previous and ("evidence_quality_score" in current or "evidence_quality_score" in previous) else 0.0
            if quality_delta > 0:
                parts.append(f"evidence quality +{quality_delta:.2f}")
            elif quality_delta < 0:
                parts.append(f"evidence quality {quality_delta:.2f}")

        return " · ".join(parts)

    def _build_evaluation_delta(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> dict[str, Any]:
        if not current:
            return {}
        if not previous:
            return {
                "score": 0.0,
                "passed": 0,
                "warning": 0,
                "failed": 0,
                "total": 0,
                "pass_ratio": 0.0,
                "accepted_ratio": 0.0,
                "check_pass_ratio": 0.0,
                "false_positive_count": 0,
                "false_negative_count": 0,
                "blocking_check_count": 0,
                "evidence_quality_score": 0.0,
                "evidence_quality_failed_count": 0,
            }
        return {
            "score": round(float(current.get("current_score") or 0) - float(previous.get("current_score") or 0), 4),
            "passed": int(current.get("current_passed") or 0) - int(previous.get("current_passed") or 0),
            "warning": int(current.get("current_warning") or 0) - int(previous.get("current_warning") or 0),
            "failed": int(current.get("current_failed") or 0) - int(previous.get("current_failed") or 0),
            "total": int(current.get("current_total") or 0) - int(previous.get("current_total") or 0),
            "pass_ratio": round(float(current.get("pass_ratio") or 0) - float(previous.get("pass_ratio") or 0), 4),
            "accepted_ratio": round(
                float(current.get("accepted_ratio") or 0) - float(previous.get("accepted_ratio") or 0),
                4,
            ) if ("accepted_ratio" in current or "accepted_ratio" in previous) else 0.0,
            "check_pass_ratio": round(
                float(current.get("check_pass_ratio") or 0) - float(previous.get("check_pass_ratio") or 0),
                4,
            ) if ("check_pass_ratio" in current or "check_pass_ratio" in previous) else 0.0,
            "false_positive_count": int(current.get("false_positive_count") or 0) - int(previous.get("false_positive_count") or 0),
            "false_negative_count": int(current.get("false_negative_count") or 0) - int(previous.get("false_negative_count") or 0),
            "blocking_check_count": int(current.get("blocking_check_count") or 0) - int(previous.get("blocking_check_count") or 0),
            "evidence_quality_score": round(
                float(current.get("evidence_quality_score") or 0) - float(previous.get("evidence_quality_score") or 0),
                4,
            ) if ("evidence_quality_score" in current or "evidence_quality_score" in previous) else 0.0,
            "evidence_quality_failed_count": int(current.get("evidence_quality_failed_count") or 0) - int(previous.get("evidence_quality_failed_count") or 0),
        }

    def _build_evaluation_trend(
        self,
        summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        entries = [item for item in summaries if isinstance(item, dict) and isinstance(item.get("comparison"), dict)]
        if not entries:
            return {}

        def _score(entry: dict[str, Any]) -> float:
            return float(entry.get("comparison", {}).get("current_score") or 0)

        def _pass_ratio(entry: dict[str, Any]) -> float:
            return float(entry.get("comparison", {}).get("pass_ratio") or 0)

        current = entries[0].get("comparison", {})
        baseline = entries[-1].get("comparison", {})
        best_entry = max(entries, key=lambda item: (_score(item), _pass_ratio(item)))
        worst_entry = min(entries, key=lambda item: (_score(item), _pass_ratio(item)))

        score_values = [_score(item) for item in entries]
        pass_ratio_values = [_pass_ratio(item) for item in entries]
        accepted_ratio_values = [
            float(item.get("comparison", {}).get("accepted_ratio"))
            for item in entries
            if "accepted_ratio" in item.get("comparison", {})
        ]
        check_pass_ratio_values = [
            float(item.get("comparison", {}).get("check_pass_ratio"))
            for item in entries
            if "check_pass_ratio" in item.get("comparison", {})
        ]
        evidence_quality_values = [
            float(item.get("comparison", {}).get("evidence_quality_score"))
            for item in entries
            if "evidence_quality_score" in item.get("comparison", {})
        ]
        delta_from_baseline = self._build_evaluation_delta(current, baseline)
        delta_from_best = self._build_evaluation_delta(current, best_entry.get("comparison", {}))

        score_delta = float(delta_from_baseline.get("score") or 0)
        pass_ratio_delta = float(delta_from_baseline.get("pass_ratio") or 0)
        if score_delta > 0.02 or pass_ratio_delta > 0.02:
            direction = "improving"
        elif score_delta < -0.02 or pass_ratio_delta < -0.02:
            direction = "regressing"
        else:
            direction = "flat"

        status_counts = {
            "passed": sum(1 for item in entries if item.get("status") == "passed"),
            "warning": sum(1 for item in entries if item.get("status") == "warning"),
            "failed": sum(1 for item in entries if item.get("status") == "failed"),
        }

        parts = [f"recent {len(entries)}-run trend {direction}", f"avg score {sum(score_values) / len(score_values):.2f}"]
        parts.append(f"best {float(best_entry.get('comparison', {}).get('current_score') or 0):.2f}")
        if len(entries) > 1 and score_delta != 0:
            parts.append(f"vs oldest {score_delta:+.2f}")
        if len(entries) > 1 and pass_ratio_delta != 0:
            parts.append(f"pass ratio {pass_ratio_delta:+.2f} vs oldest")

        trend = {
            "window_size": len(entries),
            "direction": direction,
            "status_counts": status_counts,
            "average_score": round(sum(score_values) / len(score_values), 4),
            "average_pass_ratio": round(sum(pass_ratio_values) / len(pass_ratio_values), 4),
            "best_score": round(float(best_entry.get("comparison", {}).get("current_score") or 0), 4),
            "best_pass_ratio": round(float(best_entry.get("comparison", {}).get("pass_ratio") or 0), 4),
            "best_created_at": best_entry.get("created_at"),
            "worst_score": round(float(worst_entry.get("comparison", {}).get("current_score") or 0), 4),
            "worst_pass_ratio": round(float(worst_entry.get("comparison", {}).get("pass_ratio") or 0), 4),
            "worst_created_at": worst_entry.get("created_at"),
            "delta_from_baseline": delta_from_baseline,
            "delta_from_best": delta_from_best,
            "latest_created_at": entries[0].get("created_at"),
            "baseline_created_at": entries[-1].get("created_at"),
            "summary": " · ".join(parts),
        }
        if accepted_ratio_values:
            trend["average_accepted_ratio"] = round(sum(accepted_ratio_values) / len(accepted_ratio_values), 4)
        if check_pass_ratio_values:
            trend["average_check_pass_ratio"] = round(sum(check_pass_ratio_values) / len(check_pass_ratio_values), 4)
        if evidence_quality_values:
            trend["average_evidence_quality_score"] = round(sum(evidence_quality_values) / len(evidence_quality_values), 4)
        return trend

    async def list_evaluation_history(
        self,
        *,
        tenant_id: str,
        evaluation_type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        try:
            records = await self.evaluation_repository.list_evaluations(
                tenant_id=tenant_id,
                evaluation_type=evaluation_type,
                limit=limit,
            )
        except Exception:
            if evaluation_type:
                records = list(self._evaluation_history.get(evaluation_type, []))[:limit]
            else:
                merged: list[dict[str, Any]] = []
                for items in self._evaluation_history.values():
                    merged.extend(items)
                records = sorted(
                    merged,
                    key=lambda item: str(item.get("created_at") or ""),
                    reverse=True,
                )[:limit]
        summaries = [self._summarize_evaluation_record(record) for record in records]
        latest = records[0] if records else None
        previous = records[1] if len(records) > 1 else None
        latest_summary = summaries[0] if summaries else {}
        previous_summary = summaries[1] if len(summaries) > 1 else {}
        trend = self._build_evaluation_trend(summaries)
        comparison = {}
        if latest_summary:
            comparison = {
                "current": latest_summary.get("comparison", {}),
                "previous": previous_summary.get("comparison", {}),
                "delta": {},
                "trend": trend,
                "window": {
                    "count": len(records),
                    "latest_created_at": latest_summary.get("created_at"),
                    "previous_created_at": previous_summary.get("created_at"),
                    "oldest_created_at": summaries[-1].get("created_at") if summaries else None,
                },
            }
            current = comparison["current"] or {}
            prior = comparison["previous"] or {}
            comparison["delta"] = self._build_evaluation_delta(current, prior)
            comparison["summary"] = self._describe_evaluation_comparison_delta(current, prior)
        return {
            "status": "completed",
            "evaluation_type": evaluation_type,
            "count": len(records),
            "history": records,
            "history_summary": {
                **latest_summary,
                "trend": trend,
            } if latest_summary else {},
            "history_comparison": comparison,
        }

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self.workspace_lifecycle.start()

    async def shutdown(self) -> None:
        await self.workspace_lifecycle.stop()
        await self.mcp_registry.close()
        await self.state_store.close_all()
        self._started = False

    def _hydrate_upload_context(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        run_input: dict | None,
    ) -> dict:
        payload = dict(run_input or {})
        bundle_ids = normalize_bundle_ids(payload.get("upload_bundle_ids"))
        if not bundle_ids:
            payload.pop("uploaded_attachments", None)
            payload.pop("uploaded_attachments_manifest", None)
            return payload

        query = str(payload.get("message") or payload.get("prompt") or payload.get("original_message") or "").strip()
        store = get_attachment_bundle_store()
        summary = store.summarize_bundles(
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_ids=bundle_ids,
            query=query,
        )
        payload["upload_bundle_ids"] = bundle_ids
        payload["uploaded_attachments_manifest"] = {
            "bundle_ids": summary["bundle_ids"],
            "file_count": summary["file_count"],
            "directory_tree": summary["directory_tree"],
            "files": [
                {
                    "id": item.get("id"),
                    "bundle_id": item.get("bundle_id"),
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "score": item.get("score", 0),
                    "char_count": item.get("char_count"),
                }
                for item in summary["files"]
            ],
        }
        payload["uploaded_attachments"] = {
            "bundle_ids": summary["bundle_ids"],
            "directory_tree": summary["directory_tree"],
            "files": summary["files"],
            "context_text": summary["context_text"],
        }
        return payload

    def _build_resume_context(self, run_row: dict) -> dict:
        context = dict(run_row.get("context") or {})
        if not isinstance(context.get("conversation"), list):
            context["conversation"] = []
        if not isinstance(context.get("step_history"), list):
            context["step_history"] = []

        for key in (
            "pending_question",
            "pending_subagent_clarification",
            "resolved_subagent_invocations",
            "ask_user_guard",
            "last_plan",
            "last_result_contract",
            "last_summary_model",
            "planning_model",
            "synthesis_model",
            "normalized_task_input",
            "mounted_knowledge_base_ids",
            "promoted_artifacts",
        ):
            context.pop(key, None)

        context = prune_runtime_governance_ledger_for_resume(context)
        context["tool_failures"] = 0
        context["execution_count"] = 0
        return context

    def _hydrate_run_row(
        self,
        run_row: dict,
        *,
        artifacts: list[dict] | None = None,
        steps: list[dict] | None = None,
        tool_calls: list[dict] | None = None,
    ) -> AgentRun:
        legacy = hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=artifacts,
        )
        hydrated = {
            **run_row,
            "final_output": legacy.get("final_output"),
            "final_output_text": legacy.get("final_output_text"),
            "final_output_json": legacy.get("final_output_json"),
            "artifacts": legacy.get("artifacts") or [],
            "steps": steps or [],
            "tool_calls": tool_calls or [],
        }
        return AgentRun.model_validate(
            {
                **hydrated,
                "artifacts": [AgentArtifact.model_validate(item) for item in hydrated["artifacts"]],
            }
        )

    def _hydrate_subagent_invocation_row(self, row: dict) -> AgentSubagentInvocation:
        return AgentSubagentInvocation.model_validate(
            {
                **row,
                "request_payload": row.get("request_payload") if isinstance(row.get("request_payload"), dict) else {},
                "result_payload": row.get("result_payload") if isinstance(row.get("result_payload"), dict) else {},
            }
        )

    def _hydrate_tree_run_summary(self, run_row: dict) -> AgentRunTreeRunSummary:
        legacy = hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=[],
        )
        return AgentRunTreeRunSummary.model_validate(
            {
                **run_row,
                "final_output": legacy.get("final_output"),
                "final_output_text": legacy.get("final_output_text"),
                "final_output_json": legacy.get("final_output_json"),
            }
        )

    async def _build_run_tree_node(
        self,
        run_row: dict,
        *,
        tenant_id: str | None,
        depth: int,
        remaining_depth: int,
    ) -> AgentRunTreeNode:
        invocations = await self.subagent_invocation_repository.list_invocations_for_parent_run(run_row["id"])
        invocation_models = [self._hydrate_subagent_invocation_row(item) for item in invocations]

        child_nodes_by_run_id: dict[str, AgentRunTreeNode] = {}
        child_run_ids = [
            invocation.child_run_id
            for invocation in invocation_models
            if invocation.child_run_id
        ]
        if remaining_depth > 0 and child_run_ids:
            child_rows = await self.run_repository.list_runs_by_ids(child_run_ids, tenant_id=tenant_id)
            child_rows_by_id = {str(item.get("id")): item for item in child_rows if item.get("id")}
            for child_run_id in child_run_ids:
                child_row = child_rows_by_id.get(child_run_id)
                if child_row is None:
                    continue
                child_nodes_by_run_id[child_run_id] = await self._build_run_tree_node(
                    child_row,
                    tenant_id=tenant_id,
                    depth=depth + 1,
                    remaining_depth=remaining_depth - 1,
                )

        return AgentRunTreeNode(
            run=self._hydrate_tree_run_summary(run_row),
            depth=depth,
            invocations=[
                AgentRunTreeEdge(
                    invocation=invocation,
                    child_run=child_nodes_by_run_id.get(invocation.child_run_id or ""),
                )
                for invocation in invocation_models
            ],
        )

    async def _load_terminal_run_surface(self, run_row: dict | None) -> dict:
        if not run_row:
            return {
                "final_output": None,
                "final_output_text": None,
                "final_output_json": None,
                "artifacts": [],
            }

        context = run_row.get("context") if isinstance(run_row.get("context"), dict) else {}
        promoted_artifacts = context.get("promoted_artifacts") if isinstance(context.get("promoted_artifacts"), list) else []
        stored_artifacts = await self.run_repository.list_artifacts(run_row["id"])
        return hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=merge_artifacts(stored_artifacts, promoted_artifacts),
        )

    async def list_tools(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        agent_definition_id: str | None = None,
    ) -> list[dict]:
        agent_definition = None
        if agent_definition_id:
            agent_definition = await self.agent_repository.get_definition(agent_definition_id, tenant_id)
        execution_mode = normalize_execution_mode(
            agent_definition.get("config") if isinstance(agent_definition, dict) else None
        )
        catalog_tools = await self.registry.list_specs(
            context=ToolLookupContext(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_definition_id=agent_definition_id,
            )
        )
        annotated_catalog = [annotate_tool_spec_for_execution_mode(tool, execution_mode) for tool in catalog_tools]
        tools = [tool for tool in annotated_catalog if tool["metadata"].get("execution_mode_allowed")]
        return {
            "tools": tools,
            "execution_mode": build_execution_mode_surface(annotated_catalog, execution_mode),
        }

    async def list_workspace_sources(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        max_entries: int = 200,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        del tenant_id, user_id
        return self.workspace_manager.list_available_sources(
            max_entries=max_entries,
            max_depth=max_depth,
        )

    async def test_mcp_server(self, *, tenant_id: str, server_id: str) -> dict:
        return await self.mcp_registry.test_server_summary(tenant_id=tenant_id, server_id=server_id)

    async def refresh_mcp_server_tools(self, *, tenant_id: str, server_id: str) -> dict:
        return await self.mcp_registry.refresh_server_tools_summary(tenant_id=tenant_id, server_id=server_id)

    async def create_run(self, request: RuntimeCreateRunRequest) -> AgentRunSummaryResponse:
        hydrated_input = self._hydrate_upload_context(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            run_input=request.input,
        )
        run_row = await self.run_repository.create_run(
            {
                "agent_definition_id": request.agent_definition_id,
                "tenant_id": request.tenant_id,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "input": hydrated_input,
                "metadata": request.metadata,
            }
        )
        run = self._hydrate_run_row(run_row, artifacts=[])
        await self.tracer.emit_event(run.id, "run.created", status=run.status, input=run.input)
        if request.auto_start:
            await self.start_run(run.id)
            refreshed = await self.run_repository.get_run(run.id, run.tenant_id)
            artifacts = await self.run_repository.list_artifacts(run.id)
            steps = await self.run_repository.list_steps(run.id)
            tool_calls = await self.tool_call_repository.list_tool_calls(run.id)
            run = self._hydrate_run_row(refreshed, artifacts=artifacts, steps=steps, tool_calls=tool_calls)
        return AgentRunSummaryResponse(run=run)

    async def start_run(self, run_id: str) -> None:
        existing = self.state_store.get_task(run_id)
        if existing and not existing.done():
            return
        self.state_store.reset_cancel(run_id)

        import os

        if os.getenv("AI_RUNTIME_AGENT_GRAPH", "").lower() in {"1", "true", "yes"}:
            from ai_runtime.graphs.agent import build_agent_graph

            if not hasattr(self, "_agent_graph"):
                self._agent_graph = build_agent_graph()

            async def _run_via_graph() -> None:
                config = {"configurable": {"thread_id": f"agent:{run_id}"}}
                state = {"run_id": run_id, "iteration": 0}
                await self._agent_graph.ainvoke(state, config=config)

            task = asyncio.create_task(_run_via_graph())
        else:
            task = asyncio.create_task(self.orchestrator.start_run(run_id))

        self.state_store.register_task(run_id, task)

    async def get_run(self, run_id: str, tenant_id: Optional[str]) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        artifacts = await self.run_repository.list_artifacts(run_id)
        steps = await self.run_repository.list_steps(run_id)
        tool_calls = await self.tool_call_repository.list_tool_calls(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(run, artifacts=artifacts, steps=steps, tool_calls=tool_calls))

    async def list_subagent_invocations(
        self,
        run_id: str,
        tenant_id: Optional[str],
    ) -> AgentSubagentInvocationListResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        rows = await self.subagent_invocation_repository.list_invocations_for_parent_run(run_id)
        invocations = [self._hydrate_subagent_invocation_row(row) for row in rows]
        return AgentSubagentInvocationListResponse(invocations=invocations, total=len(invocations))

    async def get_run_tree(
        self,
        run_id: str,
        tenant_id: Optional[str],
        *,
        max_depth: int = 4,
    ) -> AgentRunTreeResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        bounded_depth = max(1, min(int(max_depth), 8))
        root = await self._build_run_tree_node(
            run,
            tenant_id=tenant_id,
            depth=0,
            remaining_depth=bounded_depth - 1,
        )
        return AgentRunTreeResponse(root=root)

    async def list_runs(
        self,
        tenant_id: str,
        user_id: Optional[str],
        limit: int = 50,
        offset: int = 0,
    ) -> AgentRunListResponse:
        rows = await self.run_repository.list_runs(tenant_id, user_id=user_id, limit=limit, offset=offset)
        artifact_map = await self.run_repository.list_artifacts_for_runs([row["id"] for row in rows])
        runs = [self._hydrate_run_row(row, artifacts=artifact_map.get(row["id"], [])) for row in rows]
        return AgentRunListResponse(runs=runs, total=len(runs))

    async def list_events(
        self,
        run_id: str,
        tenant_id: Optional[str],
        after_sequence: int = 0,
        limit: int = 500,
    ) -> AgentRunEventListResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        rows = await self.run_repository.list_events(run_id, after_sequence=after_sequence, limit=limit)
        events = [AgentRunEvent.model_validate(row) for row in rows]
        return AgentRunEventListResponse(events=events, total=len(events))

    async def build_run_audit_view(
        self,
        run_id: str,
        tenant_id: Optional[str],
        *,
        viewer_role: str = "user",
        include_events: bool = True,
        include_tool_calls: bool = True,
        event_limit: int = 500,
    ) -> dict[str, Any]:
        from ai_runtime.core.agent_runtime.audit_view import (
            ViewerRole,
            build_audit_view_for_events,
            build_audit_view_for_run,
            build_audit_view_for_tool_calls,
        )

        run = await self.get_run(run_id, tenant_id)
        try:
            role = ViewerRole(str(viewer_role or "user").lower())
        except ValueError:
            role = ViewerRole.USER
        run_payload = run.run.model_dump(mode="json")
        audit_run = build_audit_view_for_run(run_payload, viewer_role=role)
        events: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        if include_events:
            event_rows = await self.run_repository.list_events(run_id, after_sequence=0, limit=event_limit)
            events = build_audit_view_for_events(event_rows, viewer_role=role)
        if include_tool_calls:
            call_rows = await self.tool_call_repository.list_tool_calls(run_id)
            tool_calls = build_audit_view_for_tool_calls(call_rows, viewer_role=role)
        return {
            "run": audit_run,
            "events": events,
            "tool_calls": tool_calls,
            "viewer_role": role.value,
            "event_count": len(events),
            "tool_call_count": len(tool_calls),
        }

    async def stream_events(
        self,
        run_id: str,
        tenant_id: Optional[str],
        after_sequence: int = 0,
    ) -> AsyncIterator[AgentRunEvent]:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")

        snapshot = await self.list_events(run_id, tenant_id, after_sequence=after_sequence)
        last_sequence = after_sequence
        for event in snapshot.events:
            last_sequence = max(last_sequence, event.sequence)
            yield event

        latest_run = await self.run_repository.get_run(run_id, tenant_id)
        if latest_run is None:
            raise ValueError("run not found")

        if latest_run["status"] in {"completed", "failed", "cancelled", "waiting_user"}:
            return

        async for event in self.state_store.subscribe(run_id):
            if event.sequence <= last_sequence:
                continue
            last_sequence = event.sequence
            yield event

    async def cancel_run(self, run_id: str, tenant_id: Optional[str]) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        terminal_surface = await self._load_terminal_run_surface(run)
        self.state_store.request_cancel(run_id)
        task = self.state_store.get_task(run_id)
        if task is not None and not task.done():
            task.cancel()
        updated = await self.run_repository.update_run_status(
            run_id,
            "cancelled",
            plan=run.get("plan") if isinstance(run.get("plan"), dict) else None,
            context=run.get("context") if isinstance(run.get("context"), dict) else None,
            final_output=terminal_surface.get("final_output"),
            final_output_text=terminal_surface.get("final_output_text"),
            final_output_json=terminal_surface.get("final_output_json"),
            error_message="Run cancelled",
        )
        await self.run_repository.replace_artifacts(run_id, terminal_surface.get("artifacts") or [])
        await self.tracer.emit_event(
            run_id,
            "run.cancelled",
            status="cancelled",
            final_output=terminal_surface.get("final_output"),
            final_output_text=terminal_surface.get("final_output_text"),
            final_output_json=terminal_surface.get("final_output_json"),
            artifacts=terminal_surface.get("artifacts") or [],
        )
        artifacts = await self.run_repository.list_artifacts(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(updated, artifacts=artifacts))

    async def resume_run(
        self,
        run_id: str,
        tenant_id: Optional[str],
        input_patch: Optional[dict] = None,
    ) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        if input_patch:
            merged_input = {
                **(run.get("input") if isinstance(run.get("input"), dict) else {}),
                **input_patch,
            }
            hydrated_input = self._hydrate_upload_context(
                tenant_id=str(run.get("tenant_id") or tenant_id or ""),
                user_id=run.get("user_id"),
                run_input=merged_input,
            )
            run = await self.run_repository.patch_run_input(run_id, hydrated_input)
            await self.tracer.emit_event(run_id, "run.input_patched", input_patch=input_patch)
        updated = await self.run_repository.reset_run_execution(
            run_id,
            context=self._build_resume_context(run),
        )
        await self.tracer.emit_event(run_id, "run.resumed", status="queued")
        await self.start_run(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(updated, artifacts=[], steps=[], tool_calls=[]))

    async def review_artifact(
        self,
        run_id: str,
        artifact_id: str,
        tenant_id: Optional[str],
        reviewer_id: Optional[str],
        request: RuntimeArtifactReviewDecisionRequest,
    ) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        updated_artifact = await self.run_repository.update_artifact_review_decision(
            run_id=run_id,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            decision=request.decision,
            reviewer_id=reviewer_id,
            note=request.note,
        )
        if updated_artifact is None:
            raise ValueError("artifact not found")
        artifacts = await self.run_repository.list_artifacts(run_id)
        steps = await self.run_repository.list_steps(run_id)
        tool_calls = await self.tool_call_repository.list_tool_calls(run_id)
        await self.tracer.emit_event(
            run_id,
            "artifact.reviewed",
            artifact_id=artifact_id,
            decision=request.decision,
            note=request.note,
            reviewer_id=reviewer_id,
        )
        return AgentRunSummaryResponse(run=self._hydrate_run_row(run, artifacts=artifacts, steps=steps, tool_calls=tool_calls))

    async def writeback_run_workspace(
        self,
        run_id: str,
        tenant_id: Optional[str],
        reviewer_id: Optional[str],
        request: RuntimeWorkspaceWritebackRequest,
    ) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        context = run.get("context") if isinstance(run.get("context"), dict) else {}
        workspace = context.get("workspace") if isinstance(context.get("workspace"), dict) else {}
        workspace_root = str(context.get("workspace_root") or workspace.get("root") or "").strip()
        source = workspace.get("source") if isinstance(workspace.get("source"), dict) else {}
        source_path = str(source.get("path") or source.get("root") or "").strip()
        source_type = str(source.get("type") or "").strip()
        if not workspace_root:
            raise ValueError("run has no bound workspace")
        if not source_path or source_type == "upload_bundle":
            raise ValueError("workspace source is not a writable registered repository")

        result = self.workspace_manager.apply_workspace_writeback(
            workspace_root=workspace_root,
            source_path=source_path,
            tenant_id=str(run.get("tenant_id") or tenant_id or ""),
            dry_run=request.dry_run,
            confirmed=request.confirmed,
            max_diff_chars=request.max_diff_chars,
        )
        artifact = {
            "artifact_type": "code_patch",
            "name": "Workspace Repository Writeback",
            "payload": {
                "operation": "repository_writeback",
                "status": result.get("status"),
                "dry_run": bool(result.get("dry_run")),
                "files": result.get("files") or [],
                "diff": result.get("diff") or "",
                "truncated": bool(result.get("truncated")),
                "review_notes": [
                    "This artifact was produced by an explicit user-triggered writeback from the isolated run workspace.",
                    "Review source repository status before committing or opening a PR.",
                ],
                "merge_policy": "explicit_user_writeback",
                "writeback": {
                    "source_path": result.get("source_path"),
                    "workspace_root": result.get("workspace_root"),
                    "change_count": result.get("change_count"),
                    "applied_count": result.get("applied_count"),
                    "failed_count": result.get("failed_count"),
                    "status": result.get("status"),
                },
            },
            "metadata": {
                "source": "workspace_writeback",
                "requested_by": reviewer_id,
                "dry_run": bool(result.get("dry_run")),
                "confirmed": bool(request.confirmed),
                "source_path": result.get("source_path"),
                "workspace_root": result.get("workspace_root"),
                "generated_at": result.get("generated_at"),
                "completed_at": result.get("completed_at"),
            },
        }
        artifact = sanitize_runtime_payload(artifact)
        await self.run_repository.create_artifact(run_id, artifact)
        await self.tracer.emit_event(
            run_id,
            "workspace.writeback",
            dry_run=bool(result.get("dry_run")),
            status=result.get("status"),
            change_count=result.get("change_count"),
            applied_count=result.get("applied_count"),
            failed_count=result.get("failed_count"),
            source_path=result.get("source_path"),
            reviewer_id=reviewer_id,
        )
        artifacts = await self.run_repository.list_artifacts(run_id)
        steps = await self.run_repository.list_steps(run_id)
        tool_calls = await self.tool_call_repository.list_tool_calls(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(run, artifacts=artifacts, steps=steps, tool_calls=tool_calls))
