from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


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
    return data


class RunRepository:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def create_run(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = """
            INSERT INTO agent_runs (
                agent_definition_id, tenant_id, user_id, session_id, status,
                input, plan, context, metadata
            )
            VALUES ($1, $2, $3, $4, COALESCE($5, 'queued'), $6, $7, $8, $9)
            RETURNING *
        """
        row = await self.db_pool.fetchrow(
            query,
            _serialize_uuid(payload["agent_definition_id"]),
            _serialize_uuid(payload["tenant_id"]),
            _serialize_uuid(payload.get("user_id")),
            _serialize_uuid(payload.get("session_id")),
            payload.get("status", "queued"),
            dict(payload.get("input", {})),
            dict(payload.get("plan", {})),
            dict(payload.get("context", {})),
            dict(payload.get("metadata", {})),
        )
        return _record_to_dict(row)

    async def get_run(self, run_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            SELECT *
            FROM agent_runs
            WHERE id = $1
              AND ($2::uuid IS NULL OR tenant_id = $2)
            """,
            _serialize_uuid(run_id),
            _serialize_uuid(tenant_id),
        )
        return _record_to_dict(row) if row else None

    async def list_runs(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT *
            FROM agent_runs
            WHERE tenant_id = $1
              AND ($2::uuid IS NULL OR user_id = $2)
            ORDER BY created_at DESC
            LIMIT $3 OFFSET $4
            """,
            _serialize_uuid(tenant_id),
            _serialize_uuid(user_id),
            limit,
            offset,
        )
        return [_record_to_dict(row) for row in rows]

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        *,
        plan: Optional[Dict[str, Any]] = None,
        final_output: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            UPDATE agent_runs
            SET
                status = $2,
                plan = COALESCE($3, plan),
                final_output = COALESCE($4, final_output),
                error_message = $5,
                metadata = COALESCE($6, metadata),
                started_at = CASE
                    WHEN $2 = 'running' AND started_at IS NULL THEN now()
                    ELSE started_at
                END,
                finished_at = CASE
                    WHEN $2 IN ('completed', 'failed') THEN now()
                    ELSE finished_at
                END,
                cancelled_at = CASE
                    WHEN $2 = 'cancelled' THEN now()
                    ELSE cancelled_at
                END
            WHERE id = $1
            RETURNING *
            """,
            _serialize_uuid(run_id),
            status,
            dict(plan) if plan is not None else None,
            final_output,
            error_message,
            dict(metadata) if metadata is not None else None,
        )
        return _record_to_dict(row) if row else None

    async def patch_run_input(self, run_id: str, input_patch: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            UPDATE agent_runs
            SET input = COALESCE(input, '{}'::jsonb) || $2::jsonb
            WHERE id = $1
            RETURNING *
            """,
            _serialize_uuid(run_id),
            dict(input_patch),
        )
        return _record_to_dict(row) if row else None

    async def get_next_step_index(self, run_id: str) -> int:
        value = await self.db_pool.fetchval(
            "SELECT COALESCE(MAX(step_index), 0) + 1 FROM agent_run_steps WHERE run_id = $1",
            _serialize_uuid(run_id),
        )
        return int(value or 1)

    async def create_step(
        self,
        run_id: str,
        *,
        step_index: int,
        kind: str,
        title: Optional[str],
        status: str,
        input_payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = await self.db_pool.fetchrow(
            """
            INSERT INTO agent_run_steps (
                run_id, step_index, kind, title, status, input, metadata, started_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, CASE WHEN $5 = 'running' THEN now() ELSE NULL END)
            RETURNING *
            """,
            _serialize_uuid(run_id),
            step_index,
            kind,
            title,
            status,
            dict(input_payload or {}),
            dict(metadata or {}),
        )
        return _record_to_dict(row)

    async def update_step(
        self,
        step_id: str,
        *,
        status: Optional[str] = None,
        output_payload: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        row = await self.db_pool.fetchrow(
            """
            UPDATE agent_run_steps
            SET
                status = COALESCE($2, status),
                output = COALESCE($3, output),
                error_message = $4,
                metadata = COALESCE($5, metadata),
                started_at = CASE
                    WHEN COALESCE($2, status) = 'running' AND started_at IS NULL THEN now()
                    ELSE started_at
                END,
                completed_at = CASE
                    WHEN COALESCE($2, status) IN ('completed', 'failed', 'cancelled') THEN now()
                    ELSE completed_at
                END
            WHERE id = $1
            RETURNING *
            """,
            _serialize_uuid(step_id),
            status,
            dict(output_payload) if output_payload is not None else None,
            error_message,
            dict(metadata) if metadata is not None else None,
        )
        return _record_to_dict(row) if row else None

    async def append_event(self, run_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1::text))",
                    run_id,
                )
                sequence = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_run_events WHERE run_id = $1",
                    _serialize_uuid(run_id),
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO agent_run_events (run_id, sequence, event_type, payload)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                    """,
                    _serialize_uuid(run_id),
                    int(sequence or 1),
                    event_type,
                    dict(payload or {}),
                )
        return _record_to_dict(row)

    async def list_events(self, run_id: str, after_sequence: int = 0, limit: int = 500) -> List[Dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT *
            FROM agent_run_events
            WHERE run_id = $1
              AND sequence > $2
            ORDER BY sequence ASC
            LIMIT $3
            """,
            _serialize_uuid(run_id),
            after_sequence,
            limit,
        )
        return [_record_to_dict(row) for row in rows]
