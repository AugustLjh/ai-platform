from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_runtime.core.agent_runtime.events import MASK
from ai_runtime.core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from ai_runtime.core.agent_runtime.orchestrator import AgentOrchestrator
from ai_runtime.core.agent_runtime.policy import RuntimePolicy
from ai_runtime.core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _build_definition() -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "id": "agent-parent",
            "tenant_id": "tenant-1",
            "name": "Parent Agent",
            "system_prompt": "Stay concise.",
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )


def _build_run() -> AgentRun:
    return AgentRun.model_validate(
        {
            "id": "run-parent",
            "agent_definition_id": "agent-parent",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": "running",
            "input": {"message": "Find the docs and summarize them."},
            "plan": {},
            "context": {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )


class FakeRegistry:
    async def get_spec(self, tool_name, context=None):
        return {"kind": "mcp"} if tool_name == "search_docs" else {"kind": "builtin"}

    async def list_specs(self, context=None):
        return []


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.registry = FakeRegistry()

    async def execute_tool(self, planner_result, tool_context=None, policy=None):
        return self.result

    def shape_output(self, value, output_schema):
        return value

    def format_output(self, value, output_schema):
        return str(value)


class ToolBudgetRegistry(FakeRegistry):
    async def get_spec(self, tool_name, context=None):
        if tool_name == "run_tests":
            return {
                "kind": "sandbox-exec",
                "metadata": {
                    "requires_workspace": False,
                    "requires_sandbox": True,
                },
            }
        return await super().get_spec(tool_name, context=context)


class DummyHandoff:
    def __init__(self, delegation: SubagentDelegationResult):
        self.delegation = delegation

    async def start_delegate(self, **kwargs):
        return self.delegation

    async def delegate(self, **kwargs):
        return self.delegation


class FakeSummarizer:
    async def summarize(self, **kwargs):
        return "Final synthesis.", {"resolved_model_name": "summary-model"}


class FakeLLMService:
    def __init__(self):
        self.resolve_calls: list[dict] = []

    async def resolve_candidates(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return {"requested_model": None, "candidates": [{}]}

    async def chat_with_candidates(self, resolution, messages, **kwargs):
        return "{}", {"resolved_model_name": "fake-model"}


class CapturingSummarizer:
    def __init__(self):
        self.calls: list[dict] = []

    async def summarize(self, **kwargs):
        self.calls.append(kwargs)
        prompt_context = kwargs["runtime_context"]["prompt_context"]
        assert prompt_context["mode"] == "compressed"
        assert prompt_context["compressed_context"]["objective"]
        return "Compressed synthesis.", {"resolved_model_name": "summary-model"}


class FakeRunRepository:
    def __init__(self, run_row: dict | None = None):
        self.updated_steps: list[dict] = []
        self.run_row = run_row
        self.status_updates: list[dict] = []
        self.replaced_artifacts: list[dict] = []

    async def update_step(self, step_id, **payload):
        self.updated_steps.append({"step_id": step_id, **payload})
        return {"id": step_id, **payload}

    async def get_run(self, run_id, tenant_id=None):
        return self.run_row

    async def update_run_status(self, run_id, status, **payload):
        if self.run_row is None:
            return None
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

    async def list_artifacts(self, run_id):
        return list(self.replaced_artifacts)

    async def replace_artifacts(self, run_id, artifacts):
        self.replaced_artifacts = list(artifacts)
        return self.replaced_artifacts

    async def update_artifact_review_decision(self, *, run_id, artifact_id, tenant_id, decision, reviewer_id=None, note=None):
        matching = None
        for artifact in self.replaced_artifacts:
            if artifact.get("id") == artifact_id:
                matching = artifact
                break
        if matching is None:
            return None
        matching["metadata"] = {
            **(matching.get("metadata") or {}),
            "review_decision": decision,
            "reviewed_by": reviewer_id,
            "review_note": note,
        }
        return matching


class FakeToolCallRepository:
    def __init__(self):
        self.updated_calls: list[dict] = []

    async def create_tool_call(self, **payload):
        return {
            "id": "tool-call-1",
            "run_id": payload["run_id"],
            "step_id": payload["step_id"],
            "tool_name": payload["tool_name"],
            "tool_kind": payload["tool_kind"],
            "arguments": payload["arguments"],
        }

    async def update_tool_call(self, tool_call_id, **payload):
        self.updated_calls.append({"tool_call_id": tool_call_id, **payload})
        return {"id": tool_call_id, **payload}


class FakeTracer:
    def __init__(self):
        self.events: list[dict] = []
        self.steps: list[dict] = []

    async def emit_event(self, run_id, event_type, **payload):
        self.events.append({"run_id": run_id, "event_type": event_type, "payload": payload})
        return self.events[-1]

    async def create_step(self, run_id, *, kind, title, status, input_payload=None, metadata=None):
        step = {
            "id": f"step-{len(self.steps) + 1}",
            "run_id": run_id,
            "step_index": len(self.steps) + 1,
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
    def is_cancelled(self, run_id):
        return False

    def clear_task(self, run_id):
        return None

    async def close(self, run_id):
        return None


class FakeAgentRepository:
    def __init__(self, definition):
        self.definition = definition

    async def get_definition(self, agent_definition_id, tenant_id):
        return self.definition

    async def list_accessible_knowledge_bindings(self, agent_definition_id, tenant_id, user_id):
        return []


class FakePlanner:
    async def plan(self, *args, **kwargs):
        runtime_context = kwargs["runtime_context"]
        assert "compressed_context" in runtime_context
        assert "prompt_context" in runtime_context
        return PlannerResult(
            action=PlannerAction(
                type="final_answer",
                title="Return answer",
                content="Return the answer from compressed context.",
            ),
            reasoning="Compressed context is available.",
            iteration=kwargs["iteration"],
        )


@pytest.mark.asyncio
async def test_orchestrator_promotes_tool_result_artifacts_into_final_run_result():
    tool_result = {
        "structured_content": {
            "citations": [
                {
                    "title": "Runtime Plan",
                    "url": "https://example.com/runtime-plan",
                    "snippet": "Use structured artifacts.",
                }
            ],
            "table": {
                "columns": ["name", "status"],
                "rows": [{"name": "catalog", "status": "ready"}],
            },
        },
        "text": "Found the matching docs.",
    }
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor(tool_result),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=FakeTracer(),
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )
    runtime_context = {"step_history": [], "tool_failures": 0}
    run = _build_run()

    tool_observation = await orchestrator._execute_tool_action(
        definition=_build_definition(),
        run=run,
        runtime_context=runtime_context,
        planner_result=PlannerResult(
            action=PlannerAction(
                type="tool_call",
                title="Search docs",
                tool_name="search_docs",
                tool_arguments={"query": "runtime"},
            ),
            reasoning="Need MCP docs before summarizing.",
            iteration=1,
        ),
        runtime_policy=RuntimePolicy(),
    )

    assert tool_observation["status"] == "completed"
    assert runtime_context["promoted_artifacts"][0]["artifact_type"] == "citations"
    assert runtime_context["promoted_artifacts"][1]["artifact_type"] == "table"

    final_result = await orchestrator._execute_final_answer(
        definition=_build_definition(),
        run=run,
        runtime_context=runtime_context,
        skill_context=None,
        planner_result=PlannerResult(
            action=PlannerAction(
                type="final_answer",
                title="Return answer",
                content="Summarize the findings.",
            ),
            reasoning="Enough evidence gathered.",
            iteration=2,
        ),
        synthesis_resolution={"candidates": [{}]},
    )

    artifact_types = [artifact["artifact_type"] for artifact in final_result["artifacts"]]
    assert artifact_types[0] == "answer"
    assert "citations" in artifact_types
    assert "table" in artifact_types
    assert any(artifact["name"] == "search_docs - Citations" for artifact in final_result["artifacts"])


@pytest.mark.asyncio
async def test_orchestrator_emits_tool_policy_approval_events():
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({"text": "ok"}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    observation = await orchestrator._execute_tool_action(
        definition=_build_definition(),
        run=_build_run(),
        runtime_context={"step_history": [], "tool_failures": 0},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="tool_call",
                title="Search docs",
                tool_name="search_docs",
                tool_arguments={"query": "runtime", "api_key": "secret-value"},
            ),
            reasoning="Need docs.",
            iteration=1,
        ),
        runtime_policy=RuntimePolicy(["search_docs"]),
    )

    assert observation["status"] == "completed"
    event_types = [event["event_type"] for event in tracer.events]
    assert "policy.requested" in event_types
    assert "policy.approved" in event_types
    requested = next(event for event in tracer.events if event["event_type"] == "policy.requested")
    assert requested["payload"]["decision"] == "approved"
    assert requested["payload"]["policy"]["runtime_policy_allows"] is True


@pytest.mark.asyncio
async def test_orchestrator_denies_tool_before_tool_call_when_policy_blocks_it():
    tracer = FakeTracer()
    tool_call_repository = FakeToolCallRepository()
    run_repository = FakeRunRepository()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({"text": "should not run"}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=tool_call_repository,
        state_store=FakeStateStore(),
    )

    observation = await orchestrator._execute_tool_action(
        definition=_build_definition(),
        run=_build_run(),
        runtime_context={"step_history": [], "tool_failures": 0},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="tool_call",
                title="Search docs",
                tool_name="search_docs",
                tool_arguments={"query": "runtime"},
            ),
            reasoning="Need docs.",
            iteration=1,
        ),
        runtime_policy=RuntimePolicy(["calculator"]),
    )

    assert observation["status"] == "failed"
    assert "not allowed" in observation["error"]
    assert tool_call_repository.updated_calls == []
    assert run_repository.updated_steps[-1]["status"] == "failed"
    assert run_repository.updated_steps[-1]["output_payload"]["tool_result"]["failure_category"] == "policy_denied"
    assert run_repository.updated_steps[-1]["output_payload"]["recovery"]["primary_code"] == "tool_policy_denied"
    denied = next(event for event in tracer.events if event["event_type"] == "policy.denied")
    assert denied["payload"]["policy"]["runtime_policy_allows"] is False
    assert denied["payload"]["recovery_actions"]


