from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
import json
import logging
import os
import sys
from uuid import UUID

# Add proto path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../proto"))

from core.agent import AgentExecutor
from core.agent.tools import get_default_tools
from core.dependencies import get_container
from core.llm import DeepseekLLM, LocalLLM, OpenAILLM
from core.prompt import PromptBuilder
from core.rag import RAGPipeline, Retriever, SimpleVectorStore
from core.rag.retriever import DatabaseVectorStore
from core.stream import CostTrackingMiddleware, StreamPipeline, TokenCounterMiddleware

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PRICE_PER_1K = 0.0015
DEFAULT_OUTPUT_PRICE_PER_1K = 0.002


class ChatServiceImpl:
    """Chat service implementation"""

    def __init__(self):
        self.prompt_builder = PromptBuilder()
        self.vector_store = SimpleVectorStore()
        self.retriever = Retriever(self.vector_store)
        self.rag_pipeline = RAGPipeline(self.retriever)
        self.default_llm = DeepseekLLM(
            model=os.getenv("DEFAULT_CHAT_MODEL", "deepseek-chat"),
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
        )
        self._llm_cache: Dict[str, Any] = {}
        self.stream_pipeline = StreamPipeline([
            TokenCounterMiddleware(),
            CostTrackingMiddleware(),
        ])
        self.sessions = {}

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

        for index, (doc, score) in enumerate(results, 1):
            matched_segments = await doc_service.get_matched_segments(
                document=doc,
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,
                max_segments=2,
            )
            snippets = [segment.get("content", "") for segment in matched_segments if segment.get("content")]
            snippet_text = "\n---\n".join(snippets) if snippets else (doc.content or "")[:800]

            context_parts.append(f"[Document {index}] title={doc.title} score={score:.4f}")
            if doc.source:
                context_parts.append(f"source={doc.source}")
            context_parts.append(snippet_text)
            context_parts.append("")

            citations.append(
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "source": doc.source,
                    "knowledge_base_id": doc.knowledge_base_id,
                    "score": round(float(score), 4),
                    "matched_segments": matched_segments,
                }
            )

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
        """Build a RAG pipeline with database-backed retriever when available."""
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
        """Support both dict and attribute-style request objects."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_config_field(self, config, key, default=None):
        """Support both dict and attribute-style config objects."""
        if config is None:
            return default
        if isinstance(config, dict):
            return config.get(key, default)
        return getattr(config, key, default)

    def _determine_route_scene(self, use_rag: bool, use_agent: bool) -> str:
        if use_agent:
            return "agent_chat"
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

    async def stream_chat(self, request) -> AsyncIterator:
        """
        Stream chat handler

        Args:
            request: ChatRequest protobuf message

        Yields:
            ChatResponse protobuf messages
        """
        session_id = self._get_field(request, "session_id")
        user_message = self._get_field(request, "message")
        config = self._get_field(request, "config")
        use_rag = bool(self._get_config_field(config, "use_rag", False))
        use_agent = bool(self._get_config_field(config, "use_agent", False))
        temperature = self._get_config_field(config, "temperature", 0.7) or 0.7
        max_tokens = self._get_config_field(config, "max_tokens", 2000) or 2000
        requested_model = self._get_config_field(config, "model", None) or None
        knowledge_base_id = self._get_config_field(config, "knowledge_base_id", None)
        if knowledge_base_id == "":
            knowledge_base_id = None
        metadata = self._get_field(request, "metadata", {}) or {}
        if not knowledge_base_id and isinstance(metadata, dict):
            knowledge_base_id = metadata.get("knowledge_base_id") or None
        tenant_id = self._get_field(request, "tenant_id", "default-tenant") or "default-tenant"
        user_id = self._get_field(request, "user_id", None) or None
        route_scene = self._determine_route_scene(use_rag, use_agent)

        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "metadata": {},
            }

        session = self.sessions[session_id]

        try:
            context = None
            citations: List[Dict[str, Any]] = []
            kb_name: Optional[str] = None
            governance_resolution = await self._resolve_llm_candidates(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                route_scene=route_scene,
                requested_model=requested_model,
            )

            if use_rag:
                context, citations, kb_name = await self._build_rag_context_and_citations(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    knowledge_base_id=knowledge_base_id,
                    query=user_message,
                    top_k=3,
                )

                if not citations:
                    no_hit_metadata = self._build_response_metadata(
                        retrieval_status="no_hits",
                        use_rag=True,
                        knowledge_base_id=knowledge_base_id,
                        knowledge_base_name=kb_name,
                        citations=[],
                        route_scene=route_scene,
                        feature_code=route_scene,
                        governance_config_version=governance_resolution["config_version"],
                    )
                    no_hit_message = "我没有在当前知识库中检索到足够相关的内容，请换个问法，或先补充文档后再提问。"
                    yield {
                        "session_id": session_id,
                        "message_id": f"msg_{session_id}_{len(session['history'])}",
                        "type": 1,
                        "content": no_hit_message,
                        "metadata": no_hit_metadata,
                    }
                    yield {
                        "session_id": session_id,
                        "message_id": f"msg_{session_id}_{len(session['history'])}",
                        "type": 4,
                        "content": "",
                        "token_usage": {},
                        "metadata": no_hit_metadata,
                    }
                    session["history"].append({"role": "user", "content": user_message})
                    session["history"].append({"role": "assistant", "content": no_hit_message})
                    return

            base_completion_metadata = self._build_response_metadata(
                retrieval_status="hit" if citations else "not_used",
                use_rag=use_rag,
                knowledge_base_id=knowledge_base_id,
                knowledge_base_name=kb_name,
                citations=citations,
            )

            messages = self.prompt_builder.build(
                system_prompt=(
                    "You are a helpful AI assistant. "
                    "When retrieval context is provided, answer strictly from that context. "
                    "If the context is insufficient, say so clearly instead of making up facts."
                ),
                user_message=user_message,
                context=context,
                history=session["history"],
            )

            last_error: Optional[str] = None
            for attempt_index, model_candidate in enumerate(governance_resolution["candidates"]):
                fallback_used = attempt_index > 0
                full_response = ""
                stream_started = False

                try:
                    if use_agent:
                        agent = AgentExecutor(model_candidate["llm"], tools=get_default_tools())
                        stream_source = agent.stream_execute(
                            messages,
                            use_tools=True,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )

                        async for agent_response in stream_source:
                            response_type = self._map_response_type(agent_response.response_type)
                            if response_type == 1 and agent_response.content:
                                stream_started = True
                                full_response += agent_response.content

                            if not agent_response.finish_reason:
                                yield {
                                    "session_id": session_id,
                                    "message_id": f"msg_{session_id}_{len(session['history'])}",
                                    "type": response_type,
                                    "content": agent_response.content,
                                    "metadata": {},
                                }

                            if agent_response.finish_reason:
                                completion_metadata = self._build_completion_metadata(
                                    base_metadata=base_completion_metadata,
                                    model_row=model_candidate,
                                    route_scene=route_scene,
                                    config_version=governance_resolution["config_version"],
                                    usage=agent_response.usage,
                                    fallback_used=fallback_used,
                                    fallback_reason=last_error,
                                    requested_model=requested_model,
                                )
                                yield {
                                    "session_id": session_id,
                                    "message_id": f"msg_{session_id}_{len(session['history'])}",
                                    "type": 4,
                                    "content": "",
                                    "token_usage": agent_response.usage,
                                    "metadata": completion_metadata,
                                }
                    else:
                        async for llm_chunk in model_candidate["llm"].stream_chat(
                            messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        ):
                            if llm_chunk.content:
                                stream_started = True
                                full_response += llm_chunk.content
                                yield {
                                    "session_id": session_id,
                                    "message_id": f"msg_{session_id}_{len(session['history'])}",
                                    "type": 1,
                                    "content": llm_chunk.content,
                                    "metadata": {},
                                }

                            if llm_chunk.finish_reason:
                                completion_metadata = self._build_completion_metadata(
                                    base_metadata=base_completion_metadata,
                                    model_row=model_candidate,
                                    route_scene=route_scene,
                                    config_version=governance_resolution["config_version"],
                                    usage=llm_chunk.usage,
                                    fallback_used=fallback_used,
                                    fallback_reason=last_error,
                                    requested_model=requested_model,
                                )
                                yield {
                                    "session_id": session_id,
                                    "message_id": f"msg_{session_id}_{len(session['history'])}",
                                    "type": 4,
                                    "content": "",
                                    "token_usage": llm_chunk.usage,
                                    "metadata": completion_metadata,
                                }

                    session["history"].append({"role": "user", "content": user_message})
                    session["history"].append({"role": "assistant", "content": full_response})
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
            yield {
                "session_id": session_id,
                "message_id": "",
                "type": 5,
                "content": "",
                "error": str(exc),
                "metadata": {},
            }

    def _map_response_type(self, agent_type: str) -> int:
        """Map agent response type to protobuf enum"""
        mapping = {
            "content": 1,
            "thinking": 2,
            "tool_call": 3,
            "complete": 4,
            "error": 5,
        }
        return mapping.get(agent_type, 1)

    async def get_chat_history(self, request):
        """Get chat history handler"""
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
