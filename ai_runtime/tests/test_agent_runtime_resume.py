from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_runtime.core.agent_runtime.models import AgentRun
from ai_runtime.core.agent_runtime.runtime import AgentRuntime
from ai_runtime.core.agent_runtime.subagents.governance import evaluate_governance_gate
from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


def _run_row(*, status: str = "waiting_user", input_payload: dict | None = None, context: dict | None = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": "00000000-0000-0000-0000-000000000111",
        "agent_definition_id": "00000000-0000-0000-0000-000000000222",
        "tenant_id": "00000000-0000-0000-0000-000000000333",
        "user_id": "00000000-0000-0000-0000-000000000444",
        "session_id": "00000000-0000-0000-0000-000000000555",
        "status": status,
        "input": input_payload or {"message": "Need more context"},
        "plan": {"steps": ["old plan"]},
        "context": context or {},
        "final_output": "previous output",
        "final_output_text": "previous output",
        "final_output_json": {"answer": "previous output"},
        "error_message": "old error",
        "started_at": now,
        "finished_at": now,
        "cancelled_at": None,
        "created_at": now,
        "updated_at": now,
        "metadata": {},
    }


class FakeRunRepository:
    def __init__(self, run_row: dict) -> None:
        self.run_row = run_row
        self.patched_inputs: list[dict] = []
        self.reset_calls: list[dict] = []
        self.status_updates: list[dict] = []
        self.artifacts: list[dict] = []
        self.replaced_artifacts: list[dict] = []

    async def get_run(self, run_id: str, tenant_id: str | None = None) -> dict | None:
        return self.run_row

    async def patch_run_input(self, run_id: str, input_patch: dict) -> dict:
        self.patched_inputs.append({"run_id": run_id, "input_patch": input_patch})
        self.run_row = {
            **self.run_row,
            "input": {
                **self.run_row.get("input", {}),
                **input_patch,
            },
        }
        return self.run_row

    async def reset_run_execution(self, run_id: str, *, context: dict | None = None) -> dict:
        self.reset_calls.append({"run_id": run_id, "context": context})
        self.run_row = {
            **self.run_row,
            "status": "queued",
            "plan": {},
            "context": context or self.run_row.get("context", {}),
            "final_output": None,
            "final_output_text": None,
            "final_output_json": None,
            "error_message": None,
            "started_at": None,
            "finished_at": None,
            "cancelled_at": None,
        }
        return self.run_row

    async def update_run_status(self, run_id: str, status: str, **payload) -> dict:
        self.status_updates.append({"run_id": run_id, "status": status, **payload})
        self.run_row = {
            **self.run_row,
            "status": status,
            "plan": payload.get("plan") if payload.get("plan") is not None else self.run_row.get("plan"),
            "context": payload.get("context") if payload.get("context") is not None else self.run_row.get("context"),
            "final_output": payload.get("final_output") if payload.get("final_output") is not None else self.run_row.get("final_output"),
            "final_output_text": payload.get("final_output_text") if payload.get("final_output_text") is not None else self.run_row.get("final_output_text"),
            "final_output_json": payload.get("final_output_json") if payload.get("final_output_json") is not None else self.run_row.get("final_output_json"),
            "error_message": payload.get("error_message"),
        }
        return self.run_row

    async def list_artifacts(self, run_id: str) -> list[dict]:
        return list(self.artifacts)

    async def replace_artifacts(self, run_id: str, artifacts: list[dict]) -> list[dict]:
        self.replaced_artifacts = list(artifacts)
        self.artifacts = list(artifacts)
        return self.artifacts

    async def update_artifact_review_decision(
        self,
        *,
        run_id: str,
        artifact_id: str,
        tenant_id: str | None,
        decision: str,
        reviewer_id: str | None = None,
        note: str | None = None,
    ) -> dict | None:
        for artifact in self.artifacts:
            if artifact.get("id") != artifact_id:
                continue
            artifact["metadata"] = {
                **(artifact.get("metadata") or {}),
                "review_decision": decision,
                "reviewed_by": reviewer_id,
                "review_note": note,
            }
            return artifact
        return None

    async def list_steps(self, run_id: str) -> list[dict]:
        return []


