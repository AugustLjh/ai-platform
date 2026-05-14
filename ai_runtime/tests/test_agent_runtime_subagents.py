from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ai_runtime.core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from ai_runtime.core.agent_runtime.orchestrator import AgentOrchestrator
from ai_runtime.core.agent_runtime.subagents.governance import record_delegation_outcome
from ai_runtime.core.agent_runtime.subagents.handoff import SubagentHandoff
from ai_runtime.core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget
from ai_runtime.core.agent_runtime.subagents.registry import SubagentRegistry
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
        "input": {"message": "Ship the runtime contract changes."},
        "plan": {},
        "context": {},
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
    }
    base.update(overrides)
    return AgentRun.model_validate(base)


class FakeAgentRepository:
    def __init__(self, definitions):
        self.definitions = definitions

    async def get_definition(self, definition_id, tenant_id=None):
        return self.definitions.get(definition_id)


class FakeDBPool:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def fetch(self, query, *args):
        return self.rows


class FakeRunRepository:
    def __init__(self):
        self.rows = {}
        self.updated_steps = []

    async def create_run(self, payload):
        row = {
            "id": "child-run-1",
            "agent_definition_id": payload["agent_definition_id"],
            "tenant_id": payload["tenant_id"],
            "user_id": payload.get("user_id"),
            "session_id": payload.get("session_id"),
            "status": "queued",
            "input": payload.get("input", {}),
            "plan": {},
            "context": {},
            "final_output": None,
            "final_output_text": None,
            "final_output_json": None,
            "error_message": None,
            "metadata": payload.get("metadata", {}),
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
        self.rows[row["id"]] = row
        return row

    async def get_run(self, run_id, tenant_id=None):
        return self.rows.get(run_id)

    async def list_artifacts(self, run_id):
        return self.rows.get(run_id, {}).get("artifacts", [])

    async def update_step(self, step_id, **payload):
        self.updated_steps.append({"step_id": step_id, **payload})
        return {"id": step_id, **payload}


class FakeTracer:
    def __init__(self):
        self.events = []
        self.steps = []

    async def emit_event(self, run_id, event_type, **payload):
        self.events.append({"run_id": run_id, "event_type": event_type, "payload": payload})
        return {"run_id": run_id, "event_type": event_type, "payload": payload}

    async def create_step(self, run_id, *, kind, title, status, input_payload=None, metadata=None):
        step = {
            "id": "step-1",
            "run_id": run_id,
            "step_index": 1,
            "kind": kind,
            "title": title,
            "status": status,
            "input": input_payload or {},
            "metadata": metadata or {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
        self.steps.append(step)
        return step


class FakeStateStore:
    def __init__(self):
        self.cancelled = set()
        self.tasks = {}

    def is_cancelled(self, run_id):
        return run_id in self.cancelled

    def get_task(self, run_id):
        return self.tasks.get(run_id)

    def register_task(self, run_id, task):
        self.tasks[run_id] = task


class FakeHandoff:
    def __init__(self, result: SubagentDelegationResult):
        self.result = result
        self.calls = []

    async def delegate(self, **payload):
        self.calls.append(payload)
        return self.result

    async def start_delegate(self, **payload):
        self.calls.append(payload)
        return self.result

    async def resolve_delegation_result(self, **payload):
        self.calls.append(payload)
        return self.result if self.result.status not in {"queued", "running"} else None


class FakeInvocationRepository:
    def __init__(self):
        self.rows = {}
        self.creates = []
        self.updates = []

    async def create_invocation(self, **payload):
        row = {"id": f"invocation-{len(self.creates) + 1}", **payload}
        self.creates.append(row)
        self.rows[row["id"]] = row
        return row

    async def update_invocation(self, invocation_id, **payload):
        row = {
            **self.rows.get(invocation_id, {"id": invocation_id}),
            **payload,
        }
        self.updates.append({"id": invocation_id, **payload})
        self.rows[invocation_id] = row
        return row


async def test_subagent_registry_resolves_targets_from_agent_metadata():
    registry = SubagentRegistry(
        FakeDBPool(),
        FakeAgentRepository(
            {
                "agent-reviewer": {
                    "id": "agent-reviewer",
                    "tenant_id": "tenant-1",
                    "name": "Review Specialist",
                    "description": "Focused reviewer",
                    "status": "active",
                },
                "agent-other": {
                    "id": "agent-other",
                    "tenant_id": "tenant-1",
                    "name": "Metadata Review Specialist",
                    "description": "Metadata fallback reviewer",
                    "status": "active",
                }
            }
        )
    )
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "",
            "metadata": {
                "subagents": [
                    {
                        "agent_definition_id": "agent-reviewer",
                        "slug": "review-specialist",
                        "handoff_prompt": "Perform a bounded review pass.",
                    }
                ]
            },
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    targets = await registry.resolve_for_definition(definition)

    assert len(targets) == 1
    assert targets[0].slug == "review-specialist"
    assert targets[0].name == "Review Specialist"
    assert targets[0].handoff_prompt == "Perform a bounded review pass."


async def test_subagent_registry_resolves_builtin_templates_from_agent_metadata():
    registry = SubagentRegistry(FakeDBPool(), FakeAgentRepository({}))
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "",
            "metadata": {
                "subagents": [
                    {"template": "explorer"},
                    {
                        "builtin_template": "reviewer",
                        "slug": "strict-review",
                        "runtime_policy": {"max_parent_delegations": 2},
                    },
                ]
            },
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    targets = await registry.resolve_for_definition(definition)

    assert [target.slug for target in targets] == ["explorer", "strict-review"]
    assert targets[0].agent_definition_id is None
    assert targets[0].subagent_definition_id is None
    assert "workspace_read_file" in targets[0].tool_allowlist
    assert "workspace_apply_patch" not in targets[0].tool_allowlist
    assert targets[0].runtime_policy["async_execution"] is True
    assert targets[0].runtime_policy["allow_delegation"] is False
    assert targets[0].metadata["template_slug"] == "explorer"
    assert targets[1].review_policy["blocking_severities"] == ["high", "critical"]
    assert targets[1].runtime_policy["max_parent_delegations"] == 2
    assert targets[1].runtime_policy["allow_delegation"] is False
    assert targets[1].runtime_policy["delegation_mode"] == "reviewer"


async def test_subagent_registry_uses_slug_as_builtin_template_alias():
    registry = SubagentRegistry(FakeDBPool(), FakeAgentRepository({}))
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "",
            "metadata": {"subagents": [{"slug": "worker", "name": "Scoped Worker"}]},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    targets = await registry.resolve_for_definition(definition)

    assert len(targets) == 1
    assert targets[0].slug == "worker"
    assert targets[0].name == "Scoped Worker"
    assert "workspace_apply_patch" in targets[0].tool_allowlist
    assert "run_tests" in targets[0].tool_allowlist
    assert targets[0].metadata["requires_write_scope"] is True


def test_builtin_subagent_templates_map_capabilities_to_tool_allowlists():
    explorer = build_builtin_subagent_target("explorer")
    worker = build_builtin_subagent_target("worker")
    researcher = build_builtin_subagent_target("researcher")
    devops = build_builtin_subagent_target("devops")

    assert explorer is not None
    assert worker is not None
    assert researcher is not None
    assert devops is not None
    assert "workspace_read_file" in explorer.tool_allowlist
    assert "workspace_write_file" not in explorer.tool_allowlist
    assert "workspace_apply_patch" in worker.tool_allowlist
    assert "run_build" in worker.tool_allowlist
    assert "test_discover" in worker.tool_allowlist
    assert "typecheck_run" in worker.tool_allowlist
    assert "dependency_audit" in worker.tool_allowlist
    assert worker.review_policy["requires_reviewer"] is True
    assert "web_search" in researcher.tool_allowlist
    assert "workspace_apply_patch" not in researcher.tool_allowlist
    assert devops.metadata["risk_level"] == "high"
    assert devops.runtime_policy["max_concurrent_delegations"] == 1


async def test_subagent_registry_ignores_legacy_database_bindings_and_uses_metadata_fallback():
    registry = SubagentRegistry(
        FakeDBPool(
            rows=[
                {
                    "subagent_definition_id": "subagent-reviewer",
                    "name_override": None,
                    "description_override": None,
                    "binding_metadata": {"slug": "db-reviewer"},
                    "name": "DB Review Specialist",
                    "description": "Bound from control plane",
                    "system_prompt": "Use a strict review checklist.",
                    "metadata": {"host_agent_definition_id": "agent-reviewer", "handoff_prompt": "Review carefully."},
                }
            ]
        ),
        FakeAgentRepository(
            {
                "agent-reviewer": {
                    "id": "agent-reviewer",
                    "tenant_id": "tenant-1",
                    "name": "Review Specialist",
                    "description": "Focused reviewer",
                    "status": "active",
                },
                "agent-other": {
                    "id": "agent-other",
                    "tenant_id": "tenant-1",
                    "name": "Metadata Review Specialist",
                    "description": "Metadata fallback reviewer",
                    "status": "active",
                }
            }
        )
    )
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "",
            "metadata": {
                "subagents": [
                    {
                        "agent_definition_id": "agent-other",
                        "slug": "legacy-fallback",
                    }
                ]
            },
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    targets = await registry.resolve_for_definition(definition)

    assert len(targets) == 1
    assert targets[0].slug == "legacy-fallback"
    assert targets[0].agent_definition_id == "agent-other"


async def test_subagent_registry_resolves_authorized_managed_capability_without_target_bridge():
    registry = SubagentRegistry(
        FakeDBPool(
            rows=[
                {
                    "authorization_id": "auth-reviewer",
                    "priority": 50,
                    "authorization_metadata": {"agent_policy": "preferred"},
                    "budget_policy": {"max_tokens": 1200},
                    "publication_id": "pub-reviewer",
                    "visibility": "tenant",
                    "publication_status": "active",
                    "publication_metadata": {"risk_level": "high"},
                    "version_id": "ver-reviewer",
                    "version_number": 3,
                    "lifecycle_status": "active",
                    "system_prompt": "Perform a structured review pass.",
                    "model": "gpt-5.4",
                    "config": {"max_iterations": 4},
                    "version_metadata": {"slug": "managed-reviewer", "handoff_prompt": "Review only the delegated diff."},
                    "output_schema": {"type": "object", "properties": {"review_findings": {"type": "array"}}},
                    "handoff_input_schema": {"type": "object"},
                    "tool_allowlist": ["calculator"],
                    "skill_allowlist": ["code-review"],
                    "mcp_allowlist": ["server-review"],
                    "knowledge_policy": {"mode": "disabled"},
                    "review_policy": {"required": True},
                    "runtime_policy": {"allow_delegation": False},
                    "subagent_definition_id": "subagent-reviewer",
                    "name": "Managed Reviewer",
                    "description": "Published review capability",
                    "definition_metadata": {"category": "review"},
                }
            ]
        ),
        FakeAgentRepository({}),
    )
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "",
            "metadata": {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    targets = await registry.resolve_for_definition(definition)

    assert len(targets) == 1
    assert targets[0].publication_id == "pub-reviewer"
    assert targets[0].version_id == "ver-reviewer"
    assert targets[0].authorization_id == "auth-reviewer"
    assert targets[0].agent_definition_id is None
    assert targets[0].tool_allowlist == ["calculator"]
    assert targets[0].skill_allowlist == ["code-review"]
    assert targets[0].runtime_policy["allow_delegation"] is False
    assert targets[0].budget_policy["max_tokens"] == 1200
    assert targets[0].handoff_prompt == "Review only the delegated diff."


async def test_subagent_handoff_creates_child_run_and_returns_completed_result():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()

    async def start_run(run_id):
        run_repository.rows[run_id]["status"] = "completed"
        run_repository.rows[run_id]["final_output"] = "Child review complete."
        run_repository.rows[run_id]["final_output_text"] = "Child review complete."

    handoff = SubagentHandoff(
        run_repository,
        tracer,
        state_store,
        start_run=start_run,
    )
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        handoff_prompt="Perform a bounded review pass.",
    )

    result = await handoff.delegate(
        parent_run=_build_run(),
        parent_step_id="step-parent",
        planner_action=PlannerAction(
            type="delegate",
            title="Ask review specialist",
            delegate_target="review-specialist",
            delegate_task="Review the migration patch",
            delegate_input={"focus_paths": ["db/alembic/versions/example.py"]},
        ),
        runtime_context={"step_history": [{"title": "Collected patch context"}]},
        target=target,
    )

    assert result.child_run_id == "child-run-1"
    assert result.status == "completed"
    assert result.final_output_text == "Child review complete."
    assert result.input["message"].startswith("Perform a bounded review pass.")
    assert result.input["delegation"]["parent_run_id"] == "run-parent"
    assert result.input["handoff_envelope"]["progress"]["protocol_version"] == "managed-subagent.progress.v1"
    assert result.input["handoff_envelope"]["progress"]["state"] == "in_progress"
    assert tracer.events[0]["event_type"] == "run.created"


async def test_subagent_handoff_embeds_managed_capability_metadata_without_target_bridge():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()
    invocation_repository = FakeInvocationRepository()

    async def start_run(run_id):
        run_repository.rows[run_id]["status"] = "completed"
        run_repository.rows[run_id]["metadata"] = {
            **run_repository.rows[run_id].get("metadata", {}),
            "governance_usage": {
                "prompt_tokens": 180,
                "completion_tokens": 420,
                "total_tokens": 600,
                "cost_usd": 0.24,
            },
        }
        run_repository.rows[run_id]["final_output_text"] = "Managed review complete."
        run_repository.rows[run_id]["final_output_json"] = {
            "answer": "Managed review complete.",
            "progress": {
                "summary": "Reviewed the delegated migration patch.",
                "completed_items": ["Inspected migration plan", "Validated review findings"],
            },
            "review_findings": [
                {
                    "title": "Missing migration",
                    "severity": "high",
                    "description": "Add the missing schema migration.",
                    "path": "db/alembic/versions/example.py",
                    "line": 12,
                }
            ],
            "test_gaps": ["No end-to-end verification covered this path."],
        }

    handoff = SubagentHandoff(
        run_repository,
        tracer,
        state_store,
        start_run=start_run,
        invocation_repository=invocation_repository,
    )
    target = SubagentTarget(
        slug="managed-reviewer",
        name="Managed Reviewer",
        subagent_definition_id="subagent-reviewer",
        publication_id="pub-reviewer",
        version_id="ver-reviewer",
        authorization_id="auth-reviewer",
        system_prompt="Perform a structured review pass.",
        tool_allowlist=["calculator"],
        skill_allowlist=["code-review"],
        review_policy={"required": True},
        runtime_policy={"allow_delegation": False},
        budget_policy={"max_tokens": 1200, "max_cost_usd": 0.5},
    )

    result = await handoff.delegate(
        parent_run=_build_run(),
        parent_step_id="step-parent",
        planner_action=PlannerAction(
            type="delegate",
            title="Ask managed reviewer",
            delegate_target="managed-reviewer",
            delegate_task="Review the migration patch",
        ),
        runtime_context={"step_history": [{"title": "Collected patch context"}]},
        target=target,
    )

    child_run = run_repository.rows[result.child_run_id]
    assert child_run["agent_definition_id"] == "agent-parent"
    assert child_run["metadata"]["managed_subagent"]["publication_id"] == "pub-reviewer"
    assert child_run["metadata"]["managed_subagent"]["authorization_id"] == "auth-reviewer"
    assert child_run["metadata"]["managed_subagent"]["tool_allowlist"] == ["calculator"]
    assert child_run["input"]["delegation"]["subagent_definition_id"] == "subagent-reviewer"
    assert "target_agent_definition_id" not in child_run["input"]["delegation"]
    assert "compatibility_target_agent_definition_id" not in child_run["input"]["delegation"]
    assert child_run["input"]["handoff_envelope"]["protocol_version"] == "managed-subagent.v1"
    assert child_run["input"]["handoff_envelope"]["policy_snapshot"]["target"]["publication_id"] == "pub-reviewer"
    assert child_run["input"]["handoff_envelope"]["policy_snapshot"]["review_policy"]["mode"] == "reviewer"
    assert child_run["input"]["handoff_envelope"]["policy_snapshot"]["governance_policy"]["limits"]["allow_nested_delegation"] is False
    assert child_run["metadata"]["delegation"]["invocation_id"] == "invocation-1"
    assert child_run["metadata"]["managed_subagent"]["budget_policy"] == {"max_tokens": 1200, "max_cost_usd": 0.5}
    assert invocation_repository.creates[0]["request_payload"]["status"] == "requested"
    assert invocation_repository.updates[0]["status"] == "running"
    assert invocation_repository.updates[-1]["status"] == "completed"
    assert invocation_repository.updates[-1]["result_payload"]["final_result"]["final_output_text"] == "Managed review complete."
    assert invocation_repository.updates[-1]["result_payload"]["final_result"]["progress"]["state"] == "completed"
    assert invocation_repository.updates[-1]["result_payload"]["final_result"]["progress"]["completed_items"] == [
        "Inspected migration plan",
        "Validated review findings",
    ]
    assert invocation_repository.updates[-1]["result_payload"]["governance_policy"]["budget"]["usage"]["total_tokens"] == 600
    assert invocation_repository.updates[-1]["result_payload"]["governance_policy"]["budget"]["usage"]["cost_usd"] == 0.24
    assert invocation_repository.updates[-1]["result_payload"]["governance_policy"]["budget"]["last_invocation_usage"]["total_tokens"] == 600
    assert invocation_repository.updates[-1]["result_payload"]["governance_policy"]["budget"]["prior_usage"]["total_tokens"] is None
    assert invocation_repository.updates[-1]["result_payload"]["governance_policy"]["budget"]["usage_status"] == "within_limits"
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["mode"] == "reviewer"
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["decision"] == "changes_requested"
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["blocking_finding_count"] == 1
    assert result.progress["state"] == "completed"
    assert result.metadata["review_result"]["decision"] == "changes_requested"
    assert result.metadata["governance_policy"]["budget"]["usage"]["total_tokens"] == 600
    assert result.metadata["governance_policy"]["budget"]["last_invocation_usage"]["total_tokens"] == 600


async def test_subagent_handoff_enforces_timeout_policy():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()

    async def start_run(run_id):
        async def _complete_later():
            await asyncio.sleep(0.3)
            run_repository.rows[run_id]["status"] = "completed"
            run_repository.rows[run_id]["final_output_text"] = "Late completion."

        task = asyncio.create_task(_complete_later())
        state_store.register_task(run_id, task)

    handoff = SubagentHandoff(
        run_repository,
        tracer,
        state_store,
        start_run=start_run,
    )
    target = SubagentTarget(
        slug="managed-reviewer",
        name="Managed Reviewer",
        subagent_definition_id="subagent-reviewer",
        runtime_policy={"timeout_seconds": 0.05},
    )

    try:
        await handoff.delegate(
            parent_run=_build_run(),
            parent_step_id="step-parent",
            planner_action=PlannerAction(
                type="delegate",
                title="Ask managed reviewer",
                delegate_target="managed-reviewer",
                delegate_task="Review the migration patch",
            ),
            runtime_context={"step_history": [{"title": "Collected patch context"}]},
            target=target,
        )
    except TimeoutError as exc:
        assert "timeout of 0.05s" in str(exc)
    else:
        raise AssertionError("Expected timeout enforcement to raise TimeoutError")


async def test_subagent_handoff_hard_budget_limit_marks_result_failed():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()

    async def start_run(run_id):
        run_repository.rows[run_id]["status"] = "completed"
        run_repository.rows[run_id]["metadata"] = {
            **run_repository.rows[run_id].get("metadata", {}),
            "governance_usage": {"total_tokens": 250},
        }
        run_repository.rows[run_id]["final_output_text"] = "Child work complete."

    handoff = SubagentHandoff(
        run_repository,
        tracer,
        state_store,
        start_run=start_run,
    )
    target = SubagentTarget(
        slug="budget-worker",
        name="Budget Worker",
        agent_definition_id="agent-worker",
        budget_policy={"max_tokens": 100, "hard_limit": True},
    )

    result = await handoff.delegate(
        parent_run=_build_run(),
        parent_step_id="step-parent",
        planner_action=PlannerAction(
            type="delegate",
            title="Ask budget worker",
            delegate_target="budget-worker",
            delegate_task="Run a bounded task",
        ),
        runtime_context={"step_history": [{"title": "Collected context"}]},
        target=target,
    )

    assert result.status == "failed"
    assert result.metadata["governance_policy"]["budget"]["usage_status"] == "over_budget"
    assert result.metadata["governance_policy"]["enforcement"]["budget_hard_limit_exceeded"] is True


async def test_subagent_handoff_start_delegate_returns_running_without_waiting():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()

    async def start_run(run_id):
        async def _complete_later():
            await asyncio.sleep(0.2)
            run_repository.rows[run_id]["status"] = "completed"
            run_repository.rows[run_id]["final_output_text"] = "Async completion."

        state_store.register_task(run_id, asyncio.create_task(_complete_later()))

    handoff = SubagentHandoff(
        run_repository,
        tracer,
        state_store,
        start_run=start_run,
    )
    target = SubagentTarget(
        slug="parallel-worker",
        name="Parallel Worker",
        agent_definition_id="agent-worker",
        runtime_policy={"async_execution": True},
    )

    result = await handoff.start_delegate(
        parent_run=_build_run(),
        parent_step_id="step-parent",
        planner_action=PlannerAction(
            type="delegate",
            title="Ask parallel worker",
            delegate_target="parallel-worker",
            delegate_task="Run an independent check",
        ),
        runtime_context={"step_history": [{"title": "Collected context"}]},
        target=target,
    )

    assert result.status == "running"
    assert result.child_run_id == "child-run-1"
    assert run_repository.rows[result.child_run_id]["status"] == "queued"
    assert result.metadata["async_execution"] is True


async def test_orchestrator_execute_delegate_action_records_step_and_subagent_events():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="completed",
        target=target,
        summary="Child review complete.",
        final_output="Child review complete.",
        final_output_text="Child review complete.",
        artifacts=[],
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "completed",
            "summary": "Child review complete.",
            "completed_items": ["Reviewed the patch"],
            "pending_items": [],
            "next_action": None,
            "artifact_count": 0,
        },
        clarification={},
        metadata={
            "invocation_id": "invocation-1",
            "review_result": {
                "protocol_version": "managed-subagent.review-result.v1",
                "required": True,
                "mode": "reviewer",
                "decision": "approved_with_findings",
                "approved": True,
                "summary": "Reviewer 通过但有提示 · 1 条 finding",
                "finding_count": 1,
                "blocking_finding_count": 0,
                "findings": [
                    {
                        "title": "Missing regression test",
                        "severity": "medium",
                        "description": "Add a regression test for the fallback path.",
                    }
                ],
                "test_gaps": ["No automated regression test was run."],
            },
            "handoff_envelope": {
                "protocol_version": "managed-subagent.v1",
                "task": {"message": "Review the patch"},
                "constraints": ["focus_paths: db/alembic/versions/example.py"],
                "context_slice": {
                    "delegation_depth": 0,
                    "recent_observations": [{"title": "Collected patch context"}],
                    "conversation_tail": [],
                    "mounted_knowledge_base_ids": [],
                },
                "policy_snapshot": {"target": {"slug": "review-specialist"}},
            },
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "review-specialist",
                "budget": {
                    "max_tokens": 1200,
                    "usage": {"total_tokens": 640, "source": "metadata.governance_usage"},
                    "usage_status": "within_limits",
                },
            },
        },
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    handoff = FakeHandoff(delegation)
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={"step_history": []},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Review the patch",
            ),
            reasoning="A bounded specialist review is the fastest next step.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is None
    assert observation["delegate_target"] == "review-specialist"
    assert observation["result"]["child_run_id"] == "child-run-1"
    assert run_repository.updated_steps[0]["output_payload"]["delegate_result"]["summary"] == "Child review complete."
    assert run_repository.updated_steps[0]["output_payload"]["handoff"]["protocol_version"] == "managed-subagent.v1"
    assert run_repository.updated_steps[0]["output_payload"]["review_result"]["decision"] == "approved_with_findings"
    assert run_repository.updated_steps[0]["output_payload"]["governance_policy"]["protocol_version"] == "managed-subagent.governance.v1"
    assert run_repository.updated_steps[0]["output_payload"]["governance_policy"]["budget"]["usage"]["total_tokens"] == 640
    assert run_repository.updated_steps[0]["output_payload"]["governance_policy"]["history"]["attempt_count"] == 1
    assert run_repository.updated_steps[0]["output_payload"]["progress"]["state"] == "completed"
    event_types = [event["event_type"] for event in tracer.events]
    assert "subagent.started" in event_types
    assert "subagent.completed" in event_types
    completed_event = next(event for event in tracer.events if event["event_type"] == "subagent.completed")
    assert completed_event["payload"]["review_result"]["mode"] == "reviewer"
    assert completed_event["payload"]["progress"]["completed_items"] == ["Reviewed the patch"]
    assert completed_event["payload"]["governance_policy"]["target_slug"] == "review-specialist"
    assert completed_event["payload"]["governance_policy"]["budget"]["usage"]["total_tokens"] == 640
    assert completed_event["payload"]["governance_policy"]["budget"]["last_invocation_usage"]["total_tokens"] == 640
    assert run_repository.updated_steps[0]["output_payload"]["governance_policy"]["history"]["active_child_count"] == 0