@pytest.mark.asyncio
async def test_orchestrator_blocks_managed_subagent_tool_call_when_tool_budget_is_exhausted():
    tracer = FakeTracer()
    tool_call_repository = FakeToolCallRepository()
    run_repository = FakeRunRepository()
    executor = FakeExecutor({"text": "should not run"})
    executor.registry = ToolBudgetRegistry()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=executor,
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=tool_call_repository,
        state_store=FakeStateStore(),
    )
    target = SubagentTarget(
        slug="worker",
        name="Worker",
        subagent_definition_id="subagent-worker",
        tool_allowlist=["run_tests"],
        budget_policy={"max_tool_calls": 1},
    )

    observation = await orchestrator._execute_tool_action(
        definition=_build_definition(),
        run=_build_run(),
        runtime_context={
            "step_history": [{"tool_name": "workspace_read_file", "status": "completed"}],
            "tool_failures": 0,
        },
        planner_result=PlannerResult(
            action=PlannerAction(
                type="tool_call",
                title="Run tests",
                tool_name="run_tests",
                tool_arguments={"command": "pytest"},
            ),
            reasoning="Need verification.",
            iteration=2,
        ),
        runtime_policy=RuntimePolicy(["run_tests"]),
        managed_subagent=target,
    )

    assert observation["status"] == "failed"
    assert run_repository.updated_steps[-1]["output_payload"]["tool_budget_gate"]["blockers"][0]["code"] == "tool_budget_exceeded"
    assert tool_call_repository.updated_calls == []
    assert run_repository.updated_steps[-1]["output_payload"]["tool_result"]["failure_category"] == "tool_budget_exceeded"
    assert run_repository.updated_steps[-1]["output_payload"]["recovery"]["primary_code"] == "tool_budget_exceeded"
    denied = next(event for event in tracer.events if event["event_type"] == "policy.denied")
    assert denied["payload"]["policy_type"] == "managed_subagent_tool_budget"


