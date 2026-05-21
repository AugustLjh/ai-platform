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
        elif key in {"summary", "payload", "metadata"}:
            data[key] = parse_json_field(value, {})
    return data


class EvaluationRepository:
    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    async def create_evaluation(
        self,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        row = await self.db_pool.fetchrow(
            """
            INSERT INTO agent_evaluations (
                tenant_id,
                evaluation_type,
                suite_name,
                status,
                actor_user_id,
                summary,
                payload,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            _serialize_uuid(payload.get("tenant_id")),
            str(payload.get("evaluation_type") or "").strip(),
            str(payload.get("suite_name") or "").strip(),
            str(payload.get("status") or "unknown").strip(),
            _serialize_uuid(payload.get("actor_user_id")),
            encode_json(payload.get("summary"), {}),
            encode_json(payload.get("payload"), {}),
            encode_json(payload.get("metadata"), {}),
        )
        return _record_to_dict(row)

    async def list_evaluations(
        self,
        *,
        tenant_id: str,
        evaluation_type: str | None = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT *
            FROM agent_evaluations
            WHERE tenant_id = $1
              AND ($2::varchar IS NULL OR evaluation_type = $2)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            _serialize_uuid(tenant_id),
            evaluation_type,
            limit,
        )
        return [_record_to_dict(row) for row in rows]
