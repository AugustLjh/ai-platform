from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


NETWORK_TOOL_NAMES = {
    "fetch_url",
    "open_page",
    "extract_page_text",
    "web_search",
    "download_file",
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_snapshot",
    "browser_close",
    "browser_verify",
    "pdf_extract",
}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _serialize_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))


@dataclass(frozen=True)
class TenantGovernanceConfig:
    window_hours: int = 24
    max_active_runs: int = 0
    max_runs_per_window: int = 0
    max_tool_calls_per_window: int = 0
    max_network_tool_calls_per_window: int = 0
    max_workspace_bytes: int = 0
    max_workspace_count: int = 0
    warning_percent: float = 80.0
    enforcement_enabled: bool = False

    @classmethod
    def from_env(cls) -> "TenantGovernanceConfig":
        return cls(
            window_hours=max(1, _env_int("AGENT_TENANT_QUOTA_WINDOW_HOURS", 24)),
            max_active_runs=_env_int("AGENT_TENANT_MAX_ACTIVE_RUNS", 0),
            max_runs_per_window=_env_int("AGENT_TENANT_MAX_RUNS_PER_WINDOW", 0),
            max_tool_calls_per_window=_env_int("AGENT_TENANT_MAX_TOOL_CALLS_PER_WINDOW", 0),
            max_network_tool_calls_per_window=_env_int("AGENT_TENANT_MAX_NETWORK_TOOL_CALLS_PER_WINDOW", 0),
            max_workspace_bytes=_env_int("AGENT_TENANT_MAX_WORKSPACE_BYTES", 0),
            max_workspace_count=_env_int("AGENT_TENANT_MAX_WORKSPACE_COUNT", 0),
            warning_percent=min(100.0, _env_float("AGENT_TENANT_QUOTA_WARNING_PERCENT", 80.0)),
            enforcement_enabled=_env_bool("AGENT_TENANT_QUOTA_ENFORCEMENT_ENABLED", False),
        )

    def model_dump(self) -> dict[str, Any]:
        return {
            "window_hours": self.window_hours,
            "max_active_runs": self.max_active_runs,
            "max_runs_per_window": self.max_runs_per_window,
            "max_tool_calls_per_window": self.max_tool_calls_per_window,
            "max_network_tool_calls_per_window": self.max_network_tool_calls_per_window,
            "max_workspace_bytes": self.max_workspace_bytes,
            "max_workspace_count": self.max_workspace_count,
            "warning_percent": self.warning_percent,
            "enforcement_enabled": self.enforcement_enabled,
        }


def _metric(
    *,
    key: str,
    label: str,
    used: int,
    limit: int,
    unit: str,
    warning_percent: float,
    enforced: bool,
) -> dict[str, Any]:
    used = max(0, int(used or 0))
    limit = max(0, int(limit or 0))
    if limit <= 0:
        return {
            "key": key,
            "label": label,
            "used": used,
            "limit": 0,
            "remaining": None,
            "unit": unit,
            "utilization_percent": 0.0,
            "status": "unlimited",
            "enforced": False,
        }

    utilization = round((used / limit) * 100, 2)
    if used >= limit:
        status = "exceeded"
    elif utilization >= warning_percent:
        status = "warning"
    else:
        status = "healthy"
    return {
        "key": key,
        "label": label,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "unit": unit,
        "utilization_percent": utilization,
        "status": status,
        "enforced": bool(enforced),
    }


