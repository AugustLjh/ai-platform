"""Tests for ``ai_runtime.llm.capability.CapabilityGateRunnable``.

Rewritten in Phase P1: the legacy ``_normalize_model_config`` helper lives
at the API layer (unchanged); P1 introduces a dedicated capability gate
runnable that fails requests with unsupported modalities or unknown
endpoint protocols *before* the model is invoked.

Assertions cover the gate's observable behaviour: violations raise
:class:`CapabilityViolation` with structured fields, and supported
requests return a populated :class:`CapabilityCheckResult`.
"""
from __future__ import annotations

import pytest

from ai_runtime.core.llm.messages import (
    UnifiedModelRequest,
    capability_profile_from_settings,
)
from ai_runtime.llm.capability import (
    CapabilityCheckResult,
    CapabilityGateRunnable,
    CapabilityViolation,
    evaluate_capability,
)


# ---------------------------------------------------------------------------
# Text-only models reject multimodal requests
# ---------------------------------------------------------------------------


def test_text_only_model_rejects_image_input():
    gate = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]}
    )
    with pytest.raises(CapabilityViolation) as exc_info:
        gate.check(
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
    assert exc_info.value.reason == "modality_unsupported"
    assert "image" in exc_info.value.missing_modalities


def test_text_only_model_rejects_audio_input():
    gate = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]}
    )
    with pytest.raises(CapabilityViolation) as exc_info:
        gate.check(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "audio", "url": "https://example.com/clip.mp3"}],
                    }
                ]
            }
        )
    assert exc_info.value.reason == "modality_unsupported"
    assert "audio" in exc_info.value.missing_modalities


# ---------------------------------------------------------------------------
# Vision-capable models accept image input
# ---------------------------------------------------------------------------


def test_vision_capable_model_passes_image_request():
    gate = CapabilityGateRunnable.for_capability(
        {
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "supports_vision": True,
        }
    )
    result = gate.check(
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
    assert isinstance(result, CapabilityCheckResult)
    assert "image" in result.request_profile.input_modalities
    assert "image" in result.capability.input_modalities


def test_supports_vision_flag_promotes_image_modality():
    profile = capability_profile_from_settings(
        {"input_modalities": ["text"], "output_modalities": ["text"], "supports_vision": True}
    )
    gate = CapabilityGateRunnable.for_capability(profile)
    result = gate.check(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "url": "https://example.com/cat.png"}],
                }
            ]
        }
    )
    assert "image" in result.capability.input_modalities


# ---------------------------------------------------------------------------
# Endpoint protocol gating
# ---------------------------------------------------------------------------


def test_unknown_endpoint_protocol_violates_immediately():
    gate = CapabilityGateRunnable.for_capability(
        {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "endpoint_protocol": "dashscope.multimodal_conversation",
        }
    )
    with pytest.raises(CapabilityViolation) as exc_info:
        gate.check({"messages": [{"role": "user", "content": "hi"}]})
    assert exc_info.value.reason == "unknown_endpoint_protocol"
    assert exc_info.value.endpoint_protocol == "dashscope.multimodal_conversation"


def test_endpoint_protocol_without_required_modality_violates():
    gate = CapabilityGateRunnable.for_capability(
        {
            "input_modalities": ["text", "audio"],
            "output_modalities": ["text"],
            "endpoint_protocol": "deepseek.chat_completions",
        }
    )
    with pytest.raises(CapabilityViolation) as exc_info:
        gate.check(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "audio", "url": "https://example.com/clip.mp3"}],
                    }
                ]
            }
        )
    assert exc_info.value.reason == "endpoint_protocol_modality_gap"
    assert "audio" in exc_info.value.missing_modalities


def test_openai_responses_protocol_accepts_video_input():
    gate = CapabilityGateRunnable.for_capability(
        {
            "input_modalities": ["text", "video"],
            "output_modalities": ["text"],
            "supports_video_input": True,
            "endpoint_protocol": "openai.responses",
        }
    )
    result = gate.check(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video", "file_id": "file-video", "file_name": "demo.mp4"}
                    ],
                }
            ]
        }
    )
    assert result.endpoint_protocol == "openai.responses"


# ---------------------------------------------------------------------------
# Output forced to text
# ---------------------------------------------------------------------------


def test_capability_profile_forces_text_output_even_when_audio_output_declared():
    gate = CapabilityGateRunnable.for_capability(
        {
            "input_modalities": ["text", "audio"],
            "output_modalities": ["text", "audio"],
            "supports_audio_input": True,
            "supports_audio_output": True,
        }
    )
    assert gate.capability.output_modalities == ["text"]
    assert gate.capability.supports_audio_output is True


# ---------------------------------------------------------------------------
# evaluate_capability is symmetric with the runnable
# ---------------------------------------------------------------------------


def test_evaluate_capability_accepts_unified_request_object():
    request = UnifiedModelRequest.from_messages(
        [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    )
    result = evaluate_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]},
        request,
    )
    assert result.required_modalities == frozenset({"text"})


def test_evaluate_capability_uses_supports_vision_to_promote_modality():
    request = UnifiedModelRequest.from_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image", "url": "https://example.com/cat.png"},
                ],
            }
        ]
    )
    # Even though input_modalities is just ["text"], supports_vision=True
    # promotes image into the modality set.
    result = evaluate_capability(
        {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_vision": True,
        },
        request,
    )
    assert "image" in result.capability.input_modalities


# ---------------------------------------------------------------------------
# Gate as a Runnable (no underlying model bound -> returns CheckResult)
# ---------------------------------------------------------------------------


def test_gate_invoke_without_bound_returns_check_result():
    gate = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]}
    )
    result = gate.invoke({"messages": [{"role": "user", "content": "hi"}]})
    assert isinstance(result, CapabilityCheckResult)


def test_gate_invoke_raises_on_violation_even_without_bound():
    gate = CapabilityGateRunnable.for_capability(
        {"input_modalities": ["text"], "output_modalities": ["text"]}
    )
    with pytest.raises(CapabilityViolation):
        gate.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "image", "url": "https://example.com/a.png"}],
                    }
                ]
            }
        )
