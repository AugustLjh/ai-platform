from __future__ import annotations

import json
import posixpath
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


TEXT_CANDIDATE_KEYS = (
    "final_output_text",
    "answer",
    "summary",
    "final_answer",
    "response",
    "message",
    "content",
    "result",
)
PLAN_KEYS = ("task_plan", "plan", "implementation_plan")
CITATION_KEYS = ("citations", "sources", "references")
FINDING_KEYS = ("review_findings", "findings", "issues", "risks")
CODE_FILE_KEYS = ("code_files", "files")
TABLE_KEYS = ("table", "tables", "rows")
EXCERPT_KEYS = ("document_excerpt", "document_excerpts", "excerpts", "excerpt")
PAGED_KEYS = ("paged_collection", "paged_results", "page", "page_result")
MEDIA_KEYS = ("media_gallery", "image_gallery", "images", "media")
FILE_BUNDLE_KEYS = ("file_bundle", "attachments", "resources", "downloads")
DIRECTORY_TREE_KEYS = ("directory_tree", "tree", "file_tree")
DOCUMENT_PAGE_KEYS = ("document_pages", "pages", "document_preview_pages")
ARCHIVE_BUNDLE_KEYS = ("archive_bundle", "archive_entries", "compressed_bundle")
ARTIFACT_TYPE_PRIORITY = {
    "answer": 0,
    "workspace_summary": 1,
    "review_findings": 1,
    "citations": 2,
    "code_files": 3,
    "code_patch": 4,
    "verification_report": 5,
    "task_plan": 6,
    "table": 7,
    "paged_collection": 8,
    "directory_tree": 9,
    "document_pages": 10,
    "document_excerpt": 11,
    "media_gallery": 12,
    "archive_bundle": 13,
    "file_bundle": 14,
}
IMPLICIT_LIST_KEYS = ("items", "results", "entries", "records", "matches", "documents", "data")
CODE_FILE_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "text",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".zsh": "zsh",
}
MEDIA_EXTENSIONS = {
    ".apng": "image",
    ".avif": "image",
    ".gif": "image",
    ".jpeg": "image",
    ".jpg": "image",
    ".png": "image",
    ".svg": "image",
    ".webp": "image",
    ".bmp": "image",
    ".ico": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".mkv": "video",
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _compact_title(key: str, fallback: str) -> str:
    text = str(key or "").strip().replace("_", " ").replace("-", " ")
    if not text:
        return fallback
    return " ".join(part.capitalize() for part in text.split())


def _extract_text_candidate(value: Any) -> Optional[str]:
    if _is_non_empty_string(value):
        return value.strip()

    if isinstance(value, list):
        text_items: list[str] = []
        for item in value:
            candidate = _extract_text_candidate(item)
            if candidate:
                text_items.append(candidate)
        if text_items:
            return "\n".join(text_items[:3])
        return None

    if not isinstance(value, dict):
        return None

    for key in TEXT_CANDIDATE_KEYS:
        candidate = value.get(key)
        if _is_non_empty_string(candidate):
            return str(candidate).strip()

    for nested_key in ("answer", "summary", "response", "result"):
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            nested_candidate = _extract_text_candidate(nested)
            if nested_candidate:
                return nested_candidate

    for nested_key in EXCERPT_KEYS:
        nested = value.get(nested_key)
        if isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict) and _is_non_empty_string(entry.get("text")):
                    return str(entry.get("text")).strip()
        nested_candidate = _extract_text_candidate(nested)
        if nested_candidate:
            return nested_candidate

    for nested_key in FINDING_KEYS:
        nested = value.get(nested_key)
        if isinstance(nested, list):
            for entry in nested:
                if not isinstance(entry, dict):
                    continue
                if _is_non_empty_string(entry.get("title")):
                    return str(entry.get("title")).strip()
                if _is_non_empty_string(entry.get("description")):
                    return str(entry.get("description")).strip()
        nested_candidate = _extract_text_candidate(nested)
        if nested_candidate:
            return nested_candidate

    for nested_key in PAGED_KEYS + MEDIA_KEYS + FILE_BUNDLE_KEYS:
        nested_candidate = _extract_text_candidate(value.get(nested_key))
        if nested_candidate:
            return nested_candidate

    for nested_key in DOCUMENT_PAGE_KEYS:
        nested = value.get(nested_key)
        if isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, dict):
                    for page_key in ("text", "content", "excerpt", "summary"):
                        if _is_non_empty_string(entry.get(page_key)):
                            return str(entry.get(page_key)).strip()
        nested_candidate = _extract_text_candidate(nested)
        if nested_candidate:
            return nested_candidate

    for nested_key in PLAN_KEYS + ("steps", "items"):
        nested_candidate = _extract_text_candidate(value.get(nested_key))
        if nested_candidate:
            return nested_candidate

    for key in ("text", "description", "details", "title"):
        candidate = value.get(key)
        if _is_non_empty_string(candidate):
            return str(candidate).strip()

    return None


