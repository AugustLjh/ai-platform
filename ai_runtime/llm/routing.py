"""Governance-aware model routing Runnable.

Replaces the candidate-resolution logic from
``ChatService._resolve_llm_candidates``. The new layer is a pure runnable
that takes a *resolved* candidate list (already loaded from the DB by the
caller) and returns the first runnable whose capability gate accepts the
incoming request. Falls back through the chain on
:class:`CapabilityViolation` or any underlying error matching the
configured exception classes.

The chain composition is built by :func:`build_router` and uses
``langchain_core.runnables.with_fallbacks`` so the standard tracing /
retry semantics still apply.

Note on responsibilities split with the legacy implementation:

* DB I/O (``_get_governance_settings``, ``_get_model_row``) is *not*
  re-implemented here; it lives in ``api/`` and ``repositories/`` and
  produces the candidate list. P1 only shapes the in-memory routing
  decision so it is fully testable with mock candidates.
* ``_reject_reason_for_model_request`` semantics are preserved:
  an unknown ``endpoint_protocol`` or modality gap raises
  :class:`CapabilityViolation` *before* invoking the underlying model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

try:
    from langchain_core.runnables import (
        Runnable,
        RunnableConfig,
        RunnableSerializable,
        RunnableWithFallbacks,
    )
except ImportError:  # pragma: no cover
    Runnable = object  # type: ignore[assignment,misc]
    RunnableConfig = dict  # type: ignore[assignment,misc]
    RunnableSerializable = object  # type: ignore[assignment,misc]
    RunnableWithFallbacks = object  # type: ignore[assignment,misc]

from ai_runtime.llm.capability import CapabilityViolation


@dataclass(frozen=True)
class RouteDecision:
    """The decision produced by :class:`ModelRouterRunnable.select`."""

    candidate_id: str
    candidate: dict[str, Any]
    fallback_used: bool
    rejected: tuple[tuple[str, str], ...]
    """``((candidate_id, reject_reason), …)`` for inspection / metrics."""


class ModelRouterRunnable(RunnableSerializable):  # type: ignore[misc]
    """Pick the first capable candidate; fall back on failures.

    ``candidates`` items follow the legacy candidate dict shape:
    ``{"id": ..., "name": ..., "config": {...}, "llm": <runnable>, ...}``.
    The wrapped chat-model-bearing runnables are expected to already be
    composed (capability gate + adapter + chat model) — the router only
    decides *which* of the available pre-composed runnables runs first
    and arranges fallbacks.
    """

    candidates: list[dict[str, Any]]
    fallback_exceptions: tuple[type[BaseException], ...] = (
        CapabilityViolation,
        RuntimeError,
    )
    route_scene: str = "chat"

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def for_candidates(
        cls,
        candidates: Sequence[dict[str, Any]],
        *,
        route_scene: str = "chat",
        fallback_exceptions: Iterable[type[BaseException]] | None = None,
    ) -> "ModelRouterRunnable":
        if not candidates:
            raise ValueError("ModelRouterRunnable requires at least one candidate")
        return cls(
            candidates=list(candidates),
            route_scene=route_scene,
            fallback_exceptions=tuple(fallback_exceptions) if fallback_exceptions else (
                CapabilityViolation,
                RuntimeError,
            ),
        )

    # ------------------------------------------------------------------
    # Selection helper used in tests + by ``invoke``/``ainvoke``.
    # ------------------------------------------------------------------

    def select(self, request: Any) -> RouteDecision:
        """Pre-flight: probe each candidate's capability gate and pick.

        Candidates may expose either:

        * a ``llm`` runnable that is itself a :class:`CapabilityGateRunnable`
          (``llm.check(request)`` is invoked); or
        * a ``capability`` profile (a :class:`ModelCapabilityProfile` or
          dict) — we lazily build a gate to check.

        The first candidate whose gate accepts the request wins.
        """

        from ai_runtime.llm.capability import CapabilityGateRunnable

        rejected: list[tuple[str, str]] = []
        for index, candidate in enumerate(self.candidates):
            gate = self._candidate_gate(candidate)
            if gate is None:
                # No capability info -> assume permissive (legacy behaviour)
                return RouteDecision(
                    candidate_id=str(candidate.get("id") or candidate.get("name") or index),
                    candidate=candidate,
                    fallback_used=index > 0,
                    rejected=tuple(rejected),
                )
            try:
                gate.check(request)
            except CapabilityViolation as exc:
                rejected.append(
                    (
                        str(candidate.get("id") or candidate.get("name") or index),
                        f"{exc.reason}: {exc}",
                    )
                )
                continue
            return RouteDecision(
                candidate_id=str(candidate.get("id") or candidate.get("name") or index),
                candidate=candidate,
                fallback_used=index > 0,
                rejected=tuple(rejected),
            )
        if rejected:
            names = ", ".join(name for name, _ in rejected)
            reasons = "; ".join(f"{name}: {reason}" for name, reason in rejected)
            raise CapabilityViolation(
                f"All candidates rejected request ({names}): {reasons}",
                reason="all_rejected",
            )
        raise CapabilityViolation(
            "No candidates available for routing",
            reason="empty_candidates",
        )

    @staticmethod
    def _candidate_gate(candidate: dict[str, Any]):  # noqa: ANN401
        from ai_runtime.llm.capability import CapabilityGateRunnable

        runnable = candidate.get("llm")
        if isinstance(runnable, CapabilityGateRunnable):
            return runnable
        capability = candidate.get("capability") or (candidate.get("config") or {}).get("capabilities")
        if capability is None and runnable is not None and hasattr(runnable, "capability"):
            capability = runnable.capability
        if capability is None:
            return None
        return CapabilityGateRunnable.for_capability(capability)

    # ------------------------------------------------------------------
    # Runnable contract — invoke selected candidate and arrange fallbacks
    # ------------------------------------------------------------------

    def _build_fallback_chain(self) -> Any:
        """Return ``primary.with_fallbacks([second, third, …])`` or primary alone."""

        runnables: list[Any] = []
        for candidate in self.candidates:
            llm = candidate.get("llm")
            if llm is None:
                continue
            runnables.append(llm)
        if not runnables:
            raise RuntimeError("Router has no invocable candidate runnables")
        primary = runnables[0]
        if len(runnables) == 1:
            return primary
        return primary.with_fallbacks(
            runnables[1:],
            exceptions_to_handle=self.fallback_exceptions,
        )

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        chain = self._build_fallback_chain()
        return chain.invoke(input, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:  # noqa: A002
        chain = self._build_fallback_chain()
        return await chain.ainvoke(input, config=config, **kwargs)


__all__ = [
    "ModelRouterRunnable",
    "RouteDecision",
]
