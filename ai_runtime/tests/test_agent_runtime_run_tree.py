from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_runtime.core.agent_runtime.runtime import AgentRuntime


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _run_row(run_id: str, *, status: str = "completed", final_output_text: str = "", metadata: dict | None = None) -> dict:
    now = _timestamp()
    return {
        "id": run_id,
        "agent_definition_id": "00000000-0000-0000-0000-0000000000aa",
        "tenant_id": "00000000-0000-0000-0000-0000000000bb",
        "user_id": "00000000-0000-0000-0000-0000000000cc",
        "session_id": "00000000-0000-0000-0000-0000000000dd",
        "status": status,
        "input": {"message": f"run {run_id} task"},
        "plan": {},
        "context": {},
        "final_output": final_output_text or None,
        "final_output_text": final_output_text or None,
        "final_output_json": {"answer": final_output_text} if final_output_text else None,
        "error_message": None,
        "started_at": now,
        "finished_at": now if status == "completed" else None,
        "cancelled_at": None,
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }


def _invocation_row(
    invocation_id: str,
    parent_run_id: str,
    child_run_id: str | None,
    *,
    status: str = "completed",
    target_name: str = "Review Specialist",
) -> dict:
    now = _timestamp()
    return {
        "id": invocation_id,
        "parent_run_id": parent_run_id,
        "parent_step_id": "00000000-0000-0000-0000-0000000000ee",
        "subagent_definition_id": "00000000-0000-0000-0000-0000000000ff",
        "publication_id": "00000000-0000-0000-0000-000000000101",
        "version_id": "00000000-0000-0000-0000-000000000102",
        "authorization_id": "00000000-0000-0000-0000-000000000103",
        "child_run_id": child_run_id,
        "status": status,
        "request_payload": {
            "task": {"message": "Review the change set."},
            "policy_snapshot": {"target": {"name": target_name, "slug": "review-specialist"}},
        },
        "result_payload": {
            "status": status,
            "final_result": {"summary": f"{target_name} done."},
            "review_result": {
                "mode": "judge" if "Judge" in target_name else "reviewer",
                "required": True,
                "decision": "approved",
                "summary": f"{target_name} passed.",
            },
        },
        "error_message": None,
        "started_at": now,
        "completed_at": now,
        "created_at": now,
        "updated_at": now,
    }


class FakeRunRepository:
    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    async def get_run(self, run_id: str, tenant_id: str | None = None) -> dict | None:
        return self.rows.get(run_id)

    async def list_runs_by_ids(self, run_ids: list[str], *, tenant_id: str | None = None) -> list[dict]:
        return [self.rows[run_id] for run_id in run_ids if run_id in self.rows]


class FakeInvocationRepository:
    def __init__(self, rows_by_parent: dict[str, list[dict]]) -> None:
        self.rows_by_parent = rows_by_parent

    async def list_invocations_for_parent_run(self, parent_run_id: str) -> list[dict]:
        return list(self.rows_by_parent.get(parent_run_id, []))


@pytest.mark.asyncio
async def test_list_subagent_invocations_returns_structured_items():
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.run_repository = FakeRunRepository(
        {
            "00000000-0000-0000-0000-000000000201": _run_row(
                "00000000-0000-0000-0000-000000000201",
                final_output_text="Parent complete.",
            )
        }
    )
    runtime.subagent_invocation_repository = FakeInvocationRepository(
        {
            "00000000-0000-0000-0000-000000000201": [
                _invocation_row(
                    "00000000-0000-0000-0000-000000000301",
                    "00000000-0000-0000-0000-000000000201",
                    "00000000-0000-0000-0000-000000000401",
                )
            ]
        }
    )

    response = await runtime.list_subagent_invocations(
        "00000000-0000-0000-0000-000000000201",
        "00000000-0000-0000-0000-0000000000bb",
    )

    assert response.total == 1
    assert response.invocations[0].child_run_id == "00000000-0000-0000-0000-000000000401"
    assert response.invocations[0].request_payload["policy_snapshot"]["target"]["slug"] == "review-specialist"
    assert response.invocations[0].result_payload["review_result"]["mode"] == "reviewer"


@pytest.mark.asyncio
async def test_get_run_tree_builds_nested_child_runs():
    parent_run_id = "00000000-0000-0000-0000-000000000201"
    child_run_id = "00000000-0000-0000-0000-000000000401"
    nested_child_run_id = "00000000-0000-0000-0000-000000000501"

    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.run_repository = FakeRunRepository(
        {
            parent_run_id: _run_row(parent_run_id, final_output_text="Parent complete."),
            child_run_id: _run_row(child_run_id, status="waiting_user", final_output_text="Need approval."),
            nested_child_run_id: _run_row(nested_child_run_id, final_output_text="Nested review complete."),
        }
    )
    runtime.subagent_invocation_repository = FakeInvocationRepository(
        {
            parent_run_id: [
                _invocation_row(
                    "00000000-0000-0000-0000-000000000301",
                    parent_run_id,
                    child_run_id,
                    target_name="Review Specialist",
                )
            ],
            child_run_id: [
                _invocation_row(
                    "00000000-0000-0000-0000-000000000302",
                    child_run_id,
                    nested_child_run_id,
                    target_name="Judge Specialist",
                )
            ],
        }
    )

    response = await runtime.get_run_tree(
        parent_run_id,
        "00000000-0000-0000-0000-0000000000bb",
        max_depth=4,
    )

    root = response.root
    assert root.depth == 0
    assert root.run.id == parent_run_id
    assert len(root.invocations) == 1
    assert root.invocations[0].child_run is not None
    assert root.invocations[0].child_run.run.id == child_run_id
    assert root.invocations[0].child_run.depth == 1
    assert root.invocations[0].child_run.invocations[0].child_run.run.id == nested_child_run_id
    assert root.invocations[0].child_run.invocations[0].invocation.result_payload["review_result"]["mode"] == "judge"


@pytest.mark.asyncio
async def test_get_run_tree_respects_max_depth():
    parent_run_id = "00000000-0000-0000-0000-000000000201"
    child_run_id = "00000000-0000-0000-0000-000000000401"
    nested_child_run_id = "00000000-0000-0000-0000-000000000501"

    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.run_repository = FakeRunRepository(
        {
            parent_run_id: _run_row(parent_run_id, final_output_text="Parent complete."),
            child_run_id: _run_row(child_run_id, final_output_text="Child complete."),
            nested_child_run_id: _run_row(nested_child_run_id, final_output_text="Nested review complete."),
        }
    )
    runtime.subagent_invocation_repository = FakeInvocationRepository(
        {
            parent_run_id: [
                _invocation_row(
                    "00000000-0000-0000-0000-000000000301",
                    parent_run_id,
                    child_run_id,
                )
            ],
            child_run_id: [
                _invocation_row(
                    "00000000-0000-0000-0000-000000000302",
                    child_run_id,
                    nested_child_run_id,
                )
            ],
        }
    )

    response = await runtime.get_run_tree(
        parent_run_id,
        "00000000-0000-0000-0000-0000000000bb",
        max_depth=2,
    )

    root = response.root
    assert root.invocations[0].child_run is not None
    assert root.invocations[0].child_run.run.id == child_run_id
    assert root.invocations[0].child_run.invocations[0].child_run is None
