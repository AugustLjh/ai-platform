"""OpenAI-compatible chat model subclasses.

Most providers we support speak the OpenAI Chat Completions wire protocol
with only ``base_url``/``api_base`` and a few default param differences.
We expose thin subclasses of ``langchain_openai.ChatOpenAI`` that:

* set the right ``base_url`` and provider identifier;
* attach a ``ModelCapabilityProfile`` (consulted by the capability gate);
* expose a ``ProviderAdapterRunnable`` for the corresponding adapter spec;
* expose ``provider`` and ``endpoint_protocol`` attributes.

Subclassing is intentionally minimal — ``ChatOpenAI`` already implements
all the streaming, retries, tool-calling, etc. machinery. Anything the
codebase adds on top of that (capability gating, governance routing,
media transport, adapter param remapping) lives in dedicated Runnables
applied in :mod:`ai_runtime.llm.factory`.
"""
from __future__ import annotations

from typing import Any, ClassVar

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - skeleton fallback
    ChatOpenAI = object  # type: ignore[assignment,misc]

from pydantic import Field

from ai_runtime.core.llm.messages import (
    ModelCapabilityProfile,
    capability_profile_from_settings,
)
from ai_runtime.llm.adapters import (
    ProviderAdapterRunnable,
    ProviderAdapterSpec,
    get_adapter_spec,
    get_adapter_spec_for_protocol,
    normalize_endpoint_protocol,
)
from ai_runtime.llm.catalog import infer_model_capabilities


class _OpenAICompatBase(ChatOpenAI):  # type: ignore[misc]
    """Shared functionality for every OpenAI-compatible provider.

    Default values for ``api_base`` / ``endpoint_protocol`` are class
    attributes that subclasses override.
    """

    DEFAULT_API_BASE: ClassVar[str] = "https://api.openai.com/v1"
    DEFAULT_PROVIDER: ClassVar[str] = "openai"
    DEFAULT_ENDPOINT_PROTOCOL: ClassVar[str] = "openai.chat_completions"
    USES_CATALOG: ClassVar[bool] = False

    provider_name: str = Field(default="openai")
    endpoint_protocol: str = Field(default="openai.chat_completions")
    capability: ModelCapabilityProfile = Field(
        default_factory=lambda: capability_profile_from_settings()
    )

    model_config = {"arbitrary_types_allowed": True, "populate_by_name": True}

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        provider: str | None = None,
        endpoint_protocol: str | None = None,
        capability: ModelCapabilityProfile | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider_name = (provider or self.DEFAULT_PROVIDER).strip().lower()
        protocol = normalize_endpoint_protocol(endpoint_protocol or self.DEFAULT_ENDPOINT_PROTOCOL)
        base_url = api_base or kwargs.pop("base_url", None) or self.DEFAULT_API_BASE

        merged_capability = self._compose_capability(provider_name, model, capability, protocol)

        # Local / mock providers point at offline endpoints; ChatOpenAI still
        # demands a non-empty api_key for the openai SDK to instantiate.
        effective_api_key = api_key
        if not effective_api_key and provider_name in {"local", "mock"}:
            effective_api_key = "local-placeholder"

        # Don't pass our extra kwargs to ChatOpenAI super().__init__
        chat_kwargs = dict(kwargs)
        chat_kwargs.setdefault("model", model or "")
        chat_kwargs.setdefault("api_key", effective_api_key)
        chat_kwargs.setdefault("base_url", base_url)
        chat_kwargs["provider_name"] = provider_name
        chat_kwargs["endpoint_protocol"] = protocol
        chat_kwargs["capability"] = merged_capability
        super().__init__(**chat_kwargs)

    @classmethod
    def _compose_capability(
        cls,
        provider_name: str,
        model: str | None,
        override: ModelCapabilityProfile | dict[str, Any] | None,
        resolved_protocol: str | None = None,
    ) -> ModelCapabilityProfile:
        # Base defaults (lowest priority)
        sources: list[Any] = [{"endpoint_protocol": resolved_protocol or cls.DEFAULT_ENDPOINT_PROTOCOL}]
        # Catalog inference (medium priority)
        if cls.USES_CATALOG and model:
            sources.append(infer_model_capabilities(provider_name, model))
        # Explicit override (highest priority)
        if override is not None:
            sources.append(override)
        # If override specifies endpoint_protocol, ensure it wins
        if isinstance(override, dict) and override.get("endpoint_protocol"):
            sources.append({"endpoint_protocol": override["endpoint_protocol"]})
        elif resolved_protocol:
            sources.append({"endpoint_protocol": resolved_protocol})
        return capability_profile_from_settings(*sources)

    @property
    def adapter_spec(self) -> ProviderAdapterSpec:
        spec = get_adapter_spec(self.provider_name, self.endpoint_protocol)
        if spec is None:
            spec = get_adapter_spec_for_protocol(self.endpoint_protocol)
        if spec is None:
            raise RuntimeError(
                f"No adapter registered for provider={self.provider_name!r}, "
                f"endpoint_protocol={self.endpoint_protocol!r}"
            )
        return spec

    def adapter_runnable(self) -> ProviderAdapterRunnable:
        return ProviderAdapterRunnable(spec=self.adapter_spec, bound=self)


