"""Citation-aware Qdrant retriever.

Wraps :class:`langchain_qdrant.QdrantVectorStore` and rewrites the
returned :class:`langchain_core.documents.Document` instances so each one
carries citation metadata that mirrors what
``ai_runtime.core.chat.service.ChatRuntimeService._build_rag_context_and_citations``
emits today.

Each returned ``Document.metadata`` is hydrated with at least:

* ``citation_id`` – stable id ``"{document_id}:{chunk_id or segment_index or idx}"``;
* ``document_id``;
* ``chunk_id``;
* ``document_rank`` – 1-based rank within the result set;
* ``segment_index``;
* ``section_title``;
* ``score``;
* ``kb_id`` – knowledge base id;
* ``citation_label``.

The retriever sorts documents by score descending.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

logger = logging.getLogger(__name__)


def _hydrate_citation_metadata(
    *,
    doc: Document,
    score: float,
    document_rank: int,
    citation_index: int,
) -> Document:
    """Return a new :class:`Document` with the citation metadata fields
    layered onto ``doc.metadata``.

    The original metadata is preserved; only missing keys are filled in
    using payload conventions used by ``core/vector_index/qdrant.py``.
    """
    metadata = dict(doc.metadata or {})

    document_id = (
        metadata.get("document_id")
        or metadata.get("id")
        or metadata.get("doc_id")
        or ""
    )
    chunk_id = metadata.get("chunk_id")
    segment_index = (
        metadata.get("segment_index")
        if metadata.get("segment_index") is not None
        else metadata.get("chunk_index")
    )
    section_title = metadata.get("section_title") or metadata.get("title")
    citation_label = metadata.get("citation_label")
    if not citation_label:
        if section_title and segment_index is not None:
            citation_label = f"{section_title} · 段落 {segment_index}"
        elif section_title:
            citation_label = section_title
        else:
            citation_label = "全文"

    kb_id = (
        metadata.get("kb_id")
        or metadata.get("knowledge_base_id")
    )

    citation_id = metadata.get("citation_id") or (
        f"{document_id}:{chunk_id or segment_index or citation_index}"
    )

    hydrated = {
        **metadata,
        "citation_id": citation_id,
        "document_id": document_id,
        "chunk_id": chunk_id,
        "document_rank": document_rank,
        "segment_index": segment_index,
        "section_title": section_title,
        "score": round(float(score), 4),
        "kb_id": kb_id,
        "citation_label": citation_label,
    }

    return Document(page_content=doc.page_content, metadata=hydrated)


class CitationAwareRetriever(BaseRetriever):
    """Retriever that runs a Qdrant similarity search and hydrates
    citation metadata on each returned document.

    The retriever is intentionally tolerant: it accepts any object that
    exposes ``similarity_search_with_score`` and/or
    ``asimilarity_search_with_score`` so it can be unit-tested with a
    plain ``Mock`` without depending on a live Qdrant cluster.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: Any = Field(...)
    """Underlying vector store (``QdrantVectorStore`` or mock)."""

    k: int = 5
    """Number of candidates to fetch."""

    score_threshold: Optional[float] = None
    """Optional Qdrant ``score_threshold`` passed straight through."""

    filter: Any = None
    """Optional ``qdrant_client.models.Filter`` passed to the underlying
    similarity search."""

    extra_search_kwargs: dict[str, Any] = Field(default_factory=dict)
    """Forwarded as ``**kwargs`` to the underlying search call."""

    # ------------------------------------------------------------------ helpers
    def _build_kwargs(self, k: Optional[int]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"k": int(k or self.k)}
        if self.filter is not None:
            kwargs["filter"] = self.filter
        if self.score_threshold is not None:
            kwargs["score_threshold"] = float(self.score_threshold)
        if self.extra_search_kwargs:
            kwargs.update(self.extra_search_kwargs)
        return kwargs

    def _post_process(
        self,
        results: Sequence[tuple[Document, float]],
    ) -> List[Document]:
        # Sort by score desc; ties preserve original order.
        sorted_results = sorted(
            enumerate(results),
            key=lambda item: (-float(item[1][1] or 0.0), item[0]),
        )
        hydrated: List[Document] = []
        for rank, (_, (doc, score)) in enumerate(sorted_results, start=1):
            hydrated.append(
                _hydrate_citation_metadata(
                    doc=doc,
                    score=float(score or 0.0),
                    document_rank=rank,
                    citation_index=rank,
                )
            )
        return hydrated

    # ------------------------------------------------------------------ BaseRetriever
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        sync_fn = getattr(self.vector_store, "similarity_search_with_score", None)
        if sync_fn is None:
            raise NotImplementedError(
                "Underlying vector store has no 'similarity_search_with_score'"
            )
        results = sync_fn(query, **self._build_kwargs(self.k))
        return self._post_process(results)

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
    ) -> List[Document]:
        async_fn = getattr(self.vector_store, "asimilarity_search_with_score", None)
        if async_fn is not None:
            results = await async_fn(query, **self._build_kwargs(self.k))
            return self._post_process(results)

        # Fallback: run the sync method in a worker thread.
        from langchain_core.runnables.config import run_in_executor

        sync_fn = getattr(self.vector_store, "similarity_search_with_score", None)
        if sync_fn is None:
            raise NotImplementedError(
                "Underlying vector store has neither sync nor async similarity_search_with_score"
            )
        results = await run_in_executor(
            None,
            lambda: sync_fn(query, **self._build_kwargs(self.k)),
        )
        return self._post_process(results)


__all__ = ["CitationAwareRetriever", "_hydrate_citation_metadata"]