def _maybe_parse_json_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    if len(text) < 2 or (text[0], text[-1]) not in {("{", "}"), ("[", "]")}:
        return value

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _normalize_structured_root(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    normalized = dict(value)
    if "task_plan" not in normalized and isinstance(normalized.get("steps"), list):
        normalized["task_plan"] = {
            "summary": normalized.get("summary") or normalized.get("answer") or "",
            "steps": normalized.get("steps") or [],
            "decisions": normalized.get("decisions") or [],
        }

    return normalized


def _normalize_code_files(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = []
        for path, content in value.items():
            items.append(
                {
                    "path": str(path),
                    "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2),
                }
            )
        return items

    if not isinstance(value, list):
        return []

    items: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if isinstance(entry, dict):
            path = str(entry.get("path") or entry.get("file_path") or entry.get("name") or f"file-{index + 1}")
            content = entry.get("content")
            if content is None and entry.get("patch") is not None:
                content = entry.get("patch")
            items.append(
                {
                    "path": path,
                    "language": entry.get("language"),
                    "content": content if isinstance(content, str) else json.dumps(content or {}, ensure_ascii=False, indent=2),
                    "metadata": (
                        dict(entry.get("metadata"))
                        if isinstance(entry.get("metadata"), dict)
                        else {key: value for key, value in entry.items() if key not in {"path", "file_path", "name", "language", "content", "patch", "metadata"}}
                    ),
                }
            )
        elif _is_non_empty_string(entry):
            items.append({"path": f"file-{index + 1}", "content": str(entry).strip()})
    return items


def _normalize_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    findings: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            findings.append(
                {
                    "title": entry.get("title") or entry.get("summary") or entry.get("message") or "Finding",
                    "severity": entry.get("severity") or entry.get("level") or "info",
                    "description": entry.get("description") or entry.get("details") or entry.get("message") or "",
                    "path": entry.get("path") or entry.get("file"),
                    "line": entry.get("line"),
                    "code": entry.get("code"),
                    "metadata": (
                        dict(entry.get("metadata"))
                        if isinstance(entry.get("metadata"), dict)
                        else {
                            key: value
                            for key, value in entry.items()
                            if key not in {"title", "summary", "message", "severity", "level", "description", "details", "path", "file", "line", "code", "metadata"}
                        }
                    ),
                }
            )
        elif _is_non_empty_string(entry):
            findings.append(
                {
                    "title": str(entry).strip().splitlines()[0][:80] or "Finding",
                    "severity": "info",
                    "description": str(entry).strip(),
                }
            )
    return findings


def _normalize_citations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    citations: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if isinstance(entry, dict):
            citations.append(
                {
                    "title": entry.get("title") or entry.get("name") or entry.get("source") or f"Source {index + 1}",
                    "url": entry.get("url") or entry.get("link"),
                    "snippet": entry.get("snippet") or entry.get("quote") or entry.get("excerpt"),
                    "metadata": (
                        dict(entry.get("metadata"))
                        if isinstance(entry.get("metadata"), dict)
                        else {
                            key: value
                            for key, value in entry.items()
                            if key not in {"title", "name", "source", "url", "link", "snippet", "quote", "excerpt", "metadata"}
                        }
                    ),
                }
            )
        elif _is_non_empty_string(entry):
            citations.append({"title": f"Source {index + 1}", "snippet": str(entry).strip()})
    return citations


def _normalize_excerpt_entries(value: Any) -> list[dict[str, Any]]:
    if _is_non_empty_string(value):
        return [{"text": str(value).strip()}]

    if not isinstance(value, list):
        return []

    entries: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            entries.append(
                {
                    "title": entry.get("title") or entry.get("heading"),
                    "text": entry.get("text") or entry.get("content") or entry.get("excerpt") or entry.get("preview") or entry.get("snippet") or "",
                    "source": entry.get("source"),
                    "metadata": (
                        dict(entry.get("metadata"))
                        if isinstance(entry.get("metadata"), dict)
                        else {
                            key: value
                            for key, value in entry.items()
                            if key not in {"title", "heading", "text", "content", "excerpt", "preview", "snippet", "source", "metadata"}
                        }
                    ),
                }
            )
        elif _is_non_empty_string(entry):
            entries.append({"text": str(entry).strip()})
    return entries


def _normalize_table_payload(value: Any) -> Optional[dict[str, Any]]:
    if isinstance(value, dict):
        rows = value.get("rows")
        columns = value.get("columns")
        if isinstance(rows, list):
            normalized_columns = columns if isinstance(columns, list) else []
            if not normalized_columns and rows and isinstance(rows[0], dict):
                normalized_columns = list(rows[0].keys())
            return {
                "title": value.get("title"),
                "columns": normalized_columns,
                "rows": rows,
            }
    if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        return {
            "columns": list(value[0].keys()),
            "rows": value,
        }
    return None


def _normalize_metadata(entry: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
    metadata.update({key: value for key, value in entry.items() if key not in excluded})
    return metadata


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def _normalize_inline_uri(source: str, mime_type: str = "", data: Any = None) -> str:
    source_text = str(source or "").strip()
    if source_text:
        return source_text

    if not _is_non_empty_string(data):
        return ""

    data_text = str(data).strip()
    if data_text.startswith("data:"):
        return data_text
    return f"data:{str(mime_type or 'application/octet-stream').strip() or 'application/octet-stream'};base64,{data_text}"


def _normalize_mcp_content_entries(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _guess_media_kind(path: str, mime_type: str = "") -> str | None:
    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime.startswith("image/"):
        return "image"
    if normalized_mime.startswith("video/"):
        return "video"
    if normalized_mime.startswith("audio/"):
        return "audio"

    extension = posixpath.splitext(str(path or "").strip().lower())[1]
    return MEDIA_EXTENSIONS.get(extension)


def _looks_like_resource_entry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    resource = value.get("resource")
    resource_dict = resource if isinstance(resource, dict) else {}
    return any(
        _is_non_empty_string(candidate)
        for candidate in (
            value.get("uri"),
            value.get("url"),
            value.get("href"),
            value.get("resource_link"),
            value.get("resourceLink"),
            value.get("path"),
            value.get("file_path"),
            value.get("name"),
            resource_dict.get("uri"),
            resource_dict.get("url"),
            resource_dict.get("href"),
            resource_dict.get("resource_link"),
            resource_dict.get("resourceLink"),
            resource_dict.get("path"),
            resource_dict.get("file_path"),
            resource_dict.get("name"),
        )
    ) or _is_non_empty_string(value.get("data")) or _is_non_empty_string(resource_dict.get("data"))


def _extract_pagination_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    pagination = value.get("pagination") if isinstance(value.get("pagination"), dict) else None
    if pagination is None:
        for alias in ("page_info", "pageInfo"):
            candidate = value.get(alias)
            if isinstance(candidate, dict):
                pagination = candidate
                break
    source = pagination or value

    metadata = {
        "cursor": source.get("cursor"),
        "next_cursor": source.get("next_cursor") or source.get("nextCursor"),
        "previous_cursor": source.get("previous_cursor") or source.get("previousCursor") or source.get("prev_cursor"),
        "has_more": _coerce_bool(source.get("has_more") if source.get("has_more") is not None else source.get("hasMore")),
        "page": _coerce_int(source.get("page") if source.get("page") is not None else source.get("page_index") or source.get("pageIndex")),
        "page_size": _coerce_int(source.get("page_size") if source.get("page_size") is not None else source.get("pageSize") or source.get("limit")),
        "offset": _coerce_int(source.get("offset")),
        "total_count": _coerce_int(source.get("total_count") if source.get("total_count") is not None else source.get("totalCount") or source.get("total")),
    }
    return {key: item for key, item in metadata.items() if item is not None and item != ""}


def _extract_paged_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if not isinstance(value, dict):
        return []

    for key in IMPLICIT_LIST_KEYS + ("rows",):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return candidate
    return []


def _normalize_paged_collection_payload(
    value: Any,
    *,
    context: Any = None,
    title: str | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    items = _extract_paged_items(value)
    if not items and isinstance(value, list):
        items = value
    if not isinstance(items, list) or not items:
        return None

    pagination = _extract_pagination_metadata(value if isinstance(value, dict) else context)
    if not force and not pagination:
        return None

    columns = list(items[0].keys()) if items and all(isinstance(item, dict) for item in items[:1]) else []
    return {
        "title": title,
        "items": items,
        "columns": columns,
        "display": "table" if columns else "list",
        "pagination": {
            **pagination,
            "returned_count": len(items),
        },
    }


def _normalize_media_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        entries = [value]
    elif isinstance(value, list):
        entries = value
    else:
        return []

    items: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        resource_dict = resource if isinstance(resource, dict) else {}
        source = str(
            entry.get("uri")
            or entry.get("url")
            or entry.get("href")
            or entry.get("resource_link")
            or entry.get("resourceLink")
            or resource_dict.get("uri")
            or resource_dict.get("url")
            or resource_dict.get("href")
            or resource_dict.get("resource_link")
            or resource_dict.get("resourceLink")
            or ""
        ).strip()
        mime_type = str(
            entry.get("mimeType")
            or entry.get("mime_type")
            or resource_dict.get("mimeType")
            or resource_dict.get("mime_type")
            or ""
        ).strip()
        path = str(
            entry.get("path")
            or entry.get("file_path")
            or resource_dict.get("path")
            or resource_dict.get("file_path")
            or resource_dict.get("name")
            or _path_from_source(source)
        ).strip()
        media_kind = _guess_media_kind(path, mime_type)
        if media_kind not in {"image", "video", "audio"}:
            continue

        data = entry.get("data") or entry.get("blob") or resource_dict.get("data") or resource_dict.get("blob")
        uri = _normalize_inline_uri(source, mime_type, data)
        title = str(
            entry.get("title")
            or entry.get("name")
            or resource_dict.get("title")
            or resource_dict.get("name")
            or path
            or f"Media {index + 1}"
        ).strip()
        items.append(
            {
                "title": title,
                "uri": uri,
                "mime_type": mime_type,
                "kind": media_kind,
                "alt": str(entry.get("alt") or entry.get("description") or resource_dict.get("alt") or title).strip(),
                "path": path,
                "source": source,
                "size_bytes": _coerce_int(
                    entry.get("size_bytes")
                    if entry.get("size_bytes") is not None
                    else entry.get("sizeBytes")
                    or entry.get("bytes")
                    or resource_dict.get("size_bytes")
                    or resource_dict.get("sizeBytes")
                    or resource_dict.get("bytes")
                ),
                "metadata": _normalize_metadata(
                    {**resource_dict, **entry},
                    {
                        "resource",
                        "metadata",
                        "uri",
                        "url",
                        "href",
                        "mimeType",
                        "mime_type",
                        "path",
                        "file_path",
                        "name",
                        "title",
                        "alt",
                        "description",
                        "data",
                        "blob",
                        "size_bytes",
                        "sizeBytes",
                        "bytes",
                    },
                ),
            }
        )
    return items


def _normalize_file_bundle_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        entries = [value]
    elif isinstance(value, list):
        entries = value
    else:
        return []

    files: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        resource_dict = resource if isinstance(resource, dict) else {}
        source = str(
            entry.get("uri")
            or entry.get("url")
            or entry.get("href")
            or entry.get("resource_link")
            or entry.get("resourceLink")
            or resource_dict.get("uri")
            or resource_dict.get("url")
            or resource_dict.get("href")
            or resource_dict.get("resource_link")
            or resource_dict.get("resourceLink")
            or ""
        ).strip()
        source_url = str(
            entry.get("source_url")
            or entry.get("sourceUrl")
            or resource_dict.get("source_url")
            or resource_dict.get("sourceUrl")
            or entry.get("source")
            or resource_dict.get("source")
            or ""
        ).strip()
        mime_type = str(
            entry.get("mimeType")
            or entry.get("mime_type")
            or resource_dict.get("mimeType")
            or resource_dict.get("mime_type")
            or ""
        ).strip()
        path = str(
            entry.get("path")
            or entry.get("file_path")
            or resource_dict.get("path")
            or resource_dict.get("file_path")
            or resource_dict.get("name")
            or _path_from_source(source)
        ).strip()
        if not (
            source
            or mime_type
            or _is_non_empty_string(entry.get("name"))
            or _is_non_empty_string(entry.get("title"))
            or _is_non_empty_string(resource_dict.get("name"))
            or _is_non_empty_string(resource_dict.get("title"))
            or _is_non_empty_string(entry.get("data"))
            or _is_non_empty_string(resource_dict.get("data"))
        ):
            continue
        if _guess_media_kind(path, mime_type) in {"image", "video", "audio"}:
            continue

        preview_text = ""
        for candidate in (
            entry.get("preview_text"),
            entry.get("previewText"),
            entry.get("text"),
            entry.get("content"),
            entry.get("excerpt"),
            resource_dict.get("preview_text"),
            resource_dict.get("previewText"),
            resource_dict.get("text"),
            resource_dict.get("content"),
            resource_dict.get("excerpt"),
        ):
            if _is_non_empty_string(candidate):
                preview_text = str(candidate).strip()
                break

        files.append(
            {
                "name": str(
                    entry.get("name")
                    or entry.get("title")
                    or resource_dict.get("name")
                    or resource_dict.get("title")
                    or path
                    or f"File {index + 1}"
                ).strip(),
                "path": path,
                "uri": _normalize_inline_uri(source, mime_type, entry.get("data") or resource_dict.get("data")),
                "mime_type": mime_type,
                "size_bytes": _coerce_int(
                    entry.get("size_bytes")
                    if entry.get("size_bytes") is not None
                    else entry.get("sizeBytes")
                    or entry.get("bytes")
                    or resource_dict.get("size_bytes")
                    or resource_dict.get("sizeBytes")
                    or resource_dict.get("bytes")
                ),
                "description": str(entry.get("description") or resource_dict.get("description") or "").strip(),
                "preview_text": preview_text,
                "source": source_url or source,
                "metadata": _normalize_metadata(
                    {**resource_dict, **entry},
                    {
                        "resource",
                        "metadata",
                        "uri",
                        "url",
                        "href",
                        "mimeType",
                        "mime_type",
                        "path",
                        "file_path",
                        "name",
                        "title",
                        "source_url",
                        "sourceUrl",
                        "source",
                        "description",
                        "preview_text",
                        "previewText",
                        "text",
                        "content",
                        "excerpt",
                        "data",
                        "blob",
                        "size_bytes",
                        "sizeBytes",
                        "bytes",
                    },
                ),
            }
        )
    return files


def _path_segments(path: str) -> list[str]:
    text = str(path or "").strip().strip("/")
    if not text:
        return []
    return [segment for segment in text.split("/") if segment]


def _coerce_tree_node_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "directory" if value else "file"
    text = str(value or "").strip().lower()
    if text in {"dir", "directory", "folder"}:
        return "directory"
    if text in {"file", "document", "blob", "leaf"}:
        return "file"
    return None


def _normalize_tree_leaf_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    return _normalize_metadata(
        entry,
        {
            "metadata",
            "resource",
            "name",
            "title",
            "path",
            "file_path",
            "type",
            "kind",
            "node_type",
            "is_dir",
            "is_directory",
            "children",
            "nodes",
            "entries",
            "items",
            "uri",
            "url",
            "href",
            "mimeType",
            "mime_type",
            "size_bytes",
            "sizeBytes",
            "bytes",
        },
    )


def _normalize_directory_tree_node(entry: Any, index: int = 0) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        path = str(entry or "").strip()
        if not path:
            return None
        node_type = "directory" if path.endswith("/") else "file"
        trimmed_path = path.rstrip("/")
        name = posixpath.basename(trimmed_path) or trimmed_path or f"Node {index + 1}"
        return {
            "name": name,
            "path": trimmed_path,
            "node_type": node_type,
            "children": [],
            "metadata": {},
        }

    resource = entry.get("resource")
    resource_dict = resource if isinstance(resource, dict) else {}
    merged = {**resource_dict, **entry}
    raw_path = str(
        merged.get("path")
        or merged.get("file_path")
        or merged.get("uri")
        or merged.get("url")
        or merged.get("href")
        or merged.get("name")
        or merged.get("title")
        or ""
    ).strip()
    path = raw_path.rstrip("/")
    name = str(merged.get("name") or merged.get("title") or posixpath.basename(path) or path or f"Node {index + 1}").strip()
    child_entries = (
        merged.get("children")
        if isinstance(merged.get("children"), list)
        else merged.get("nodes")
        if isinstance(merged.get("nodes"), list)
        else merged.get("entries")
        if isinstance(merged.get("entries"), list)
        else merged.get("items")
        if isinstance(merged.get("items"), list)
        else []
    )
    node_type = (
        _coerce_tree_node_type(merged.get("node_type"))
        or _coerce_tree_node_type(merged.get("type"))
        or _coerce_tree_node_type(merged.get("kind"))
        or _coerce_tree_node_type(merged.get("is_dir"))
        or _coerce_tree_node_type(merged.get("is_directory"))
    )
    if node_type is None:
        node_type = "directory" if child_entries or raw_path.endswith("/") else "file"

    children = [
        child
        for child in (_normalize_directory_tree_node(item, child_index) for child_index, item in enumerate(child_entries))
        if child is not None
    ]
    if children:
        node_type = "directory"

    return {
        "name": name,
        "path": path,
        "node_type": node_type,
        "uri": str(merged.get("uri") or merged.get("url") or merged.get("href") or "").strip(),
        "mime_type": str(merged.get("mimeType") or merged.get("mime_type") or "").strip(),
        "size_bytes": _coerce_int(
            merged.get("size_bytes")
            if merged.get("size_bytes") is not None
            else merged.get("sizeBytes") or merged.get("bytes")
        ),
        "children": children,
        "metadata": _normalize_tree_leaf_metadata(merged),
    }


def _insert_directory_path(root_nodes: list[dict[str, Any]], entry: dict[str, Any], index: int) -> None:
    path = str(entry.get("path") or entry.get("file_path") or entry.get("name") or entry.get("title") or "").strip()
    segments = _path_segments(path)
    if not segments:
        normalized = _normalize_directory_tree_node(entry, index)
        if normalized is not None:
            root_nodes.append(normalized)
        return

    node_type = (
        _coerce_tree_node_type(entry.get("node_type"))
        or _coerce_tree_node_type(entry.get("type"))
        or _coerce_tree_node_type(entry.get("kind"))
        or _coerce_tree_node_type(entry.get("is_dir"))
        or _coerce_tree_node_type(entry.get("is_directory"))
    )
    if node_type is None:
        node_type = "directory" if path.endswith("/") else "file"

    current_level = root_nodes
    accumulated: list[str] = []
    for segment_index, segment in enumerate(segments):
        accumulated.append(segment)
        is_leaf = segment_index == len(segments) - 1
        expected_type = node_type if is_leaf else "directory"
        existing = next((item for item in current_level if item.get("name") == segment), None)
        if existing is None:
            existing = {
                "name": segment,
                "path": "/".join(accumulated),
                "node_type": expected_type,
                "children": [],
                "metadata": {},
            }
            current_level.append(existing)
        if not is_leaf:
            existing["node_type"] = "directory"
            existing.setdefault("children", [])
            current_level = existing["children"]
            continue

        normalized = _normalize_directory_tree_node(entry, index) or {}
        existing.update(
            {
                "name": segment,
                "path": "/".join(accumulated),
                "node_type": expected_type,
                "uri": normalized.get("uri"),
                "mime_type": normalized.get("mime_type"),
                "size_bytes": normalized.get("size_bytes"),
                "metadata": normalized.get("metadata") or {},
            }
        )
        if normalized.get("children"):
            existing["children"] = normalized["children"]
            existing["node_type"] = "directory"


def _count_directory_tree(nodes: list[dict[str, Any]], depth: int = 1) -> dict[str, int]:
    file_count = 0
    directory_count = 0
    max_depth = depth if nodes else 0
    for node in nodes:
        children = node.get("children") if isinstance(node.get("children"), list) else []
        if str(node.get("node_type") or "").strip() == "directory":
            directory_count += 1
        else:
            file_count += 1
        child_counts = _count_directory_tree(children, depth + 1)
        file_count += child_counts["file_count"]
        directory_count += child_counts["directory_count"]
        max_depth = max(max_depth, child_counts["max_depth"])
    return {
        "file_count": file_count,
        "directory_count": directory_count,
        "max_depth": max_depth,
    }


def _normalize_directory_tree_payload(
    value: Any,
    *,
    title: str | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    root_name = ""
    nodes: list[dict[str, Any]] = []
    explicit_structure = False

    if isinstance(value, dict):
        child_entries = (
            value.get("children")
            if isinstance(value.get("children"), list)
            else value.get("nodes")
            if isinstance(value.get("nodes"), list)
            else value.get("entries")
            if isinstance(value.get("entries"), list)
            else value.get("items")
            if isinstance(value.get("items"), list)
            else []
        )
        root_name = str(value.get("name") or value.get("title") or value.get("path") or "").strip().rstrip("/")
        if child_entries:
            explicit_structure = True
            nodes = [
                node
                for node in (_normalize_directory_tree_node(item, index) for index, item in enumerate(child_entries))
                if node is not None
            ]
        elif isinstance(value.get("path"), str) and (
            _coerce_tree_node_type(value.get("type")) == "directory"
            or _coerce_tree_node_type(value.get("kind")) == "directory"
            or str(value.get("path") or "").endswith("/")
        ):
            normalized_root = _normalize_directory_tree_node(value, 0)
            if normalized_root is not None:
                nodes = [normalized_root]
    elif isinstance(value, list):
        entries = [item for item in value if isinstance(item, (dict, str)) and str(item or "").strip()]
        if entries:
            if any(isinstance(item, dict) and isinstance(item.get("children"), list) for item in entries):
                nodes = [
                    node
                    for node in (_normalize_directory_tree_node(item, index) for index, item in enumerate(entries))
                    if node is not None
                ]
            else:
                flat_root: list[dict[str, Any]] = []
                for index, item in enumerate(entries):
                    if isinstance(item, dict):
                        _insert_directory_path(flat_root, item, index)
                    else:
                        _insert_directory_path(flat_root, {"path": str(item)}, index)
                nodes = flat_root

    if not nodes:
        return None

    if not force and not (
        explicit_structure
        or any(node.get("children") for node in nodes)
        or any(str(node.get("node_type") or "").strip() == "directory" for node in nodes)
    ):
        return None

    counts = _count_directory_tree(nodes)
    return {
        "title": title or root_name,
        "root_name": root_name,
        "nodes": nodes,
        "summary": counts,
    }


def _looks_like_document_page_entry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("page") is not None or value.get("page_number") is not None or value.get("pageNumber") is not None:
        return True
    return any(
        _is_non_empty_string(value.get(key))
        for key in ("text", "content", "excerpt", "thumbnail_uri", "thumbnailUrl", "image_uri", "imageUrl")
    )


def _normalize_document_pages_payload(
    value: Any,
    *,
    title: str | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    pages_source = value
    payload = value if isinstance(value, dict) else {}
    if isinstance(value, dict):
        for candidate_key in ("pages", "items", "entries"):
            candidate = value.get(candidate_key)
            if isinstance(candidate, list):
                pages_source = candidate
                break

    if not isinstance(pages_source, list) or not pages_source:
        return None
    if not force and not any(_looks_like_document_page_entry(item) for item in pages_source):
        return None

    pages: list[dict[str, Any]] = []
    for index, entry in enumerate(pages_source):
        if not isinstance(entry, dict):
            text = str(entry or "").strip()
            if not text:
                continue
            pages.append(
                {
                    "page_number": index + 1,
                    "title": f"Page {index + 1}",
                    "text": text,
                    "uri": "",
                    "thumbnail_uri": "",
                    "mime_type": "",
                    "source": "",
                    "metadata": {},
                }
            )
            continue

        page_number = _coerce_int(
            entry.get("page_number")
            if entry.get("page_number") is not None
            else entry.get("pageNumber") or entry.get("page") or entry.get("index")
        )
        pages.append(
            {
                "page_number": page_number or index + 1,
                "title": str(entry.get("title") or entry.get("heading") or f"Page {page_number or index + 1}").strip(),
                "text": str(entry.get("text") or entry.get("content") or entry.get("excerpt") or "").strip(),
                "uri": str(entry.get("uri") or entry.get("url") or "").strip(),
                "thumbnail_uri": str(
                    entry.get("thumbnail_uri")
                    or entry.get("thumbnailUrl")
                    or entry.get("image_uri")
                    or entry.get("imageUrl")
                    or ""
                ).strip(),
                "mime_type": str(entry.get("mimeType") or entry.get("mime_type") or "").strip(),
                "source": str(entry.get("source") or entry.get("uri") or entry.get("url") or "").strip(),
                "metadata": _normalize_metadata(
                    entry,
                    {
                        "metadata",
                        "page_number",
                        "pageNumber",
                        "page",
                        "index",
                        "title",
                        "heading",
                        "text",
                        "content",
                        "excerpt",
                        "uri",
                        "url",
                        "thumbnail_uri",
                        "thumbnailUrl",
                        "image_uri",
                        "imageUrl",
                        "mimeType",
                        "mime_type",
                        "source",
                    },
                ),
            }
        )

    if not pages:
        return None

    return {
        "title": title or str(payload.get("title") or payload.get("name") or "").strip(),
        "page_count": _coerce_int(payload.get("page_count") if payload.get("page_count") is not None else payload.get("pageCount"))
        or len(pages),
        "pages": pages,
    }


def _archive_format_from_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip", ".rar", ".7z", ".gz"):
        if text.endswith(suffix):
            return suffix.lstrip(".")
    if text in {"zip", "tar", "tgz", "tar.gz", "rar", "7z", "gz"}:
        return text
    return ""


def _looks_like_archive_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if _archive_format_from_value(value.get("format")):
        return True
    if _archive_format_from_value(value.get("path")) or _archive_format_from_value(value.get("name")) or _archive_format_from_value(value.get("uri")):
        return True
    mime_type = str(value.get("mimeType") or value.get("mime_type") or "").strip().lower()
    return mime_type in {"application/zip", "application/x-tar", "application/gzip", "application/x-7z-compressed", "application/vnd.rar"}


def _normalize_archive_bundle_payload(
    value: Any,
    *,
    title: str | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    entries_source = value
    payload = value if isinstance(value, dict) else {}
    if isinstance(value, dict):
        for candidate_key in ("entries", "items", "members", "files"):
            candidate = value.get(candidate_key)
            if isinstance(candidate, list):
                entries_source = candidate
                break

    if not isinstance(entries_source, list) or not entries_source:
        return None
    if not force and not _looks_like_archive_payload(payload):
        return None

    files: list[dict[str, Any]] = []
    total_size = 0
    total_compressed_size = 0
    for index, entry in enumerate(entries_source):
        if not isinstance(entry, dict):
            path = str(entry or "").strip()
            if not path:
                continue
            files.append(
                {
                    "name": posixpath.basename(path) or path,
                    "path": path,
                    "mime_type": "",
                    "size_bytes": None,
                    "compressed_size_bytes": None,
                    "checksum": "",
                    "description": "",
                    "metadata": {},
                }
            )
            continue

        size_bytes = _coerce_int(entry.get("size_bytes") if entry.get("size_bytes") is not None else entry.get("sizeBytes") or entry.get("bytes"))
        compressed_size_bytes = _coerce_int(
            entry.get("compressed_size_bytes")
            if entry.get("compressed_size_bytes") is not None
            else entry.get("compressedSizeBytes") or entry.get("compressed_bytes") or entry.get("compressedBytes")
        )
        if isinstance(size_bytes, int):
            total_size += size_bytes
        if isinstance(compressed_size_bytes, int):
            total_compressed_size += compressed_size_bytes
        files.append(
            {
                "name": str(entry.get("name") or entry.get("title") or entry.get("path") or entry.get("file_path") or f"Entry {index + 1}").strip(),
                "path": str(entry.get("path") or entry.get("file_path") or entry.get("name") or "").strip(),
                "mime_type": str(entry.get("mimeType") or entry.get("mime_type") or "").strip(),
                "size_bytes": size_bytes,
                "compressed_size_bytes": compressed_size_bytes,
                "checksum": str(entry.get("checksum") or entry.get("digest") or entry.get("sha256") or "").strip(),
                "description": str(entry.get("description") or "").strip(),
                "metadata": _normalize_metadata(
                    entry,
                    {
                        "metadata",
                        "name",
                        "title",
                        "path",
                        "file_path",
                        "mimeType",
                        "mime_type",
                        "size_bytes",
                        "sizeBytes",
                        "bytes",
                        "compressed_size_bytes",
                        "compressedSizeBytes",
                        "compressed_bytes",
                        "compressedBytes",
                        "checksum",
                        "digest",
                        "sha256",
                        "description",
                    },
                ),
            }
        )

    if not files:
        return None

    archive_name = str(payload.get("name") or payload.get("title") or payload.get("path") or payload.get("uri") or "").strip()
    archive_format = (
        _archive_format_from_value(payload.get("format"))
        or _archive_format_from_value(payload.get("path"))
        or _archive_format_from_value(payload.get("name"))
        or _archive_format_from_value(payload.get("uri"))
    )
    return {
        "title": title or archive_name,
        "archive_name": archive_name,
        "format": archive_format,
        "entry_count": len(files),
        "total_size_bytes": total_size or None,
        "total_compressed_size_bytes": total_compressed_size or None,
        "files": files,
    }


def _looks_like_media_list(value: Any) -> bool:
    return isinstance(value, list) and bool(_normalize_media_entries(value))


def _looks_like_file_bundle_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return any(_looks_like_resource_entry(item) for item in value) and bool(_normalize_file_bundle_entries(value))


def _has_artifact_type(artifacts: list[dict[str, Any]], artifact_type: str) -> bool:
    return any(str(item.get("artifact_type") or "").strip() == artifact_type for item in artifacts)


def _looks_like_citation_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return any(
        isinstance(item, dict) and (
            _is_non_empty_string(item.get("url"))
            or _is_non_empty_string(item.get("link"))
            or (
                _is_non_empty_string(item.get("source"))
                and (
                    _is_non_empty_string(item.get("snippet"))
                    or _is_non_empty_string(item.get("quote"))
                    or _is_non_empty_string(item.get("excerpt"))
                )
            )
        )
        for item in value
    )


def _looks_like_finding_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return any(
        isinstance(item, dict) and (
            _is_non_empty_string(item.get("severity"))
            or _is_non_empty_string(item.get("level"))
            or _is_non_empty_string(item.get("description"))
            or _is_non_empty_string(item.get("details"))
            or _is_non_empty_string(item.get("message"))
        )
        for item in value
    )


def _looks_like_code_file_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return any(
        isinstance(item, dict)
        and (
            _is_non_empty_string(item.get("path"))
            or _is_non_empty_string(item.get("file_path"))
            or _is_non_empty_string(item.get("name"))
        )
        and (
            _is_non_empty_string(item.get("content"))
            or _is_non_empty_string(item.get("patch"))
        )
        for item in value
    )


def _looks_like_excerpt_list(value: Any) -> bool:
    if _is_non_empty_string(value):
        return True
    if not isinstance(value, list) or not value:
        return False
    if all(_is_non_empty_string(item) for item in value):
        return True
    return any(
        isinstance(item, dict) and (
            _is_non_empty_string(item.get("text"))
            or _is_non_empty_string(item.get("content"))
            or _is_non_empty_string(item.get("excerpt"))
        )
        for item in value
    )


def _append_implicit_list_artifacts(
    artifacts: list[dict[str, Any]],
    value: dict[str, Any],
) -> None:
    if not isinstance(value, dict):
        return

    for key in IMPLICIT_LIST_KEYS:
        candidate = value.get(key)
        if candidate in (None, "", []):
            continue

        if not _has_artifact_type(artifacts, "citations") and _looks_like_citation_list(candidate):
            citations = _normalize_citations(candidate)
            if citations:
                _append_artifact(
                    artifacts,
                    artifact_type="citations",
                    name=_compact_title(key, "Citations"),
                    payload={"items": citations},
                )
                continue

        if not _has_artifact_type(artifacts, "review_findings") and _looks_like_finding_list(candidate):
            findings = _normalize_findings(candidate)
            if findings:
                _append_artifact(
                    artifacts,
                    artifact_type="review_findings",
                    name=_compact_title(key, "Review Findings"),
                    payload={"items": findings},
                )
                continue

        if not _has_artifact_type(artifacts, "code_files") and _looks_like_code_file_list(candidate):
            files = _normalize_code_files(candidate)
            if files:
                _append_artifact(
                    artifacts,
                    artifact_type="code_files",
                    name=_compact_title(key, "Code Files"),
                    payload={"files": files},
                )
                continue

        if not _has_artifact_type(artifacts, "media_gallery") and _looks_like_media_list(candidate):
            media_items = _normalize_media_entries(candidate)
            if media_items:
                _append_artifact(
                    artifacts,
                    artifact_type="media_gallery",
                    name=_compact_title(key, "Media Gallery"),
                    payload={"items": media_items},
                )
                continue

        if not _has_artifact_type(artifacts, "file_bundle") and _looks_like_file_bundle_list(candidate):
            files = _normalize_file_bundle_entries(candidate)
            if files:
                _append_artifact(
                    artifacts,
                    artifact_type="file_bundle",
                    name=_compact_title(key, "File Bundle"),
                    payload={"files": files},
                )
                continue

        if not _has_artifact_type(artifacts, "paged_collection"):
            paged_payload = _normalize_paged_collection_payload(
                candidate,
                context=value,
                title=_compact_title(key, "Paged Collection"),
            )
            if paged_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="paged_collection",
                    name=_compact_title(key, "Paged Collection"),
                    payload=paged_payload,
                )
                continue

        if not _has_artifact_type(artifacts, "document_excerpt") and _looks_like_excerpt_list(candidate):
            excerpts = _normalize_excerpt_entries(candidate)
            if excerpts:
                _append_artifact(
                    artifacts,
                    artifact_type="document_excerpt",
                    name=_compact_title(key, "Document Excerpt"),
                    payload={"items": excerpts},
                )
                continue

        if not _has_artifact_type(artifacts, "table"):
            table_payload = _normalize_table_payload(candidate)
            if table_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="table",
                    name=_compact_title(key, "Table"),
                    payload=table_payload,
                )


def _path_from_source(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    path = parsed.path or text
    name = posixpath.basename(path.rstrip("/"))
    return name or text


def _guess_language(path: str, mime_type: str = "") -> str | None:
    extension = posixpath.splitext(str(path or "").strip().lower())[1]
    if extension in CODE_FILE_EXTENSIONS:
        return CODE_FILE_EXTENSIONS[extension]

    normalized_mime = str(mime_type or "").strip().lower()
    mime_suffix_map = {
        "javascript": "javascript",
        "typescript": "typescript",
        "json": "json",
        "markdown": "markdown",
        "html": "html",
        "css": "css",
        "xml": "xml",
        "yaml": "yaml",
        "python": "python",
        "shell": "bash",
    }
    for token, language in mime_suffix_map.items():
        if token in normalized_mime:
            return language
    return None


def _is_code_like_content(path: str, mime_type: str) -> bool:
    extension = posixpath.splitext(str(path or "").strip().lower())[1]
    if extension in CODE_FILE_EXTENSIONS and extension != ".txt":
        return True

    normalized_mime = str(mime_type or "").strip().lower()
    if not normalized_mime:
        return False

    return (
        normalized_mime.startswith("text/x-")
        or normalized_mime.startswith("application/x-")
        or normalized_mime in {
            "application/json",
            "application/javascript",
            "application/xml",
            "text/css",
            "text/html",
            "text/javascript",
            "text/markdown",
            "text/xml",
        }
        or normalized_mime.endswith("+json")
        or normalized_mime.endswith("+xml")
    )


def _extract_content_core(entry: Any, index: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        text = str(entry or "").strip()
        return {
            "title": f"Content {index + 1}",
            "text": text,
            "source": "",
            "uri": "",
            "mime_type": "",
            "path": "",
            "kind": None,
            "description": "",
            "size_bytes": None,
        }

    resource = entry.get("resource")
    resource_dict = resource if isinstance(resource, dict) else {}
    source = str(
        entry.get("uri")
        or entry.get("url")
        or entry.get("href")
        or entry.get("resource_link")
        or entry.get("resourceLink")
        or resource_dict.get("uri")
        or resource_dict.get("url")
        or resource_dict.get("href")
        or resource_dict.get("resource_link")
        or resource_dict.get("resourceLink")
        or ""
    ).strip()
    mime_type = str(
        entry.get("mimeType")
        or entry.get("mime_type")
        or resource_dict.get("mimeType")
        or resource_dict.get("mime_type")
        or ""
    ).strip()
    path = str(
        entry.get("path")
        or entry.get("file_path")
        or resource_dict.get("path")
        or resource_dict.get("file_path")
        or resource_dict.get("name")
        or _path_from_source(source)
    ).strip()
    text = ""
    item_type = str(entry.get("type") or "").strip().lower()
    if item_type == "text" and _is_non_empty_string(entry.get("text")):
        text = str(entry.get("text")).strip()
    if not text:
        for candidate in (
            entry.get("text"),
            entry.get("content"),
            entry.get("excerpt"),
            resource_dict.get("text"),
            resource_dict.get("content"),
            resource_dict.get("excerpt"),
        ):
            if _is_non_empty_string(candidate):
                text = str(candidate).strip()
                break
    if not text:
        text = _extract_text_candidate(resource_dict) or _extract_text_candidate(entry) or ""

    title = str(
        entry.get("title")
        or entry.get("name")
        or resource_dict.get("title")
        or resource_dict.get("name")
        or path
        or f"Content {index + 1}"
    ).strip()
    data = entry.get("data") or entry.get("blob") or resource_dict.get("data") or resource_dict.get("blob")
    return {
        "title": title,
        "text": str(text or "").strip(),
        "source": source,
        "uri": _normalize_inline_uri(source, mime_type, data),
        "mime_type": mime_type,
        "path": path,
        "kind": _guess_media_kind(path, mime_type),
        "description": str(entry.get("description") or resource_dict.get("description") or "").strip(),
        "size_bytes": _coerce_int(
            entry.get("size_bytes")
            if entry.get("size_bytes") is not None
            else entry.get("sizeBytes")
            or entry.get("bytes")
            or resource_dict.get("size_bytes")
            or resource_dict.get("sizeBytes")
            or resource_dict.get("bytes")
        ),
        "metadata": _normalize_metadata(
            {**resource_dict, **entry},
            {
                "resource",
                "metadata",
                "type",
                "uri",
                "url",
                "href",
                "mimeType",
                "mime_type",
                "path",
                "file_path",
                "name",
                "title",
                "text",
                "content",
                "excerpt",
                "description",
                "data",
                "blob",
                "size_bytes",
                "sizeBytes",
                "bytes",
                "structured_content",
                "structuredContent",
            },
        ),
    }


def _promote_structured_artifacts(
    value: Any,
    *,
    tool_name: str,
    tool_kind: str,
    step_id: str | None,
    tool_call_id: str | None,
    include_answer: bool,
    source: str,
    extra_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    structured = build_structured_run_result(value)
    promoted: list[dict[str, Any]] = []
    for artifact in structured.get("artifacts") or []:
        if not include_answer and artifact.get("artifact_type") == "answer":
            continue
        promoted.append(
            {
                **_normalize_artifact_entry(artifact),
                "name": _tool_artifact_name(tool_name, artifact.get("name"), "Result"),
                "metadata": {
                    **dict(artifact.get("metadata") or {}),
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    **({"content_metadata": extra_metadata} if extra_metadata else {}),
                },
                "step_id": step_id or artifact.get("step_id"),
            }
        )
    return promoted


def _append_artifact(
    artifacts: list[dict[str, Any]],
    *,
    artifact_type: str,
    name: str,
    payload: Any,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    artifacts.append(
        {
            "artifact_type": artifact_type,
            "name": name,
            "payload": payload,
            "metadata": metadata or {},
        }
    )


def _normalize_artifact_payload(artifact_type: str, payload: Any) -> Any:
    normalized_type = str(artifact_type or "").strip()

    if normalized_type == "answer":
        if isinstance(payload, dict):
            text = _extract_text_candidate(payload.get("text"))
            if text:
                return {"text": text, "format": payload.get("format") or "markdown"}
            return {"text": _extract_text_candidate(payload) or "", "format": payload.get("format") or "markdown"}
        text = _extract_text_candidate(payload) or ""
        return {"text": text, "format": "markdown"}

    if normalized_type == "citations":
        source_items = payload.get("items") if isinstance(payload, dict) else payload
        return {"items": _normalize_citations(source_items)}

    if normalized_type == "review_findings":
        source_items = payload.get("items") if isinstance(payload, dict) else payload
        return {"items": _normalize_findings(source_items)}

    if normalized_type == "workspace_summary":
        return dict(payload) if isinstance(payload, dict) else {}

    if normalized_type == "code_files":
        source_items = payload.get("files") if isinstance(payload, dict) else payload
        return {"files": _normalize_code_files(source_items)}

    if normalized_type == "code_patch":
        source = payload if isinstance(payload, dict) else {}
        files = []
        for entry in source.get("files") or []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip()
            if not path:
                continue
            files.append(
                {
                    "path": path,
                    "operation": str(entry.get("operation") or source.get("operation") or "modify").strip(),
                    "before_sha256": entry.get("before_sha256") or entry.get("beforeSha256"),
                    "after_sha256": entry.get("after_sha256") or entry.get("afterSha256"),
                    "size_bytes": _coerce_int(entry.get("size_bytes") if entry.get("size_bytes") is not None else entry.get("sizeBytes")) or 0,
                    "changed": entry.get("changed") is not False,
                }
            )
        raw_review_notes = source.get("review_notes") if isinstance(source.get("review_notes"), list) else source.get("reviewNotes")
        review_notes = raw_review_notes if isinstance(raw_review_notes, list) else []
        return {
            "operation": str(source.get("operation") or "").strip(),
            "status": str(source.get("status") or "").strip(),
            "dry_run": bool(source.get("dry_run") if source.get("dry_run") is not None else source.get("dryRun")),
            "files": files,
            "diff": str(source.get("diff") or ""),
            "truncated": bool(source.get("truncated")),
            "review_notes": [str(item) for item in review_notes or [] if str(item).strip()],
            "merge_policy": str(source.get("merge_policy") or source.get("mergePolicy") or "manual_review_required"),
            "writeback": source.get("writeback") if isinstance(source.get("writeback"), dict) else None,
        }

    if normalized_type == "verification_report":
        source = payload if isinstance(payload, dict) else {}
        command = source.get("command") if isinstance(source.get("command"), list) else []
        logs = source.get("logs") if isinstance(source.get("logs"), dict) else {}
        runner = source.get("runner") if isinstance(source.get("runner"), dict) else {}
        structured_report = source.get("structured_report") if isinstance(source.get("structured_report"), dict) else source.get("structuredReport")
        if not isinstance(structured_report, dict):
            structured_report = None
        source_kind = str(source.get("kind") or source.get("purpose") or "").strip()
        if source_kind == "browser_verify":
            structured_report = _browser_verification_report(source)
        kind = str(source.get("kind") or source.get("purpose") or "shell").strip() or "shell"
        if source_kind == "browser_verify":
            kind = "browser_verify"
        return {
            "kind": kind,
            "status": str(source.get("status") or "unknown").strip() or "unknown",
            "exit_code": source.get("exit_code"),
            "command": [str(item) for item in command],
            "cwd": str(source.get("cwd") or ".").strip() or ".",
            "duration_ms": _coerce_int(source.get("duration_ms")) or 0,
            "timeout_seconds": _coerce_int(source.get("timeout_seconds")),
            "summary": str(source.get("summary") or "").strip(),
            "failure_category": source.get("failure_category"),
            "truncated": bool(source.get("truncated")),
            "logs": {
                "stdout": str(logs.get("stdout") or source.get("stdout") or ""),
                "stderr": str(logs.get("stderr") or source.get("stderr") or ""),
            },
            "runner": runner,
            "selector": source.get("selector"),
            "target": source.get("target"),
            "ecosystem": source.get("ecosystem"),
            "report_format": source.get("report_format") or source.get("reportFormat"),
            "structured_report": structured_report,
        }

    if normalized_type == "file_bundle":
        source_items = payload.get("files") if isinstance(payload, dict) else payload
        return {"files": _normalize_file_bundle_entries(source_items)}

    if normalized_type == "archive_bundle":
        archive_payload = _normalize_archive_bundle_payload(payload, title=payload.get("title") if isinstance(payload, dict) else None, force=True)
        return archive_payload or payload

    if normalized_type == "media_gallery":
        source_items = payload.get("items") if isinstance(payload, dict) else payload
        return {"items": _normalize_media_entries(source_items)}

    if normalized_type == "directory_tree":
        directory_payload = _normalize_directory_tree_payload(payload, title=payload.get("title") if isinstance(payload, dict) else None, force=True)
        return directory_payload or payload

    if normalized_type == "document_pages":
        document_payload = _normalize_document_pages_payload(payload, title=payload.get("title") if isinstance(payload, dict) else None, force=True)
        return document_payload or payload

    if normalized_type == "document_excerpt":
        source_items = payload.get("items") if isinstance(payload, dict) else payload
        return {"items": _normalize_excerpt_entries(source_items)}

    if normalized_type == "paged_collection":
        title = payload.get("title") if isinstance(payload, dict) else None
        paged_payload = _normalize_paged_collection_payload(payload, title=title, force=True)
        return paged_payload or payload

    if normalized_type == "table":
        table_payload = _normalize_table_payload(payload)
        return table_payload or payload

    return payload


def _normalize_mcp_content_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, entry in enumerate(_normalize_mcp_content_entries(value)):
        if not isinstance(entry, dict):
            text = str(entry or "").strip()
            if text:
                items.append(
                    {
                        "title": f"Content {index + 1}",
                        "text": text,
                        "source": "",
                        "metadata": {},
                    }
                )
            continue

        item_type = str(entry.get("type") or "").strip().lower()
        if item_type == "text":
            text = str(entry.get("text") or "").strip()
        else:
            text = _extract_text_candidate(entry) or json.dumps(entry, ensure_ascii=False, indent=2)
        text = str(text or "").strip()
        if not text:
            continue

        items.append(
            {
                "title": str(entry.get("title") or entry.get("name") or f"Content {index + 1}").strip(),
                "text": text,
                "source": str(
                    entry.get("uri")
                    or entry.get("url")
                    or entry.get("href")
                    or entry.get("resource_link")
                    or entry.get("resourceLink")
                    or entry.get("mimeType")
                    or entry.get("mime_type")
                    or ""
                ).strip(),
                "metadata": _normalize_metadata(
                    entry,
                    {
                        "metadata",
                        "type",
                        "title",
                        "name",
                        "text",
                        "content",
                        "excerpt",
                        "uri",
                        "url",
                        "href",
                        "resource_link",
                        "resourceLink",
                        "mimeType",
                        "mime_type",
                    },
                ),
            }
        )
    return items


def _tool_artifact_name(tool_name: str, artifact_name: str | None, fallback: str) -> str:
    tool_label = str(tool_name or "").strip() or "Tool Result"
    base_name = str(artifact_name or "").strip() or fallback
    if base_name.lower().startswith(tool_label.lower()):
        return base_name
    return f"{tool_label} - {base_name}"


def _verification_title(tool_name: str, purpose: str | None) -> str:
    if tool_name in {"run_tests", "test_run"} or purpose == "test":
        return "Test Verification"
    if tool_name in {"run_lint", "lint_run"} or purpose == "lint":
        return "Lint Verification"
    if tool_name == "run_build" or purpose == "build":
        return "Build Verification"
    if tool_name == "typecheck_run" or purpose == "typecheck":
        return "Typecheck Verification"
    if tool_name == "coverage_run" or purpose == "coverage":
        return "Coverage Verification"
    if tool_name == "dependency_audit" or purpose == "dependency_audit":
        return "Dependency Audit"
    return "Sandbox Verification"


def _verification_kind(tool_name: str, purpose: str | None) -> str:
    if tool_name == "browser_verify" or purpose == "browser_verify":
        return "browser_verify"
    if tool_name in {"run_tests", "test_run"} or purpose == "test":
        return "test"
    if tool_name in {"run_lint", "lint_run"} or purpose == "lint":
        return "lint"
    if tool_name == "run_build" or purpose == "build":
        return "build"
    if tool_name == "typecheck_run" or purpose == "typecheck":
        return "typecheck"
    if tool_name == "coverage_run" or purpose == "coverage":
        return "coverage"
    if tool_name == "dependency_audit" or purpose == "dependency_audit":
        return "dependency_audit"
    return "shell"


def _browser_verification_report(payload: dict[str, Any]) -> dict[str, Any]:
    console_messages = payload.get("console_messages") if isinstance(payload.get("console_messages"), list) else []
    network_errors = payload.get("network_errors") if isinstance(payload.get("network_errors"), list) else []
    findings: list[dict[str, Any]] = []
    for item in console_messages:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or "info").strip() or "info"
        if level not in {"error", "warning", "warn"}:
            continue
        findings.append(
            {
                "title": str(item.get("text") or "Browser console issue").strip() or "Browser console issue",
                "severity": "error" if level == "error" else "warning",
                "type": "console",
                "source": "browser_console",
                "message": str(item.get("text") or "").strip(),
            }
        )
    for item in network_errors:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "title": str(item.get("url") or "Browser network error").strip() or "Browser network error",
                "severity": "error",
                "type": "network",
                "source": str(item.get("url") or "browser_network").strip() or "browser_network",
                "message": str(item.get("text") or "request failed").strip() or "request failed",
            }
        )
    return {
        "schema_version": "verification_report.v1",
        "summary": {
            "report_count": 1,
            "finding_count": len(findings),
            "console_message_count": len(console_messages),
            "network_error_count": len(network_errors),
        },
        "reports": [
            {
                "kind": "browser_verify",
                "format": "browser_diagnostics",
                "summary": {
                    "finding_count": len(findings),
                    "console_message_count": len(console_messages),
                    "network_error_count": len(network_errors),
                    "url": payload.get("url"),
                    "title": payload.get("title"),
                },
                "findings": findings,
                "truncated": bool(payload.get("truncated")),
            }
        ],
    }


def _verification_summary(status: Any, exit_code: Any, failure_category: Any) -> str:
    status_text = str(status or "unknown").strip() or "unknown"
    if status_text == "completed":
        return "Verification completed successfully."
    if status_text == "timeout":
        return "Verification timed out before completion."
    if status_text == "failed":
        category = str(failure_category or "non_zero_exit").strip() or "non_zero_exit"
        return f"Verification failed ({category})."
    if exit_code is not None:
        return f"Verification finished with exit code {exit_code}."
    return f"Verification status: {status_text}."


def _build_embedded_resource_artifacts(
    entry: Any,
    *,
    tool_name: str,
    tool_kind: str,
    step_id: str | None,
    tool_call_id: str | None,
    source: str,
) -> list[dict[str, Any]]:
    if not isinstance(entry, dict):
        return []

    candidates: list[dict[str, Any]] = []
    if isinstance(entry, dict):
        candidates.append(entry)
    resource = entry.get("resource")
    if isinstance(resource, dict):
        candidates.append(resource)

    promoted: list[dict[str, Any]] = []
    for candidate in candidates:
        directory_payload = _normalize_directory_tree_payload(candidate)
        if directory_payload:
            promoted.append(
                {
                    "artifact_type": "directory_tree",
                    "name": _tool_artifact_name(tool_name, directory_payload.get("title"), "Directory Tree"),
                    "payload": directory_payload,
                    "metadata": {
                        "source": source,
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "tool_call_id": tool_call_id,
                        "promoted_to_run": True,
                    },
                    "step_id": step_id,
                }
            )

        document_payload = _normalize_document_pages_payload(candidate)
        if document_payload:
            promoted.append(
                {
                    "artifact_type": "document_pages",
                    "name": _tool_artifact_name(tool_name, document_payload.get("title"), "Document Pages"),
                    "payload": document_payload,
                    "metadata": {
                        "source": source,
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "tool_call_id": tool_call_id,
                        "promoted_to_run": True,
                    },
                    "step_id": step_id,
                }
            )

        archive_payload = _normalize_archive_bundle_payload(candidate)
        if archive_payload:
            promoted.append(
                {
                    "artifact_type": "archive_bundle",
                    "name": _tool_artifact_name(tool_name, archive_payload.get("title"), "Archive Bundle"),
                    "payload": archive_payload,
                    "metadata": {
                        "source": source,
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "tool_call_id": tool_call_id,
                        "promoted_to_run": True,
                    },
                    "step_id": step_id,
                }
            )
    return merge_artifacts(promoted)


def _normalize_artifact_entry(artifact: Dict[str, Any]) -> dict[str, Any]:
    artifact_type = str(artifact.get("artifact_type") or "answer").strip() or "answer"
    return {
        "artifact_type": artifact_type,
        "name": str(artifact.get("name") or "Untitled Artifact").strip() or "Untitled Artifact",
        "payload": _normalize_artifact_payload(
            artifact_type,
            artifact.get("payload") if artifact.get("payload") is not None else {},
        ),
        "metadata": dict(artifact.get("metadata") or {}),
        "step_id": artifact.get("step_id"),
        "mime_type": artifact.get("mime_type"),
        "uri": artifact.get("uri"),
    }


def _artifact_signature(artifact: Dict[str, Any]) -> str:
    normalized = _normalize_artifact_entry(artifact)
    return json.dumps(
        {
            "artifact_type": normalized["artifact_type"],
            "payload": normalized["payload"],
            "mime_type": normalized["mime_type"],
            "uri": normalized["uri"],
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def merge_artifacts(*artifact_groups: list[Dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for group in artifact_groups:
        if not group:
            continue
        for artifact in group:
            if not isinstance(artifact, dict):
                continue
            normalized = _normalize_artifact_entry(artifact)
            signature = _artifact_signature(normalized)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            merged.append(normalized)

    return sorted(
        merged,
        key=lambda item: (
            ARTIFACT_TYPE_PRIORITY.get(str(item.get("artifact_type") or ""), 100),
            str(item.get("name") or ""),
        ),
    )


def build_artifacts_from_tool_result(
    value: Any,
    *,
    tool_name: str = "",
    tool_kind: str = "",
    step_id: str | None = None,
    tool_call_id: str | None = None,
    include_answer: bool = False,
    source: str = "tool_call",
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []

    payload = dict(value)
    text = str(payload.get("text") or "").strip() if _is_non_empty_string(payload.get("text")) else ""
    structured_content = payload.get("structured_content")
    if structured_content is None:
        structured_content = payload.get("structuredContent")

    promoted: list[dict[str, Any]] = []
    if structured_content is not None and structured_content != "":
        promoted.extend(
            _promote_structured_artifacts(
                structured_content,
                tool_name=tool_name,
                tool_kind=tool_kind,
                step_id=step_id,
                tool_call_id=tool_call_id,
                include_answer=include_answer,
                source=source,
            )
        )

    if tool_name == "workspace_status" and isinstance(payload.get("workspace"), dict):
        workspace_payload = dict(payload.get("workspace") or {})
        promoted.append(
            {
                "artifact_type": "workspace_summary",
                "name": _tool_artifact_name(tool_name, None, "Workspace Binding"),
                "payload": workspace_payload,
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "workspace_tree" and isinstance(payload.get("entries"), list):
        promoted.append(
            {
                "artifact_type": "directory_tree",
                "name": _tool_artifact_name(tool_name, None, "Directory Tree"),
                "payload": {
                    "title": payload.get("path") or "Workspace Tree",
                    "entries": payload.get("entries") or [],
                    "root_name": payload.get("path") or ".",
                    "summary": {
                        "file_count": sum(1 for item in payload.get("entries") or [] if isinstance(item, dict) and item.get("type") == "file"),
                        "directory_count": sum(1 for item in payload.get("entries") or [] if isinstance(item, dict) and item.get("type") == "directory"),
                    },
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "workspace_root": payload.get("workspace_root"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "workspace_list_files" and isinstance(payload.get("entries"), list):
        promoted.append(
            {
                "artifact_type": "file_bundle",
                "name": _tool_artifact_name(tool_name, None, "Files"),
                "payload": {
                    "files": [
                        {
                            "name": str(item.get("path") or "").rsplit("/", 1)[-1],
                            "path": item.get("path"),
                            "size_bytes": item.get("size_bytes"),
                            "description": item.get("type"),
                            "metadata": {"type": item.get("type")},
                        }
                        for item in payload.get("entries") or []
                        if isinstance(item, dict)
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "workspace_root": payload.get("workspace_root"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "workspace_file_info" and _is_non_empty_string(payload.get("path")):
        promoted.append(
            {
                "artifact_type": "file_bundle",
                "name": _tool_artifact_name(tool_name, payload.get("path"), "File Info"),
                "payload": {
                    "files": [
                        {
                            "name": str(payload.get("path") or "").rsplit("/", 1)[-1] or str(payload.get("path") or ""),
                            "path": payload.get("path"),
                            "size_bytes": payload.get("size_bytes"),
                            "description": payload.get("type"),
                            "metadata": {
                                key: value
                                for key, value in payload.items()
                                if key not in {"path", "size_bytes", "type"}
                            },
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "workspace_read_file" and _is_non_empty_string(payload.get("content")):
        promoted.append(
            {
                "artifact_type": "code_files",
                "name": _tool_artifact_name(tool_name, payload.get("path"), "File"),
                "payload": {
                    "files": [
                        {
                            "path": payload.get("path"),
                            "language": _guess_language(str(payload.get("path") or ""), ""),
                            "content": payload.get("content") or "",
                            "metadata": {
                                "size_bytes": payload.get("size_bytes"),
                                "truncated": payload.get("truncated"),
                            },
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "workspace_search_text" and isinstance(payload.get("matches"), list):
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, None, "Search Matches"),
                "payload": {
                    "items": [
                        {
                            "title": f"{item.get('path')}:{item.get('line')}",
                            "text": item.get("preview") or "",
                            "source": item.get("path"),
                            "metadata": {
                                "line": item.get("line"),
                                "line_truncated": item.get("line_truncated"),
                            },
                        }
                        for item in payload.get("matches") or []
                        if isinstance(item, dict)
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "query": payload.get("query"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name in {"git_status", "git_diff", "git_show", "git_log", "git_branch"}:
        stdout = payload.get("stdout") if _is_non_empty_string(payload.get("stdout")) else ""
        if not stdout and payload.get("exit_code") == 0 and tool_name in {"git_status", "git_diff"}:
            stdout = "No changes."
        if not stdout and _is_non_empty_string(payload.get("stderr")):
            stdout = str(payload.get("stderr") or "")
        if not stdout:
            stdout = f"{tool_name} completed with exit code {payload.get('exit_code')}."
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, None, "Git Output"),
                "payload": {
                    "items": [
                        {
                            "title": " ".join(str(item) for item in payload.get("command") or []),
                            "text": stdout,
                            "source": "git",
                            "metadata": {
                                "exit_code": payload.get("exit_code"),
                                "stderr": payload.get("stderr"),
                                "truncated": payload.get("truncated"),
                            },
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "web_search" and isinstance(payload.get("items"), list):
        promoted.append(
            {
                "artifact_type": "citations",
                "name": _tool_artifact_name(tool_name, None, "Search Results"),
                "payload": {
                    "items": [
                        {
                            "title": item.get("title") or item.get("url") or "Search Result",
                            "url": item.get("url") or "",
                            "snippet": item.get("snippet") or "",
                            "source": payload.get("source") or "web_search",
                            "metadata": {
                                "query": payload.get("query"),
                                "fetched_at": payload.get("fetched_at"),
                            },
                        }
                        for item in payload.get("items") or []
                        if isinstance(item, dict)
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "query": payload.get("query"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name in {"open_page", "extract_page_text", "fetch_url"} and (
        _is_non_empty_string(payload.get("text")) or _is_non_empty_string(payload.get("error"))
    ):
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, payload.get("title"), "Web Page"),
                "payload": {
                    "items": [
                        {
                            "title": payload.get("title") or payload.get("url") or tool_name,
                            "text": payload.get("text") or payload.get("error") or "",
                            "source": payload.get("url") or payload.get("requested_url") or "web",
                            "metadata": {
                                "requested_url": payload.get("requested_url"),
                                "status": payload.get("status"),
                                "fetched_at": payload.get("fetched_at"),
                                "truncated": payload.get("truncated"),
                                "failure_category": payload.get("failure_category"),
                            },
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "status": payload.get("status"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "browser_verify":
        promoted.append(
            {
                "artifact_type": "verification_report",
                "name": _tool_artifact_name(tool_name, None, "Browser Verification"),
                "payload": {
                    "kind": "browser_verify",
                    "status": payload.get("status") or "unknown",
                    "summary": str(payload.get("summary") or "Browser verification completed.").strip(),
                    "truncated": bool(payload.get("truncated")),
                    "structured_report": (
                        payload.get("structured_report")
                        if isinstance(payload.get("structured_report"), dict)
                        else payload.get("structuredReport")
                        if isinstance(payload.get("structuredReport"), dict)
                        else _browser_verification_report(payload)
                    ),
                    "logs": {
                        "stdout": payload.get("text") or payload.get("html") or "",
                        "stderr": "",
                    },
                    "runner": {
                        "backend": "browser",
                        "url": payload.get("url"),
                        "session_id": payload.get("session_id"),
                    },
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "session_id": payload.get("session_id"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name in {"browser_open", "browser_click", "browser_type", "browser_snapshot"} and (
        _is_non_empty_string(payload.get("text")) or _is_non_empty_string(payload.get("html"))
    ):
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, payload.get("title"), "Browser Snapshot"),
                "payload": {
                    "items": [
                        {
                            "title": payload.get("title") or payload.get("url") or tool_name,
                            "text": payload.get("text") or payload.get("html") or "",
                            "source": payload.get("url") or "browser",
                            "metadata": {
                                "session_id": payload.get("session_id"),
                                "captured_at": payload.get("captured_at"),
                                "http_status": payload.get("http_status"),
                                "viewport": payload.get("viewport"),
                                "action": payload.get("action"),
                                "selector": payload.get("selector"),
                                "truncated": payload.get("truncated"),
                            },
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "session_id": payload.get("session_id"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "browser_screenshot" and isinstance(payload.get("images"), list):
        promoted.append(
            {
                "artifact_type": "media_gallery",
                "name": _tool_artifact_name(tool_name, payload.get("title"), "Browser Screenshot"),
                "payload": {"items": _normalize_media_entries(payload.get("images"))},
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "session_id": payload.get("session_id"),
                    "captured_at": payload.get("captured_at"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "pdf_extract" and isinstance(payload.get("pages"), list):
        promoted.append(
            {
                "artifact_type": "document_pages",
                "name": _tool_artifact_name(tool_name, payload.get("filename"), "PDF Extract"),
                "payload": {
                    "title": payload.get("filename") or payload.get("url") or "PDF Extract",
                    "pages": payload.get("pages") or [],
                    "source": payload.get("url") or payload.get("requested_url"),
                    "metadata": {
                        "requested_url": payload.get("requested_url"),
                        "status": payload.get("status"),
                        "fetched_at": payload.get("fetched_at"),
                        "page_count": payload.get("page_count"),
                        "extracted_pages": payload.get("extracted_pages"),
                        "sha256": payload.get("sha256"),
                        "truncated": payload.get("truncated"),
                    },
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "requested_url": payload.get("requested_url"),
                    "status": payload.get("status"),
                    "truncated": payload.get("truncated"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name == "download_file" and isinstance(payload.get("files"), list):
        promoted.append(
            {
                "artifact_type": "file_bundle",
                "name": _tool_artifact_name(tool_name, payload.get("filename"), "Downloaded File"),
                "payload": {
                    "files": _normalize_file_bundle_entries(payload.get("files")),
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "url": payload.get("url"),
                    "requested_url": payload.get("requested_url"),
                    "status": payload.get("status"),
                    "content_type": payload.get("content_type"),
                    "bytes": payload.get("bytes"),
                    "sha256": payload.get("sha256"),
                    "truncated": payload.get("truncated"),
                    "failure_category": payload.get("failure_category"),
                },
                "step_id": step_id,
            }
        )
    elif tool_name in {"workspace_apply_patch", "workspace_create_file", "workspace_write_file", "workspace_rename_path", "workspace_delete_path"}:
        patch_promoted = False
        for artifact in payload.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            normalized = _normalize_artifact_entry(artifact)
            promoted.append(
                {
                    **normalized,
                    "name": _tool_artifact_name(tool_name, normalized.get("name"), "Workspace Patch"),
                    "metadata": {
                        **dict(normalized.get("metadata") or {}),
                        "source": source,
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "tool_call_id": tool_call_id,
                        "promoted_to_run": True,
                        "path": payload.get("path"),
                        "source_path": payload.get("source_path"),
                        "target_path": payload.get("target_path"),
                        "operation": payload.get("operation"),
                        "dry_run": payload.get("dry_run"),
                        "changed": payload.get("changed"),
                    },
                    "step_id": step_id or normalized.get("step_id"),
                }
            )
            patch_promoted = True
        if not patch_promoted:
            promoted.append(
                {
                    "artifact_type": "code_patch",
                    "name": _tool_artifact_name(tool_name, None, "Workspace Patch"),
                    "payload": {
                        "operation": payload.get("operation"),
                        "status": payload.get("status"),
                        "dry_run": payload.get("dry_run"),
                        "files": [
                            {
                                "path": payload.get("path"),
                                "operation": payload.get("operation"),
                                "before_sha256": payload.get("before_sha256"),
                                "after_sha256": payload.get("after_sha256"),
                                "changed": payload.get("changed"),
                            }
                        ],
                        "diff": payload.get("diff") or "",
                        "truncated": payload.get("truncated"),
                        "review_notes": payload.get("review_notes") or [],
                        "merge_policy": payload.get("merge_policy") or "manual_review_required",
                    },
                    "metadata": {
                        "source": source,
                        "tool_name": tool_name,
                        "tool_kind": tool_kind,
                        "tool_call_id": tool_call_id,
                        "promoted_to_run": True,
                    },
                    "step_id": step_id,
                }
            )
    elif tool_name in {
        "shell_exec",
        "run_tests",
        "run_lint",
        "run_build",
        "test_run",
        "lint_run",
        "typecheck_run",
        "coverage_run",
        "dependency_audit",
    }:
        stdout = payload.get("stdout") if _is_non_empty_string(payload.get("stdout")) else ""
        stderr = payload.get("stderr") if _is_non_empty_string(payload.get("stderr")) else ""
        output_text = "\n".join(item for item in (stdout, stderr) if item).strip()
        if not output_text:
            output_text = f"{tool_name} completed with status {payload.get('status') or 'unknown'}."
        purpose = str(payload.get("purpose") or "").strip() or None
        promoted.append(
            {
                "artifact_type": "verification_report",
                "name": _tool_artifact_name(tool_name, None, _verification_title(tool_name, purpose)),
                "payload": {
                    "kind": _verification_kind(tool_name, purpose),
                    "status": payload.get("status") or "unknown",
                    "exit_code": payload.get("exit_code"),
                    "command": payload.get("command") or [],
                    "cwd": payload.get("cwd") or ".",
                    "duration_ms": payload.get("duration_ms") or 0,
                    "timeout_seconds": payload.get("timeout_seconds"),
                    "summary": _verification_summary(
                        payload.get("status"),
                        payload.get("exit_code"),
                        payload.get("failure_category"),
                    ),
                    "failure_category": payload.get("failure_category"),
                    "truncated": payload.get("truncated"),
                    "logs": {
                        "stdout": stdout,
                        "stderr": stderr,
                    },
                    "runner": payload.get("runner") if isinstance(payload.get("runner"), dict) else {},
                    "selector": payload.get("selector"),
                    "target": payload.get("target"),
                    "ecosystem": payload.get("ecosystem"),
                    "report_format": payload.get("report_format"),
                    "structured_report": payload.get("structured_report") if isinstance(payload.get("structured_report"), dict) else None,
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                    "status": payload.get("status"),
                    "exit_code": payload.get("exit_code"),
                    "failure_category": payload.get("failure_category"),
                },
                "step_id": step_id,
            }
        )

    content_preview_items: list[dict[str, Any]] = []
    content_code_files: list[dict[str, Any]] = []
    content_media_items: list[dict[str, Any]] = []
    content_file_bundle: list[dict[str, Any]] = []
    for index, entry in enumerate(_normalize_mcp_content_entries(payload.get("content"))):
        core = _extract_content_core(entry, index)
        resource_dict = entry.get("resource") if isinstance(entry, dict) and isinstance(entry.get("resource"), dict) else {}
        for structured_candidate in (
            entry.get("structured_content") if isinstance(entry, dict) else None,
            entry.get("structuredContent") if isinstance(entry, dict) else None,
            resource_dict.get("structured_content") if isinstance(resource_dict, dict) else None,
            resource_dict.get("structuredContent") if isinstance(resource_dict, dict) else None,
        ):
            if structured_candidate in (None, ""):
                continue
            promoted.extend(
                _promote_structured_artifacts(
                    structured_candidate,
                    tool_name=tool_name,
                    tool_kind=tool_kind,
                    step_id=step_id,
                    tool_call_id=tool_call_id,
                    include_answer=include_answer,
                    source=source,
                    extra_metadata=core.get("metadata") if isinstance(core.get("metadata"), dict) else None,
                )
            )

        embedded_artifacts = _build_embedded_resource_artifacts(
            entry,
            tool_name=tool_name,
            tool_kind=tool_kind,
            step_id=step_id,
            tool_call_id=tool_call_id,
            source=source,
        )
        if embedded_artifacts:
            promoted.extend(embedded_artifacts)
        parsed_text = _maybe_parse_json_like(core["text"])
        if isinstance(parsed_text, (dict, list)):
            structured_artifacts = _promote_structured_artifacts(
                parsed_text,
                tool_name=tool_name,
                tool_kind=tool_kind,
                step_id=step_id,
                tool_call_id=tool_call_id,
                include_answer=include_answer,
                source=source,
                extra_metadata=core.get("metadata") if isinstance(core.get("metadata"), dict) else None,
            )
            if structured_artifacts:
                promoted.extend(structured_artifacts)
                continue

        if embedded_artifacts and not core["text"]:
            continue

        if core["kind"] in {"image", "video", "audio"} and core["uri"]:
            content_media_items.append(
                {
                    "title": core["title"],
                    "uri": core["uri"],
                    "mime_type": core["mime_type"],
                    "kind": core["kind"],
                    "alt": core["description"] or core["title"],
                    "path": core["path"],
                    "source": core["source"],
                    "size_bytes": core["size_bytes"],
                    "metadata": dict(core.get("metadata") or {}),
                }
            )
            continue

        if core["text"] and _is_code_like_content(core["path"], core["mime_type"]):
            content_code_files.append(
                {
                    "path": core["path"] or core["title"],
                    "language": _guess_language(core["path"], core["mime_type"]),
                    "content": core["text"],
                    "metadata": {
                        "source": core["source"],
                        "mime_type": core["mime_type"],
                        **dict(core.get("metadata") or {}),
                    },
                }
            )
            continue

        if core["text"]:
            content_preview_items.append(
                {
                    "title": core["title"],
                    "text": core["text"],
                    "source": core["source"] or core["mime_type"],
                    "metadata": dict(core.get("metadata") or {}),
                }
            )
            continue

        if core["uri"] or core["path"]:
            content_file_bundle.append(
                {
                    "name": core["title"],
                    "path": core["path"],
                    "uri": core["uri"],
                    "mime_type": core["mime_type"],
                    "size_bytes": core["size_bytes"],
                    "description": core["description"],
                    "preview_text": "",
                    "source": core["source"],
                    "metadata": dict(core.get("metadata") or {}),
                }
            )

    if content_code_files:
        promoted.append(
            {
                "artifact_type": "code_files",
                "name": _tool_artifact_name(tool_name, None, "Files"),
                "payload": {"files": content_code_files},
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )

    if content_media_items:
        promoted.append(
            {
                "artifact_type": "media_gallery",
                "name": _tool_artifact_name(tool_name, None, "Media"),
                "payload": {"items": content_media_items},
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )

    if content_file_bundle:
        promoted.append(
            {
                "artifact_type": "file_bundle",
                "name": _tool_artifact_name(tool_name, None, "Files"),
                "payload": {"files": content_file_bundle},
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )

    if content_preview_items:
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, None, "Preview"),
                "payload": {"items": content_preview_items},
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )

    if not promoted and text:
        promoted.append(
            {
                "artifact_type": "document_excerpt",
                "name": _tool_artifact_name(tool_name, None, "Preview"),
                "payload": {
                    "items": [
                        {
                            "title": str(tool_name or "Tool Result").strip() or "Tool Result",
                            "text": text,
                            "source": "",
                        }
                    ]
                },
                "metadata": {
                    "source": source,
                    "tool_name": tool_name,
                    "tool_kind": tool_kind,
                    "tool_call_id": tool_call_id,
                    "promoted_to_run": True,
                },
                "step_id": step_id,
            }
        )

    return merge_artifacts(promoted)


def build_structured_run_result(
    value: Any,
    *,
    fallback_text: Optional[str] = None,
) -> dict[str, Any]:
    normalized_value = _normalize_structured_root(_maybe_parse_json_like(value))
    final_output_json = normalized_value if isinstance(normalized_value, (dict, list)) else None
    final_output_text = _extract_text_candidate(normalized_value) or (_extract_text_candidate(fallback_text) if fallback_text else None)
    artifacts: list[dict[str, Any]] = []

    if final_output_text:
        _append_artifact(
            artifacts,
            artifact_type="answer",
            name="Final Answer",
            payload={"text": final_output_text, "format": "markdown"},
        )

    if isinstance(final_output_json, dict):
        for key in PLAN_KEYS:
            if key in final_output_json:
                _append_artifact(
                    artifacts,
                    artifact_type="task_plan",
                    name=_compact_title(key, "Task Plan"),
                    payload=final_output_json[key],
                )
                break

        for key in CITATION_KEYS:
            citations = _normalize_citations(final_output_json.get(key))
            if citations:
                _append_artifact(
                    artifacts,
                    artifact_type="citations",
                    name=_compact_title(key, "Citations"),
                    payload={"items": citations},
                )
                break

        for key in FINDING_KEYS:
            findings = _normalize_findings(final_output_json.get(key))
            if findings:
                _append_artifact(
                    artifacts,
                    artifact_type="review_findings",
                    name=_compact_title(key, "Review Findings"),
                    payload={"items": findings},
                )
                break

        for key in CODE_FILE_KEYS:
            files = _normalize_code_files(final_output_json.get(key))
            if files:
                _append_artifact(
                    artifacts,
                    artifact_type="code_files",
                    name=_compact_title(key, "Code Files"),
                    payload={"files": files},
                )
                break

        for key in DIRECTORY_TREE_KEYS:
            directory_payload = _normalize_directory_tree_payload(
                final_output_json.get(key),
                title=_compact_title(key, "Directory Tree"),
                force=key in final_output_json,
            )
            if directory_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="directory_tree",
                    name=_compact_title(key, "Directory Tree"),
                    payload=directory_payload,
                )
                break

        for key in DOCUMENT_PAGE_KEYS:
            document_payload = _normalize_document_pages_payload(
                final_output_json.get(key),
                title=_compact_title(key, "Document Pages"),
                force=key in final_output_json,
            )
            if document_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="document_pages",
                    name=_compact_title(key, "Document Pages"),
                    payload=document_payload,
                )
                break

        for key in PAGED_KEYS:
            paged_payload = _normalize_paged_collection_payload(
                final_output_json.get(key),
                context=final_output_json,
                title=_compact_title(key, "Paged Collection"),
                force=key in final_output_json,
            )
            if paged_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="paged_collection",
                    name=_compact_title(key, "Paged Collection"),
                    payload=paged_payload,
                )
                break

        for key in MEDIA_KEYS:
            media_items = _normalize_media_entries(final_output_json.get(key))
            if media_items:
                _append_artifact(
                    artifacts,
                    artifact_type="media_gallery",
                    name=_compact_title(key, "Media Gallery"),
                    payload={"items": media_items},
                )
                break

        for key in FILE_BUNDLE_KEYS:
            files = _normalize_file_bundle_entries(final_output_json.get(key))
            if files:
                _append_artifact(
                    artifacts,
                    artifact_type="file_bundle",
                    name=_compact_title(key, "File Bundle"),
                    payload={"files": files},
                )
                break

        for key in ARCHIVE_BUNDLE_KEYS:
            archive_payload = _normalize_archive_bundle_payload(
                final_output_json.get(key),
                title=_compact_title(key, "Archive Bundle"),
                force=key in final_output_json,
            )
            if archive_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="archive_bundle",
                    name=_compact_title(key, "Archive Bundle"),
                    payload=archive_payload,
                )
                break

        for key in TABLE_KEYS:
            table_payload = _normalize_table_payload(final_output_json.get(key))
            if table_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="table",
                    name=_compact_title(key, "Table"),
                    payload=table_payload,
                )
                break

        for key in EXCERPT_KEYS:
            excerpts = _normalize_excerpt_entries(final_output_json.get(key))
            if excerpts:
                _append_artifact(
                    artifacts,
                    artifact_type="document_excerpt",
                    name=_compact_title(key, "Document Excerpt"),
                    payload={"items": excerpts},
                )
                break

        _append_implicit_list_artifacts(artifacts, final_output_json)

        if not _has_artifact_type(artifacts, "directory_tree"):
            directory_payload = _normalize_directory_tree_payload(final_output_json)
            if directory_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="directory_tree",
                    name=directory_payload.get("title") or "Directory Tree",
                    payload=directory_payload,
                )

        if not _has_artifact_type(artifacts, "document_pages"):
            document_payload = _normalize_document_pages_payload(final_output_json)
            if document_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="document_pages",
                    name=document_payload.get("title") or "Document Pages",
                    payload=document_payload,
                )

        if not _has_artifact_type(artifacts, "archive_bundle"):
            archive_payload = _normalize_archive_bundle_payload(final_output_json)
            if archive_payload:
                _append_artifact(
                    artifacts,
                    artifact_type="archive_bundle",
                    name=archive_payload.get("title") or "Archive Bundle",
                    payload=archive_payload,
                )

    if isinstance(final_output_json, list):
        directory_payload = _normalize_directory_tree_payload(final_output_json)
        if directory_payload:
            _append_artifact(
                artifacts,
                artifact_type="directory_tree",
                name=directory_payload.get("title") or "Directory Tree",
                payload=directory_payload,
            )

        document_payload = _normalize_document_pages_payload(final_output_json)
        if document_payload:
            _append_artifact(
                artifacts,
                artifact_type="document_pages",
                name=document_payload.get("title") or "Document Pages",
                payload=document_payload,
            )

        media_items = _normalize_media_entries(final_output_json)
        if media_items:
            _append_artifact(
                artifacts,
                artifact_type="media_gallery",
                name="Media Gallery",
                payload={"items": media_items},
            )

        files = _normalize_file_bundle_entries(final_output_json)
        if files:
            _append_artifact(
                artifacts,
                artifact_type="file_bundle",
                name="File Bundle",
                payload={"files": files},
            )

        archive_payload = _normalize_archive_bundle_payload(final_output_json)
        if archive_payload:
            _append_artifact(
                artifacts,
                artifact_type="archive_bundle",
                name=archive_payload.get("title") or "Archive Bundle",
                payload=archive_payload,
            )

        table_payload = _normalize_table_payload(final_output_json)
        if table_payload:
            _append_artifact(
                artifacts,
                artifact_type="table",
                name="Result Table",
                payload=table_payload,
            )

    legacy_final_output = final_output_text
    if not legacy_final_output and final_output_json is not None:
        legacy_final_output = json.dumps(final_output_json, ensure_ascii=False, indent=2)
    if not legacy_final_output and _is_non_empty_string(fallback_text):
        legacy_final_output = str(fallback_text).strip()

    return {
        "final_output": legacy_final_output,
        "final_output_text": final_output_text,
        "final_output_json": final_output_json,
        "artifacts": merge_artifacts(artifacts),
    }


def hydrate_legacy_result(
    *,
    final_output: Any = None,
    final_output_text: Any = None,
    final_output_json: Any = None,
    artifacts: Optional[List[Dict[str, Any]]] = None,
) -> dict[str, Any]:
    normalized_artifacts = list(artifacts or [])
    text_value = str(final_output_text).strip() if _is_non_empty_string(final_output_text) else None
    legacy_text = str(final_output).strip() if _is_non_empty_string(final_output) else None
    result_json = final_output_json if isinstance(final_output_json, (dict, list)) else None

    if not text_value and legacy_text:
        text_value = legacy_text

    derived_result = build_structured_run_result(
        result_json if result_json is not None else text_value or legacy_text or "",
        fallback_text=text_value or legacy_text,
    )
    if not text_value and _is_non_empty_string(derived_result.get("final_output_text")):
        text_value = str(derived_result["final_output_text"]).strip()
    if not legacy_text and _is_non_empty_string(derived_result.get("final_output")):
        legacy_text = str(derived_result["final_output"]).strip()
    normalized_artifacts = merge_artifacts(
        normalized_artifacts,
        derived_result.get("artifacts") or [],
    )

    return {
        "final_output": legacy_text or text_value,
        "final_output_text": text_value,
        "final_output_json": result_json,
        "artifacts": normalized_artifacts,
    }
