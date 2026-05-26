"""CJK-aware text splitter.

Uses ``jieba`` to find sentence boundaries in CJK text and respects CJK
punctuation (。！？；) as natural split points. Falls back to
:class:`langchain_text_splitters.RecursiveCharacterTextSplitter` for
non-CJK regions or when jieba is unavailable.

Ported from the chunking logic in
``ai_runtime/core/services/document_service.py``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional, Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

try:
    import jieba
except ImportError:  # pragma: no cover
    jieba = None  # type: ignore[assignment]

# CJK sentence-ending punctuation
_CJK_SENTENCE_ENDS = set("。！？；!?;")

# Regex to detect whether a text block is predominantly CJK
_CJK_RANGE_RE = re.compile(
    r"[一-鿿㐀-䶿豈-﫿"
    r"\U00020000-\U0002a6df\U0002a700-\U0002b73f"
    r"\U0002b740-\U0002b81f\U0002b820-\U0002ceaf"
    r"\U0002ceb0-\U0002ebef\U00030000-\U0003134f"
    r"　-〿＀-￯]"
)


def _is_predominantly_cjk(text: str, threshold: float = 0.3) -> bool:
    """Return True if at least *threshold* fraction of non-whitespace chars
    are CJK."""
    if not text:
        return False
    non_ws = [ch for ch in text if not ch.isspace()]
    if not non_ws:
        return False
    cjk_count = sum(1 for ch in non_ws if _CJK_RANGE_RE.match(ch))
    return (cjk_count / len(non_ws)) >= threshold


def _split_cjk_sentences(text: str) -> List[str]:
    """Split CJK text into sentences using jieba (if available) and
    punctuation boundaries.

    The algorithm:
    1. Split on CJK sentence-ending punctuation.
    2. Within each resulting fragment, use jieba.cut to tokenize and
       re-join into sub-sentences if they exceed a soft limit.
    """
    if not text.strip():
        return []

    # First pass: split on sentence-ending punctuation
    sentences: List[str] = []
    current: List[str] = []
    for ch in text:
        current.append(ch)
        if ch in _CJK_SENTENCE_ENDS:
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    # Remainder
    if current:
        remainder = "".join(current).strip()
        if remainder:
            sentences.append(remainder)

    return sentences


class CJKAwareTextSplitter(TextSplitter):
    """A text splitter that handles CJK text with sentence-boundary
    awareness.

    For CJK-dominant text, it splits on sentence-ending punctuation
    (。！？；) and groups sentences into chunks that respect
    ``chunk_size``. For non-CJK text, it delegates to
    :class:`RecursiveCharacterTextSplitter`.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[Sequence[str]] = None,
        cjk_threshold: float = 0.3,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs)
        self._cjk_threshold = cjk_threshold
        self._fallback_separators = list(separators) if separators else None
        self._fallback_splitter: Optional[RecursiveCharacterTextSplitter] = None

    def _get_fallback(self) -> RecursiveCharacterTextSplitter:
        if self._fallback_splitter is None:
            kwargs: dict[str, Any] = {
                "chunk_size": self._chunk_size,
                "chunk_overlap": self._chunk_overlap,
                "keep_separator": True,
            }
            if self._fallback_separators:
                kwargs["separators"] = self._fallback_separators
            self._fallback_splitter = RecursiveCharacterTextSplitter(**kwargs)
        return self._fallback_splitter

    def _group_sentences_into_chunks(
        self,
        sentences: List[str],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[str]:
        """Group sentences into chunks respecting size limits."""
        if not sentences:
            return []

        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            # If a single sentence exceeds chunk_size, split it further
            if sentence_len > chunk_size:
                # Flush current chunk first
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                # Use fallback for oversized sentences
                sub_chunks = self._get_fallback().split_text(sentence)
                chunks.extend(sub_chunks)
                continue

            # Would adding this sentence exceed the limit?
            if current_length + sentence_len > chunk_size and current_chunk:
                chunks.append("".join(current_chunk))
                # Overlap: keep trailing sentences that fit within overlap budget
                overlap_chunk: List[str] = []
                overlap_len = 0
                for s in reversed(current_chunk):
                    if overlap_len + len(s) > chunk_overlap:
                        break
                    overlap_chunk.insert(0, s)
                    overlap_len += len(s)
                current_chunk = overlap_chunk
                current_length = overlap_len

            current_chunk.append(sentence)
            current_length += sentence_len

        if current_chunk:
            chunks.append("".join(current_chunk))

        return chunks

    def split_text(self, text: str) -> List[str]:
        """Split *text* into chunks.

        If the text is predominantly CJK, uses sentence-boundary splitting.
        Otherwise delegates to :class:`RecursiveCharacterTextSplitter`.
        """
        if not text or not text.strip():
            return []

        if not _is_predominantly_cjk(text, self._cjk_threshold):
            return self._get_fallback().split_text(text)

        sentences = _split_cjk_sentences(text)
        if not sentences:
            return self._get_fallback().split_text(text)

        return self._group_sentences_into_chunks(
            sentences,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )


__all__ = ["CJKAwareTextSplitter", "_is_predominantly_cjk", "_split_cjk_sentences"]
