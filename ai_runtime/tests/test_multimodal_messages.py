from pathlib import Path

import pytest

from ai_runtime.core.llm.messages import capability_profile_from_settings, normalize_messages, required_input_modalities, supports_modalities, build_model_request_profile, supports_model_request, supports_endpoint_protocol, endpoint_protocol_input_modalities, validate_message_constraints
from ai_runtime.core.llm.openai import OpenAILLM


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


def test_openai_llm_prepares_mixed_content_parts():
    llm = OpenAILLM(model="gpt-test", api_key="test")

    prepared = llm.prepare_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is in this image"},
                    {"type": "image", "url": "https://example.com/image.png", "mime_type": "image/png"},
                ],
            }
        ]
    )

    assert prepared[0]["role"] == "user"
    assert isinstance(prepared[0]["content"], list)
    assert prepared[0]["content"][0]["type"] == "text"
    assert prepared[0]["content"][1]["type"] == "image_url"


def test_openai_responses_prepares_file_audio_and_video_parts(tmp_path):
    audio_path = tmp_path / "sample.mp3"
    video_path = tmp_path / "sample.mp4"
    audio_path.write_bytes(b"audio")
    video_path.write_bytes(b"video")
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "image", "audio", "video", "file"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "file", "file_id": "file-abc", "file_name": "guide.pdf"},
                    {"type": "audio", "url": str(audio_path), "mime_type": "audio/mpeg"},
                    {"type": "video", "url": str(video_path), "mime_type": "video/mp4"},
                ],
            }
        ]
    )

    parts = prepared[0]["content"]
    assert parts[0] == {
        "type": "input_file",
        "file_id": "file-abc",
        "filename": "guide.pdf",
        "mime_type": "application/pdf",
    }
    assert parts[1]["type"] == "input_audio"
    assert parts[1]["input_audio"]["data"] == "YXVkaW8="
    assert parts[1]["input_audio"]["format"] == "mp3"
    assert parts[2]["type"] == "input_file"
    assert parts[2]["file_data"] == "dmlkZW8="
    assert parts[2]["filename"] == "sample.mp4"
    assert parts[2]["mime_type"] == "video/mp4"


def test_openai_responses_honors_media_transport_priority_for_file_id():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "image", "file"],
        adapter_options={"media_transport": ["file_id", "base64", "url"]},
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image", "file_id": "img-1", "file_name": "cover.png", "mime_type": "image/png"},
                    {"type": "file", "file_id": "file-1", "file_name": "report.pdf", "text": "summary"},
                ],
            }
        ]
    )

    assert prepared[0]["content"][0]["file_id"] == "img-1"
    assert prepared[0]["content"][1]["file_id"] == "file-1"


def test_openai_responses_materializes_base64_audio_part():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "audio"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "audio",
                        "base64": "YXVkaW8=",
                        "mime_type": "audio/wav",
                        "file_name": "clip.wav",
                    }
                ],
            }
        ]
    )

    part = prepared[0]["content"][0]
    assert part["type"] == "input_audio"
    assert part["input_audio"]["data"] == "YXVkaW8="
    assert part["input_audio"]["format"] == "wav"


def test_openai_responses_protocol_accepts_video_input():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "video"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [{"type": "video", "file_id": "file-video", "file_name": "demo.mp4"}],
            }
        ]
    )

    assert prepared[0]["content"][0]["type"] == "input_file"
    assert prepared[0]["content"][0]["file_id"] == "file-video"


def test_openai_responses_uses_extracted_file_text_as_input_text():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "file"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [{"type": "file", "text": "extracted document text"}],
            }
        ]
    )

    assert prepared[0]["content"][0] == {"type": "input_text", "text": "extracted document text"}


def test_openai_responses_uses_file_url_for_remote_audio():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "audio"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [{"type": "audio", "url": "https://example.com/clip.mp3"}],
            }
        ]
    )

    assert prepared[0]["content"][0]["type"] == "input_file"
    assert prepared[0]["content"][0]["file_url"] == "https://example.com/clip.mp3"
    assert prepared[0]["content"][0]["filename"] == "clip.mp3"


def test_openai_responses_accepts_base64_file_payloads():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "file"],
    )

    prepared = llm.prepare_responses_messages(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "base64": "cGRm",
                        "mime_type": "application/pdf",
                        "file_name": "guide.pdf",
                    }
                ],
            }
        ]
    )

    part = prepared[0]["content"][0]
    assert part["type"] == "input_file"
    assert part["file_data"] == "cGRm"
    assert part["filename"] == "guide.pdf"
    assert part["mime_type"] == "application/pdf"


def test_openai_responses_rejects_unsupported_audio_format():
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "audio"],
    )

    with pytest.raises(RuntimeError, match="only supports mp3/wav audio"):
        llm.prepare_responses_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio",
                            "base64": "YXVkaW8=",
                            "mime_type": "audio/ogg",
                            "file_name": "clip.ogg",
                        }
                    ],
                }
            ]
        )


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
