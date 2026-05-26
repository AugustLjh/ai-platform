import pytest

from ai_runtime.core.chat.service import ChatRuntimeService
from ai_runtime.core.llm.messages import normalize_messages


def test_history_deserializer_preserves_content_parts():
    service = ChatRuntimeService()
    history = service._deserialize_history(
        [
            {
                "role": "user",
                "content": "",
                "content_parts": [
                    {"type": "text", "text": "look"},
                    {"type": "image", "url": "https://example.com/a.png"},
                ],
            }
        ]
    )

    assert history[0]["content_parts"][1]["type"] == "image"
    assert normalize_messages(history)[0].content[1].type == "image"


def test_request_user_parts_does_not_duplicate_text():
    service = ChatRuntimeService()
    parts = service._build_request_user_parts(
        "hello",
        [{"type": "text", "text": "hello"}, {"type": "image", "url": "https://example.com/a.png"}],
        None,
    )

    assert [part["type"] for part in parts] == ["text", "image"]


def test_materialize_request_user_parts_for_candidate_uses_attachment_text_or_file_id():
    service = ChatRuntimeService()
    upload_context = {
        "files": [
            {
                "id": "file-1",
                "name": "doc.txt",
                "media_kind": "file",
                "content_type": "text/plain",
                "content": "hello world",
                "excerpt": "hello world",
                "preview_text": "hello world",
                "transport": {"preferred_types": ["text", "file_id"]},
                "metadata": {"sha256": "abc"},
            },
            {
                "id": "image-1",
                "name": "cover.png",
                "media_kind": "image",
                "content_type": "image/png",
                "base64": "abcd",
                "transport": {"preferred_types": ["file_id", "base64"]},
                "metadata": {"sha256": "def"},
            },
        ],
        "media_parts": [
            {
                "type": "image",
                "file_id": "image-1",
                "file_name": "cover.png",
                "base64": "abcd",
                "mime_type": "image/png",
                "transport": {"preferred_types": ["file_id", "base64"]},
                "metadata": {"sha256": "def"},
            }
        ],
    }

    candidate = {"config": {"adapter_options": {"media_transport_by_type": {"file": ["text"], "image": ["file_id"]}}}}
    request_user_parts = [
        {"type": "text", "text": "hello"},
        {"type": "file", "attachment_id": "file-1", "file_id": "file-1", "text": "hello world"},
        {"type": "image", "attachment_id": "image-1", "file_id": "image-1"},
    ]

    materialized = service._materialize_request_user_parts_for_candidate(candidate, request_user_parts, upload_context)

    assert materialized[1]["type"] == "file"
    assert materialized[1]["text"] == "hello world"
    assert materialized[2]["type"] == "image"
    assert materialized[2]["file_id"] == "image-1"


@pytest.mark.asyncio
async def test_resolve_llm_candidates_rejects_text_only_model_for_image_request():
    service = ChatRuntimeService()

    class DummyLLM:
        capabilities = {"input_modalities": ["text"], "output_modalities": ["text"]}

    async def fake_governance_settings(*args, **kwargs):
        return {}

    async def fake_get_model_row(*args, **kwargs):
        return {
            "id": "model-text-only",
            "name": "text-only",
            "display_name": "Text Only",
            "provider": "mock",
            "model_id": "mock-text-only",
            "api_base": None,
            "api_key_encrypted": None,
            "config": {"input_modalities": ["text"], "output_modalities": ["text"]},
        }

    def fake_create_llm_instance(model_row):
        return DummyLLM()

    service._get_governance_settings = fake_governance_settings
    service._get_model_row = fake_get_model_row
    service._create_llm_instance = fake_create_llm_instance

    try:
        await service.resolve_llm_candidates(
            tenant_id="tenant-1",
            user_id="user-1",
            knowledge_base_id=None,
            route_scene="chat",
            requested_model=None,
            required_modalities={"text", "image"},
        )
    except RuntimeError as exc:
        assert "image" in str(exc)
        assert "静默切换" not in str(exc)
    else:
        raise AssertionError("expected route resolution to reject text-only model for image input")


@pytest.mark.asyncio
async def test_resolve_llm_candidates_rejects_protocol_without_media_adapter():
    service = ChatRuntimeService()

    class DummyLLM:
        capabilities = {
            "endpoint_protocol": "deepseek.chat_completions",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        }

    async def fake_governance_settings(*args, **kwargs):
        return {}

    async def fake_get_model_row(*args, **kwargs):
        return {
            "id": "model-bad-protocol",
            "name": "bad-protocol",
            "display_name": "Bad Protocol",
            "provider": "mock",
            "model_id": "mock-bad-protocol",
            "api_base": None,
            "api_key_encrypted": None,
            "config": {
                "endpoint_protocol": "deepseek.chat_completions",
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
        }

    service._get_governance_settings = fake_governance_settings
    service._get_model_row = fake_get_model_row
    service._build_model_candidate = lambda model_row, source: {**model_row, "llm": DummyLLM(), "source": source}

    with pytest.raises(RuntimeError) as exc_info:
        await service.resolve_llm_candidates(
            tenant_id="tenant-1",
            user_id="user-1",
            knowledge_base_id=None,
            route_scene="chat",
            requested_model="bad-protocol",
            required_modalities={"text", "image"},
        )

    assert "endpoint_protocol=deepseek.chat_completions" in str(exc_info.value)
    assert "image" in str(exc_info.value)
    assert "静默切换" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_llm_candidates_builds_database_model_candidate():
    service = ChatRuntimeService()

    class DummyLLM:
        capabilities = {
            "endpoint_protocol": "openai.responses",
            "input_modalities": ["text", "image", "file"],
            "output_modalities": ["text"],
        }

    async def fake_governance_settings(*args, **kwargs):
        return {}

    async def fake_get_model_row(*args, **kwargs):
        return {
            "id": "model-vision",
            "name": "vision",
            "display_name": "Vision",
            "provider": "openai",
            "model_id": "gpt-vision",
            "api_base": None,
            "api_key_encrypted": None,
            "config": {
                "endpoint_protocol": "openai.responses",
                "input_modalities": ["text", "image", "file"],
                "output_modalities": ["text"],
            },
        }

    service._get_governance_settings = fake_governance_settings
    service._get_model_row = fake_get_model_row
    service._create_llm_instance = lambda model_row: DummyLLM()

    resolution = await service.resolve_llm_candidates(
        tenant_id="tenant-1",
        user_id="user-1",
        knowledge_base_id=None,
        route_scene="chat",
        requested_model="vision",
        required_modalities={"text", "image"},
    )

    assert resolution["candidates"][0]["id"] == "model-vision"
    assert resolution["candidates"][0]["source"] == "request_override"
