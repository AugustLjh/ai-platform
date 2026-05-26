"""LangChain-native LLM stack.

Public API consumed by graphs / chat / agent runtime layers:

* :func:`build_chat_model` — DB row → ``BaseChatModel``
* :func:`wrap_model` — composition pipeline
* :class:`ModelRouterRunnable` — governance + fallbacks
* :class:`CapabilityGateRunnable`, :class:`CapabilityViolation`
* :class:`MediaTransportRunnable`, :func:`materialize_parts`
* :class:`ProviderAdapterRunnable`, ``ProviderAdapterSpec``, ``ADAPTER_REGISTRY``

Submodules expose the per-provider chat model classes.
"""
from ai_runtime.llm.adapters import (
    ADAPTER_REGISTRY,
    AdapterParamRule,
    EndpointFamily,
    ParamPolicy,
    ProviderAdapterRunnable,
    ProviderAdapterSpec,
    SUPPORTED_ENDPOINT_PROTOCOLS,
    adapter_schema,
    endpoint_protocol_input_modalities,
    get_adapter_spec,
    get_adapter_spec_for_protocol,
    normalize_endpoint_protocol,
    normalize_provider,
    supports_endpoint_protocol,
)
from ai_runtime.llm.capability import (
    CapabilityCheckResult,
    CapabilityGateRunnable,
    CapabilityViolation,
    evaluate_capability,
)
from ai_runtime.llm.catalog import (
    infer_model_capabilities,
    load_model_capability_catalog,
    model_capability_schema,
)
from ai_runtime.llm.factory import (
    PROVIDER_CHAT_MODELS,
    SUPPORTED_PROVIDERS,
    build_chat_model,
    wrap_model,
)
from ai_runtime.llm.jina import JinaChatModel
from ai_runtime.llm.media_transport import (
    MediaTransportRunnable,
    TransportPlan,
    materialize_parts,
    resolve_transport_plan,
)
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
from ai_runtime.llm.routing import ModelRouterRunnable, RouteDecision
from ai_runtime.llm.wenxin import WenxinChatModel


__all__ = [
    "ADAPTER_REGISTRY",
    "AdapterParamRule",
    "CapabilityCheckResult",
    "CapabilityGateRunnable",
    "CapabilityViolation",
    "DeepseekChatModel",
    "DoubaoChatModel",
    "EndpointFamily",
    "GLMChatModel",
    "JinaChatModel",
    "KimiChatModel",
    "LocalChatModel",
    "MediaTransportRunnable",
    "MockChatModel",
    "ModelRouterRunnable",
    "OpenAIChatModel",
    "PROVIDER_CHAT_MODELS",
    "ParamPolicy",
    "ProviderAdapterRunnable",
    "ProviderAdapterSpec",
    "QwenChatModel",
    "RouteDecision",
    "SUPPORTED_ENDPOINT_PROTOCOLS",
    "SUPPORTED_PROVIDERS",
    "TransportPlan",
    "WenxinChatModel",
    "adapter_schema",
    "build_chat_model",
    "endpoint_protocol_input_modalities",
    "evaluate_capability",
    "get_adapter_spec",
    "get_adapter_spec_for_protocol",
    "infer_model_capabilities",
    "load_model_capability_catalog",
    "materialize_parts",
    "model_capability_schema",
    "normalize_endpoint_protocol",
    "normalize_provider",
    "resolve_transport_plan",
    "supports_endpoint_protocol",
    "wrap_model",
]
