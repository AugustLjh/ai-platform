"""LangGraph state for the agent graph (P6).

The state intentionally tracks the bare minimum needed by the graph
shell. The bulk of the agent execution context (conversation,
step_history, governance ledger, pending subagent invocations,
intent state, promoted artifacts) lives inside the orchestrator's
in-memory ``runtime_context`` dict and is persisted to the agent_runs
database row through the existing ``StateStore``. The LangGraph
checkpoint tables added in P0 (alembic 20260526_0016) provide the
graph-level resumability for ``ask_user`` interrupts.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    tenant_id: Optional[str]
    user_id: Optional[str]
    iteration: int
    terminal_result: Optional[Dict[str, Any]]
    error: Optional[str]
    ask_user_question: Optional[str]


__all__ = ["AgentState"]
