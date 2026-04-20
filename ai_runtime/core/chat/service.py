from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
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
from ai_runtime.core.dependencies import DEV_DEFAULT_TENANT_ID, get_container
from ai_runtime.core.llm import DeepseekLLM, JinaLLM, LocalLLM, OpenAILLM
from ai_runtime.core.rag import RAGPipeline, Retriever, SimpleVectorStore
from ai_runtime.core.rag.retriever import DatabaseVectorStore
from ai_runtime.core.uploads.bundle_store import UPLOAD_BUNDLE_IDS_METADATA_KEY, get_attachment_bundle_store, normalize_bundle_ids

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PRICE_PER_1K = 0.0015
DEFAULT_OUTPUT_PRICE_PER_1K = 0.002
CHAT_HISTORY_METADATA_KEY = "chat_history"


class ChatRuntimeService:
    """Dedicated runtime for chat-mode requests."""

    def __init__(self, sessions: Optional[Dict[str, Dict[str, Any]]] = None):
        self.prompt_builder = ChatPromptBuilder()
        self.vector_store = SimpleVectorStore()
        self.retriever = Retriever(self.vector_store)
        self.rag_pipeline = RAGPipeline(self.retriever)
        self.default_llm = DeepseekLLM(
            model=os.getenv("DEFAULT_CHAT_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
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
            return dict(value)
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                return decoded if isinstance(decoded, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
        return {}

    def _deserialize_history(self, value: Any) -> List[Dict[str, str]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return []

        if not isinstance(value, list):
            return []

        history: List[Dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if not role or content is None:
                continue
            history.append(
                {
                    "role": str(role),
                    "content": str(content),
                }
            )
        return history

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
        config = dict(model_row.get("config") or {})
        llm_kwargs = dict(config)
        if api_base:
            llm_kwargs["api_base"] = api_base

        if provider == "openai":
            llm = OpenAILLM(model=model_id, api_key=api_key, **llm_kwargs)
        elif provider == "deepseek":
            llm = DeepseekLLM(model=model_id, api_key=api_key, **llm_kwargs)
        elif provider == "jina":
            llm = JinaLLM(model=model_id, api_key=api_key, **llm_kwargs)
        elif provider in {"local", "mock"}:
            llm = LocalLLM(model=model_id, **llm_kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

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
            return {
                **model_row,
                "llm": self._create_llm_instance(model_row),
                "source": source,
            }
        except Exception as exc:
            logger.warning(
                "Failed to initialize model candidate %s: %s",
                model_row.get("display_name") or model_row.get("model_id"),
                exc,
            )
            return None

    async def _resolve_llm_candidates(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        route_scene: str,
        requested_model: Optional[str],
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
        fallback_selector = route.get("fallback_model_id") if route_enabled else None

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

        return {
            "route_scene": route_scene,
            "requested_model": requested_model,
            "config_version": self._safe_int(governance_settings.get("config_version"), 1),
            "fallback_selector": fallback_selector,
            "candidates": candidates,
        }

    async def resolve_llm_candidates(
        self,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        route_scene: str,
        requested_model: Optional[str],
    ) -> Dict[str, Any]:
        return await self._resolve_llm_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene=route_scene,
            requested_model=requested_model,
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
    ) -> List[Dict[str, str]]:
        return self.prompt_builder.build_messages(
            user_message=user_message,
            context=context,
            history=history,
        )

    def _build_combined_context(self, *parts: Optional[str]) -> Optional[str]:
        sections = [str(part).strip() for part in parts if str(part or "").strip()]
        if not sections:
            return None
        return "\n\n".join(sections)

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
        upload_bundle_ids = normalize_bundle_ids(metadata.get(UPLOAD_BUNDLE_IDS_METADATA_KEY)) if isinstance(metadata, dict) else []

        return {
            "session_id": session_id,
            "user_message": self._get_field(request, "message"),
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
    ) -> List[Dict[str, str]]:
        return [
            *history,
            {"role": "user", "content": user_message},
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

        try:
            context = None
            citations: List[Dict[str, Any]] = []
            kb_name: Optional[str] = None
            upload_context: Optional[dict[str, Any]] = None
            governance_resolution = await self.resolve_llm_candidates(
                tenant_id=request_context["tenant_id"],
                user_id=request_context["user_id"],
                knowledge_base_id=request_context["knowledge_base_id"],
                route_scene=route_scene,
                requested_model=request_context["requested_model"],
            )

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
                        governance_config_version=governance_resolution["config_version"],
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

            base_completion_metadata = self.build_response_metadata(
                retrieval_status="hit" if citations else "not_used",
                use_rag=request_context["use_rag"],
                knowledge_base_id=request_context["knowledge_base_id"],
                knowledge_base_name=kb_name,
                citations=citations,
                upload_bundle_ids=request_context["upload_bundle_ids"],
                uploaded_files=(upload_context or {}).get("files", []),
                uploaded_file_directory_tree=(upload_context or {}).get("directory_tree", []),
            )

            messages = self.build_messages(
                user_message=request_context["user_message"],
                context=context,
                history=history,
            )

            last_error: Optional[str] = None
            for attempt_index, model_candidate in enumerate(governance_resolution["candidates"]):
                fallback_used = attempt_index > 0
                full_response = ""
                stream_started = False

                try:
                    async for llm_chunk in model_candidate["llm"].stream_chat(
                        messages,
                        temperature=request_context["temperature"],
                        max_tokens=request_context["max_tokens"],
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
                        self.append_history(history, request_context["user_message"], full_response),
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
            messages.append(
                {
                    "id": f"msg_{index}",
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                    "timestamp": 0,
                    "token_usage": {},
                }
            )

        return {
            "messages": messages,
            "total": len(messages),
        }
