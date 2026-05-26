"""Agent graph builder (P6).

Compiles a single-node StateGraph that delegates the agent execution
loop to the existing orchestrator. See :mod:`.nodes` for the rationale.

Future phases will expand this into a multi-node topology:

    bootstrap -> preprocess_intent -> iterate_guard -> plan
    plan -> {execute_tool, execute_delegate, synthesize_final, ask_user}
    execute_tool -> iterate_guard
    execute_delegate -> iterate_guard
    synthesize_final -> terminal_completed
    ask_user -> END (via interrupt)
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import execute_run_node
from .state import AgentState


def build_agent_graph() -> Any:
    """Compile and return the agent graph."""
    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("execute_run", execute_run_node)
    builder.add_edge(START, "execute_run")
    builder.add_edge("execute_run", END)

    return builder.compile()


__all__ = ["build_agent_graph"]
