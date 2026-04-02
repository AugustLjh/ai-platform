from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
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
        elif key in {"request_payload", "result_payload"}:
            data[key] = parse_json_field(value, {})
    return data


class SubagentInvocationRepository:
    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def create_invocation(
        self,
        *,
        parent_run_id: str,
        parent_step_id: str | None,
        subagent_definition_id: str,
        publication_id: str | None = None,
        version_id: str | None = None,
        authorization_id: str | None = None,
        child_run_id: str | None = None,
        status: str = "pending",
        request_payload: Dict[str, Any] | None = None,
        result_payload: Dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> Dict[str, Any]:
        row = await self.db_pool.fetchrow(
            """
            INSERT INTO agent_subagent_invocations (
                parent_run_id,
                parent_step_id,
                subagent_definition_id,
                publication_id,
                version_id,
                authorization_id,
                child_run_id,
                status,
                request_payload,
                result_payload,
                error_message,
                started_at,
                completed_at
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8::varchar,
                $9,
                $10,
                $11,
                CASE WHEN $8::varchar = 'running' THEN now() ELSE NULL END,
                CASE WHEN $8::varchar IN ('completed', 'failed', 'cancelled') THEN now() ELSE NULL END
            )
            RETURNING *
            """,
            _serialize_uuid(parent_run_id),
            _serialize_uuid(parent_step_id),
            _serialize_uuid(subagent_definition_id),
            _serialize_uuid(publication_id),
            _serialize_uuid(version_id),
            _serialize_uuid(authorization_id),
            _serialize_uuid(child_run_id),
            status,
            encode_json(request_payload, {}),
            encode_json(result_payload, {}),
            error_message,
        )
        return _record_to_dict(row)

    async def update_invocation(
        self,
        invocation_id: str,
        *,
        status: str,
        child_run_id: str | None = None,
        request_payload: Dict[str, Any] | None = None,
        result_payload: Dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            UPDATE agent_subagent_invocations
            SET
                status = $2::varchar,
                child_run_id = COALESCE($3, child_run_id),
                request_payload = COALESCE($4, request_payload),
                result_payload = COALESCE($5, result_payload),
                error_message = $6,
                started_at = CASE
                    WHEN $2::varchar = 'running' AND started_at IS NULL THEN now()
                    ELSE started_at
                END,
                completed_at = CASE
                    WHEN $2::varchar IN ('completed', 'failed', 'cancelled') THEN now()
                    ELSE completed_at
                END
            WHERE id = $1
            RETURNING *
            """,
            _serialize_uuid(invocation_id),
            status,
            _serialize_uuid(child_run_id),
            encode_json(request_payload, {}) if request_payload is not None else None,
            encode_json(result_payload, {}) if result_payload is not None else None,
            error_message,
        )
        return _record_to_dict(row) if row else None
