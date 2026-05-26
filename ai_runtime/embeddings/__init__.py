"""LangChain-compatible embeddings adapters."""
from .factory import build_embeddings
from .jina import JinaEmbeddings
from .openai import OpenAIEmbeddingsAdapter
from .sentence_transformer import STEmbeddings

__all__ = [
    "build_embeddings",
    "JinaEmbeddings",
    "OpenAIEmbeddingsAdapter",
    "STEmbeddings",
]