async def test_orchestrator_async_delegate_registers_pending_child_without_blocking_parent():
    target = SubagentTarget(
        slug="parallel-worker",
        name="Parallel Worker",
        agent_definition_id="agent-worker",
        runtime_policy={"delegation_mode": "parallel_worker"},
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="running",
        target=target,
        summary="Parallel Worker child run started.",
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "in_progress",
            "summary": "Parallel worker is running.",
        },
        metadata={
            "invocation_id": "invocation-1",
            "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "parallel-worker",
                "waiting_user": {"propagation": "continue_parent"},
            },
            "async_execution": True,
        },
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    handoff = FakeHandoff(delegation)
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )
    runtime_context = {"step_history": []}

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context=runtime_context,
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask parallel worker",
                delegate_target="parallel-worker",
                delegate_task="Run the independent verification",
            ),
            reasoning="Parallelizable verification.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert delegated_result is None
    assert observation["status"] == "running"
    assert runtime_context["pending_subagent_invocations"][0]["child_run_id"] == "child-run-1"
    assert runtime_context["subagent_governance_ledger"]["targets"]["parallel-worker"]["history"]["active_child_count"] == 1
    assert run_repository.updated_steps[0]["status"] == "running"


async def test_orchestrator_collects_pending_subagent_completion_without_double_counting_attempt():
    target = SubagentTarget(
        slug="parallel-worker",
        name="Parallel Worker",
        agent_definition_id="agent-worker",
        runtime_policy={"delegation_mode": "parallel_worker"},
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="completed",
        target=target,
        summary="Async worker complete.",
        final_output_text="Async worker complete.",
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "completed",
            "summary": "Async worker complete.",
        },
        metadata={
            "invocation_id": "invocation-1",
            "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
            "review_result": {"protocol_version": "managed-subagent.review-result.v1", "decision": "not_required"},
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "parallel-worker",
                "budget": {
                    "last_invocation_usage": {"total_tokens": 120},
                    "usage": {"total_tokens": 120},
                },
            },
        },
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    handoff = FakeHandoff(delegation)
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )
    runtime_context = {
        "step_history": [],
        "pending_subagent_invocations": [
            {
                "child_run_id": "child-run-1",
                "target": target.model_dump(mode="json"),
                "parent_step_id": "step-1",
                "planner_result": PlannerResult(
                    action=PlannerAction(
                        type="delegate",
                        title="Ask parallel worker",
                        delegate_target="parallel-worker",
                        delegate_task="Run the independent verification",
                    ),
                    reasoning="Parallelizable verification.",
                    iteration=2,
                ).model_dump(mode="json"),
                "delegation_gate": {
                    "governance": {
                        "prior_usage": {},
                        "history": {
                            "target_slug": "parallel-worker",
                            "attempt_count": 1,
                            "active_child_count": 1,
                            "statuses": ["running"],
                        },
                    }
                },
                "invocation_id": "invocation-1",
                "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
                "child_input": {"message": "Run the independent verification"},
            }
        ],
        "subagent_governance_ledger": {
            "protocol_version": "managed-subagent.governance.v1",
            "targets": {
                "parallel-worker": {
                    "target_slug": "parallel-worker",
                    "history": {
                        "target_slug": "parallel-worker",
                        "attempt_count": 1,
                        "failed_attempt_count": 0,
                        "active_child_count": 1,
                        "waiting_user_count": 0,
                        "statuses": ["running"],
                    },
                    "usage": {},
                    "last_invocation_usage": {},
                    "active_children": {
                        "child:child-run-1": {
                            "child_run_id": "child-run-1",
                            "invocation_id": "invocation-1",
                            "status": "running",
                            "counts_as_active_child": True,
                        }
                    },
                    "latest_waiting_user": {},
                    "recent_outcomes": [],
                }
            },
        },
    }

    terminal = await orchestrator._collect_pending_subagent_invocations(
        run=_build_run(),
        runtime_context=runtime_context,
    )

    assert terminal is None
    assert runtime_context["pending_subagent_invocations"] == []
    assert runtime_context["step_history"][0]["result"]["status"] == "completed"
    history = runtime_context["subagent_governance_ledger"]["targets"]["parallel-worker"]["history"]
    assert history["attempt_count"] == 1
    assert history["active_child_count"] == 0
    assert runtime_context["subagent_governance_ledger"]["targets"]["parallel-worker"]["usage"]["total_tokens"] == 120
    completed_event = next(event for event in tracer.events if event["event_type"] == "subagent.completed")
    assert completed_event["payload"]["child_run_id"] == "child-run-1"


