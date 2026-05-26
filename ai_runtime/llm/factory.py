"""LLM factory + composition pipeline.

Exposes:

* :func:`build_chat_model` — given a normalized ``model_config`` dict (the
  shape produced by :func:`ai_runtime.api.models._normalize_model_config`,
  i.e. what the database hands back), instantiate the right
  ``BaseChatModel`` subclass with provider-specific ``base_url`` /
  capabilities. This is the LangChain-native counterpart to
  ``ai_runtime.core.llm.providers.create_llm_for_provider``.

* :func:`wrap_model` — given a ``BaseChatModel`` plus its config, wrap it
  in the standard composition pipeline ::

      ModelRouter -> CapabilityGate -> MediaTransport -> ProviderAdapter -> ChatModel

  ``wrap_model`` returns a :class:`langchain_core.runnables.Runnable`.
  ``ModelRouter`` is added later by callers that have a candidate list;
  for single-candidate use cases it is omitted.
"""
from __future__ import annotations

from typing import Any

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.runnables import Runnable
except ImportError:  # pragma: no cover - skeleton fallback
    BaseChatModel = object  # type: ignore[assignment,misc]
    Runnable = object  # type: ignore[assignment,misc]

from ai_runtime.llm.adapters import (
    ProviderAdapterRunnable,
    get_adapter_spec,
    get_adapter_spec_for_protocol,
    normalize_endpoint_protocol,
    normalize_provider,
)
from ai_runtime.llm.capability import CapabilityGateRunnable
from ai_runtime.llm.jina import JinaChatModel
from ai_runtime.llm.media_transport import MediaTransportRunnable
from ai_runtime.llm.openai_compat import (
    DeepseekChatModel,
    DoubaoChatModel,
    GLMChatModel,
    KimiChatModel,
    LocalChatModel,
    MockChatModel,
    OpenAIChatModel,
    QwenChatModel,
)
from ai_runtime.llm.wenxin import WenxinChatModel


SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "openai",
    "deepseek",
    "jina",
    "qwen",
    "wenxin",
    "glm",
    "kimi",
    "doubao",
    "local",
    "mock",
)


PROVIDER_CHAT_MODELS: dict[str, type] = {
    "openai": OpenAIChatModel,
    "deepseek": DeepseekChatModel,
    "jina": JinaChatModel,
    "qwen": QwenChatModel,
    "wenxin": WenxinChatModel,
    "glm": GLMChatModel,
    "kimi": KimiChatModel,
    "doubao": DoubaoChatModel,
    "local": LocalChatModel,
    "mock": MockChatModel,
}


def _extract_provider(model_config: dict[str, Any]) -> str:
    return normalize_provider(model_config.get("provider"))


def _extract_endpoint_protocol(model_config: dict[str, Any]) -> str | None:
    config = model_config.get("config") if isinstance(model_config.get("config"), dict) else {}
    raw = (
        model_config.get("endpoint_protocol")
        or (config or {}).get("endpoint_protocol")
        or (config or {}).get("capabilities", {}).get("endpoint_protocol")
        if isinstance(config, dict)
        else None
    )
    if not raw:
        return None
    return normalize_endpoint_protocol(raw)


def _extract_capability(model_config: dict[str, Any]) -> dict[str, Any] | None:
    config = model_config.get("config")
    if isinstance(config, dict):
        capabilities = config.get("capabilities")
        if isinstance(capabilities, dict):
            return capabilities
    capabilities = model_config.get("capabilities")
    if isinstance(capabilities, dict):
        return capabilities
    return None


def build_chat_model(model_config: dict[str, Any]) -> BaseChatModel:
    """Instantiate the ``BaseChatModel`` for a normalized model config.

    ``model_config`` is the shape stored in the ``llm_models`` table, e.g.::

        {
          "id": "row-uuid",
          "name": "qwen-vl",
          "display_name": "Qwen VL Max",
          "provider": "qwen",
          "model_id": "qwen-vl-max",
          "api_base": "https://...",
          "api_key": "...",
          "config": {"temperature": 0.3, "endpoint_protocol": "...", "capabilities": {...}},
        }

    The returned model is *not* yet wrapped in capability/adapter/transport
    runnables — call :func:`wrap_model` for the full pipeline.
    """

    provider = _extract_provider(model_config)
    if provider not in PROVIDER_CHAT_MODELS:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    klass = PROVIDER_CHAT_MODELS[provider]
    config = model_config.get("config") if isinstance(model_config.get("config"), dict) else {}
    config = config or {}
    capability = _extract_capability(model_config)
    endpoint_protocol = _extract_endpoint_protocol(model_config) or klass.DEFAULT_ENDPOINT_PROTOCOL

    init_kwargs: dict[str, Any] = {
        "model": model_config.get("model_id") or model_config.get("name"),
        "api_key": model_config.get("api_key"),
        "api_base": model_config.get("api_base"),
        "provider": provider,
        "endpoint_protocol": endpoint_protocol,
        "capability": capability,
    }

    # Optional generation defaults baked into the chat model.
    for option in ("temperature", "top_p"):
        value = config.get(option)
        if value is not None:
            init_kwargs[option] = value

    max_tokens = config.get("max_output_tokens", config.get("max_tokens"))
    if max_tokens is not None:
        # ChatOpenAI accepts ``max_tokens`` as a top-level attribute; it
        # forwards to the upstream provider regardless of whether they
        # expose ``max_tokens`` or ``max_completion_tokens``.
        init_kwargs["max_tokens"] = int(max_tokens)

    return klass(**{key: value for key, value in init_kwargs.items() if value is not None})


def wrap_model(
    base: BaseChatModel,
    config: dict[str, Any] | None = None,
    *,
    capability: dict[str, Any] | Any | None = None,
    media_transport: bool = True,
) -> Runnable:
    """Compose the full pipeline around ``base``.

    Pipeline (left-to-right):

        CapabilityGate -> MediaTransport (optional) -> ProviderAdapter -> base

    The router layer is *not* applied here — callers that need governance
    fallback wrap a list of these per-candidate runnables in
    :class:`ai_runtime.llm.routing.ModelRouterRunnable`.

    ``config`` is the normalized model config dict (same shape consumed by
    :func:`build_chat_model`); it carries ``adapter_options`` used by the
    media transport runnable.
    """

    config = config or {}
    provider = _extract_provider(config) if config else getattr(base, "provider_name", "openai")
    endpoint_protocol = (
        _extract_endpoint_protocol(config)
        or getattr(base, "endpoint_protocol", None)
        or "openai.chat_completions"
    )
    capability = (
        capability
        or _extract_capability(config)
        or getattr(base, "capability", None)
    )

    adapter = ProviderAdapterRunnable.for_provider(
        provider,
        endpoint_protocol,
        bound=base,
    )
    chain: Runnable = adapter
    if media_transport:
        chain = MediaTransportRunnable.for_candidate(
            model_config=config.get("config") if isinstance(config.get("config"), dict) else config,
            provider=provider,
            endpoint_protocol=endpoint_protocol,
            bound=chain,
        )
    chain = CapabilityGateRunnable.for_capability(capability, bound=chain)
    return chain


__all__ = [
    "PROVIDER_CHAT_MODELS",
    "SUPPORTED_PROVIDERS",
    "build_chat_model",
    "wrap_model",
]