@pytest.mark.asyncio
async def test_orchestrator_records_structured_tool_failure_result_on_execution_error():
    tracer = FakeTracer()
    tool_call_repository = FakeToolCallRepository()
    run_repository = FakeRunRepository()

    class RaisingExecutor(FakeExecutor):
        async def execute_tool(self, planner_result, tool_context=None, policy=None):
            raise RuntimeError("sandbox unreachable")

    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=RaisingExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=tool_call_repository,
        state_store=FakeStateStore(),
    )

    observation = await orchestrator._execute_tool_action(
        definition=_build_definition(),
        run=_build_run(),
        runtime_context={"step_history": [], "tool_failures": 0},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="tool_call",
                title="Search docs",
                tool_name="search_docs",
                tool_arguments={"query": "runtime"},
            ),
            reasoning="Need docs.",
            iteration=1,
        ),
        runtime_policy=RuntimePolicy(["search_docs"]),
    )

    assert observation["status"] == "failed"
    assert tool_call_repository.updated_calls[-1]["result"]["failure_category"] == "execution_error"
    assert tool_call_repository.updated_calls[-1]["result"]["recovery"]["primary_code"] == "tool_execution_failed"
    failed_event = next(event for event in tracer.events if event["event_type"] == "tool.failed")
    assert failed_event["payload"]["result"]["failure_category"] == "execution_error"
    assert failed_event["payload"]["recovery"]["primary_code"] == "tool_execution_failed"


