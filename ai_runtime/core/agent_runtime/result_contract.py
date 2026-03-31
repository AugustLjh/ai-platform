from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


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
        string_items = [str(item).strip() for item in value if _is_non_empty_string(item)]
        if string_items:
            return "\n".join(string_items)
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

    return None


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
                    "metadata": {key: value for key, value in entry.items() if key not in {"path", "file_path", "name", "language", "content", "patch"}},
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
                    "metadata": {
                        key: value
                        for key, value in entry.items()
                        if key not in {"title", "summary", "message", "severity", "level", "description", "details", "path", "file", "line", "code"}
                    },
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
                    "metadata": {
                        key: value
                        for key, value in entry.items()
                        if key not in {"title", "name", "source", "url", "link", "snippet", "quote", "excerpt"}
                    },
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
                    "text": entry.get("text") or entry.get("content") or entry.get("excerpt") or "",
                    "source": entry.get("source"),
                    "metadata": {
                        key: value
                        for key, value in entry.items()
                        if key not in {"title", "heading", "text", "content", "excerpt", "source"}
                    },
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


def build_structured_run_result(
    value: Any,
    *,
    fallback_text: Optional[str] = None,
) -> dict[str, Any]:
    final_output_json = value if isinstance(value, (dict, list)) else None
    final_output_text = _extract_text_candidate(value) or (_extract_text_candidate(fallback_text) if fallback_text else None)
    artifacts: list[dict[str, Any]] = []

    if final_output_text:
        _append_artifact(
            artifacts,
            artifact_type="answer",
            name="Final Answer",
            payload={"text": final_output_text, "format": "markdown"},
        )

    if isinstance(final_output_json, dict):
        if "task_plan" not in final_output_json and isinstance(final_output_json.get("steps"), list):
            final_output_json = {
                **final_output_json,
                "task_plan": {
                    "summary": final_output_json.get("summary") or final_output_json.get("answer") or "",
                    "steps": final_output_json.get("steps") or [],
                    "decisions": final_output_json.get("decisions") or [],
                },
            }

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

    if isinstance(final_output_json, list):
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
        "artifacts": artifacts,
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

    if not normalized_artifacts:
        normalized_artifacts = build_structured_run_result(
            result_json if result_json is not None else text_value or legacy_text or "",
            fallback_text=text_value or legacy_text,
        )["artifacts"]

    return {
        "final_output": legacy_text or text_value,
        "final_output_text": text_value,
        "final_output_json": result_json,
        "artifacts": normalized_artifacts,
    }
