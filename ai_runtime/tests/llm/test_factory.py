"""Unit tests for :mod:`ai_runtime.llm.factory`.

Exercises ``build_chat_model`` against mocked DB-style config rows for
every supported provider, plus the ``wrap_model`` composition pipeline.
"""
from __future__ import annotations

import pytest

from ai_runtime.llm.capability import CapabilityGateRunnable
from ai_runtime.llm.factory import (
    PROVIDER_CHAT_MODELS,
    SUPPORTED_PROVIDERS,
    build_chat_model,
    wrap_model,
)
from ai_runtime.llm.media_transport import MediaTransportRunnable
from ai_runtime.llm.adapters import ProviderAdapterRunnable


@pytest.mark.parametrize(
    "provider, model_id",
    [
        ("openai", "gpt-4"),
        ("deepseek", "deepseek-chat"),
        ("jina", "jina-deepsearch-v1"),
        ("qwen", "qwen-plus"),
        ("wenxin", "ernie-4.0-turbo-8k"),
        ("glm", "glm-4-plus"),
        ("kimi", "moonshot-v1-8k"),
        ("doubao", "doubao-seed-1-6"),
    ],
)
def test_build_chat_model_returns_provider_specific_subclass(provider: str, model_id: str):
    row = {
        "id": "row-1",
        "name": model_id,
        "provider": provider,
        "model_id": model_id,
        "api_key": "test-key",
        "config": {},
    }
    model = build_chat_model(row)
    assert isinstance(model, PROVIDER_CHAT_MODELS[provider])
    assert model.provider_name == provider
    assert model.model_name == model_id  # ChatOpenAI exposes ``model_name``


def test_build_chat_model_falls_back_to_placeholder_api_key_for_local():
    row = {
        "id": "row-local",
        "name": "local",
        "provider": "local",
        "model_id": "local-model",
        "api_key": None,
        "config": {},
    }
    model = build_chat_model(row)
    assert model.provider_name == "local"
    # Effective api_key shouldn't be empty (would crash ChatOpenAI init).
    assert model.openai_api_key.get_secret_value() != ""


def test_build_chat_model_rejects_unsupported_provider():
    row = {
        "id": "x",
        "name": "x",
        "provider": "imaginary",
        "model_id": "x",
        "api_key": "k",
        "config": {},
    }
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_chat_model(row)


def test_build_chat_model_respects_explicit_api_base():
    row = {
        "id": "r",
        "name": "ds",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "api_key": "k",
        "api_base": "https://example.invalid/v1",
        "config": {},
    }
    model = build_chat_model(row)
    assert model.openai_api_base == "https://example.invalid/v1"


def test_build_chat_model_threads_temperature_into_chat_model():
    row = {
        "id": "r",
        "name": "qwen",
        "provider": "qwen",
        "model_id": "qwen-plus",
        "api_key": "k",
        "config": {"temperature": 0.42},
    }
    model = build_chat_model(row)
    assert model.temperature == 0.42


def test_build_chat_model_threads_max_tokens_as_top_level_attribute():
    row = {
        "id": "r",
        "name": "qwen",
        "provider": "qwen",
        "model_id": "qwen-plus",
        "api_key": "k",
        "config": {"max_output_tokens": 256},
    }
    model = build_chat_model(row)
    # ChatOpenAI exposes ``max_tokens`` as a top-level attribute.
    assert model.max_tokens == 256


def test_wrap_model_composes_capability_media_transport_and_adapter():
    base = build_chat_model(
        {
            "id": "r",
            "provider": "qwen",
            "model_id": "qwen-vl-max",
            "api_key": "k",
            "config": {},
        }
    )
    wrapped = wrap_model(
        base,
        {
            "provider": "qwen",
            "config": {
                "endpoint_protocol": "dashscope.openai_compatible",
                "capabilities": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                    "supports_vision": True,
                    "endpoint_protocol": "dashscope.openai_compatible",
                },
                "adapter_options": {"media_transport": ["url", "file_id"]},
            },
        },
    )
    # Outermost layer is the capability gate.
    assert isinstance(wrapped, CapabilityGateRunnable)
    # Inner layers: media transport -> provider adapter -> base
    media = wrapped.bound
    assert isinstance(media, MediaTransportRunnable)
    adapter = media.bound
    assert isinstance(adapter, ProviderAdapterRunnable)
    assert adapter.spec.adapter_id == "qwen.dashscope.openai_compatible"
    assert adapter.bound is base


def test_wrap_model_without_media_transport_drops_that_layer():
    base = build_chat_model(
        {
            "id": "r",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "api_key": "k",
            "config": {},
        }
    )
    wrapped = wrap_model(
        base,
        {"provider": "deepseek", "config": {"capabilities": {"input_modalities": ["text"]}}},
        media_transport=False,
    )
    assert isinstance(wrapped, CapabilityGateRunnable)
    assert isinstance(wrapped.bound, ProviderAdapterRunnable)
    assert wrapped.bound.bound is base


def test_supported_providers_match_factory_keys():
    assert set(SUPPORTED_PROVIDERS) == set(PROVIDER_CHAT_MODELS)
