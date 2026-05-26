"""Smoke tests for the multi-node agent graph (P6) and the subagent
graph (P7).

These tests exercise the graph topology and the RunContext side-channel
contract directly (not through orchestrator integration), so they fail
fast if the graph wiring drifts."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_runtime.graphs.agent import build_agent_graph, registry
from ai_runtime.graphs.agent.context import RunContext
from ai_runtime.graphs.subagent import build_subagent_graph


def _make_ctx(*, orchestrator) -> RunContext:
    """Build a RunContext sufficient for the graph nodes to run."""
    return RunContext(
        orchestrator=orchestrator,
        definition=SimpleNamespace(),
        synthesis_definition=SimpleNamespace(),
        planning_definition=SimpleNamespace(),
        output_skill_context=None,
        run=SimpleNamespace(id="run-1", tenant_id=None, user_id=None),
        managed_subagent=None,
        runtime_context={},
        available_tools=[],
        available_subagents=[],
        runtime_policy=None,
        mounted_knowledge_base_ids=[],
        planning_resolution={},
        synthesis_resolution={},
    )


def test_agent_graph_topology():
    g = build_agent_graph()
    assert {
        "iterate_guard",
        "plan",
        "execute_tool",
        "execute_delegate",
        "synthesize_final",
        "ask_user",
    }.issubset(g.nodes.keys())


def test_subagent_graph_returns_same_topology():
    parent = build_agent_graph()
    sub = build_subagent_graph()
    assert set(parent.nodes.keys()) == set(sub.nodes.keys())


@pytest.mark.asyncio
async def test_agent_graph_drives_final_answer_path():
    """Plan returns a final_answer action -> synthesize_final -> END."""
    planner_action = SimpleNamespace(type="final_answer")
    planner_result = SimpleNamespace(
        action=planner_action,
        model_dump=lambda mode="json": {"action": {"type": "final_answer"}},
    )

    orch = MagicMock()
    orch._raise_if_cancelled = MagicMock(return_value=None)
    orch._collect_pending_subagent_invocations = AsyncMock(return_value=None)
    orch._persist_run_state = AsyncMock(return_value=None)
    orch._plan_next_action = AsyncMock(return_value=planner_result)
    orch.tracer = MagicMock()
    orch.tracer.emit_event = AsyncMock(return_value=None)
    orch._execute_final_answer = AsyncMock(return_value={"status": "completed"})

    ctx = _make_ctx(orchestrator=orch)
    registry().put("run-1", ctx)
    try:
        graph = build_agent_graph()
        final = await graph.ainvoke({"run_id": "run-1", "iteration": 0, "max_iterations": 5})
        assert final["terminal_result"] == {"status": "completed"}
        orch._execute_final_answer.assert_awaited_once()
        orch._execute_tool_action = AsyncMock()  # never called on this path
    finally:
        registry().discard("run-1")


@pytest.mark.asyncio
async def test_agent_graph_drives_tool_then_final_answer():
    """First plan returns 'tool', second returns 'final_answer' — graph
    loops through execute_tool back to iterate_guard."""
    plans = iter([
        SimpleNamespace(
            action=SimpleNamespace(type="tool"),
            model_dump=lambda mode="json": {"action": {"type": "tool"}},
        ),
        SimpleNamespace(
            action=SimpleNamespace(type="final_answer"),
            model_dump=lambda mode="json": {"action": {"type": "final_answer"}},
        ),
    ])

    orch = MagicMock()
    orch._raise_if_cancelled = MagicMock(return_value=None)
    orch._collect_pending_subagent_invocations = AsyncMock(return_value=None)
    orch._persist_run_state = AsyncMock(return_value=None)
    orch._plan_next_action = AsyncMock(side_effect=lambda **_: next(plans))
    orch.tracer = MagicMock()
    orch.tracer.emit_event = AsyncMock(return_value=None)
    orch._execute_tool_action = AsyncMock(return_value={"observation": "tool-out"})
    orch._execute_final_answer = AsyncMock(return_value={"status": "completed"})

    ctx = _make_ctx(orchestrator=orch)
    registry().put("run-1", ctx)
    try:
        graph = build_agent_graph()
        final = await graph.ainvoke({"run_id": "run-1", "iteration": 0, "max_iterations": 5})
        assert final["terminal_result"] == {"status": "completed"}
        assert orch._execute_tool_action.await_count == 1
        assert orch._execute_final_answer.await_count == 1
        assert ctx.runtime_context["step_history"] == [{"observation": "tool-out"}]
    finally:
        registry().discard("run-1")


@pytest.mark.asyncio
async def test_agent_graph_short_circuits_on_pending_subagent_invocation():
    """If iterate_guard observes a pending subagent terminal result the
    graph routes straight to END without planning."""
    pending = {"status": "waiting_subagent"}

    orch = MagicMock()
    orch._raise_if_cancelled = MagicMock(return_value=None)
    orch._collect_pending_subagent_invocations = AsyncMock(return_value=pending)
    orch._persist_run_state = AsyncMock(return_value=None)
    orch._plan_next_action = AsyncMock()  # must NOT be called

    ctx = _make_ctx(orchestrator=orch)
    registry().put("run-1", ctx)
    try:
        graph = build_agent_graph()
        final = await graph.ainvoke({"run_id": "run-1", "iteration": 0, "max_iterations": 3})
        assert final["terminal_result"] is pending
        orch._plan_next_action.assert_not_awaited()
    finally:
        registry().discard("run-1")


@pytest.mark.asyncio
async def test_agent_graph_max_iterations_raises():
    """Looping past max_iterations raises so start_run can mark the run failed."""
    plans = iter([
        SimpleNamespace(
            action=SimpleNamespace(type="tool"),
            model_dump=lambda mode="json": {"action": {"type": "tool"}},
        )
    ] * 5)

    orch = MagicMock()
    orch._raise_if_cancelled = MagicMock(return_value=None)
    orch._collect_pending_subagent_invocations = AsyncMock(return_value=None)
    orch._persist_run_state = AsyncMock(return_value=None)
    orch._plan_next_action = AsyncMock(side_effect=lambda **_: next(plans))
    orch.tracer = MagicMock()
    orch.tracer.emit_event = AsyncMock(return_value=None)
    orch._execute_tool_action = AsyncMock(return_value={"observation": "tool"})

    ctx = _make_ctx(orchestrator=orch)
    registry().put("run-1", ctx)
    try:
        graph = build_agent_graph()
        with pytest.raises(Exception) as exc_info:
            await graph.ainvoke({"run_id": "run-1", "iteration": 0, "max_iterations": 1})
        assert "exceeded maximum iterations" in str(exc_info.value)
    finally:
        registry().discard("run-1")