async def test_orchestrator_subagent_waiting_user_event_exposes_protocol_question():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="waiting_user",
        target=target,
        summary="Need the migration rollout window.",
        final_output="Need the migration rollout window.",
        final_output_text="Need the migration rollout window.",
        artifacts=[{"artifact_type": "answer", "title": "Question"}],
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "blocked",
            "summary": "Review is blocked pending rollout details.",
            "completed_items": ["Checked the current rollout plan"],
            "pending_items": ["Need the migration rollout window."],
            "next_action": "Answer the clarification so the child run can continue.",
            "artifact_count": 1,
        },
        clarification={
            "protocol_version": "managed-subagent.clarification.v1",
            "state": "required",
            "question": "Need the migration rollout window.",
            "reason": "The rollout plan cannot be approved without a concrete window.",
            "required_fields": ["migration rollout window"],
            "response_hint": "Provide the approved rollout window and any blackout constraints.",
            "blocking": True,
        },
        metadata={
            "invocation_id": "invocation-1",
            "review_result": {
                "protocol_version": "managed-subagent.review-result.v1",
                "required": False,
                "mode": "none",
                "decision": "needs_input",
            },
            "handoff_envelope": {
                "protocol_version": "managed-subagent.v1",
                "task": {"message": "Review the rollout plan"},
                "constraints": ["focus_paths: db/alembic/versions/example.py"],
                "policy_snapshot": {"target": {"slug": "review-specialist"}},
            },
        },
    )
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(delegation),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={"step_history": [{"title": "Collected rollout context"}]},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Review the rollout plan",
            ),
            reasoning="Need a bounded follow-up review.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is not None
    waiting_event = next(event for event in tracer.events if event["event_type"] == "subagent.waiting_user")
    assert waiting_event["payload"]["question"] == "Need the migration rollout window."
    assert waiting_event["payload"]["partial_result"]["question"] == "Need the migration rollout window."
    assert waiting_event["payload"]["partial_result"]["progress"]["state"] == "blocked"
    assert waiting_event["payload"]["partial_result"]["clarification"]["required_fields"] == ["migration rollout window"]
    assert waiting_event["payload"]["clarification"]["response_hint"] == "Provide the approved rollout window and any blackout constraints."
    assert waiting_event["payload"]["handoff_envelope"]["protocol_version"] == "managed-subagent.v1"
    assert waiting_event["payload"]["governance_policy"]["protocol_version"] == "managed-subagent.governance.v1"
    assert waiting_event["payload"]["governance_policy"]["history"]["waiting_user_count"] == 1


