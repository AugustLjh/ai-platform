from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple
import json
import logging
import os
from uuid import UUID

from ai_runtime.core.chat.prompting import ChatPromptBuilder
from ai_runtime.core.chat.response_types import (
    RESPONSE_TYPE_COMPLETE,
    RESPONSE_TYPE_CONTENT,
    RESPONSE_TYPE_ERROR,
)
from ai_runtime.core.config import LLMConfig
from ai_runtime.core.dependencies import DEV_DEFAULT_TENANT_ID, get_container
from ai_runtime.core.llm import create_llm_for_provider
from ai_runtime.core.llm.messages import (
    ContentPart,
    ModelRequestProfile,
    SUPPORTED_ENDPOINT_PROTOCOLS,
    UnifiedMessage,
    UnifiedModelRequest,
    build_model_request_profile,
    capability_profile_from_settings,
    endpoint_protocol_input_modalities,
    normalize_messages,
    required_input_modalities,
    supports_model_request,
    validate_message_constraints,
)
from ai_runtime.core.rag import RAGPipeline, Retriever, SimpleVectorStore
from ai_runtime.core.rag.retriever import DatabaseVectorStore
from ai_runtime.core.uploads.bundle_store import UPLOAD_BUNDLE_IDS_METADATA_KEY, get_attachment_bundle_store, normalize_bundle_ids

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PRICE_PER_1K = 0.0015
DEFAULT_OUTPUT_PRICE_PER_1K = 0.002
CHAT_HISTORY_METADATA_KEY = "chat_history"
CHAT_CONTENT_PARTS_METADATA_KEY = "chat_content_parts"

