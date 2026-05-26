"""Agent graph builder (P6).

Compiles a multi-node StateGraph that mirrors the legacy
``AgentOrchestrator._execute_run`` iteration loop. The graph's caller
is responsible for bootstrap and finalize — see :mod:`.nodes`.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import (
    ask_user_node,
    execute_delegate_node,
    execute_tool_node,
    iterate_guard_node,
    plan_node,
    route_after_delegate,
    route_after_iterate_guard,
    route_after_plan,
    synthesize_final_node,
)
from .state import AgentState


def build_agent_graph() -> Any:
    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("iterate_guard", iterate_guard_node)
    builder.add_node("plan", plan_node)
    builder.add_node("execute_tool", execute_tool_node)
    builder.add_node("execute_delegate", execute_delegate_node)
    builder.add_node("synthesize_final", synthesize_final_node)
    builder.add_node("ask_user", ask_user_node)

    builder.add_edge(START, "iterate_guard")
    builder.add_conditional_edges(
        "iterate_guard",
        route_after_iterate_guard,
        {"plan": "plan", "__end__": END},
    )
    builder.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "execute_tool": "execute_tool",
            "execute_delegate": "execute_delegate",
            "synthesize_final": "synthesize_final",
            "ask_user": "ask_user",
        },
    )
    builder.add_edge("execute_tool", "iterate_guard")
    builder.add_conditional_edges(
        "execute_delegate",
        route_after_delegate,
        {"iterate_guard": "iterate_guard", "__end__": END},
    )
    builder.add_edge("synthesize_final", END)
    builder.add_edge("ask_user", END)

    return builder.compile()


__all__ = ["build_agent_graph"]