class FakeToolCallRepository:
    async def list_tool_calls(self, run_id: str) -> list[dict]:
        return []


class FakeTracer:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def emit_event(self, run_id: str, event_type: str, **payload) -> None:
        self.events.append((run_id, event_type, payload))


class FakeStateStore:
    def __init__(self) -> None:
        self.cancel_requests: list[str] = []

    def request_cancel(self, run_id: str) -> None:
        self.cancel_requests.append(run_id)

    def get_task(self, run_id: str):
        return None


@pytest.mark.asyncio
async def test_resume_run_resets_execution_surface_and_prunes_transient_context():
    runtime = AgentRuntime.__new__(AgentRuntime)
    repository = FakeRunRepository(
        _run_row(
            context={
                "conversation": [
                    {"role": "user", "content": "Need more context"},
                    {"role": "assistant", "content": "Which environment?"},
                ],
                "step_history": [{"status": "failed", "tool_name": "knowledge_search"}],
                "pending_question": "Which environment?",
                "pending_subagent_clarification": {
                    "child_run_id": "child-run-1",
                    "question": "Which environment?",
                },
                "resolved_subagent_invocations": [
                    {
                        "child_run_id": "child-run-1",
                        "invocation_id": "invocation-1",
                        "summary": "stale child result from previous attempt",
                    }
                ],
                "ask_user_guard": {"attempt": 1},
                "last_plan": {"steps": ["old plan"]},
                "last_result_contract": {"artifact_count": 2},
                "last_summary_model": {"resolved_model_name": "gpt-test"},
                "planning_model": {"candidate_count": 2},
                "synthesis_model": {"candidate_count": 2},
                "normalized_task_input": {"message": "Need more context"},
                "mounted_knowledge_base_ids": ["kb-1"],
                "promoted_artifacts": [
                    {
                        "artifact_type": "document_excerpt",
                        "name": "search_docs - Preview",
                        "payload": {"items": [{"text": "stale preview"}]},
                    }
                ],
                "tool_failures": 3,
                "execution_count": 4,
                "intent_state": {"inferred_intent": "research"},
                "subagent_governance_ledger": {
                    "protocol_version": "managed-subagent.governance.v1",
                    "targets": {
                        "review-specialist": {
                            "history": {
                                "target_slug": "review-specialist",
                                "attempt_count": 2,
                                "failed_attempt_count": 0,
                                "active_child_count": 1,
                                "waiting_user_count": 1,
                                "bubble_to_parent_count": 1,
                                "continue_parent_count": 0,
                                "child_only_count": 0,
                                "statuses": ["completed", "waiting_user"],
                                "waiting_user_strategies": ["bubble_to_parent"],
                            },
                            "usage": {
                                "total_tokens": 480,
                                "cost_usd": 0.19,
                                "source": "ledger",
                            },
                            "last_invocation_usage": {
                                "total_tokens": 180,
                                "cost_usd": 0.07,
                                "source": "metadata.governance_usage",
                            },
                            "active_children": {
                                "child:child-run-1": {
                                    "child_run_id": "child-run-1",
                                    "status": "waiting_user",
                                    "counts_as_active_child": True,
                                    "waiting_user_propagation": "bubble_to_parent",
                                }
                            },
                            "latest_waiting_user": {
                                "child_run_id": "child-run-1",
                                "question": "Which environment?",
                                "waiting_user_path": [
                                    {"run_id": "parent-run", "role": "parent", "status": "running"},
                                    {"run_id": "child-run-1", "role": "child", "status": "waiting_user"},
                                ],
                            },
                        }
                    },
                },
            }
        )
    )
    tracer = FakeTracer()
    started_runs: list[str] = []

    runtime.run_repository = repository
    runtime.tracer = tracer

    async def fake_start_run(run_id: str) -> None:
        started_runs.append(run_id)

    runtime.start_run = fake_start_run

    response = await runtime.resume_run(
        "00000000-0000-0000-0000-000000000111",
        "00000000-0000-0000-0000-000000000333",
        input_patch={"message": "Production only"},
    )

    assert repository.patched_inputs == [
        {
            "run_id": "00000000-0000-0000-0000-000000000111",
            "input_patch": {"message": "Production only"},
        }
    ]
    assert len(repository.reset_calls) == 1

    reset_context = repository.reset_calls[0]["context"]
    assert reset_context["conversation"][0]["content"] == "Need more context"
    assert reset_context["step_history"][0]["tool_name"] == "knowledge_search"
    assert reset_context["intent_state"]["inferred_intent"] == "research"
    assert reset_context["tool_failures"] == 0
    assert reset_context["execution_count"] == 0
    assert "pending_question" not in reset_context
    assert "pending_subagent_clarification" not in reset_context
    assert "resolved_subagent_invocations" not in reset_context
    assert "ask_user_guard" not in reset_context
    assert "last_plan" not in reset_context
    assert "last_result_contract" not in reset_context
    assert "planning_model" not in reset_context
    assert "synthesis_model" not in reset_context
    assert "normalized_task_input" not in reset_context
    assert "mounted_knowledge_base_ids" not in reset_context
    assert "promoted_artifacts" not in reset_context
    assert reset_context["subagent_governance_ledger"]["targets"]["review-specialist"]["history"]["active_child_count"] == 0
    assert reset_context["subagent_governance_ledger"]["targets"]["review-specialist"]["active_children"] == {}
    assert reset_context["subagent_governance_ledger"]["targets"]["review-specialist"]["latest_waiting_user"] == {}

    assert tracer.events == [
        (
            "00000000-0000-0000-0000-000000000111",
            "run.input_patched",
            {"input_patch": {"message": "Production only"}},
        ),
        (
            "00000000-0000-0000-0000-000000000111",
            "run.resumed",
            {"status": "queued"},
        ),
    ]
    assert started_runs == ["00000000-0000-0000-0000-000000000111"]

    run = response.run
    assert run.status == "queued"
    assert run.plan == {}
    assert run.input["message"] == "Production only"
    assert run.final_output is None
    assert run.final_output_text is None
    assert run.final_output_json is None
    assert run.error_message is None
    assert run.started_at is None
    assert run.finished_at is None
    assert run.cancelled_at is None
    assert run.artifacts == []
    assert run.steps == []
    assert run.tool_calls == []


