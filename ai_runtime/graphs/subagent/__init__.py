"""Subagent graph (P6 / P7).

Subagents reuse the same agent graph topology — they are independent
agent runs invoked via ``SubagentHandoff`` with their own thread_id.
The factory ``build_subagent_graph()`` exists so that future phases can
specialize the topology per subagent target (different bootstrap, tool
filter, etc.) without disturbing the parent agent graph.
"""
from __future__ import annotations

from ai_runtime.graphs.agent import build_agent_graph as build_subagent_graph

__all__ = ["build_subagent_graph"]
