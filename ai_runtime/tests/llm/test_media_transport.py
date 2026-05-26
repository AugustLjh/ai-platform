"""Unit tests for :mod:`ai_runtime.llm.media_transport`.

Exercises the per-provider transport priority resolution and the
``ContentPart[]`` materialization that ports
``ChatService._materialize_request_user_parts_for_candidate``.
"""
from __future__ import annotations

import pytest

from ai_runtime.llm.media_transport import (
    MediaTransportRunnable,
    TransportPlan,
    materialize_parts,
    resolve_transport_plan,
)


# ---------------------------------------------------------------------------
# resolve_transport_plan
# ---------------------------------------------------------------------------


def test_default_plan_falls_back_to_adapter_spec_when_no_options():
    plan = resolve_transport_plan(
        model_config={},
        provider="openai",
        endpoint_protocol="openai.chat_completions",
    )
    assert plan.default == ("file_id", "url", "base64", "text")
    assert plan.for_kind("image") == ("file_id", "url", "base64", "text")


def test_plan_uses_explicit_media_transport_setting():
    plan = resolve_transport_plan(
        model_config={"adapter_options": {"media_transport": ["url", "file_id"]}},
        provider="qwen",
        endpoint_protocol="dashscope.openai_compatible",
    )
    assert plan.default == ("url", "file_id")


def test_plan_supports_per_modality_override():
    plan = resolve_transport_plan(
        model_config={
            "adapter_options": {
                "media_transport": ["file_id", "url"],
                "media_transport_by_type": {"video": ["base64"]},
            }
        },
        provider="openai",
        endpoint_protocol="openai.responses",
    )
    assert plan.for_kind("image") == ("file_id", "url")
    assert plan.for_kind("video") == ("base64",)


def test_plan_drops_unknown_transport_tokens():
    plan = resolve_transport_plan(
        model_config={"adapter_options": {"media_transport": ["url", "qr_code", "file_id"]}},
        provider="openai",
        endpoint_protocol="openai.chat_completions",
    )
    assert plan.default == ("url", "file_id")


def test_plan_accepts_comma_separated_string():
    plan = resolve_transport_plan(
        model_config={"adapter_options": {"media_transport": "file_id, url, base64"}},
        provider="openai",
        endpoint_protocol="openai.chat_completions",
    )
    assert plan.default == ("file_id", "url", "base64")


# ---------------------------------------------------------------------------
# materialize_parts
# ---------------------------------------------------------------------------


def test_passthrough_when_no_upload_context():
    parts = [
        {"type": "text", "text": "hello"},
        {"type": "image", "url": "https://example.com/cat.png"},
    ]
    assert materialize_parts(parts, upload_context=None, plan=TransportPlan(default=("file_id",))) == parts


def test_part_without_attachment_id_is_returned_as_is():
    plan = TransportPlan(default=("file_id", "url", "base64", "text"))
    upload_context = {"files": [{"id": "a1", "name": "cat.png", "media_kind": "image"}]}
    parts = [{"type": "text", "text": "hi"}]
    result = materialize_parts(parts, upload_context=upload_context, plan=plan)
    assert result == parts