@pytest.mark.asyncio
async def test_orchestrator_marks_failed_subagent_step_failed_with_recovery_strategy():
    target = SubagentTarget(
        slug="tester",
        name="Tester",
        agent_definition_id="agent-tester",
    )
    delegation = SubagentDelegationResult(
        child_run_id="child-run-1",
        status="failed",
        target=target,
        summary="Tester failed.",
        final_output_text="Tests could not run.",
        metadata={"error_message": "sandbox unavailable"},
    )
    tracer = FakeTracer()
    run_repository = FakeRunRepository()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=None,
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
        subagent_handoff=DummyHandoff(delegation),
    )

    observation, delegated_result = await orchestrator._execute_delegate_action(
        run=_build_run(),
        runtime_context={"step_history": [{"tool_name": "git_diff"}]},
        planner_result=PlannerResult(
            action=PlannerAction(
                type="delegate",
                title="Ask tester",
                delegate_target="tester",
                delegate_task="Run focused verification",
                delegate_input={"checks": ["pytest ai_runtime/tests/test_example.py"]},
            ),
            reasoning="Verification is isolated.",
            iteration=2,
        ),
        available_subagents=[target],
        available_tools=[],
    )

    assert delegated_result is None
    assert observation["status"] == "failed"
    assert observation["result"]["failure_strategy"]["strategy"] == "retry_or_fallback"
    assert run_repository.updated_steps[-1]["status"] == "failed"
    assert run_repository.updated_steps[-1]["output_payload"]["failure_strategy"]["retry_allowed"] is True
    failed_event = next(event for event in tracer.events if event["event_type"] == "subagent.failed")
    assert failed_event["payload"]["failure_strategy"]["strategy"] == "retry_or_fallback"


@pytest.mark.asyncio
async def test_orchestrator_persists_partial_artifacts_and_terminal_payload_when_run_fails():
    run_row = _build_run().model_dump(mode="json")
    definition_row = _build_definition().model_dump(mode="json")
    run_repository = FakeRunRepository(run_row=run_row)
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=FakeAgentRepository(definition_row),
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    async def fake_execute_run(definition, run):
        run_repository.run_row = {
            **run_repository.run_row,
            "plan": {
                "action": {"type": "final_answer", "title": "Return answer"},
                "reasoning": "Enough evidence gathered to summarize.",
            },
            "context": {
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
                ]
            },
        }
        raise RuntimeError("Synthesis failed")

    orchestrator._execute_run = fake_execute_run

    result = await orchestrator.start_run("run-parent")

    assert result.status == "failed"
    assert run_repository.status_updates[-1]["status"] == "failed"
    assert run_repository.status_updates[-1]["plan"]["action"]["title"] == "Return answer"
    assert run_repository.replaced_artifacts[0]["artifact_type"] == "citations"

    terminal_event = tracer.events[-1]
    assert terminal_event["event_type"] == "run.failed"
    assert terminal_event["payload"]["error"] == "Synthesis failed"
    assert terminal_event["payload"]["artifacts"][0]["artifact_type"] == "citations"


@pytest.mark.asyncio
async def test_orchestrator_redacts_completed_run_surface_before_persistence_and_events():
    run_row = _build_run().model_dump(mode="json")
    definition_row = _build_definition().model_dump(mode="json")
    run_repository = FakeRunRepository(run_row=run_row)
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=FakeAgentRepository(definition_row),
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    async def fake_execute_run(definition, run):
        return {
            "status": "completed",
            "plan": {},
            "context": {"env": {"OPENAI_API_KEY": "sk-1234567890abcdef"}},
            "final_output": "token=super-secret-token-value",
            "final_output_text": "Bearer abcdefghijklmnop",
            "final_output_json": {"authorization": "Bearer secret-token"},
            "artifacts": [
                {
                    "artifact_type": "answer",
                    "name": "Answer",
                    "payload": {"text": "api_key=sk-1234567890abcdef"},
                }
            ],
        }

    orchestrator._execute_run = fake_execute_run

    result = await orchestrator.start_run("run-parent")

    serialized_updates = str(run_repository.status_updates)
    serialized_events = str(tracer.events)
    serialized_artifacts = str(run_repository.replaced_artifacts)
    assert result.status == "completed"
    assert "sk-1234567890abcdef" not in serialized_updates
    assert "super-secret-token-value" not in serialized_updates
    assert "abcdefghijklmnop" not in serialized_events
    assert "secret-token" not in serialized_events
    assert "sk-1234567890abcdef" not in serialized_artifacts
    assert MASK in serialized_updates
    assert MASK in serialized_events
    assert MASK in serialized_artifacts


