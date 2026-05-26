"""Stateless helpers for the chat graph.

These free functions absorb the logic that previously lived on
``ChatRuntimeService``. The split is:

  * helpers.py — pure functions (metadata building, history parsing,
    request shaping, candidate filtering)
  * sessions.py — the dev-only in-memory session cache
  * llm_resolver.py — async governance routing + model row resolution

The chat graph nodes import from here directly; ``ChatServiceImpl``
in ``api/`` imports ``parse_request`` and ``build_error_response``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from ai_runtime.core.chat.prompting import ChatPromptBuilder
from ai_runtime.core.chat.response_types import RESPONSE_TYPE_ERROR
from ai_runtime.core.dependencies import DEV_DEFAULT_TENANT_ID, get_container
from ai_runtime.core.llm import create_llm_for_provider
from ai_runtime.core.llm.messages import (
    ContentPart,
    ModelRequestProfile,
    SUPPORTED_ENDPOINT_PROTOCOLS,
    UnifiedMessage,
    capability_profile_from_settings,
    endpoint_protocol_input_modalities,
    supports_model_request,
)
from ai_runtime.core.uploads.bundle_store import (
    UPLOAD_BUNDLE_IDS_METADATA_KEY,
    normalize_bundle_ids,
)

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PRICE_PER_1K = 0.0015
DEFAULT_OUTPUT_PRICE_PER_1K = 0.002
CHAT_HISTORY_METADATA_KEY = "chat_history"
CHAT_CONTENT_PARTS_METADATA_KEY = "chat_content_parts"


_PROMPT_BUILDER = ChatPromptBuilder()


def prompt_builder() -> ChatPromptBuilder:
    return _PROMPT_BUILDER


# ---------- request shape helpers ----------

def get_field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_config_field(config, key, default=None):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in ("", None):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------- request parsing ----------

def deserialize_history(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(value, list):
        return []
    history: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        content_parts = deserialize_content_parts(item.get("content_parts"))
        if not role or (content is None and not content_parts):
            continue
        entry: Dict[str, Any] = {"role": str(role)}
        if content_parts:
            entry["content"] = content_parts
            entry["content_parts"] = content_parts
        else:
            entry["content"] = content
        history.append(entry)
    return history


def deserialize_content_parts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def extract_request_parts(request: Any) -> List[Dict[str, Any]]:
    raw_parts = get_field(request, "content", None)
    if raw_parts is None:
        raw_parts = get_field(request, "content_parts", None)
    if raw_parts is None:
        return []
    if isinstance(raw_parts, list):
        return deserialize_content_parts(raw_parts)
    if isinstance(raw_parts, str):
        return deserialize_content_parts(raw_parts)
    return []


def parse_request(request, *, sessions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    config = get_field(request, "config")
    knowledge_base_id = get_config_field(config, "knowledge_base_id", None)
    if knowledge_base_id == "":
        knowledge_base_id = None

    metadata = get_field(request, "metadata", {}) or {}
    if not knowledge_base_id and isinstance(metadata, dict):
        knowledge_base_id = metadata.get("knowledge_base_id") or None
    session_id = get_field(request, "session_id")
    history = deserialize_history(metadata.get(CHAT_HISTORY_METADATA_KEY)) if isinstance(metadata, dict) else []
    if not history:
        session = sessions.get(session_id, {"history": []})
        history = list(session.get("history", []))
    content_parts = extract_request_parts(request)
    upload_bundle_ids = (
        normalize_bundle_ids(metadata.get(UPLOAD_BUNDLE_IDS_METADATA_KEY))
        if isinstance(metadata, dict)
        else []
    )
    user_message = get_field(request, "message")
    if not user_message and content_parts:
        user_message = "".join(
            str(part.get("text") or "")
            for part in content_parts
            if str(part.get("type") or "").lower() == "text"
        )

    return {
        "session_id": session_id,
        "user_message": user_message,
        "temperature": get_config_field(config, "temperature", 0.7) or 0.7,
        "max_tokens": get_config_field(config, "max_tokens", 2000) or 2000,
        "requested_model": get_config_field(config, "model", None) or None,
        "use_rag": bool(get_config_field(config, "use_rag", False)),
        "knowledge_base_id": knowledge_base_id,
        "metadata": metadata,
        "tenant_id": get_field(request, "tenant_id", DEV_DEFAULT_TENANT_ID) or DEV_DEFAULT_TENANT_ID,
        "user_id": get_field(request, "user_id", None) or None,
        "history": history,
        "upload_bundle_ids": upload_bundle_ids,
        "content_parts": content_parts,
    }


def build_error_response(session_id: str, error: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "message_id": "",
        "type": RESPONSE_TYPE_ERROR,
        "content": "",
        "error": error,
        "metadata": {},
    }


def build_message_id(session_id: str, history_length: int) -> str:
    return f"msg_{session_id}_{history_length}"


def append_history(
    history: List[Dict[str, Any]],
    user_message: str,
    assistant_message: str,
    user_parts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    user_entry: Dict[str, Any] = {"role": "user", "content": user_message}
    if user_parts:
        user_entry["content"] = list(user_parts)
    return [
        *history,
        user_entry,
        {"role": "assistant", "content": assistant_message},
    ]


def build_combined_context(*parts: Optional[str]) -> Optional[str]:
    sections = [str(part).strip() for part in parts if str(part or "").strip()]
    if not sections:
        return None
    return "\n\n".join(sections)


def determine_route_scene(use_rag: bool) -> str:
    return "rag_chat" if use_rag else "chat"


# ---------- metadata building ----------

def build_response_metadata(
    base_metadata: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for source in (base_metadata or {}, extra):
        for key, value in source.items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                metadata[key] = json.dumps(value, ensure_ascii=False)
            else:
                metadata[key] = str(value)
    return metadata


def calculate_usage_cost(usage: Dict[str, Any], model_row: Dict[str, Any]) -> float:
    config = model_row.get("config") or {}
    input_price = safe_float(
        config.get("input_price_per_1k", config.get("input_token_price")),
        DEFAULT_INPUT_PRICE_PER_1K,
    )
    output_price = safe_float(
        config.get("output_price_per_1k", config.get("output_token_price")),
        DEFAULT_OUTPUT_PRICE_PER_1K,
    )
    prompt_tokens = safe_int(usage.get("prompt_tokens"))
    completion_tokens = safe_int(usage.get("completion_tokens"))
    return round(
        (prompt_tokens / 1000.0 * input_price)
        + (completion_tokens / 1000.0 * output_price),
        6,
    )


def build_completion_metadata(
    base_metadata: Dict[str, Any],
    model_row: Dict[str, Any],
    route_scene: str,
    config_version: int,
    usage: Optional[Dict[str, Any]],
    fallback_used: bool,
    fallback_reason: Optional[str],
    requested_model: Optional[str],
) -> Dict[str, str]:
    normalized_usage = {
        "prompt_tokens": safe_int((usage or {}).get("prompt_tokens")),
        "completion_tokens": safe_int((usage or {}).get("completion_tokens")),
        "total_tokens": safe_int((usage or {}).get("total_tokens")),
    }
    cost = safe_float((usage or {}).get("cost"), 0.0)
    if not cost and normalized_usage["total_tokens"] > 0:
        cost = calculate_usage_cost(normalized_usage, model_row)

    return build_response_metadata(
        base_metadata,
        route_scene=route_scene,
        feature_code=route_scene,
        governance_config_version=config_version,
        requested_model=requested_model,
        model_source=model_row.get("source"),
        resolved_model_id=model_row.get("id"),
        resolved_model_name=model_row.get("display_name"),
        resolved_model_provider=model_row.get("provider"),
        resolved_provider_model_id=model_row.get("model_id"),
        endpoint_protocol=(model_row.get("config") or {}).get("endpoint_protocol"),
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        prompt_tokens=normalized_usage["prompt_tokens"],
        completion_tokens=normalized_usage["completion_tokens"],
        total_tokens=normalized_usage["total_tokens"],
        cost_usd=cost,
    )


# ---------- attachments / media transport ----------

def adapter_options(candidate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = (candidate or {}).get("config") if candidate else None
    if isinstance(config, dict):
        options = config.get("adapter_options")
        if isinstance(options, dict):
            return options
    return {}


def media_transport_priority(candidate: Optional[Dict[str, Any]], media_kind: str) -> List[str]:
    options = adapter_options(candidate)
    by_type = options.get("media_transport_by_type")
    raw = None
    if isinstance(by_type, dict):
        raw = by_type.get(media_kind)
    if raw is None:
        raw = options.get("media_transport")
    if isinstance(raw, str):
        items = [item.strip().lower() for item in raw.split(",")]
    elif isinstance(raw, list):
        items = [str(item or "").strip().lower() for item in raw]
    else:
        items = []
    normalized = [item for item in items if item in {"text", "url", "base64", "file_id"}]
    return normalized or ["file_id", "url", "base64", "text"]


def attachment_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def attachment_requires_text(item: Dict[str, Any]) -> bool:
    media_kind = str(item.get("media_kind") or "").lower()
    if media_kind in {"image", "audio", "video"}:
        return False
    transport = dict(
        item.get("transport") or attachment_metadata(item).get("transport") or {}
    )
    preferred = [str(value).lower() for value in transport.get("preferred_types") or []]
    return "text" in preferred or bool(item.get("context_available"))


def build_request_user_parts(
    user_message: str,
    content_parts: Sequence[Dict[str, Any]] | None,
    upload_context: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    has_text_part = False
    file_map = (
        {
            str(item.get("id") or ""): item
            for item in (upload_context.get("files") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        if upload_context
        else {}
    )
    for part in content_parts or []:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "").strip().lower()
        if part_type == "text":
            parts.append(part)
            if str(part.get("text") or "").strip():
                has_text_part = True
            continue
        if part_type == "tool_result":
            parts.append(part)
            continue
        if part_type in {"image", "audio", "video", "file"}:
            has_binary_source = any(
                str(part.get(field) or "").strip()
                for field in ("url", "base64", "data", "file_id")
            )
            if not upload_context or (has_binary_source and not str(part.get("file_id") or "").strip()):
                parts.append(part)
    if user_message and not has_text_part:
        parts.insert(0, {"type": "text", "text": user_message})
    if upload_context:
        for item in upload_context.get("media_parts", []) or []:
            if not isinstance(item, dict):
                continue
            attachment_id = str(item.get("file_id") or item.get("attachment_id") or "").strip()
            source = file_map.get(attachment_id) if attachment_id else None
            if source:
                parts.append(
                    {
                        **item,
                        "attachment_id": attachment_id,
                        "data": {
                            "size_bytes": source.get("size_bytes"),
                            "sha256": source.get("sha256"),
                            "extension": source.get("extension"),
                            "transport": source.get("transport") or {},
                            "metadata": source.get("metadata") or {},
                        },
                    }
                )
            else:
                parts.append(item)
        for item in upload_context.get("files", []) or []:
            if not isinstance(item, dict):
                continue
            if attachment_requires_text(item):
                parts.append(
                    {
                        "type": "file",
                        "attachment_id": item.get("id"),
                        "file_id": item.get("id"),
                        "file_name": item.get("name"),
                        "text": item.get("excerpt") or item.get("preview_text") or None,
                        "mime_type": item.get("mime_type") or item.get("content_type"),
                        "data": {
                            "size_bytes": item.get("size_bytes"),
                            "sha256": item.get("sha256"),
                            "extension": item.get("extension"),
                            "transport": item.get("transport") or {},
                            "metadata": item.get("metadata") or {},
                        },
                    }
                )
    return parts


def materialize_request_user_parts_for_candidate(
    candidate: Optional[Dict[str, Any]],
    request_user_parts: Sequence[Dict[str, Any]],
    upload_context: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not upload_context or not request_user_parts:
        return list(request_user_parts or [])

    file_map = {
        str(item.get("id") or ""): item
        for item in (upload_context.get("files") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    media_map = {
        str(item.get("file_id") or item.get("attachment_id") or ""): item
        for item in (upload_context.get("media_parts") or [])
        if isinstance(item, dict) and str(item.get("file_id") or item.get("attachment_id") or "").strip()
    }
    materialized: List[Dict[str, Any]] = []
    for part in request_user_parts:
        if not isinstance(part, dict):
            continue
        attachment_id = str(part.get("attachment_id") or part.get("file_id") or "").strip()
        if not attachment_id:
            materialized.append(part)
            continue
        source = file_map.get(attachment_id) or media_map.get(attachment_id)
        if not source:
            materialized.append(part)
            continue
        media_kind = str(source.get("media_kind") or part.get("type") or "file").lower()
        transport_priority = media_transport_priority(candidate, media_kind)
        metadata = attachment_metadata(source)
        base_data = {
            "size_bytes": source.get("size_bytes"),
            "sha256": source.get("sha256") or metadata.get("sha256"),
            "extension": source.get("extension") or metadata.get("extension"),
            "transport": dict(source.get("transport") or metadata.get("transport") or {}),
            "metadata": metadata,
        }
        chosen: Dict[str, Any] | None = None
        for transport in transport_priority:
            if transport == "text" and str(
                source.get("content") or source.get("excerpt") or source.get("preview_text") or ""
            ).strip():
                chosen = {
                    "type": "file",
                    "attachment_id": attachment_id,
                    "file_id": attachment_id,
                    "file_name": source.get("name"),
                    "text": source.get("content") or source.get("excerpt") or source.get("preview_text"),
                    "mime_type": source.get("mime_type") or source.get("content_type"),
                    "data": base_data,
                }
                break
            if transport == "file_id" and attachment_id:
                chosen = {
                    "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                    "attachment_id": attachment_id,
                    "file_id": attachment_id,
                    "file_name": source.get("name"),
                    "mime_type": source.get("mime_type") or source.get("content_type"),
                    "base64": source.get("base64") if media_kind == "image" else None,
                    "data": base_data,
                }
                break
            if transport == "base64" and source.get("base64"):
                chosen = {
                    "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                    "attachment_id": attachment_id,
                    "file_id": attachment_id,
                    "file_name": source.get("name"),
                    "mime_type": source.get("mime_type") or source.get("content_type"),
                    "base64": source.get("base64"),
                    "data": base_data,
                }
                break
            if transport == "url" and source.get("path"):
                chosen = {
                    "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                    "attachment_id": attachment_id,
                    "file_id": attachment_id,
                    "file_name": source.get("name"),
                    "url": source.get("path"),
                    "mime_type": source.get("mime_type") or source.get("content_type"),
                    "data": base_data,
                }
                break
        materialized.append(chosen or part)
    return materialized


# ---------- model config / candidate building ----------

def deserialize_config(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        config = dict(value)
        config.setdefault("task_type", "chat.completion")
        config["output_modalities"] = ["text"]
        config.setdefault("constraints", {})
        config.setdefault("adapter_options", {})
        config["capabilities"] = build_capabilities_from_config(config)
        return config
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, dict):
                decoded.setdefault("task_type", "chat.completion")
                decoded["output_modalities"] = ["text"]
                decoded.setdefault("constraints", {})
                decoded.setdefault("adapter_options", {})
                decoded["capabilities"] = build_capabilities_from_config(decoded)
                return decoded
            return {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def build_capabilities_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    input_modalities = config.get("input_modalities")
    capabilities = capability_profile_from_settings(
        config.get("capabilities") if isinstance(config.get("capabilities"), dict) else None,
        {
            "task_type": "chat.completion",
            "endpoint_protocol": config.get("endpoint_protocol"),
            "input_modalities": input_modalities,
            "output_modalities": ["text"],
            "default_output_modalities": ["text"],
            "supported_response_formats": config.get("supported_response_formats", ["text"]),
            "supports_tools": bool(config.get("supports_tools", False)),
            "supports_streaming": bool(config.get("supports_streaming", True)),
            "supports_reasoning": bool(config.get("supports_reasoning", False)),
            "supports_vision": bool(config.get("supports_vision", False)),
            "supports_audio_input": bool(config.get("supports_audio_input", False)),
            "supports_audio_output": bool(config.get("supports_audio_output", False)),
            "supports_video_input": bool(config.get("supports_video_input", False)),
            "supports_file_input": bool(config.get("supports_file_input", False)),
        },
    )
    return capabilities.model_dump()


def candidate_capability(candidate: Dict[str, Any]):
    return (
        getattr(candidate.get("llm"), "capabilities", None)
        or (candidate.get("config") or {}).get("capabilities")
        or candidate.get("config", {})
    )


def candidate_endpoint_protocol(candidate: Dict[str, Any], capability: Any = None) -> Optional[str]:
    if capability is None:
        capability = candidate_capability(candidate)
    endpoint_protocol = getattr(capability, "endpoint_protocol", None)
    if not endpoint_protocol and isinstance(capability, dict):
        endpoint_protocol = capability.get("endpoint_protocol")
    if not endpoint_protocol:
        endpoint_protocol = (candidate.get("config") or {}).get("endpoint_protocol")
    normalized = str(endpoint_protocol or "").strip().lower()
    return normalized or None


def reject_reason_for_model_request(
    candidate: Dict[str, Any], request_profile: ModelRequestProfile
) -> str | None:
    capability = candidate_capability(candidate)
    endpoint_protocol = candidate_endpoint_protocol(candidate, capability)
    if endpoint_protocol and endpoint_protocol not in SUPPORTED_ENDPOINT_PROTOCOLS:
        return f"endpoint_protocol={endpoint_protocol} 没有对应 adapter"
    if not supports_model_request(capability, request_profile):
        return "模型能力不满足请求画像"
    return None


# ---------- LLM resolution (governance routing) ----------

_LLM_INSTANCE_CACHE: Dict[str, Any] = {}


def _create_llm_instance(model_row: Dict[str, Any]):
    cache_key = model_row["id"]
    cached = _LLM_INSTANCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    provider = (model_row.get("provider") or "").lower()
    model_id = model_row.get("model_id") or "unknown-model"
    api_key = model_row.get("api_key_encrypted")
    api_base = model_row.get("api_base")
    llm = create_llm_for_provider(
        provider,
        model=model_id,
        api_key=api_key,
        api_base=api_base,
        config=model_row.get("config") or {},
    )
    _LLM_INSTANCE_CACHE[cache_key] = llm
    return llm


def _build_model_candidate(
    model_row: Optional[Dict[str, Any]],
    source: str,
) -> Optional[Dict[str, Any]]:
    if not model_row:
        return None
    try:
        config = model_row.get("config") or {}
        llm = _create_llm_instance({**model_row, "config": config})
        return {
            **model_row,
            "config": config,
            "llm": llm,
            "source": source,
        }
    except Exception as exc:
        logger.warning(
            "Failed to initialize model candidate %s: %s",
            model_row.get("display_name") or model_row.get("model_id"),
            exc,
        )
        return None


async def _get_model_row(
    tenant_id: str,
    selector: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    pool = get_container().kb_repository.db_pool

    async with pool.acquire() as conn:
        if selector:
            try:
                selector_uuid = UUID(selector)
            except ValueError:
                selector_uuid = None
            if selector_uuid:
                query = """
                    SELECT id, name, display_name, provider, model_id, api_base,
                           api_key_encrypted, config, enabled, is_default
                    FROM llm_models
                    WHERE model_type = 'llm'
                      AND enabled = true
                      AND (tenant_id = $1 OR tenant_id IS NULL)
                      AND (id = $2 OR model_id = $3 OR name = $3 OR display_name = $3)
                    ORDER BY CASE WHEN tenant_id = $1 THEN 0 ELSE 1 END, is_default DESC, updated_at DESC
                    LIMIT 1
                """
                row = await conn.fetchrow(query, tenant_id, selector_uuid, selector)
            else:
                query = """
                    SELECT id, name, display_name, provider, model_id, api_base,
                           api_key_encrypted, config, enabled, is_default
                    FROM llm_models
                    WHERE model_type = 'llm'
                      AND enabled = true
                      AND (tenant_id = $1 OR tenant_id IS NULL)
                      AND (model_id = $2 OR name = $2 OR display_name = $2)
                    ORDER BY CASE WHEN tenant_id = $1 THEN 0 ELSE 1 END, is_default DESC, updated_at DESC
                    LIMIT 1
                """
                row = await conn.fetchrow(query, tenant_id, selector)
        else:
            query = """
                SELECT id, name, display_name, provider, model_id, api_base,
                       api_key_encrypted, config, enabled, is_default
                FROM llm_models
                WHERE model_type = 'llm'
                  AND enabled = true
                  AND (tenant_id = $1 OR tenant_id IS NULL)
                ORDER BY CASE WHEN tenant_id = $1 THEN 0 ELSE 1 END, is_default DESC, updated_at DESC
                LIMIT 1
            """
            row = await conn.fetchrow(query, tenant_id)

    if not row:
        return None
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "display_name": row["display_name"],
        "provider": row["provider"],
        "model_id": row["model_id"],
        "api_base": row["api_base"],
        "api_key_encrypted": row["api_key_encrypted"],
        "config": deserialize_config(row["config"]),
    }


async def _get_governance_settings(
    tenant_id: str,
    user_id: Optional[str],
    knowledge_base_id: Optional[str],
) -> Dict[str, Any]:
    if not knowledge_base_id:
        return {}
    try:
        settings = await get_container().kb_service.get_governance_settings(
            kb_id=knowledge_base_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return settings or {}
    except Exception as exc:
        logger.warning("Failed to resolve governance settings: %s", exc)
        return {}


def _env_default_candidate() -> Dict[str, Any]:
    """Build the env-default fallback candidate (Deepseek by default)."""
    import os
    from ai_runtime.core.config import LLMConfig

    llm_config = LLMConfig.from_env()
    llm = create_llm_for_provider(
        llm_config.provider,
        model=os.getenv("DEFAULT_CHAT_MODEL", llm_config.model),
        api_key=llm_config.api_key,
        api_base=llm_config.api_base,
        config={
            "timeout": llm_config.timeout,
            "max_retries": llm_config.max_retries,
        },
    )
    return {
        "id": "env-default",
        "name": "env-default",
        "display_name": "Environment Default",
        "provider": llm_config.provider,
        "model_id": llm.model,
        "config": {},
        "llm": llm,
        "source": "env_default",
    }


async def resolve_llm_candidates(
    *,
    tenant_id: str,
    user_id: Optional[str],
    knowledge_base_id: Optional[str],
    route_scene: str,
    requested_model: Optional[str],
    required_modalities: Optional[set[str]] = None,
    request_profile: Optional[ModelRequestProfile] = None,
) -> Dict[str, Any]:
    governance_settings = await _get_governance_settings(
        tenant_id=tenant_id,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )
    route = {}
    if isinstance(governance_settings.get("routes"), dict):
        route = governance_settings["routes"].get(route_scene) or {}

    route_enabled = route.get("enabled", True)
    primary_selector = requested_model or (route.get("primary_model_id") if route_enabled else None)
    fallback_selector = None if requested_model else (route.get("fallback_model_id") if route_enabled else None)

    source = (
        "request_override"
        if requested_model
        else "governance_route"
        if primary_selector
        else "default_model"
    )

    candidates: List[Dict[str, Any]] = []
    primary_row = await _get_model_row(tenant_id, primary_selector)
    primary_candidate = _build_model_candidate(primary_row, source)
    if primary_candidate:
        candidates.append(primary_candidate)

    if not candidates:
        fallback_default_row = await _get_model_row(tenant_id, None)
        fallback_default_candidate = _build_model_candidate(fallback_default_row, "default_model")
        if fallback_default_candidate:
            candidates.append(fallback_default_candidate)

    if fallback_selector:
        fallback_row = await _get_model_row(tenant_id, fallback_selector)
        fallback_candidate = _build_model_candidate(fallback_row, "fallback_model")
        if fallback_candidate and all(item["id"] != fallback_candidate["id"] for item in candidates):
            candidates.append(fallback_candidate)

    if not candidates:
        candidates.append(_env_default_candidate())

    if request_profile is None and required_modalities:
        request_profile = ModelRequestProfile(
            input_modalities=sorted(required_modalities),
            output_modalities=["text"],
        )

    if request_profile:
        filtered = []
        rejected: List[Dict[str, Any]] = []
        for candidate in candidates:
            reject_reason = reject_reason_for_model_request(candidate, request_profile)
            if not reject_reason:
                filtered.append(candidate)
            else:
                candidate["_reject_reason"] = reject_reason
                rejected.append(candidate)
        candidates = filtered

        if not candidates:
            required_inputs = set(request_profile.input_modalities or ["text"])
            rejected_names = [
                item.get("display_name") or item.get("model_id") or item.get("name") or "unknown"
                for item in rejected
            ]
            first_capability = None
            if rejected:
                first_llm = rejected[0].get("llm")
                first_capability = (
                    getattr(first_llm, "capabilities", None)
                    or (rejected[0].get("config") or {}).get("capabilities")
                )
            supported_inputs = sorted(
                set(
                    getattr(first_capability, "input_modalities", None)
                    or (first_capability or {}).get("input_modalities", ["text"])
                )
            )
            missing_inputs = sorted(required_inputs - set(supported_inputs))
            endpoint_protocol = (
                candidate_endpoint_protocol(rejected[0], first_capability) if rejected else None
            )
            protocol_modalities = endpoint_protocol_input_modalities(endpoint_protocol)
            fixed_hint = "，不会静默切换到 fallback 模型" if requested_model or primary_selector else ""
            protocol_hint = ""
            if endpoint_protocol and endpoint_protocol not in SUPPORTED_ENDPOINT_PROTOCOLS:
                protocol_hint = f" endpoint_protocol={endpoint_protocol} 没有对应 adapter。"
            elif endpoint_protocol and protocol_modalities is not None and not required_inputs.issubset(protocol_modalities):
                unsupported_by_protocol = sorted(required_inputs - protocol_modalities)
                protocol_hint = (
                    f" 模型声明的 endpoint_protocol={endpoint_protocol} 当前 adapter 未实现 "
                    f"{', '.join(unsupported_by_protocol)} part 转换。"
                )
            raise RuntimeError(
                "当前智能体模型"
                f" {', '.join(rejected_names) or 'unknown'} 只支持输入 {', '.join(supported_inputs)}，"
                f"不能处理 {', '.join(missing_inputs or sorted(required_inputs))}{fixed_hint}。"
                f"{protocol_hint}"
                "请切换到支持这些输入且输出 text 的聊天模型。"
            )

    return {
        "route_scene": route_scene,
        "requested_model": requested_model,
        "config_version": safe_int(governance_settings.get("config_version"), 1),
        "fallback_selector": fallback_selector,
        "candidates": candidates,
        "required_modalities": sorted(
            required_modalities or (request_profile.input_modalities if request_profile else [])
        ),
        "request_profile": request_profile.model_dump() if request_profile else None,
    }


# ---------- RAG ----------

async def _get_knowledge_base_name(
    tenant_id: str,
    user_id: Optional[str],
    knowledge_base_id: Optional[str],
) -> Optional[str]:
    if not knowledge_base_id:
        return None
    try:
        kb_service = get_container().kb_service
        kb = await kb_service.get_knowledge_base(
            kb_id=knowledge_base_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if kb:
            return kb.name
    except Exception as exc:
        logger.warning("Failed to resolve knowledge base name: %s", exc)
    return None


async def build_rag_context_and_citations(
    *,
    tenant_id: str,
    user_id: Optional[str],
    knowledge_base_id: Optional[str],
    query: str,
    top_k: int = 3,
) -> tuple[str, List[Dict[str, Any]], Optional[str]]:
    try:
        container = get_container()
        doc_service = container.document_service
        results = await doc_service.search_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
        )
        kb_name = await _get_knowledge_base_name(tenant_id, user_id, knowledge_base_id)
    except Exception as exc:
        logger.warning("Failed to build RAG citations: %s", exc)
        return "", [], None

    if not results:
        return "", [], kb_name

    context_parts: List[str] = []
    citations: List[Dict[str, Any]] = []
    citation_index = 1

    for doc_rank, (doc, score) in enumerate(results, 1):
        matched_segments = await doc_service.get_matched_segments(
            document=doc,
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            max_segments=2,
        )
        if not matched_segments:
            matched_segments = [
                {
                    "chunk_id": None,
                    "segment_index": 1,
                    "start_offset": 0,
                    "end_offset": len(doc.content or ""),
                    "char_count": len(doc.content or ""),
                    "content": (doc.content or "")[:800],
                    "match_score": 0.0,
                    "segment_type": "full",
                    "section_title": doc.title,
                    "citation_label": "全文",
                    "heading_level": None,
                }
            ]

        for segment in matched_segments:
            context_parts.append(f"[Citation {citation_index}] title={doc.title} score={score:.4f}")
            if doc.source:
                context_parts.append(f"source={doc.source}")
            if segment.get("citation_label"):
                context_parts.append(f"segment={segment['citation_label']}")
            context_parts.append(segment.get("content", "") or "")
            context_parts.append("")

            citations.append(
                {
                    "citation_id": f"{doc.id}:{segment.get('chunk_id') or segment.get('segment_index') or citation_index}",
                    "document_id": doc.id,
                    "chunk_id": segment.get("chunk_id"),
                    "title": doc.title,
                    "source": doc.source,
                    "knowledge_base_id": doc.knowledge_base_id,
                    "score": round(float(score), 4),
                    "document_rank": doc_rank,
                    "segment_index": segment.get("segment_index"),
                    "segment_type": segment.get("segment_type"),
                    "section_title": segment.get("section_title"),
                    "citation_label": segment.get("citation_label"),
                    "matched_segments": [segment],
                }
            )
            citation_index += 1

    return "\n".join(context_parts), citations, kb_name


# ---------- prompt building ----------

def build_unified_messages(
    *,
    user_message: str,
    history: Optional[Sequence[UnifiedMessage | Dict[str, Any]]] = None,
    context: Optional[str] = None,
    user_parts: Optional[Sequence[ContentPart | Dict[str, Any]]] = None,
) -> List[UnifiedMessage]:
    return prompt_builder().build_unified_messages(
        user_message=user_message,
        context=context,
        history=history,
        user_parts=user_parts,
    )
