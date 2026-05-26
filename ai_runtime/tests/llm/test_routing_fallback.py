"""Unit tests for :mod:`ai_runtime.llm.routing`.

Exercises ``ModelRouterRunnable`` with a primary/fallback candidate chain
built from mock chat-model-bearing runnables. The mocks use
``langchain_core.runnables.RunnableLambda`` so we can verify both
LCEL fallback dispatch and the explicit ``select`` pre-flight.
"""
from __future__ import annotations

from typing import Any

import pytest

try:
    from langchain_core.runnables import RunnableLambda
except ImportError:  # pragma: no cover
    RunnableLambda = None  # type: ignore[assignment]

from ai_runtime.core.llm.messages import ModelCapabilityProfile
from ai_runtime.llm.capability import CapabilityGateRunnable, CapabilityViolation
from ai_runtime.llm.routing import ModelRouterRunnable, RouteDecision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _candidate(
    candidate_id: str,
    *,
    capability: dict[str, Any],
    runnable: Any | None = None,
) -> dict[str, Any]:
    """Build a candidate dict in the legacy shape understood by the router."""

    return {
        "id": candidate_id,
        "name": candidate_id,
        "display_name": candidate_id,
        "config": {},
        "capability": capability,
        "llm": runnable,
    }


def _gate_runnable(capability: dict[str, Any], *, output: Any) -> CapabilityGateRunnable:
    """Build a ``CapabilityGateRunnable`` whose ``bound`` returns ``output``."""

    if RunnableLambda is None:  # pragma: no cover
        pytest.skip("langchain_core not installed")
    inner = RunnableLambda(lambda _: output)
    return CapabilityGateRunnable.for_capability(capability, bound=inner)


# ---------------------------------------------------------------------------
# select() — pure routing decision
# ---------------------------------------------------------------------------


def test_select_returns_first_capable_candidate():
    primary = _candidate("primary", capability={"input_modalities": ["text"]})
    secondary = _candidate("secondary", capability={"input_modalities": ["text", "image"]})
    router = ModelRouterRunnable.for_candidates([primary, secondary])

    decision = router.select({"messages": [{"role": "user", "content": "hi"}]})

    assert isinstance(decision, RouteDecision)
    assert decision.candidate_id == "primary"
    assert decision.fallback_used is False
    assert decision.rejected == ()


def test_select_skips_text_only_when_image_required():
    primary = _candidate("text-only", capability={"input_modalities": ["text"]})
    secondary = _candidate(
        "vision",
        capability={
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "supports_vision": True,
        },
    )
    router = ModelRouterRunnable.for_candidates([primary, secondary])

    decision = router.select(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {"type": "image", "url": "https://example.com/cat.png"},
                    ],
                }
            ]
        }
    )

    assert decision.candidate_id == "vision"
    assert decision.fallback_used is True
    assert len(decision.rejected) == 1
    assert decision.rejected[0][0] == "text-only"
    assert "modality_unsupported" in decision.rejected[0][1]


def test_select_raises_when_all_candidates_reject():
    primary = _candidate("p1", capability={"input_modalities": ["text"]})
    secondary = _candidate("p2", capability={"input_modalities": ["text"]})
    router = ModelRouterRunnable.for_candidates([primary, secondary])

    with pytest.raises(CapabilityViolation) as exc_info:
        router.select(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "image", "url": "https://example.com/cat.png"}],
                    }
                ]
            }
        )
    assert exc_info.value.reason == "all_rejected"


def test_select_treats_candidate_without_capability_as_permissive():
    primary = _candidate("text-only", capability={"input_modalities": ["text"]})
    permissive = _candidate("permissive", capability={})  # no capability info -> assume OK
    permissive["capability"] = None  # explicit None means "unknown" too
    permissive["llm"] = None
    router = ModelRouterRunnable.for_candidates([primary, permissive])

    decision = router.select(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "url": "https://example.com/cat.png"}],
                }
            ]
        }
    )
    assert decision.candidate_id == "permissive"
    assert decision.fallback_used is True


