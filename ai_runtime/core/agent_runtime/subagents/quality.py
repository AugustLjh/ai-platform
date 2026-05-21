from __future__ import annotations

import posixpath
from typing import Any


_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SUBAGENT_QUALITY_PROTOCOL_VERSION = "managed-subagent.quality-suite.v1"

DEFAULT_SUBAGENT_QUALITY_CASES: list[dict[str, Any]] = [
    {
        "name": "reviewer blocking finding recall",
        "kind": "reviewer",
        "source": "builtin",
        "actual": {
            "decision": "changes_requested",
            "approved": False,
            "blocking_finding_count": 1,
            "conclusion": "Blocking security issue remains.",
            "findings": [
                {
                    "title": "Missing authorization check",
                    "severity": "high",
                    "path": "src/api.py",
                    "line": 10,
                }
            ],
        },
        "expected": {
            "decision": "changes_requested",
            "approved": False,
            "min_blocking_findings": 1,
            "required_severities": ["high"],
            "findings": [
                {
                    "title": "Missing authorization check",
                    "path": "src/api.py",
                    "line": 10,
                }
            ],
            "requires_conclusion": True,
        },
    },
    {
        "name": "tester verification structure",
        "kind": "tester",
        "source": "builtin",
        "actual": {
            "payload": {
                "status": "failed",
                "command": ["python", "-m", "pytest"],
                "logs": {"stdout": "FAILED tests/test_app.py::test_app"},
                "structured_report": {
                    "summary": {"failed": 1},
                    "reports": [
                        {
                            "summary": {"failed": 1},
                            "failures": [{"title": "tests/test_app.py::test_app"}],
                        }
                    ],
                },
            }
        },
        "expected": {
            "status": "failed",
            "min_failed_tests": 1,
            "required_failure_titles": ["tests/test_app.py::test_app"],
            "require_command": True,
            "require_logs": True,
            "require_structured_report": True,
        },
    },
    {
        "name": "worker scoped patch with verification evidence",
        "kind": "worker",
        "source": "builtin",
        "actual": {
            "input": {
                "message": "Tighten the parallel worker write scope gate.",
                "write_scope": ["ai_runtime/core/agent_runtime/subagents"],
            },
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "payload": {
                        "operation": "modify",
                        "files": [
                            {
                                "path": "ai_runtime/core/agent_runtime/subagents/governance.py",
                                "operation": "modify",
                                "changed": True,
                            }
                        ],
                        "diff": "@@\n- old\n+ new\n",
                        "review_notes": [],
                        "merge_policy": "manual_review_required",
                    },
                },
                {
                    "artifact_type": "verification_report",
                    "payload": {
                        "status": "passed",
                        "command": [
                            "python",
                            "-m",
                            "pytest",
                            "ai_runtime/tests/test_agent_runtime_subagents.py",
                        ],
                        "logs": {"stdout": "1 passed"},
                    },
                },
            ],
        },
        "expected": {
            "require_write_scope": True,
            "require_patch_artifact": True,
            "require_verification_report": True,
            "enforce_write_scope": True,
            "required_paths": [
                "ai_runtime/core/agent_runtime/subagents/governance.py",
            ],
        },
    },
    {
        "name": "worker delete patch remains reviewable",
        "kind": "worker",
        "source": "builtin",
        "actual": {
            "input": {
                "message": "Delete stale patch UI helper.",
                "write_scope": ["frontend-vue/src/components/agent"],
            },
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "payload": {
                        "operation": "delete",
                        "files": [
                            {
                                "path": "frontend-vue/src/components/agent/LegacyPatchCard.vue",
                                "operation": "delete",
                                "changed": True,
                            }
                        ],
                        "diff": "@@\n-old\n",
                        "review_notes": ["Deletion requires review."],
                        "merge_policy": "manual_review_required",
                    },
                }
            ],
        },
        "expected": {
            "require_write_scope": True,
            "require_patch_artifact": True,
            "enforce_write_scope": True,
            "required_operations": ["delete"],
            "require_review_for_operations": ["delete"],
            "required_paths": [
                "frontend-vue/src/components/agent/LegacyPatchCard.vue",
            ],
        },
    },
    {
        "name": "worker rename patch requires explicit writeback confirmation",
        "kind": "worker",
        "source": "builtin",
        "actual": {
            "input": {
                "message": "Rename the patch card component and stage writeback guidance.",
                "write_scope": ["frontend-vue/src/components/agent"],
            },
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "payload": {
                        "operation": "rename",
                        "files": [
                            {
                                "path": "frontend-vue/src/components/agent/AgentPatchCard.vue",
                                "operation": "rename",
                                "changed": True,
                            }
                        ],
                        "diff": "@@\n-old name\n+new name\n",
                        "review_notes": ["Rename must be reviewed before writing back to source root."],
                        "merge_policy": "explicit_user_writeback",
                        "writeback": {
                            "mode": "confirmed",
                            "requires_confirmation": True,
                            "status": "planned",
                        },
                    },
                }
            ],
        },
        "expected": {
            "require_write_scope": True,
            "require_patch_artifact": True,
            "enforce_write_scope": True,
            "required_operations": ["rename"],
            "require_review_for_operations": ["rename"],
            "require_writeback": True,
            "require_writeback_confirmation": True,
            "required_writeback_modes": ["confirmed"],
            "required_merge_policies": ["explicit_user_writeback"],
            "required_paths": [
                "frontend-vue/src/components/agent/AgentPatchCard.vue",
            ],
        },
    },
    {
        "name": "worker overlap governance captures conflicting write scopes",
        "kind": "worker",
        "source": "builtin",
        "actual": {
            "input": {
                "message": "Coordinate with a sibling worker before touching the shared runtime package.",
                "write_scope": ["ai_runtime/core/agent_runtime/subagents"],
                "sibling_write_scopes": [
                    "ai_runtime/core/agent_runtime",
                    "frontend-vue/src/views",
                ],
            },
            "governance": {
                "findings": [
                    {
                        "code": "write_scope_conflict",
                        "severity": "high",
                        "path": "ai_runtime/core/agent_runtime/subagents",
                        "message": "Sibling worker owns an overlapping parent directory.",
                    }
                ]
            },
        },
        "expected": {
            "require_write_scope": True,
            "require_scope_conflict_detection": True,
            "required_governance_codes": ["write_scope_conflict"],
        },
    },
    {
        "name": "worker multi-stage writeback keeps reviewability across rename and delete",
        "kind": "worker",
        "source": "builtin",
        "actual": {
            "input": {
                "message": "Refactor the run tree panel and remove the stale detail card in one bounded worker pass.",
                "write_scope": [
                    "frontend-vue/src/components/agent",
                    "frontend-vue/src/utils/agentRunTree.js",
                ],
                "sibling_write_scopes": [
                    ["frontend-vue/src/views"],
                    ["ai_runtime/core/agent_runtime"],
                ],
            },
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "payload": {
                        "operation": "rename",
                        "files": [
                            {
                                "path": "frontend-vue/src/components/agent/AgentRunTreeNode.vue",
                                "operation": "rename",
                                "changed": True,
                            },
                            {
                                "path": "frontend-vue/src/utils/agentRunTree.js",
                                "operation": "modify",
                                "changed": True,
                            },
                            {
                                "path": "frontend-vue/src/components/agent/AgentSubagentReviewCard.vue",
                                "operation": "delete",
                                "changed": True,
                            },
                        ],
                        "diff": "@@\n-old tree card\n+new tree node summary\n",
                        "review_notes": [
                            "Rename and delete must be reviewed together before source writeback.",
                            "UI summary logic was updated to keep invocation governance readable.",
                        ],
                        "merge_policy": "explicit_user_writeback",
                        "writeback": {
                            "mode": "confirmed",
                            "requires_confirmation": True,
                            "status": "planned",
                        },
                    },
                },
                {
                    "artifact_type": "verification_report",
                    "payload": {
                        "status": "passed",
                        "command": [
                            "npm",
                            "run",
                            "test",
                            "--",
                            "frontend-vue/tests/agentRunTree.test.js",
                        ],
                        "logs": {"stdout": "agentRunTree.test.js passed"},
                    },
                },
            ],
            "governance": {
                "findings": [],
            },
        },
        "expected": {
            "require_write_scope": True,
            "require_patch_artifact": True,
            "require_verification_report": True,
            "enforce_write_scope": True,
            "disallow_overlapping_scopes": True,
            "required_operations": ["rename", "delete"],
            "require_review_for_operations": ["rename", "delete"],
            "require_writeback": True,
            "require_writeback_confirmation": True,
            "required_writeback_modes": ["confirmed"],
            "required_merge_policies": ["explicit_user_writeback"],
            "required_paths": [
                "frontend-vue/src/components/agent/AgentRunTreeNode.vue",
                "frontend-vue/src/utils/agentRunTree.js",
                "frontend-vue/src/components/agent/AgentSubagentReviewCard.vue",
            ],
        },
    },
    {
        "name": "multi worker partial failure keeps recovery strategy visible",
        "kind": "collaboration",
        "source": "builtin",
        "actual": {
            "invocations": [
                {
                    "target": "worker-runtime",
                    "status": "completed",
                    "write_scope": ["ai_runtime/core/agent_runtime/subagents"],
                    "artifacts": [{"artifact_type": "code_patch"}],
                },
                {
                    "target": "worker-frontend",
                    "status": "failed",
                    "write_scope": ["frontend-vue/src/components/agent"],
                    "failure_strategy": {
                        "strategy": "retry_or_fallback",
                        "retry_allowed": True,
                        "recovery": {
                            "actions": [
                                "Retry once with a narrower write_scope.",
                                "Fallback to parent implementation when retry is exhausted.",
                            ]
                        },
                    },
                },
            ],
        },
        "expected": {
            "min_invocations": 2,
            "min_completed": 1,
            "min_failed": 1,
            "require_partial_failure_strategy": True,
            "require_recovery_actions": True,
            "require_write_scope_per_worker": True,
        },
    },
    {
        "name": "child waiting_user propagates to parent run",
        "kind": "collaboration",
        "source": "builtin",
        "actual": {
            "parent": {
                "run_id": "parent-run",
                "status": "waiting_user",
                "waiting_user": True,
            },
            "invocations": [
                {
                    "target": "worker-runtime",
                    "status": "waiting_user",
                    "child_run_status": "waiting_user",
                    "waiting_user_propagated": True,
                }
            ],
        },
        "expected": {
            "min_invocations": 1,
            "require_waiting_user_propagation": True,
        },
    },
    {
        "name": "parent resume boundary hides stale child work",
        "kind": "collaboration",
        "source": "builtin",
        "actual": {
            "resume": {
                "latest_attempt": 2,
                "stale_invocation_count": 0,
                "stale_event_count": 0,
                "stale_artifact_count": 0,
            },
            "invocations": [
                {
                    "target": "tester",
                    "status": "completed",
                    "attempt": 2,
                }
            ],
        },
        "expected": {
            "min_invocations": 1,
            "require_resume_boundary_cleanup": True,
        },
    },
]


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any, default: float = 0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _snake_or_camel(source: dict[str, Any], snake: str, camel: str | None = None, default: Any = None) -> Any:
    if snake in source:
        return source[snake]
    if camel and camel in source:
        return source[camel]
    return default


