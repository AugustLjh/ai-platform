"""Streaming adapters that bridge LangGraph state machines to the SSE/gRPC
chunk contracts already in use by ``ai_runtime.api.http_server`` and
``ai_runtime.api.grpc_server``.

Single source of truth for the chunk shape: ``{session_id, message_id,
type, content, metadata, token_usage?}``. The HTTP layer wraps this in
``data: <json>\\n\\n`` SSE framing and the gRPC layer maps it into a
``ChatResponse`` protobuf — neither needs to know the chunk came from a
graph rather than direct LLM streaming.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Dict, Optional

from ai_runtime.core.chat.response_types import RESPONSE_TYPE_ERROR

logger = logging.getLogger(__name__)


async def graph_to_chat_chunks(
    graph: Any,
    state: Dict[str, Any],
    *,
    thread_id: Optional[str] = None,
    on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Drive a compiled chat graph and yield pre-shaped chat chunks.

    The graph nodes accumulate chunks in ``state["pending_chunks"]``. We
    stream the graph with ``astream`` so we get incremental state updates;
    after each node tick we drain the buffer. ``on_complete`` (if given)
    receives the final accumulated state once the graph terminates without
    error — used by the API layer to persist post-run history.
    """
    config: Dict[str, Any] = {}
    if thread_id is not None:
        config["configurable"] = {"thread_id": thread_id}

    drained = 0
    accumulated: Dict[str, Any] = dict(state)

    try:
        async for update in graph.astream(state, config=config):
            for _, partial in update.items():
                if not isinstance(partial, dict):
                    continue
                if "pending_chunks" in partial:
                    accumulated["pending_chunks"] = partial["pending_chunks"]
                for key, value in partial.items():
                    if key != "pending_chunks":
                        accumulated[key] = value

            buffer = accumulated.get("pending_chunks") or []
            while drained < len(buffer):
                yield buffer[drained]
                drained += 1

        if on_complete is not None:
            try:
                on_complete(accumulated)
            except Exception:
                logger.exception("on_complete callback failed")
    except Exception as exc:
        logger.exception("chat graph failed: %s", exc)
        yield {
            "session_id": state.get("session_id"),
            "message_id": state.get("message_id"),
            "type": RESPONSE_TYPE_ERROR,
            "content": "",
            "error": str(exc),
            "metadata": {},
        }


__all__ = ["graph_to_chat_chunks"]
