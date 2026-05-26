from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict

from ai_runtime.core.agent_runtime.repositories.agent_repository import AgentRepository
from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from ai_runtime.core.database import get_db_manager
from ai_runtime.core.dependencies import get_container


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


async def _resolve_accessible_knowledge_base_ids(
    *,
    tenant_id: str,
    user_id: str | None,
    agent_definition_id: str | None,
    allowed_knowledge_base_ids: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    agent_definition_id = str(agent_definition_id or "").strip()
    if not agent_definition_id:
        return []
    repository = AgentRepository(get_db_manager().pool)
    mounted_ids = await repository.list_accessible_knowledge_bindings(
        definition_id=agent_definition_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    allowed = {str(item).strip() for item in (allowed_knowledge_base_ids or []) if str(item).strip()}
    if not allowed:
        return mounted_ids
    return [knowledge_base_id for knowledge_base_id in mounted_ids if knowledge_base_id in allowed]


class KnowledgeSearchTool(BaseTool):
    spec = ToolSpec(
        name="knowledge_search",
        description="Search the tenant knowledge base catalog and return matched documents with segments.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "knowledge_base_id": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        kind="knowledge",
    )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")

        knowledge_base_id = str(arguments.get("knowledge_base_id") or "").strip() or None
        top_k = _clamp_int(arguments.get("top_k"), default=5, minimum=1, maximum=10)
        container = get_container()
        document_service = container.document_service
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
            allowed_knowledge_base_ids=context.allowed_knowledge_base_ids,
        )
        if not mounted_knowledge_base_ids:
            raise PermissionError("agent has no mounted knowledge bases available to the current user")

        if knowledge_base_id:
            if knowledge_base_id not in mounted_knowledge_base_ids:
                raise PermissionError(f"knowledge base {knowledge_base_id} is not mounted on this agent or access is denied")
            search_targets = [knowledge_base_id]
        else:
            search_targets = mounted_knowledge_base_ids

        merged: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        for target_kb_id in search_targets:
            results = await document_service.search_documents(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                query=query,
                top_k=top_k,
                knowledge_base_id=target_kb_id,
            )
            for document, score in results:
                current = merged.get(document.id)
                if current is not None and current[1] >= float(score):
                    continue
                merged[document.id] = (document, float(score))

        ranked_results = sorted(
            merged.values(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]

        items = []
        for document, score in ranked_results:
            matched_segments = await document_service.get_matched_segments(
                document=document,
                query=query,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                max_segments=2,
            )
            items.append(
                {
                    "document_id": document.id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "title": document.title,
                    "source": document.source,
                    "source_type": document.source_type.value,
                    "score": float(score),
                    "indexed": bool(document.indexed),
                    "matched_segments": matched_segments,
                }
            )

        return {
            "query": query,
            "knowledge_base_id": knowledge_base_id,
            "total": len(items),
            "results": items,
        }


class KnowledgeFetchDocumentTool(BaseTool):
    spec = ToolSpec(
        name="knowledge_fetch_document",
        description="Fetch a single knowledge-base document and a preview of its content.",
        input_schema={
            "type": "object",
            "required": ["document_id"],
            "properties": {
                "document_id": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 20000},
            },
        },
        kind="knowledge",
    )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        document_id = str(arguments.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required")

        max_chars = _clamp_int(arguments.get("max_chars"), default=4000, minimum=100, maximum=20000)
        container = get_container()
        document_service = container.document_service
        document_repository = container.document_repository
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
            allowed_knowledge_base_ids=context.allowed_knowledge_base_ids,
        )
        if not mounted_knowledge_base_ids:
            raise PermissionError("agent has no mounted knowledge bases available to the current user")

        document = await document_repository.get_document(document_id, context.tenant_id, context.user_id)
        if document is None:
            raise ValueError(f"document {document_id} not found")
        if document.knowledge_base_id not in mounted_knowledge_base_ids:
            raise PermissionError(f"document {document_id} is not in an agent-mounted knowledge base")

        preview = await document_service.get_document_preview(
            document_id=document_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            max_chars=max_chars,
        )

        return {
            "document": {
                "id": document.id,
                "knowledge_base_id": document.knowledge_base_id,
                "title": document.title,
                "source": document.source,
                "source_type": document.source_type.value,
                "indexed": bool(document.indexed),
                "index_status": document.index_status,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
                "metadata": document.metadata,
            },
            "preview": preview,
        }


class KnowledgeFetchSegmentsTool(BaseTool):
    spec = ToolSpec(
        name="knowledge_fetch_segments",
        description="Fetch indexed segments for a knowledge-base document.",
        input_schema={
            "type": "object",
            "required": ["document_id"],
            "properties": {
                "document_id": {"type": "string"},
                "max_segments": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
        kind="knowledge",
    )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        document_id = str(arguments.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id is required")

        max_segments = _clamp_int(arguments.get("max_segments"), default=50, minimum=1, maximum=1000)
        container = get_container()
        document_repository = container.document_repository
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
            allowed_knowledge_base_ids=context.allowed_knowledge_base_ids,
        )
        if not mounted_knowledge_base_ids:
            raise PermissionError("agent has no mounted knowledge bases available to the current user")

        document = await document_repository.get_document(document_id, context.tenant_id, context.user_id)
        if document is None:
            raise ValueError(f"document {document_id} not found")
        if document.knowledge_base_id not in mounted_knowledge_base_ids:
            raise PermissionError(f"document {document_id} is not in an agent-mounted knowledge base")

        segments = await container.document_service.get_document_segments(
            document_id=document_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            max_segments=max_segments,
        )
        if segments is None:
            raise ValueError(f"document {document_id} not found")
        return segments


class KnowledgeToolProvider:
    def __init__(self) -> None:
        self._tools = {
            "knowledge_search": KnowledgeSearchTool(),
            "knowledge_fetch_document": KnowledgeFetchDocumentTool(),
            "knowledge_fetch_segments": KnowledgeFetchSegmentsTool(),
        }

    async def _has_accessible_knowledge_tools(self, context: ToolLookupContext | None) -> bool:
        if context is None:
            return False
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
            allowed_knowledge_base_ids=context.allowed_knowledge_base_ids,
        )
        return len(mounted_knowledge_base_ids) > 0

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        tool = self._tools.get(name)
        if tool is None:
            return None
        if not await self._has_accessible_knowledge_tools(context):
            return None
        return tool

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = await self.get(name, context=context)
        if tool is None:
            return None
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": tool.spec.metadata,
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        if not await self._has_accessible_knowledge_tools(context):
            return []
        return [
            {
                "name": tool.spec.name,
                "description": tool.spec.description,
                "input_schema": tool.spec.input_schema,
                "kind": tool.spec.kind,
                "metadata": tool.spec.metadata,
            }
            for tool in self._tools.values()
        ]


def register_knowledge_tools(registry) -> None:
    registry.register_provider(KnowledgeToolProvider(), name="knowledge")