async def test_orchestrator_bubbles_waiting_user_to_parent_run_by_default():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="waiting_user",
        target=target,
        summary="Need the migration rollout window.",
        final_output="Need the migration rollout window.",
        final_output_text="Need the migration rollout window.",
        artifacts=[{"artifact_type": "answer", "name": "Question", "payload": {"text": "Need the migration rollout window."}}],
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "blocked",
            "summary": "Review is blocked pending rollout details.",
            "completed_items": ["Checked the current rollout plan"],
            "pending_items": ["Need the migration rollout window."],
            "next_action": "Answer the clarification so the child run can continue.",
            "artifact_count": 1,
        },
        clarification={
            "protocol_version": "managed-subagent.clarification.v1",
            "state": "required",
            "question": "Need the migration rollout window.",
            "reason": "The rollout plan cannot be approved without a concrete window.",
            "required_fields": ["migration rollout window"],
            "response_hint": "Provide the approved rollout window and any blackout constraints.",
            "blocking": True,
        },
        metadata={
            "invocation_id": "invocation-1",
            "review_result": {
                "protocol_version": "managed-subagent.review-result.v1",
                "required": False,
                "mode": "none",
                "decision": "needs_input",
            },
            "handoff_envelope": {
                "protocol_version": "managed-subagent.v1",
                "task": {"message": "Review the rollout plan"},
                "constraints": ["focus_paths: db/alembic/versions/example.py"],
                "policy_snapshot": {"target": {"slug": "review-specialist"}},
            },
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "review-specialist",
                "waiting_user": {
                    "propagation": "bubble_to_parent",
                    "counts_as_active_child": True,
                },
            },
        },
    )
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(delegation),
    )
    runtime_context = {"step_history": [{"title": "Collected rollout context"}]}
    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context=runtime_context,
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Review the rollout plan",
            ),
            reasoning="Need a bounded follow-up review.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is not None
    assert delegated_result["status"] == "waiting_user"
    assert delegated_result["final_output_text"] == "Need the migration rollout window."
    assert delegated_result["context"]["pending_question"] == "Need the migration rollout window."
    assert delegated_result["context"]["pending_subagent_clarification"]["child_run_id"] == "child-run-1"
    assert delegated_result["context"]["pending_subagent_clarification"]["governance_policy"]["waiting_user"]["propagation"] == "bubble_to_parent"
    assert delegated_result["context"]["pending_subagent_clarification"]["waiting_user_policy"]["propagation"] == "bubble_to_parent"
    assert delegated_result["context"]["pending_subagent_clarification"]["governance_policy"]["history"]["waiting_user_count"] == 1
    assert delegated_result["context"]["pending_subagent_clarification"]["waiting_user_path"][1]["run_id"] == "child-run-1"
    assert delegated_result["context"]["subagent_governance_ledger"]["targets"]["review-specialist"]["history"]["active_child_count"] == 1
    assert delegated_result["final_output_json"]["source"] == "subagent_waiting_user"
    assert delegated_result["final_output_json"]["clarification"]["required_fields"] == ["migration rollout window"]
    assert delegated_result["final_output_json"]["governance_policy"]["target_slug"] == "review-specialist"
    assert delegated_result["final_output_json"]["waiting_user_policy"]["propagation"] == "bubble_to_parent"
    assert delegated_result["final_output_json"]["waiting_user_path"][1]["status"] == "waiting_user"
    assert delegated_result["artifacts"][0]["artifact_type"] == "answer"


