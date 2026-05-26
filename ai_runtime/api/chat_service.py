"""HTTP/gRPC adapter that routes chat requests through the LangGraph chat graph.

P5: ``ChatServiceImpl`` previously delegated directly to
:class:`ChatRuntimeService.stream_chat`. After the rewrite the request flows
through ``ai_runtime.graphs.chat`` and the streaming adapter
``graph_to_chat_chunks``. Inner primitives (governance routing, RAG context,
message building) still live on ``ChatRuntimeService`` while we incrementally
port them in P8.

History retrieval keeps using the existing in-memory session store on
``ChatRuntimeService`` so existing GET /api/v1/chat/history/{id} behaviour is
unchanged.
"""
from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict

from ai_runtime.core.chat import ChatRuntimeService
from ai_runtime.graphs.chat import build_chat_graph
from ai_runtime.streaming import graph_to_chat_chunks


def _use_legacy_chat() -> bool:
    """Allow opt-in to the legacy stream_chat path for parity testing."""
    return os.getenv("AI_RUNTIME_CHAT_LEGACY", "").lower() in {"1", "true", "yes"}


class ChatServiceImpl:
    """Adapter that routes chat through the LangGraph chat graph (P5)."""

    def __init__(self):
        self.chat_runtime = ChatRuntimeService()
        self.sessions = self.chat_runtime.sessions
        self._graph = build_chat_graph()

    async def stream_chat(self, request) -> AsyncIterator[Dict[str, Any]]:
        if _use_legacy_chat():
            async for chunk in self.chat_runtime.stream_chat(request):
                yield chunk
            return

        request_context = self.chat_runtime.parse_request(request)
        state: Dict[str, Any] = {
            "session_id": request_context["session_id"],
            "user_id": request_context.get("user_id"),
            "tenant_id": request_context.get("tenant_id"),
            "user_message": request_context["user_message"],
            "content_parts": request_context.get("content_parts") or [],
            "history": request_context.get("history") or [],
            "config": {
                "model": request_context.get("requested_model"),
                "use_rag": request_context.get("use_rag", False),
                "temperature": request_context.get("temperature"),
                "max_tokens": request_context.get("max_tokens"),
                "knowledge_base_id": request_context.get("knowledge_base_id"),
            },
            "upload_bundle_ids": request_context.get("upload_bundle_ids") or [],
        }

        try:
            async for chunk in graph_to_chat_chunks(
                self._graph,
                state,
                thread_id=state["session_id"],
            ):
                yield chunk
        except Exception as exc:
            yield self.chat_runtime.build_error_response(state["session_id"], str(exc))

    async def get_chat_history(self, request):
        return await self.chat_runtime.get_chat_history(request)
