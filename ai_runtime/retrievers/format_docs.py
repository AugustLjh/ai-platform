"""Helpers for rendering retrieved documents into a single context string.

Mirrors the format produced by
``ChatRuntimeService._build_rag_context_and_citations`` so the LCEL chain
can stay aligned with the legacy chat citations contract.
"""
from __future__ import annotations

from typing import Iterable, List

from langchain_core.documents import Document


def _format_one(doc: Document, citation_index: int) -> str:
    """Format a single :class:`Document` into the ``[Citation N] ...`` block."""
    md = doc.metadata or {}
    title = md.get("title") or md.get("section_title") or ""
    score = md.get("score")
    parts: List[str] = []

    score_str = f" score={float(score):.4f}" if isinstance(score, (int, float)) else ""
    parts.append(f"[Citation {citation_index}] title={title}{score_str}")

    source = md.get("source")
    if source:
        parts.append(f"source={source}")

    label = md.get("citation_label")
    if label:
        parts.append(f"segment={label}")

    parts.append(doc.page_content or "")
    parts.append("")
    return "\n".join(parts)


def format_docs(docs: Iterable[Document]) -> str:
    """Render an iterable of retrieved documents into a single context
    string preserving citation metadata.

    The output is identical in shape to the legacy chat service: each
    chunk starts with ``[Citation N] title=... score=0.XXXX`` followed by
    optional ``source=`` / ``segment=`` lines, then the chunk content,
    then a blank line.
    """
    blocks: List[str] = []
    for idx, doc in enumerate(docs, start=1):
        blocks.append(_format_one(doc, idx))
    return "\n".join(blocks)


__all__ = ["format_docs"]