async def test_orchestrator_preserves_nested_waiting_user_path_when_child_returns_multihop_path():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="waiting_user",
        target=target,
        summary="Need final production rollout window.",
        final_output="Need final production rollout window.",
        final_output_text="Need final production rollout window.",
        artifacts=[],
        progress={
            "protocol_version": "managed-subagent.progress.v1",
            "state": "blocked",
            "summary": "Nested review is blocked on deployment timing.",
            "waiting_user_path": [
                {"run_id": "child-run-1", "role": "parent", "status": "running"},
                {"run_id": "grandchild-run-1", "role": "child", "status": "waiting_user"},
            ],
        },
        clarification={
            "protocol_version": "managed-subagent.clarification.v1",
            "state": "required",
            "question": "Need final production rollout window.",
            "waiting_user_path": [
                {"run_id": "child-run-1", "role": "parent", "status": "running"},
                {"run_id": "grandchild-run-1", "role": "child", "status": "waiting_user"},
            ],
        },
        metadata={
            "invocation_id": "invocation-1",
            "review_result": {
                "protocol_version": "managed-subagent.review-result.v1",
                "required": False,
                "mode": "none",
                "decision": "needs_input",
            },
            "handoff_envelope": {
                "protocol_version": "managed-subagent.v1",
                "task": {"message": "Review the rollout plan"},
                "policy_snapshot": {"target": {"slug": "review-specialist"}},
            },
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "review-specialist",
                "waiting_user": {
                    "propagation": "bubble_to_parent",
                    "counts_as_active_child": True,
                },
            },
        },
    )
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=FakeTracer(),
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(delegation),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={"step_history": [{"title": "Collected rollout context"}]},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Review the rollout plan",
            ),
            reasoning="Need a bounded follow-up review.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is not None
    waiting_user_path = delegated_result["final_output_json"]["waiting_user_path"]
    assert waiting_user_path == [
        {"run_id": "run-parent", "role": "parent", "status": "running"},
        {"run_id": "child-run-1", "role": "parent", "status": "running"},
        {"run_id": "grandchild-run-1", "role": "child", "status": "waiting_user"},
    ]
    assert delegated_result["context"]["pending_subagent_clarification"]["waiting_user_path"] == waiting_user_path


