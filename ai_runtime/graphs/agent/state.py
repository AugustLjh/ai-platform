"""LangGraph state for the agent graph (P6).

The graph models the iteration loop inside
:meth:`AgentOrchestrator._execute_run`. The bootstrap + preprocess_intent
phases stay in the orchestrator (they only run once per run, mutate the
runtime_context dict in place, and have no branching of interest), as
does the outer ``start_run`` envelope (run-level status updates and
``run.started``/``run.completed``/``run.failed`` emission).

What the graph contributes is the topology of the iteration loop:

    iterate_guard -> plan -> {execute_tool, execute_delegate,
                              synthesize_final, ask_user}
    execute_tool / execute_delegate -> iterate_guard
    synthesize_final / ask_user / exhausted -> END

Bulky per-run state (definition, run, runtime_context, available_tools,
…) lives in :class:`ai_runtime.graphs.agent.context.RunContext` (process-
local, keyed by run_id). The LangGraph state itself only carries
control-flow primitives so the AsyncPostgresSaver checkpoint envelope
stays small.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str

    iteration: int
    max_iterations: int
    last_action_type: Optional[str]
    last_plan: Optional[Dict[str, Any]]

    terminal_result: Optional[Dict[str, Any]]


__all__ = ["AgentState"]