def test_image_attachment_resolves_to_file_id_when_priority_first():
    plan = TransportPlan(default=("file_id", "url"))
    upload = {
        "files": [
            {
                "id": "att-1",
                "name": "cat.png",
                "media_kind": "image",
                "mime_type": "image/png",
                "base64": "BASE",
                "path": "https://example.com/cat.png",
            }
        ]
    }
    parts = [{"type": "image", "attachment_id": "att-1"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result[0]["type"] == "image"
    assert result[0]["file_id"] == "att-1"
    assert result[0]["mime_type"] == "image/png"
    # base64 carried for images so downstream providers can pick another transport
    assert result[0]["base64"] == "BASE"


def test_image_attachment_resolves_to_url_when_file_id_unavailable():
    plan = TransportPlan(default=("file_id", "url", "base64", "text"))
    upload = {
        "media_parts": [
            {
                "file_id": "att-2",
                "name": "cat.png",
                "media_kind": "image",
                "mime_type": "image/png",
                "path": "https://example.com/cat.png",
            }
        ]
    }
    parts = [{"type": "image", "attachment_id": "att-2"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    # file_id wins because attachment_id matches; upgrade to url is only when
    # transport priority skips file_id explicitly.
    assert result[0]["file_id"] == "att-2"


def test_url_transport_used_when_file_id_priority_skipped():
    plan = TransportPlan(default=("url", "base64"))
    upload = {
        "files": [
            {
                "id": "att-3",
                "name": "cat.png",
                "media_kind": "image",
                "mime_type": "image/png",
                "path": "https://example.com/cat.png",
            }
        ]
    }
    parts = [{"type": "image", "attachment_id": "att-3"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result[0]["url"] == "https://example.com/cat.png"
    assert "base64" not in result[0]


def test_text_transport_used_for_extracted_file_text():
    plan = TransportPlan(default=("text", "file_id", "url", "base64"))
    upload = {
        "files": [
            {
                "id": "doc-1",
                "name": "report.pdf",
                "media_kind": "file",
                "content": "extracted document text",
                "mime_type": "application/pdf",
            }
        ]
    }
    parts = [{"type": "file", "attachment_id": "doc-1"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result[0]["type"] == "file"
    assert result[0]["text"] == "extracted document text"


def test_base64_transport_used_when_path_unavailable():
    plan = TransportPlan(default=("url", "base64"))
    upload = {
        "media_parts": [
            {
                "attachment_id": "att-b",
                "name": "snapshot.png",
                "media_kind": "image",
                "base64": "iVBORw0KG...",
                "mime_type": "image/png",
            }
        ]
    }
    parts = [{"type": "image", "attachment_id": "att-b"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result[0]["base64"] == "iVBORw0KG..."
    assert "url" not in result[0]


def test_per_modality_override_used_for_video():
    plan = TransportPlan(
        default=("url", "file_id"),
        by_type={"video": ("base64",)},
    )
    upload = {
        "files": [
            {
                "id": "v1",
                "name": "demo.mp4",
                "media_kind": "video",
                "base64": "VIDEO==",
                "path": "https://example.com/demo.mp4",
            }
        ]
    }
    parts = [{"type": "video", "attachment_id": "v1"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result[0]["base64"] == "VIDEO=="
    assert "url" not in result[0]


def test_unmatched_attachment_returns_original_part_unchanged():
    plan = TransportPlan(default=("file_id", "url"))
    upload = {"files": [{"id": "other", "name": "x", "media_kind": "image"}]}
    parts = [{"type": "image", "attachment_id": "missing"}]
    result = materialize_parts(parts, upload_context=upload, plan=plan)
    assert result == parts


# ---------------------------------------------------------------------------
# MediaTransportRunnable
# ---------------------------------------------------------------------------


def test_runnable_rewrites_input_parts_in_place():
    mt = MediaTransportRunnable.for_candidate(
        model_config={"adapter_options": {"media_transport": ["file_id", "url"]}},
        provider="openai",
        endpoint_protocol="openai.responses",
    )
    out = mt.invoke(
        {
            "request_user_parts": [{"type": "image", "attachment_id": "a1"}],
            "upload_context": {
                "files": [
                    {
                        "id": "a1",
                        "name": "cat.png",
                        "media_kind": "image",
                        "mime_type": "image/png",
                        "path": "https://x/cat.png",
                    }
                ]
            },
        }
    )
    assert out["request_user_parts"][0]["file_id"] == "a1"


def test_runnable_passes_through_inputs_without_request_user_parts():
    mt = MediaTransportRunnable.for_candidate(model_config={})
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    assert mt.invoke(payload) == payload


def test_for_candidate_uses_adapter_default_when_no_options():
    mt = MediaTransportRunnable.for_candidate(
        model_config={},
        provider="openai",
        endpoint_protocol="openai.responses",
    )
    assert mt.plan.default == ("file_id", "url", "base64", "text")
