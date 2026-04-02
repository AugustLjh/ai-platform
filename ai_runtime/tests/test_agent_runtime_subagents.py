from __future__ import annotations

from datetime import datetime, timezone

from core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from core.agent_runtime.orchestrator import AgentOrchestrator
from core.agent_runtime.subagents.handoff import SubagentHandoff
from core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget
from core.agent_runtime.subagents.registry import SubagentRegistry


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

    def is_cancelled(self, run_id):
        return run_id in self.cancelled

    def get_task(self, run_id):
        return None


class FakeHandoff:
    def __init__(self, result: SubagentDelegationResult):
        self.result = result
        self.calls = []

    async def delegate(self, **payload):
        self.calls.append(payload)
        return self.result


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


async def test_subagent_registry_prefers_database_bindings_over_metadata_fallback():
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
    assert targets[0].slug == "db-reviewer"
    assert targets[0].agent_definition_id == "agent-reviewer"
    assert targets[0].handoff_prompt == "Review carefully."


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
    assert tracer.events[0]["event_type"] == "run.created"


async def test_subagent_handoff_embeds_managed_capability_metadata_without_target_bridge():
    run_repository = FakeRunRepository()
    tracer = FakeTracer()
    state_store = FakeStateStore()
    invocation_repository = FakeInvocationRepository()

    async def start_run(run_id):
        run_repository.rows[run_id]["status"] = "completed"
        run_repository.rows[run_id]["final_output_text"] = "Managed review complete."
        run_repository.rows[run_id]["final_output_json"] = {
            "answer": "Managed review complete.",
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
    assert child_run["input"]["handoff_envelope"]["protocol_version"] == "managed-subagent.v1"
    assert child_run["input"]["handoff_envelope"]["policy_snapshot"]["target"]["publication_id"] == "pub-reviewer"
    assert child_run["input"]["handoff_envelope"]["policy_snapshot"]["review_policy"]["mode"] == "reviewer"
    assert child_run["metadata"]["delegation"]["invocation_id"] == "invocation-1"
    assert invocation_repository.creates[0]["request_payload"]["status"] == "requested"
    assert invocation_repository.updates[0]["status"] == "running"
    assert invocation_repository.updates[-1]["status"] == "completed"
    assert invocation_repository.updates[-1]["result_payload"]["final_result"]["final_output_text"] == "Managed review complete."
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["mode"] == "reviewer"
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["decision"] == "changes_requested"
    assert invocation_repository.updates[-1]["result_payload"]["review_result"]["blocking_finding_count"] == 1
    assert result.metadata["review_result"]["decision"] == "changes_requested"


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

    observation = await orchestrator._execute_delegate_action(
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
    assert observation["delegate_target"] == "review-specialist"
    assert observation["result"]["child_run_id"] == "child-run-1"
    assert run_repository.updated_steps[0]["output_payload"]["delegate_result"]["summary"] == "Child review complete."
    assert run_repository.updated_steps[0]["output_payload"]["handoff"]["protocol_version"] == "managed-subagent.v1"
    assert run_repository.updated_steps[0]["output_payload"]["review_result"]["decision"] == "approved_with_findings"
    event_types = [event["event_type"] for event in tracer.events]
    assert "subagent.started" in event_types
    assert "subagent.completed" in event_types
    completed_event = next(event for event in tracer.events if event["event_type"] == "subagent.completed")
    assert completed_event["payload"]["review_result"]["mode"] == "reviewer"


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

    observation = await orchestrator._execute_delegate_action(
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
    waiting_event = next(event for event in tracer.events if event["event_type"] == "subagent.waiting_user")
    assert waiting_event["payload"]["question"] == "Need the migration rollout window."
    assert waiting_event["payload"]["partial_result"]["question"] == "Need the migration rollout window."
    assert waiting_event["payload"]["handoff_envelope"]["protocol_version"] == "managed-subagent.v1"


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

    observation = await orchestrator._execute_delegate_action(
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
    assert "Delegation gate rejected" in observation["error"]
    assert handoff.calls == []
    assert run_repository.updated_steps[0]["status"] == "failed"
    assert run_repository.updated_steps[0]["metadata"]["delegation_gate"]["allowed"] is False
    event_types = [event["event_type"] for event in tracer.events]
    assert "subagent.rejected" in event_types


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
