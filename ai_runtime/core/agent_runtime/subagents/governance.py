from __future__ import annotations

from typing import Any

from ai_runtime.core.agent_runtime.models import AgentRun
from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


GOVERNANCE_PROTOCOL_VERSION = "managed-subagent.governance.v1"

_ACTIVE_CHILD_STATUSES = {"queued", "running", "waiting_user"}
_FAILED_CHILD_STATUSES = {"failed", "cancelled"}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _coerce_non_negative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _coerce_positive_seconds(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return min(parsed, 24 * 60 * 60)


def _coerce_positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _coerce_non_negative_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def resolve_timeout_seconds(target: SubagentTarget) -> float | None:
    policy = target.runtime_policy or {}
    budget_policy = target.budget_policy or {}
    value = _first_value(
        policy.get("timeout_seconds"),
        policy.get("deadline_seconds"),
        policy.get("max_duration_seconds"),
        budget_policy.get("timeout_seconds"),
        budget_policy.get("deadline_seconds"),
        target.metadata.get("timeout_seconds"),
    )
    if value in (None, ""):
        value = _first_value(policy.get("timeout_ms"), budget_policy.get("timeout_ms"))
        parsed_ms = _coerce_positive_float(value)
        return parsed_ms / 1000 if parsed_ms is not None else None
    return _coerce_positive_seconds(value)


def resolve_max_retry_attempts(target: SubagentTarget) -> int | None:
    policy = target.runtime_policy or {}
    budget_policy = target.budget_policy or {}
    return _coerce_non_negative_int(
        _first_value(
            policy.get("max_retry_attempts"),
            policy.get("max_retries"),
            budget_policy.get("max_retry_attempts"),
            target.metadata.get("max_retry_attempts"),
        )
    )


def resolve_max_parent_delegations(target: SubagentTarget) -> int | None:
    policy = target.runtime_policy or {}
    budget_policy = target.budget_policy or {}
    return _coerce_non_negative_int(
        _first_value(
            policy.get("max_parent_delegations"),
            policy.get("max_delegations_per_parent"),
            policy.get("max_child_runs"),
            budget_policy.get("max_child_runs"),
            budget_policy.get("max_delegations"),
            target.metadata.get("max_parent_delegations"),
        )
    )


def resolve_max_concurrent_delegations(target: SubagentTarget) -> int | None:
    policy = target.runtime_policy or {}
    budget_policy = target.budget_policy or {}
    return _coerce_non_negative_int(
        _first_value(
            policy.get("max_concurrent_delegations"),
            policy.get("concurrency_limit"),
            policy.get("max_pending_children"),
            budget_policy.get("max_concurrent_delegations"),
            target.metadata.get("max_concurrent_delegations"),
        )
    )


def resolve_waiting_user_propagation(target: SubagentTarget) -> str:
    raw_value = str(
        (target.runtime_policy or {}).get("waiting_user_propagation")
        or (target.runtime_policy or {}).get("waiting_user_strategy")
        or target.metadata.get("waiting_user_propagation")
        or "bubble_to_parent"
    ).strip().lower()
    if not raw_value:
        return "bubble_to_parent"

    aliases = {
        "bubble": "bubble_to_parent",
        "propagate": "bubble_to_parent",
        "bubble_to_parent": "bubble_to_parent",
        "bubble-to-parent": "bubble_to_parent",
        "bubble_to_parent_release_slot": "bubble_to_parent_release_slot",
        "bubble-to-parent-release-slot": "bubble_to_parent_release_slot",
        "bubble_to_parent_non_blocking": "bubble_to_parent_non_blocking",
        "bubble-to-parent-non-blocking": "bubble_to_parent_non_blocking",
        "child_only": "child_only",
        "child-only": "child_only",
        "stay_with_child": "child_only",
        "stay-with-child": "child_only",
        "continue_parent": "continue_parent",
        "continue-parent": "continue_parent",
        "continue_parent_non_blocking": "continue_parent_non_blocking",
        "continue-parent-non-blocking": "continue_parent_non_blocking",
        "non_blocking": "continue_parent_non_blocking",
        "non-blocking": "continue_parent_non_blocking",
        "release_concurrency_slot": "continue_parent_non_blocking",
        "release-concurrency-slot": "continue_parent_non_blocking",
    }
    return aliases.get(raw_value, raw_value)


def should_bubble_waiting_user_to_parent(propagation: str | None) -> bool:
    normalized = str(propagation or "").strip().lower()
    if not normalized:
        return True
    return normalized in {
        "bubble_to_parent",
        "bubble_to_parent_release_slot",
        "bubble_to_parent_non_blocking",
    }


def resolve_waiting_user_counts_as_active_child(target: SubagentTarget) -> bool:
    policy = target.runtime_policy or {}
    metadata = target.metadata or {}
    explicit = _first_value(
        policy.get("waiting_user_counts_as_active_child"),
        policy.get("counts_waiting_user_as_active_child"),
        policy.get("waiting_user_holds_concurrency_slot"),
        metadata.get("waiting_user_counts_as_active_child"),
    )
    parsed = _coerce_bool(explicit)
    if parsed is not None:
        return parsed

    propagation = resolve_waiting_user_propagation(target).lower()
    if propagation in {
        "bubble_to_parent_release_slot",
        "bubble_to_parent_non_blocking",
        "release_concurrency_slot",
        "non_blocking",
    }:
        return False
    return True


def _extract_child_status(observation: dict[str, Any], target_slug: str) -> str | None:
    if str(observation.get("delegate_target") or "").strip() != target_slug:
        return None
    result = observation.get("result")
    if isinstance(result, dict):
        status = str(result.get("status") or "").strip().lower()
        if status:
            return status
    status = str(observation.get("status") or "").strip().lower()
    return status or None


def _normalize_usage_snapshot(usage: dict[str, Any] | None, *, source: str | None = None) -> dict[str, Any]:
    usage = usage if isinstance(usage, dict) else {}
    prompt_tokens = _coerce_non_negative_int(_first_value(usage.get("prompt_tokens"), usage.get("input_tokens")))
    completion_tokens = _coerce_non_negative_int(
        _first_value(usage.get("completion_tokens"), usage.get("output_tokens"))
    )
    total_tokens = _coerce_non_negative_int(usage.get("total_tokens"))
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    cost_usd = _coerce_non_negative_float(_first_value(usage.get("cost_usd"), usage.get("cost"), usage.get("usd")))
    resolved_source = str(source or usage.get("source") or "").strip()
    has_data = any(value is not None for value in (prompt_tokens, completion_tokens, total_tokens, cost_usd))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "source": resolved_source,
        "has_data": has_data,
    }


