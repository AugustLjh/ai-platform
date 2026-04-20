from __future__ import annotations

from typing import Any


PROGRESS_PROTOCOL_VERSION = "managed-subagent.progress.v1"
CLARIFICATION_PROTOCOL_VERSION = "managed-subagent.clarification.v1"

_PROGRESS_STATE_ALIASES = {
    "queued": "requested",
    "requested": "requested",
    "pending": "requested",
    "running": "in_progress",
    "working": "in_progress",
    "in_progress": "in_progress",
    "in-progress": "in_progress",
    "blocked": "blocked",
    "waiting": "blocked",
    "waiting_user": "blocked",
    "waiting-user": "blocked",
    "waiting_input": "blocked",
    "waiting-input": "blocked",
    "clarification": "blocked",
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "succeeded": "completed",
    "success": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}

_CLARIFICATION_STATE_ALIASES = {
    "required": "required",
    "needs_input": "required",
    "need_input": "required",
    "waiting_user": "required",
    "waiting-user": "required",
    "blocked": "required",
    "resolved": "resolved",
    "completed": "resolved",
    "not_required": "not_required",
    "none": "not_required",
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_text_list(value: Any) -> list[str]:
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = [segment for segment in value.replace("\r", "\n").split("\n")]
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _stringify(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _extract_first_mapping(container: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = container.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_first_text(container: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _stringify(container.get(key))
        if text:
            return text
    return ""


def _extract_first_text_list(container: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        items = _normalize_text_list(container.get(key))
        if items:
            return items
    return []


def _normalize_progress_state(value: Any, *, fallback: str) -> str:
    text = _stringify(value).lower().replace(" ", "_")
    if not text:
        return fallback
    return _PROGRESS_STATE_ALIASES.get(text, fallback)


def _normalize_clarification_state(value: Any, *, fallback: str) -> str:
    text = _stringify(value).lower().replace(" ", "_")
    if not text:
        return fallback
    return _CLARIFICATION_STATE_ALIASES.get(text, fallback)


def build_requested_progress_payload(
    *,
    summary: str,
    delegate_task: str,
    delegate_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scope_items: list[str] = []
    payload = delegate_input or {}
    for key in ("deliverables", "checks", "focus_paths", "constraints"):
        values = _normalize_text_list(payload.get(key))
        if not values:
            continue
        if key == "focus_paths":
            scope_items.extend(f"Focus path: {value}" for value in values)
        elif key == "deliverables":
            scope_items.extend(f"Deliverable: {value}" for value in values)
        elif key == "checks":
            scope_items.extend(f"Check: {value}" for value in values)
        else:
            scope_items.extend(values)
    if delegate_task:
        scope_items.insert(0, delegate_task)

    return {
        "protocol_version": PROGRESS_PROTOCOL_VERSION,
        "state": "in_progress",
        "summary": summary or None,
        "completed_items": [],
        "pending_items": list(dict.fromkeys(item for item in scope_items if item)),
        "next_action": "Child capability should execute the delegated task and return a bounded result.",
        "artifact_count": 0,
        "source": "handoff_request",
    }


def build_progress_payload(
    *,
    status: str,
    hydrated: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    final_output_json = hydrated.get("final_output_json")
    artifacts = hydrated.get("artifacts") if isinstance(hydrated.get("artifacts"), list) else []
    payload = final_output_json if isinstance(final_output_json, dict) else {}
    raw_progress = _extract_first_mapping(payload, "progress", "progress_update", "status_update")

    fallback_state = {
        "waiting_user": "blocked",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }.get(str(status or "").strip().lower(), "in_progress")
    state = _normalize_progress_state(raw_progress.get("state"), fallback=fallback_state)

    progress_summary = _extract_first_text(
        raw_progress,
        "summary",
        "status",
        "message",
    ) or _extract_first_text(
        payload,
        "progress_summary",
        "summary",
        "answer",
        "conclusion",
    ) or summary

    completed_items = _extract_first_text_list(
        raw_progress,
        "completed_items",
        "completed",
        "done",
    ) or _extract_first_text_list(
        payload,
        "completed_items",
        "completed_work",
        "completed_steps",
    )
    pending_items = _extract_first_text_list(
        raw_progress,
        "pending_items",
        "remaining_items",
        "open_items",
    ) or _extract_first_text_list(
        payload,
        "pending_items",
        "remaining_work",
        "next_steps",
        "open_questions",
    )
    next_action = _extract_first_text(
        raw_progress,
        "next_action",
        "next_step",
        "next",
    ) or _extract_first_text(
        payload,
        "next_action",
        "next_step",
        "recommendation",
    )
    if state == "blocked" and not next_action:
        next_action = "Answer the clarification so the child run can continue."

    return {
        "protocol_version": PROGRESS_PROTOCOL_VERSION,
        "state": state,
        "summary": progress_summary or None,
        "completed_items": completed_items,
        "pending_items": pending_items,
        "next_action": next_action or None,
        "artifact_count": len(artifacts),
        "source": "result_payload" if raw_progress else "status_fallback",
    }


def build_clarification_payload(
    *,
    status: str,
    hydrated: dict[str, Any],
    question: str | None = None,
) -> dict[str, Any] | None:
    final_output_json = hydrated.get("final_output_json")
    payload = final_output_json if isinstance(final_output_json, dict) else {}
    raw_clarification = _extract_first_mapping(payload, "clarification", "clarification_request", "input_request")

    fallback_question = _stringify(question or hydrated.get("final_output_text") or hydrated.get("final_output"))
    clarification_question = _extract_first_text(
        raw_clarification,
        "question",
        "prompt",
        "request",
        "message",
    ) or _extract_first_text(payload, "question", "clarification_question") or fallback_question

    required_fields = _extract_first_text_list(
        raw_clarification,
        "required_fields",
        "missing_fields",
        "requested_fields",
        "inputs",
    ) or _extract_first_text_list(
        payload,
        "required_fields",
        "missing_fields",
        "requested_fields",
    )
    reason = _extract_first_text(
        raw_clarification,
        "reason",
        "blocking_reason",
        "context",
    ) or _extract_first_text(payload, "clarification_reason", "missing_information")
    response_hint = _extract_first_text(
        raw_clarification,
        "response_hint",
        "response_format",
        "expected_response",
    )

    waiting_user = str(status or "").strip().lower() == "waiting_user"
    state = _normalize_clarification_state(
        raw_clarification.get("state") or raw_clarification.get("status"),
        fallback="required" if waiting_user else "resolved",
    )
    blocking = bool(raw_clarification.get("blocking")) if raw_clarification else waiting_user

    if not any((clarification_question, required_fields, reason, response_hint)) and not waiting_user:
        return None

    return {
        "protocol_version": CLARIFICATION_PROTOCOL_VERSION,
        "state": state,
        "question": clarification_question or None,
        "reason": reason or None,
        "required_fields": required_fields,
        "response_hint": response_hint or None,
        "blocking": blocking,
        "source": "result_payload" if raw_clarification else "status_fallback",
    }


def build_partial_result_payload(
    *,
    status: str,
    hydrated: dict[str, Any],
    summary: str,
    question: str | None = None,
) -> dict[str, Any] | None:
    progress = build_progress_payload(status=status, hydrated=hydrated, summary=summary)
    clarification = build_clarification_payload(status=status, hydrated=hydrated, question=question)
    partial = {
        "question": _stringify(question),
        "artifacts": hydrated.get("artifacts") or [],
        "progress": progress,
        "clarification": clarification,
    }
    if not partial["question"] and not partial["artifacts"] and clarification is None:
        return None
    if not partial["question"]:
        partial["question"] = None
    return partial
