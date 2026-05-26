"""LangGraph nodes for the chat graph.

Each node is a pure async function ``ChatState -> ChatState``. The actual
heavy lifting (LLM resolution, RAG retrieval, message building) delegates
to the existing :class:`ChatRuntimeService` while we incrementally port
those primitives into the new layers. This keeps the diff focused on the
graph topology and event surface; the inner primitives migrate in P8.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_runtime.core.chat.response_types import (
    RESPONSE_TYPE_COMPLETE,
    RESPONSE_TYPE_CONTENT,
    RESPONSE_TYPE_RETRIEVAL,
    RESPONSE_TYPE_ROUTE_DECISION,
)
from ai_runtime.core.llm.messages import (
    UnifiedModelRequest,
    build_model_request_profile,
    validate_message_constraints,
)
from ai_runtime.core.uploads.bundle_store import get_attachment_bundle_store

from .state import ChatState

logger = logging.getLogger(__name__)


def _service():
    """Lazy import to avoid a circular dep at module load time."""
    from ai_runtime.core.chat import ChatRuntimeService

    if not hasattr(_service, "_instance"):
        _service._instance = ChatRuntimeService()  # type: ignore[attr-defined]
    return _service._instance  # type: ignore[attr-defined]


async def parse_node(state: ChatState) -> ChatState:
    """Normalize the incoming request into ChatState fields.

    Sets ``message_id`` exactly once so it remains stable across streaming
    chunks (the legacy code rebuilt it from ``len(history)`` on every
    yield, which was brittle when history mutated mid-stream).
    """
    svc = _service()
    history = state.get("history") or []
    session_id = state.get("session_id") or ""
    state["history"] = history
    state["message_id"] = svc.build_message_id(session_id, len(history))
    state["pending_chunks"] = []
    state["response_text"] = ""
    state["usage"] = {}
    state["fallback_used"] = False
    state["fallback_reason"] = None
    state["error"] = None
    svc.cache_history(session_id, history)
    return state


async def resolve_route_node(state: ChatState) -> ChatState:
    """Resolve governance + LLM candidates and emit ROUTE_DECISION chunk."""
    svc = _service()
    config = state.get("config") or {}
    use_rag = bool(config.get("use_rag"))
    state["route_scene"] = svc._determine_route_scene(use_rag)
    # Candidates are resolved lazily in call_model once the message
    # request profile is known (depends on uploads + RAG context).
    return state


async def retrieve_node(state: ChatState) -> ChatState:
    """Optionally pull RAG context + citations and emit a RETRIEVAL chunk."""
    svc = _service()
    config = state.get("config") or {}
    use_rag = bool(config.get("use_rag"))
    if not use_rag:
        state["rag_context"] = None
        state["citations"] = []
        state["knowledge_base_name"] = None
        return state

    context, citations, kb_name = await svc.build_rag_context_and_citations(
        tenant_id=state.get("tenant_id"),
        user_id=state.get("user_id"),
        knowledge_base_id=config.get("knowledge_base_id"),
        query=state.get("user_message", ""),
        top_k=3,
    )
    state["rag_context"] = context
    state["citations"] = citations or []
    state["knowledge_base_name"] = kb_name

    if citations:
        state["pending_chunks"].append(
            {
                "session_id": state.get("session_id"),
                "message_id": state.get("message_id"),
                "type": RESPONSE_TYPE_RETRIEVAL,
                "content": "",
                "metadata": svc.build_response_metadata(
                    retrieval_status="hit",
                    use_rag=True,
                    knowledge_base_id=config.get("knowledge_base_id"),
                    knowledge_base_name=kb_name,
                    citations=citations,
                ),
            }
        )
    return state


async def build_messages_node(state: ChatState) -> ChatState:
    """Build unified messages with context + uploads and emit ROUTE_DECISION."""
    svc = _service()
    config = state.get("config") or {}
    upload_bundle_ids = state.get("upload_bundle_ids") or []
    upload_context: Optional[Dict[str, Any]] = None

    if upload_bundle_ids:
        upload_context = get_attachment_bundle_store().build_prompt_context(
            tenant_id=state.get("tenant_id"),
            user_id=state.get("user_id"),
            bundle_ids=upload_bundle_ids,
            query=state.get("user_message", ""),
        )
        state["rag_context"] = svc._build_combined_context(
            state.get("rag_context"), upload_context.get("context_text")
        )
    state["upload_context"] = upload_context

    request_user_parts = svc._build_request_user_parts(
        state.get("user_message", ""),
        state.get("content_parts") or [],
        upload_context,
    )
    state["request_user_parts"] = request_user_parts

    unified_messages = svc.build_unified_messages(
        user_message=state.get("user_message", ""),
        context=state.get("rag_context"),
        history=state.get("history") or [],
        user_parts=request_user_parts,
    )
    state["unified_messages"] = unified_messages

    request_profile = build_model_request_profile(unified_messages)
    state["request_profile"] = request_profile.model_dump()
    required_modalities = set(request_profile.input_modalities)

    governance_resolution = await svc.resolve_llm_candidates(
        tenant_id=state.get("tenant_id"),
        user_id=state.get("user_id"),
        knowledge_base_id=config.get("knowledge_base_id"),
        route_scene=state.get("route_scene", "chat"),
        requested_model=config.get("model"),
        required_modalities=required_modalities,
        request_profile=request_profile,
    )
    state["governance_resolution"] = governance_resolution

    state["base_completion_metadata"] = svc.build_response_metadata(
        retrieval_status="hit" if state.get("citations") else "not_used",
        use_rag=bool(config.get("use_rag")),
        knowledge_base_id=config.get("knowledge_base_id"),
        knowledge_base_name=state.get("knowledge_base_name"),
        citations=state.get("citations") or [],
        upload_bundle_ids=upload_bundle_ids,
        uploaded_files=(upload_context or {}).get("files", []),
        uploaded_file_directory_tree=(upload_context or {}).get("directory_tree", []),
        request_content_parts=request_user_parts,
        required_input_modalities=sorted(required_modalities),
        required_output_modalities=request_profile.output_modalities,
        model_request_profile=request_profile.model_dump(),
    )

    # ROUTE_DECISION — surface chosen primary candidate to the client.
    candidates = governance_resolution.get("candidates") or []
    if candidates:
        primary = candidates[0]
        state["pending_chunks"].append(
            {
                "session_id": state.get("session_id"),
                "message_id": state.get("message_id"),
                "type": RESPONSE_TYPE_ROUTE_DECISION,
                "content": "",
                "metadata": {
                    "route_scene": state.get("route_scene", "chat"),
                    "resolved_model_id": str(primary.get("id") or primary.get("model_id") or ""),
                    "resolved_model_name": str(primary.get("display_name") or primary.get("name") or ""),
                    "resolved_model_provider": str(primary.get("provider") or ""),
                    "fallback_candidates": str(len(candidates) - 1),
                    "config_version": str(governance_resolution.get("config_version", 1)),
                },
            }
        )

    return state


async def call_model_node(state: ChatState) -> ChatState:
    """Stream the LLM response, walking candidates on failure.

    Pre-buffers CONTENT and COMPLETE chunks into ``pending_chunks`` for the
    streaming adapter. Mirrors the legacy fallback-on-error semantics: if
    the first candidate fails *before* streaming started, we try the next;
    once streaming has started we propagate the failure.
    """
    svc = _service()
    config = state.get("config") or {}
    governance_resolution = state.get("governance_resolution") or {}
    candidates = governance_resolution.get("candidates") or []
    if not candidates:
        raise RuntimeError("No available model candidate")

    history = state.get("history") or []
    upload_context = state.get("upload_context")
    request_user_parts = state.get("request_user_parts") or []
    base_completion_metadata = state.get("base_completion_metadata") or {}
    last_error: Optional[str] = None

    for attempt_index, model_candidate in enumerate(candidates):
        fallback_used = attempt_index > 0
        full_response = ""
        stream_started = False

        try:
            constraint_errors = validate_message_constraints(
                state.get("unified_messages") or [],
                (model_candidate.get("config") or {}).get("constraints") or {},
            )
            if constraint_errors:
                raise RuntimeError("；".join(constraint_errors))

            candidate_messages = svc.build_unified_messages(
                user_message=state.get("user_message", ""),
                context=state.get("rag_context"),
                history=history,
                user_parts=svc._materialize_request_user_parts_for_candidate(
                    model_candidate,
                    request_user_parts,
                    upload_context,
                ),
            )

            async for llm_chunk in model_candidate["llm"].stream_chat(
                UnifiedModelRequest.from_messages(
                    candidate_messages,
                    temperature=config.get("temperature"),
                    max_tokens=config.get("max_tokens"),
                ),
            ):
                if llm_chunk.content:
                    stream_started = True
                    full_response += llm_chunk.content
                    state["pending_chunks"].append(
                        {
                            "session_id": state.get("session_id"),
                            "message_id": state.get("message_id"),
                            "type": RESPONSE_TYPE_CONTENT,
                            "content": llm_chunk.content,
                            "metadata": {},
                        }
                    )

                if llm_chunk.finish_reason:
                    state["usage"] = llm_chunk.usage or {}
                    state["fallback_used"] = fallback_used
                    state["fallback_reason"] = last_error
                    completion_metadata = svc.build_completion_metadata(
                        base_metadata=base_completion_metadata,
                        model_row=model_candidate,
                        route_scene=state.get("route_scene", "chat"),
                        config_version=governance_resolution.get("config_version", 1),
                        usage=llm_chunk.usage,
                        fallback_used=fallback_used,
                        fallback_reason=last_error,
                        requested_model=config.get("model"),
                    )
                    state["pending_chunks"].append(
                        {
                            "session_id": state.get("session_id"),
                            "message_id": state.get("message_id"),
                            "type": RESPONSE_TYPE_COMPLETE,
                            "content": "",
                            "token_usage": llm_chunk.usage or {},
                            "metadata": completion_metadata,
                        }
                    )

            state["response_text"] = full_response
            svc.cache_history(
                state.get("session_id", ""),
                svc.append_history(
                    history,
                    state.get("user_message", ""),
                    full_response,
                    user_parts=request_user_parts,
                ),
            )
            return state
        except Exception as exc:
            if stream_started or attempt_index == len(candidates) - 1:
                raise
            last_error = str(exc)
            logger.warning(
                "Model %s failed before streaming, falling back: %s",
                model_candidate.get("display_name") or model_candidate.get("model_id"),
                exc,
            )

    raise RuntimeError(last_error or "No available model candidate")


async def no_hit_node(state: ChatState) -> ChatState:
    """Emit canned no-hit response and terminate when RAG returned nothing."""
    svc = _service()
    config = state.get("config") or {}
    no_hit_metadata = svc.build_response_metadata(
        retrieval_status="no_hits",
        use_rag=True,
        knowledge_base_id=config.get("knowledge_base_id"),
        knowledge_base_name=state.get("knowledge_base_name"),
        citations=[],
        route_scene=state.get("route_scene", "rag_chat"),
        feature_code=state.get("route_scene", "rag_chat"),
        governance_config_version=1,
    )
    no_hit_message = "我没有在当前知识库中检索到足够相关的内容，请换个问法，或先补充文档后再提问。"
    state["pending_chunks"].extend(
        [
            {
                "session_id": state.get("session_id"),
                "message_id": state.get("message_id"),
                "type": RESPONSE_TYPE_CONTENT,
                "content": no_hit_message,
                "metadata": no_hit_metadata,
            },
            {
                "session_id": state.get("session_id"),
                "message_id": state.get("message_id"),
                "type": RESPONSE_TYPE_COMPLETE,
                "content": "",
                "token_usage": {},
                "metadata": no_hit_metadata,
            },
        ]
    )
    svc.cache_history(
        state.get("session_id", ""),
        svc.append_history(state.get("history") or [], state.get("user_message", ""), no_hit_message),
    )
    state["response_text"] = no_hit_message
    return state


def route_after_retrieve(state: ChatState) -> str:
    """Conditional: RAG was requested, retrieval ran, no citations came back."""
    config = state.get("config") or {}
    if bool(config.get("use_rag")) and not (state.get("citations") or []):
        return "no_hit"
    return "build_messages"


__all__ = [
    "parse_node",
    "resolve_route_node",
    "retrieve_node",
    "build_messages_node",
    "call_model_node",
    "no_hit_node",
    "route_after_retrieve",
]
