"""Embeddings factory.

Selects an :class:`langchain_core.embeddings.Embeddings` implementation
based on a config dict / Pydantic model. Mirrors the shape produced by
``ai_runtime.core.config`` so chat/agent graphs can pass either a typed
config or a raw mapping.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from langchain_core.embeddings import Embeddings

from .jina import JinaEmbeddings
from .openai import OpenAIEmbeddingsAdapter
from .sentence_transformer import STEmbeddings


_PROVIDER_ALIASES: Mapping[str, str] = {
    "openai": "openai",
    "openai_compatible": "openai",
    "azure_openai": "openai",
    "deepseek": "openai",
    "jina": "jina",
    "jina_ai": "jina",
    "sentence_transformer": "sentence_transformer",
    "sentence-transformer": "sentence_transformer",
    "sentence_transformers": "sentence_transformer",
    "st": "sentence_transformer",
    "local": "sentence_transformer",
    "huggingface": "sentence_transformer",
    "hf": "sentence_transformer",
}


def _coerce_mapping(config: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(config, Mapping):
        return config
    if hasattr(config, "model_dump"):
        return config.model_dump()
    if hasattr(config, "dict") and not isinstance(getattr(config, "dict"), type):
        try:
            return config.dict()  # type: ignore[no-any-return]
        except TypeError:
            pass
    if hasattr(config, "__dict__"):
        merged: dict[str, Any] = {}
        # Pull class-level public attributes first, then override with
        # instance attributes so users can subclass + override.
        for cls in reversed(type(config).__mro__):
            for key, value in vars(cls).items():
                if key.startswith("_") or callable(value):
                    continue
                merged[key] = value
        merged.update({
            k: v for k, v in vars(config).items() if not k.startswith("_")
        })
        if merged:
            return merged
    raise TypeError(f"Cannot coerce config of type {type(config)!r} to mapping")


def _resolve_provider(value: Optional[str]) -> str:
    if not value:
        raise ValueError("Embeddings config requires a non-empty 'provider'")
    key = str(value).strip().lower()
    if key not in _PROVIDER_ALIASES:
        raise ValueError(f"Unsupported embeddings provider: {value!r}")
    return _PROVIDER_ALIASES[key]


def build_embeddings(config: Union[Mapping[str, Any], Any]) -> Embeddings:
    """Build an :class:`Embeddings` instance from a config mapping.

    Recognised top-level keys:

    * ``provider`` – one of ``openai`` / ``jina`` / ``sentence_transformer``
      (aliases supported, see :data:`_PROVIDER_ALIASES`).
    * ``model`` (alias ``model_name``) – model identifier.
    * ``api_key``, ``base_url`` (alias ``api_base``), ``timeout``,
      ``dimensions`` – provider-specific kwargs.
    * ``device``, ``cache_folder``, ``batch_size`` – sentence-transformers
      kwargs.
    """
    payload = dict(_coerce_mapping(config))
    provider = _resolve_provider(payload.pop("provider", None))

    model = payload.pop("model", None) or payload.pop("model_name", None)
    api_key = payload.pop("api_key", None)
    base_url = payload.pop("base_url", None) or payload.pop("api_base", None)
    timeout = payload.pop("timeout", None)
    dimensions = payload.pop("dimensions", None) or payload.pop("dimension", None)

    if provider == "openai":
        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url
        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)
        if timeout is not None:
            kwargs["timeout"] = timeout
        organization = payload.pop("organization", None)
        if organization is not None:
            kwargs["organization"] = organization
        # remaining unknown fields go to extra_kwargs for forward-compat
        if payload:
            kwargs["extra_kwargs"] = dict(payload)
        return OpenAIEmbeddingsAdapter(**kwargs)

    if provider == "jina":
        if not api_key:
            raise ValueError("Jina embeddings require 'api_key'")
        kwargs = {"api_key": api_key}
        if model:
            kwargs["model"] = model
        if base_url is not None:
            kwargs["base_url"] = base_url
        if timeout is not None:
            kwargs["timeout"] = float(timeout)
        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)
        if payload:
            kwargs["extra_payload"] = dict(payload)
        return JinaEmbeddings(**kwargs)

    if provider == "sentence_transformer":
        kwargs = {}
        if model:
            kwargs["model_name"] = model
        device = payload.pop("device", None)
        if device is not None:
            kwargs["device"] = device
        cache_folder = payload.pop("cache_folder", None)
        if cache_folder is not None:
            kwargs["cache_folder"] = cache_folder
        batch_size = payload.pop("batch_size", None)
        if batch_size is not None:
            kwargs["batch_size"] = int(batch_size)
        return STEmbeddings(**kwargs)

    raise ValueError(f"Unhandled provider: {provider}")


__all__ = ["build_embeddings"]
