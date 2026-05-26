"""Tests for the embeddings factory.

Asserts that ``build_embeddings`` returns the correct adapter type for
each provider config. We avoid making real network calls — for the
OpenAI adapter we just check the chosen model and (lazy) underlying
type without invoking it.
"""
from __future__ import annotations

import pytest

from ai_runtime.embeddings import (
    JinaEmbeddings,
    OpenAIEmbeddingsAdapter,
    STEmbeddings,
    build_embeddings,
)


def test_factory_builds_openai_adapter():
    adapter = build_embeddings(
        {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "api_key": "sk-test",
            "base_url": "https://api.example.com/v1",
        }
    )
    assert isinstance(adapter, OpenAIEmbeddingsAdapter)
    assert adapter.model == "text-embedding-3-small"
    assert adapter.base_url == "https://api.example.com/v1"
    assert adapter.dimension == 1536


def test_factory_builds_openai_adapter_via_alias():
    adapter = build_embeddings(
        {
            "provider": "openai_compatible",
            "model": "text-embedding-3-large",
            "api_key": "sk",
            "api_base": "https://proxy.local/v1",
        }
    )
    assert isinstance(adapter, OpenAIEmbeddingsAdapter)
    assert adapter.dimension == 3072
    assert adapter.base_url == "https://proxy.local/v1"


def test_factory_builds_jina_with_explicit_model():
    adapter = build_embeddings(
        {
            "provider": "jina",
            "model": "jina-embeddings-v2-base-zh",
            "api_key": "jina-key",
        }
    )
    assert isinstance(adapter, JinaEmbeddings)
    assert adapter.model == "jina-embeddings-v2-base-zh"
    assert adapter.dimension == 768


def test_factory_jina_requires_api_key():
    with pytest.raises(ValueError):
        build_embeddings({"provider": "jina"})


def test_factory_builds_sentence_transformer():
    adapter = build_embeddings(
        {
            "provider": "sentence_transformer",
            "model": "paraphrase-multilingual-MiniLM-L12-v2",
            "device": "cpu",
            "batch_size": 8,
        }
    )
    assert isinstance(adapter, STEmbeddings)
    assert adapter.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
    assert adapter.device == "cpu"
    assert adapter.batch_size == 8


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_embeddings({"provider": "unknown"})


def test_factory_requires_provider():
    with pytest.raises(ValueError):
        build_embeddings({})


def test_factory_accepts_pydantic_like_object():
    class Config:
        provider = "openai"
        model = "text-embedding-3-small"
        api_key = "sk"

    cfg = Config()
    adapter = build_embeddings(cfg)
    assert isinstance(adapter, OpenAIEmbeddingsAdapter)
