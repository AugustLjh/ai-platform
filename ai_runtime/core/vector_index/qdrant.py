"""
Qdrant-backed vector index.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient, models

from core.config import QdrantConfig

from .base import VectorIndex, VectorSearchHit

logger = logging.getLogger(__name__)


class QdrantVectorIndex(VectorIndex):
    """Qdrant implementation for chunk-level vector search."""

    def __init__(self, config: QdrantConfig):
        self.config = config
        self.client = AsyncQdrantClient(
            url=config.url,
            host=None if config.url else config.host,
            port=None if config.url else config.port,
            grpc_port=config.grpc_port,
            api_key=config.api_key,
            https=config.use_https,
            prefer_grpc=config.prefer_grpc,
            timeout=config.timeout,
        )
        self._collection_locks: dict[str, asyncio.Lock] = {}
        self._known_collections: set[str] = set()

    async def initialize(self) -> None:
        await self.client.get_collections()

    async def close(self) -> None:
        await self.client.close()

    def _collection_name(self, dimension: int) -> str:
        return f"{self.config.collection_prefix}_d{dimension}"

    def _point_id(self, chunk_id: str, document_id: str, chunk_index: int) -> str:
        return chunk_id or f"{document_id}:{chunk_index}"

    def _match_condition(self, key: str, value: Optional[str]) -> Optional[models.FieldCondition]:
        if value in (None, ""):
            return None
        return models.FieldCondition(
            key=key,
            match=models.MatchValue(value=value),
        )

    async def _list_managed_collections(self) -> list[str]:
        response = await self.client.get_collections()
        return [
            collection.name
            for collection in response.collections
            if collection.name.startswith(f"{self.config.collection_prefix}_d")
        ]

    async def _collection_exists(self, collection_name: str) -> bool:
        if collection_name in self._known_collections:
            return True
        existing = await self._list_managed_collections()
        self._known_collections.update(existing)
        return collection_name in self._known_collections

    async def _ensure_collection(self, dimension: int) -> str:
        collection_name = self._collection_name(dimension)
        if await self._collection_exists(collection_name):
            return collection_name

        lock = self._collection_locks.setdefault(collection_name, asyncio.Lock())
        async with lock:
            if await self._collection_exists(collection_name):
                return collection_name

            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            self._known_collections.add(collection_name)
            logger.info("Created Qdrant collection %s", collection_name)
        return collection_name

    def _build_access_filter(
        self,
        *,
        user_id: Optional[str],
        access_level: Optional[str],
    ) -> models.Filter:
        if access_level:
            return models.Filter(
                must=[
                    self._match_condition("access_level", access_level),
                ]
            )

        should_conditions: list[Any] = [
            self._match_condition("access_level", "tenant"),
        ]
        if user_id:
            should_conditions.append(
                models.Filter(
                    must=[
                        self._match_condition("access_level", "user"),
                        self._match_condition("user_id", user_id),
                    ]
                )
            )

        return models.Filter(should=[item for item in should_conditions if item is not None])

    def _build_filter(
        self,
        *,
        tenant_id: str,
        user_id: Optional[str],
        knowledge_base_id: Optional[str],
        access_level: Optional[str],
        source_type: Optional[str],
        embedding_model_key: Optional[str],
    ) -> models.Filter:
        must_conditions: list[Any] = [
            self._match_condition("tenant_id", tenant_id),
        ]

        for key, value in (
            ("knowledge_base_id", knowledge_base_id),
            ("source_type", source_type),
            ("embedding_model_key", embedding_model_key),
        ):
            condition = self._match_condition(key, value)
            if condition is not None:
                must_conditions.append(condition)

        must_conditions.append(
            self._build_access_filter(user_id=user_id, access_level=access_level)
        )
        return models.Filter(must=[item for item in must_conditions if item is not None])

    async def sync_document_chunks(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        document_id: str,
        user_id: Optional[str],
        access_level: str,
        source_type: Optional[str],
        embedding_model_key: Optional[str],
        embedding_dimension: Optional[int],
        chunks: list[dict[str, Any]],
    ) -> None:
        vector_chunks = [chunk for chunk in chunks if chunk.get("embedding")]
        if embedding_dimension is None:
            return

        await self.delete_document(document_id=document_id, embedding_dimension=None)
        if not vector_chunks:
            return

        collection_name = await self._ensure_collection(embedding_dimension)
        points = []
        for chunk in vector_chunks:
            chunk_index = int(chunk["chunk_index"])
            chunk_id = str(chunk.get("chunk_id") or "")
            payload = {
                "tenant_id": tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "user_id": user_id,
                "access_level": access_level,
                "source_type": source_type,
                "embedding_model_key": embedding_model_key,
                "chunk_index": chunk_index,
                "start_offset": int(chunk["start_offset"]),
                "end_offset": int(chunk["end_offset"]),
                "char_count": int(chunk["char_count"]),
            }
            points.append(
                models.PointStruct(
                    id=self._point_id(chunk_id, document_id, chunk_index),
                    vector=chunk["embedding"],
                    payload=payload,
                )
            )

        await self.client.upsert(
            collection_name=collection_name,
            wait=True,
            points=points,
        )

    async def delete_document(
        self,
        *,
        document_id: str,
        embedding_dimension: Optional[int] = None,
    ) -> None:
        collections = []
        if embedding_dimension is not None:
            collection_name = self._collection_name(embedding_dimension)
            if await self._collection_exists(collection_name):
                collections = [collection_name]
        else:
            collections = await self._list_managed_collections()

        if not collections:
            return

        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    self._match_condition("document_id", document_id),
                ]
            )
        )
        for collection_name in collections:
            await self.client.delete(
                collection_name=collection_name,
                wait=True,
                points_selector=selector,
            )

    async def search(
        self,
        *,
        tenant_id: str,
        query_embedding: list[float],
        user_id: Optional[str] = None,
        top_k: int = 5,
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[str] = None,
        source_type: Optional[str] = None,
        score_threshold: Optional[float] = None,
        embedding_model_key: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
    ) -> list[VectorSearchHit]:
        if embedding_dimension is None:
            return []

        collection_name = self._collection_name(embedding_dimension)
        if not await self._collection_exists(collection_name):
            return []

        response = await self.client.query_points(
            collection_name=collection_name,
            query=query_embedding,
            query_filter=self._build_filter(
                tenant_id=tenant_id,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                access_level=access_level,
                source_type=source_type,
                embedding_model_key=embedding_model_key,
            ),
            limit=max(top_k * 8, top_k),
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        grouped: OrderedDict[str, VectorSearchHit] = OrderedDict()
        for point in response.points:
            payload = dict(point.payload or {})
            document_id = str(payload.get("document_id") or "")
            if not document_id:
                continue

            current = grouped.get(document_id)
            score = float(point.score or 0.0)
            chunk_index = payload.get("chunk_index")
            if current is not None:
                current_chunk = current.chunk_index if current.chunk_index is not None else 10**9
                next_chunk = int(chunk_index) if chunk_index is not None else 10**9
                if score < current.score or (score == current.score and next_chunk >= current_chunk):
                    continue

            grouped[document_id] = VectorSearchHit(
                document_id=document_id,
                score=score,
                chunk_id=str(payload.get("chunk_id") or "") or None,
                chunk_index=int(chunk_index) if chunk_index is not None else None,
                start_offset=int(payload["start_offset"]) if payload.get("start_offset") is not None else None,
                end_offset=int(payload["end_offset"]) if payload.get("end_offset") is not None else None,
                char_count=int(payload["char_count"]) if payload.get("char_count") is not None else None,
                payload=payload,
            )

        hits = list(grouped.values())
        hits.sort(
            key=lambda item: (
                item.score,
                -(item.chunk_index or 0),
            ),
            reverse=True,
        )
        return hits[:top_k]
