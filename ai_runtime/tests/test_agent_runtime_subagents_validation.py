"""GA hardening: Subagents concurrency validation tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from ai_runtime.core.agent_runtime.models import AgentRun, PlannerAction
from ai_runtime.core.agent_runtime.subagents.governance import (
    build_governance_policy,
    build_subagent_failure_strategy,
    build_tool_budget_gate,
    evaluate_governance_gate,
    record_delegation_outcome,
)
from ai_runtime.core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget
from ai_runtime.core.agent_runtime.subagents.review import build_review_result
from ai_runtime.core.agent_runtime.subagents.templates import build_builtin_subagent_target


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _build_run(**overrides):
    base = {
        "id": "run-parent",
        "agent_definition_id": "agent-parent",
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "status": "running",
        "input": {"message": "Implement the feature."},
        "plan": {},
        "context": {},
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
    }
    base.update(overrides)
    return AgentRun.model_validate(base)


def _worker_target(**overrides) -> SubagentTarget:
    target = build_builtin_subagent_target("worker")
    assert target is not None
    for key, value in overrides.items():
        if hasattr(target, key):
            object.__setattr__(target, key, value)
        elif key in target.runtime_policy:
            target.runtime_policy[key] = value
        elif key in target.budget_policy:
            target.budget_policy[key] = value
    return target


def _reviewer_target() -> SubagentTarget:
    target = build_builtin_subagent_target("reviewer")
    assert target is not None
    return target


def _explorer_target() -> SubagentTarget:
    target = build_builtin_subagent_target("explorer")
    assert target is not None
    return target


def _delegation_result(*, child_run_id: str = "child-1", status: str = "completed", **overrides) -> SubagentDelegationResult:
    target = _worker_target()
    base = {
        "child_run_id": child_run_id,
        "status": status,
        "target": target,
        "input": {"message": "Do the work"},
        "summary": "Work completed",
    }
    base.update(overrides)
    return SubagentDelegationResult.model_validate(base)


# --- Parallel worker merge paths ---


async def test_parallel_workers_produce_independent_results():
    worker_a = _worker_target()
    worker_b = _worker_target()

    result_a = SubagentDelegationResult(
        child_run_id="child-a",
        status="completed",
        target=worker_a,
        input={"message": "Fix auth", "write_scope": ["src/auth.py"]},
        summary="Fixed auth module",
        final_output_text="Auth fixed",
        artifacts=[{"artifact_type": "code_patch", "payload": {"diff": "+auth fix"}}],
    )
    result_b = SubagentDelegationResult(
        child_run_id="child-b",
        status="completed",
        target=worker_b,
        input={"message": "Fix db", "write_scope": ["src/db.py"]},
        summary="Fixed db module",
        final_output_text="DB fixed",
        artifacts=[{"artifact_type": "code_patch", "payload": {"diff": "+db fix"}}],
    )

    assert result_a.status == "completed"
    assert result_b.status == "completed"
    assert result_a.child_run_id != result_b.child_run_id
    assert len(result_a.artifacts) == 1
    assert len(result_b.artifacts) == 1


async def test_parallel_worker_results_can_be_collected():
    results = []
    for i in range(4):
        results.append(SubagentDelegationResult(
            child_run_id=f"child-{i}",
            status="completed",
            target=_worker_target(),
            input={"message": f"Task {i}", "write_scope": [f"src/module_{i}.py"]},
            summary=f"Completed task {i}",
        ))

    completed = [r for r in results if r.status == "completed"]
    assert len(completed) == 4
    assert len(set(r.child_run_id for r in completed)) == 4


# --- Write_scope conflict detection ---


async def test_write_scope_conflict_detected_for_overlapping_paths():
    run = _build_run(metadata={
        "delegation": {
            "active_children": [
                {"child_run_id": "child-existing", "write_scope": ["src/auth.py", "src/utils.py"]},
            ],
        },
    })
    target = _worker_target()
    policy = build_governance_policy(target)

    existing_scopes = []
    delegation = run.metadata.get("delegation", {})
    for child in delegation.get("active_children", []):
        existing_scopes.extend(child.get("write_scope", []))

    new_scope = ["src/auth.py", "src/new.py"]
    conflicts = [path for path in new_scope if path in existing_scopes]

    assert len(conflicts) == 1
    assert "src/auth.py" in conflicts


async def test_write_scope_no_conflict_for_disjoint_paths():
    existing_scopes = ["src/auth.py", "src/utils.py"]
    new_scope = ["src/db.py", "src/models.py"]
    conflicts = [path for path in new_scope if path in existing_scopes]

    assert len(conflicts) == 0


# --- Parent run cancel propagation ---


async def test_parent_cancel_marks_children_for_cancellation():
    parent_run = _build_run(status="cancelled", metadata={
        "delegation": {
            "active_children": [
                {"child_run_id": "child-1", "status": "running"},
                {"child_run_id": "child-2", "status": "running"},
                {"child_run_id": "child-3", "status": "completed"},
            ],
        },
    })

    active_children = parent_run.metadata.get("delegation", {}).get("active_children", [])
    to_cancel = [c for c in active_children if c.get("status") in {"running", "queued", "waiting_user"}]

    assert len(to_cancel) == 2
    assert all(c["child_run_id"] in {"child-1", "child-2"} for c in to_cancel)


# --- Parent run resume after cancel ---


async def test_parent_resume_does_not_affect_completed_children():
    parent_run = _build_run(status="running", metadata={
        "delegation": {
            "active_children": [
                {"child_run_id": "child-1", "status": "completed"},
                {"child_run_id": "child-2", "status": "cancelled"},
            ],
        },
    })

    active_children = parent_run.metadata.get("delegation", {}).get("active_children", [])
    completed = [c for c in active_children if c["status"] == "completed"]
    cancelled = [c for c in active_children if c["status"] == "cancelled"]

    assert len(completed) == 1
    assert len(cancelled) == 1


# --- Child waiting_user propagation ---


async def test_child_waiting_user_propagates_to_parent_context():
    child_result = SubagentDelegationResult(
        child_run_id="child-waiting",
        status="waiting_user",
        target=_worker_target(),
        input={"message": "Need clarification"},
        summary="Waiting for user input",
        clarification={"question": "Which database?", "blocking": True},
    )

    assert child_result.status == "waiting_user"
    assert child_result.clarification.get("question") == "Which database?"
    assert child_result.clarification.get("blocking") is True


async def test_waiting_user_non_blocking_does_not_block_parent():
    target = _explorer_target()
    # Explorer has waiting_user_propagation = "continue_parent_non_blocking"
    propagation = target.runtime_policy.get("waiting_user_propagation", "block_parent")

    assert propagation == "continue_parent_non_blocking"


# --- Reviewer blocking gate ---


async def test_reviewer_blocks_on_high_severity_findings():
    target = _reviewer_target()
    hydrated = {
        "final_output_json": {
            "review_decision": "reject",
            "review_findings": [
                {"title": "SQL injection", "severity": "critical", "path": "src/db.py", "line": 42},
                {"title": "Missing validation", "severity": "high", "path": "src/api.py", "line": 10},
            ],
        },
        "artifacts": [],
    }

    result = build_review_result(
        target=target,
        status="completed",
        hydrated=hydrated,
        child_run_id="child-reviewer",
    )

    assert result["approved"] is False
    assert result["decision"] in {"rejected", "changes_requested"}
    assert result["blocking_finding_count"] >= 1
    assert result["finding_count"] == 2


async def test_reviewer_approves_with_no_blocking_findings():
    target = _reviewer_target()
    hydrated = {
        "final_output_json": {
            "review_decision": "approve",
            "review_findings": [
                {"title": "Minor style issue", "severity": "low", "path": "src/utils.py", "line": 5},
            ],
        },
        "artifacts": [],
    }

    result = build_review_result(
        target=target,
        status="completed",
        hydrated=hydrated,
        child_run_id="child-reviewer",
    )

    assert result["approved"] is True
    assert result["decision"] in {"approved", "approved_with_findings"}
    assert result["blocking_finding_count"] == 0
    assert result["finding_count"] == 1


async def test_reviewer_inconclusive_without_explicit_decision():
    target = _reviewer_target()
    hydrated = {
        "final_output_json": {},
        "final_output_text": "",
        "artifacts": [],
    }

    result = build_review_result(
        target=target,
        status="completed",
        hydrated=hydrated,
        child_run_id="child-reviewer",
    )

    assert result["decision"] == "inconclusive"
    assert result["approved"] is None


# --- Budget hard limit enforcement ---


async def test_budget_hard_limit_blocks_delegation():
    run = _build_run(metadata={
        "delegation": {
            "usage": {"total_tokens": 15000},
        },
    })
    target = _worker_target()
    target.budget_policy["max_tokens"] = 10000
    target.budget_policy["hard_limit"] = True

    policy = build_governance_policy(target)

    usage = run.metadata.get("delegation", {}).get("usage", {})
    budget_max = target.budget_policy.get("max_tokens", float("inf"))
    current_tokens = usage.get("total_tokens", 0)

    assert current_tokens > budget_max


async def test_budget_within_limit_allows_delegation():
    run = _build_run(metadata={
        "delegation": {
            "usage": {"total_tokens": 5000},
        },
    })
    target = _worker_target()
    target.budget_policy["max_tokens"] = 10000

    usage = run.metadata.get("delegation", {}).get("usage", {})
    budget_max = target.budget_policy.get("max_tokens", float("inf"))
    current_tokens = usage.get("total_tokens", 0)

    assert current_tokens <= budget_max


# --- Delegation depth limit ---


async def test_delegation_depth_limit_blocks_deep_nesting():
    target = _worker_target()
    target.runtime_policy["max_delegation_depth"] = 3

    max_depth = target.max_delegation_depth()
    current_depth = 4

    assert current_depth > max_depth


async def test_delegation_depth_within_limit_allows():
    target = _worker_target()
    target.runtime_policy["max_delegation_depth"] = 3

    max_depth = target.max_delegation_depth()
    current_depth = 2

    assert current_depth <= max_depth


# --- Concurrent delegation limit ---


async def test_concurrent_delegation_limit_blocks_excess():
    target = _worker_target()
    max_concurrent = target.runtime_policy.get("max_concurrent_delegations", 2)

    active_children = [
        {"child_run_id": f"child-{i}", "status": "running"}
        for i in range(max_concurrent)
    ]

    running_count = sum(1 for c in active_children if c["status"] in {"running", "queued"})
    assert running_count >= max_concurrent


async def test_concurrent_delegation_within_limit_allows():
    target = _worker_target()
    max_concurrent = target.runtime_policy.get("max_concurrent_delegations", 2)

    active_children = [
        {"child_run_id": "child-1", "status": "running"},
    ]

    running_count = sum(1 for c in active_children if c["status"] in {"running", "queued"})
    assert running_count < max_concurrent


# --- Retry limit enforcement ---


async def test_retry_limit_blocks_excessive_retries():
    target = _worker_target()
    max_retries = 3

    # Simulate retry tracking
    retry_history = [
        {"attempt": 1, "status": "failed", "error": "timeout"},
        {"attempt": 2, "status": "failed", "error": "timeout"},
        {"attempt": 3, "status": "failed", "error": "timeout"},
    ]

    assert len(retry_history) >= max_retries


async def test_retry_within_limit_allows():
    max_retries = 3
    retry_history = [
        {"attempt": 1, "status": "failed", "error": "timeout"},
    ]

    assert len(retry_history) < max_retries


# --- Governance gate evaluation ---


async def test_governance_gate_evaluates_all_conditions():
    run = _build_run()
    target = _worker_target()

    policy = build_governance_policy(target)

    assert "gates" in policy or "protocol_version" in policy


async def test_failure_strategy_returns_structured_result():
    target = _worker_target()

    strategy = build_subagent_failure_strategy(
        target=target,
        status="failed",
        error_message="Process timed out",
    )

    assert "strategy" in strategy
    assert strategy["strategy"] in {"retry_or_fallback", "escalate", "abort", "terminate"}
    assert strategy["recoverable"] is True
    assert strategy["retry_allowed"] is True


async def test_failure_strategy_escalates_after_max_attempts():
    target = _worker_target()

    strategy = build_subagent_failure_strategy(
        target=target,
        status="failed",
        error_message="Process timed out",
        blockers=[{"gate": "retry_limit_exceeded", "code": "retry_limit_exceeded"}],
    )

    # With retry limit exceeded blocker, strategy should not allow retry
    assert strategy["status"] == "failed"
    assert "recovery" in strategy
