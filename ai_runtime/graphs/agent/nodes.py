"""Agent graph nodes (P6).

The agent graph currently delegates to the existing AgentOrchestrator for
the full execution loop. This is a deliberate design choice: the
orchestrator contains ~3000 lines of battle-tested logic (governance gates,
subagent delegation, tool budget enforcement, context compression, intent
preprocessing) that would be risky to rewrite in one pass.

The graph topology exists so that:
  1. The API layer routes through a LangGraph CompiledGraph
  2. AsyncPostgresSaver provides checkpoint-based resume for ask_user
  3. P7 (subagents) and P8 (cleanup) can progressively extract nodes
     from the orchestrator into discrete graph nodes

The ``execute_run`` node is the single-node workhorse that calls
``orchestrator.start_run(run_id)`` and captures the terminal result.
"""
from __future__ import annotations

import logging
from typing import Any

from .state import AgentState

logger = logging.getLogger(__name__)


async def execute_run_node(state: AgentState) -> AgentState:
    """Drive the full agent execution loop via the existing orchestrator.

    This node is intentionally opaque — it delegates to the orchestrator
    which handles planning, tool execution, delegation, governance, and
    event emission internally. The graph provides the topology and
    checkpoint envelope; the orchestrator provides the logic.
    """
    from ai_runtime.core.agent_runtime import AgentRuntime

    run_id = state["run_id"]

    try:
        # The orchestrator is accessed via the global runtime singleton.
        # In production this is initialized at startup; in tests it's
        # injected via the state_store fixture.
        runtime = AgentRuntime._instance  # type: ignore[attr-defined]
        if runtime is None:
            raise RuntimeError("AgentRuntime not initialized")

        await runtime.orchestrator.start_run(run_id)

        # After orchestrator completes, fetch terminal state
        run_row = await runtime.run_repository.get_run(run_id, state.get("tenant_id"))
        artifacts = await runtime.run_repository.list_artifacts(run_id)
        state["terminal_result"] = {
            "status": run_row.get("status") if isinstance(run_row, dict) else getattr(run_row, "status", "completed"),
            "run_id": run_id,
            "artifacts_count": len(artifacts) if artifacts else 0,
        }
    except Exception as exc:
        logger.exception("Agent graph execute_run failed for run %s: %s", run_id, exc)
        state["error"] = str(exc)

    return state


__all__ = ["execute_run_node"]