async def test_orchestrator_keeps_parent_running_when_waiting_user_propagation_is_continue_parent():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        runtime_policy={"waiting_user_propagation": "continue_parent"},
    )
    handoff = FakeHandoff(
        SubagentDelegationResult(
            child_run_id="child-run-2",
            status="completed",
            target=target,
            summary="Second review completed.",
            final_output_text="Second review completed.",
            metadata={
                "protocol_version": "managed-subagent.v1",
                "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
                "review_result": {"mode": "none", "required": False, "decision": "not_required"},
            },
        )
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={
            "step_history": [
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {"status": "waiting_user"},
                }
            ]
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist again",
                delegate_target="review-specialist",
                delegate_task="Resume with fresh details",
            ),
            reasoning="Waiting-user should not bubble to parent for this capability.",
            iteration=4,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is None


async def test_orchestrator_accumulates_governance_usage_from_history_and_current_invocation():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        budget_policy={"max_tokens": 1000, "max_cost_usd": 0.5},
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-3",
        status="completed",
        target=target,
        summary="Third review completed.",
        final_output_text="Third review completed.",
        metadata={
            "invocation_id": "invocation-3",
            "review_result": {"mode": "none", "required": False, "decision": "not_required"},
            "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
            "governance_policy": {
                "protocol_version": "managed-subagent.governance.v1",
                "target_slug": "review-specialist",
                "budget": {
                    "max_tokens": 1000,
                    "max_cost_usd": 0.5,
                    "last_invocation_usage": {
                        "total_tokens": 220,
                        "cost_usd": 0.08,
                        "source": "metadata.governance_usage",
                    },
                },
                "waiting_user": {
                    "propagation": "continue_parent",
                    "counts_as_active_child": False,
                },
            },
        },
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(delegation),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={
            "step_history": [
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {
                        "status": "waiting_user",
                        "waiting_user_policy": {"propagation": "continue_parent"},
                        "governance_policy": {
                            "budget": {
                                "last_invocation_usage": {
                                    "total_tokens": 180,
                                    "cost_usd": 0.05,
                                    "source": "step_history",
                                }
                            }
                        },
                    },
                },
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {
                        "status": "completed",
                        "governance_policy": {
                            "budget": {
                                "last_invocation_usage": {
                                    "total_tokens": 140,
                                    "cost_usd": 0.04,
                                    "source": "step_history",
                                }
                            }
                        },
                    },
                },
            ]
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Review another change",
            ),
            reasoning="Need another bounded review.",
            iteration=5,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is None
    budget = run_repository.updated_steps[0]["output_payload"]["governance_policy"]["budget"]
    history = run_repository.updated_steps[0]["output_payload"]["governance_policy"]["history"]
    assert budget["prior_usage"]["total_tokens"] == 320
    assert budget["last_invocation_usage"]["total_tokens"] == 220
    assert budget["usage"]["total_tokens"] == 540
    assert budget["remaining_tokens"] == 460
    assert history["attempt_count"] == 3
    assert history["waiting_user_count"] == 1
    assert history["continue_parent_count"] == 1
    assert history["active_child_count"] == 0


