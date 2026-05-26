"""LangChain-compatible retrievers for the AI runtime."""
from .collection_router import QdrantCollectionRouter
from .format_docs import format_docs
from .pipeline import build_rag_chain
from .qdrant import CitationAwareRetriever

__all__ = [
    "CitationAwareRetriever",
    "QdrantCollectionRouter",
    "format_docs",
    "build_rag_chain",
]