# ---------------------------------------------------------------------------
# invoke() — actual LCEL fallback dispatch
# ---------------------------------------------------------------------------


def test_invoke_uses_primary_when_capability_passes():
    primary_runnable = _gate_runnable(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        output={"from": "primary"},
    )
    secondary_runnable = _gate_runnable(
        {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        output={"from": "secondary"},
    )
    router = ModelRouterRunnable.for_candidates(
        [
            _candidate(
                "primary",
                capability={"input_modalities": ["text"]},
                runnable=primary_runnable,
            ),
            _candidate(
                "secondary",
                capability={"input_modalities": ["text", "image"]},
                runnable=secondary_runnable,
            ),
        ]
    )

    result = router.invoke({"messages": [{"role": "user", "content": "hi"}]})
    assert result == {"from": "primary"}


def test_invoke_falls_through_on_capability_violation():
    primary_runnable = _gate_runnable(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        output={"from": "primary"},
    )
    secondary_runnable = _gate_runnable(
        {
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "supports_vision": True,
        },
        output={"from": "secondary"},
    )
    router = ModelRouterRunnable.for_candidates(
        [
            _candidate(
                "primary",
                capability={"input_modalities": ["text"]},
                runnable=primary_runnable,
            ),
            _candidate(
                "secondary",
                capability={
                    "input_modalities": ["text", "image"],
                    "supports_vision": True,
                },
                runnable=secondary_runnable,
            ),
        ]
    )

    result = router.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "url": "https://example.com/cat.png"}],
                }
            ]
        }
    )
    assert result == {"from": "secondary"}


def test_invoke_falls_through_on_runtime_error_from_primary():
    if RunnableLambda is None:  # pragma: no cover
        pytest.skip("langchain_core not installed")

    def _raise(_value: Any) -> Any:
        raise RuntimeError("simulated upstream failure")

    primary = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        bound=RunnableLambda(_raise),
    )
    secondary = _gate_runnable(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        output={"from": "secondary"},
    )
    router = ModelRouterRunnable.for_candidates(
        [
            _candidate(
                "primary",
                capability={"input_modalities": ["text"]},
                runnable=primary,
            ),
            _candidate(
                "secondary",
                capability={"input_modalities": ["text"]},
                runnable=secondary,
            ),
        ]
    )

    result = router.invoke({"messages": [{"role": "user", "content": "hi"}]})
    assert result == {"from": "secondary"}


def test_invoke_propagates_when_all_runnables_fail():
    if RunnableLambda is None:  # pragma: no cover
        pytest.skip("langchain_core not installed")

    def _raise(_value: Any) -> Any:
        raise RuntimeError("downstream gone")

    primary = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        bound=RunnableLambda(_raise),
    )
    secondary = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        bound=RunnableLambda(_raise),
    )
    router = ModelRouterRunnable.for_candidates(
        [
            _candidate("primary", capability={"input_modalities": ["text"]}, runnable=primary),
            _candidate("secondary", capability={"input_modalities": ["text"]}, runnable=secondary),
        ]
    )
    with pytest.raises(RuntimeError, match="downstream gone"):
        router.invoke({"messages": [{"role": "user", "content": "hi"}]})


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_for_candidates_rejects_empty_list():
    with pytest.raises(ValueError):
        ModelRouterRunnable.for_candidates([])


def test_router_uses_capability_from_runnable_attribute():
    """Candidates may rely on the bound chat model's ``capability`` attr."""

    class _StubModel:
        capability = ModelCapabilityProfile(
            input_modalities=["text"],
            output_modalities=["text"],
        )

    primary = _candidate("primary", capability={}, runnable=_StubModel())
    secondary = _candidate(
        "vision", capability={"input_modalities": ["text", "image"], "supports_vision": True}
    )
    router = ModelRouterRunnable.for_candidates([primary, secondary])
    decision = router.select(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "url": "https://example.com/cat.png"}],
                }
            ]
        }
    )
    assert decision.candidate_id == "vision"
