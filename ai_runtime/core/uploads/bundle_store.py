from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from fastapi import UploadFile

from core.config import QuotaConfig
from core.parsers.file_parser import FileParser

UPLOAD_BUNDLE_IDS_METADATA_KEY = "upload_bundle_ids"
DEFAULT_STORAGE_ROOT = Path(os.getenv("CHAT_UPLOAD_STORAGE_ROOT", "/tmp/ai-platform-upload-bundles"))
MAX_BUNDLE_FILES = int(os.getenv("CHAT_UPLOAD_MAX_FILES", "200"))
MAX_CONTEXT_FILES = int(os.getenv("CHAT_UPLOAD_MAX_CONTEXT_FILES", "8"))
MAX_CONTEXT_CHARS = int(os.getenv("CHAT_UPLOAD_MAX_CONTEXT_CHARS", "48000"))
MAX_FILE_CONTEXT_CHARS = int(os.getenv("CHAT_UPLOAD_MAX_FILE_CONTEXT_CHARS", "8000"))
MAX_STORED_FILE_CHARS = int(os.getenv("CHAT_UPLOAD_MAX_STORED_FILE_CHARS", "160000"))

_WHITESPACE_RE = re.compile(r"\s+")
_PATH_SPLIT_RE = re.compile(r"[\\/]+")


@dataclass(slots=True)
class ParsedUploadItem:
    relative_path: str
    display_name: str
    size_bytes: int
    content_type: str
    status: str
    parser_name: str | None = None
    text_content: str = ""
    error: str | None = None


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned or "anonymous"


def _normalize_relative_path(value: str | None, fallback_name: str) -> str:
    raw = str(value or "").strip().replace("\x00", "")
    parts = [part for part in _PATH_SPLIT_RE.split(raw) if part not in {"", ".", ".."}]
    if not parts:
        parts = [Path(fallback_name).name or "upload"]
    return "/".join(parts)


def _text_terms(value: str) -> list[str]:
    normalized = _WHITESPACE_RE.sub(" ", str(value or "").lower()).strip()
    if not normalized:
        return []
    return [term for term in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff_./-]+", normalized) if len(term) >= 2]


