from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.agent_runtime.repositories.json_utils import encode_json, parse_json_field


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
        elif key in {"arguments", "result"}:
            data[key] = parse_json_field(value, {})
    return data


class ToolCallRepository:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def create_tool_call(
        self,
        *,
        run_id: str,
        step_id: Optional[str],
        tool_name: str,
        tool_kind: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        row = await self.db_pool.fetchrow(
            """
            INSERT INTO agent_tool_calls (
                run_id, step_id, tool_name, tool_kind, status, arguments, started_at
            )
            VALUES ($1, $2, $3, $4, 'running', $5, now())
            RETURNING *
            """,
            _serialize_uuid(run_id),
            _serialize_uuid(step_id),
            tool_name,
            tool_kind,
            encode_json(arguments, {}),
        )
        return _record_to_dict(row)

    async def update_tool_call(
        self,
        tool_call_id: str,
        *,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            UPDATE agent_tool_calls
            SET
                status = $2::varchar,
                result = COALESCE($3, result),
                error_message = $4,
                completed_at = CASE
                    WHEN $2::varchar IN ('completed', 'failed', 'cancelled') THEN now()
                    ELSE completed_at
                END
            WHERE id = $1
            RETURNING *
            """,
            _serialize_uuid(tool_call_id),
            status,
            encode_json(result, {}) if result is not None else None,
            error_message,
        )
        return _record_to_dict(row) if row else None

    async def list_tool_calls(self, run_id: str) -> List[Dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT *
            FROM agent_tool_calls
            WHERE run_id = $1
            ORDER BY created_at ASC
            """,
            _serialize_uuid(run_id),
        )
        return [_record_to_dict(row) for row in rows]
