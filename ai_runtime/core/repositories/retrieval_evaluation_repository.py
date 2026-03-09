"""
Retrieval Evaluation Repository
"""
import json
from typing import Optional, List, Dict, Any
import asyncpg


class RetrievalEvaluationRepository:
    """检索评测数据访问层"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def list_test_sets(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT *
            FROM retrieval_test_sets
            WHERE tenant_id = $1
              AND knowledge_base_id = $2
              AND (user_id IS NULL OR user_id = $3)
            ORDER BY updated_at DESC, created_at DESC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, knowledge_base_id, user_id)
        return [self._row_to_dict(row) for row in rows]

    async def get_test_set(
        self,
        test_set_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT *
            FROM retrieval_test_sets
            WHERE id = $1
              AND tenant_id = $2
              AND knowledge_base_id = $3
              AND (user_id IS NULL OR user_id = $4)
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, test_set_id, tenant_id, knowledge_base_id, user_id)
        return self._row_to_dict(row) if row else None

    async def create_test_set(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        name: str,
        description: Optional[str],
        cases: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = """
            INSERT INTO retrieval_test_sets (
                tenant_id, knowledge_base_id, user_id, name, description, cases, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                tenant_id,
                knowledge_base_id,
                user_id,
                name,
                description,
                json.dumps(cases),
                json.dumps(metadata or {}),
            )
        return self._row_to_dict(row)

    async def update_test_set(
        self,
        test_set_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        cases: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        updates = []
        params: List[Any] = [test_set_id, tenant_id, knowledge_base_id, user_id]
        param_idx = 5

        if name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(name)
            param_idx += 1
        if description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(description)
            param_idx += 1
        if cases is not None:
            updates.append(f"cases = ${param_idx}")
            params.append(json.dumps(cases))
            param_idx += 1
        if metadata is not None:
            updates.append(f"metadata = ${param_idx}")
            params.append(json.dumps(metadata))
            param_idx += 1

        if not updates:
            return await self.get_test_set(test_set_id, tenant_id, knowledge_base_id, user_id)

        query = f"""
            UPDATE retrieval_test_sets
            SET {', '.join(updates)}
            WHERE id = $1
              AND tenant_id = $2
              AND knowledge_base_id = $3
              AND (user_id IS NULL OR user_id = $4)
            RETURNING *
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        return self._row_to_dict(row) if row else None

    async def delete_test_set(
        self,
        test_set_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        query = """
            DELETE FROM retrieval_test_sets
            WHERE id = $1
              AND tenant_id = $2
              AND knowledge_base_id = $3
              AND (user_id IS NULL OR user_id = $4)
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(query, test_set_id, tenant_id, knowledge_base_id, user_id)
        return int(result.split()[-1]) > 0

    async def list_runs(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT *
            FROM retrieval_test_runs
            WHERE tenant_id = $1
              AND knowledge_base_id = $2
              AND (user_id IS NULL OR user_id = $3)
            ORDER BY created_at DESC
            LIMIT $4
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, knowledge_base_id, user_id, limit)
        return [self._row_to_dict(row) for row in rows]

    async def get_run(
        self,
        run_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT *
            FROM retrieval_test_runs
            WHERE id = $1
              AND tenant_id = $2
              AND knowledge_base_id = $3
              AND (user_id IS NULL OR user_id = $4)
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, run_id, tenant_id, knowledge_base_id, user_id)
        return self._row_to_dict(row) if row else None

    async def create_run(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        config: Dict[str, Any],
        summary: Dict[str, Any],
        results: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        test_set_id: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = """
            INSERT INTO retrieval_test_runs (
                tenant_id, knowledge_base_id, test_set_id, user_id, name, config, summary, results, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                tenant_id,
                knowledge_base_id,
                test_set_id,
                user_id,
                name,
                json.dumps(config or {}),
                json.dumps(summary or {}),
                json.dumps(results or []),
                json.dumps(metadata or {}),
            )
        return self._row_to_dict(row)

    async def update_run(
        self,
        run_id: str,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        updates = []
        params: List[Any] = [run_id, tenant_id, knowledge_base_id, user_id]
        param_idx = 5

        if summary is not None:
            updates.append(f"summary = ${param_idx}")
            params.append(json.dumps(summary))
            param_idx += 1
        if results is not None:
            updates.append(f"results = ${param_idx}")
            params.append(json.dumps(results))
            param_idx += 1
        if metadata is not None:
            updates.append(f"metadata = ${param_idx}")
            params.append(json.dumps(metadata))
            param_idx += 1

        if not updates:
            return await self.get_run(run_id, tenant_id, knowledge_base_id, user_id)

        query = f"""
            UPDATE retrieval_test_runs
            SET {', '.join(updates)}
            WHERE id = $1
              AND tenant_id = $2
              AND knowledge_base_id = $3
              AND (user_id IS NULL OR user_id = $4)
            RETURNING *
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: asyncpg.Record) -> Dict[str, Any]:
        if row is None:
            return {}

        payload = dict(row)
        for key in ("cases", "config", "summary", "results", "metadata"):
            value = payload.get(key)
            if isinstance(value, str):
                payload[key] = json.loads(value)
        for key in ("id", "tenant_id", "knowledge_base_id", "user_id", "test_set_id"):
            if payload.get(key) is not None:
                payload[key] = str(payload[key])
        for key in ("created_at", "updated_at"):
            if payload.get(key) is not None:
                payload[key] = payload[key].isoformat()
        return payload