@pytest.mark.asyncio
async def test_orchestrator_builds_and_uses_compressed_context_in_main_chain():
    run_repository = FakeRunRepository(
        {
            "id": "run-parent",
            "agent_definition_id": "agent-parent",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": "running",
            "input": {"message": "Summarize the long discussion."},
            "plan": {},
            "context": {
                "conversation": [{"role": "user", "content": f"message {idx}"} for idx in range(14)],
                "step_history": [
                    {
                        "step_index": idx + 1,
                        "title": f"step {idx}",
                        "kind": "tool",
                        "status": "completed",
                        "tool_name": "knowledge_search",
                        "result": {"text": f"result {idx}"},
                    }
                    for idx in range(10)
                ],
            },
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=FakePlanner(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=FakeLLMService(),
        tracer=tracer,
        agent_repository=FakeAgentRepository(_build_definition().model_dump(mode="json")),
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    result = await orchestrator.start_run("run-parent")

    assert result.status == "completed"
    assert result.context["context_compression"]["applied"] is True
    assert result.context["prompt_context"]["mode"] == "compressed"
    assert result.context["prompt_context"]["compressed_context"]["objective"] == "Summarize the long discussion."
    assert tracer.events[-1]["event_type"] == "run.completed"
    assert any(event["event_type"] == "context.compression.updated" for event in tracer.events)


@pytest.mark.asyncio
async def test_execute_final_answer_uses_compressed_prompt_context():
    summarizer = CapturingSummarizer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=summarizer,
        llm_service=None,
        tracer=FakeTracer(),
        agent_repository=None,
        run_repository=FakeRunRepository(),
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )
    runtime_context = {
        "conversation": [{"role": "user", "content": f"message {idx}"} for idx in range(12)],
        "step_history": [
            {
                "step_index": idx + 1,
                "title": f"step {idx}",
                "kind": "tool",
                "status": "completed",
                "tool_name": "knowledge_search",
                "result": {"text": f"result {idx}"},
            }
            for idx in range(9)
        ],
        "tool_failures": 0,
        "intent_state": {"inferred_intent": "summarize"},
        "normalized_task_input": {"message": "Summarize the long discussion."},
    }
    run = _build_run()

    final_result = await orchestrator._execute_final_answer(
        definition=_build_definition(),
        run=run,
        runtime_context=runtime_context,
        skill_context=None,
        planner_result=PlannerResult(
            action=PlannerAction(
                type="final_answer",
                title="Return answer",
                content="Summarize the findings.",
            ),
            reasoning="Enough evidence gathered.",
            iteration=2,
        ),
        synthesis_resolution={"candidates": [{}]},
    )

    assert final_result["status"] == "completed"
    assert runtime_context["prompt_context"]["mode"] == "compressed"
    assert summarizer.calls[0]["runtime_context"]["prompt_context"]["mode"] == "compressed"


@pytest.mark.asyncio
async def test_orchestrator_uses_phase_specific_requested_models_and_default_iteration_budget():
    llm_service = FakeLLMService()
    run_repository = FakeRunRepository(
        {
            "id": "run-parent",
            "agent_definition_id": "agent-parent",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": "running",
            "input": {
                "message": "Summarize the long discussion.",
                "planning_model": "fast-model",
                "synthesis_model": "quality-model",
            },
            "plan": {},
            "context": {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )
    orchestrator = AgentOrchestrator(
        planner=FakePlanner(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=llm_service,
        tracer=FakeTracer(),
        agent_repository=FakeAgentRepository(
            _build_definition().model_copy(update={"config": {}}).model_dump(mode="json")
        ),
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    result = await orchestrator.start_run("run-parent")

    assert result.status == "completed"
    assert llm_service.resolve_calls[0]["route_scene"] == "agent_planning"
    assert llm_service.resolve_calls[0]["requested_model"] == "fast-model"
    assert llm_service.resolve_calls[1]["route_scene"] == "agent_synthesis"
    assert llm_service.resolve_calls[1]["requested_model"] == "quality-model"
    assert orchestrator._resolve_max_iterations(_build_definition().model_copy(update={"config": {}})) == 5


@pytest.mark.asyncio
async def test_orchestrator_run_waiting_user_event_includes_subagent_context_patch():
    run_repository = FakeRunRepository(
        {
            "id": "run-parent",
            "agent_definition_id": "agent-parent",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": "running",
            "input": {"message": "Review the rollout plan"},
            "plan": {},
            "context": {},
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )
    tracer = FakeTracer()
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=tracer,
        agent_repository=FakeAgentRepository(_build_definition().model_dump(mode="json")),
        run_repository=run_repository,
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    async def fake_execute_run(definition, run):
        return {
            "status": "waiting_user",
            "plan": {
                "action": {"type": "delegate", "title": "Ask review specialist"},
                "reasoning": "Need rollout confirmation.",
            },
            "final_output": "Need the migration rollout window.",
            "final_output_text": "Need the migration rollout window.",
            "final_output_json": {
                "source": "subagent_waiting_user",
                "question": "Need the migration rollout window.",
            },
            "artifacts": [],
            "context": {
                "conversation": [{"role": "user", "content": "Review the rollout plan"}],
                "pending_question": "Need the migration rollout window.",
                "pending_subagent_clarification": {
                    "child_run_id": "child-run-1",
                    "question": "Need the migration rollout window.",
                    "target": {
                        "slug": "review-specialist",
                        "name": "Review Specialist",
                    },
                    "clarification": {
                        "protocol_version": "managed-subagent.clarification.v1",
                        "state": "required",
                        "required_fields": ["migration rollout window"],
                    },
                    "waiting_user_path": [
                        {"run_id": "run-parent", "role": "parent", "status": "running"},
                        {"run_id": "child-run-1", "role": "child", "status": "waiting_user"},
                    ],
                },
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
                        }
                    },
                },
            },
        }

    orchestrator._execute_run = fake_execute_run

    result = await orchestrator.start_run("run-parent")

    assert result.status == "waiting_user"
    terminal_event = tracer.events[-1]
    assert terminal_event["event_type"] == "run.waiting_user"
    assert terminal_event["payload"]["final_output_json"]["source"] == "subagent_waiting_user"
    assert terminal_event["payload"]["context_patch"]["pending_question"] == "Need the migration rollout window."
    assert terminal_event["payload"]["context_patch"]["pending_subagent_clarification"]["child_run_id"] == "child-run-1"
    assert terminal_event["payload"]["context_patch"]["pending_subagent_clarification"]["waiting_user_path"][1]["run_id"] == "child-run-1"
    assert terminal_event["payload"]["context_patch"]["subagent_governance_ledger"]["targets"]["review-specialist"]["history"]["waiting_user_count"] == 1
    assert "conversation" not in terminal_event["payload"]["context_patch"]


def test_prepare_runtime_context_clears_stale_subagent_clarification_when_new_user_input_arrives():
    orchestrator = AgentOrchestrator(
        planner=object(),
        executor=FakeExecutor({}),
        summarizer=FakeSummarizer(),
        llm_service=None,
        tracer=FakeTracer(),
        agent_repository=FakeAgentRepository(_build_definition().model_dump(mode="json")),
        run_repository=FakeRunRepository(),
        tool_call_repository=FakeToolCallRepository(),
        state_store=FakeStateStore(),
    )

    run = AgentRun.model_validate(
        {
            "id": "run-parent",
            "agent_definition_id": "agent-parent",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": "running",
            "input": {"message": "Production only"},
            "plan": {},
            "context": {
                "conversation": [
                    {"role": "user", "content": "Review the rollout plan"},
                    {"role": "assistant", "content": "Need the migration rollout window."},
                ],
                "last_user_message": "Review the rollout plan",
                "pending_question": "Need the migration rollout window.",
                "pending_subagent_clarification": {
                    "child_run_id": "child-run-1",
                    "question": "Need the migration rollout window.",
                },
                "ask_user_guard": {"attempt": 1},
            },
            "created_at": _timestamp(),
            "updated_at": _timestamp(),
        }
    )

    runtime_context = orchestrator._prepare_runtime_context(run)

    assert runtime_context["last_user_message"] == "Production only"
    assert runtime_context["conversation"][-1] == {"role": "user", "content": "Production only"}
    assert "pending_question" not in runtime_context
    assert "pending_subagent_clarification" not in runtime_context
    assert "ask_user_guard" not in runtime_context