class ChatRuntimeService:
    """Dedicated runtime for chat-mode requests."""

    def __init__(self, sessions: Optional[Dict[str, Dict[str, Any]]] = None):
        self.prompt_builder = ChatPromptBuilder()
        self.vector_store = SimpleVectorStore()
        self.retriever = Retriever(self.vector_store)
        self.rag_pipeline = RAGPipeline(self.retriever)
        llm_config = LLMConfig.from_env()
        self.default_llm = create_llm_for_provider(
            llm_config.provider,
            model=os.getenv("DEFAULT_CHAT_MODEL", llm_config.model),
            api_key=llm_config.api_key,
            api_base=llm_config.api_base,
            config={
                "timeout": llm_config.timeout,
                "max_retries": llm_config.max_retries,
            },
        )
        self._llm_cache: Dict[str, Any] = {}
        # Dev-only cache used by the standalone runtime history endpoints.
        self.sessions = sessions if sessions is not None else {}

    async def _get_knowledge_base_name(
        self,
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

    async def _get_governance_settings(
        self,
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

    async def _build_rag_context_and_citations(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        query: str,
        top_k: int = 3,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
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
            kb_name = await self._get_knowledge_base_name(tenant_id, user_id, knowledge_base_id)
        except Exception as exc:
            logger.warning("Failed to build RAG citations, fallback to pipeline: %s", exc)
            rag_pipeline = self._build_rag_pipeline(tenant_id, user_id, knowledge_base_id)
            return await rag_pipeline.process(query, top_k=top_k), [], None

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

    def _build_response_metadata(
        self,
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

    def _build_rag_pipeline(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
    ) -> RAGPipeline:
        try:
            container = get_container()
            kb_service = container.kb_service
            vector_store = DatabaseVectorStore(
                kb_service=kb_service,
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )
            retriever = Retriever(vector_store)
            return RAGPipeline(retriever)
        except Exception as exc:
            logger.warning("RAG pipeline fallback to in-memory store: %s", exc)
            return self.rag_pipeline

    def _get_field(self, obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_config_field(self, config, key, default=None):
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(key, default)
        return getattr(config, key, default)

    def _adapter_options(self, candidate: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = (candidate or {}).get("config") if candidate else None
        if isinstance(config, dict):
            options = config.get("adapter_options")
            if isinstance(options, dict):
                return options
        return {}

    def _media_transport_priority(self, candidate: Optional[Dict[str, Any]], media_kind: str) -> list[str]:
        options = self._adapter_options(candidate)
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

    def _attachment_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        metadata = item.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    def _attachment_context_part(self, item: Dict[str, Any]) -> Dict[str, Any]:
        media_kind = str(item.get("media_kind") or "file").lower()
        metadata = self._attachment_metadata(item)
        transport = dict(item.get("transport") or metadata.get("transport") or {})
        return {
            "type": media_kind,
            "attachment_id": item.get("id"),
            "file_id": item.get("id"),
            "file_name": item.get("name"),
            "mime_type": item.get("mime_type") or item.get("content_type"),
            "base64": item.get("base64"),
            "text": item.get("content") or item.get("excerpt") or item.get("preview_text") or None,
            "data": {
                "size_bytes": item.get("size_bytes"),
                "sha256": item.get("sha256") or metadata.get("sha256"),
                "extension": item.get("extension") or metadata.get("extension"),
                "transport": transport,
                "metadata": metadata,
            },
        }

    def _attachment_requires_text(self, item: Dict[str, Any]) -> bool:
        media_kind = str(item.get("media_kind") or "").lower()
        if media_kind in {"image", "audio", "video"}:
            return False
        transport = dict(item.get("transport") or self._attachment_metadata(item).get("transport") or {})
        preferred = [str(value).lower() for value in transport.get("preferred_types") or []]
        return "text" in preferred or bool(item.get("context_available"))

    def _determine_route_scene(self, use_rag: bool) -> str:
        if use_rag:
            return "rag_chat"
        return "chat"

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in ("", None):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value in ("", None):
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _deserialize_config(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            config = dict(value)
            config.setdefault("task_type", "chat.completion")
            config["output_modalities"] = ["text"]
            config.setdefault("constraints", {})
            config.setdefault("adapter_options", {})
            config["capabilities"] = self._build_capabilities_from_config(config)
            return config
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, dict):
                    decoded.setdefault("task_type", "chat.completion")
                    decoded["output_modalities"] = ["text"]
                    decoded.setdefault("constraints", {})
                    decoded.setdefault("adapter_options", {})
                    decoded["capabilities"] = self._build_capabilities_from_config(decoded)
                    return decoded
                return {}
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
        return {}

    def _build_capabilities_from_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
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
            }
        )
        return capabilities.model_dump()

    def _deserialize_history(self, value: Any) -> List[Dict[str, Any]]:
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
            content_parts = self._deserialize_content_parts(item.get("content_parts"))
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

    def _deserialize_content_parts(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
        if not isinstance(value, list):
            return []
        parts: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item)
        return parts

    async def _get_model_row(
        self,
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
            "config": self._deserialize_config(row["config"]),
        }

    def _create_llm_instance(self, model_row: Dict[str, Any]):
        cache_key = model_row["id"]
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

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

        self._llm_cache[cache_key] = llm
        return llm

    def _build_model_candidate(
        self,
        model_row: Optional[Dict[str, Any]],
        source: str,
    ) -> Optional[Dict[str, Any]]:
        if not model_row:
            return None

        try:
            config = model_row.get("config") or {}
            llm = self._create_llm_instance({**model_row, "config": config})
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

    def _candidate_capability(self, candidate: Dict[str, Any]):
        return (
            getattr(candidate.get("llm"), "capabilities", None)
            or (candidate.get("config") or {}).get("capabilities")
            or candidate.get("config", {})
        )

    def _candidate_endpoint_protocol(self, candidate: Dict[str, Any], capability: Any = None) -> Optional[str]:
        if capability is None:
            capability = self._candidate_capability(candidate)
        endpoint_protocol = getattr(capability, "endpoint_protocol", None)
        if not endpoint_protocol and isinstance(capability, dict):
            endpoint_protocol = capability.get("endpoint_protocol")
        if not endpoint_protocol:
            endpoint_protocol = (candidate.get("config") or {}).get("endpoint_protocol")
        normalized = str(endpoint_protocol or "").strip().lower()
        return normalized or None

    def _reject_reason_for_model_request(self, candidate: Dict[str, Any], request_profile: ModelRequestProfile) -> str | None:
        capability = self._candidate_capability(candidate)
        endpoint_protocol = self._candidate_endpoint_protocol(candidate, capability)
        if endpoint_protocol and endpoint_protocol not in SUPPORTED_ENDPOINT_PROTOCOLS:
            return f"endpoint_protocol={endpoint_protocol} 没有对应 adapter"
        if not supports_model_request(capability, request_profile):
            return "模型能力不满足请求画像"
        return None

    async def _resolve_llm_candidates(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        route_scene: str,
        requested_model: Optional[str],
        required_modalities: Optional[set[str]] = None,
        request_profile: Optional[ModelRequestProfile] = None,
    ) -> Dict[str, Any]:
        governance_settings = await self._get_governance_settings(
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

        source = "request_override" if requested_model else "governance_route" if primary_selector else "default_model"

        candidates: List[Dict[str, Any]] = []
        primary_row = await self._get_model_row(tenant_id, primary_selector)
        primary_candidate = self._build_model_candidate(primary_row, source)
        if primary_candidate:
            candidates.append(primary_candidate)

        if not candidates:
            fallback_default_row = await self._get_model_row(tenant_id, None)
            fallback_default_candidate = self._build_model_candidate(fallback_default_row, "default_model")
            if fallback_default_candidate:
                candidates.append(fallback_default_candidate)

        if fallback_selector:
            fallback_row = await self._get_model_row(tenant_id, fallback_selector)
            fallback_candidate = self._build_model_candidate(fallback_row, "fallback_model")
            if fallback_candidate and all(item["id"] != fallback_candidate["id"] for item in candidates):
                candidates.append(fallback_candidate)

        if not candidates:
            candidates.append(
                {
                    "id": "env-default",
                    "name": "env-default",
                    "display_name": "Environment Default",
                    "provider": "deepseek",
                    "model_id": self.default_llm.model,
                    "config": {},
                    "llm": self.default_llm,
                    "source": "env_default",
                }
            )

        if request_profile is None and required_modalities:
            request_profile = ModelRequestProfile(
                input_modalities=sorted(required_modalities),
                output_modalities=["text"],
            )

        if request_profile:
            filtered = []
            rejected: List[Dict[str, Any]] = []
            for candidate in candidates:
                reject_reason = self._reject_reason_for_model_request(candidate, request_profile)
                if not reject_reason:
                    filtered.append(candidate)
                else:
                    candidate["_reject_reason"] = reject_reason
                    rejected.append(candidate)
            candidates = filtered

        if request_profile and not candidates:
            required_inputs = set(request_profile.input_modalities or ["text"])
            rejected_names = [
                item.get("display_name") or item.get("model_id") or item.get("name") or "unknown"
                for item in rejected
            ]
            first_capability = None
            if rejected:
                first_llm = rejected[0].get("llm")
                first_capability = getattr(first_llm, "capabilities", None) or (rejected[0].get("config") or {}).get("capabilities")
            supported_inputs = sorted(set(getattr(first_capability, "input_modalities", None) or (first_capability or {}).get("input_modalities", ["text"])))
            missing_inputs = sorted(required_inputs - set(supported_inputs))
            endpoint_protocol = self._candidate_endpoint_protocol(rejected[0], first_capability) if rejected else None
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
            "config_version": self._safe_int(governance_settings.get("config_version"), 1),
            "fallback_selector": fallback_selector,
            "candidates": candidates,
            "required_modalities": sorted(required_modalities or (request_profile.input_modalities if request_profile else [])),
            "request_profile": request_profile.model_dump() if request_profile else None,
        }

    async def resolve_llm_candidates(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        route_scene: str,
        requested_model: Optional[str],
        required_modalities: Optional[set[str]] = None,
        request_profile: Optional[ModelRequestProfile] = None,
    ) -> Dict[str, Any]:
        return await self._resolve_llm_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene=route_scene,
            requested_model=requested_model,
            required_modalities=required_modalities,
            request_profile=request_profile,
        )

    def _calculate_usage_cost(self, usage: Dict[str, Any], model_row: Dict[str, Any]) -> float:
        config = model_row.get("config") or {}
        input_price = self._safe_float(
            config.get("input_price_per_1k", config.get("input_token_price")),
            DEFAULT_INPUT_PRICE_PER_1K,
        )
        output_price = self._safe_float(
            config.get("output_price_per_1k", config.get("output_token_price")),
            DEFAULT_OUTPUT_PRICE_PER_1K,
        )
        prompt_tokens = self._safe_int(usage.get("prompt_tokens"))
        completion_tokens = self._safe_int(usage.get("completion_tokens"))
        return round((prompt_tokens / 1000.0 * input_price) + (completion_tokens / 1000.0 * output_price), 6)

    def _build_completion_metadata(
        self,
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
            "prompt_tokens": self._safe_int((usage or {}).get("prompt_tokens")),
            "completion_tokens": self._safe_int((usage or {}).get("completion_tokens")),
            "total_tokens": self._safe_int((usage or {}).get("total_tokens")),
        }
        cost = self._safe_float((usage or {}).get("cost"), 0.0)
        if not cost and normalized_usage["total_tokens"] > 0:
            cost = self._calculate_usage_cost(normalized_usage, model_row)

        return self._build_response_metadata(
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

    async def build_rag_context_and_citations(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        query: str,
        top_k: int = 3,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        return await self._build_rag_context_and_citations(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=top_k,
        )

    def build_response_metadata(
        self,
        base_metadata: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> Dict[str, str]:
        return self._build_response_metadata(base_metadata, **extra)

    def build_completion_metadata(
        self,
        base_metadata: Dict[str, Any],
        model_row: Dict[str, Any],
        route_scene: str,
        config_version: int,
        usage: Optional[Dict[str, Any]],
        fallback_used: bool,
        fallback_reason: Optional[str],
        requested_model: Optional[str],
    ) -> Dict[str, str]:
        return self._build_completion_metadata(
            base_metadata=base_metadata,
            model_row=model_row,
            route_scene=route_scene,
            config_version=config_version,
            usage=usage,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            requested_model=requested_model,
        )

    def build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        context: Optional[str] = None,
        user_parts: Optional[Sequence[ContentPart | Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        return self.prompt_builder.build_messages(
            user_message=user_message,
            context=context,
            history=history,
        )

    def build_unified_messages(
        self,
        user_message: str,
        history: Optional[Sequence[UnifiedMessage | Dict[str, Any]]] = None,
        context: Optional[str] = None,
        user_parts: Optional[Sequence[ContentPart | Dict[str, Any]]] = None,
    ) -> list[UnifiedMessage]:
        return self.prompt_builder.build_unified_messages(
            user_message=user_message,
            context=context,
            history=history,
            user_parts=user_parts,
        )

    def _build_request_user_parts(
        self,
        user_message: str,
        content_parts: Sequence[Dict[str, Any]] | None,
        upload_context: Optional[dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        parts: list[Dict[str, Any]] = []
        has_text_part = False
        file_map = {
            str(item.get("id") or ""): item
            for item in (upload_context.get("files") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        } if upload_context else {}
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
                if self._attachment_requires_text(item):
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

    def _build_transport_parts(
        self,
        candidate: Optional[Dict[str, Any]],
        upload_context: Optional[dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        if not upload_context:
            return []
        parts: list[Dict[str, Any]] = []
        for item in upload_context.get("media_parts", []) or []:
            if isinstance(item, dict):
                parts.append(item)
        for item in upload_context.get("files", []) or []:
            if not isinstance(item, dict):
                continue
            media_kind = str(item.get("media_kind") or "file").lower()
            transport_priority = self._media_transport_priority(candidate, media_kind)
            metadata = self._attachment_metadata(item)
            base_part = self._attachment_context_part(item)
            selected_part: Dict[str, Any] | None = None
            for transport in transport_priority:
                if transport == "text" and self._attachment_requires_text(item):
                    selected_part = {
                        "type": "file",
                        "attachment_id": base_part["attachment_id"],
                        "file_id": base_part["file_id"],
                        "file_name": base_part["file_name"],
                        "text": base_part["text"],
                        "mime_type": base_part["mime_type"],
                        "data": base_part["data"],
                    }
                    break
                if transport == "file_id" and item.get("id"):
                    selected_part = {
                        "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                        "attachment_id": item.get("id"),
                        "file_id": item.get("id"),
                        "file_name": item.get("name"),
                        "mime_type": item.get("mime_type") or item.get("content_type"),
                        "data": {
                            "size_bytes": item.get("size_bytes"),
                            "sha256": item.get("sha256") or metadata.get("sha256"),
                            "extension": item.get("extension") or metadata.get("extension"),
                            "transport": dict(item.get("transport") or metadata.get("transport") or {}),
                            "metadata": metadata,
                        },
                    }
                    if media_kind == "image":
                        selected_part["base64"] = item.get("base64")
                    break
                if transport == "base64" and item.get("base64"):
                    selected_part = {
                        "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                        "attachment_id": item.get("id"),
                        "file_id": item.get("id"),
                        "file_name": item.get("name"),
                        "mime_type": item.get("mime_type") or item.get("content_type"),
                        "base64": item.get("base64"),
                        "data": {
                            "size_bytes": item.get("size_bytes"),
                            "sha256": item.get("sha256") or metadata.get("sha256"),
                            "extension": item.get("extension") or metadata.get("extension"),
                            "transport": dict(item.get("transport") or metadata.get("transport") or {}),
                            "metadata": metadata,
                        },
                    }
                    break
                if transport == "url" and item.get("path"):
                    selected_part = {
                        "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                        "attachment_id": item.get("id"),
                        "file_id": item.get("id"),
                        "file_name": item.get("name"),
                        "url": item.get("path"),
                        "mime_type": item.get("mime_type") or item.get("content_type"),
                        "data": {
                            "size_bytes": item.get("size_bytes"),
                            "sha256": item.get("sha256") or metadata.get("sha256"),
                            "extension": item.get("extension") or metadata.get("extension"),
                            "transport": dict(item.get("transport") or metadata.get("transport") or {}),
                            "metadata": metadata,
                        },
                    }
                    break
            if selected_part is None:
                selected_part = base_part
            parts.append(selected_part)
        return parts

    def _materialize_request_user_parts_for_candidate(
        self,
        candidate: Optional[Dict[str, Any]],
        request_user_parts: Sequence[Dict[str, Any]],
        upload_context: Optional[dict[str, Any]],
    ) -> list[Dict[str, Any]]:
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
        materialized: list[Dict[str, Any]] = []
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
            transport_priority = self._media_transport_priority(candidate, media_kind)
            metadata = self._attachment_metadata(source)
            base_data = {
                "size_bytes": source.get("size_bytes"),
                "sha256": source.get("sha256") or metadata.get("sha256"),
                "extension": source.get("extension") or metadata.get("extension"),
                "transport": dict(source.get("transport") or metadata.get("transport") or {}),
                "metadata": metadata,
            }
            chosen: Dict[str, Any] | None = None
            for transport in transport_priority:
                if transport == "text" and str(source.get("content") or source.get("excerpt") or source.get("preview_text") or "").strip():
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

    def _build_combined_context(self, *parts: Optional[str]) -> Optional[str]:
        sections = [str(part).strip() for part in parts if str(part or "").strip()]
        if not sections:
            return None
        return "\n\n".join(sections)

    def _extract_request_parts(self, request: Any) -> list[Dict[str, Any]]:
        raw_parts = self._get_field(request, "content", None)
        if raw_parts is None:
            raw_parts = self._get_field(request, "content_parts", None)
        if raw_parts is None:
            return []
        if isinstance(raw_parts, list):
            return self._deserialize_content_parts(raw_parts)
        if isinstance(raw_parts, str):
            return self._deserialize_content_parts(raw_parts)
        return []

    def parse_request(self, request) -> Dict[str, Any]:
        config = self._get_field(request, "config")
        knowledge_base_id = self._get_config_field(config, "knowledge_base_id", None)
        if knowledge_base_id == "":
            knowledge_base_id = None

        metadata = self._get_field(request, "metadata", {}) or {}
        if not knowledge_base_id and isinstance(metadata, dict):
            knowledge_base_id = metadata.get("knowledge_base_id") or None
        session_id = self._get_field(request, "session_id")
        history = self._deserialize_history(metadata.get(CHAT_HISTORY_METADATA_KEY)) if isinstance(metadata, dict) else []
        if not history:
            session = self.sessions.get(session_id, {"history": []})
            history = list(session.get("history", []))
        content_parts = self._extract_request_parts(request)
        upload_bundle_ids = normalize_bundle_ids(metadata.get(UPLOAD_BUNDLE_IDS_METADATA_KEY)) if isinstance(metadata, dict) else []
        user_message = self._get_field(request, "message")
        if not user_message and content_parts:
            user_message = "".join(
                str(part.get("text") or "")
                for part in content_parts
                if str(part.get("type") or "").lower() == "text"
            )

        return {
            "session_id": session_id,
            "user_message": user_message,
            "temperature": self._get_config_field(config, "temperature", 0.7) or 0.7,
            "max_tokens": self._get_config_field(config, "max_tokens", 2000) or 2000,
            "requested_model": self._get_config_field(config, "model", None) or None,
            "use_rag": bool(self._get_config_field(config, "use_rag", False)),
            "knowledge_base_id": knowledge_base_id,
            "metadata": metadata,
            "tenant_id": self._get_field(request, "tenant_id", DEV_DEFAULT_TENANT_ID) or DEV_DEFAULT_TENANT_ID,
            "user_id": self._get_field(request, "user_id", None) or None,
            "history": history,
            "upload_bundle_ids": upload_bundle_ids,
            "content_parts": content_parts,
        }

    def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "metadata": {},
            }
        return self.sessions[session_id]

    def build_message_id(self, session_id: str, history_length: int) -> str:
        return f"msg_{session_id}_{history_length}"

    def append_history(
        self,
        history: List[Dict[str, Any]],
        user_message: str,
        assistant_message: str,
        user_parts: Optional[list[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        user_entry: Dict[str, Any] = {"role": "user", "content": user_message}
        if user_parts:
            user_entry["content"] = list(user_parts)
        return [
            *history,
            user_entry,
            {"role": "assistant", "content": assistant_message},
        ]

    def cache_history(self, session_id: str, history: List[Dict[str, Any]]) -> None:
        session = self.get_or_create_session(session_id)
        session["history"] = list(history)

    def build_error_response(self, session_id: str, error: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "message_id": "",
            "type": RESPONSE_TYPE_ERROR,
            "content": "",
            "error": error,
            "metadata": {},
        }

    async def stream_chat(self, request) -> AsyncIterator[Dict[str, Any]]:
        request_context = self.parse_request(request)
        history = request_context["history"]
        self.cache_history(request_context["session_id"], history)
        route_scene = self._determine_route_scene(request_context["use_rag"])
        governance_resolution: Optional[Dict[str, Any]] = None

        try:
            context = None
            citations: List[Dict[str, Any]] = []
            kb_name: Optional[str] = None
            upload_context: Optional[dict[str, Any]] = None

            if request_context["use_rag"]:
                context, citations, kb_name = await self.build_rag_context_and_citations(
                    tenant_id=request_context["tenant_id"],
                    user_id=request_context["user_id"],
                    knowledge_base_id=request_context["knowledge_base_id"],
                    query=request_context["user_message"],
                    top_k=3,
                )

                if not citations:
                    no_hit_metadata = self.build_response_metadata(
                        retrieval_status="no_hits",
                        use_rag=True,
                        knowledge_base_id=request_context["knowledge_base_id"],
                        knowledge_base_name=kb_name,
                        citations=[],
                        route_scene=route_scene,
                        feature_code=route_scene,
                        governance_config_version=(governance_resolution or {}).get("config_version", 1),
                    )
                    no_hit_message = "我没有在当前知识库中检索到足够相关的内容，请换个问法，或先补充文档后再提问。"
                    message_id = self.build_message_id(request_context["session_id"], len(history))
                    yield {
                        "session_id": request_context["session_id"],
                        "message_id": message_id,
                        "type": RESPONSE_TYPE_CONTENT,
                        "content": no_hit_message,
                        "metadata": no_hit_metadata,
                    }
                    yield {
                        "session_id": request_context["session_id"],
                        "message_id": message_id,
                        "type": RESPONSE_TYPE_COMPLETE,
                        "content": "",
                        "token_usage": {},
                        "metadata": no_hit_metadata,
                    }
                    self.cache_history(
                        request_context["session_id"],
                        self.append_history(history, request_context["user_message"], no_hit_message),
                    )
                    return

            if request_context["upload_bundle_ids"]:
                upload_context = get_attachment_bundle_store().build_prompt_context(
                    tenant_id=request_context["tenant_id"],
                    user_id=request_context["user_id"],
                    bundle_ids=request_context["upload_bundle_ids"],
                    query=request_context["user_message"],
                )
                context = self._build_combined_context(context, upload_context.get("context_text"))

            request_user_parts = self._build_request_user_parts(
                request_context["user_message"],
                request_context["content_parts"],
                upload_context,
            )
            unified_messages = self.build_unified_messages(
                user_message=request_context["user_message"],
                context=context,
                history=history,
                user_parts=request_user_parts,
            )
            request_profile = build_model_request_profile(unified_messages)
            required_modalities = set(request_profile.input_modalities)
            governance_resolution = await self.resolve_llm_candidates(
                tenant_id=request_context["tenant_id"],
                user_id=request_context["user_id"],
                knowledge_base_id=request_context["knowledge_base_id"],
                route_scene=route_scene,
                requested_model=request_context["requested_model"],
                required_modalities=required_modalities,
                request_profile=request_profile,
            )
            base_completion_metadata = self.build_response_metadata(
                retrieval_status="hit" if citations else "not_used",
                use_rag=request_context["use_rag"],
                knowledge_base_id=request_context["knowledge_base_id"],
                knowledge_base_name=kb_name,
                citations=citations,
                upload_bundle_ids=request_context["upload_bundle_ids"],
                uploaded_files=(upload_context or {}).get("files", []),
                uploaded_file_directory_tree=(upload_context or {}).get("directory_tree", []),
                request_content_parts=request_user_parts,
                required_input_modalities=sorted(required_modalities),
                required_output_modalities=request_profile.output_modalities,
                model_request_profile=request_profile.model_dump(),
            )

            last_error: Optional[str] = None
            for attempt_index, model_candidate in enumerate(governance_resolution["candidates"]):
                fallback_used = attempt_index > 0
                full_response = ""
                stream_started = False

                try:
                    constraint_errors = validate_message_constraints(
                        unified_messages,
                        (model_candidate.get("config") or {}).get("constraints") or {},
                    )
                    if constraint_errors:
                        raise RuntimeError("；".join(constraint_errors))
                    candidate_messages = self.build_unified_messages(
                        user_message=request_context["user_message"],
                        context=context,
                        history=history,
                        user_parts=self._materialize_request_user_parts_for_candidate(
                            model_candidate,
                            request_user_parts,
                            upload_context,
                        ),
                    )
                    async for llm_chunk in model_candidate["llm"].stream_chat(
                        UnifiedModelRequest.from_messages(
                            candidate_messages,
                            temperature=request_context["temperature"],
                            max_tokens=request_context["max_tokens"],
                        ),
                    ):
                        if llm_chunk.content:
                            stream_started = True
                            full_response += llm_chunk.content
                            yield {
                                "session_id": request_context["session_id"],
                                "message_id": self.build_message_id(request_context["session_id"], len(history)),
                                "type": RESPONSE_TYPE_CONTENT,
                                "content": llm_chunk.content,
                                "metadata": {},
                            }

                        if llm_chunk.finish_reason:
                            completion_metadata = self.build_completion_metadata(
                                base_metadata=base_completion_metadata,
                                model_row=model_candidate,
                                route_scene=route_scene,
                                config_version=governance_resolution["config_version"],
                                usage=llm_chunk.usage,
                                fallback_used=fallback_used,
                                fallback_reason=last_error,
                                requested_model=request_context["requested_model"],
                            )
                            yield {
                                "session_id": request_context["session_id"],
                                "message_id": self.build_message_id(request_context["session_id"], len(history)),
                                "type": RESPONSE_TYPE_COMPLETE,
                                "content": "",
                                "token_usage": llm_chunk.usage,
                                "metadata": completion_metadata,
                            }

                    self.cache_history(
                        request_context["session_id"],
                        self.append_history(history, request_context["user_message"], full_response, user_parts=request_user_parts),
                    )
                    return
                except Exception as exc:
                    if stream_started or attempt_index == len(governance_resolution["candidates"]) - 1:
                        raise
                    last_error = str(exc)
                    logger.warning(
                        "Model %s failed before streaming, falling back: %s",
                        model_candidate.get("display_name") or model_candidate.get("model_id"),
                        exc,
                    )

            raise RuntimeError(last_error or "No available model candidate")
        except Exception as exc:
            yield self.build_error_response(request_context["session_id"], str(exc))

    async def get_chat_history(self, request):
        session_id = self._get_field(request, "session_id")
        session = self.sessions.get(session_id, {"history": []})

        messages = []
        history = session["history"]

        for index, msg in enumerate(history):
            content = msg.get("content", "")
            content_parts = msg.get("content_parts")
            if isinstance(content, list):
                content_parts = content
            messages.append(
                {
                    "id": f"msg_{index}",
                    "role": msg.get("role", ""),
                    "content": content if isinstance(content, str) else "".join(
                        str(part.get("text") or "") for part in (content_parts or []) if isinstance(part, dict) and str(part.get("type") or "").lower() == "text"
                    ),
                    "content_parts": content_parts or [],
                    "timestamp": 0,
                    "token_usage": {},
                }
            )

        return {
            "messages": messages,
            "total": len(messages),
        }
