from __future__ import annotations

from typing import Any

from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_SEVERITY_ALIASES = {
    "minor": "low",
    "warning": "medium",
    "moderate": "medium",
    "major": "high",
    "severe": "high",
    "blocker": "critical",
    "fatal": "critical",
}

_POSITIVE_DECISIONS = {
    "approve",
    "approved",
    "accept",
    "accepted",
    "pass",
    "passed",
    "success",
    "succeeded",
    "ship",
    "ship_it",
    "ship-it",
    "ok",
    "yes",
    "true",
    "allow",
    "allowed",
    "safe",
}

_NEGATIVE_DECISIONS = {
    "reject",
    "rejected",
    "fail",
    "failed",
    "changes_requested",
    "changes-requested",
    "request_changes",
    "request-changes",
    "needs_changes",
    "needs-changes",
    "block",
    "blocked",
    "deny",
    "denied",
    "no",
    "false",
    "unsafe",
}

_NEEDS_INPUT_DECISIONS = {
    "need_input",
    "needs_input",
    "need-input",
    "needs-input",
    "need_more_info",
    "needs_more_info",
    "need-more-info",
    "needs-more-info",
    "clarify",
    "clarification",
    "waiting_user",
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_severity(value: Any) -> str:
    text = _stringify(value).lower().replace(" ", "_")
    if not text:
        return ""
    return _SEVERITY_ALIASES.get(text, text)


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [segment.strip() for segment in value.split(",")]
    elif isinstance(value, list):
        items = [_stringify(item) for item in value]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_decision(value: Any) -> str | None:
    if isinstance(value, bool):
        return "approved" if value else "rejected"

    text = _stringify(value).lower().replace(" ", "_")
    if not text:
        return None
    if text in _POSITIVE_DECISIONS:
        return "approved"
    if text in _NEGATIVE_DECISIONS:
        return "rejected"
    if text in _NEEDS_INPUT_DECISIONS:
        return "needs_input"
    return None


def _extract_explicit_decision(final_output_json: Any) -> str | None:
    if not isinstance(final_output_json, dict):
        return None

    for key in (
        "review_decision",
        "review_verdict",
        "judge_decision",
        "judge_verdict",
        "decision",
        "verdict",
        "outcome",
        "approval",
        "approved",
        "pass",
        "passed",
        "accepted",
    ):
        if key not in final_output_json:
            continue
        normalized = _normalize_decision(final_output_json.get(key))
        if normalized:
            return normalized
    return None


def _extract_test_gaps(final_output_json: Any) -> list[str]:
    if not isinstance(final_output_json, dict):
        return []

    for key in ("test_gaps", "missing_verification", "verification_gaps"):
        value = final_output_json.get(key)
        if isinstance(value, list):
            return [item for item in (_stringify(entry) for entry in value) if item]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _extract_conclusion(final_output_json: Any, fallback_text: str) -> str:
    if isinstance(final_output_json, dict):
        for key in ("answer", "summary", "conclusion", "review_summary", "judge_summary"):
            text = _stringify(final_output_json.get(key))
            if text:
                return text
    return fallback_text


def _normalize_finding(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None

    title = _stringify(entry.get("title") or entry.get("summary") or entry.get("name"))
    description = _stringify(entry.get("description") or entry.get("details") or entry.get("reason"))
    severity = _normalize_severity(entry.get("severity") or entry.get("level") or entry.get("priority"))
    path = _stringify(entry.get("path") or entry.get("file") or entry.get("filepath"))
    code = _stringify(entry.get("code"))

    line_value = entry.get("line") if entry.get("line") is not None else entry.get("line_number")
    try:
        line = int(line_value) if line_value not in (None, "") else None
    except (TypeError, ValueError):
        line = None

    if not any((title, description, severity, path, code, line is not None)):
        return None

    return {
        "title": title or description or "Untitled finding",
        "description": description or title or "",
        "severity": severity or "medium",
        "path": path or None,
        "line": line,
        "code": code or None,
    }


def _extract_findings_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            finding
            for finding in (_normalize_finding(item) for item in payload)
            if finding is not None
        ]
    if isinstance(payload, dict):
        for key in ("review_findings", "findings", "items", "entries", "rows"):
            if key in payload:
                return _extract_findings_from_payload(payload.get(key))
    return []


def _extract_review_findings(final_output_json: Any, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(final_output_json, dict):
        findings.extend(
            _extract_findings_from_payload(
                final_output_json.get("review_findings")
                or final_output_json.get("findings")
                or []
            )
        )

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if _stringify(artifact.get("artifact_type") or artifact.get("artifactType")) != "review_findings":
            continue
        findings.extend(_extract_findings_from_payload(artifact.get("payload")))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, int | None]] = set()
    for finding in findings:
        key = (
            finding.get("title") or "",
            finding.get("description") or "",
            finding.get("severity") or "",
            finding.get("path") or "",
            finding.get("line"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def build_review_result(
    *,
    target: SubagentTarget,
    status: str,
    hydrated: dict[str, Any],
    error_message: str | None = None,
    child_run_id: str | None = None,
) -> dict[str, Any]:
    policy = target.normalized_review_policy()
    role = policy.get("mode") or "none"
    required = bool(policy.get("required"))
    fallback_text = _stringify(hydrated.get("final_output_text") or hydrated.get("final_output"))
    final_output_json = hydrated.get("final_output_json")
    artifacts = hydrated.get("artifacts") if isinstance(hydrated.get("artifacts"), list) else []
    findings = _extract_review_findings(final_output_json, artifacts)
    finding_count = len(findings)
    blocking_severities = {
        _normalize_severity(item)
        for item in _normalize_string_list(policy.get("blocking_severities"))
    }
    blocking_finding_count = sum(
        1 for finding in findings if _normalize_severity(finding.get("severity")) in blocking_severities
    )
    explicit_decision = _extract_explicit_decision(final_output_json)
    conclusion = _extract_conclusion(final_output_json, fallback_text)
    test_gaps = _extract_test_gaps(final_output_json)

    if role == "none" and not required:
        decision = "not_required"
        approved = None
    elif status == "waiting_user":
        decision = "needs_input"
        approved = None
    elif status == "failed":
        decision = "failed"
        approved = False
    elif status == "cancelled":
        decision = "cancelled"
        approved = False
    elif explicit_decision == "needs_input":
        decision = "needs_input"
        approved = None
    elif explicit_decision == "rejected":
        decision = "rejected" if role == "judge" else "changes_requested"
        approved = False
    elif blocking_finding_count > 0:
        decision = "rejected" if role == "judge" else "changes_requested"
        approved = False
    elif explicit_decision == "approved":
        decision = "approved_with_findings" if finding_count > 0 else "approved"
        approved = True
    elif finding_count > 0:
        decision = "approved_with_findings"
        approved = True
    elif conclusion:
        decision = "approved"
        approved = True
    else:
        decision = "inconclusive"
        approved = None

    summary_parts: list[str] = []
    if role == "judge":
        summary_parts.append("Judge")
    elif role == "reviewer":
        summary_parts.append("Reviewer")
    else:
        summary_parts.append("委派结果")

    decision_labels = {
        "not_required": "未要求评审",
        "approved": "通过",
        "approved_with_findings": "通过但有提示",
        "changes_requested": "要求修改",
        "rejected": "拒绝",
        "needs_input": "等待补充",
        "failed": "执行失败",
        "cancelled": "已取消",
        "inconclusive": "结论不足",
    }
    summary_parts.append(decision_labels.get(decision, decision))
    if finding_count > 0:
        summary_parts.append(f"{finding_count} 条 finding")
    if blocking_finding_count > 0:
        summary_parts.append(f"{blocking_finding_count} 条阻塞")

    return {
        "protocol_version": "managed-subagent.review-result.v1",
        "required": required,
        "mode": role,
        "approved": approved,
        "decision": decision,
        "child_status": status,
        "child_run_id": child_run_id,
        "summary": " · ".join(summary_parts),
        "conclusion": conclusion or None,
        "finding_count": finding_count,
        "blocking_finding_count": blocking_finding_count,
        "blocking_severities": sorted(blocking_severities, key=lambda item: _SEVERITY_ORDER.get(item, 99)),
        "findings": findings,
        "test_gaps": test_gaps,
        "explicit_decision": explicit_decision,
        "error": _stringify(error_message) or None,
    }