def merge_governance_usage_snapshots(*snapshots: dict[str, Any] | None, source: str | None = None) -> dict[str, Any]:
    normalized = [_normalize_usage_snapshot(snapshot) for snapshot in snapshots if isinstance(snapshot, dict)]
    normalized = [snapshot for snapshot in normalized if snapshot.get("has_data")]
    if not normalized:
        return _normalize_usage_snapshot({}, source=source)

    prompt_values = [snapshot.get("prompt_tokens") for snapshot in normalized if snapshot.get("prompt_tokens") is not None]
    completion_values = [
        snapshot.get("completion_tokens")
        for snapshot in normalized
        if snapshot.get("completion_tokens") is not None
    ]
    total_values = [snapshot.get("total_tokens") for snapshot in normalized if snapshot.get("total_tokens") is not None]
    cost_values = [snapshot.get("cost_usd") for snapshot in normalized if snapshot.get("cost_usd") is not None]
    sources = [snapshot.get("source") for snapshot in normalized if str(snapshot.get("source") or "").strip()]

    prompt_tokens = sum(prompt_values) if prompt_values else None
    completion_tokens = sum(completion_values) if completion_values else None
    total_tokens = sum(total_values) if total_values else None
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    cost_usd = sum(cost_values) if cost_values else None

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "source": str(source or ", ".join(dict.fromkeys(sources))).strip(),
        "has_data": True,
    }


def _extract_waiting_user_propagation(observation: dict[str, Any], target_slug: str) -> str:
    if str(observation.get("delegate_target") or "").strip() != target_slug:
        return ""
    result = observation.get("result")
    if not isinstance(result, dict):
        return ""

    waiting_user_policy = result.get("waiting_user_policy")
    if isinstance(waiting_user_policy, dict):
        propagation = str(waiting_user_policy.get("propagation") or "").strip()
        if propagation:
            return propagation

    governance_policy = result.get("governance_policy")
    if isinstance(governance_policy, dict):
        waiting_user = governance_policy.get("waiting_user")
        if isinstance(waiting_user, dict):
            propagation = str(waiting_user.get("propagation") or "").strip()
            if propagation:
                return propagation
    return ""


def _classify_waiting_user_strategy(propagation: str | None) -> str:
    normalized = str(propagation or "").strip().lower()
    if not normalized:
        normalized = "bubble_to_parent"
    if should_bubble_waiting_user_to_parent(normalized):
        return "bubble_to_parent"
    if normalized.startswith("continue_parent"):
        return "continue_parent"
    return "child_only"


def _extract_observed_usage(observation: dict[str, Any], target_slug: str) -> dict[str, Any]:
    if str(observation.get("delegate_target") or "").strip() != target_slug:
        return _normalize_usage_snapshot({})
    result = observation.get("result")
    if not isinstance(result, dict):
        return _normalize_usage_snapshot({})

    governance_policy = result.get("governance_policy")
    budget = governance_policy.get("budget") if isinstance(governance_policy, dict) else {}
    candidates = [
        budget.get("last_invocation_usage") if isinstance(budget, dict) else None,
        result.get("governance_usage"),
        budget.get("usage") if isinstance(budget, dict) else None,
        result.get("usage"),
        result.get("token_usage"),
    ]
    for candidate in candidates:
        normalized = _normalize_usage_snapshot(candidate)
        if normalized["has_data"]:
            return normalized
    return _normalize_usage_snapshot({})


def _default_history(target_slug: str) -> dict[str, Any]:
    return {
        "target_slug": target_slug,
        "attempt_count": 0,
        "failed_attempt_count": 0,
        "active_child_count": 0,
        "waiting_user_count": 0,
        "bubble_to_parent_count": 0,
        "continue_parent_count": 0,
        "child_only_count": 0,
        "statuses": [],
        "waiting_user_strategies": [],
    }


