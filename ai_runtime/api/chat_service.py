"""HTTP/gRPC adapter that routes chat requests through the LangGraph chat graph.

After P8.2, the legacy ``ChatRuntimeService`` is gone — request parsing,
RAG retrieval, governance routing, message building, and streaming all
flow through ``ai_runtime.graphs.chat`` and its ``helpers`` module.
History is kept in a process-local dict on this adapter so the dev-only
``GET /api/v1/chat/history/{id}`` endpoint behaves identically.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict

from ai_runtime.graphs.chat import build_chat_graph, helpers
from ai_runtime.streaming import graph_to_chat_chunks


class ChatServiceImpl:
    """Adapter that routes chat through the LangGraph chat graph."""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._graph = build_chat_graph()

    async def stream_chat(self, request) -> AsyncIterator[Dict[str, Any]]:
        request_context = helpers.parse_request(request, sessions=self.sessions)
        session_id = request_context["session_id"]
        history = request_context.get("history") or []

        # Seed the session cache so the no-hit / completion nodes' final
        # state.history flows back to GET /history.
        self.sessions[session_id] = {"history": list(history), "metadata": {}}

        state: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": request_context.get("user_id"),
            "tenant_id": request_context.get("tenant_id"),
            "user_message": request_context["user_message"],
            "content_parts": request_context.get("content_parts") or [],
            "history": history,
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
                thread_id=session_id,
                on_complete=lambda final_state: self._cache_history(
                    session_id, final_state.get("history") or []
                ),
            ):
                yield chunk
        except Exception as exc:
            yield helpers.build_error_response(session_id, str(exc))

    def _cache_history(self, session_id: str, history: list) -> None:
        session = self.sessions.setdefault(session_id, {"history": [], "metadata": {}})
        session["history"] = list(history)

    async def get_chat_history(self, request):
        session_id = helpers.get_field(request, "session_id")
        session = self.sessions.get(session_id, {"history": []})
        history = session.get("history", [])

        messages = []
        for index, msg in enumerate(history):
            content = msg.get("content", "")
            content_parts = msg.get("content_parts")
            if isinstance(content, list):
                content_parts = content
            messages.append(
                {
                    "id": f"msg_{index}",
                    "role": msg.get("role", ""),
                    "content": (
                        content
                        if isinstance(content, str)
                        else "".join(
                            str(part.get("text") or "")
                            for part in (content_parts or [])
                            if isinstance(part, dict) and str(part.get("type") or "").lower() == "text"
                        )
                    ),
                    "content_parts": content_parts or [],
                    "timestamp": 0,
                    "token_usage": {},
                }
            )

        return {"messages": messages, "total": len(messages)}