def _normalize_finding(raw: Any) -> dict[str, Any]:
    source = _dict(raw)
    return {
        "title": _stringify(source.get("title") or source.get("summary") or source.get("message")),
        "description": _stringify(source.get("description") or source.get("details") or source.get("reason")),
        "severity": _stringify(source.get("severity") or source.get("level") or "medium").lower(),
        "path": _stringify(source.get("path") or source.get("file") or source.get("filepath")),
        "line": source.get("line") or source.get("line_number") or source.get("lineNumber"),
    }


def _normalize_path(value: Any) -> str:
    text = _stringify(value).replace("\\", "/")
    if not text:
        return ""
    normalized = posixpath.normpath(text)
    if normalized in {".", "/"}:
        return ""
    return normalized.lstrip("/")


def _path_in_scope(path: str, scope: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_scope = _normalize_path(scope)
    if not normalized_path or not normalized_scope:
        return False
    return normalized_path == normalized_scope or normalized_path.startswith(f"{normalized_scope}/")


def _normalize_write_scope(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = _normalize_path(value)
        return [normalized] if normalized else []
    normalized_items: list[str] = []
    for item in _list(value):
        normalized = _normalize_path(item)
        if normalized and normalized not in normalized_items:
            normalized_items.append(normalized)
    return normalized_items


def _normalize_scope_groups(value: Any) -> list[list[str]]:
    if isinstance(value, str):
        normalized = _normalize_path(value)
        return [[normalized]] if normalized else []
    groups: list[list[str]] = []
    for item in _list(value):
        if isinstance(item, str):
            normalized = _normalize_path(item)
            if normalized:
                groups.append([normalized])
            continue
        normalized_group = _normalize_write_scope(item)
        if normalized_group:
            groups.append(normalized_group)
    return groups


def _scopes_overlap(left: str, right: str) -> bool:
    normalized_left = _normalize_path(left)
    normalized_right = _normalize_path(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left.startswith(f"{normalized_right}/")
        or normalized_right.startswith(f"{normalized_left}/")
    )


def _collect_scope_overlaps(write_scope: list[str], sibling_scope_groups: list[list[str]]) -> list[dict[str, str]]:
    overlaps: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for scope in write_scope:
        for group in sibling_scope_groups:
            for sibling_scope in group:
                if not _scopes_overlap(scope, sibling_scope):
                    continue
                key = (scope, sibling_scope)
                if key in seen:
                    continue
                seen.add(key)
                overlaps.append({
                    "scope": scope,
                    "sibling_scope": sibling_scope,
                })
    return overlaps


def _normalize_governance_codes(value: Any) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        source = _dict(item)
        code = _stringify(
            source.get("code")
            or source.get("type")
            or source.get("rule")
            or source.get("title")
            or source.get("message")
            or item
        ).lower()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _normalize_writeback(raw: Any) -> dict[str, Any]:
    source = _dict(raw)
    if not source:
        return {}
    return {
        "mode": _stringify(source.get("mode") or source.get("stage") or source.get("state")).lower(),
        "status": _stringify(source.get("status")).lower(),
        "supported": bool(source.get("supported", True)),
        "requires_confirmation": bool(
            source.get("requires_confirmation")
            or source.get("requiresConfirmation")
            or source.get("confirmation_required")
        ),
        "target_root": _stringify(source.get("target_root") or source.get("targetRoot")),
        "risk_level": _stringify(source.get("risk_level") or source.get("riskLevel")).lower(),
    }


def _normalize_patch_artifact(raw: Any) -> dict[str, Any]:
    artifact = _dict(raw)
    payload = _dict(artifact.get("payload") if "payload" in artifact else artifact)
    files: list[dict[str, Any]] = []
    for entry in _list(payload.get("files")):
        source = _dict(entry)
        path = _normalize_path(source.get("path") or source.get("target_path") or source.get("targetPath"))
        operation = _stringify(source.get("operation") or payload.get("operation") or "modify").lower()
        if path or operation:
            files.append({
                "path": path,
                "operation": operation or "modify",
                "changed": bool(source.get("changed", True)),
            })
    review_notes = payload.get("review_notes") if isinstance(payload.get("review_notes"), list) else payload.get("reviewNotes")
    return {
        "artifact_type": _stringify(artifact.get("artifact_type") or artifact.get("artifactType")),
        "operation": _stringify(payload.get("operation") or artifact.get("operation") or "modify").lower(),
        "files": files,
        "review_notes": [str(item).strip() for item in (review_notes or []) if str(item).strip()],
        "merge_policy": _stringify(payload.get("merge_policy") or payload.get("mergePolicy") or artifact.get("merge_policy") or artifact.get("mergePolicy")),
        "writeback": _normalize_writeback(
            payload.get("writeback")
            or artifact.get("writeback")
            or _dict(artifact.get("metadata")).get("writeback")
        ),
    }


def _finding_key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _stringify(finding.get("title")).lower(),
        _stringify(finding.get("path")).lower(),
        _stringify(finding.get("line")),
    )


def _check(name: str, passed: bool, weight: float, summary: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "weight": weight,
        "summary": summary,
        "details": details or {},
    }


def _score_checks(checks: list[dict[str, Any]]) -> float:
    total = sum(_number(item.get("weight")) for item in checks)
    if total <= 0:
        return 1.0
    passed = sum(_number(item.get("weight")) for item in checks if item.get("passed"))
    return round(passed / total, 4)


def _status_for_score(score: float) -> str:
    if score >= 0.999:
        return "passed"
    if score >= 0.75:
        return "warning"
    return "failed"


def _extract_failed_test_count(report: dict[str, Any]) -> int:
    summary = _dict(report.get("summary"))
    failed = int(_number(summary.get("failed") or summary.get("failures") or summary.get("errors"), 0))
    for item in _list(report.get("reports")):
        nested = _dict(item).get("summary")
        if isinstance(nested, dict):
            failed += int(_number(nested.get("failed") or nested.get("failures") or nested.get("errors"), 0))
    return failed


def _extract_failure_titles(report: dict[str, Any]) -> set[str]:
    titles: set[str] = set()
    for item in _list(report.get("failures")):
        title = _stringify(_dict(item).get("title") or _dict(item).get("name")).lower()
        if title:
            titles.add(title)
    for nested in _list(report.get("reports")):
        for item in _list(_dict(nested).get("failures")):
            title = _stringify(_dict(item).get("title") or _dict(item).get("name")).lower()
            if title:
                titles.add(title)
    return titles


def evaluate_reviewer_quality_case(case: dict[str, Any]) -> dict[str, Any]:
    """Score one reviewer or judge result against deterministic expectations."""

    actual = _dict(case.get("actual") or case.get("review_result") or case.get("reviewResult"))
    expected = _dict(case.get("expected"))
    findings = [_normalize_finding(item) for item in _list(actual.get("findings"))]
    expected_findings = [_normalize_finding(item) for item in _list(expected.get("findings"))]
    finding_keys = {_finding_key(item) for item in findings}
    expected_finding_keys = {_finding_key(item) for item in expected_findings if item.get("title") or item.get("path")}
    required_severities = {
        _stringify(item).lower()
        for item in _list(expected.get("required_severities") or expected.get("requiredSeverities"))
    }
    actual_severities = {_stringify(item.get("severity")).lower() for item in findings}

    checks: list[dict[str, Any]] = []
    if expected.get("decision"):
        checks.append(_check(
            "decision",
            _stringify(actual.get("decision")) == _stringify(expected.get("decision")),
            2.0,
            "review decision matches expectation",
            {"expected": expected.get("decision"), "actual": actual.get("decision")},
        ))
    if "approved" in expected:
        checks.append(_check(
            "approved",
            actual.get("approved") is expected.get("approved"),
            1.5,
            "approval state matches expectation",
            {"expected": expected.get("approved"), "actual": actual.get("approved")},
        ))
    if "min_blocking_findings" in expected or "minBlockingFindings" in expected:
        minimum = int(_number(_snake_or_camel(expected, "min_blocking_findings", "minBlockingFindings"), 0))
        actual_count = int(_number(_snake_or_camel(actual, "blocking_finding_count", "blockingFindingCount"), 0))
        checks.append(_check(
            "blocking_findings",
            actual_count >= minimum,
            1.5,
            "blocking finding count meets the expected floor",
            {"expected_min": minimum, "actual": actual_count},
        ))
    if required_severities:
        checks.append(_check(
            "severity_recall",
            required_severities.issubset(actual_severities),
            1.25,
            "required severities are present in reviewer findings",
            {"missing": sorted(required_severities - actual_severities)},
        ))
    if expected_finding_keys:
        missing = sorted(expected_finding_keys - finding_keys)
        checks.append(_check(
            "finding_recall",
            not missing,
            2.0,
            "expected finding titles and locations are present",
            {"missing": missing},
        ))
    if expected.get("requires_conclusion"):
        checks.append(_check(
            "conclusion",
            bool(_stringify(actual.get("conclusion") or actual.get("summary"))),
            1.0,
            "review result includes a readable conclusion",
        ))

    score = _score_checks(checks)
    return {
        "kind": "reviewer",
        "name": case.get("name") or "reviewer quality case",
        "status": _status_for_score(score),
        "score": score,
        "checks": checks,
        "finding_count": len(findings),
        "blocking_finding_count": int(_number(_snake_or_camel(actual, "blocking_finding_count", "blockingFindingCount"), 0)),
    }


def evaluate_tester_quality_case(case: dict[str, Any]) -> dict[str, Any]:
    """Score one tester verification report against deterministic expectations."""

    artifact = _dict(case.get("actual") or case.get("artifact"))
    payload = _dict(artifact.get("payload") if "payload" in artifact else artifact)
    expected = _dict(case.get("expected"))
    structured_report = _dict(
        payload.get("structured_report")
        or payload.get("structuredReport")
        or artifact.get("structured_report")
        or artifact.get("structuredReport")
    )
    logs = _dict(payload.get("logs"))
    stdout = _stringify(logs.get("stdout") or payload.get("stdout"))
    stderr = _stringify(logs.get("stderr") or payload.get("stderr"))

    checks: list[dict[str, Any]] = []
    if expected.get("status"):
        checks.append(_check(
            "status",
            _stringify(payload.get("status")) == _stringify(expected.get("status")),
            1.5,
            "verification status matches expectation",
            {"expected": expected.get("status"), "actual": payload.get("status")},
        ))
    if "min_failed_tests" in expected or "minFailedTests" in expected:
        minimum = int(_number(_snake_or_camel(expected, "min_failed_tests", "minFailedTests"), 0))
        actual_count = _extract_failed_test_count(structured_report)
        checks.append(_check(
            "failed_test_count",
            actual_count >= minimum,
            1.5,
            "structured report captures the expected failed test count",
            {"expected_min": minimum, "actual": actual_count},
        ))
    required_titles = {_stringify(item).lower() for item in _list(expected.get("required_failure_titles") or expected.get("requiredFailureTitles"))}
    if required_titles:
        actual_titles = _extract_failure_titles(structured_report)
        checks.append(_check(
            "failure_title_recall",
            required_titles.issubset(actual_titles),
            2.0,
            "required failure titles are present",
            {"missing": sorted(required_titles - actual_titles)},
        ))
    if expected.get("require_command"):
        checks.append(_check(
            "command",
            bool(_list(payload.get("command")) or _stringify(payload.get("command"))),
            1.0,
            "verification report records the command",
        ))
    if expected.get("require_logs"):
        checks.append(_check(
            "logs",
            bool(stdout or stderr),
            1.0,
            "verification report includes stdout or stderr",
        ))
    if expected.get("require_structured_report"):
        checks.append(_check(
            "structured_report",
            bool(structured_report),
            1.5,
            "verification report includes machine-readable details",
        ))

    score = _score_checks(checks)
    return {
        "kind": "tester",
        "name": case.get("name") or "tester quality case",
        "status": _status_for_score(score),
        "score": score,
        "checks": checks,
        "failed_test_count": _extract_failed_test_count(structured_report),
    }


def evaluate_worker_quality_case(case: dict[str, Any]) -> dict[str, Any]:
    """Score one implementation worker result against write_scope and reviewability expectations."""

    actual = _dict(case.get("actual") or case.get("delegation_result") or case.get("delegationResult"))
    expected = _dict(case.get("expected"))
    input_payload = _dict(actual.get("input") or actual.get("delegate_input") or actual.get("delegateInput"))
    write_scope = _normalize_write_scope(
        input_payload.get("write_scope")
        or input_payload.get("allowed_write_scope")
        or input_payload.get("write_paths")
        or actual.get("write_scope")
    )
    sibling_write_scopes = _normalize_scope_groups(
        input_payload.get("sibling_write_scopes")
        or input_payload.get("parallel_write_scopes")
        or actual.get("sibling_write_scopes")
        or actual.get("parallel_write_scopes")
    )
    governance = _dict(
        actual.get("governance")
        or actual.get("policy_evaluation")
        or actual.get("policyEvaluation")
        or actual.get("review")
    )
    artifacts = _list(actual.get("artifacts"))
    patch_artifacts = [
        _normalize_patch_artifact(item)
        for item in artifacts
        if _stringify(_dict(item).get("artifact_type") or _dict(item).get("artifactType")).lower() == "code_patch"
    ]
    verification_artifacts = [
        _dict(item)
        for item in artifacts
        if _stringify(_dict(item).get("artifact_type") or _dict(item).get("artifactType")).lower() == "verification_report"
    ]

    patch_files = [entry for artifact in patch_artifacts for entry in artifact.get("files", []) if entry.get("path")]
    changed_paths = sorted({entry["path"] for entry in patch_files})
    merge_policies = sorted(
        {
            _stringify(artifact.get("merge_policy")).lower()
            for artifact in patch_artifacts
            if _stringify(artifact.get("merge_policy"))
        }
    )
    operations = sorted(
        {
            _stringify(entry.get("operation") or artifact.get("operation") or "modify").lower()
            for artifact in patch_artifacts
            for entry in (artifact.get("files") or [{"operation": artifact.get("operation")}])
            if _stringify(entry.get("operation") or artifact.get("operation") or "modify")
        }
    )
    out_of_scope_paths = [
        path
        for path in changed_paths
        if write_scope and not any(_path_in_scope(path, scope) for scope in write_scope)
    ]
    overlapping_scope_pairs = _collect_scope_overlaps(write_scope, sibling_write_scopes)
    governance_codes = _normalize_governance_codes(
        governance.get("findings")
        or governance.get("blocked_reasons")
        or governance.get("blockedReasons")
        or governance.get("issues")
    )
    writeback = _normalize_writeback(actual.get("writeback"))
    if not writeback:
        for artifact in patch_artifacts:
            candidate = _dict(artifact.get("writeback"))
            if candidate:
                writeback = candidate
                break

    checks: list[dict[str, Any]] = []
    if expected.get("require_write_scope"):
        checks.append(_check(
            "write_scope",
            bool(write_scope),
            1.5,
            "worker result records an explicit write_scope",
            {"write_scope": write_scope},
        ))
    if expected.get("require_patch_artifact"):
        checks.append(_check(
            "patch_artifact",
            bool(patch_artifacts),
            2.0,
            "worker result includes a code_patch artifact",
            {"patch_count": len(patch_artifacts)},
        ))
    if expected.get("require_verification_report"):
        checks.append(_check(
            "verification_report",
            bool(verification_artifacts),
            1.5,
            "worker result includes a verification_report artifact",
            {"verification_count": len(verification_artifacts)},
        ))
    if expected.get("enforce_write_scope") and write_scope:
        checks.append(_check(
            "write_scope_enforcement",
            not out_of_scope_paths,
            2.75,
            "all changed paths stay inside the delegated write_scope",
            {"out_of_scope_paths": out_of_scope_paths},
        ))
    if expected.get("disallow_overlapping_scopes"):
        checks.append(_check(
            "write_scope_overlap",
            not overlapping_scope_pairs,
            1.75,
            "delegated write_scope does not overlap with sibling worker scopes",
            {"overlaps": overlapping_scope_pairs},
        ))
    if expected.get("require_scope_conflict_detection"):
        checks.append(_check(
            "scope_conflict_detection",
            bool(overlapping_scope_pairs) and bool(governance_codes),
            1.75,
            "overlapping scopes are surfaced through governance findings",
            {
                "overlaps": overlapping_scope_pairs,
                "governance_codes": governance_codes,
            },
        ))

    required_paths = {
        _normalize_path(item)
        for item in _list(expected.get("required_paths") or expected.get("requiredPaths"))
        if _normalize_path(item)
    }
    if required_paths:
        actual_paths = set(changed_paths)
        checks.append(_check(
            "required_paths",
            required_paths.issubset(actual_paths),
            1.5,
            "required changed paths are present in patch artifacts",
            {"missing": sorted(required_paths - actual_paths)},
        ))

    required_operations = {
        _stringify(item).lower()
        for item in _list(expected.get("required_operations") or expected.get("requiredOperations"))
        if _stringify(item)
    }
    actual_operations = set(operations)
    if required_operations:
        checks.append(_check(
            "required_operations",
            required_operations.issubset(actual_operations),
            1.25,
            "required patch operations are present",
            {"missing": sorted(required_operations - actual_operations)},
        ))

    required_governance_codes = {
        _stringify(item).lower()
        for item in _list(expected.get("required_governance_codes") or expected.get("requiredGovernanceCodes"))
        if _stringify(item)
    }
    if required_governance_codes:
        actual_governance_codes = set(governance_codes)
        checks.append(_check(
            "governance_codes",
            required_governance_codes.issubset(actual_governance_codes),
            1.25,
            "required governance findings are present",
            {"missing": sorted(required_governance_codes - actual_governance_codes)},
        ))

    if expected.get("require_writeback"):
        checks.append(_check(
            "writeback",
            bool(writeback),
            1.25,
            "worker result carries structured workspace writeback guidance",
            {"writeback": writeback},
        ))

    if expected.get("require_writeback_confirmation"):
        checks.append(_check(
            "writeback_confirmation",
            bool(writeback.get("requires_confirmation")),
            1.0,
            "writeback guidance keeps explicit confirmation as a separate gate",
            {"writeback": writeback},
        ))

    required_writeback_modes = {
        _stringify(item).lower()
        for item in _list(expected.get("required_writeback_modes") or expected.get("requiredWritebackModes"))
        if _stringify(item)
    }
    if required_writeback_modes:
        actual_mode = _stringify(writeback.get("mode")).lower()
        checks.append(_check(
            "writeback_mode",
            actual_mode in required_writeback_modes,
            1.0,
            "writeback mode matches expectation",
            {"expected": sorted(required_writeback_modes), "actual": actual_mode},
        ))

    required_merge_policies = {
        _stringify(item).lower()
        for item in _list(expected.get("required_merge_policies") or expected.get("requiredMergePolicies"))
        if _stringify(item)
    }
    if required_merge_policies:
        checks.append(_check(
            "merge_policy",
            required_merge_policies.issubset(set(merge_policies)),
            1.0,
            "patch artifacts advertise the required merge policy",
            {"missing": sorted(required_merge_policies - set(merge_policies)), "actual": merge_policies},
        ))

    review_required_operations = {
        _stringify(item).lower()
        for item in _list(expected.get("require_review_for_operations") or expected.get("requireReviewForOperations"))
        if _stringify(item)
    }
    if review_required_operations:
        reviewable = True
        failing_operations: list[str] = []
        for artifact in patch_artifacts:
            artifact_operations = {
                _stringify(entry.get("operation") or artifact.get("operation") or "modify").lower()
                for entry in (artifact.get("files") or [{"operation": artifact.get("operation")}])
                if _stringify(entry.get("operation") or artifact.get("operation") or "modify")
            }
            if not artifact_operations.intersection(review_required_operations):
                continue
            if not artifact.get("review_notes") or artifact.get("merge_policy") not in {"manual_review_required", "explicit_user_writeback"}:
                reviewable = False
                failing_operations.extend(sorted(artifact_operations.intersection(review_required_operations)))
        checks.append(_check(
            "reviewable_high_risk_operations",
            reviewable,
            1.5,
            "delete or rename style worker patches remain explicitly reviewable",
            {"failing_operations": sorted(set(failing_operations))},
        ))

    score = _score_checks(checks)
    return {
        "kind": "worker",
        "name": case.get("name") or "worker quality case",
        "status": _status_for_score(score),
        "score": score,
        "checks": checks,
        "write_scope": write_scope,
        "changed_path_count": len(changed_paths),
        "changed_paths": changed_paths,
        "operations": operations,
        "patch_count": len(patch_artifacts),
        "verification_count": len(verification_artifacts),
        "out_of_scope_paths": out_of_scope_paths,
        "sibling_write_scopes": sibling_write_scopes,
        "overlapping_scope_pairs": overlapping_scope_pairs,
        "governance_codes": governance_codes,
        "merge_policies": merge_policies,
        "writeback": writeback,
    }


def _normalize_invocations(value: Any) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for item in _list(value):
        source = _dict(item)
        if not source:
            continue
        failure_strategy = _dict(source.get("failure_strategy") or source.get("failureStrategy"))
        recovery = _dict(failure_strategy.get("recovery") or source.get("recovery"))
        invocations.append(
            {
                "target": _stringify(source.get("target") or source.get("delegate_target") or source.get("delegateTarget")),
                "status": _stringify(source.get("status") or source.get("child_run_status") or source.get("childRunStatus")).lower(),
                "child_run_status": _stringify(source.get("child_run_status") or source.get("childRunStatus")).lower(),
                "attempt": int(_number(source.get("attempt") or source.get("attempt_number") or source.get("attemptNumber"), 0)),
                "write_scope": _normalize_write_scope(source.get("write_scope") or source.get("writeScope")),
                "failure_strategy": failure_strategy,
                "recovery_actions": [
                    _stringify(action)
                    for action in _list(recovery.get("actions") or recovery.get("recovery_actions") or recovery.get("recoveryActions"))
                    if _stringify(action)
                ],
                "waiting_user_propagated": bool(
                    source.get("waiting_user_propagated")
                    or source.get("waitingUserPropagated")
                    or source.get("propagated_to_parent")
                    or source.get("propagatedToParent")
                ),
            }
        )
    return invocations


def evaluate_collaboration_quality_case(case: dict[str, Any]) -> dict[str, Any]:
    """Score multi-subagent collaboration contracts such as partial failure, waiting_user, and resume cleanup."""

    actual = _dict(case.get("actual") or case.get("collaboration"))
    expected = _dict(case.get("expected"))
    invocations = _normalize_invocations(actual.get("invocations") or actual.get("subagent_invocations") or actual.get("subagentInvocations"))
    parent = _dict(actual.get("parent") or actual.get("parent_run") or actual.get("parentRun"))
    resume = _dict(actual.get("resume") or actual.get("resume_boundary") or actual.get("resumeBoundary"))

    completed_count = sum(1 for item in invocations if item["status"] in {"completed", "succeeded", "success"})
    failed_count = sum(1 for item in invocations if item["status"] in {"failed", "error", "cancelled"})
    waiting_count = sum(1 for item in invocations if item["status"] == "waiting_user" or item["child_run_status"] == "waiting_user")
    missing_write_scope_targets = [
        item["target"] or f"invocation-{index + 1}"
        for index, item in enumerate(invocations)
        if not item["write_scope"] and item["status"] in {"completed", "failed", "running", "waiting_user"}
    ]
    failed_without_strategy = [
        item["target"] or f"invocation-{index + 1}"
        for index, item in enumerate(invocations)
        if item["status"] in {"failed", "error", "cancelled"} and not item["failure_strategy"]
    ]
    failed_without_recovery_actions = [
        item["target"] or f"invocation-{index + 1}"
        for index, item in enumerate(invocations)
        if item["status"] in {"failed", "error", "cancelled"} and not item["recovery_actions"]
    ]

    checks: list[dict[str, Any]] = []
    if "min_invocations" in expected or "minInvocations" in expected:
        minimum = int(_number(_snake_or_camel(expected, "min_invocations", "minInvocations"), 0))
        checks.append(_check(
            "invocation_count",
            len(invocations) >= minimum,
            1.0,
            "collaboration result contains the expected number of subagent invocations",
            {"expected_min": minimum, "actual": len(invocations)},
        ))
    if "min_completed" in expected or "minCompleted" in expected:
        minimum = int(_number(_snake_or_camel(expected, "min_completed", "minCompleted"), 0))
        checks.append(_check(
            "completed_invocations",
            completed_count >= minimum,
            1.0,
            "collaboration result preserves completed child work",
            {"expected_min": minimum, "actual": completed_count},
        ))
    if "min_failed" in expected or "minFailed" in expected:
        minimum = int(_number(_snake_or_camel(expected, "min_failed", "minFailed"), 0))
        checks.append(_check(
            "failed_invocations",
            failed_count >= minimum,
            1.0,
            "collaboration result preserves failed child status for recovery",
            {"expected_min": minimum, "actual": failed_count},
        ))
    if expected.get("require_partial_failure_strategy"):
        checks.append(_check(
            "partial_failure_strategy",
            failed_count > 0 and completed_count > 0 and not failed_without_strategy,
            2.0,
            "partial failure includes a structured failure strategy without hiding successful sibling work",
            {"failed_without_strategy": failed_without_strategy},
        ))
    if expected.get("require_recovery_actions"):
        checks.append(_check(
            "recovery_actions",
            failed_count == 0 or not failed_without_recovery_actions,
            1.5,
            "failed child work includes concrete recovery actions",
            {"failed_without_recovery_actions": failed_without_recovery_actions},
        ))
    if expected.get("require_write_scope_per_worker"):
        checks.append(_check(
            "worker_write_scopes",
            not missing_write_scope_targets,
            1.5,
            "worker-style invocations retain explicit write_scope ownership",
            {"missing_write_scope_targets": missing_write_scope_targets},
        ))
    if expected.get("require_waiting_user_propagation"):
        parent_waiting = _stringify(parent.get("status")).lower() == "waiting_user" or bool(parent.get("waiting_user") or parent.get("waitingUser"))
        propagated = any(item["waiting_user_propagated"] for item in invocations)
        checks.append(_check(
            "waiting_user_propagation",
            parent_waiting and waiting_count > 0 and propagated,
            2.0,
            "child waiting_user state is visible on the parent run",
            {
                "parent_waiting": parent_waiting,
                "waiting_invocation_count": waiting_count,
                "propagated": propagated,
            },
        ))
    if expected.get("require_resume_boundary_cleanup"):
        latest_attempt = int(_number(resume.get("latest_attempt") or resume.get("latestAttempt"), 0))
        stale_invocation_count = int(_number(resume.get("stale_invocation_count") or resume.get("staleInvocationCount"), 0))
        stale_event_count = int(_number(resume.get("stale_event_count") or resume.get("staleEventCount"), 0))
        stale_artifact_count = int(_number(resume.get("stale_artifact_count") or resume.get("staleArtifactCount"), 0))
        stale_attempts = [
            item["attempt"]
            for item in invocations
            if latest_attempt and item["attempt"] and item["attempt"] < latest_attempt
        ]
        checks.append(_check(
            "resume_boundary_cleanup",
            latest_attempt > 0
            and stale_invocation_count == 0
            and stale_event_count == 0
            and stale_artifact_count == 0
            and not stale_attempts,
            2.0,
            "resume boundary hides stale child invocations, events, and artifacts",
            {
                "latest_attempt": latest_attempt,
                "stale_invocation_count": stale_invocation_count,
                "stale_event_count": stale_event_count,
                "stale_artifact_count": stale_artifact_count,
                "stale_attempts": stale_attempts,
            },
        ))

    score = _score_checks(checks)
    return {
        "kind": "collaboration",
        "name": case.get("name") or "subagent collaboration quality case",
        "status": _status_for_score(score),
        "score": score,
        "checks": checks,
        "invocation_count": len(invocations),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "waiting_user_count": waiting_count,
    }


def evaluate_subagent_quality_suite(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        kind = _stringify(case.get("kind") or case.get("template")).lower()
        if kind in {"reviewer", "judge", "review"}:
            results.append(evaluate_reviewer_quality_case(case))
        elif kind in {"tester", "verification", "test"}:
            results.append(evaluate_tester_quality_case(case))
        elif kind in {"worker", "implementation", "patch"}:
            results.append(evaluate_worker_quality_case(case))
        elif kind in {"collaboration", "subagent_collaboration", "multi_worker", "resume"}:
            results.append(evaluate_collaboration_quality_case(case))
        else:
            results.append({
                "kind": kind or "unknown",
                "name": case.get("name") or "unknown quality case",
                "status": "failed",
                "score": 0.0,
                "checks": [_check("kind", False, 1.0, "unsupported subagent quality case kind")],
            })

    total = len(results)
    passed = sum(1 for item in results if item.get("status") == "passed")
    warning = sum(1 for item in results if item.get("status") == "warning")
    failed = sum(1 for item in results if item.get("status") == "failed")
    average_score = round(sum(_number(item.get("score")) for item in results) / total, 4) if total else 1.0
    return {
        "protocol_version": SUBAGENT_QUALITY_PROTOCOL_VERSION,
        "status": "passed" if failed == 0 and warning == 0 else ("warning" if failed == 0 else "failed"),
        "total": total,
        "passed": passed,
        "warning": warning,
        "failed": failed,
        "average_score": average_score,
        "results": results,
    }


def evaluate_default_subagent_quality_suite(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    suite = cases if cases else DEFAULT_SUBAGENT_QUALITY_CASES
    result = evaluate_subagent_quality_suite(suite)
    result["suite_name"] = "builtin"
    result["suite_source"] = "request" if cases else "builtin"
    return result
