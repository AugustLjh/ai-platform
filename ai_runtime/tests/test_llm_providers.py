from ai_runtime.core.config import LLMConfig
from ai_runtime.core.llm import (
    DoubaoLLM,
    GLMLLM,
    KimiLLM,
    QwenLLM,
    SUPPORTED_LLM_PROVIDERS,
    WenxinLLM,
    create_llm_for_provider,
)


def test_supported_llm_providers_include_new_chinese_vendors():
    assert "qwen" in SUPPORTED_LLM_PROVIDERS
    assert "wenxin" in SUPPORTED_LLM_PROVIDERS
    assert "glm" in SUPPORTED_LLM_PROVIDERS
    assert "kimi" in SUPPORTED_LLM_PROVIDERS
    assert "doubao" in SUPPORTED_LLM_PROVIDERS


def test_create_llm_for_provider_uses_vendor_defaults():
    assert isinstance(create_llm_for_provider("qwen", model="qwen-plus"), QwenLLM)
    assert isinstance(create_llm_for_provider("wenxin", model="ernie-4.0-turbo-8k"), WenxinLLM)
    assert isinstance(create_llm_for_provider("glm", model="glm-4-plus"), GLMLLM)
    assert isinstance(create_llm_for_provider("kimi", model="moonshot-v1-8k"), KimiLLM)
    assert isinstance(create_llm_for_provider("doubao", model="doubao-seed-1-6"), DoubaoLLM)


def test_qwen_model_capabilities_distinguish_input_and_output_modalities():
    text_model = create_llm_for_provider("qwen", model="qwen-plus")
    vision_model = create_llm_for_provider("qwen", model="qwen-vl-max")
    audio_model = create_llm_for_provider("qwen", model="qwen-audio-turbo")
    multimodal_text_model = create_llm_for_provider("qwen", model="qwen3.7")

    assert text_model.capabilities.input_modalities == ["text"]
    assert vision_model.capabilities.supports_video_input is True
    assert "image" in vision_model.capabilities.input_modalities
    assert audio_model.capabilities.supports_audio_input is True
    assert multimodal_text_model.capabilities.input_modalities == ["text", "audio", "image", "video", "file"]
    assert multimodal_text_model.capabilities.output_modalities == ["text"]


def test_qwen_explicit_modalities_override_provider_family_defaults():
    llm = create_llm_for_provider(
        "qwen",
        model="qwen-plus",
        config={
            "input_modalities": ["text", "image", "file"],
            "output_modalities": ["text"],
            "supports_vision": True,
            "supports_file_input": True,
        },
    )

    assert llm.capabilities.input_modalities == ["text", "image", "file"]
    assert llm.capabilities.output_modalities == ["text"]
    assert llm.capabilities.supports_vision is True
    assert llm.capabilities.supports_file_input is True


def test_openai_llm_protocol_defaults_to_chat_completions():
    llm = create_llm_for_provider("openai", model="gpt-4.1", config={"endpoint_protocol": "openai.responses"})

    assert llm.config["endpoint_protocol"] == "openai.responses"
    assert llm.capabilities.output_modalities == ["text"]
    assert llm.capabilities.endpoint_protocol == "openai.responses"


def test_llm_config_from_env_reads_vendor_specific_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")
    monkeypatch.setenv("QWEN_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen-max")

    config = LLMConfig.from_env()

    assert config.provider == "qwen"
    assert config.api_key == "qwen-key"
    assert config.api_base == "https://example.invalid/v1"
    assert config.model == "qwen-max"
