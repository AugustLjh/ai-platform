from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ParamPolicy = Literal["pass", "rename", "drop", "error"]
EndpointFamily = Literal["chat_completions", "responses", "local"]


@dataclass(frozen=True)
class AdapterParamRule:
    provider_param: str | None
    policy: ParamPolicy = "rename"


@dataclass(frozen=True)
class ProviderAdapterSpec:
    adapter_id: str
    provider: str
    endpoint_protocol: str
    endpoint_family: EndpointFamily
    input_modalities: frozenset[str]
    canonical_param_map: dict[str, AdapterParamRule] = field(default_factory=dict)
    default_media_transport: tuple[str, ...] = ("file_id", "url", "base64", "text")

    def map_params(self, canonical: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        provider_params: dict[str, Any] = {}
        metadata: dict[str, Any] = {
            "adapter_id": self.adapter_id,
            "endpoint_protocol": self.endpoint_protocol,
            "param_mapping": {},
            "dropped_params": [],
            "unsupported_params": [],
        }
        for key, value in canonical.items():
            if value is None:
                continue
            rule = self.canonical_param_map.get(key)
            if rule is None:
                metadata["dropped_params"].append(key)
                continue
            if rule.policy == "drop":
                metadata["dropped_params"].append(key)
                continue
            if rule.policy == "error":
                metadata["unsupported_params"].append(key)
                continue
            provider_key = rule.provider_param or key
            provider_params[provider_key] = value
            metadata["param_mapping"][key] = provider_key
        if metadata["unsupported_params"]:
            names = ", ".join(metadata["unsupported_params"])
            raise RuntimeError(f"{self.adapter_id} does not support request parameters: {names}")
        return provider_params, metadata


CHAT_COMPLETIONS_PARAM_MAP: dict[str, AdapterParamRule] = {
    "temperature": AdapterParamRule("temperature"),
    "max_output_tokens": AdapterParamRule("max_tokens"),
    "top_p": AdapterParamRule("top_p"),
    "tools": AdapterParamRule("tools"),
    "tool_choice": AdapterParamRule("tool_choice"),
    "response_format": AdapterParamRule("response_format"),
    "reasoning": AdapterParamRule(None, "drop"),
    "media_transport": AdapterParamRule(None, "drop"),
}

RESPONSES_PARAM_MAP: dict[str, AdapterParamRule] = {
    "temperature": AdapterParamRule("temperature"),
    "max_output_tokens": AdapterParamRule("max_output_tokens"),
    "top_p": AdapterParamRule("top_p"),
    "tools": AdapterParamRule("tools"),
    "tool_choice": AdapterParamRule("tool_choice"),
    "response_format": AdapterParamRule("text"),
    "reasoning": AdapterParamRule("reasoning"),
    "media_transport": AdapterParamRule(None, "drop"),
}

TEXT_CHAT_PARAM_MAP: dict[str, AdapterParamRule] = {
    "temperature": AdapterParamRule("temperature"),
    "max_output_tokens": AdapterParamRule("max_tokens"),
    "top_p": AdapterParamRule("top_p"),
    "tools": AdapterParamRule(None, "drop"),
    "tool_choice": AdapterParamRule(None, "drop"),
    "response_format": AdapterParamRule("response_format"),
    "reasoning": AdapterParamRule(None, "drop"),
    "media_transport": AdapterParamRule(None, "drop"),
}


def _spec(
    provider: str,
    endpoint_protocol: str,
    endpoint_family: EndpointFamily,
    input_modalities: set[str],
    param_map: dict[str, AdapterParamRule],
) -> ProviderAdapterSpec:
    return ProviderAdapterSpec(
        adapter_id=f"{provider}.{endpoint_protocol}",
        provider=provider,
        endpoint_protocol=endpoint_protocol,
        endpoint_family=endpoint_family,
        input_modalities=frozenset(input_modalities),
        canonical_param_map=param_map,
    )


ADAPTER_REGISTRY: dict[tuple[str, str], ProviderAdapterSpec] = {
    ("openai", "openai.chat_completions"): _spec(
        "openai", "openai.chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("openai", "openai.responses"): _spec(
        "openai", "openai.responses", "responses", {"text", "image", "audio", "video", "file"}, RESPONSES_PARAM_MAP
    ),
    ("jina", "jina.responses"): _spec(
        "jina", "jina.responses", "responses", {"text", "image", "audio", "video", "file"}, RESPONSES_PARAM_MAP
    ),
    ("jina", "openai.chat_completions"): _spec(
        "jina", "openai.chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("deepseek", "deepseek.chat_completions"): _spec(
        "deepseek", "deepseek.chat_completions", "chat_completions", {"text"}, TEXT_CHAT_PARAM_MAP
    ),
    ("qwen", "dashscope.openai_compatible"): _spec(
        "qwen", "dashscope.openai_compatible", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("qwen", "dashscope.responses"): _spec(
        "qwen", "dashscope.responses", "responses", {"text", "image", "audio", "video", "file"}, RESPONSES_PARAM_MAP
    ),
    ("glm", "bigmodel.chat_completions"): _spec(
        "glm", "bigmodel.chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("glm", "bigmodel.responses"): _spec(
        "glm", "bigmodel.responses", "responses", {"text", "image", "file"}, RESPONSES_PARAM_MAP
    ),
    ("kimi", "moonshot.chat_completions"): _spec(
        "kimi", "moonshot.chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("kimi", "moonshot.responses"): _spec(
        "kimi", "moonshot.responses", "responses", {"text", "image", "file"}, RESPONSES_PARAM_MAP
    ),
    ("doubao", "volcengine.ark_chat_completions"): _spec(
        "doubao", "volcengine.ark_chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("doubao", "volcengine.ark_responses"): _spec(
        "doubao", "volcengine.ark_responses", "responses", {"text", "image", "file"}, RESPONSES_PARAM_MAP
    ),
    ("wenxin", "baidu.qianfan_chat_completions"): _spec(
        "wenxin", "baidu.qianfan_chat_completions", "chat_completions", {"text", "image"}, CHAT_COMPLETIONS_PARAM_MAP
    ),
    ("wenxin", "baidu.qianfan_responses"): _spec(
        "wenxin", "baidu.qianfan_responses", "responses", {"text", "image", "audio", "video", "file"}, RESPONSES_PARAM_MAP
    ),
    ("local", "local.chat_completions"): _spec(
        "local", "local.chat_completions", "local", {"text"}, TEXT_CHAT_PARAM_MAP
    ),
    ("mock", "local.chat_completions"): _spec(
        "mock", "local.chat_completions", "local", {"text"}, TEXT_CHAT_PARAM_MAP
    ),
}


ENDPOINT_PROTOCOL_INPUT_MODALITIES: dict[str, set[str]] = {}
for spec in ADAPTER_REGISTRY.values():
    ENDPOINT_PROTOCOL_INPUT_MODALITIES.setdefault(spec.endpoint_protocol, set()).update(spec.input_modalities)

SUPPORTED_ENDPOINT_PROTOCOLS: set[str] = set(ENDPOINT_PROTOCOL_INPUT_MODALITIES)


def normalize_provider(value: Any) -> str:
    return str(value or "openai").strip().lower() or "openai"


def normalize_endpoint_protocol(value: Any, fallback: str = "openai.chat_completions") -> str:
    protocol = str(value or fallback).strip().lower()
    return protocol or fallback


def get_adapter_spec(provider: str | None, endpoint_protocol: str | None) -> ProviderAdapterSpec | None:
    normalized_provider = normalize_provider(provider)
    normalized_protocol = normalize_endpoint_protocol(endpoint_protocol)
    return ADAPTER_REGISTRY.get((normalized_provider, normalized_protocol))


def get_adapter_spec_for_protocol(endpoint_protocol: str | None) -> ProviderAdapterSpec | None:
    normalized_protocol = normalize_endpoint_protocol(endpoint_protocol)
    for spec in ADAPTER_REGISTRY.values():
        if spec.endpoint_protocol == normalized_protocol:
            return spec
    return None


def endpoint_protocol_input_modalities(endpoint_protocol: str | None) -> set[str] | None:
    if not endpoint_protocol:
        return None
    return ENDPOINT_PROTOCOL_INPUT_MODALITIES.get(normalize_endpoint_protocol(endpoint_protocol))


def supports_endpoint_protocol(endpoint_protocol: str | None) -> bool:
    if not endpoint_protocol:
        return True
    return normalize_endpoint_protocol(endpoint_protocol) in SUPPORTED_ENDPOINT_PROTOCOLS


def adapter_schema() -> dict[str, Any]:
    protocols = {
        protocol: sorted(modalities)
        for protocol, modalities in sorted(ENDPOINT_PROTOCOL_INPUT_MODALITIES.items())
    }
    adapters = [
        {
            "adapter_id": spec.adapter_id,
            "provider": spec.provider,
            "endpoint_protocol": spec.endpoint_protocol,
            "endpoint_family": spec.endpoint_family,
            "input_modalities": sorted(spec.input_modalities),
            "canonical_param_map": {
                key: {"provider_param": rule.provider_param, "policy": rule.policy}
                for key, rule in spec.canonical_param_map.items()
            },
            "default_media_transport": list(spec.default_media_transport),
        }
        for spec in sorted(ADAPTER_REGISTRY.values(), key=lambda item: (item.provider, item.endpoint_protocol))
    ]
    return {
        "endpoint_protocol_input_modalities": protocols,
        "supported_endpoint_protocols": sorted(SUPPORTED_ENDPOINT_PROTOCOLS),
        "adapters": adapters,
    }