async def test_orchestrator_rejects_delegate_when_single_agent_gate_is_not_satisfied():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    handoff = FakeHandoff(
        SubagentDelegationResult(
            child_run_id="child-run-1",
            status="completed",
            target=target,
        )
    )
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={"step_history": [], "tool_failures": 0},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Take a look",
            ),
            reasoning="Delegate immediately.",
            iteration=1,
        ),
        available_subagents=[target],
        available_tools=[{"name": "knowledge_search", "kind": "knowledge"}],
    )

    assert observation["status"] == "failed"
    assert delegated_result is None
    assert "Delegation gate rejected" in observation["error"]
    assert handoff.calls == []
    assert run_repository.updated_steps[0]["status"] == "failed"
    assert run_repository.updated_steps[0]["metadata"]["delegation_gate"]["allowed"] is False
    assert run_repository.updated_steps[0]["metadata"]["delegation_gate"]["governance"]["protocol_version"] == "managed-subagent.governance.v1"
    event_types = [event["event_type"] for event in tracer.events]
    assert "subagent.rejected" in event_types


async def test_orchestrator_rejects_delegate_when_retry_limit_exceeded():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        runtime_policy={"max_retry_attempts": 1},
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(
            SubagentDelegationResult(
                child_run_id="child-run-1",
                status="completed",
                target=target,
            )
        ),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={
            "step_history": [
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {"status": "failed"},
                },
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {"status": "failed"},
                },
            ]
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Try the review again",
            ),
            reasoning="Retry the specialist review.",
            iteration=3,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "failed"
    assert delegated_result is None
    assert "retry limit 1" in observation["error"]