class OpenAIChatModel(_OpenAICompatBase):
    """``ChatOpenAI`` against OpenAI's own endpoint."""

    DEFAULT_API_BASE = "https://api.openai.com/v1"
    DEFAULT_PROVIDER = "openai"
    DEFAULT_ENDPOINT_PROTOCOL = "openai.chat_completions"


class DeepseekChatModel(_OpenAICompatBase):
    """DeepSeek chat completions (text only)."""

    DEFAULT_API_BASE = "https://api.deepseek.com/v1"
    DEFAULT_PROVIDER = "deepseek"
    DEFAULT_ENDPOINT_PROTOCOL = "deepseek.chat_completions"


class QwenChatModel(_OpenAICompatBase):
    """Alibaba DashScope Qwen chat completions (OpenAI-compatible mode)."""

    DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_PROVIDER = "qwen"
    DEFAULT_ENDPOINT_PROTOCOL = "dashscope.openai_compatible"
    USES_CATALOG = True


class KimiChatModel(_OpenAICompatBase):
    """Moonshot Kimi chat completions."""

    DEFAULT_API_BASE = "https://api.moonshot.cn/v1"
    DEFAULT_PROVIDER = "kimi"
    DEFAULT_ENDPOINT_PROTOCOL = "moonshot.chat_completions"
    USES_CATALOG = True


class DoubaoChatModel(_OpenAICompatBase):
    """Volcengine Ark / Doubao chat completions."""

    DEFAULT_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_PROVIDER = "doubao"
    DEFAULT_ENDPOINT_PROTOCOL = "volcengine.ark_chat_completions"
    USES_CATALOG = True


class GLMChatModel(_OpenAICompatBase):
    """Zhipu GLM (BigModel) chat completions."""

    DEFAULT_API_BASE = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_PROVIDER = "glm"
    DEFAULT_ENDPOINT_PROTOCOL = "bigmodel.chat_completions"
    USES_CATALOG = True


class LocalChatModel(_OpenAICompatBase):
    """Local / mock OpenAI-compatible endpoint (Ollama, vLLM, …)."""

    DEFAULT_API_BASE = "http://localhost:8000/v1"
    DEFAULT_PROVIDER = "local"
    DEFAULT_ENDPOINT_PROTOCOL = "local.chat_completions"


class MockChatModel(LocalChatModel):
    """Alias used when ``provider == "mock"`` (offline tests)."""

    DEFAULT_PROVIDER = "mock"


__all__ = [
    "DeepseekChatModel",
    "DoubaoChatModel",
    "GLMChatModel",
    "KimiChatModel",
    "LocalChatModel",
    "MockChatModel",
    "OpenAIChatModel",
    "QwenChatModel",
    "_OpenAICompatBase",
]
