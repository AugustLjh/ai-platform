"""OpenAI embeddings adapter for the LangChain pipeline.

Wraps :class:`langchain_openai.OpenAIEmbeddings` so we can plug a custom
``base_url``, request timeouts and per-tenant API keys, while exposing a
stable :class:`langchain_core.embeddings.Embeddings` instance for the rest
of the runtime.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional

from langchain_core.embeddings import Embeddings


_DEFAULT_DIMENSION_MAP: Mapping[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingsAdapter(Embeddings):
    """Thin adapter over :class:`langchain_openai.OpenAIEmbeddings`.

    The langchain-openai class is itself a Pydantic model that already
    implements :class:`Embeddings`; we still wrap it so we can:

    * accept ``api_base`` (legacy alias) and translate to ``base_url``;
    * delay importing ``langchain_openai`` until first use (so module
      imports stay lightweight if the dep is missing);
    * expose ``dimension`` and ``model_name`` helpers used by the
      collection router.
    """

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_base: Optional[str] = None,
        dimensions: Optional[int] = None,
        timeout: Optional[float] = None,
        organization: Optional[str] = None,
        extra_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or api_base
        self._dimensions = dimensions
        self.timeout = timeout
        self.organization = organization
        self._extra_kwargs = dict(extra_kwargs or {})
        self._underlying: Optional[Embeddings] = None

    # ------------------------------------------------------------------ utils
    @property
    def dimension(self) -> int:
        if self._dimensions is not None:
            return int(self._dimensions)
        return _DEFAULT_DIMENSION_MAP.get(self.model, 1536)

    @property
    def model_name(self) -> str:
        return self.model

    def _build_underlying(self) -> Embeddings:
        if self._underlying is not None:
            return self._underlying
        try:
            from langchain_openai import OpenAIEmbeddings  # type: ignore
        except ImportError as exc:  # pragma: no cover - import guard
            raise NotImplementedError(
                "langchain-openai is not installed; cannot build OpenAIEmbeddings"
            ) from exc

        kwargs: dict[str, Any] = {"model": self.model}
        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        if self.base_url is not None:
            kwargs["base_url"] = self.base_url
        if self._dimensions is not None:
            kwargs["dimensions"] = int(self._dimensions)
        if self.timeout is not None:
            kwargs["timeout"] = self.timeout
        if self.organization is not None:
            kwargs["organization"] = self.organization
        kwargs.update(self._extra_kwargs)
        self._underlying = OpenAIEmbeddings(**kwargs)
        return self._underlying

    # ------------------------------------------------------------------ Embeddings API
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._build_underlying().embed_documents(list(texts))

    def embed_query(self, text: str) -> List[float]:
        return self._build_underlying().embed_query(text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return await self._build_underlying().aembed_documents(list(texts))

    async def aembed_query(self, text: str) -> List[float]:
        return await self._build_underlying().aembed_query(text)


__all__ = ["OpenAIEmbeddingsAdapter"]
