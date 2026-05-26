"""Agent graph nodes (P6).

The graph models the iteration loop of
``AgentOrchestrator._execute_run`` (lines 2630-2719 in the legacy
implementation). Each node delegates leaf compute to existing
orchestrator methods so this stays a control-flow rewrite, not a logic
rewrite.

The graph's caller is responsible for bootstrap (definition resolution,
runtime_context preparation, skill/intent setup) and finalize (terminal
status update, run-level events). See
:meth:`AgentOrchestrator._iterate_via_graph` for the wiring.
"""
from __future__ import annotations

import logging
from typing import Any

from .context import registry
from .state import AgentState

logger = logging.getLogger(__name__)


async def iterate_guard_node(state: AgentState) -> AgentState:
    """Increment iteration, check cancellation and max_iterations, drain
    pending subagent invocations. Mirrors lines 2630-2644 of
    ``_execute_run``."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    iteration = int(state.get("iteration", 0)) + 1
    state["iteration"] = iteration
    max_iter = int(state.get("max_iterations", 1))

    if iteration > max_iter:
        raise RuntimeError(
            f"Agent exceeded maximum iterations ({max_iter}) before reaching a final answer"
        )

    orch._raise_if_cancelled(ctx.run.id)
    ctx.runtime_context["execution_count"] = iteration

    pending_terminal = await orch._collect_pending_subagent_invocations(
        run=ctx.run, runtime_context=ctx.runtime_context
    )
    last_plan = state.get("last_plan")
    await orch._persist_run_state(
        ctx.run.id,
        status="running",
        runtime_context=ctx.runtime_context,
        plan=last_plan,
    )
    if pending_terminal is not None:
        state["terminal_result"] = pending_terminal
    return state


async def plan_node(state: AgentState) -> AgentState:
    """Run the planner. Mirrors lines 2646-2662."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    planner_result = await orch._plan_next_action(
        definition=ctx.planning_definition,
        run=ctx.run,
        runtime_context=ctx.runtime_context,
        available_tools=ctx.available_tools,
        available_subagents=ctx.available_subagents,
        llm_resolution=ctx.planning_resolution,
        iteration=int(state.get("iteration", 1)),
    )
    last_plan = planner_result.model_dump(mode="json")
    ctx.runtime_context["last_plan"] = last_plan
    ctx.last_planner_result = planner_result

    await orch.tracer.emit_event(
        ctx.run.id,
        "plan.created",
        iteration=int(state.get("iteration", 1)),
        plan=last_plan,
    )

    state["last_plan"] = last_plan
    state["last_action_type"] = planner_result.action.type
    return state


async def execute_tool_node(state: AgentState) -> AgentState:
    """Mirrors lines 2702-2717."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    observation = await orch._execute_tool_action(
        definition=ctx.definition,
        run=ctx.run,
        runtime_context=ctx.runtime_context,
        planner_result=ctx.last_planner_result,
        runtime_policy=ctx.runtime_policy,
        mounted_knowledge_base_ids=ctx.mounted_knowledge_base_ids,
        managed_subagent=ctx.managed_subagent,
    )
    ctx.runtime_context.setdefault("step_history", []).append(observation)
    await orch._persist_run_state(
        ctx.run.id,
        status="running",
        runtime_context=ctx.runtime_context,
        plan=state.get("last_plan"),
    )
    return state


async def execute_delegate_node(state: AgentState) -> AgentState:
    """Mirrors lines 2683-2700."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    observation, delegated_result = await orch._execute_delegate_action(
        run=ctx.run,
        runtime_context=ctx.runtime_context,
        planner_result=ctx.last_planner_result,
        available_subagents=ctx.available_subagents,
        available_tools=ctx.available_tools,
    )
    ctx.runtime_context.setdefault("step_history", []).append(observation)
    await orch._persist_run_state(
        ctx.run.id,
        status="running",
        runtime_context=ctx.runtime_context,
        plan=state.get("last_plan"),
    )
    if delegated_result is not None:
        state["terminal_result"] = delegated_result
    return state


async def synthesize_final_node(state: AgentState) -> AgentState:
    """Mirrors lines 2672-2681."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    result = await orch._execute_final_answer(
        definition=ctx.synthesis_definition,
        run=ctx.run,
        runtime_context=ctx.runtime_context,
        skill_context=ctx.output_skill_context,
        managed_subagent=ctx.managed_subagent,
        planner_result=ctx.last_planner_result,
        synthesis_resolution=ctx.synthesis_resolution,
    )
    state["terminal_result"] = result
    return state


async def ask_user_node(state: AgentState) -> AgentState:
    """Mirrors lines 2665-2670."""
    ctx = registry().require(state["run_id"])
    orch = ctx.orchestrator

    result = await orch._execute_ask_user(
        run=ctx.run,
        runtime_context=ctx.runtime_context,
        planner_result=ctx.last_planner_result,
    )
    state["terminal_result"] = result
    return state


def route_after_iterate_guard(state: AgentState) -> str:
    if state.get("terminal_result") is not None:
        return "__end__"
    return "plan"


def route_after_plan(state: AgentState) -> str:
    action = state.get("last_action_type")
    if action == "ask_user":
        return "ask_user"
    if action == "final_answer":
        return "synthesize_final"
    if action == "delegate":
        return "execute_delegate"
    return "execute_tool"


def route_after_delegate(state: AgentState) -> str:
    if state.get("terminal_result") is not None:
        return "__end__"
    return "iterate_guard"


__all__ = [
    "iterate_guard_node",
    "plan_node",
    "execute_tool_node",
    "execute_delegate_node",
    "synthesize_final_node",
    "ask_user_node",
    "route_after_iterate_guard",
    "route_after_plan",
    "route_after_delegate",
]
