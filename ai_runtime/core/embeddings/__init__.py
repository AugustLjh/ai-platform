"""
Embedding Service for Knowledge Base
"""
from .base import EmbeddingService
from .sentence_transformer import SentenceTransformerEmbedding
from .openai_embedding import OpenAIEmbedding
from .jina_embedding import JinaEmbedding

__all__ = [
    "EmbeddingService",
    "SentenceTransformerEmbedding",
    "OpenAIEmbedding",
    "JinaEmbedding",
]
