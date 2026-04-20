"""
Vector index abstractions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class VectorSearchHit:
    """Single vector search hit."""
    document_id: str
    score: float
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    char_count: Optional[int] = None
    payload: dict[str, Any] = field(default_factory=dict)


class VectorIndex(ABC):
    """Abstract vector index backend."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize backend resources."""

    @abstractmethod
    async def close(self) -> None:
        """Close backend resources."""

    @abstractmethod
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
        """Upsert current document chunks into the vector backend."""

    @abstractmethod
    async def delete_document(
        self,
        *,
        document_id: str,
        embedding_dimension: Optional[int] = None,
    ) -> None:
        """Delete one document from the vector backend."""

    @abstractmethod
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
        """Search documents by embedding."""
