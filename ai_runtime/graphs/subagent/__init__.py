"""Subagent graph (P7).

Subagents are independent agent runs invoked via
:class:`SubagentHandoff`. Each subagent run gets its own ``agent_runs``
row with ``metadata.managed_subagent`` populated, and is executed by the
same :func:`AgentRuntime.start_run` entry point as parent runs. This
means subagent runs already flow through the multi-node agent graph
(see :mod:`ai_runtime.graphs.agent`) — the orchestrator's
``_resolve_managed_subagent`` + ``_apply_managed_subagent_definition``
hooks at the start of ``_execute_run`` apply the per-target tool
allowlist, knowledge-base scope, MCP filters, skill scope, and
augmented system prompt, so the same graph topology produces
subagent-scoped behavior automatically.

The :func:`build_subagent_graph` factory exists so that:

  1. Future phases can return a *different* compiled graph for specific
     subagent targets without touching parent-run wiring (``target`` is
     the per-target hook). For example, a "review_only" subagent might
     skip ``execute_delegate`` entirely.
  2. Call sites have an explicit, intent-revealing entry point rather
     than reusing ``build_agent_graph`` and obscuring the fact that
     they are constructing a subagent loop.

For the common path (``target`` is None or a generic capability),
this returns the same compiled graph as :func:`build_agent_graph` —
specialization happens via ``managed_subagent`` resolution inside the
orchestrator nodes, not via graph topology.
"""
from __future__ import annotations

from typing import Any

from ai_runtime.graphs.agent import build_agent_graph


def build_subagent_graph(target: Any | None = None) -> Any:
    """Compile a subagent-scoped agent graph.

    Currently delegates to :func:`build_agent_graph` because the
    ``managed_subagent`` resolution inside the orchestrator's bootstrap
    + node helpers already enforces all per-target scoping. The
    ``target`` parameter is reserved for future per-capability topology
    overrides (e.g. tool-free review subagents, single-shot lookups
    that skip the iteration loop).
    """
    del target  # currently unused; reserved for future specialization
    return build_agent_graph()


__all__ = ["build_subagent_graph"]
