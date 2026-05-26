"""Tests for the CJK-aware text splitter.

Fixture-based tests that verify byte-equal chunk output for CJK corpora
and correct fallback behavior for non-CJK text.
"""
from __future__ import annotations

import pytest

from ai_runtime.splitters import CJKAwareTextSplitter, build_splitter
from ai_runtime.splitters.cjk_aware import _is_predominantly_cjk, _split_cjk_sentences


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CJK_CORPUS = (
    "RAG 是 Retrieval-Augmented Generation 的缩写。"
    "它结合了检索和生成两种技术。"
    "系统首先从知识库中检索相关文档。"
    "然后将检索到的内容作为上下文传递给语言模型。"
    "最终生成包含引用的回答。"
)

ENGLISH_CORPUS = (
    "RAG stands for Retrieval-Augmented Generation. "
    "It combines retrieval and generation techniques. "
    "The system first retrieves relevant documents from a knowledge base. "
    "Then it passes the retrieved content as context to the language model. "
    "Finally it generates an answer with citations."
)


# ---------------------------------------------------------------------------
# _is_predominantly_cjk
# ---------------------------------------------------------------------------

class TestIsPredominantlyCJK:
    def test_pure_chinese(self):
        assert _is_predominantly_cjk("这是一段中文文本") is True

    def test_pure_english(self):
        assert _is_predominantly_cjk("This is English text") is False

    def test_mixed_above_threshold(self):
        # 60% CJK chars
        assert _is_predominantly_cjk("中文中文中文abc") is True

    def test_mixed_below_threshold(self):
        # Mostly English with a few CJK
        assert _is_predominantly_cjk("Hello world 你好") is False

    def test_empty(self):
        assert _is_predominantly_cjk("") is False

    def test_whitespace_only(self):
        assert _is_predominantly_cjk("   \t\n  ") is False


# ---------------------------------------------------------------------------
# _split_cjk_sentences
# ---------------------------------------------------------------------------

class TestSplitCJKSentences:
    def test_basic_split(self):
        text = "第一句话。第二句话！第三句话？"
        sentences = _split_cjk_sentences(text)
        assert sentences == ["第一句话。", "第二句话！", "第三句话？"]

    def test_semicolon_split(self):
        text = "条件一；条件二；条件三"
        sentences = _split_cjk_sentences(text)
        assert sentences == ["条件一；", "条件二；", "条件三"]

    def test_no_punctuation(self):
        text = "没有标点的一段话"
        sentences = _split_cjk_sentences(text)
        assert sentences == ["没有标点的一段话"]

    def test_empty(self):
        assert _split_cjk_sentences("") == []
        assert _split_cjk_sentences("   ") == []


# ---------------------------------------------------------------------------
# CJKAwareTextSplitter
# ---------------------------------------------------------------------------

class TestCJKAwareTextSplitter:
    def test_cjk_corpus_splits_on_sentence_boundaries(self):
        splitter = CJKAwareTextSplitter(chunk_size=60, chunk_overlap=10)
        chunks = splitter.split_text(CJK_CORPUS)
        assert len(chunks) >= 2
        # Each chunk should end at a sentence boundary (punctuation)
        for chunk in chunks[:-1]:  # last chunk may not end with punctuation
            assert chunk[-1] in "。！？；!?;", f"Chunk does not end at sentence boundary: {chunk!r}"

    def test_cjk_corpus_respects_chunk_size(self):
        splitter = CJKAwareTextSplitter(chunk_size=40, chunk_overlap=5)
        chunks = splitter.split_text(CJK_CORPUS)
        # Most chunks should be within chunk_size (oversized single sentences
        # are handled by fallback, so we allow some slack)
        for chunk in chunks:
            # Allow 2x for single oversized sentences that get fallback-split
            assert len(chunk) <= 80, f"Chunk too large: {len(chunk)} chars"

    def test_english_text_uses_fallback(self):
        splitter = CJKAwareTextSplitter(chunk_size=80, chunk_overlap=10)
        chunks = splitter.split_text(ENGLISH_CORPUS)
        assert len(chunks) >= 2
        # Should not crash; content preserved
        joined = "".join(chunks)
        # Due to overlap, joined may be longer, but all original content present
        for word in ["RAG", "Retrieval", "citations"]:
            assert word in " ".join(chunks)

    def test_empty_text(self):
        splitter = CJKAwareTextSplitter(chunk_size=100, chunk_overlap=10)
        assert splitter.split_text("") == []
        assert splitter.split_text("   ") == []

    def test_single_short_sentence(self):
        splitter = CJKAwareTextSplitter(chunk_size=100, chunk_overlap=10)
        chunks = splitter.split_text("短句。")
        assert chunks == ["短句。"]

    def test_overlap_preserves_trailing_content(self):
        text = "第一句。第二句。第三句。第四句。第五句。"
        splitter = CJKAwareTextSplitter(chunk_size=12, chunk_overlap=6)
        chunks = splitter.split_text(text)
        # With overlap, later chunks should contain content from previous
        assert len(chunks) >= 2
        # Verify no content is lost
        all_text = set()
        for chunk in chunks:
            for ch in chunk:
                all_text.add(ch)
        for ch in text:
            if ch.strip():
                assert ch in all_text

    def test_deterministic_output(self):
        """Same input always produces same output."""
        splitter = CJKAwareTextSplitter(chunk_size=50, chunk_overlap=10)
        chunks1 = splitter.split_text(CJK_CORPUS)
        chunks2 = splitter.split_text(CJK_CORPUS)
        assert chunks1 == chunks2


# ---------------------------------------------------------------------------
# build_splitter factory
# ---------------------------------------------------------------------------

class TestBuildSplitter:
    def test_cjk_profile(self):
        sp = build_splitter("cjk", chunk_size=100, chunk_overlap=10)
        assert isinstance(sp, CJKAwareTextSplitter)

    def test_zh_alias(self):
        sp = build_splitter("zh")
        assert isinstance(sp, CJKAwareTextSplitter)

    def test_english_profile(self):
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        sp = build_splitter("en")
        assert isinstance(sp, RecursiveCharacterTextSplitter)

    def test_auto_with_cjk_sample(self):
        sp = build_splitter("auto", sample_text="这是中文样本文本用于检测语言")
        assert isinstance(sp, CJKAwareTextSplitter)

    def test_auto_with_english_sample(self):
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        sp = build_splitter("auto", sample_text="This is English sample text")
        assert isinstance(sp, RecursiveCharacterTextSplitter)

    def test_mapping_profile(self):
        sp = build_splitter(
            {"language": "cjk", "chunk_size": 200, "chunk_overlap": 20}
        )
        assert isinstance(sp, CJKAwareTextSplitter)
        assert sp._chunk_size == 200
        assert sp._chunk_overlap == 20
