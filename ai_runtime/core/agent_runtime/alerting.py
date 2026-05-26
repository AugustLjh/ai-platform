"""External alerting, SLO metrics, and ops runbook structures for GA hardening."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Sequence

import aiohttp

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    WEBHOOK = "webhook"
    LOG = "log"
    EVENT_BUS = "event_bus"


@dataclass(frozen=True)
class AlertRule:
    name: str
    condition: str
    severity: AlertSeverity
    subsystem: str
    threshold: float | int | None = None
    cooldown_seconds: int = 300
    description: str = ""
    recovery_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SLODefinition:
    name: str
    subsystem: str
    metric: str
    target_percent: float
    window_seconds: int = 3600
    description: str = ""
    breach_severity: AlertSeverity = AlertSeverity.WARNING


@dataclass
class SLOState:
    definition: SLODefinition
    total_events: int = 0
    good_events: int = 0
    last_evaluated_at: str | None = None
    breached: bool = False

    @property
    def current_percent(self) -> float:
        if self.total_events == 0:
            return 100.0
        return (self.good_events / self.total_events) * 100.0

    @property
    def error_budget_remaining(self) -> float:
        target = self.definition.target_percent
        if self.total_events == 0:
            return 100.0 - target
        actual = self.current_percent
        return actual - target

    def record(self, *, good: bool) -> None:
        self.total_events += 1
        if good:
            self.good_events += 1
        self.last_evaluated_at = datetime.now(timezone.utc).isoformat()
        self.breached = self.current_percent < self.definition.target_percent

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.definition.name,
            "subsystem": self.definition.subsystem,
            "metric": self.definition.metric,
            "target_percent": self.definition.target_percent,
            "current_percent": round(self.current_percent, 2),
            "error_budget_remaining": round(self.error_budget_remaining, 2),
            "total_events": self.total_events,
            "good_events": self.good_events,
            "breached": self.breached,
            "last_evaluated_at": self.last_evaluated_at,
            "window_seconds": self.definition.window_seconds,
        }


@dataclass
class Alert:
    rule_name: str
    severity: AlertSeverity
    subsystem: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "subsystem": self.subsystem,
            "message": self.message,
            "details": self.details,
            "generated_at": self.generated_at,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


AlertSink = Callable[[Alert], Awaitable[None] | None]


@dataclass
class OpsRunbookEntry:
    subsystem: str
    scenario: str
    symptoms: list[str]
    diagnosis_steps: list[str]
    recovery_actions: list[str]
    escalation: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING


WORKSPACE_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="workspace_expired_count_high",
        condition="expired_count >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="workspace",
        threshold=10,
        cooldown_seconds=600,
        description="Too many expired workspaces awaiting cleanup.",
        recovery_actions=(
            "Run workspace cleanup with confirmed=true.",
            "Check workspace lifecycle scheduler is running.",
            "Verify retention_hours is appropriate for workload.",
        ),
    ),
    AlertRule(
        name="workspace_quota_exceeded",
        condition="quota_exceeded_count >= threshold",
        severity=AlertSeverity.CRITICAL,
        subsystem="workspace",
        threshold=5,
        cooldown_seconds=300,
        description="Workspaces exceeding file or byte quota.",
        recovery_actions=(
            "Identify large workspaces and clean up or archive.",
            "Review max_files and max_bytes configuration.",
            "Check for runaway file generation in sandbox tasks.",
        ),
    ),
    AlertRule(
        name="workspace_stale_locks",
        condition="stale_lock_count >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="workspace",
        threshold=3,
        cooldown_seconds=600,
        description="Cleanup locks have exceeded their TTL.",
        recovery_actions=(
            "Run stale lock cleanup with dry_run=false.",
            "Check for crashed cleanup processes.",
            "Verify cleanup_lock_ttl_seconds is sufficient.",
        ),
    ),
    AlertRule(
        name="workspace_storage_high",
        condition="total_size_bytes >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="workspace",
        threshold=500 * 1024 * 1024,
        cooldown_seconds=1800,
        description="Total workspace storage usage is high.",
        recovery_actions=(
            "Run expired workspace cleanup.",
            "Review workspace retention policy.",
            "Consider increasing disk allocation.",
        ),
    ),
)

SANDBOX_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="sandbox_isolation_degraded",
        condition="isolation_status != ready",
        severity=AlertSeverity.CRITICAL,
        subsystem="sandbox",
        cooldown_seconds=300,
        description="Sandbox isolation checks are failing.",
        recovery_actions=(
            "Run sandbox_isolation_check and review failed checks.",
            "Verify Docker daemon is running and accessible.",
            "Check AGENT_SANDBOX_DOCKER_* environment variables.",
        ),
    ),
    AlertRule(
        name="sandbox_session_leak",
        condition="active_session_count >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="sandbox",
        threshold=10,
        cooldown_seconds=600,
        description="Too many active sandbox process sessions.",
        recovery_actions=(
            "Review and stop idle dev server sessions.",
            "Check session timeout configuration.",
            "Verify process reaping is functioning.",
        ),
    ),
)

BROWSER_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="browser_session_leak",
        condition="active_session_count >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="browser",
        threshold=3,
        cooldown_seconds=600,
        description="Too many active browser sessions.",
        recovery_actions=(
            "Close idle browser sessions with browser_close.",
            "Review browser_session_ttl_seconds configuration.",
            "Check for stale sessions not being reaped.",
        ),
    ),
    AlertRule(
        name="browser_network_errors_high",
        condition="network_error_rate >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="browser",
        threshold=0.5,
        cooldown_seconds=900,
        description="High rate of network errors in browser sessions.",
        recovery_actions=(
            "Check target URLs are accessible.",
            "Review allowed_domains configuration.",
            "Verify network connectivity from sandbox.",
        ),
    ),
)

WEB_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="web_fetch_timeout_rate_high",
        condition="timeout_rate >= threshold",
        severity=AlertSeverity.WARNING,
        subsystem="web",
        threshold=0.3,
        cooldown_seconds=900,
        description="High rate of web fetch timeouts.",
        recovery_actions=(
            "Check network connectivity.",
            "Review timeout_seconds configuration.",
            "Verify target domains are responsive.",
        ),
    ),
)

OBSERVABILITY_ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule(
        name="observability_db_unavailable",
        condition="db_configured and not db_reachable",
        severity=AlertSeverity.CRITICAL,
        subsystem="observability",
        cooldown_seconds=300,
        description="Configured database is not reachable for observability queries.",
        recovery_actions=(
            "Check database connection string.",
            "Verify database is running and accepting connections.",
            "Check network connectivity to database host.",
        ),
    ),
    AlertRule(
        name="observability_redis_unavailable",
        condition="redis_configured and not redis_reachable",
        severity=AlertSeverity.WARNING,
        subsystem="observability",
        cooldown_seconds=300,
        description="Configured Redis is not reachable for observability inspection.",
        recovery_actions=(
            "Check Redis host and port configuration.",
            "Verify Redis is running.",
            "Check network connectivity to Redis host.",
        ),
    ),
)

ALL_ALERT_RULES: tuple[AlertRule, ...] = (
    *WORKSPACE_ALERT_RULES,
    *SANDBOX_ALERT_RULES,
    *BROWSER_ALERT_RULES,
    *WEB_ALERT_RULES,
    *OBSERVABILITY_ALERT_RULES,
)

WORKSPACE_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="workspace_cleanup_success_rate",
        subsystem="workspace",
        metric="cleanup_success",
        target_percent=99.0,
        window_seconds=3600,
        description="Percentage of workspace cleanup operations that succeed.",
    ),
    SLODefinition(
        name="workspace_materialization_success_rate",
        subsystem="workspace",
        metric="materialization_success",
        target_percent=99.5,
        window_seconds=3600,
        description="Percentage of workspace materializations that complete without error.",
    ),
)

SANDBOX_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="sandbox_execution_success_rate",
        subsystem="sandbox",
        metric="execution_success",
        target_percent=95.0,
        window_seconds=3600,
        description="Percentage of sandbox executions that complete (not timeout or runner_unavailable).",
    ),
    SLODefinition(
        name="sandbox_isolation_compliance",
        subsystem="sandbox",
        metric="isolation_pass",
        target_percent=100.0,
        window_seconds=86400,
        description="Sandbox isolation checks must always pass in production.",
        breach_severity=AlertSeverity.CRITICAL,
    ),
)

WEB_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="web_fetch_success_rate",
        subsystem="web",
        metric="fetch_success",
        target_percent=90.0,
        window_seconds=3600,
        description="Percentage of web fetches that return a valid response.",
    ),
)

BROWSER_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="browser_session_success_rate",
        subsystem="browser",
        metric="session_open_success",
        target_percent=95.0,
        window_seconds=3600,
        description="Percentage of browser session opens that succeed.",
    ),
)

OBSERVABILITY_SLOS: tuple[SLODefinition, ...] = (
    SLODefinition(
        name="observability_query_success_rate",
        subsystem="observability",
        metric="query_success",
        target_percent=99.0,
        window_seconds=3600,
        description="Percentage of observability queries that return results.",
    ),
)

ALL_SLO_DEFINITIONS: tuple[SLODefinition, ...] = (
    *WORKSPACE_SLOS,
    *SANDBOX_SLOS,
    *WEB_SLOS,
    *BROWSER_SLOS,
    *OBSERVABILITY_SLOS,
)

WORKSPACE_RUNBOOK: tuple[OpsRunbookEntry, ...] = (
    OpsRunbookEntry(
        subsystem="workspace",
        scenario="Expired workspaces accumulating",
        symptoms=[
            "workspace_expired_count_high alert firing",
            "Disk usage growing on workspace volume",
            "workspace inspection shows many expired entries",
        ],
        diagnosis_steps=[
            "Check workspace lifecycle scheduler status via runtime_status API.",
            "Verify AGENT_WORKSPACE_RETENTION_HOURS is set appropriately.",
            "Check for cleanup lock contention via workspace inspection.",
            "Review recent cleanup run results for failures.",
        ],
        recovery_actions=[
            "POST /api/v1/agents/workspaces/cleanup with dry_run=false.",
            "If locks are stale, POST /api/v1/agents/workspaces/locks/cleanup.",
            "Restart workspace lifecycle scheduler if stopped.",
            "Reduce retention_hours if workload permits.",
        ],
        escalation="If cleanup consistently fails, check disk permissions and filesystem health.",
    ),
    OpsRunbookEntry(
        subsystem="workspace",
        scenario="Writeback fails or produces unexpected results",
        symptoms=[
            "Writeback API returns partial status.",
            "Files missing or corrupted after writeback.",
            "Permission errors during writeback.",
        ],
        diagnosis_steps=[
            "Run writeback with dry_run=true to preview changes.",
            "Verify source_roots configuration includes the target directory.",
            "Check file permissions on target directory.",
            "Review writeback audit events for error details.",
        ],
        recovery_actions=[
            "Fix file permissions on target source root.",
            "Verify workspace_root is within managed base_root.",
            "Re-run writeback after fixing underlying issue.",
        ],
        escalation="If writeback consistently fails, check for filesystem corruption or quota issues.",
    ),
)

SANDBOX_RUNBOOK: tuple[OpsRunbookEntry, ...] = (
    OpsRunbookEntry(
        subsystem="sandbox",
        scenario="Sandbox isolation check failing",
        symptoms=[
            "sandbox_isolation_degraded alert firing",
            "sandbox_isolation_check returns status=failed",
            "Sandbox tools returning runner_unavailable errors",
        ],
        diagnosis_steps=[
            "Run sandbox_isolation_check tool and review failed checks.",
            "Verify Docker daemon is running: docker info.",
            "Check AGENT_SANDBOX_RUNNER_CONFIGURED=true.",
            "Verify Docker image is available: docker images.",
        ],
        recovery_actions=[
            "Start Docker daemon if stopped.",
            "Pull required Docker image.",
            "Fix Docker configuration (network, memory, caps).",
            "Set AGENT_SANDBOX_RUNNER_CONFIGURED=true after fixes.",
        ],
        escalation="If Docker is unavailable, fall back to local_subprocess for development only.",
    ),
    OpsRunbookEntry(
        subsystem="sandbox",
        scenario="Dev server sessions leaking",
        symptoms=[
            "sandbox_session_leak alert firing",
            "process_list shows many running sessions",
            "System resources (PIDs, memory) growing",
        ],
        diagnosis_steps=[
            "Run process_list to see active sessions.",
            "Check session timeouts and ages.",
            "Verify session reaping is working (check logs).",
        ],
        recovery_actions=[
            "Stop idle sessions with process_stop.",
            "Reduce session timeout if appropriate.",
            "Restart runtime worker if reaping is broken.",
        ],
        escalation="If sessions cannot be stopped, kill processes manually and restart worker.",
    ),
)

BROWSER_RUNBOOK: tuple[OpsRunbookEntry, ...] = (
    OpsRunbookEntry(
        subsystem="browser",
        scenario="Browser sessions not being cleaned up",
        symptoms=[
            "browser_session_leak alert firing",
            "Playwright processes accumulating",
            "Memory usage growing on worker",
        ],
        diagnosis_steps=[
            "Check browser session summary via runtime_status.",
            "Verify browser_session_ttl_seconds is reasonable.",
            "Check for errors in session reaping logs.",
        ],
        recovery_actions=[
            "Close stale sessions with browser_close.",
            "Reduce browser_max_sessions if needed.",
            "Restart worker to force cleanup of all sessions.",
        ],
        escalation="If Playwright processes are orphaned, kill them manually.",
    ),
)

WEB_RUNBOOK: tuple[OpsRunbookEntry, ...] = (
    OpsRunbookEntry(
        subsystem="web",
        scenario="Web fetch or search quality degraded",
        symptoms=[
            "web_fetch_timeout_rate_high alert firing",
            "fetch_url or web_search tool calls timing out",
            "Search results contain missing URLs, titles, or duplicate domains",
        ],
        diagnosis_steps=[
            "Check AGENT_WEB_ENABLED and AGENT_WEB_NETWORK_CONFIGURED.",
            "Verify allowed_domains and denied_domains policy.",
            "Review web tool_call failures and timeout_seconds.",
            "Run a controlled fetch against an allowed health-check URL.",
        ],
        recovery_actions=[
            "Fix domain policy or search endpoint configuration.",
            "Increase timeout_seconds only after validating target latency.",
            "Route production alerting to the configured webhook sink.",
        ],
        escalation="If network failures persist across allowed domains, inspect worker network policy and egress controls.",
    ),
)

OBSERVABILITY_RUNBOOK: tuple[OpsRunbookEntry, ...] = (
    OpsRunbookEntry(
        subsystem="observability",
        scenario="Database observability queries failing",
        symptoms=[
            "observability_db_unavailable alert firing",
            "db_query_readonly returning errors",
            "Runtime status shows db not reachable",
        ],
        diagnosis_steps=[
            "Check database connection string in environment.",
            "Verify database is accepting connections.",
            "Check for connection pool exhaustion.",
            "Review statement_timeout settings.",
        ],
        recovery_actions=[
            "Restart database if down.",
            "Fix connection string if incorrect.",
            "Increase connection pool size if exhausted.",
            "Review and fix slow queries.",
        ],
        escalation="If database is consistently unreachable, check network and DNS.",
    ),
)

ALL_RUNBOOK_ENTRIES: tuple[OpsRunbookEntry, ...] = (
    *WORKSPACE_RUNBOOK,
    *SANDBOX_RUNBOOK,
    *BROWSER_RUNBOOK,
    *WEB_RUNBOOK,
    *OBSERVABILITY_RUNBOOK,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_alert_sinks_from_env() -> list[AlertSink]:
    sinks: list[AlertSink] = []
    webhook_url = os.getenv("AGENT_ALERT_WEBHOOK_URL", "").strip()
    if webhook_url:
        timeout_seconds = int(os.getenv("AGENT_ALERT_WEBHOOK_TIMEOUT_SECONDS", "5"))

        async def webhook_sink(alert: Alert) -> None:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as session:
                async with session.post(webhook_url, json=alert.snapshot()) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise RuntimeError(f"alert webhook returned {response.status}: {body[:300]}")

        sinks.append(webhook_sink)

    if _env_bool("AGENT_ALERT_LOG_SINK_ENABLED", True):

        def log_sink(alert: Alert) -> None:
            logger.warning(
                "runtime alert fired: rule=%s subsystem=%s severity=%s message=%s",
                alert.rule_name,
                alert.subsystem,
                alert.severity.value,
                alert.message,
            )

        sinks.append(log_sink)

    return sinks


class AlertManager:
    def __init__(
        self,
        *,
        rules: Sequence[AlertRule] = ALL_ALERT_RULES,
        sinks: Sequence[AlertSink] | None = None,
        max_history: int = 200,
    ) -> None:
        self.rules = {rule.name: rule for rule in rules}
        self.sinks: list[AlertSink] = list(sinks or [])
        self._history: list[Alert] = []
        self._last_fired: dict[str, float] = {}
        self._max_history = max(10, max_history)

    def _in_cooldown(self, rule: AlertRule) -> bool:
        last = self._last_fired.get(rule.name)
        if last is None:
            return False
        return (time.monotonic() - last) < rule.cooldown_seconds

    async def evaluate(self, subsystem: str, metrics: dict[str, Any]) -> list[Alert]:
        fired: list[Alert] = []
        for rule in self.rules.values():
            if rule.subsystem != subsystem:
                continue
            if self._in_cooldown(rule):
                continue
            if not self._check_condition(rule, metrics):
                continue
            alert = Alert(
                rule_name=rule.name,
                severity=rule.severity,
                subsystem=rule.subsystem,
                message=rule.description,
                details={"metrics": metrics, "threshold": rule.threshold},
            )
            fired.append(alert)
            self._last_fired[rule.name] = time.monotonic()
            self._history.append(alert)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            for sink in self.sinks:
                try:
                    result = sink(alert)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("alert sink failed for rule %s", rule.name)
        return fired

    def _check_condition(self, rule: AlertRule, metrics: dict[str, Any]) -> bool:
        condition = rule.condition
        threshold = rule.threshold

        if ">=" in condition:
            metric_key = condition.split(">=")[0].strip()
            value = metrics.get(metric_key)
            if value is None:
                return False
            try:
                return float(value) >= float(threshold)
            except (TypeError, ValueError):
                return False

        if "!=" in condition:
            parts = condition.split("!=")
            metric_key = parts[0].strip()
            expected = parts[1].strip()
            value = str(metrics.get(metric_key, "")).strip()
            return value != expected

        if " and " in condition:
            parts = condition.split(" and ")
            results = []
            for part in parts:
                part = part.strip()
                if part.startswith("not "):
                    key = part[4:].strip()
                    results.append(not bool(metrics.get(key)))
                else:
                    results.append(bool(metrics.get(part)))
            return all(results)

        return False

    @property
    def history(self) -> list[Alert]:
        return list(self._history)

    def acknowledge(self, rule_name: str) -> bool:
        for alert in reversed(self._history):
            if alert.rule_name == rule_name and not alert.acknowledged:
                alert.acknowledged = True
                return True
        return False

    def resolve(self, rule_name: str) -> bool:
        for alert in reversed(self._history):
            if alert.rule_name == rule_name and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def active_alerts(self) -> list[Alert]:
        return [alert for alert in self._history if not alert.resolved]

    def status_summary(self) -> dict[str, Any]:
        active = self.active_alerts()
        by_severity: dict[str, int] = {}
        by_subsystem: dict[str, int] = {}
        for alert in active:
            by_severity[alert.severity.value] = by_severity.get(alert.severity.value, 0) + 1
            by_subsystem[alert.subsystem] = by_subsystem.get(alert.subsystem, 0) + 1
        return {
            "status": "critical" if by_severity.get("critical") else "warning" if by_severity.get("warning") else "healthy",
            "active_alert_count": len(active),
            "total_alert_count": len(self._history),
            "by_severity": by_severity,
            "by_subsystem": by_subsystem,
            "rules_configured": len(self.rules),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.status_summary(),
            "active": [alert.snapshot() for alert in self.active_alerts()],
            "history": [alert.snapshot() for alert in self._history[-50:]],
            "rules": [
                {
                    "name": rule.name,
                    "condition": rule.condition,
                    "severity": rule.severity.value,
                    "subsystem": rule.subsystem,
                    "threshold": rule.threshold,
                    "cooldown_seconds": rule.cooldown_seconds,
                    "description": rule.description,
                    "recovery_actions": list(rule.recovery_actions),
                }
                for rule in self.rules.values()
            ],
        }


class SLOTracker:
    def __init__(self, definitions: Sequence[SLODefinition] = ALL_SLO_DEFINITIONS) -> None:
        self._states: dict[str, SLOState] = {}
        for definition in definitions:
            self._states[definition.name] = SLOState(definition=definition)

    def record(self, slo_name: str, *, good: bool) -> SLOState | None:
        state = self._states.get(slo_name)
        if state is None:
            return None
        state.record(good=good)
        return state

    def get(self, slo_name: str) -> SLOState | None:
        return self._states.get(slo_name)

    def breached_slos(self) -> list[SLOState]:
        return [state for state in self._states.values() if state.breached]

    def snapshot(self) -> dict[str, Any]:
        states = [state.snapshot() for state in self._states.values()]
        breached = [state for state in states if state["breached"]]
        return {
            "status": "breached" if breached else "healthy",
            "slo_count": len(states),
            "breached_count": len(breached),
            "slos": states,
            "breached": breached,
        }

    def subsystem_snapshot(self, subsystem: str) -> dict[str, Any]:
        states = [state.snapshot() for state in self._states.values() if state.definition.subsystem == subsystem]
        breached = [state for state in states if state["breached"]]
        return {
            "subsystem": subsystem,
            "status": "breached" if breached else "healthy",
            "slo_count": len(states),
            "breached_count": len(breached),
            "slos": states,
        }


def _prometheus_label_value(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _prometheus_labels(labels: dict[str, Any]) -> str:
    cleaned = {
        key: value
        for key, value in labels.items()
        if value is not None and str(value).strip()
    }
    if not cleaned:
        return ""
    rendered = ",".join(f'{key}="{_prometheus_label_value(value)}"' for key, value in sorted(cleaned.items()))
    return f"{{{rendered}}}"


def _prometheus_sample(name: str, labels: dict[str, Any], value: int | float) -> str:
    if isinstance(value, bool):
        value = int(value)
    return f"{name}{_prometheus_labels(labels)} {value}"


def export_ops_prometheus_metrics(
    *,
    alert_manager: AlertManager,
    slo_tracker: SLOTracker,
    generated_at: str | None = None,
) -> str:
    """Render runtime ops status as Prometheus text exposition."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    alert_summary = alert_manager.status_summary()
    active_alerts = alert_manager.active_alerts()
    slo_snapshot = slo_tracker.snapshot()
    lines = [
        "# HELP agent_runtime_ops_info Agent runtime ops exporter metadata.",
        "# TYPE agent_runtime_ops_info gauge",
        _prometheus_sample("agent_runtime_ops_info", {"generated_at": generated_at}, 1),
        "# HELP agent_runtime_alerts_active Active runtime alerts.",
        "# TYPE agent_runtime_alerts_active gauge",
        _prometheus_sample("agent_runtime_alerts_active", {}, int(alert_summary["active_alert_count"])),
        "# HELP agent_runtime_alerts_total Runtime alerts retained in local history.",
        "# TYPE agent_runtime_alerts_total gauge",
        _prometheus_sample("agent_runtime_alerts_total", {}, int(alert_summary["total_alert_count"])),
        "# HELP agent_runtime_alert_rules_configured Runtime alert rules configured.",
        "# TYPE agent_runtime_alert_rules_configured gauge",
        _prometheus_sample("agent_runtime_alert_rules_configured", {}, int(alert_summary["rules_configured"])),
        "# HELP agent_runtime_alerts_active_by_severity Active runtime alerts by severity.",
        "# TYPE agent_runtime_alerts_active_by_severity gauge",
    ]
    for severity in ("info", "warning", "critical"):
        lines.append(
            _prometheus_sample(
                "agent_runtime_alerts_active_by_severity",
                {"severity": severity},
                int(alert_summary.get("by_severity", {}).get(severity, 0)),
            )
        )
    lines.extend([
        "# HELP agent_runtime_alert_active Active alert state per alert rule.",
        "# TYPE agent_runtime_alert_active gauge",
    ])
    active_rule_names = {alert.rule_name for alert in active_alerts}
    for rule in alert_manager.rules.values():
        lines.append(
            _prometheus_sample(
                "agent_runtime_alert_active",
                {
                    "rule": rule.name,
                    "subsystem": rule.subsystem,
                    "severity": rule.severity.value,
                },
                1 if rule.name in active_rule_names else 0,
            )
        )

    lines.extend([
        "# HELP agent_runtime_slo_current_percent Current SLO success percentage.",
        "# TYPE agent_runtime_slo_current_percent gauge",
        "# HELP agent_runtime_slo_target_percent Target SLO success percentage.",
        "# TYPE agent_runtime_slo_target_percent gauge",
        "# HELP agent_runtime_slo_error_budget_remaining SLO error budget remaining in percentage points.",
        "# TYPE agent_runtime_slo_error_budget_remaining gauge",
        "# HELP agent_runtime_slo_events_total SLO total observed events.",
        "# TYPE agent_runtime_slo_events_total counter",
        "# HELP agent_runtime_slo_good_events_total SLO good observed events.",
        "# TYPE agent_runtime_slo_good_events_total counter",
        "# HELP agent_runtime_slo_breached SLO breach state.",
        "# TYPE agent_runtime_slo_breached gauge",
    ])
    for slo in slo_snapshot.get("slos", []):
        labels = {
            "slo": slo["name"],
            "subsystem": slo["subsystem"],
            "metric": slo["metric"],
        }
        lines.append(_prometheus_sample("agent_runtime_slo_current_percent", labels, float(slo["current_percent"])))
        lines.append(_prometheus_sample("agent_runtime_slo_target_percent", labels, float(slo["target_percent"])))
        lines.append(
            _prometheus_sample(
                "agent_runtime_slo_error_budget_remaining",
                labels,
                float(slo["error_budget_remaining"]),
            )
        )
        lines.append(_prometheus_sample("agent_runtime_slo_events_total", labels, int(slo["total_events"])))
        lines.append(_prometheus_sample("agent_runtime_slo_good_events_total", labels, int(slo["good_events"])))
        lines.append(_prometheus_sample("agent_runtime_slo_breached", labels, 1 if slo["breached"] else 0))
    return "\n".join(lines) + "\n"


