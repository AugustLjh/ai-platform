from __future__ import annotations

import logging
import os
from collections import OrderedDict
from datetime import datetime
from typing import Any, Sequence

from core.agent_runtime.repositories.run_repository import RunRepository
from core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from core.agent_runtime.tools.providers.knowledge import _resolve_accessible_knowledge_base_ids
from core.database import get_db_manager
from core.dependencies import get_container
from core.models.knowledge_base import SourceType

logger = logging.getLogger(__name__)

DEFAULT_ENGINEERING_TOOL_NAMES = (
    "project_list_context",
    "project_search_context",
    "project_read_context_item",
)


def _parse_csv(value: str | None, default: Sequence[str]) -> list[str]:
    if value is None or not value.strip():
        return [item for item in default]
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


class ProjectContextTool(BaseTool):
    def _run_repository(self) -> RunRepository:
        return RunRepository(get_db_manager().pool)

    async def _resolve_run(self, context: ToolContext) -> dict[str, Any]:
        run = await self._run_repository().get_run(context.run_id, context.tenant_id)
        if run is None:
            raise ValueError(f"run {context.run_id} not found")
        return run

    async def _resolve_session_id(self, context: ToolContext) -> str:
        run = await self._resolve_run(context)
        session_id = str(run.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("current run is not linked to a conversation session")
        return session_id

    async def _list_session_messages(
        self,
        context: ToolContext,
        *,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
        message_id: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        session_id = await self._resolve_session_id(context)
        db_pool = get_db_manager().pool

        if message_id:
            rows = await db_pool.fetch(
                """
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE session_id = $1::uuid
                  AND id = $2::uuid
                ORDER BY created_at ASC
                """,
                session_id,
                message_id,
            )
            return session_id, [self._message_row_to_dict(row) for row in rows]

        if query:
            rows = await db_pool.fetch(
                """
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE session_id = $1::uuid
                  AND content ILIKE $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
                """,
                session_id,
                f"%{query}%",
                limit,
                offset,
            )
            items = [self._message_row_to_dict(row) for row in rows]
            items.reverse()
            return session_id, items

        rows = await db_pool.fetch(
            """
            SELECT id, role, content, created_at, metadata
            FROM messages
            WHERE session_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            session_id,
            limit,
            offset,
        )
        items = [self._message_row_to_dict(row) for row in rows]
        items.reverse()
        return session_id, items

    def _message_row_to_dict(self, row: Any) -> dict[str, Any]:
        created_at = row["created_at"]
        return {
            "item_type": "message",
            "id": str(row["id"]),
            "role": str(row["role"] or ""),
            "content": str(row["content"] or ""),
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
            "metadata": _parse_metadata(row["metadata"]),
        }

    async def _resolve_uploaded_documents(
        self,
        context: ToolContext,
        *,
        title_query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
        )
        if not mounted_knowledge_base_ids:
            return []

        container = get_container()
        document_service = container.document_service
        merged: OrderedDict[str, dict[str, Any]] = OrderedDict()

        for knowledge_base_id in mounted_knowledge_base_ids:
            documents, _total = await document_service.list_documents(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                knowledge_base_id=knowledge_base_id,
                source_type=SourceType.FILE,
                page=1,
                page_size=max(limit, 20),
            )
            for document in documents:
                if title_query:
                    title = str(document.title or "")
                    source = str(document.source or "")
                    query_text = title_query.lower()
                    if query_text not in title.lower() and query_text not in source.lower():
                        continue
                merged[document.id] = {
                    "item_type": "document",
                    "id": document.id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "title": document.title,
                    "source": document.source,
                    "source_type": document.source_type.value if document.source_type else "file",
                    "indexed": bool(document.indexed),
                    "index_status": document.index_status,
                    "updated_at": document.updated_at.isoformat() if document.updated_at else None,
                    "metadata": document.metadata or {},
                }

        items = sorted(
            merged.values(),
            key=lambda item: item.get("updated_at") or "",
            reverse=True,
        )
        return items[:limit]

    async def _resolve_document_preview(
        self,
        context: ToolContext,
        *,
        document_id: str,
        max_chars: int,
    ) -> dict[str, Any]:
        mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            agent_definition_id=context.agent_definition_id,
        )
        if not mounted_knowledge_base_ids:
            raise PermissionError("agent has no mounted knowledge bases available to the current user")

        container = get_container()
        document_repository = container.document_repository
        document_service = container.document_service

        document = await document_repository.get_document(document_id, context.tenant_id, context.user_id)
        if document is None:
            raise ValueError(f"document {document_id} not found")
        if document.knowledge_base_id not in mounted_knowledge_base_ids:
            raise PermissionError(f"document {document_id} is not in an agent-mounted knowledge base")
        if document.source_type != SourceType.FILE:
            raise PermissionError(f"document {document_id} is not a user-uploaded file")

        preview = await document_service.get_document_preview(
            document_id=document_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            max_chars=max_chars,
        )

        return {
            "item_type": "document",
            "id": document.id,
            "knowledge_base_id": document.knowledge_base_id,
            "title": document.title,
            "source": document.source,
            "source_type": document.source_type.value if document.source_type else "file",
            "indexed": bool(document.indexed),
            "index_status": document.index_status,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "metadata": document.metadata or {},
            "preview": preview,
        }


class ProjectListContextTool(ProjectContextTool):
    spec = ToolSpec(
        name="project_list_context",
        description="List the current session conversation history and user-uploaded documents mounted on this agent. Do not use this for local filesystem access.",
        input_schema={
            "type": "object",
            "properties": {
                "message_limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "document_limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "document_query": {"type": "string"},
            },
        },
        kind="engineering",
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        message_limit = _clamp_int(arguments.get("message_limit"), default=10, minimum=1, maximum=100)
        document_limit = _clamp_int(arguments.get("document_limit"), default=20, minimum=1, maximum=100)
        document_query = str(arguments.get("document_query") or "").strip() or None

        session_id, messages = await self._list_session_messages(
            context,
            limit=message_limit,
            offset=0,
        )
        documents = await self._resolve_uploaded_documents(
            context,
            title_query=document_query,
            limit=document_limit,
        )
        return {
            "session_id": session_id,
            "message_count": len(messages),
            "document_count": len(documents),
            "messages": messages,
            "uploaded_documents": documents,
        }


class ProjectSearchContextTool(ProjectContextTool):
    spec = ToolSpec(
        name="project_search_context",
        description="Search the current conversation history and mounted user-uploaded documents. Prefer this over any local file search.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "target": {"type": "string", "enum": ["all", "messages", "documents"]},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
        kind="engineering",
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")

        target = str(arguments.get("target") or "all").strip().lower()
        if target not in {"all", "messages", "documents"}:
            target = "all"
        max_results = _clamp_int(arguments.get("max_results"), default=10, minimum=1, maximum=50)

        session_id = await self._resolve_session_id(context)
        results: list[dict[str, Any]] = []

        if target in {"all", "messages"}:
            _session_id, messages = await self._list_session_messages(
                context,
                query=query,
                limit=max_results,
                offset=0,
            )
            for item in messages:
                results.append(
                    {
                        "item_type": "message",
                        "id": item["id"],
                        "title": item["role"],
                        "content_preview": item["content"][:400],
                        "created_at": item["created_at"],
                        "metadata": item["metadata"],
                    }
                )

        if target in {"all", "documents"} and len(results) < max_results:
            mounted_knowledge_base_ids = await _resolve_accessible_knowledge_base_ids(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                agent_definition_id=context.agent_definition_id,
            )
            container = get_container()
            document_service = container.document_service
            merged_documents: OrderedDict[str, dict[str, Any]] = OrderedDict()
            per_kb_limit = max(2, min(max_results, 5))

            for knowledge_base_id in mounted_knowledge_base_ids:
                document_hits = await document_service.search_documents(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    query=query,
                    top_k=per_kb_limit,
                    knowledge_base_id=knowledge_base_id,
                    source_type=SourceType.FILE,
                )
                for document, score in document_hits:
                    merged_documents[document.id] = {
                        "item_type": "document",
                        "id": document.id,
                        "title": document.title,
                        "knowledge_base_id": document.knowledge_base_id,
                        "source": document.source,
                        "score": float(score),
                        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
                    }

            ranked_documents = sorted(
                merged_documents.values(),
                key=lambda item: float(item.get("score") or 0),
                reverse=True,
            )
            for item in ranked_documents:
                results.append(item)
                if len(results) >= max_results:
                    break

        return {
            "session_id": session_id,
            "query": query,
            "target": target,
            "results": results[:max_results],
            "truncated": len(results) > max_results,
        }


class ProjectReadContextItemTool(ProjectContextTool):
    spec = ToolSpec(
        name="project_read_context_item",
        description="Read a full conversation message or a mounted user-uploaded document preview by id.",
        input_schema={
            "type": "object",
            "required": ["item_type", "item_id"],
            "properties": {
                "item_type": {"type": "string", "enum": ["message", "document"]},
                "item_id": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 20000},
            },
        },
        kind="engineering",
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        item_type = str(arguments.get("item_type") or "").strip().lower()
        item_id = str(arguments.get("item_id") or "").strip()
        if item_type not in {"message", "document"}:
            raise ValueError("item_type must be one of: message, document")
        if not item_id:
            raise ValueError("item_id is required")

        max_chars = _clamp_int(arguments.get("max_chars"), default=4000, minimum=100, maximum=20000)

        if item_type == "message":
            session_id, messages = await self._list_session_messages(
                context,
                message_id=item_id,
                limit=1,
                offset=0,
            )
            if not messages:
                raise ValueError(f"message {item_id} not found in the current session")
            message = messages[0]
            content = message["content"]
            truncated = len(content) > max_chars
            return {
                "session_id": session_id,
                "item": {
                    **message,
                    "content": content[:max_chars],
                    "truncated": truncated,
                },
            }

        return {
            "item": await self._resolve_document_preview(
                context,
                document_id=item_id,
                max_chars=max_chars,
            )
        }


ENGINEERING_TOOL_TYPES = {
    "project_list_context": ProjectListContextTool,
    "project_search_context": ProjectSearchContextTool,
    "project_read_context_item": ProjectReadContextItemTool,
}


class EngineeringToolProvider:
    def __init__(self, *, enabled_tool_names: Sequence[str]) -> None:
        self.enabled_tool_names = [name for name in enabled_tool_names if name in ENGINEERING_TOOL_TYPES]
        self._metadata = {
            "provider": "engineering",
            "source": "conversation_history_and_uploaded_documents",
        }

    @classmethod
    def from_env(cls) -> "EngineeringToolProvider":
        enabled_tool_names = _parse_csv(os.getenv("AGENT_ENGINEERING_TOOLS"), DEFAULT_ENGINEERING_TOOL_NAMES)
        return cls(enabled_tool_names=enabled_tool_names)

    def _build_tool(self, name: str) -> BaseTool | None:
        tool_type = ENGINEERING_TOOL_TYPES.get(name)
        if tool_type is None or name not in self.enabled_tool_names:
            return None
        return tool_type()

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        return self._build_tool(name)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = self._build_tool(name)
        if tool is None:
            return None
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": {
                **tool.spec.metadata,
                **self._metadata,
            },
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        items = []
        for name in self.enabled_tool_names:
            spec = await self.get_spec(name, context=context)
            if spec is not None:
                items.append(spec)
        return items
