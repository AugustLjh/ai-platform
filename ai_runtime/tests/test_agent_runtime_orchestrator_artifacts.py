from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_runtime.core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from ai_runtime.core.agent_runtime.orchestrator import AgentOrchestrator
from ai_runtime.core.agent_runtime.policy import RuntimePolicy


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
