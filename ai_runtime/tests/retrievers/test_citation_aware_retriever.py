"""Tests for the citation-aware Qdrant retriever.

We avoid spinning up a real Qdrant cluster by passing a mock vector
store that exposes ``asimilarity_search_with_score`` /
``similarity_search_with_score``.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from ai_runtime.retrievers import CitationAwareRetriever


def _doc(content: str, metadata: dict) -> Document:
    return Document(page_content=content, metadata=metadata)


def test_retriever_hydrates_citation_metadata_async():
    mock_store = MagicMock()
    mock_store.asimilarity_search_with_score = AsyncMock(
        return_value=[
            (
                _doc(
                    "第一段命中内容",
                    {
                        "document_id": "doc-1",
                        "chunk_id": "chunk-1",
                        "section_title": "简介",
                        "title": "RAG 手册",
                        "source": "manual.md",
                        "knowledge_base_id": "kb-1",
                        "segment_index": 1,
                    },
                ),
                0.93,
            ),
            (
                _doc(
                    "第二段命中内容",
                    {
                        "document_id": "doc-1",
                        "chunk_id": "chunk-2",
                        "section_title": "简介",
                        "title": "RAG 手册",
                        "source": "manual.md",
                        "knowledge_base_id": "kb-1",
                        "segment_index": 2,
                    },
                ),
                0.85,
            ),
        ]
    )

    retriever = CitationAwareRetriever(vector_store=mock_store, k=3)
    docs = asyncio.run(retriever.ainvoke("什么是 RAG"))

    assert len(docs) == 2
    # Sorted by score descending (already sorted in this case)
    assert docs[0].metadata["score"] == 0.93
    assert docs[1].metadata["score"] == 0.85

    # Each doc must carry the contract keys
    expected_keys = {
        "citation_id",
        "document_id",
        "chunk_id",
        "document_rank",
        "segment_index",
        "section_title",
        "score",
        "kb_id",
        "citation_label",
    }
    for doc in docs:
        assert expected_keys.issubset(doc.metadata.keys())

    assert docs[0].metadata["citation_id"] == "doc-1:chunk-1"
    assert docs[0].metadata["document_rank"] == 1
    assert docs[0].metadata["kb_id"] == "kb-1"
    assert docs[0].metadata["citation_label"] == "简介 · 段落 1"
    assert docs[1].metadata["document_rank"] == 2

    mock_store.asimilarity_search_with_score.assert_awaited_once()
    args, kwargs = mock_store.asimilarity_search_with_score.call_args
    assert args[0] == "什么是 RAG"
    assert kwargs.get("k") == 3


def test_retriever_sorts_by_score_descending():
    mock_store = MagicMock()
    mock_store.asimilarity_search_with_score = AsyncMock(
        return_value=[
            (_doc("low", {"document_id": "d1", "chunk_id": "c1"}), 0.4),
            (_doc("high", {"document_id": "d2", "chunk_id": "c2"}), 0.95),
            (_doc("mid", {"document_id": "d3", "chunk_id": "c3"}), 0.7),
        ]
    )

    retriever = CitationAwareRetriever(vector_store=mock_store)
    docs = asyncio.run(retriever.ainvoke("query"))

    contents = [d.page_content for d in docs]
    assert contents == ["high", "mid", "low"]
    assert [d.metadata["document_rank"] for d in docs] == [1, 2, 3]


def test_retriever_falls_back_to_segment_index_for_citation_id():
    mock_store = MagicMock()
    mock_store.asimilarity_search_with_score = AsyncMock(
        return_value=[
            (
                _doc("body", {"document_id": "doc-x", "segment_index": 7}),
                0.5,
            ),
        ]
    )
    retriever = CitationAwareRetriever(vector_store=mock_store)
    docs = asyncio.run(retriever.ainvoke("q"))
    assert docs[0].metadata["citation_id"] == "doc-x:7"


def test_retriever_uses_sync_path_when_no_async_method():
    mock_store = MagicMock()
    mock_store.asimilarity_search_with_score = None  # not callable
    mock_store.similarity_search_with_score = MagicMock(
        return_value=[
            (_doc("hello", {"document_id": "d1", "chunk_id": "c1"}), 0.9),
        ]
    )
    # Remove asimilarity_search_with_score so getattr returns None
    del mock_store.asimilarity_search_with_score

    retriever = CitationAwareRetriever(vector_store=mock_store, k=2)
    docs = retriever.invoke("query")
    assert len(docs) == 1
    assert docs[0].metadata["citation_id"] == "d1:c1"
    mock_store.similarity_search_with_score.assert_called_once()


def test_retriever_passes_filter_and_threshold():
    mock_store = MagicMock()
    mock_store.asimilarity_search_with_score = AsyncMock(return_value=[])
    sentinel_filter = object()

    retriever = CitationAwareRetriever(
        vector_store=mock_store,
        k=4,
        score_threshold=0.6,
        filter=sentinel_filter,
    )
    asyncio.run(retriever.ainvoke("q"))

    _, kwargs = mock_store.asimilarity_search_with_score.call_args
    assert kwargs["k"] == 4
    assert kwargs["filter"] is sentinel_filter
    assert kwargs["score_threshold"] == 0.6
