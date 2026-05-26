"""Capability gating Runnable.

Wraps a chat-model-bearing runnable in a check that fails fast when the
incoming ``UnifiedModelRequest`` (or message list) demands modalities or
response formats the configured ``ModelCapabilityProfile`` cannot serve.

Ports the gating semantics from ``ai_runtime.core.llm.messages.supports_model_request``
but raises ``CapabilityViolation`` (a typed exception) instead of returning
``bool``. ``ModelRouterRunnable`` can catch the exception to switch to the
next candidate via ``with_fallbacks``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:
    from langchain_core.runnables import Runnable, RunnableConfig, RunnableSerializable
except ImportError:  # pragma: no cover
    Runnable = object  # type: ignore[assignment,misc]
    RunnableConfig = dict  # type: ignore[assignment,misc]
    RunnableSerializable = object  # type: ignore[assignment,misc]

from ai_runtime.core.llm.messages import (
    ModelCapabilityProfile,
    ModelRequestProfile,
    UnifiedMessage,
    UnifiedModelRequest,
    build_model_request_profile,
    merge_capability_profiles,
    required_input_modalities,
    supports_model_request,
)
from ai_runtime.llm.adapters import (
    SUPPORTED_ENDPOINT_PROTOCOLS,
    endpoint_protocol_input_modalities,
    supports_endpoint_protocol,
)


class CapabilityViolation(RuntimeError):
    """Raised by ``CapabilityGateRunnable`` when a request cannot be served.

    Carries structured details so the router can surface them to operators
    or use them for fallback routing decisions.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        capability: ModelCapabilityProfile | None = None,
        request_profile: ModelRequestProfile | None = None,
        missing_modalities: Sequence[str] | None = None,
        endpoint_protocol: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.capability = capability
        self.request_profile = request_profile
        self.missing_modalities = tuple(missing_modalities or ())
        self.endpoint_protocol = endpoint_protocol


@dataclass(frozen=True)
class CapabilityCheckResult:
    request_profile: ModelRequestProfile
    capability: ModelCapabilityProfile
    required_modalities: frozenset[str]
    endpoint_protocol: str | None


def _coerce_request(value: Any) -> UnifiedModelRequest:
    if isinstance(value, UnifiedModelRequest):
        return value
    if isinstance(value, dict):
        if "messages" in value or "metadata" in value:
            payload = dict(value)
            messages = payload.pop("messages", [])
            return UnifiedModelRequest.from_messages(messages, **payload)
        return UnifiedModelRequest.from_messages([value])
    if isinstance(value, (list, tuple)):
        return UnifiedModelRequest.from_messages(list(value))
    if isinstance(value, UnifiedMessage):
        return UnifiedModelRequest(messages=[value])
    raise TypeError(f"Cannot coerce input to UnifiedModelRequest: {type(value).__name__}")


def evaluate_capability(
    capability: ModelCapabilityProfile | dict[str, Any] | None,
    request: UnifiedModelRequest | Sequence[UnifiedMessage | dict[str, Any]] | dict[str, Any],
) -> CapabilityCheckResult:
    """Inspect ``request`` against ``capability``; raise on violations.

    Returns the merged capability + request profile when the check passes.
    """

    coerced = _coerce_request(request)
    profile = merge_capability_profiles(capability)
    required = frozenset(required_input_modalities(coerced.messages))

    response_format = "text"
    if coerced.response_format is not None:
        if isinstance(coerced.response_format, str):
            response_format = coerced.response_format
        elif isinstance(coerced.response_format, dict):
            response_format = (
                str(coerced.response_format.get("type") or "text").strip().lower() or "text"
            )

    request_profile = build_model_request_profile(
        coerced.messages,
        endpoint_protocol=profile.endpoint_protocol,
        response_format=response_format,
    )

    endpoint_protocol = (
        str(profile.endpoint_protocol or "").strip().lower() or None
    )
    if endpoint_protocol and not supports_endpoint_protocol(endpoint_protocol):
        raise CapabilityViolation(
            f"endpoint_protocol={endpoint_protocol} 没有对应 adapter",
            reason="unknown_endpoint_protocol",
            capability=profile,
            request_profile=request_profile,
            endpoint_protocol=endpoint_protocol,
        )

    if endpoint_protocol:
        protocol_modalities = endpoint_protocol_input_modalities(endpoint_protocol)
        if protocol_modalities is not None and not required.issubset(protocol_modalities):
            missing = sorted(required - protocol_modalities)
            raise CapabilityViolation(
                f"endpoint_protocol={endpoint_protocol} adapter 当前未实现 "
                f"{', '.join(missing)} part 的转换",
                reason="endpoint_protocol_modality_gap",
                capability=profile,
                request_profile=request_profile,
                missing_modalities=missing,
                endpoint_protocol=endpoint_protocol,
            )

    if not supports_model_request(profile, request_profile):
        supported = set(profile.input_modalities or ["text"])
        missing = sorted(set(request_profile.input_modalities or ["text"]) - supported)
        raise CapabilityViolation(
            "模型能力不满足请求画像: "
            f"required={sorted(request_profile.input_modalities)}, "
            f"supported={sorted(supported)}",
            reason="modality_unsupported",
            capability=profile,
            request_profile=request_profile,
            missing_modalities=missing,
            endpoint_protocol=endpoint_protocol,
        )

    return CapabilityCheckResult(
        request_profile=request_profile,
        capability=profile,
        required_modalities=required,
        endpoint_protocol=endpoint_protocol,
    )


class CapabilityGateRunnable(RunnableSerializable):  # type: ignore[misc]
    """Runnable that pre-checks capability compatibility.

    Pipeline position: ``ModelRouter -> CapabilityGate -> MediaTransport ->
    ProviderAdapter -> ChatModel``.

    The gate raises :class:`CapabilityViolation` *before* the wrapped chat
    model is invoked, so ``with_fallbacks([...])`` upstream can switch to
    a more capable candidate.
    """

    capability: ModelCapabilityProfile
    bound: Any = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def for_capability(
        cls,
        capability: ModelCapabilityProfile | dict[str, Any] | None,
        *,
        bound: Any | None = None,
    ) -> "CapabilityGateRunnable":
        merged = merge_capability_profiles(capability)
        return cls(capability=merged, bound=bound)

    def check(
        self,
        request: UnifiedModelRequest | Sequence[UnifiedMessage | dict[str, Any]] | dict[str, Any],
    ) -> CapabilityCheckResult:
        return evaluate_capability(self.capability, request)

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        result = self.check(input)
        if self.bound is None:
            return result
        return self.bound.invoke(input, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:  # noqa: A002
        result = self.check(input)
        if self.bound is None:
            return result
        return await self.bound.ainvoke(input, config=config, **kwargs)


__all__ = [
    "CapabilityCheckResult",
    "CapabilityGateRunnable",
    "CapabilityViolation",
    "evaluate_capability",
]
