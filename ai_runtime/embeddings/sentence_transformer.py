"""Local sentence-transformers embeddings adapter.

Ported from ``ai_runtime/core/embeddings/sentence_transformer.py``. The
heavy model is imported lazily so unit tests can import this module
without pulling in PyTorch.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from langchain_core.embeddings import Embeddings


class STEmbeddings(Embeddings):
    """LangChain :class:`Embeddings` wrapping a local sentence-transformers model."""

    def __init__(
        self,
        *,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: Optional[str] = None,
        cache_folder: Optional[str] = None,
        batch_size: int = 32,
    ) -> None:
        self._model_name = model_name
        self.device = device
        self.cache_folder = cache_folder
        self.batch_size = batch_size
        self._model = None
        self._dimension: Optional[int] = None

    # ------------------------------------------------------------------ utils
    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_model(self):  # pragma: no cover - heavy dep
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise NotImplementedError(
                "sentence-transformers not installed; install with"
                " `pip install sentence-transformers`"
            ) from exc
        self._model = SentenceTransformer(
            self._model_name,
            device=self.device,
            cache_folder=self.cache_folder,
        )
        self._dimension = int(self._model.get_sentence_embedding_dimension())
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        self._ensure_model()
        assert self._dimension is not None
        return self._dimension

    # ------------------------------------------------------------------ Embeddings API
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        result = model.encode(
            list(texts),
            convert_to_numpy=True,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in result]

    def embed_query(self, text: str) -> List[float]:
        model = self._ensure_model()
        vec = model.encode(text, convert_to_numpy=True)
        return vec.tolist()

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, list(texts))

    async def aembed_query(self, text: str) -> List[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)


__all__ = ["STEmbeddings"]
