import pytest
from pydantic import ValidationError

from ai_runtime.api.models import LLMModelConfig, _normalize_model_config


def test_normalize_model_config_promotes_vision_flag_to_image_modality():
    config = _normalize_model_config(
        {
            "temperature": 0.7,
            "max_tokens": 2000,
            "input_modalities": "text",
            "output_modalities": "text",
            "supports_vision": True,
        }
    )

    assert config["supports_vision"] is True
    assert config["input_modalities"] == ["text", "image"]
    assert config["capabilities"]["input_modalities"] == ["text", "image"]


def test_normalize_model_config_preserves_explicit_file_and_audio_modalities():
    config = _normalize_model_config(
        {
            "input_modalities": ["text", "file", "audio"],
            "output_modalities": ["text", "audio"],
            "supports_audio_output": True,
        }
    )

    assert config["supports_file_input"] is True
    assert config["supports_audio_input"] is True
    assert config["supports_audio_output"] is True
    assert config["output_modalities"] == ["text"]
    assert config["capabilities"]["output_modalities"] == ["text"]


def test_normalize_model_config_preserves_video_input_modality():
    config = _normalize_model_config(
        {
            "input_modalities": ["text", "video"],
            "output_modalities": ["text"],
        }
    )

    assert config["supports_video_input"] is True
    assert config["capabilities"]["supports_video_input"] is True
    assert config["capabilities"]["input_modalities"] == ["text", "video"]


def test_normalize_model_config_adds_task_type_endpoint_protocol_and_constraints():
    config = _normalize_model_config(
        {
            "endpoint_protocol": "openai.responses",
            "input_modalities": ["text", "image", "file"],
            "constraints": {"max_images": 20},
            "adapter_options": {"media_transport": ["url", "file_id"]},
        }
    )

    assert config["task_type"] == "chat.completion"
    assert config["endpoint_protocol"] == "openai.responses"
    assert config["output_modalities"] == ["text"]
    assert config["constraints"]["max_images"] == 20
    assert config["adapter_options"]["media_transport"] == ["url", "file_id"]
    assert config["capabilities"]["endpoint_protocol"] == "openai.responses"
    assert config["capabilities"]["adapter_options"]["media_transport"] == ["url", "file_id"]


def test_normalize_model_config_allows_openai_responses_audio_and_video_inputs():
    config = _normalize_model_config(
        {
            "endpoint_protocol": "openai.responses",
            "input_modalities": ["text", "audio", "video", "file"],
            "supports_audio_input": True,
            "supports_video_input": True,
            "supports_file_input": True,
        }
    )

    assert config["input_modalities"] == ["text", "audio", "video", "file"]
    assert config["capabilities"]["input_modalities"] == ["text", "audio", "video", "file"]
    assert config["capabilities"]["supports_audio_input"] is True
    assert config["capabilities"]["supports_video_input"] is True
    assert config["capabilities"]["supports_file_input"] is True


def test_normalize_model_config_forces_text_output_even_if_explicit_output_modalities_are_non_text():
    config = _normalize_model_config(
        {
            "input_modalities": ["text"],
            "output_modalities": ["text", "image"],
        }
    )

    assert config["output_modalities"] == ["text"]
    assert config["default_output_modalities"] == ["text"]


def test_llm_model_config_rejects_non_text_output_modalities():
    with pytest.raises(ValidationError):
        LLMModelConfig(output_modalities=["text", "image"])


def test_llm_model_config_rejects_unknown_endpoint_protocol():
    with pytest.raises(ValidationError):
        LLMModelConfig(endpoint_protocol="dashscope.multimodal_conversation")
