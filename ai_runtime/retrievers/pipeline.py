"""LCEL RAG chain factory.

Composes a citation-aware retriever, a prompt and a chat model into a
single :class:`langchain_core.runnables.Runnable`. The chain accepts an
input dict with at minimum a ``question`` (or ``query``) field and emits
a dict with ``answer`` (the model output) plus ``citations`` and
``context`` so callers can keep the legacy chat contract.
"""
from __future__ import annotations

from typing import Any, Mapping

from langchain_core.documents import Document
from langchain_core.prompts import BasePromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnablePassthrough,
)

from .format_docs import format_docs


def _extract_question(payload: Mapping[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, Mapping):
        for key in ("question", "query", "input"):
            if key in payload and payload[key] is not None:
                return str(payload[key])
    return str(payload)


def _docs_to_citations(docs: list[Document]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for doc in docs:
        md = doc.metadata or {}
        citations.append(
            {
                "citation_id": md.get("citation_id"),
                "document_id": md.get("document_id"),
                "chunk_id": md.get("chunk_id"),
                "title": md.get("title") or md.get("section_title"),
                "source": md.get("source"),
                "knowledge_base_id": md.get("kb_id") or md.get("knowledge_base_id"),
                "score": md.get("score"),
                "document_rank": md.get("document_rank"),
                "segment_index": md.get("segment_index"),
                "section_title": md.get("section_title"),
                "citation_label": md.get("citation_label"),
            }
        )
    return citations


def build_rag_chain(
    retriever: BaseRetriever,
    prompt: BasePromptTemplate,
    model: Runnable,
) -> Runnable:
    """Build an LCEL chain that runs the retriever, formats the context,
    runs the prompt + model and emits a dict with ``answer``, ``context``
    and ``citations``.

    The chain is async-friendly out of the box — the resulting Runnable
    supports both ``invoke`` and ``ainvoke``.
    """

    def _retrieve(inp: Any) -> list[Document]:
        question = _extract_question(inp)
        return retriever.invoke(question)

    async def _aretrieve(inp: Any) -> list[Document]:
        question = _extract_question(inp)
        return await retriever.ainvoke(question)

    retriever_runnable = RunnableLambda(_retrieve, afunc=_aretrieve)

    chain = (
        RunnablePassthrough.assign(
            question=RunnableLambda(_extract_question),
            documents=retriever_runnable,
        )
        | RunnablePassthrough.assign(
            context=RunnableLambda(lambda x: format_docs(x["documents"])),
            citations=RunnableLambda(lambda x: _docs_to_citations(x["documents"])),
        )
        | RunnablePassthrough.assign(
            answer=(
                RunnableLambda(lambda x: {"context": x["context"], "question": x["question"]})
                | prompt
                | model
            )
        )
    )
    return chain


__all__ = ["build_rag_chain"]
