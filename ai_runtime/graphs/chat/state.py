"""LangGraph state schema for the chat graph (P5).

The chat graph replaces the bespoke ``ChatRuntimeService.stream_chat`` loop
with a ``StateGraph`` whose nodes mirror the original phases (parse,
resolve_route, retrieve, build_messages, call_model, finalize). The state
is intentionally flat so it can be checkpointed by AsyncPostgresSaver
without custom serializers.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover - py<3.8 fallback
    from typing_extensions import TypedDict


class ChatState(TypedDict, total=False):
    # Identity
    session_id: str
    message_id: str
    user_id: Optional[str]
    tenant_id: Optional[str]

    # Inputs
    user_message: str
    content_parts: List[Dict[str, Any]]
    history: List[Dict[str, Any]]
    config: Dict[str, Any]
    upload_bundle_ids: List[str]

    # Resolved at graph entry
    route_scene: str
    governance_resolution: Dict[str, Any]
    rag_context: Optional[str]
    citations: List[Dict[str, Any]]
    knowledge_base_name: Optional[str]
    upload_context: Optional[Dict[str, Any]]
    request_user_parts: List[Dict[str, Any]]
    unified_messages: List[Any]
    request_profile: Optional[Dict[str, Any]]
    base_completion_metadata: Dict[str, str]

    # Output (accumulated across stream)
    response_text: str
    usage: Dict[str, Any]
    fallback_used: bool
    fallback_reason: Optional[str]
    error: Optional[str]

    # Streaming buffer — populated by call_model node, consumed by the
    # streaming adapter in ai_runtime/streaming/. Each entry is a
    # pre-shaped chat chunk dict ready for SSE/gRPC emission.
    pending_chunks: List[Dict[str, Any]]


__all__ = ["ChatState"]
