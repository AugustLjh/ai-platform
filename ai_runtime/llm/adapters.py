"""Provider adapter registry + ``ProviderAdapterRunnable``.

The dataclasses + registry + free functions live in
``ai_runtime.core.llm.adapters`` (legacy home, no LangChain dep). This
module re-exports them and adds the ``Runnable`` wrapper used by the
LangChain composition pipeline:

    ModelRouter -> CapabilityGate -> MediaTransport -> ProviderAdapter -> ChatModel

``ProviderAdapterRunnable`` lives in the next-to-last position and only
mutates the canonical-form request; the actual HTTP shaping is performed
by the chat model (e.g. ``langchain_openai.ChatOpenAI``).
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised via factory
    from langchain_core.runnables import RunnableConfig, RunnableSerializable
except ImportError:  # pragma: no cover - skeleton fallback
    RunnableConfig = dict  # type: ignore[assignment,misc]
    RunnableSerializable = object  # type: ignore[assignment,misc]

from ai_runtime.core.llm.adapters import (
    ADAPTER_REGISTRY,
    AdapterParamRule,
    CHAT_COMPLETIONS_PARAM_MAP,
    ENDPOINT_PROTOCOL_INPUT_MODALITIES,
    EndpointFamily,
    ParamPolicy,
    ProviderAdapterSpec,
    RESPONSES_PARAM_MAP,
    SUPPORTED_ENDPOINT_PROTOCOLS,
    TEXT_CHAT_PARAM_MAP,
    adapter_schema,
    endpoint_protocol_input_modalities,
    get_adapter_spec,
    get_adapter_spec_for_protocol,
    normalize_endpoint_protocol,
    normalize_provider,
    supports_endpoint_protocol,
)


class ProviderAdapterRunnable(RunnableSerializable):  # type: ignore[misc]
    """Pre-invoke param mapping wrapper around a ``BaseChatModel``.

    Inputs flow through the LangChain pipeline as a ``dict`` containing at
    least ``messages`` and possibly ``params``. The runnable looks up the
    adapter spec for the configured provider+protocol and rewrites the
    canonical parameter names to provider-specific ones before delegating
    to the wrapped chat model.

    Use ``ProviderAdapterRunnable.build_payload(canonical, extra)`` to
    obtain the deterministic payload+metadata pair (no I/O); the runnable
    invocation path simply forwards mapped params via ``bind`` so that
    the underlying ``langchain_openai.ChatOpenAI`` receives them in their
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
