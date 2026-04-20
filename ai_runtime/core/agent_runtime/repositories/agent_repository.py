from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from ai_runtime.core.agent_runtime.repositories.json_utils import encode_json, parse_json_field


def _serialize_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))


def _record_to_dict(record) -> Dict[str, Any]:
    data = dict(record)
    for key, value in list(data.items()):
        if isinstance(value, UUID):
            data[key] = str(value)
        elif isinstance(value, datetime):
            data[key] = value
        elif value is None:
            data[key] = None
        elif key in {"config", "metadata"}:
            data[key] = parse_json_field(value, {})
    return data


class AgentRepository:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def create_definition(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = """
            INSERT INTO agent_definitions (
                tenant_id, name, description, system_prompt, model, status,
                config, metadata, created_by, updated_by
            )
            VALUES ($1, $2, $3, $4, $5, COALESCE($6, 'active'), $7, $8, $9, $9)
            RETURNING *
        """
        row = await self.db_pool.fetchrow(
            query,
            _serialize_uuid(payload["tenant_id"]),
            payload["name"],
            payload.get("description"),
            payload.get("system_prompt", ""),
            payload.get("model"),
            payload.get("status", "active"),
            encode_json(payload.get("config"), {}),
            encode_json(payload.get("metadata"), {}),
            _serialize_uuid(payload.get("created_by")),
        )
        return _record_to_dict(row)

    async def update_definition(
        self,
        definition_id: str,
        tenant_id: str,
        payload: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        query = """
            UPDATE agent_definitions
            SET
                name = COALESCE($3, name),
                description = COALESCE($4, description),
                system_prompt = COALESCE($5, system_prompt),
                model = COALESCE($6, model),
                config = COALESCE($7, config),
                metadata = COALESCE($8, metadata),
                updated_by = COALESCE($9, updated_by)
            WHERE id = $1 AND tenant_id = $2 AND status <> 'archived'
            RETURNING *
        """
        row = await self.db_pool.fetchrow(
            query,
            _serialize_uuid(definition_id),
            _serialize_uuid(tenant_id),
            payload.get("name"),
            payload.get("description"),
            payload.get("system_prompt"),
            payload.get("model"),
            encode_json(payload.get("config"), {}) if "config" in payload else None,
            encode_json(payload.get("metadata"), {}) if "metadata" in payload else None,
            _serialize_uuid(payload.get("updated_by")),
        )
        return _record_to_dict(row) if row else None

    async def get_definition(self, definition_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        query = """
            SELECT *
            FROM agent_definitions
            WHERE id = $1
              AND ($2::uuid IS NULL OR tenant_id = $2)
        """
        row = await self.db_pool.fetchrow(query, _serialize_uuid(definition_id), _serialize_uuid(tenant_id))
        return _record_to_dict(row) if row else None

    async def list_definitions(self, tenant_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
        query = """
            SELECT *
            FROM agent_definitions
            WHERE tenant_id = $1
              AND ($2::boolean OR status <> 'archived')
            ORDER BY updated_at DESC
        """
        rows = await self.db_pool.fetch(query, _serialize_uuid(tenant_id), include_archived)
        return [_record_to_dict(row) for row in rows]

    async def archive_definition(self, definition_id: str, tenant_id: str, updated_by: Optional[str]) -> bool:
        query = """
            UPDATE agent_definitions
            SET status = 'archived', archived_at = now(), updated_by = $3
            WHERE id = $1 AND tenant_id = $2 AND status <> 'archived'
        """
        result = await self.db_pool.execute(
            query,
            _serialize_uuid(definition_id),
            _serialize_uuid(tenant_id),
            _serialize_uuid(updated_by),
        )
        return result.endswith("1")

    async def list_skill_bindings(self, definition_id: str) -> List[str]:
        rows = await self.db_pool.fetch(
            """
            SELECT skill_id
            FROM agent_skill_bindings
            WHERE agent_definition_id = $1
            ORDER BY created_at ASC
            """,
            _serialize_uuid(definition_id),
        )
        return [str(row["skill_id"]) for row in rows]

    async def list_mcp_bindings(self, definition_id: str) -> List[str]:
        rows = await self.db_pool.fetch(
            """
            SELECT server_id
            FROM agent_mcp_bindings
            WHERE agent_definition_id = $1
            ORDER BY created_at ASC
            """,
            _serialize_uuid(definition_id),
        )
        return [str(row["server_id"]) for row in rows]

    async def list_knowledge_bindings(self, definition_id: str) -> List[str]:
        rows = await self.db_pool.fetch(
            """
            SELECT knowledge_base_id
            FROM agent_knowledge_bindings
            WHERE agent_definition_id = $1
            ORDER BY created_at ASC
            """,
            _serialize_uuid(definition_id),
        )
        return [str(row["knowledge_base_id"]) for row in rows]

    async def list_accessible_knowledge_bindings(
        self,
        definition_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> List[str]:
        rows = await self.db_pool.fetch(
            """
            SELECT kb.id
            FROM agent_knowledge_bindings akb
            JOIN knowledge_bases kb ON kb.id = akb.knowledge_base_id
            WHERE akb.agent_definition_id = $1
              AND kb.tenant_id = $2
              AND (
                    kb.access_level = 'tenant'
                    OR (kb.access_level = 'user' AND kb.user_id = $3)
              )
            ORDER BY akb.created_at ASC
            """,
            _serialize_uuid(definition_id),
            _serialize_uuid(tenant_id),
            _serialize_uuid(user_id),
        )
        return [str(row["id"]) for row in rows]