@pytest.mark.asyncio
async def test_cancel_run_persists_partial_result_surface_and_emits_artifact_snapshot():
    runtime = AgentRuntime.__new__(AgentRuntime)
    repository = FakeRunRepository(
        _run_row(
            status="running",
            context={
                "conversation": [{"role": "user", "content": "Need more context"}],
                "step_history": [],
                "promoted_artifacts": [
                    {
                        "artifact_type": "citations",
                        "name": "search_docs - Citations",
                        "payload": {
                            "items": [
                                {
                                    "title": "Runtime Plan",
                                    "url": "https://example.com/runtime-plan",
                                    "snippet": "Use structured artifacts.",
                                }
                            ]
                        },
                    }
                ],
            },
        )
    )
    repository.run_row["final_output"] = None
    repository.run_row["final_output_text"] = None
    repository.run_row["final_output_json"] = {
        "steps": [
            {"title": "Audit compatibility drift", "status": "in_progress"},
            {"title": "Backfill replay coverage", "status": "pending"},
        ]
    }

    tracer = FakeTracer()
    runtime.run_repository = repository
    runtime.tracer = tracer
    runtime.state_store = FakeStateStore()

    response = await runtime.cancel_run(
        "00000000-0000-0000-0000-000000000111",
        "00000000-0000-0000-0000-000000000333",
    )

    assert runtime.state_store.cancel_requests == ["00000000-0000-0000-0000-000000000111"]
    assert repository.status_updates[-1]["status"] == "cancelled"
    assert [artifact["artifact_type"] for artifact in repository.replaced_artifacts] == ["answer", "citations", "task_plan"]

    run = response.run
    assert run.status == "cancelled"
    assert [artifact.artifact_type for artifact in run.artifacts] == ["answer", "citations", "task_plan"]
    assert run.final_output_text == "Audit compatibility drift\nBackfill replay coverage"