def _normalize_history(raw: dict[str, Any] | None, *, target_slug: str) -> dict[str, Any]:
    base = _default_history(target_slug)
    payload = raw if isinstance(raw, dict) else {}
    base.update(
        {
            "target_slug": str(payload.get("target_slug") or target_slug),
            "attempt_count": int(payload.get("attempt_count") or 0),
            "failed_attempt_count": int(payload.get("failed_attempt_count") or 0),
            "active_child_count": int(payload.get("active_child_count") or 0),
            "waiting_user_count": int(payload.get("waiting_user_count") or 0),
            "bubble_to_parent_count": int(payload.get("bubble_to_parent_count") or 0),
            "continue_parent_count": int(payload.get("continue_parent_count") or 0),
            "child_only_count": int(payload.get("child_only_count") or 0),
            "statuses": list(payload.get("statuses") or [])[-12:],
            "waiting_user_strategies": list(payload.get("waiting_user_strategies") or [])[-12:],
        }
    )
    return base


def _active_child_key(child_run_id: str | None, invocation_id: str | None, fallback_index: int) -> str:
    child_run_id = str(child_run_id or "").strip()
    invocation_id = str(invocation_id or "").strip()
    if child_run_id:
        return f"child:{child_run_id}"
    if invocation_id:
        return f"invocation:{invocation_id}"
    return f"attempt:{fallback_index}"


def _normalize_active_children(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        child_key = str(key or "").strip()
        if not child_key:
            continue
        normalized[child_key] = {
            "child_run_id": str(value.get("child_run_id") or "").strip() or None,
            "invocation_id": str(value.get("invocation_id") or "").strip() or None,
            "status": str(value.get("status") or "").strip().lower() or "running",
            "counts_as_active_child": bool(value.get("counts_as_active_child", True)),
            "waiting_user_propagation": str(value.get("waiting_user_propagation") or "").strip() or None,
            "question": str(value.get("question") or "").strip() or None,
            "waiting_user_path": list(value.get("waiting_user_path") or []),
        }
    return normalized


def _normalize_recent_outcomes(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw[-12:]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "status": str(item.get("status") or "").strip().lower() or "completed",
                "child_run_id": str(item.get("child_run_id") or "").strip() or None,
                "invocation_id": str(item.get("invocation_id") or "").strip() or None,
                "waiting_user_propagation": str(item.get("waiting_user_propagation") or "").strip() or None,
                "usage": _normalize_usage_snapshot(item.get("usage")),
                "question": str(item.get("question") or "").strip() or None,
                "waiting_user_path": list(item.get("waiting_user_path") or []),
            }
        )
    return normalized


def _matches_child_reference(
    child: dict[str, Any] | None,
    *,
    child_run_id: str | None = None,
    invocation_id: str | None = None,
) -> bool:
    if not isinstance(child, dict):
        return False
    normalized_child_run_id = str(child_run_id or "").strip()
    normalized_invocation_id = str(invocation_id or "").strip()
    if normalized_child_run_id and str(child.get("child_run_id") or "").strip() == normalized_child_run_id:
        return True
    if normalized_invocation_id and str(child.get("invocation_id") or "").strip() == normalized_invocation_id:
        return True
    return False


