from ai_runtime.core.llm.adapters import adapter_schema, get_adapter_spec
from ai_runtime.core.llm.messages import UnifiedModelRequest
from ai_runtime.core.llm.openai import OpenAILLM


def test_adapter_registry_maps_provider_and_protocol_to_explicit_adapter():
    spec = get_adapter_spec("wenxin", "baidu.qianfan_chat_completions")

    assert spec is not None
    assert spec.adapter_id == "wenxin.baidu.qianfan_chat_completions"
    assert spec.endpoint_family == "chat_completions"
    assert spec.canonical_param_map["max_output_tokens"].provider_param == "max_tokens"
    assert spec.canonical_param_map["reasoning"].policy == "drop"


def test_adapter_schema_is_single_source_for_endpoint_modalities():
    schema = adapter_schema()

    assert "openai.responses" in schema["supported_endpoint_protocols"]
    assert schema["endpoint_protocol_input_modalities"]["openai.responses"] == [
        "audio",
        "file",
        "image",
        "text",
        "video",
    ]
    assert any(item["endpoint_protocol"] == "dashscope.openai_compatible" for item in schema["adapters"])


def test_chat_completions_golden_payload_maps_canonical_params():
    llm = OpenAILLM(model="gpt-test", api_key="test", provider="openai")

    family, payload, metadata = llm.build_http_payload(
        UnifiedModelRequest.from_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe"},
                        {"type": "image", "url": "https://example.com/image.png"},
                    ],
                }
            ],
            temperature=0.2,
            max_output_tokens=123,
            top_p=0.9,
            reasoning={"effort": "low"},
        )
    )

    assert family == "chat_completions"
    assert payload == {
        "model": "gpt-test",
        "temperature": 0.2,
        "max_tokens": 123,
        "top_p": 0.9,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
                ],
            }
        ],
    }
    assert metadata["param_mapping"]["max_output_tokens"] == "max_tokens"
    assert "reasoning" in metadata["dropped_params"]


def test_openai_responses_golden_payload_covers_media_transports(tmp_path):
    audio_path = tmp_path / "clip.wav"
    video_path = tmp_path / "clip.mp4"
    audio_path.write_bytes(b"audio")
    video_path.write_bytes(b"video")
    llm = OpenAILLM(
        model="gpt-test",
        api_key="test",
        provider="openai",
        endpoint_protocol="openai.responses",
        input_modalities=["text", "image", "audio", "video", "file"],
    )

    family, payload, metadata = llm.build_http_payload(
        UnifiedModelRequest.from_messages(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "summarize all media"},
                        {"type": "image", "file_id": "img-1", "file_name": "cover.png"},
                        {"type": "audio", "url": str(audio_path), "mime_type": "audio/wav"},
                        {"type": "video", "url": str(video_path), "mime_type": "video/mp4"},
                        {"type": "file", "url": "https://example.com/report.pdf", "file_name": "report.pdf"},
                        {"type": "file", "text": "plain extracted text"},
                        {
                            "type": "file",
                            "base64": "cGRm",
                            "mime_type": "application/pdf",
                            "file_name": "base64.pdf",
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=456,
            response_format={"format": {"type": "text"}},
            reasoning={"effort": "medium"},
            media_transport_by_type=["ignored"],
            media_transport={"file": ["text", "url", "base64", "file_id"], "video": ["base64"]},
        )
    )

    assert family == "responses"
    assert payload["model"] == "gpt-test"
    assert payload["temperature"] == 0.1
    assert payload["max_output_tokens"] == 456
    assert payload["text"] == {"format": {"type": "text"}}
    assert payload["reasoning"] == {"effort": "medium"}
    parts = payload["input"][0]["content"]
    assert parts[0] == {"type": "input_text", "text": "summarize all media"}
    assert parts[1] == {"type": "input_image", "detail": "auto", "file_id": "img-1"}
    assert parts[2] == {"type": "input_audio", "input_audio": {"data": "YXVkaW8=", "format": "wav"}}
    assert parts[3] == {
        "type": "input_file",
        "file_data": "dmlkZW8=",
        "filename": "clip.mp4",
        "mime_type": "video/mp4",
    }
    assert parts[4] == {
        "type": "input_file",
        "file_url": "https://example.com/report.pdf",
        "filename": "report.pdf",
        "mime_type": "application/pdf",
    }
    assert parts[5] == {"type": "input_text", "text": "plain extracted text"}
    assert parts[6] == {
        "type": "input_file",
        "file_data": "cGRm",
        "filename": "base64.pdf",
        "mime_type": "application/pdf",
    }
    assert metadata["param_mapping"]["response_format"] == "text"
    assert {"type": "video", "transport": "base64"} in metadata["media_transports"]
    assert {"type": "file", "transport": "text"} in metadata["media_transports"]


def test_dashscope_openai_compatible_uses_chat_completions_adapter():
    llm = OpenAILLM(
        model="qwen-vl-max",
        api_key="test",
        provider="qwen",
        endpoint_protocol="dashscope.openai_compatible",
        input_modalities=["text", "image"],
    )

    family, payload, metadata = llm.build_http_payload(
        [{"role": "user", "content": [{"type": "image", "url": "https://example.com/qwen.png"}]}],
        max_output_tokens=64,
    )

    assert family == "chat_completions"
    assert metadata["adapter_id"] == "qwen.dashscope.openai_compatible"
    assert payload["max_tokens"] == 64
    assert payload["messages"][0]["content"][0]["type"] == "image_url"


def test_baidu_qianfan_chat_completions_golden_payload():
    llm = OpenAILLM(
        model="ernie-4.0-turbo-8k",
        api_key="test",
        provider="wenxin",
        endpoint_protocol="baidu.qianfan_chat_completions",
    )

    family, payload, metadata = llm.build_http_payload(
        [{"role": "user", "content": "hello"}],
        temperature=0.3,
        max_output_tokens=77,
    )

    assert family == "chat_completions"
    assert metadata["adapter_id"] == "wenxin.baidu.qianfan_chat_completions"
    assert payload == {
        "model": "ernie-4.0-turbo-8k",
        "temperature": 0.3,
        "max_tokens": 77,
        "messages": [{"role": "user", "content": "hello"}],
    }