async def test_orchestrator_rejects_delegate_when_active_child_limit_exceeded():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        runtime_policy={"max_concurrent_delegations": 1},
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=FakeHandoff(
            SubagentDelegationResult(
                child_run_id="child-run-1",
                status="completed",
                target=target,
            )
        ),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={
            "step_history": [
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {"status": "waiting_user"},
                }
            ]
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist",
                delegate_target="review-specialist",
                delegate_task="Start another review",
            ),
            reasoning="Parallelize another review pass.",
            iteration=3,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "failed"
    assert delegated_result is None
    assert "concurrency limit 1" in observation["error"]


async def test_orchestrator_allows_delegate_when_waiting_user_does_not_hold_concurrency_slot():
    target = SubagentTarget(
        slug="review-specialist",
        name="Review Specialist",
        agent_definition_id="agent-reviewer",
        runtime_policy={
            "max_concurrent_delegations": 1,
            "waiting_user_counts_as_active_child": False,
        },
    )
    handoff = FakeHandoff(
        SubagentDelegationResult(
            child_run_id="child-run-2",
            status="completed",
            target=target,
            summary="Second review completed.",
            final_output_text="Second review completed.",
            metadata={
                "protocol_version": "managed-subagent.v1",
                "handoff_envelope": {"protocol_version": "managed-subagent.v1"},
                "review_result": {"mode": "none", "required": False, "decision": "not_required"},
                "governance_policy": {
                    "protocol_version": "managed-subagent.governance.v1",
                    "waiting_user": {"counts_as_active_child": False},
                },
            },
        )
    )
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=None,
        state_store=FakeStateStore(),
        subagent_handoff=handoff,
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={
            "step_history": [
                {
                    "delegate_target": "review-specialist",
                    "status": "completed",
                    "result": {"status": "waiting_user"},
                }
            ]
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask review specialist again",
                delegate_target="review-specialist",
                delegate_task="Resume with fresh details",
            ),
            reasoning="Waiting-user should not block another bounded delegation.",
            iteration=4,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert observation["status"] == "completed"
    assert delegated_result is None
    assert handoff.calls


def test_record_delegation_outcome_keeps_latest_waiting_user_from_other_active_child():
    runtime_context = {
        "subagent_governance_ledger": {
            "protocol_version": "managed-subagent.governance.v1",
            "targets": {
                "review-specialist": {
                    "history": {
                        "target_slug": "review-specialist",
                        "attempt_count": 2,
                        "failed_attempt_count": 0,
                        "active_child_count": 2,
                        "waiting_user_count": 1,
                        "bubble_to_parent_count": 1,
                        "continue_parent_count": 0,
                        "child_only_count": 0,
                        "statuses": ["waiting_user", "running"],
                        "waiting_user_strategies": ["bubble_to_parent"],
                    },
                    "active_children": {
                        "child:child-run-1": {
                            "child_run_id": "child-run-1",
                            "invocation_id": "invocation-1",
                            "status": "waiting_user",
                            "counts_as_active_child": True,
                            "waiting_user_propagation": "bubble_to_parent",
                            "question": "Need rollout window.",
                            "waiting_user_path": [
                                {"run_id": "run-parent", "role": "parent", "status": "running"},
                                {"run_id": "child-run-1", "role": "child", "status": "waiting_user"},
                            ],
                        },
                        "child:child-run-2": {
                            "child_run_id": "child-run-2",
                            "invocation_id": "invocation-2",
                            "status": "running",
                            "counts_as_active_child": True,
                        },
                    },
                    "latest_waiting_user": {
                        "child_run_id": "child-run-1",
                        "invocation_id": "invocation-1",
                        "question": "Need rollout window.",
                        "waiting_user_path": [
                            {"run_id": "run-parent", "role": "parent", "status": "running"},
                            {"run_id": "child-run-1", "role": "child", "status": "waiting_user"},
                        ],
                        "waiting_user_propagation": "bubble_to_parent",
                    },
                }
            },
        }
    }

    entry = record_delegation_outcome(
        runtime_context,
        target_slug="review-specialist",
        status="completed",
        child_run_id="child-run-2",
        invocation_id="invocation-2",
        usage={},
    )

    assert entry["history"]["active_child_count"] == 1
    assert entry["latest_waiting_user"]["child_run_id"] == "child-run-1"
    assert entry["latest_waiting_user"]["question"] == "Need rollout window."
    assert runtime_context["subagent_governance_ledger"]["targets"]["review-specialist"]["latest_waiting_user"]["child_run_id"] == "child-run-1"


async def test_orchestrator_managed_subagent_definition_and_gates():
    target = SubagentTarget(
        slug="managed-reviewer",
        name="Managed Reviewer",
        subagent_definition_id="subagent-reviewer",
        publication_id="pub-reviewer",
        version_id="ver-reviewer",
        system_prompt="You are a review specialist.",
        model="gpt-5.4",
        config={"max_iterations": 3},
        output_schema={"type": "object", "properties": {"review_findings": {"type": "array"}}},
        runtime_policy={"allow_delegation": False},
    )
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=object(),
        summarizer=object(),
        llm_service=None,
        tracer=FakeTracer(),
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=None,
        state_store=FakeStateStore(),
    )
    parent_definition = AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "Base instructions.",
            "model": "gpt-5.3",
            "config": {"max_iterations": 8},
            "metadata": {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )
    managed_run = _build_run(
        metadata={
            "managed_subagent": target.model_dump(mode="json"),
        }
    )

    managed_target = orchestrator._resolve_managed_subagent(managed_run)
    effective_definition = orchestrator._apply_managed_subagent_definition(parent_definition, managed_target)

    assert managed_target is not None
    assert managed_target.publication_id == "pub-reviewer"
    assert effective_definition.name == "Managed Reviewer"
    assert effective_definition.model == "gpt-5.4"
    assert effective_definition.config["max_iterations"] == 3
    assert "review specialist" in effective_definition.system_prompt.lower()
    assert managed_target.allows_nested_delegation() is False
