from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.agent_runtime.runtime import AgentRuntime


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


class FakeTracer:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def emit_event(self, run_id: str, event_type: str, **payload) -> None:
        self.events.append((run_id, event_type, payload))


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
                "ask_user_guard": {"attempt": 1},
                "last_plan": {"steps": ["old plan"]},
                "last_result_contract": {"artifact_count": 2},
                "last_summary_model": {"resolved_model_name": "gpt-test"},
                "planning_model": {"candidate_count": 2},
                "synthesis_model": {"candidate_count": 2},
                "normalized_task_input": {"message": "Need more context"},
                "mounted_knowledge_base_ids": ["kb-1"],
                "tool_failures": 3,
                "execution_count": 4,
                "intent_state": {"inferred_intent": "research"},
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
    assert "ask_user_guard" not in reset_context
    assert "last_plan" not in reset_context
    assert "last_result_contract" not in reset_context
    assert "planning_model" not in reset_context
    assert "synthesis_model" not in reset_context
    assert "normalized_task_input" not in reset_context
    assert "mounted_knowledge_base_ids" not in reset_context

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
