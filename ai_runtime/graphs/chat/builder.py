"""Chat graph builder.

Compiles a StateGraph[ChatState] that mirrors the legacy
``ChatRuntimeService.stream_chat`` flow:

    START -> parse -> resolve_route -> retrieve -> (no_hit | build_messages)
    build_messages -> call_model -> END
    no_hit -> END

Streaming is handled by the adapter in :mod:`ai_runtime.streaming`, which
consumes the ``pending_chunks`` buffer that nodes populate.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import (
    build_messages_node,
    call_model_node,
    no_hit_node,
    parse_node,
    resolve_route_node,
    retrieve_node,
    route_after_retrieve,
)
from .state import ChatState


def build_chat_graph() -> Any:
    """Compile and return the chat graph."""
    builder: StateGraph = StateGraph(ChatState)

    builder.add_node("parse", parse_node)
    builder.add_node("resolve_route", resolve_route_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("no_hit", no_hit_node)
    builder.add_node("build_messages", build_messages_node)
    builder.add_node("call_model", call_model_node)

    builder.add_edge(START, "parse")
    builder.add_edge("parse", "resolve_route")
    builder.add_edge("resolve_route", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"no_hit": "no_hit", "build_messages": "build_messages"},
    )
    builder.add_edge("build_messages", "call_model")
    builder.add_edge("call_model", END)
    builder.add_edge("no_hit", END)

    return builder.compile()


__all__ = ["build_chat_graph"]
