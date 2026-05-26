"""Tests for ``ai_runtime.llm.adapters.ProviderAdapterRunnable``.

Rewritten in Phase P1: assertions verify that the adapter registry maps
provider+protocol to the correct spec, and that ``build_payload`` produces
the expected per-provider HTTP payload shapes.
"""
from __future__ import annotations

from ai_runtime.llm.adapters import (
    ProviderAdapterRunnable,
    adapter_schema,
    get_adapter_spec,
)


def test_adapter_registry_maps_provider_and_protocol_to_explicit_adapter():
    spec = get_adapter_spec("wenxin", "baidu.qianfan_chat_completions")

    assert spec is not None
    assert spec.adapter_id == "wenxin.baidu.qianfan_chat_completions"
    assert spec.endpoint_family == "chat_completions"
    assert spec.canonical_param_map["max_output_tokens"].provider_param == "max_tokens"
    assert spec.canonical_param_map["reasoning"].policy == "drop"


def test_adapter_schema_is_single_source_for_endpoint_modalities():
    schema = adapter_schema()

    assert "openai.responses" in schema["supported_endpoint_protocols"]
    assert schema["endpoint_protocol_input_modalities"]["openai.responses"] == [
        "audio",
        "file",
        "image",
        "text",
        "video",
    ]
    assert any(
        item["endpoint_protocol"] == "dashscope.openai_compatible"
        for item in schema["adapters"]
    )


def test_chat_completions_golden_payload_maps_canonical_params():
    adapter = ProviderAdapterRunnable.for_provider("openai", "openai.chat_completions")

    family, payload, metadata = adapter.build_payload(
        model_id="gpt-test",
        canonical_params={
            "temperature": 0.2,
            "max_output_tokens": 123,
            "top_p": 0.9,
            "reasoning": {"effort": "low"},
        },
        provider_messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
                ],
            }
        ],
    )

    assert family == "chat_completions"
    assert payload == {
        "model": "gpt-test",
        "temperature": 0.2,
        "max_tokens": 123,
        "top_p": 0.9,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
                ],
            }
        ],
    }
    assert metadata["param_mapping"]["max_output_tokens"] == "max_tokens"
    assert "reasoning" in metadata["dropped_params"]


def test_openai_responses_golden_payload_maps_reasoning_and_response_format():
    adapter = ProviderAdapterRunnable.for_provider("openai", "openai.responses")

    family, payload, metadata = adapter.build_payload(
        model_id="gpt-test",
        canonical_params={
            "temperature": 0.1,
            "max_output_tokens": 456,
            "response_format": {"format": {"type": "text"}},
            "reasoning": {"effort": "medium"},
        },
        provider_messages=[
            {"role": "user", "content": [{"type": "input_text", "text": "summarize"}]}
        ],
    )

    assert family == "responses"
    assert payload["model"] == "gpt-test"
    assert payload["temperature"] == 0.1
    assert payload["max_output_tokens"] == 456
    assert payload["text"] == {"format": {"type": "text"}}
    assert payload["reasoning"] == {"effort": "medium"}
    assert metadata["param_mapping"]["response_format"] == "text"


def test_dashscope_openai_compatible_uses_chat_completions_adapter():
    adapter = ProviderAdapterRunnable.for_provider("qwen", "dashscope.openai_compatible")

    family, payload, metadata = adapter.build_payload(
        model_id="qwen-vl-max",
        canonical_params={"max_output_tokens": 64},
        provider_messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://example.com/qwen.png"}}
                ],
            }
        ],
    )

    assert family == "chat_completions"
    assert metadata["adapter_id"] == "qwen.dashscope.openai_compatible"
    assert payload["max_tokens"] == 64
    assert payload["messages"][0]["content"][0]["type"] == "image_url"


def test_baidu_qianfan_chat_completions_golden_payload():
    adapter = ProviderAdapterRunnable.for_provider("wenxin", "baidu.qianfan_chat_completions")

    family, payload, metadata = adapter.build_payload(
        model_id="ernie-4.0-turbo-8k",
        canonical_params={"temperature": 0.3, "max_output_tokens": 77},
        provider_messages=[{"role": "user", "content": "hello"}],
    )

    assert family == "chat_completions"
    assert metadata["adapter_id"] == "wenxin.baidu.qianfan_chat_completions"
    assert payload == {
        "model": "ernie-4.0-turbo-8k",
        "temperature": 0.3,
        "max_tokens": 77,
        "messages": [{"role": "user", "content": "hello"}],
    }


def test_deepseek_text_chat_drops_tools_and_reasoning():
    adapter = ProviderAdapterRunnable.for_provider("deepseek", "deepseek.chat_completions")

    family, payload, metadata = adapter.build_payload(
        model_id="deepseek-chat",
        canonical_params={
            "temperature": 0.5,
            "max_output_tokens": 100,
            "tools": [{"type": "function", "function": {"name": "f"}}],
            "tool_choice": "auto",
            "reasoning": {"effort": "high"},
        },
        provider_messages=[{"role": "user", "content": "hi"}],
    )

    assert family == "chat_completions"
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert "reasoning" not in payload
    assert "tools" in metadata["dropped_params"]
    assert "reasoning" in metadata["dropped_params"]
