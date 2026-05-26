"""Tests for ``ai_runtime.llm.factory.build_chat_model``.

Rewritten in Phase P1: the legacy ``create_llm_for_provider`` factory is
replaced by :func:`ai_runtime.llm.factory.build_chat_model` which returns
LangChain-native ``BaseChatModel`` subclasses. The assertions preserve
the original intent (per-provider class, capability inference,
endpoint-protocol propagation) but at the new surface.
"""
from __future__ import annotations

from ai_runtime.core.config import LLMConfig
from ai_runtime.llm import (
    DeepseekChatModel,
    DoubaoChatModel,
    GLMChatModel,
    JinaChatModel,
    KimiChatModel,
    LocalChatModel,
    MockChatModel,
    OpenAIChatModel,
    QwenChatModel,
    SUPPORTED_PROVIDERS,
    WenxinChatModel,
    build_chat_model,
)


def _row(provider: str, model: str, **config: object) -> dict:
    """Build a normalized DB model row matching ``build_chat_model``."""

    return {
        "id": f"row-{provider}",
        "name": model,
        "display_name": model,
        "provider": provider,
        "model_id": model,
        "api_key": "test-key",
        "config": dict(config),
    }


def test_supported_providers_include_new_chinese_vendors():
    for vendor in ("qwen", "wenxin", "glm", "kimi", "doubao", "jina", "local", "mock"):
        assert vendor in SUPPORTED_PROVIDERS


def test_build_chat_model_uses_vendor_defaults():
    assert isinstance(build_chat_model(_row("openai", "gpt-4")), OpenAIChatModel)
    assert isinstance(build_chat_model(_row("deepseek", "deepseek-chat")), DeepseekChatModel)
    assert isinstance(build_chat_model(_row("jina", "jina-deepsearch-v1")), JinaChatModel)
    assert isinstance(build_chat_model(_row("qwen", "qwen-plus")), QwenChatModel)
    assert isinstance(build_chat_model(_row("wenxin", "ernie-4.0-turbo-8k")), WenxinChatModel)
    assert isinstance(build_chat_model(_row("glm", "glm-4-plus")), GLMChatModel)
    assert isinstance(build_chat_model(_row("kimi", "moonshot-v1-8k")), KimiChatModel)
    assert isinstance(build_chat_model(_row("doubao", "doubao-seed-1-6")), DoubaoChatModel)
    assert isinstance(build_chat_model({**_row("local", "local-model"), "api_key": None}), LocalChatModel)
    assert isinstance(build_chat_model({**_row("mock", "mock"), "api_key": None}), MockChatModel)


def test_qwen_model_capabilities_distinguish_input_and_output_modalities():
    text_model = build_chat_model(_row("qwen", "qwen-plus"))
    vision_model = build_chat_model(_row("qwen", "qwen-vl-max"))
    audio_model = build_chat_model(_row("qwen", "qwen-audio-turbo"))
    multimodal_text_model = build_chat_model(_row("qwen", "qwen3.7"))

    assert text_model.capability.input_modalities == ["text"]
    assert vision_model.capability.supports_video_input is True
    assert "image" in vision_model.capability.input_modalities
    assert audio_model.capability.supports_audio_input is True
    assert multimodal_text_model.capability.input_modalities == ["text", "audio", "image", "video", "file"]
    assert multimodal_text_model.capability.output_modalities == ["text"]


def test_qwen_explicit_capabilities_override_catalog_defaults():
    model = build_chat_model(
        _row(
            "qwen",
            "qwen-plus",
            capabilities={
                "input_modalities": ["text", "image", "file"],
                "output_modalities": ["text"],
                "supports_vision": True,
                "supports_file_input": True,
            },
        )
    )

    assert model.capability.input_modalities == ["text", "image", "file"]
    assert model.capability.output_modalities == ["text"]
    assert model.capability.supports_vision is True
    assert model.capability.supports_file_input is True


def test_openai_endpoint_protocol_can_be_overridden_to_responses_api():
    model = build_chat_model(
        _row("openai", "gpt-4.1", endpoint_protocol="openai.responses"),
    )

    assert model.endpoint_protocol == "openai.responses"
    assert model.capability.output_modalities == ["text"]
    assert model.capability.endpoint_protocol == "openai.responses"


def test_provider_base_urls_match_vendor_defaults():
    assert (
        build_chat_model(_row("qwen", "qwen-plus")).openai_api_base
        == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert (
        build_chat_model(_row("deepseek", "deepseek-chat")).openai_api_base
        == "https://api.deepseek.com/v1"
    )
    assert (
        build_chat_model(_row("jina", "jina-deepsearch-v1")).openai_api_base
        == "https://deepsearch.jina.ai/v1"
    )
    assert (
        build_chat_model(_row("wenxin", "ernie-4.0-turbo-8k")).openai_api_base
        == "https://qianfan.baidubce.com/v2"
    )
    assert (
        build_chat_model(_row("doubao", "doubao-seed-1-6")).openai_api_base
        == "https://ark.cn-beijing.volces.com/api/v3"
    )


def test_explicit_api_base_overrides_provider_default():
    model = build_chat_model(
        {**_row("qwen", "qwen-plus"), "api_base": "https://example.invalid/v1"}
    )
    assert model.openai_api_base == "https://example.invalid/v1"


def test_llm_config_from_env_reads_vendor_specific_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")
    monkeypatch.setenv("QWEN_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen-max")

    config = LLMConfig.from_env()

    assert config.provider == "qwen"
    assert config.api_key == "qwen-key"
    assert config.api_base == "https://example.invalid/v1"
    assert config.model == "qwen-max"
