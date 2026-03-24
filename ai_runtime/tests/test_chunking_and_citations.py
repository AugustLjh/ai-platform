import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.chat.service import ChatRuntimeService
from core.models.knowledge_base import Document, SourceType
from core.services.document_service import DocumentService


def build_document_service() -> DocumentService:
    return DocumentService(
        repository=Mock(),
        kb_repository=Mock(),
        embedding_service=Mock(),
        vector_index=Mock(),
    )


def test_structured_chunking_prefers_headings_and_paragraphs():
    service = build_document_service()
    content = (
        "# 简介\n\n"
        "RAG 是 Retrieval-Augmented Generation。\n\n"
        "## 使用方式\n\n"
        "第一段说明系统如何检索知识库。\n\n"
        "第二段说明命中后如何生成引用。"
    )

    segments = service._segment_text_with_offsets(
        "RAG 手册",
        content,
        {
            "indexing_method": "structured",
            "chunk_size": 200,
            "chunk_overlap": 20,
        },
    )

    assert len(segments) == 3
    assert segments[0]["section_title"] == "简介"
    assert segments[0]["segment_type"] == "paragraph"
    assert segments[0]["citation_label"] == "简介 · 段落 1"
    assert segments[1]["section_title"] == "使用方式"
    assert segments[2]["section_title"] == "使用方式"


def test_structured_chunking_falls_back_to_fixed_chunks_for_long_paragraphs():
    service = build_document_service()
    long_paragraph = "这是一个很长的段落。" * 30
    content = f"## 长段落\n\n{long_paragraph}"

    segments = service._segment_text_with_offsets(
        "RAG 手册",
        content,
        {
            "indexing_method": "structured",
            "chunk_size": 60,
            "chunk_overlap": 10,
        },
    )

    assert len(segments) > 1
    assert all(segment["section_title"] == "长段落" for segment in segments)
    assert all(segment["segment_type"] == "chunk" for segment in segments)
    assert all("长段落 · 分块 1" in segment["citation_label"] for segment in segments)


def test_rag_citations_are_emitted_per_matched_chunk():
    service = ChatRuntimeService()
    document = Document(
        id="doc-1",
        tenant_id="tenant-1",
        title="RAG 手册",
        content="RAG 文档内容",
        knowledge_base_id="kb-1",
        source="manual.md",
        source_type=SourceType.MANUAL,
    )

    fake_doc_service = SimpleNamespace(
        search_documents=AsyncMock(return_value=[(document, 0.93)]),
        get_matched_segments=AsyncMock(
            return_value=[
                {
                    "chunk_id": "chunk-1",
                    "segment_index": 1,
                    "start_offset": 0,
                    "end_offset": 18,
                    "char_count": 18,
                    "content": "第一段命中内容",
                    "segment_type": "paragraph",
                    "section_title": "简介",
                    "citation_label": "简介 · 段落 1",
                    "match_score": 2.0,
                },
                {
                    "chunk_id": "chunk-2",
                    "segment_index": 2,
                    "start_offset": 19,
                    "end_offset": 42,
                    "char_count": 23,
                    "content": "第二段命中内容",
                    "segment_type": "paragraph",
                    "section_title": "简介",
                    "citation_label": "简介 · 段落 2",
                    "match_score": 1.0,
                },
            ]
        ),
    )

    with patch("core.chat.service.get_container", return_value=SimpleNamespace(document_service=fake_doc_service)):
        service._get_knowledge_base_name = AsyncMock(return_value="测试知识库")
        context, citations, kb_name = asyncio.run(
            service._build_rag_context_and_citations(
                tenant_id="tenant-1",
                user_id="user-1",
                knowledge_base_id="kb-1",
                query="什么是 RAG",
                top_k=3,
            )
        )

    assert kb_name == "测试知识库"
    assert len(citations) == 2
    assert citations[0]["chunk_id"] == "chunk-1"
    assert citations[1]["chunk_id"] == "chunk-2"
    assert citations[0]["citation_label"] == "简介 · 段落 1"
    assert citations[1]["citation_label"] == "简介 · 段落 2"
    assert len(citations[0]["matched_segments"]) == 1
    assert len(citations[1]["matched_segments"]) == 1
    assert "[Citation 1]" in context
    assert "[Citation 2]" in context