def _extract_excerpt(text: str, terms: Sequence[str], *, limit: int) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    if not terms:
        return content[:limit]

    lowered = content.lower()
    best_index = -1
    for term in terms:
        best_index = lowered.find(term.lower())
        if best_index != -1:
            break
    if best_index == -1:
        return content[:limit]

    start = max(0, best_index - max(120, limit // 3))
    end = min(len(content), start + limit)
    excerpt = content[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(content):
        excerpt = excerpt + "..."
    return excerpt


class AttachmentBundleStore:
    def __init__(self, storage_root: Path | None = None) -> None:
        self.storage_root = Path(storage_root or DEFAULT_STORAGE_ROOT)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.quota = QuotaConfig.from_env()

    def _bundle_dir(self, tenant_id: str, user_id: str | None, bundle_id: str) -> Path:
        return (
            self.storage_root
            / _safe_segment(tenant_id)
            / _safe_segment(user_id or "anonymous")
            / bundle_id
        )

    def _bundle_json_path(self, tenant_id: str, user_id: str | None, bundle_id: str) -> Path:
        return self._bundle_dir(tenant_id, user_id, bundle_id) / "bundle.json"

    async def create_bundle(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        files: Sequence[UploadFile],
        relative_paths: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if not files:
            raise ValueError("至少上传一个文件")
        if len(files) > MAX_BUNDLE_FILES:
            raise ValueError(f"单次最多上传 {MAX_BUNDLE_FILES} 个文件")

        bundle_id = str(uuid4())
        bundle_dir = self._bundle_dir(tenant_id, user_id, bundle_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        file_entries: list[dict[str, Any]] = []
        skipped_entries: list[dict[str, Any]] = []
        tree_paths: list[str] = []
        total_size = 0

        for index, upload in enumerate(files):
            fallback_name = Path(upload.filename or f"upload-{index + 1}").name
            relative_path = _normalize_relative_path(
                relative_paths[index] if relative_paths and index < len(relative_paths) else None,
                fallback_name,
            )
            tree_paths.append(relative_path)

            parsed = await self._parse_file(upload, relative_path)
            total_size += parsed.size_bytes

            if parsed.status != "ready":
                skipped_entries.append(
                    {
                        "path": parsed.relative_path,
                        "name": parsed.display_name,
                        "size_bytes": parsed.size_bytes,
                        "content_type": parsed.content_type,
                        "status": parsed.status,
                        "error": parsed.error,
                    }
                )
                continue

            attachment_id = str(uuid4())
            content_filename = f"{attachment_id}.txt"
            content_path = bundle_dir / content_filename
            content_path.write_text(parsed.text_content[:MAX_STORED_FILE_CHARS], encoding="utf-8")

            preview = parsed.text_content[:1600]
            entry = {
                "id": attachment_id,
                "path": parsed.relative_path,
                "name": parsed.display_name,
                "size_bytes": parsed.size_bytes,
                "content_type": parsed.content_type,
                "parser": parsed.parser_name,
                "status": parsed.status,
                "char_count": len(parsed.text_content),
                "preview_text": preview,
                "content_file": content_filename,
            }
            file_entries.append(entry)

        if not file_entries:
            errors = [item.get("error") for item in skipped_entries if item.get("error")]
            raise ValueError(errors[0] if errors else "没有可用于解析的文件")

        bundle = {
            "bundle_id": bundle_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "file_count": len(file_entries),
                "skipped_count": len(skipped_entries),
                "total_size_bytes": total_size,
                "directory_tree": self._build_directory_tree(tree_paths),
            },
            "files": file_entries,
            "skipped": skipped_entries,
        }
        self._bundle_json_path(tenant_id, user_id, bundle_id).write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return bundle

    async def _parse_file(self, upload: UploadFile, relative_path: str) -> ParsedUploadItem:
        file_content = await upload.read()
        size_bytes = len(file_content)
        content_type = str(upload.content_type or "application/octet-stream")
        display_name = Path(relative_path).name

        if size_bytes > self.quota.max_upload_file_size:
            return ParsedUploadItem(
                relative_path=relative_path,
                display_name=display_name,
                size_bytes=size_bytes,
                content_type=content_type,
                status="skipped",
                error=f"文件超过大小限制 ({self.quota.max_upload_file_size // (1024 * 1024)}MB)",
            )

        parser = FileParser.get_parser(display_name)
        if parser is None:
            return ParsedUploadItem(
                relative_path=relative_path,
                display_name=display_name,
                size_bytes=size_bytes,
                content_type=content_type,
                status="skipped",
                error="暂不支持的文件类型",
            )

        try:
            text_content = await parser.parse(file_content, display_name)
        except Exception as exc:  # pragma: no cover - parser-specific failures
            return ParsedUploadItem(
                relative_path=relative_path,
                display_name=display_name,
                size_bytes=size_bytes,
                content_type=content_type,
                status="error",
                parser_name=parser.__class__.__name__,
                error=str(exc),
            )

        if not str(text_content or "").strip():
            return ParsedUploadItem(
                relative_path=relative_path,
                display_name=display_name,
                size_bytes=size_bytes,
                content_type=content_type,
                status="skipped",
                parser_name=parser.__class__.__name__,
                error="解析后内容为空",
            )

        return ParsedUploadItem(
            relative_path=relative_path,
            display_name=display_name,
            size_bytes=size_bytes,
            content_type=content_type,
            status="ready",
            parser_name=parser.__class__.__name__,
            text_content=str(text_content),
        )

    def load_bundle(self, *, tenant_id: str, user_id: str | None, bundle_id: str) -> dict[str, Any]:
        bundle_path = self._bundle_json_path(tenant_id, user_id, bundle_id)
        if not bundle_path.exists():
            raise ValueError(f"上传包 {bundle_id} 不存在")
        return json.loads(bundle_path.read_text(encoding="utf-8"))

    def _read_attachment_text(self, bundle: dict[str, Any], entry: dict[str, Any]) -> str:
        bundle_dir = self._bundle_dir(bundle["tenant_id"], bundle.get("user_id"), bundle["bundle_id"])
        content_file = str(entry.get("content_file") or "").strip()
        if not content_file:
            return ""
        content_path = bundle_dir / content_file
        if not content_path.exists():
            return ""
        return content_path.read_text(encoding="utf-8")

    def list_bundle_files(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
    ) -> dict[str, Any]:
        bundles = [self.load_bundle(tenant_id=tenant_id, user_id=user_id, bundle_id=bundle_id) for bundle_id in bundle_ids]
        files = []
        directory_tree = []
        for bundle in bundles:
            directory_tree.extend(bundle.get("summary", {}).get("directory_tree") or [])
            for entry in bundle.get("files") or []:
                files.append(
                    {
                        "bundle_id": bundle["bundle_id"],
                        "id": entry.get("id"),
                        "path": entry.get("path"),
                        "name": entry.get("name"),
                        "size_bytes": entry.get("size_bytes"),
                        "content_type": entry.get("content_type"),
                        "char_count": entry.get("char_count"),
                        "preview_text": entry.get("preview_text") or "",
                    }
                )
        return {
            "bundle_ids": [bundle["bundle_id"] for bundle in bundles],
            "file_count": len(files),
            "directory_tree": self._build_directory_tree([item.get("path") or "" for item in files]),
            "files": files,
        }

    def search_bundle_files(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
        query: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        terms = _text_terms(query)
        results = []
        for bundle_id in bundle_ids:
            bundle = self.load_bundle(tenant_id=tenant_id, user_id=user_id, bundle_id=bundle_id)
            for entry in bundle.get("files") or []:
                content = self._read_attachment_text(bundle, entry)
                title_source = f"{entry.get('name', '')} {entry.get('path', '')}".lower()
                lowered = content.lower()
                score = 0
                for term in terms:
                    score += title_source.count(term) * 8
                    score += lowered.count(term)
                if score <= 0 and terms:
                    continue
                excerpt = _extract_excerpt(content, terms, limit=min(MAX_FILE_CONTEXT_CHARS, 2400))
                results.append(
                    {
                        "bundle_id": bundle_id,
                        "id": entry.get("id"),
                        "path": entry.get("path"),
                        "name": entry.get("name"),
                        "score": score,
                        "excerpt": excerpt,
                        "char_count": entry.get("char_count"),
                    }
                )
        results.sort(key=lambda item: (item.get("score") or 0, item.get("char_count") or 0), reverse=True)
        return results[:limit]

    def read_bundle_file(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
        attachment_id: str,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        for bundle_id in bundle_ids:
            bundle = self.load_bundle(tenant_id=tenant_id, user_id=user_id, bundle_id=bundle_id)
            for entry in bundle.get("files") or []:
                if str(entry.get("id")) != attachment_id:
                    continue
                content = self._read_attachment_text(bundle, entry)
                return {
                    "bundle_id": bundle_id,
                    "id": entry.get("id"),
                    "path": entry.get("path"),
                    "name": entry.get("name"),
                    "size_bytes": entry.get("size_bytes"),
                    "content_type": entry.get("content_type"),
                    "char_count": entry.get("char_count"),
                    "content": content[:max_chars],
                    "truncated": len(content) > max_chars,
                }
        raise ValueError(f"附件 {attachment_id} 不存在")

    def build_prompt_context(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
        query: str,
        max_context_chars: int = MAX_CONTEXT_CHARS,
        max_files: int = MAX_CONTEXT_FILES,
    ) -> dict[str, Any]:
        if not bundle_ids:
            return {"context_text": "", "files": [], "directory_tree": []}

        bundle_ids = [str(bundle_id).strip() for bundle_id in bundle_ids if str(bundle_id).strip()]
        if not bundle_ids:
            return {"context_text": "", "files": [], "directory_tree": []}

        manifest = self.list_bundle_files(tenant_id=tenant_id, user_id=user_id, bundle_ids=bundle_ids)
        hits = self.search_bundle_files(
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_ids=bundle_ids,
            query=query,
            limit=max_files,
        )
        if not hits:
            hits = []
            for item in manifest["files"][:max_files]:
                content = self.read_bundle_file(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    bundle_ids=bundle_ids,
                    attachment_id=item["id"],
                    max_chars=min(MAX_FILE_CONTEXT_CHARS, 2400),
                )
                hits.append(
                    {
                        "bundle_id": content["bundle_id"],
                        "id": content["id"],
                        "path": content["path"],
                        "name": content["name"],
                        "score": 0,
                        "excerpt": content["content"],
                        "char_count": content["char_count"],
                    }
                )

        consumed = 0
        sections = [
            "Uploaded file context is available below. Answer from these files when relevant.",
            "Directory tree:",
            json.dumps(manifest["directory_tree"], ensure_ascii=False, indent=2),
        ]
        file_summaries = []
        for hit in hits:
            excerpt = str(hit.get("excerpt") or "").strip()
            if not excerpt:
                continue
            excerpt = excerpt[: min(MAX_FILE_CONTEXT_CHARS, max_context_chars)]
            next_len = consumed + len(excerpt)
            if next_len > max_context_chars and file_summaries:
                break
            consumed = min(max_context_chars, next_len)
            file_summaries.append(
                {
                    "id": hit.get("id"),
                    "bundle_id": hit.get("bundle_id"),
                    "name": hit.get("name"),
                    "path": hit.get("path"),
                    "score": hit.get("score", 0),
                    "excerpt": excerpt,
                    "char_count": hit.get("char_count"),
                }
            )
            sections.extend(
                [
                    f"File: {hit.get('path') or hit.get('name')}",
                    excerpt,
                ]
            )

        return {
            "context_text": "\n\n".join(section for section in sections if section),
            "files": file_summaries,
            "directory_tree": manifest["directory_tree"],
        }

    def summarize_bundles(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
        query: str,
    ) -> dict[str, Any]:
        prompt_context = self.build_prompt_context(
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_ids=bundle_ids,
            query=query,
        )
        manifest = self.list_bundle_files(tenant_id=tenant_id, user_id=user_id, bundle_ids=bundle_ids)
        return {
            "bundle_ids": [bundle_id for bundle_id in bundle_ids if str(bundle_id).strip()],
            "file_count": manifest["file_count"],
            "directory_tree": manifest["directory_tree"],
            "files": prompt_context["files"],
            "context_text": prompt_context["context_text"],
        }

    def _build_directory_tree(self, relative_paths: Iterable[str]) -> list[dict[str, Any]]:
        root: dict[str, Any] = {}

        for raw_path in relative_paths:
            normalized = _normalize_relative_path(raw_path, "upload")
            parts = normalized.split("/")
            current = root
            for index, part in enumerate(parts):
                is_leaf = index == len(parts) - 1
                node = current.setdefault(
                    part,
                    {
                        "name": part,
                        "path": "/".join(parts[: index + 1]),
                        "node_type": "file" if is_leaf else "directory",
                        "children": {},
                    },
                )
                if not is_leaf:
                    node["node_type"] = "directory"
                current = node["children"]

        def to_list(children: dict[str, Any]) -> list[dict[str, Any]]:
            items = []
            for name in sorted(children.keys()):
                node = children[name]
                child_items = to_list(node["children"])
                payload = {
                    "name": node["name"],
                    "path": node["path"],
                    "node_type": node["node_type"] if child_items else ("file" if node["node_type"] == "file" else "directory"),
                }
                if child_items:
                    payload["children"] = child_items
                items.append(payload)
            return items

        return to_list(root)


_bundle_store: AttachmentBundleStore | None = None


def get_attachment_bundle_store() -> AttachmentBundleStore:
    global _bundle_store
    if _bundle_store is None:
        _bundle_store = AttachmentBundleStore()
    return _bundle_store


def normalize_bundle_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            value = decoded
        except (TypeError, ValueError, json.JSONDecodeError):
            value = [part.strip() for part in value.split(",") if part.strip()]

    if not isinstance(value, list):
        return []

    bundle_ids = []
    seen = set()
    for item in value:
        bundle_id = str(item or "").strip()
        if not bundle_id or bundle_id in seen:
            continue
        seen.add(bundle_id)
        bundle_ids.append(bundle_id)
    return bundle_ids
