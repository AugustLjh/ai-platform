import pytest

from ai_runtime.core.uploads.bundle_store import AttachmentBundleStore
from ai_runtime.graphs.chat import helpers as chat_helpers


class MemoryUpload:
    def __init__(self, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_jpg_upload_bundle_creates_image_media_part(tmp_path):
    store = AttachmentBundleStore(storage_root=tmp_path)
    bundle = await store.create_bundle(
        tenant_id="tenant-1",
        user_id="user-1",
        files=[MemoryUpload("receipt.jpg", b"\xff\xd8\xffdemo\xff\xd9", "image/jpeg")],
        relative_paths=["receipt.jpg"],
    )

    assert bundle["summary"]["file_count"] == 1
    assert bundle["files"][0]["media_kind"] == "image"
    assert bundle["files"][0]["content_type"] == "image/jpeg"
    assert bundle["files"][0]["sha256"]
    assert bundle["files"][0]["metadata"]["transport"]["preferred_types"] == ["file_id", "base64"]

    context = store.build_prompt_context(
        tenant_id="tenant-1",
        user_id="user-1",
        bundle_ids=[bundle["bundle_id"]],
        query="describe the image",
    )

    assert context["media_parts"][0]["type"] == "image"
    assert context["media_parts"][0]["mime_type"] == "image/jpeg"
    assert context["media_parts"][0]["base64"]
    assert context["files"][0]["sha256"]
    assert context["files"][0]["transport"]["preferred_types"] == ["file_id", "base64"]


def test_upload_context_images_are_added_as_image_parts():
    parts = chat_helpers.build_request_user_parts(
        "看图",
        [{"type": "text", "text": "看图"}, {"type": "image", "file_id": "front-end-placeholder"}],
        {
            "media_parts": [
                {
                    "type": "image",
                    "file_id": "stored-image",
                    "file_name": "receipt.jpg",
                    "mime_type": "image/jpeg",
                    "base64": "abcd",
                }
            ],
            "files": [
                {
                    "id": "stored-image",
                    "name": "receipt.jpg",
                    "media_kind": "image",
                    "content_type": "image/jpeg",
                    "size_bytes": 12,
                }
            ],
        },
    )

    assert [part["type"] for part in parts] == ["text", "image"]
    assert parts[1]["file_id"] == "stored-image"
    assert parts[1]["base64"] == "abcd"
    assert parts[1]["data"]["size_bytes"] == 12


def test_missing_upload_bundle_is_skipped(tmp_path):
    store = AttachmentBundleStore(storage_root=tmp_path)

    context = store.build_prompt_context(
        tenant_id="tenant-1",
        user_id="user-1",
        bundle_ids=["missing-bundle"],
        query="hello",
    )

    assert context["bundle_ids"] == []
    assert context["missing_bundle_ids"] == ["missing-bundle"]
    assert context["context_text"] == ""
    assert context["files"] == []
