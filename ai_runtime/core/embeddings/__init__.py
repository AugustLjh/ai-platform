"""
Embedding Service for Knowledge Base
"""
from .base import EmbeddingService
from .sentence_transformer import SentenceTransformerEmbedding

__all__ = ["EmbeddingService", "SentenceTransformerEmbedding"]
