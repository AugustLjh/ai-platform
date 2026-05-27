from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ai_runtime.graphs.chat import helpers as chat_helpers
from ai_runtime.graphs.chat.message_adapter import unified_to_langchain

logger = logging.getLogger(__name__)


class AgentLLMService:
    async def resolve_candidates(
        self,
        *,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        route_scene: str,
        requested_model: Optional[str],
    ) -> Dict[str, Any]:
        return await chat_helpers.resolve_llm_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene=route_scene,
            requested_model=requested_model,
        )

    async def chat_with_candidates(
        self,
        resolution: Dict[str, Any],
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        last_error: Exception | None = None
        lc_messages = unified_to_langchain(messages)

        for candidate in resolution.get("candidates", []):
            try:
                response = await candidate["llm"].ainvoke(lc_messages, **kwargs)
                return _content_text(response), self._build_candidate_info(candidate, resolution)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Agent LLM candidate failed: route_scene=%s model=%s error=%s",
                    resolution.get("route_scene"),
                    candidate.get("display_name") or candidate.get("model_id"),
                    exc,
                )

        if last_error is not None:
            raise RuntimeError(str(last_error)) from last_error
        raise RuntimeError("No LLM candidates available for agent runtime")

    def _build_candidate_info(
        self,
        candidate: Dict[str, Any],
        resolution: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "route_scene": resolution.get("route_scene"),
            "requested_model": resolution.get("requested_model"),
            "config_version": resolution.get("config_version"),
            "resolved_model_id": candidate.get("id"),
            "resolved_model_name": candidate.get("display_name"),
            "resolved_model_provider": candidate.get("provider"),
            "resolved_provider_model_id": candidate.get("model_id"),
            "model_source": candidate.get("source"),
            "endpoint_protocol": (candidate.get("config") or {}).get("endpoint_protocol"),
        }


def _content_text(message: Any) -> str:
    """Extract printable text from an ``AIMessage`` returned by ``ainvoke``.

    LangChain may return ``content`` as either a plain string or a list of
    content-part dicts (responses-API style). Both flatten to text here.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")
