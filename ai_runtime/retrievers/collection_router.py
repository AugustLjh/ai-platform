"""Qdrant collection router.

Selects the correct ``documents_<dim>`` collection based on the embedding
dimension. Mirrors the collection-management logic from
``ai_runtime/core/vector_index/qdrant.py`` (which uses a
``{prefix}_d{dim}`` naming scheme).
"""
from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import AsyncQdrantClient, QdrantClient, models

logger = logging.getLogger(__name__)

_DEFAULT_PREFIX = "documents"


class QdrantCollectionRouter:
    """Picks (and optionally creates) the right Qdrant collection for a given
    embedding dimension.

    The naming convention is ``{prefix}_{dim}`` — e.g. ``documents_1536``.
    """

    def __init__(
        self,
        *,
        client: Optional[QdrantClient] = None,
        async_client: Optional[AsyncQdrantClient] = None,
        prefix: str = _DEFAULT_PREFIX,
        auto_create: bool = True,
    ) -> None:
        if client is None and async_client is None:
            raise ValueError("At least one of client / async_client must be provided")
        self._client = client
        self._async_client = async_client
        self.prefix = prefix
        self.auto_create = auto_create
        self._known: set[str] = set()

    def collection_name(self, dimension: int) -> str:
        return f"{self.prefix}_{dimension}"

    # ------------------------------------------------------------------ sync
    def ensure_collection(self, dimension: int) -> str:
        name = self.collection_name(dimension)
        if name in self._known:
            return name
        if self._client is None:
            raise RuntimeError("Sync client not available; use async_ensure_collection")
        existing = {
            c.name for c in self._client.get_collections().collections
        }
        if name in existing:
            self._known.add(name)
            return name
        if not self.auto_create:
            raise ValueError(f"Collection {name!r} does not exist and auto_create=False")
        self._client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        self._known.add(name)
        logger.info("Created Qdrant collection %s", name)
        return name

    # ------------------------------------------------------------------ async
    async def async_ensure_collection(self, dimension: int) -> str:
        name = self.collection_name(dimension)
        if name in self._known:
            return name
        if self._async_client is None:
            raise RuntimeError("Async client not available; use ensure_collection")
        existing_resp = await self._async_client.get_collections()
        existing = {c.name for c in existing_resp.collections}
        if name in existing:
            self._known.add(name)
            return name
        if not self.auto_create:
            raise ValueError(f"Collection {name!r} does not exist and auto_create=False")
        await self._async_client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        self._known.add(name)
        logger.info("Created Qdrant collection %s", name)
        return name


__all__ = ["QdrantCollectionRouter"]