def test_resume_prunes_governance_ledger_active_children_for_future_delegate_gate():
    runtime = AgentRuntime.__new__(AgentRuntime)
    context = runtime._build_resume_context(
        _run_row(
            context={
                "conversation": [],
                "step_history": [],
                "subagent_governance_ledger": {
                    "protocol_version": "managed-subagent.governance.v1",
                    "targets": {
                        "review-specialist": {
                            "history": {
                                "target_slug": "review-specialist",
                                "attempt_count": 1,
                                "failed_attempt_count": 0,
                                "active_child_count": 1,
                                "waiting_user_count": 1,
                                "bubble_to_parent_count": 1,
                                "continue_parent_count": 0,
                                "child_only_count": 0,
                                "statuses": ["waiting_user"],
                                "waiting_user_strategies": ["bubble_to_parent"],
                            },
                            "active_children": {
                                "child:child-run-1": {
                                    "child_run_id": "child-run-1",
                                    "status": "waiting_user",
                                    "counts_as_active_child": True,
                                }
                            },
                        }
                    },
                },
            }
        )
    )

    gate = evaluate_governance_gate(
        run=AgentRun.model_validate(_run_row(status="queued", context={})),
        runtime_context=context,
        target=SubagentTarget(
            slug="review-specialist",
            name="Review Specialist",
            agent_definition_id="agent-reviewer",
            runtime_policy={"max_concurrent_delegations": 1},
        ),
    )

    assert gate["allowed"] is True
    assert gate["history"]["active_child_count"] == 0


@pytest.mark.asyncio
async def test_review_artifact_persists_decision_and_emits_event():
    runtime = AgentRuntime.__new__(AgentRuntime)
    repository = FakeRunRepository(
        _run_row(
            status="completed",
            context={},
        )
    )
    repository.artifacts = [
        {
            "id": "artifact-1",
            "run_id": repository.run_row["id"],
            "artifact_type": "code_patch",
            "name": "Workspace Patch",
            "payload": {"diff": "--- a/file.py\n+++ b/file.py\n"},
            "metadata": {},
        }
    ]
    tracer = FakeTracer()
    runtime.run_repository = repository
    runtime.tool_call_repository = FakeToolCallRepository()
    runtime.tracer = tracer

    request = type("ReviewRequest", (), {"decision": "accepted", "note": "Looks good"})()
    response = await runtime.review_artifact(
        repository.run_row["id"],
        "artifact-1",
        repository.run_row["tenant_id"],
        repository.run_row["user_id"],
        request,
    )

    patch_artifact = next(artifact for artifact in response.run.artifacts if artifact.artifact_type == "code_patch")
    assert patch_artifact.metadata["review_decision"] == "accepted"
    assert patch_artifact.metadata["reviewed_by"] == repository.run_row["user_id"]
    assert tracer.events[-1][1] == "artifact.reviewed"


def test_governance_gate_returns_structured_recovery_for_concurrency_limit():
    context = {
        "subagent_governance_ledger": {
            "protocol_version": "managed-subagent.governance.v1",
            "targets": {
                "review-specialist": {
                    "target_slug": "review-specialist",
                    "history": {
                        "target_slug": "review-specialist",
                        "attempt_count": 1,
                        "active_child_count": 1,
                        "statuses": ["running"],
                    },
                    "active_children": {
                        "child:child-run-1": {
                            "child_run_id": "child-run-1",
                            "status": "running",
                            "counts_as_active_child": True,
                        }
                    },
                }
            },
        }
    }

    gate = evaluate_governance_gate(
        run=AgentRun.model_validate(_run_row(status="queued", context={})),
        runtime_context=context,
        target=SubagentTarget(
            slug="review-specialist",
            name="Review Specialist",
            agent_definition_id="agent-reviewer",
            runtime_policy={"max_concurrent_delegations": 1},
        ),
    )

    assert gate["allowed"] is False
    assert gate["blockers"][0]["code"] == "concurrency_limit_exceeded"
    assert gate["recovery"]["primary_code"] == "concurrency_limit_exceeded"
    assert gate["recovery"]["actions"][0].startswith("Wait for an existing child run")
