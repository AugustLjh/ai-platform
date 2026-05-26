"""Admin audit view with field-level permission boundaries and redaction rule evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence


class ViewerRole(str, Enum):
    ANONYMOUS = "anonymous"
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


class FieldVisibility(str, Enum):
    PUBLIC = "public"
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"
    REDACTED = "redacted"


ROLE_HIERARCHY: dict[ViewerRole, int] = {
    ViewerRole.ANONYMOUS: 0,
    ViewerRole.USER: 1,
    ViewerRole.OPERATOR: 2,
    ViewerRole.ADMIN: 3,
    ViewerRole.SYSTEM: 4,
}

VISIBILITY_REQUIRED_ROLE: dict[FieldVisibility, ViewerRole] = {
    FieldVisibility.PUBLIC: ViewerRole.ANONYMOUS,
    FieldVisibility.USER: ViewerRole.USER,
    FieldVisibility.OPERATOR: ViewerRole.OPERATOR,
    FieldVisibility.ADMIN: ViewerRole.ADMIN,
    FieldVisibility.SYSTEM: ViewerRole.SYSTEM,
    FieldVisibility.REDACTED: ViewerRole.SYSTEM,
}

SENSITIVE_KEY_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(password|passwd|pwd)"),
    re.compile(r"(?i)(secret|token|api[_-]?key)"),
    re.compile(r"(?i)(authorization|credential|private[_-]?key)"),
    re.compile(r"(?i)(session[_-]?id|cookie|csrf)"),
    re.compile(r"(?i)(connection[_-]?string|dsn|database[_-]?url)"),
)

SENSITIVE_VALUE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)^(bearer|basic|token)\s+\S+"),
    re.compile(r"(?i)^(sk|pk|ak|rk)[_-][a-zA-Z0-9]{16,}"),
    re.compile(r"(?i)^(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}"),
    re.compile(r"(?i)^(xox[bpas])-[a-zA-Z0-9\-]+"),
    re.compile(r"(?i)^AKIA[A-Z0-9]{16}"),
    re.compile(r"(?i)^eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+"),
)


@dataclass(frozen=True)
class FieldPolicy:
    path: str
    visibility: FieldVisibility
    redact_value: str = "[REDACTED]"
    description: str = ""


@dataclass(frozen=True)
class AuditViewPolicy:
    field_policies: tuple[FieldPolicy, ...] = ()
    default_visibility: FieldVisibility = FieldVisibility.USER
    redact_sensitive_keys: bool = True
    redact_sensitive_values: bool = True
    max_field_depth: int = 10
    max_array_items_visible: int = 50


DEFAULT_FIELD_POLICIES: tuple[FieldPolicy, ...] = (
    FieldPolicy(path="context.workspace.source.path", visibility=FieldVisibility.OPERATOR, description="Workspace source path reveals server filesystem layout"),
    FieldPolicy(path="context.workspace.root", visibility=FieldVisibility.OPERATOR, description="Workspace root reveals server filesystem layout"),
    FieldPolicy(path="context.workspace_root", visibility=FieldVisibility.OPERATOR, description="Workspace root reveals server filesystem layout"),
    FieldPolicy(path="metadata.delegation.parent_context", visibility=FieldVisibility.ADMIN, description="Parent delegation context may contain sensitive task details"),
    FieldPolicy(path="metadata.delegation.policy_snapshot", visibility=FieldVisibility.ADMIN, description="Policy snapshot contains internal governance configuration"),
    FieldPolicy(path="input.message", visibility=FieldVisibility.USER, description="User input message"),
    FieldPolicy(path="final_output", visibility=FieldVisibility.USER, description="Agent final output"),
    FieldPolicy(path="final_output_text", visibility=FieldVisibility.USER, description="Agent final output text"),
    FieldPolicy(path="final_output_json", visibility=FieldVisibility.USER, description="Agent final output JSON"),
    FieldPolicy(path="error_message", visibility=FieldVisibility.OPERATOR, description="Error messages may contain internal details"),
    FieldPolicy(path="tool_calls.*.arguments", visibility=FieldVisibility.OPERATOR, description="Tool call arguments may contain sensitive parameters"),
    FieldPolicy(path="tool_calls.*.result", visibility=FieldVisibility.OPERATOR, description="Tool call results may contain sensitive data"),
    FieldPolicy(path="events.*.payload", visibility=FieldVisibility.OPERATOR, description="Event payloads may contain internal state"),
    FieldPolicy(path="artifacts.*.payload", visibility=FieldVisibility.USER, description="Artifact payloads are user-facing"),
    FieldPolicy(path="artifacts.*.metadata", visibility=FieldVisibility.OPERATOR, description="Artifact metadata may contain internal details"),
)

DEFAULT_AUDIT_VIEW_POLICY = AuditViewPolicy(
    field_policies=DEFAULT_FIELD_POLICIES,
    default_visibility=FieldVisibility.USER,
    redact_sensitive_keys=True,
    redact_sensitive_values=True,
)


def _key_is_sensitive(key: str) -> bool:
    return any(pattern.search(key) for pattern in SENSITIVE_KEY_PATTERNS)


def _value_is_sensitive(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 8:
        return False
    return any(pattern.match(value) for pattern in SENSITIVE_VALUE_PATTERNS)


def _path_matches(field_path: str, policy_path: str) -> bool:
    field_parts = field_path.split(".")
    policy_parts = policy_path.split(".")
    if len(field_parts) != len(policy_parts):
        return False
    for field_part, policy_part in zip(field_parts, policy_parts):
        if policy_part == "*":
            continue
        if field_part != policy_part:
            return False
    return True


def _resolve_field_visibility(
    field_path: str,
    key: str,
    value: Any,
    policy: AuditViewPolicy,
) -> FieldVisibility:
    for field_policy in policy.field_policies:
        if _path_matches(field_path, field_policy.path):
            return field_policy.visibility

    if policy.redact_sensitive_keys and _key_is_sensitive(key):
        return FieldVisibility.REDACTED

    if policy.redact_sensitive_values and _value_is_sensitive(value):
        return FieldVisibility.REDACTED

    return policy.default_visibility


def _role_can_see(viewer_role: ViewerRole, visibility: FieldVisibility) -> bool:
    required_role = VISIBILITY_REQUIRED_ROLE.get(visibility, ViewerRole.SYSTEM)
    return ROLE_HIERARCHY.get(viewer_role, 0) >= ROLE_HIERARCHY.get(required_role, 99)


@dataclass
class RedactionResult:
    original_field_count: int = 0
    redacted_field_count: int = 0
    visible_field_count: int = 0
    redacted_paths: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "original_field_count": self.original_field_count,
            "redacted_field_count": self.redacted_field_count,
            "visible_field_count": self.visible_field_count,
            "redaction_rate": round(self.redacted_field_count / max(1, self.original_field_count), 4),
            "redacted_paths": self.redacted_paths[:50],
        }


def apply_audit_view(
    data: Any,
    *,
    viewer_role: ViewerRole,
    policy: AuditViewPolicy = DEFAULT_AUDIT_VIEW_POLICY,
    path_prefix: str = "",
    result: RedactionResult | None = None,
    _depth: int = 0,
) -> Any:
    if result is None:
        result = RedactionResult()

    if _depth > policy.max_field_depth:
        return "[DEPTH_LIMIT]"

    if isinstance(data, dict):
        output = {}
        for key, value in data.items():
            field_path = f"{path_prefix}.{key}" if path_prefix else key
            result.original_field_count += 1
            visibility = _resolve_field_visibility(field_path, key, value, policy)
            if not _role_can_see(viewer_role, visibility):
                result.redacted_field_count += 1
                result.redacted_paths.append(field_path)
                if visibility == FieldVisibility.REDACTED:
                    output[key] = "[REDACTED]"
                else:
                    output[key] = f"[HIDDEN:{visibility.value}]"
                continue
            result.visible_field_count += 1
            output[key] = apply_audit_view(
                value,
                viewer_role=viewer_role,
                policy=policy,
                path_prefix=field_path,
                result=result,
                _depth=_depth + 1,
            )
        return output

    if isinstance(data, list):
        visible_items = data[:policy.max_array_items_visible]
        output_list = []
        for index, item in enumerate(visible_items):
            item_path = f"{path_prefix}.{index}" if path_prefix else str(index)
            output_list.append(
                apply_audit_view(
                    item,
                    viewer_role=viewer_role,
                    policy=policy,
                    path_prefix=item_path,
                    result=result,
                    _depth=_depth + 1,
                )
            )
        if len(data) > policy.max_array_items_visible:
            output_list.append(f"[...{len(data) - policy.max_array_items_visible} more items]")
        return output_list

    if isinstance(data, str) and policy.redact_sensitive_values and _value_is_sensitive(data):
        key = path_prefix.rsplit(".", 1)[-1] if path_prefix else ""
        visibility = FieldVisibility.REDACTED
        if not _role_can_see(viewer_role, visibility):
            result.redacted_field_count += 1
            result.redacted_paths.append(path_prefix)
            return "[REDACTED]"

    return data


def build_audit_view_for_run(
    run_data: dict[str, Any],
    *,
    viewer_role: ViewerRole,
    policy: AuditViewPolicy = DEFAULT_AUDIT_VIEW_POLICY,
) -> dict[str, Any]:
    result = RedactionResult()
    filtered = apply_audit_view(
        run_data,
        viewer_role=viewer_role,
        policy=policy,
        result=result,
    )
    filtered["_audit_metadata"] = {
        "viewer_role": viewer_role.value,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        **result.snapshot(),
    }
    return filtered


def build_audit_view_for_events(
    events: list[dict[str, Any]],
    *,
    viewer_role: ViewerRole,
    policy: AuditViewPolicy = DEFAULT_AUDIT_VIEW_POLICY,
) -> list[dict[str, Any]]:
    result = RedactionResult()
    filtered_events = []
    for event in events:
        filtered = apply_audit_view(
            event,
            viewer_role=viewer_role,
            policy=policy,
            path_prefix="events.*",
            result=result,
            _depth=1,
        )
        filtered_events.append(filtered)
    return filtered_events


def build_audit_view_for_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    viewer_role: ViewerRole,
    policy: AuditViewPolicy = DEFAULT_AUDIT_VIEW_POLICY,
) -> list[dict[str, Any]]:
    result = RedactionResult()
    filtered_calls = []
    for call in tool_calls:
        filtered = apply_audit_view(
            call,
            viewer_role=viewer_role,
            policy=policy,
            path_prefix="tool_calls.*",
            result=result,
            _depth=1,
        )
        filtered_calls.append(filtered)
    return filtered_calls


@dataclass(frozen=True)
class RedactionRuleEvaluation:
    rule_name: str
    input_value: str
    expected_redacted: bool
    actual_redacted: bool
    passed: bool
    pattern_matched: str | None = None


def evaluate_redaction_rules(
    test_cases: Sequence[dict[str, Any]],
    *,
    policy: AuditViewPolicy = DEFAULT_AUDIT_VIEW_POLICY,
) -> dict[str, Any]:
    evaluations: list[RedactionRuleEvaluation] = []
    for case in test_cases:
        key = str(case.get("key") or "value")
        value = case.get("value", "")
        expected_redacted = bool(case.get("expected_redacted", True))
        rule_name = str(case.get("rule_name") or f"test_{key}")

        key_sensitive = policy.redact_sensitive_keys and _key_is_sensitive(key)
        value_sensitive = policy.redact_sensitive_values and _value_is_sensitive(value)
        actual_redacted = key_sensitive or value_sensitive

        pattern_matched = None
        if key_sensitive:
            for pattern in SENSITIVE_KEY_PATTERNS:
                if pattern.search(key):
                    pattern_matched = pattern.pattern
                    break
        elif value_sensitive:
            for pattern in SENSITIVE_VALUE_PATTERNS:
                if pattern.match(str(value)):
                    pattern_matched = pattern.pattern
                    break

        evaluations.append(RedactionRuleEvaluation(
            rule_name=rule_name,
            input_value=f"{key}={str(value)[:50]}",
            expected_redacted=expected_redacted,
            actual_redacted=actual_redacted,
            passed=expected_redacted == actual_redacted,
            pattern_matched=pattern_matched,
        ))

    passed = sum(1 for e in evaluations if e.passed)
    failed = sum(1 for e in evaluations if not e.passed)
    false_positives = [e for e in evaluations if e.actual_redacted and not e.expected_redacted]
    false_negatives = [e for e in evaluations if not e.actual_redacted and e.expected_redacted]

    return {
        "status": "passed" if failed == 0 else "failed",
        "total": len(evaluations),
        "passed": passed,
        "failed": failed,
        "false_positive_count": len(false_positives),
        "false_negative_count": len(false_negatives),
        "evaluations": [
            {
                "rule_name": e.rule_name,
                "input_value": e.input_value,
                "expected_redacted": e.expected_redacted,
                "actual_redacted": e.actual_redacted,
                "passed": e.passed,
                "pattern_matched": e.pattern_matched,
            }
            for e in evaluations
        ],
        "false_positives": [
            {"rule_name": e.rule_name, "input_value": e.input_value, "pattern_matched": e.pattern_matched}
            for e in false_positives
        ],
        "false_negatives": [
            {"rule_name": e.rule_name, "input_value": e.input_value}
            for e in false_negatives
        ],
    }