def build_grafana_dashboard(
    *,
    datasource_uid: str = "${DS_PROMETHEUS}",
    title: str = "Agent Runtime Ops",
    refresh: str = "30s",
) -> dict[str, Any]:
    """Build a portable Grafana dashboard for the exported ops metrics."""
    targets = {
        "active_alerts": "agent_runtime_alerts_active",
        "slo_breaches": "sum(agent_runtime_slo_breached)",
        "slo_percent": "agent_runtime_slo_current_percent",
        "error_budget": "agent_runtime_slo_error_budget_remaining",
    }

    def _panel(panel_id: int, panel_title: str, expr: str, x: int, y: int, w: int, h: int, panel_type: str = "timeseries") -> dict[str, Any]:
        return {
            "id": panel_id,
            "type": panel_type,
            "title": panel_title,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": {"type": "prometheus", "uid": datasource_uid},
            "targets": [
                {
                    "refId": "A",
                    "expr": expr,
                    "legendFormat": "{{slo}}{{rule}}{{severity}}",
                    "datasource": {"type": "prometheus", "uid": datasource_uid},
                }
            ],
        }

    return {
        "uid": "agent-runtime-ops",
        "title": title,
        "tags": ["agent-runtime", "ops", "slo"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": refresh,
        "time": {"from": "now-6h", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "subsystem",
                    "type": "query",
                    "datasource": {"type": "prometheus", "uid": datasource_uid},
                    "query": "label_values(agent_runtime_slo_current_percent, subsystem)",
                    "refresh": 1,
                    "includeAll": True,
                    "multi": True,
                    "current": {"selected": False, "text": "All", "value": "$__all"},
                }
            ]
        },
        "panels": [
            _panel(1, "Active Alerts", targets["active_alerts"], 0, 0, 6, 4, "stat"),
            _panel(2, "SLO Breaches", targets["slo_breaches"], 6, 0, 6, 4, "stat"),
            _panel(3, "SLO Current Percent", f'{targets["slo_percent"]}{{subsystem=~"$subsystem"}}', 0, 4, 12, 8),
            _panel(4, "Error Budget Remaining", f'{targets["error_budget"]}{{subsystem=~"$subsystem"}}', 0, 12, 12, 8),
            _panel(5, "Active Alerts By Severity", "agent_runtime_alerts_active_by_severity", 12, 0, 12, 8),
            _panel(6, "Alert Rule State", "agent_runtime_alert_active", 12, 8, 12, 12),
        ],
        "annotations": {"list": []},
        "links": [
            {
                "title": "Prometheus metrics endpoint",
                "type": "link",
                "url": "/api/v1/agents/ops-status/metrics",
                "targetBlank": True,
            }
        ],
        "description": "Runtime alert and SLO dashboard for Agent Runtime ops governance.",
        "metadata": {
            "exporter_metrics": targets,
            "import_hint": "Set datasource uid DS_PROMETHEUS or replace the datasource uid before import.",
        },
    }


