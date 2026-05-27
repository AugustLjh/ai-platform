"""Tests for the messages-module multimodal helpers.

This file used to also exercise ``OpenAILLM.prepare_messages`` /
``prepare_responses_messages`` payload-shaping helpers; that legacy code
has been removed in P8.3 in favour of LangChain ``ChatOpenAI``. The
equivalent payload + transport coverage lives in
``tests/llm/test_adapter_payloads.py`` and
``tests/llm/test_media_transport.py``.
"""

from ai_runtime.core.llm.messages import (
    build_model_request_profile,
    capability_profile_from_settings,
    endpoint_protocol_input_modalities,
    normalize_messages,
    required_input_modalities,
    supports_endpoint_protocol,
    supports_model_request,
    supports_modalities,
    validate_message_constraints,
)


def test_normalize_messages_accepts_legacy_text_and_content_parts():
    messages = normalize_messages(
        [
            {"role": "system", "content": "You are helpful."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this"},
                    {"type": "image", "url": "https://example.com/cat.png", "mime_type": "image/png"},
                ],
            },
        ]
    )

    assert messages[0].content[0].text == "You are helpful."
    assert messages[1].content[0].type == "text"
    assert messages[1].content[1].type == "image"


def test_required_input_modalities_collects_multimodal_parts():
    required = required_input_modalities(
        [
            {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "file", "file_id": "f-1", "text": "doc"}]},
            {"role": "assistant", "content": "ok"},
        ]
    )

    assert required == {"text", "file"}


def test_supports_modalities_rejects_text_only_profile_for_image():
    assert not supports_modalities({"input_modalities": ["text"]}, {"text", "image"})
    assert supports_modalities({"input_modalities": ["text", "image"]}, {"text", "image"})


def test_capability_profile_promotes_vision_and_file_flags_to_modalities():
    profile = capability_profile_from_settings(
        {
            "input_modalities": "text",
            "output_modalities": "text",
            "supports_vision": True,
            "supports_file_input": True,
        }
    )

    assert profile.supports_vision is True
    assert profile.supports_file_input is True
    assert profile.input_modalities == ["text", "image", "file"]
    assert profile.output_modalities == ["text"]


def test_capability_profile_keeps_audio_output_text_only():
    profile = capability_profile_from_settings(
        {
            "input_modalities": ["text", "audio"],
            "output_modalities": ["text", "audio"],
            "supports_audio_output": True,
        }
    )

    assert profile.output_modalities == ["text"]
    assert profile.supports_audio_output is True


def test_supports_model_request_checks_task_and_text_output():
    capability = {
        "task_type": "chat.completion",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "supported_response_formats": ["text"],
    }
    request = build_model_request_profile(
        [{"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image", "url": "https://example.com/a.png"}]}]
    )

    assert supports_model_request(capability, request)
    assert not supports_model_request(
        {**capability, "task_type": "generation.image"},
        request,
    )


def test_supports_endpoint_protocol_matches_documented_adapters():
    assert supports_endpoint_protocol("openai.responses")
    assert supports_endpoint_protocol("dashscope.openai_compatible")
    assert supports_endpoint_protocol("jina.responses")
    assert not supports_endpoint_protocol("dashscope.multimodal_conversation")
    assert endpoint_protocol_input_modalities("openai.responses") == {"text", "image", "audio", "video", "file"}
    assert endpoint_protocol_input_modalities("deepseek.chat_completions") == {"text"}


def test_required_input_modalities_treats_extracted_file_text_as_text():
    required = required_input_modalities(
        [
            {"role": "user", "content": [{"type": "file", "text": "extracted text"}]},
        ]
    )

    assert required == {"text"}


def test_required_input_modalities_requires_file_when_file_id_is_present():
    required = required_input_modalities(
        [
            {"role": "user", "content": [{"type": "file", "file_id": "f-1", "text": "extracted text"}]},
        ]
    )

    assert required == {"file"}


def test_normalize_messages_accepts_dashscope_style_media_fields():
    messages = normalize_messages(
        [
            {
                "role": "user",
                "content": [
                    {"image": "https://example.com/cat.png"},
                    {"video": "https://example.com/demo.mp4"},
                    {"audio": "https://example.com/demo.mp3"},
                    {"text": "describe these"},
                ],
            }
        ]
    )

    assert [part.type for part in messages[0].content] == ["image", "video", "audio", "text"]


def test_validate_message_constraints_flags_size_count_and_mime_violations():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "url": "https://example.com/image.png", "mime_type": "image/png", "data": {"size_bytes": 5}},
                {"type": "video", "url": "https://example.com/video.mp4", "mime_type": "video/mp4", "data": {"duration_seconds": 21}},
            ],
        }
    ]
    errors = validate_message_constraints(
        messages,
        {
            "allowed_mime_types": ["image/jpeg"],
            "max_images": 0,
            "max_video_seconds": 10,
        },
    )

    assert any("allowed_mime_types" in item for item in errors)
    assert any("max_images" in item for item in errors)
    assert any("max_video_seconds" in item for item in errors)
