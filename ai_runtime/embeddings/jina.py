"""Jina AI embeddings adapter.

Ported from ``ai_runtime/core/embeddings/jina_embedding.py`` to the
LangChain :class:`Embeddings` interface. Uses ``httpx.AsyncClient`` for
async calls and falls back to a synchronous httpx call when the caller
invokes ``embed_documents``/``embed_query`` from a sync context.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Mapping, Optional

import httpx
from langchain_core.embeddings import Embeddings


_DEFAULT_DIMENSION_MAP: Mapping[str, int] = {
    "jina-embeddings-v3": 1024,
    "jina-embeddings-v2-base-zh": 768,
    "jina-embeddings-v2-base-en": 768,
}


class JinaEmbeddings(Embeddings):
    """Jina AI embeddings client built on httpx."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "jina-embeddings-v3",
        base_url: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout: float = 30.0,
        dimensions: Optional[int] = None,
        extra_payload: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not api_key:
            raise ValueError("JinaEmbeddings requires an api_key")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or api_base or "https://api.jina.ai/v1").rstrip("/")
        self.timeout = timeout
        self._dimensions = dimensions
        self._extra_payload: Dict[str, Any] = dict(extra_payload or {})

    # ------------------------------------------------------------------ utils
    @property
    def dimension(self) -> int:
        if self._dimensions is not None:
            return int(self._dimensions)
        return _DEFAULT_DIMENSION_MAP.get(self.model, 1024)

    @property
    def model_name(self) -> str:
        return self.model

    def _build_payload(self, texts: List[str]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }
        if self._dimensions is not None:
            payload["dimensions"] = int(self._dimensions)
        payload.update(self._extra_payload)
        return payload

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse(self, data: Mapping[str, Any]) -> List[List[float]]:
        items = data.get("data") if isinstance(data, Mapping) else None
        if not isinstance(items, list):
            raise ValueError(f"Jina embeddings response missing 'data': {data!r}")
        return [list(item["embedding"]) for item in items]

    # ------------------------------------------------------------------ Embeddings API
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json=self._build_payload(list(texts)),
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Jina AI API error (status {response.status_code}): {response.text}"
                )
            return self._parse(response.json())

    def embed_query(self, text: str) -> List[float]:
        result = self.embed_documents([text])
        return result[0] if result else []

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json=self._build_payload(list(texts)),
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Jina AI API error (status {response.status_code}): {response.text}"
                )
            return self._parse(response.json())

    async def aembed_query(self, text: str) -> List[float]:
        result = await self.aembed_documents([text])
        return result[0] if result else []


__all__ = ["JinaEmbeddings"]