def monitoring_export_status() -> dict[str, Any]:
    datasource_uid = os.getenv("AGENT_GRAFANA_DATASOURCE_UID", "${DS_PROMETHEUS}").strip() or "${DS_PROMETHEUS}"
    return {
        "prometheus": {
            "enabled": True,
            "path": "/api/v1/agents/ops-status/metrics",
            "content_type": "text/plain; version=0.0.4; charset=utf-8",
            "scrape_job_example": {
                "job_name": "agent-runtime-ops",
                "metrics_path": "/api/v1/agents/ops-status/metrics",
                "static_configs": [{"targets": ["<runtime-host>"]}],
                "authorization": "send an operator/admin credential and X-User-Role header through your gateway",
            },
        },
        "grafana": {
            "enabled": True,
            "path": "/api/v1/agents/ops-status/grafana-dashboard",
            "dashboard_uid": "agent-runtime-ops",
            "datasource_uid": datasource_uid,
        },
    }


def get_runbook_entries(subsystem: str) -> list[dict[str, Any]]:
    entries = []
    for entry in ALL_RUNBOOK_ENTRIES:
        if entry.subsystem != subsystem:
            continue
        entries.append({
            "subsystem": entry.subsystem,
            "scenario": entry.scenario,
            "severity": entry.severity.value,
            "symptoms": entry.symptoms,
            "diagnosis_steps": entry.diagnosis_steps,
            "recovery_actions": entry.recovery_actions,
            "escalation": entry.escalation,
        })
    return entries


def get_all_runbook_entries() -> list[dict[str, Any]]:
    return [
        {
            "subsystem": entry.subsystem,
            "scenario": entry.scenario,
            "severity": entry.severity.value,
            "symptoms": entry.symptoms,
            "diagnosis_steps": entry.diagnosis_steps,
            "recovery_actions": entry.recovery_actions,
            "escalation": entry.escalation,
        }
        for entry in ALL_RUNBOOK_ENTRIES
    ]


def grafana_dashboard_json(**kwargs: Any) -> str:
    return json.dumps(build_grafana_dashboard(**kwargs), ensure_ascii=False, indent=2)
