"""Per-run side channel for the agent graph.

LangGraph state must be JSON-serializable for checkpointing. The
orchestrator's ``runtime_context`` (with pydantic models, async locks,
and live tool registries) is not. Rather than fight that, the graph
nodes share a process-local registry keyed by run_id and only put
primitive control-flow values in the LangGraph state.

Lifetime: a ``RunContext`` is created by ``_execute_run`` before it
invokes the graph and discarded after the graph returns. Crash recovery
inside the loop relies on the orchestrator's existing repository writes,
not on this registry.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunContext:
    runtime: Any
    definition: Any
    synthesis_definition: Any
    planning_definition: Any
    output_skill_context: Any
    run: Any
    managed_subagent: Any

    runtime_context: Dict[str, Any]
    available_tools: List[Dict[str, Any]]
    available_subagents: List[Any]
    runtime_policy: Any
    mounted_knowledge_base_ids: List[str]

    planning_resolution: Dict[str, Any]
    synthesis_resolution: Dict[str, Any]

    last_planner_result: Any = None


class RunContextRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, RunContext] = {}

    def put(self, run_id: str, ctx: RunContext) -> None:
        with self._lock:
            self._data[run_id] = ctx

    def get(self, run_id: str) -> Optional[RunContext]:
        with self._lock:
            return self._data.get(run_id)

    def require(self, run_id: str) -> RunContext:
        ctx = self.get(run_id)
        if ctx is None:
            raise RuntimeError(
                f"RunContext missing for run {run_id} — graph invoked without bootstrap"
            )
        return ctx

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._data.pop(run_id, None)


_REGISTRY = RunContextRegistry()


def registry() -> RunContextRegistry:
    return _REGISTRY


__all__ = ["RunContext", "RunContextRegistry", "registry"]
