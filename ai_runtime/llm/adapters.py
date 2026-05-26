"""Provider adapter registry + ``ProviderAdapterRunnable``.

Ports ``ai_runtime.core.llm.adapters`` and wraps it in a LangChain
``Runnable`` that maps canonical request parameters to provider-specific
HTTP payload fields *before* the underlying chat model is invoked.

The composition pipeline established in P1 is:

    ModelRouter -> CapabilityGate -> MediaTransport -> ProviderAdapter -> ChatModel

``ProviderAdapterRunnable`` lives in the next-to-last position and only
mutates the canonical-form request; the actual HTTP shaping is performed
by the chat model (e.g. ``langchain_openai.ChatOpenAI``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

try:  # pragma: no cover - exercised via factory
    from langchain_core.runnables import Runnable, RunnableConfig, RunnableSerializable
except ImportError:  # pragma: no cover - skeleton fallback
    Runnable = object  # type: ignore[assignment,misc]
    RunnableConfig = dict  # type: ignore[assignment,misc]
    RunnableSerializable = object  # type: ignore[assignment,misc]


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
        """Translate canonical params to provider-specific names.

        Returns ``(provider_params, metadata)``. ``metadata`` contains the
        adapter id, the per-key mapping, and the dropped/unsupported lists.
        Raises ``RuntimeError`` if any param has policy ``error``.
        """

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
            raise RuntimeError(
                f"{self.adapter_id} does not support request parameters: {names}"
            )
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
    """Public schema for the ``/api/v1/models/schema`` endpoint."""

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


# ---------------------------------------------------------------------------
# Runnable wrapper
# ---------------------------------------------------------------------------


class ProviderAdapterRunnable(RunnableSerializable):  # type: ignore[misc]
    """Pre-invoke param mapping wrapper around a ``BaseChatModel``.

    Inputs flow through the LangChain pipeline as a ``dict`` containing at
    least ``messages`` and possibly ``params``. The runnable looks up the
    adapter spec for the configured provider+protocol and rewrites the
    canonical parameter names to provider-specific ones before delegating
    to the wrapped chat model. The result mirrors what ``BaseChatModel``
    would produce on its own.

    Use ``ProviderAdapterRunnable.build_payload(canonical, extra)`` to
    obtain the deterministic payload+metadata pair (no I/O); the runnable
    invocation path simply forwards mapped params via ``bind`` so that
    underlying ``langchain_openai.ChatOpenAI`` receives them in their
    provider-specific names.
    """

    spec: ProviderAdapterSpec
    bound: Any = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def for_provider(
        cls,
        provider: str | None,
        endpoint_protocol: str | None,
        *,
        bound: Any | None = None,
    ) -> "ProviderAdapterRunnable":
        spec = get_adapter_spec(provider, endpoint_protocol)
        if spec is None:
            spec = get_adapter_spec_for_protocol(endpoint_protocol)
        if spec is None:
            raise RuntimeError(
                f"No provider adapter registered for provider={provider!r}, "
                f"endpoint_protocol={endpoint_protocol!r}"
            )
        return cls(spec=spec, bound=bound)

    # ------------------------------------------------------------------
    # Pure helpers (used by the chat models + tests)
    # ------------------------------------------------------------------

    def map_params(self, canonical: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.spec.map_params(canonical)

    def build_payload(
        self,
        *,
        model_id: str,
        canonical_params: dict[str, Any],
        provider_messages: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """Return ``(endpoint_family, payload, metadata)``.

        Mirrors ``OpenAILLM.build_http_payload`` but lives at the adapter
        layer so non-OpenAI clients can reuse the canonical mapping.
        """

        provider_params, metadata = self.spec.map_params(canonical_params)
        payload: dict[str, Any] = {"model": model_id, **provider_params}
        if extra:
            for key, value in extra.items():
                if value is None:
                    continue
                payload.setdefault(key, value)
        if provider_messages is not None:
            if self.spec.endpoint_family == "responses":
                payload["input"] = provider_messages
            else:
                payload["messages"] = provider_messages
        return self.spec.endpoint_family, payload, metadata

    # ------------------------------------------------------------------
    # Runnable contract — delegate to ``self.bound`` if present.
    # ------------------------------------------------------------------

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        if self.bound is None:
            return self._mapped_input(input)
        mapped = self._mapped_input(input)
        return self.bound.invoke(mapped, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        if self.bound is None:
            return self._mapped_input(input)
        mapped = self._mapped_input(input)
        return await self.bound.ainvoke(mapped, config=config, **kwargs)

    def _mapped_input(self, input: Any) -> Any:  # noqa: A002
        """Rewrite ``input["params"]`` keys via the adapter's param map.

        Tolerant of plain message lists (no params attached); they pass
        through unchanged.
        """

        if not isinstance(input, dict):
            return input
        canonical = input.get("params")
        if not isinstance(canonical, dict):
            return input
        provider_params, metadata = self.spec.map_params(canonical)
        merged = dict(input)
        merged["params"] = provider_params
        merged.setdefault("metadata", {})
        merged["metadata"] = {**merged["metadata"], "adapter": metadata}
        return merged


__all__ = [
    "AdapterParamRule",
    "ADAPTER_REGISTRY",
    "CHAT_COMPLETIONS_PARAM_MAP",
    "ENDPOINT_PROTOCOL_INPUT_MODALITIES",
    "EndpointFamily",
    "ParamPolicy",
    "ProviderAdapterRunnable",
    "ProviderAdapterSpec",
    "RESPONSES_PARAM_MAP",
    "SUPPORTED_ENDPOINT_PROTOCOLS",
    "TEXT_CHAT_PARAM_MAP",
    "adapter_schema",
    "endpoint_protocol_input_modalities",
    "get_adapter_spec",
    "get_adapter_spec_for_protocol",
    "normalize_endpoint_protocol",
    "normalize_provider",
    "supports_endpoint_protocol",
]