def build_waiting_user_path(
    *,
    parent_run_id: str,
    child_run_id: str | None,
    child_waiting_user_path: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    parent_node = {
        "run_id": str(parent_run_id or "").strip() or None,
        "role": "parent",
        "status": "running",
    }
    normalized_child_run_id = str(child_run_id or "").strip() or None
    normalized_path: list[dict[str, Any]] = []
    normalized_signatures: set[tuple[str | None, str | None, str | None]] = set()

    for node in child_waiting_user_path or []:
        if not isinstance(node, dict):
            continue
        normalized = {
            "run_id": str(node.get("run_id") or "").strip() or None,
            "role": str(node.get("role") or "").strip() or None,
            "status": str(node.get("status") or "").strip() or None,
        }
        signature = (normalized["run_id"], normalized["role"], normalized["status"])
        if signature in normalized_signatures:
            continue
        normalized_signatures.add(signature)
        normalized_path.append(normalized)

    if normalized_path:
        first = normalized_path[0]
        if first.get("run_id") == parent_node["run_id"] and first.get("role") == parent_node["role"]:
            if not first.get("status"):
                first["status"] = parent_node["status"]
            return normalized_path

    merged_path = [parent_node]
    merged_signatures = {(parent_node["run_id"], parent_node["role"], parent_node["status"])}
    for node in normalized_path:
        signature = (node["run_id"], node["role"], node["status"])
        if signature in merged_signatures:
            continue
        merged_path.append(node)
        merged_signatures.add(signature)

    if normalized_child_run_id and not any(node.get("run_id") == normalized_child_run_id for node in merged_path):
        merged_path.append(
            {
                "run_id": normalized_child_run_id,
                "role": "child",
                "status": "waiting_user",
            }
        )
    return merged_path


def _normalize_ledger_entry(raw: dict[str, Any] | None, *, target_slug: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    history = _normalize_history(payload.get("history"), target_slug=target_slug)
    active_children = _normalize_active_children(payload.get("active_children"))
    history["active_child_count"] = sum(
        1 for child in active_children.values() if bool(child.get("counts_as_active_child"))
    )
    usage = _normalize_usage_snapshot(payload.get("usage"))
    last_invocation_usage = _normalize_usage_snapshot(payload.get("last_invocation_usage"))
    if not usage["has_data"] and last_invocation_usage["has_data"]:
        usage = merge_governance_usage_snapshots(last_invocation_usage, source="ledger")

    latest_waiting_user = payload.get("latest_waiting_user") if isinstance(payload.get("latest_waiting_user"), dict) else {}
    return {
        "target_slug": target_slug,
        "history": history,
        "usage": usage,
        "last_invocation_usage": last_invocation_usage,
        "active_children": active_children,
        "latest_waiting_user": {
            "child_run_id": str(latest_waiting_user.get("child_run_id") or "").strip() or None,
            "invocation_id": str(latest_waiting_user.get("invocation_id") or "").strip() or None,
            "question": str(latest_waiting_user.get("question") or "").strip() or None,
            "waiting_user_path": list(latest_waiting_user.get("waiting_user_path") or []),
            "waiting_user_propagation": str(latest_waiting_user.get("waiting_user_propagation") or "").strip() or None,
        },
        "recent_outcomes": _normalize_recent_outcomes(payload.get("recent_outcomes")),
    }


def _get_ledger_target_entry(runtime_context: dict[str, Any], *, target_slug: str) -> dict[str, Any] | None:
    ledger = runtime_context.get("subagent_governance_ledger")
    if not isinstance(ledger, dict):
        return None
    targets = ledger.get("targets")
    if not isinstance(targets, dict):
        return None
    raw_entry = targets.get(target_slug)
    if not isinstance(raw_entry, dict):
        return None
    return _normalize_ledger_entry(raw_entry, target_slug=target_slug)


def _upsert_ledger_target_entry(runtime_context: dict[str, Any], *, target_slug: str, entry: dict[str, Any]) -> dict[str, Any]:
    ledger = runtime_context.get("subagent_governance_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
    targets = ledger.get("targets")
    if not isinstance(targets, dict):
        targets = {}
    targets[target_slug] = {
        "target_slug": target_slug,
        "history": dict(entry.get("history") or {}),
        "usage": dict(entry.get("usage") or {}),
        "last_invocation_usage": dict(entry.get("last_invocation_usage") or {}),
        "active_children": dict(entry.get("active_children") or {}),
        "latest_waiting_user": dict(entry.get("latest_waiting_user") or {}),
        "recent_outcomes": list(entry.get("recent_outcomes") or []),
    }
    runtime_context["subagent_governance_ledger"] = {
        "protocol_version": GOVERNANCE_PROTOCOL_VERSION,
        "targets": targets,
    }
    return runtime_context["subagent_governance_ledger"]


def summarize_delegation_history(
    runtime_context: dict[str, Any],
    *,
    target_slug: str,
    waiting_user_counts_as_active_child: bool = True,
) -> dict[str, Any]:
    ledger_entry = _get_ledger_target_entry(runtime_context, target_slug=target_slug)
    if ledger_entry is not None:
        history = _normalize_history(ledger_entry.get("history"), target_slug=target_slug)
        active_children = _normalize_active_children(ledger_entry.get("active_children"))
        history["active_child_count"] = sum(
            1 for child in active_children.values() if bool(child.get("counts_as_active_child"))
        )
        return history

    step_history = runtime_context.get("step_history")
    if not isinstance(step_history, list):
        step_history = []

    statuses: list[str] = []
    waiting_user_count = 0
    bubble_to_parent_count = 0
    continue_parent_count = 0
    child_only_count = 0
    waiting_user_strategies: list[str] = []
    for item in step_history:
        if not isinstance(item, dict):
            continue
        status = _extract_child_status(item, target_slug)
        if status:
            statuses.append(status)
            if status == "waiting_user":
                waiting_user_count += 1
                strategy = _classify_waiting_user_strategy(_extract_waiting_user_propagation(item, target_slug))
                waiting_user_strategies.append(strategy)
                if strategy == "bubble_to_parent":
                    bubble_to_parent_count += 1
                elif strategy == "continue_parent":
                    continue_parent_count += 1
                else:
                    child_only_count += 1

    return {
        "target_slug": target_slug,
        "attempt_count": len(statuses),
        "failed_attempt_count": sum(1 for status in statuses if status in _FAILED_CHILD_STATUSES),
        "active_child_count": sum(
            1
            for status in statuses
            if status in (_ACTIVE_CHILD_STATUSES if waiting_user_counts_as_active_child else {"queued", "running"})
        ),
        "waiting_user_count": waiting_user_count,
        "bubble_to_parent_count": bubble_to_parent_count,
        "continue_parent_count": continue_parent_count,
        "child_only_count": child_only_count,
        "statuses": statuses[-12:],
        "waiting_user_strategies": waiting_user_strategies[-12:],
    }


def summarize_delegation_usage_history(
    runtime_context: dict[str, Any],
    *,
    target_slug: str,
) -> dict[str, Any]:
    ledger_entry = _get_ledger_target_entry(runtime_context, target_slug=target_slug)
    if ledger_entry is not None:
        usage = _normalize_usage_snapshot(ledger_entry.get("usage"), source="ledger")
        usage["observation_count"] = len(ledger_entry.get("recent_outcomes") or [])
        return usage

    step_history = runtime_context.get("step_history")
    if not isinstance(step_history, list):
        step_history = []

    snapshots: list[dict[str, Any]] = []
    for item in step_history:
        if not isinstance(item, dict):
            continue
        usage = _extract_observed_usage(item, target_slug)
        if usage["has_data"]:
            snapshots.append(usage)

    merged = merge_governance_usage_snapshots(*snapshots, source="step_history")
    merged["observation_count"] = len(snapshots)
    return merged


def append_delegation_outcome(
    history: dict[str, Any] | None,
    *,
    status: str,
    waiting_user_propagation: str | None = None,
    waiting_user_counts_as_active_child: bool = True,
) -> dict[str, Any]:
    base = dict(history or {})
    statuses = list(base.get("statuses") or [])
    waiting_user_strategies = list(base.get("waiting_user_strategies") or [])
    normalized_status = str(status or "").strip().lower() or "completed"
    statuses.append(normalized_status)

    updated = {
        "target_slug": str(base.get("target_slug") or ""),
        "attempt_count": int(base.get("attempt_count") or 0) + 1,
        "failed_attempt_count": int(base.get("failed_attempt_count") or 0),
        "active_child_count": int(base.get("active_child_count") or 0),
        "waiting_user_count": int(base.get("waiting_user_count") or 0),
        "bubble_to_parent_count": int(base.get("bubble_to_parent_count") or 0),
        "continue_parent_count": int(base.get("continue_parent_count") or 0),
        "child_only_count": int(base.get("child_only_count") or 0),
        "statuses": statuses[-12:],
        "waiting_user_strategies": waiting_user_strategies[-12:],
    }

    if normalized_status in _FAILED_CHILD_STATUSES:
        updated["failed_attempt_count"] += 1
    if normalized_status in {"queued", "running"} or (
        normalized_status == "waiting_user" and waiting_user_counts_as_active_child
    ):
        updated["active_child_count"] += 1
    if normalized_status == "waiting_user":
        updated["waiting_user_count"] += 1
        strategy = _classify_waiting_user_strategy(waiting_user_propagation)
        updated["waiting_user_strategies"] = (updated["waiting_user_strategies"] + [strategy])[-12:]
        if strategy == "bubble_to_parent":
            updated["bubble_to_parent_count"] += 1
        elif strategy == "continue_parent":
            updated["continue_parent_count"] += 1
        else:
            updated["child_only_count"] += 1

    return updated


def record_delegation_outcome(
    runtime_context: dict[str, Any],
    *,
    target_slug: str,
    status: str,
    child_run_id: str | None = None,
    invocation_id: str | None = None,
    usage: dict[str, Any] | None = None,
    waiting_user_propagation: str | None = None,
    waiting_user_counts_as_active_child: bool = True,
    question: str | None = None,
    waiting_user_path: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing = _get_ledger_target_entry(runtime_context, target_slug=target_slug)
    if existing is None:
        existing = {
            "target_slug": target_slug,
            "history": summarize_delegation_history(
                runtime_context,
                target_slug=target_slug,
                waiting_user_counts_as_active_child=waiting_user_counts_as_active_child,
            ),
            "usage": summarize_delegation_usage_history(
                runtime_context,
                target_slug=target_slug,
            ),
            "last_invocation_usage": _normalize_usage_snapshot({}),
            "active_children": {},
            "latest_waiting_user": {},
            "recent_outcomes": [],
        }

    active_children = _normalize_active_children(existing.get("active_children"))
    child_key = _active_child_key(
        child_run_id,
        invocation_id,
        int(existing.get("history", {}).get("attempt_count") or 0) + 1,
    )
    normalized_status = str(status or "").strip().lower() or "completed"
    normalized_usage = _normalize_usage_snapshot(usage)
    normalized_path = list(waiting_user_path or [])

    if normalized_status in {"queued", "running"} or (
        normalized_status == "waiting_user" and waiting_user_counts_as_active_child
    ):
        active_children[child_key] = {
            "child_run_id": str(child_run_id or "").strip() or None,
            "invocation_id": str(invocation_id or "").strip() or None,
            "status": normalized_status,
            "counts_as_active_child": normalized_status != "waiting_user" or waiting_user_counts_as_active_child,
            "waiting_user_propagation": waiting_user_propagation,
            "question": str(question or "").strip() or None,
            "waiting_user_path": normalized_path,
        }
    else:
        active_children.pop(child_key, None)
        for key, child in list(active_children.items()):
            if child_run_id and child.get("child_run_id") == child_run_id:
                active_children.pop(key, None)
            elif invocation_id and child.get("invocation_id") == invocation_id:
                active_children.pop(key, None)

    history = append_delegation_outcome(
        existing.get("history"),
        status=normalized_status,
        waiting_user_propagation=waiting_user_propagation,
        waiting_user_counts_as_active_child=waiting_user_counts_as_active_child,
    )
    history["active_child_count"] = sum(
        1 for child in active_children.values() if bool(child.get("counts_as_active_child"))
    )
    prior_usage = _normalize_usage_snapshot(existing.get("usage"))
    cumulative_usage = merge_governance_usage_snapshots(
        prior_usage,
        normalized_usage,
        source="ledger",
    ) if normalized_usage.get("has_data") else prior_usage
    latest_waiting_user = dict(existing.get("latest_waiting_user") or {})
    if normalized_status == "waiting_user":
        latest_waiting_user = {
            "child_run_id": str(child_run_id or "").strip() or None,
            "invocation_id": str(invocation_id or "").strip() or None,
            "question": str(question or "").strip() or None,
            "waiting_user_path": normalized_path,
            "waiting_user_propagation": str(waiting_user_propagation or "").strip() or None,
        }
    elif _matches_child_reference(
        latest_waiting_user,
        child_run_id=child_run_id,
        invocation_id=invocation_id,
    ):
        latest_waiting_user = {}
        for child in active_children.values():
            if str(child.get("status") or "").strip().lower() != "waiting_user":
                continue
            latest_waiting_user = {
                "child_run_id": str(child.get("child_run_id") or "").strip() or None,
                "invocation_id": str(child.get("invocation_id") or "").strip() or None,
                "question": str(child.get("question") or "").strip() or None,
                "waiting_user_path": list(child.get("waiting_user_path") or []),
                "waiting_user_propagation": str(child.get("waiting_user_propagation") or "").strip() or None,
            }
            break
    recent_outcomes = _normalize_recent_outcomes(existing.get("recent_outcomes"))
    recent_outcomes.append(
        {
            "status": normalized_status,
            "child_run_id": str(child_run_id or "").strip() or None,
            "invocation_id": str(invocation_id or "").strip() or None,
            "waiting_user_propagation": str(waiting_user_propagation or "").strip() or None,
            "usage": normalized_usage,
            "question": str(question or "").strip() or None,
            "waiting_user_path": normalized_path,
        }
    )

    entry = {
        "target_slug": target_slug,
        "history": history,
        "usage": cumulative_usage,
        "last_invocation_usage": normalized_usage,
        "active_children": active_children,
        "latest_waiting_user": latest_waiting_user,
        "recent_outcomes": recent_outcomes[-12:],
    }
    _upsert_ledger_target_entry(runtime_context, target_slug=target_slug, entry=entry)
    return _normalize_ledger_entry(entry, target_slug=target_slug)


def _extract_usage_object(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}

    usage = source.get("usage")
    if isinstance(usage, dict):
        return usage

    token_usage = source.get("token_usage")
    if isinstance(token_usage, dict):
        return token_usage

    return source


def extract_governance_usage(
    *,
    child_run: dict[str, Any] | None = None,
    hydrated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    child_run = child_run if isinstance(child_run, dict) else {}
    hydrated = hydrated if isinstance(hydrated, dict) else {}
    child_metadata = child_run.get("metadata") if isinstance(child_run.get("metadata"), dict) else {}
    child_context = child_run.get("context") if isinstance(child_run.get("context"), dict) else {}
    final_output_json = hydrated.get("final_output_json")
    if not isinstance(final_output_json, dict):
        final_output_json = child_run.get("final_output_json") if isinstance(child_run.get("final_output_json"), dict) else {}

    candidates = [
        ("metadata.governance_usage", _extract_usage_object(child_metadata.get("governance_usage"))),
        ("metadata.usage", _extract_usage_object(child_metadata.get("usage"))),
        ("metadata.token_usage", _extract_usage_object(child_metadata.get("token_usage"))),
        ("context.governance_usage", _extract_usage_object(child_context.get("governance_usage"))),
        ("context.usage", _extract_usage_object(child_context.get("usage"))),
        ("context.token_usage", _extract_usage_object(child_context.get("token_usage"))),
        ("final_output_json.usage", _extract_usage_object(final_output_json.get("usage"))),
        ("final_output_json.token_usage", _extract_usage_object(final_output_json.get("token_usage"))),
        ("final_output_json", _extract_usage_object(final_output_json)),
    ]

    for source_name, candidate in candidates:
        prompt_tokens = _coerce_non_negative_int(
            _first_value(candidate.get("prompt_tokens"), candidate.get("input_tokens"))
        )
        completion_tokens = _coerce_non_negative_int(
            _first_value(candidate.get("completion_tokens"), candidate.get("output_tokens"))
        )
        total_tokens = _coerce_non_negative_int(candidate.get("total_tokens"))
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        cost_usd = _coerce_non_negative_float(
            _first_value(candidate.get("cost_usd"), candidate.get("cost"), candidate.get("usd"))
        )

        if all(value is None for value in (prompt_tokens, completion_tokens, total_tokens, cost_usd)):
            continue

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "source": source_name,
            "has_data": True,
        }

    return {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "source": "",
        "has_data": False,
    }


def annotate_governance_policy(
    policy: dict[str, Any],
    *,
    history: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    usage: dict[str, Any] | None = None,
    prior_usage: dict[str, Any] | None = None,
    last_invocation_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = {
        **dict(policy or {}),
        "limits": dict((policy or {}).get("limits") or {}),
        "budget": dict((policy or {}).get("budget") or {}),
        "waiting_user": dict((policy or {}).get("waiting_user") or {}),
        "enforcement": dict((policy or {}).get("enforcement") or {}),
    }

    merged_warnings: list[str] = []
    for item in (policy or {}).get("warnings") or []:
        if item and item not in merged_warnings:
            merged_warnings.append(item)
    for item in warnings or []:
        if item and item not in merged_warnings:
            merged_warnings.append(item)

    prior_usage = _normalize_usage_snapshot(prior_usage)
    last_invocation_usage = _normalize_usage_snapshot(last_invocation_usage)
    if isinstance(usage, dict) and usage:
        usage = _normalize_usage_snapshot(usage)
    else:
        usage = merge_governance_usage_snapshots(prior_usage, last_invocation_usage, source="tracked_child_usage")
    usage_has_data = bool(usage.get("has_data"))
    budget = enriched["budget"]
    max_tokens = _coerce_non_negative_int(_first_value(budget.get("max_tokens"), budget.get("token_limit")))
    max_cost_usd = _coerce_positive_float(_first_value(budget.get("max_cost_usd"), budget.get("cost_limit_usd")))
    total_tokens = _coerce_non_negative_int(usage.get("total_tokens"))
    cost_usd = _coerce_non_negative_float(usage.get("cost_usd"))

    budget["usage"] = {
        "prompt_tokens": _coerce_non_negative_int(usage.get("prompt_tokens")),
        "completion_tokens": _coerce_non_negative_int(usage.get("completion_tokens")),
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "source": str(usage.get("source") or "").strip(),
    }
    budget["prior_usage"] = {
        "prompt_tokens": _coerce_non_negative_int(prior_usage.get("prompt_tokens")),
        "completion_tokens": _coerce_non_negative_int(prior_usage.get("completion_tokens")),
        "total_tokens": _coerce_non_negative_int(prior_usage.get("total_tokens")),
        "cost_usd": _coerce_non_negative_float(prior_usage.get("cost_usd")),
        "source": str(prior_usage.get("source") or "").strip(),
    }
    budget["last_invocation_usage"] = {
        "prompt_tokens": _coerce_non_negative_int(last_invocation_usage.get("prompt_tokens")),
        "completion_tokens": _coerce_non_negative_int(last_invocation_usage.get("completion_tokens")),
        "total_tokens": _coerce_non_negative_int(last_invocation_usage.get("total_tokens")),
        "cost_usd": _coerce_non_negative_float(last_invocation_usage.get("cost_usd")),
        "source": str(last_invocation_usage.get("source") or "").strip(),
    }
    budget["remaining_tokens"] = (
        max(0, max_tokens - total_tokens) if max_tokens is not None and total_tokens is not None else None
    )
    budget["remaining_cost_usd"] = (
        max(0.0, max_cost_usd - cost_usd) if max_cost_usd is not None and cost_usd is not None else None
    )
    budget_status = "not_tracked"
    if usage_has_data:
        budget_status = "within_limits"
        if max_tokens is not None and total_tokens is not None and total_tokens > max_tokens:
            budget_status = "over_budget"
            merged_warnings.append(
                f"tracked child usage consumed {total_tokens} tokens, exceeding budget limit {max_tokens}"
            )
        if max_cost_usd is not None and cost_usd is not None and cost_usd > max_cost_usd:
            budget_status = "over_budget"
            merged_warnings.append(
                f"tracked child usage cost ${cost_usd:g} exceeded budget limit ${max_cost_usd:g}"
            )
    elif enriched["enforcement"].get("advisory_limits"):
        budget_status = "advisory"
    budget["usage_status"] = budget_status

    if history is not None:
        enriched["history"] = history
    else:
        enriched.setdefault(
            "history",
            {
                "target_slug": str(enriched.get("target_slug") or ""),
                "attempt_count": 0,
                "failed_attempt_count": 0,
                "active_child_count": 0,
                "waiting_user_count": 0,
                "bubble_to_parent_count": 0,
                "continue_parent_count": 0,
                "child_only_count": 0,
                "statuses": [],
                "waiting_user_strategies": [],
            },
        )
    enriched["warnings"] = merged_warnings
    latest_waiting_user = (policy or {}).get("latest_waiting_user")
    if isinstance(latest_waiting_user, dict) and latest_waiting_user:
        enriched["latest_waiting_user"] = dict(latest_waiting_user)
    return enriched


def build_governance_policy(target: SubagentTarget) -> dict[str, Any]:
    budget_policy = target.budget_policy or {}
    max_tokens = _coerce_non_negative_int(
        _first_value(budget_policy.get("max_tokens"), budget_policy.get("token_limit"))
    )
    max_cost_usd = _coerce_positive_float(
        _first_value(budget_policy.get("max_cost_usd"), budget_policy.get("cost_limit_usd"))
    )

    hard_limits = [
        key
        for key, value in {
            "max_delegation_depth": target.max_delegation_depth(),
            "max_parent_delegations": resolve_max_parent_delegations(target),
            "max_concurrent_delegations": resolve_max_concurrent_delegations(target),
            "max_retry_attempts": resolve_max_retry_attempts(target),
            "timeout_seconds": resolve_timeout_seconds(target),
        }.items()
        if value is not None
    ]
    advisory_limits = [
        key
        for key, value in {
            "max_tokens": max_tokens,
            "max_cost_usd": max_cost_usd,
        }.items()
        if value is not None
    ]

    return {
        "protocol_version": GOVERNANCE_PROTOCOL_VERSION,
        "target_slug": target.slug,
        "limits": {
            "allow_nested_delegation": target.allows_nested_delegation(),
            "max_delegation_depth": target.max_delegation_depth(),
            "max_parent_delegations": resolve_max_parent_delegations(target),
            "max_concurrent_delegations": resolve_max_concurrent_delegations(target),
            "max_retry_attempts": resolve_max_retry_attempts(target),
            "timeout_seconds": resolve_timeout_seconds(target),
            "max_context_observations": target.max_context_observations(),
        },
        "budget": {
            **dict(budget_policy),
            "max_tokens": max_tokens,
            "max_cost_usd": max_cost_usd,
        },
        "waiting_user": {
            "propagation": resolve_waiting_user_propagation(target),
            "counts_as_active_child": resolve_waiting_user_counts_as_active_child(target),
        },
        "enforcement": {
            "hard_limits": hard_limits,
            "advisory_limits": advisory_limits,
            "note": (
                "Token and cost budgets are tracked from observed child usage and remain advisory "
                "while provider accounting may still be incomplete."
            ) if advisory_limits else None,
        },
    }


def prune_runtime_governance_ledger_for_resume(runtime_context: dict[str, Any]) -> dict[str, Any]:
    ledger = runtime_context.get("subagent_governance_ledger")
    if not isinstance(ledger, dict):
        return runtime_context
    targets = ledger.get("targets")
    if not isinstance(targets, dict):
        runtime_context["subagent_governance_ledger"] = {
            "protocol_version": GOVERNANCE_PROTOCOL_VERSION,
            "targets": {},
        }
        return runtime_context

    normalized_targets: dict[str, Any] = {}
    for target_slug, raw_entry in targets.items():
        entry = _normalize_ledger_entry(raw_entry, target_slug=str(target_slug or ""))
        history = _normalize_history(entry.get("history"), target_slug=str(target_slug or ""))
        history["active_child_count"] = 0
        normalized_targets[str(target_slug or "")] = {
            "target_slug": str(target_slug or ""),
            "history": history,
            "usage": dict(entry.get("usage") or {}),
            "last_invocation_usage": dict(entry.get("last_invocation_usage") or {}),
            "active_children": {},
            "latest_waiting_user": {},
            "recent_outcomes": list(entry.get("recent_outcomes") or []),
        }

    runtime_context["subagent_governance_ledger"] = {
        "protocol_version": GOVERNANCE_PROTOCOL_VERSION,
        "targets": normalized_targets,
    }
    return runtime_context


def _resolve_current_delegation_depth(run: AgentRun) -> int:
    delegation = run.metadata.get("delegation")
    if not isinstance(delegation, dict):
        return 0
    try:
        return max(0, int(delegation.get("depth") or 0))
    except (TypeError, ValueError):
        return 0


def evaluate_governance_gate(
    *,
    run: AgentRun,
    runtime_context: dict[str, Any],
    target: SubagentTarget,
) -> dict[str, Any]:
    policy = build_governance_policy(target)
    limits = policy["limits"]
    current_depth = _resolve_current_delegation_depth(run)
    history = summarize_delegation_history(
        runtime_context,
        target_slug=target.slug,
        waiting_user_counts_as_active_child=resolve_waiting_user_counts_as_active_child(target),
    )
    prior_usage = summarize_delegation_usage_history(
        runtime_context,
        target_slug=target.slug,
    )
    blockers: list[str] = []
    warnings: list[str] = []

    max_depth = limits.get("max_delegation_depth")
    if max_depth is not None and current_depth >= int(max_depth):
        blockers.append(f"delegation depth {current_depth} already reached the target limit {max_depth}")
    if current_depth > 0 and not limits.get("allow_nested_delegation"):
        blockers.append("nested delegation is disabled for this capability")

    max_parent_delegations = limits.get("max_parent_delegations")
    if max_parent_delegations is not None and history["attempt_count"] >= int(max_parent_delegations):
        blockers.append(
            f"parent run already used {history['attempt_count']} delegation attempt(s) "
            f"for {target.slug}, limit {max_parent_delegations}"
        )

    max_concurrent = limits.get("max_concurrent_delegations")
    if max_concurrent is not None and history["active_child_count"] >= int(max_concurrent):
        blockers.append(
            f"{history['active_child_count']} unresolved child run(s) already exist "
            f"for {target.slug}, concurrency limit {max_concurrent}"
        )

    max_retries = limits.get("max_retry_attempts")
    if max_retries is not None and history["failed_attempt_count"] > int(max_retries):
        blockers.append(
            f"failed retry count {history['failed_attempt_count']} exceeded retry limit {max_retries}"
        )

    if policy["enforcement"].get("advisory_limits"):
        warnings.append("budget limits are attached to the invocation as advisory governance metadata")

    policy = annotate_governance_policy(
        policy,
        history=history,
        warnings=warnings,
        usage=prior_usage,
        prior_usage=prior_usage,
    )

    return {
        "protocol_version": GOVERNANCE_PROTOCOL_VERSION,
        "allowed": not blockers,
        "decision": "approved" if not blockers else "rejected",
        "reason": "; ".join(blockers) if blockers else "governance limits satisfied",
        "blockers": blockers,
        "warnings": warnings,
        "policy": policy,
        "current_depth": current_depth,
        "history": history,
        "prior_usage": prior_usage,
    }