def build_tenant_governance_snapshot(
    *,
    tenant_id: str,
    config: TenantGovernanceConfig,
    run_usage: dict[str, Any] | None = None,
    tool_usage: dict[str, Any] | None = None,
    subagent_usage: dict[str, Any] | None = None,
    workspace_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_usage = run_usage or {}
    tool_usage = tool_usage or {}
    subagent_usage = subagent_usage or {}
    workspace_usage = workspace_usage or {}
    metrics = [
        _metric(
            key="active_runs",
            label="Active runs",
            used=int(run_usage.get("active_runs") or 0),
            limit=config.max_active_runs,
            unit="runs",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
        _metric(
            key="runs_per_window",
            label=f"Runs / {config.window_hours}h",
            used=int(run_usage.get("runs_in_window") or 0),
            limit=config.max_runs_per_window,
            unit="runs",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
        _metric(
            key="tool_calls_per_window",
            label=f"Tool calls / {config.window_hours}h",
            used=int(tool_usage.get("tool_calls_in_window") or 0),
            limit=config.max_tool_calls_per_window,
            unit="calls",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
        _metric(
            key="network_tool_calls_per_window",
            label=f"Network tool calls / {config.window_hours}h",
            used=int(tool_usage.get("network_tool_calls_in_window") or 0),
            limit=config.max_network_tool_calls_per_window,
            unit="calls",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
        _metric(
            key="workspace_bytes",
            label="Workspace bytes",
            used=int(workspace_usage.get("total_size_bytes") or 0),
            limit=config.max_workspace_bytes,
            unit="bytes",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
        _metric(
            key="workspace_count",
            label="Workspace count",
            used=int(workspace_usage.get("workspace_count") or 0),
            limit=config.max_workspace_count,
            unit="workspaces",
            warning_percent=config.warning_percent,
            enforced=config.enforcement_enabled,
        ),
    ]
    limited_metrics = [item for item in metrics if int(item.get("limit") or 0) > 0]
    blocking_metrics = [item for item in limited_metrics if item["status"] == "exceeded"]
    warning_metrics = [item for item in limited_metrics if item["status"] == "warning"]
    if blocking_metrics:
        status = "blocked" if config.enforcement_enabled else "exceeded"
    elif warning_metrics:
        status = "warning"
    else:
        status = "healthy"
    return {
        "tenant_id": tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": config.window_hours,
        "enforcement_enabled": config.enforcement_enabled,
        "status": status,
        "summary": _summary(status, blocking_metrics, warning_metrics, len(limited_metrics)),
        "config": config.model_dump(),
        "usage": {
            "runs": dict(run_usage),
            "tools": dict(tool_usage),
            "subagents": dict(subagent_usage),
            "workspaces": dict(workspace_usage),
        },
        "metrics": metrics,
        "blocking_metrics": blocking_metrics,
        "warning_metrics": warning_metrics,
        "recovery_actions": _recovery_actions(blocking_metrics, warning_metrics),
    }


def _summary(
    status: str,
    blocking_metrics: list[dict[str, Any]],
    warning_metrics: list[dict[str, Any]],
    limited_metric_count: int,
) -> str:
    if limited_metric_count == 0:
        return "tenant quotas are advisory only; no hard limits are configured"
    if blocking_metrics:
        names = ", ".join(item["key"] for item in blocking_metrics[:3])
        return f"tenant quota exceeded for {names}"
    if warning_metrics:
        names = ", ".join(item["key"] for item in warning_metrics[:3])
        return f"tenant quota is approaching limits for {names}"
    if status == "healthy":
        return "tenant usage is within configured quotas"
    return "tenant governance snapshot is available"


def _recovery_actions(
    blocking_metrics: list[dict[str, Any]],
    warning_metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    metric_keys = {item["key"] for item in [*blocking_metrics, *warning_metrics]}
    actions: list[dict[str, Any]] = []
    if "active_runs" in metric_keys:
        actions.append(
            {
                "key": "review_active_runs",
                "label": "Review active runs",
                "category": "tenant_concurrency",
                "priority": "high",
                "requires_confirmation": False,
            }
        )
    if "network_tool_calls_per_window" in metric_keys:
        actions.append(
            {
                "key": "reduce_network_research",
                "label": "Reduce network research tools",
                "category": "tenant_network_quota",
                "priority": "medium",
                "requires_confirmation": False,
            }
        )
    if "tool_calls_per_window" in metric_keys:
        actions.append(
            {
                "key": "inspect_tool_usage",
                "label": "Inspect high tool usage",
                "category": "tenant_tool_quota",
                "priority": "medium",
                "requires_confirmation": False,
            }
        )
    if "workspace_bytes" in metric_keys or "workspace_count" in metric_keys:
        actions.append(
            {
                "key": "cleanup_tenant_workspaces",
                "label": "Cleanup tenant workspaces",
                "category": "tenant_workspace_quota",
                "priority": "medium",
                "requires_confirmation": True,
            }
        )
    return actions


async def fetch_tenant_runtime_usage(
    db_pool,
    *,
    tenant_id: str,
    window_hours: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    serialized_tenant_id = _serialize_uuid(tenant_id)
    run_row = await db_pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE status IN ('queued', 'running', 'waiting_user')) AS active_runs,
            COUNT(*) FILTER (WHERE created_at >= now() - ($2::int * interval '1 hour')) AS runs_in_window,
            COUNT(*) AS total_runs,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed_runs,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed_runs,
            COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_runs
        FROM agent_runs
        WHERE tenant_id = $1
        """,
        serialized_tenant_id,
        int(window_hours),
    )
    tool_row = await db_pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE t.created_at >= now() - ($2::int * interval '1 hour')) AS tool_calls_in_window,
            COUNT(*) FILTER (
                WHERE t.created_at >= now() - ($2::int * interval '1 hour')
                  AND (t.tool_kind IN ('web', 'browser') OR t.tool_name = ANY($3::varchar[]))
            ) AS network_tool_calls_in_window,
            COUNT(*) AS total_tool_calls,
            COUNT(*) FILTER (WHERE t.status = 'failed') AS failed_tool_calls
        FROM agent_tool_calls t
        JOIN agent_runs r ON r.id = t.run_id
        WHERE r.tenant_id = $1
        """,
        serialized_tenant_id,
        int(window_hours),
        sorted(NETWORK_TOOL_NAMES),
    )
    subagent_row = await db_pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE i.created_at >= now() - ($2::int * interval '1 hour')) AS invocations_in_window,
            COUNT(*) FILTER (WHERE i.status IN ('pending', 'running')) AS active_invocations,
            COUNT(*) AS total_invocations
        FROM agent_subagent_invocations i
        JOIN agent_runs r ON r.id = i.parent_run_id
        WHERE r.tenant_id = $1
        """,
        serialized_tenant_id,
        int(window_hours),
    )
    return _row_dict(run_row), _row_dict(tool_row), _row_dict(subagent_row)


def _row_dict(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    return {key: int(value or 0) for key, value in dict(row).items()}
