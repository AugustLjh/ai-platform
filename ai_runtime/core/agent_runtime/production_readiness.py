from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ai_runtime.core.agent_runtime.subagents.quality import evaluate_default_subagent_quality_suite
from ai_runtime.core.agent_runtime.web_quality import evaluate_default_web_search_quality_suite


PRODUCTION_READINESS_PROTOCOL_VERSION = "managed-runtime.production-readiness.v1"


EVIDENCE_CASE_REQUIREMENTS: dict[tuple[str, str], dict[str, Any]] = {
    ("sandbox", "escape_drill"): {
        "min_case_count": 4,
        "required_scenarios": ["path_escape", "network_disabled", "capabilities_dropped", "readonly_rootfs"],
    },
    ("sandbox", "resource_exhaustion_drill"): {
        "min_case_count": 4,
        "required_scenarios": ["cpu_limit", "memory_limit", "pid_limit", "timeout"],
    },
    ("sandbox", "concurrent_dev_server_drill"): {
        "min_case_count": 3,
        "required_scenarios": ["concurrent_startup", "log_collection", "process_cleanup"],
    },
    ("workspace", "large_repo_pressure_drill"): {
        "min_case_count": 4,
        "required_scenarios": ["indexing", "search", "bounded_output", "quota"],
    },
    ("workspace", "writeback_rehearsal"): {
        "min_case_count": 4,
        "required_scenarios": ["dry_run", "confirmed", "protected_path", "audit_artifact"],
    },
    ("web_browser_pdf", "long_session_drill"): {
        "min_case_count": 3,
        "required_scenarios": ["ttl_cleanup", "stale_session_cleanup", "browser_verify"],
    },
    ("web_browser_pdf", "download_safety_drill"): {
        "min_case_count": 4,
        "required_scenarios": ["mime_block", "size_block", "domain_policy", "artifact_redaction"],
    },
    ("observability", "readonly_account_drill"): {
        "min_case_count": 4,
        "required_scenarios": ["allowed_select", "blocked_write", "blocked_multi_statement", "statement_timeout"],
    },
    ("observability", "redaction_drill"): {
        "min_case_count": 3,
        "required_scenarios": ["logs", "db_output", "tool_call_payload"],
    },
    ("subagents", "multi_worker_replay"): {
        "min_case_count": 4,
        "required_scenarios": ["successful_sibling", "failed_child", "failure_strategy", "recovery_actions"],
    },
    ("subagents", "complex_write_scope_replay"): {
        "min_case_count": 4,
        "required_scenarios": ["overlap", "rename", "delete", "writeback_confirmation"],
    },
    ("subagents", "resume_waiting_user_replay"): {
        "min_case_count": 3,
        "required_scenarios": ["waiting_user_visible", "resume_boundary", "stale_child_hidden"],
    },
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "passed", "pass", "ready", "healthy"}


def _nested(source: Mapping[str, Any] | None, *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _evidence_case(evidence: Mapping[str, Any], subsystem: str, case_key: str) -> dict[str, Any]:
    subsystem_evidence = _dict(evidence.get(subsystem))
    case = _dict(subsystem_evidence.get(case_key))
    aliases = {
        "web_browser_pdf": ("web", "browser", "pdf"),
        "subagents": ("subagent", "subagent_quality"),
    }
    for alias in aliases.get(subsystem, ()):
        if case:
            break
        case = _dict(_dict(evidence.get(alias)).get(case_key))
    return case


def _case_passed(evidence: Mapping[str, Any], subsystem: str, case_key: str) -> bool:
    return bool(_case_quality(evidence, subsystem, case_key).get("passed"))


def _case_signal_passed(case: Mapping[str, Any]) -> bool:
    if not case:
        return False
    if "passed" in case:
        return _truthy(case.get("passed"))
    if "status" in case:
        return _string(case.get("status")).lower() in {"passed", "pass", "ready", "healthy", "completed"}
    if "score" in case:
        return _number(case.get("score")) >= 0.9
    return False


def _case_count(case: Mapping[str, Any]) -> int:
    explicit = case.get("case_count") or case.get("total")
    if explicit is not None:
        return int(_number(explicit))
    scenarios = _list(case.get("scenarios"))
    if scenarios:
        return len(scenarios)
    return int(_number(case.get("sample_size") or case.get("samples")))


def _scenario_key(item: Any) -> str:
    if isinstance(item, Mapping):
        value = item.get("key") or item.get("name") or item.get("scenario")
    else:
        value = item
    return _string(value).lower().replace(" ", "_").replace("-", "_")


def _scenario_passed(item: Any) -> bool:
    if not isinstance(item, Mapping):
        return True
    if "passed" in item:
        return _truthy(item.get("passed"))
    if "status" in item:
        return _string(item.get("status")).lower() in {"passed", "pass", "ready", "healthy", "completed"}
    return True


def _covered_scenarios(case: Mapping[str, Any]) -> set[str]:
    scenarios = _list(case.get("scenarios"))
    covered = {_scenario_key(item) for item in scenarios if _scenario_key(item) and _scenario_passed(item)}
    covered.update(_scenario_key(item) for item in _list(case.get("covered_scenarios")) if _scenario_key(item))
    return covered


def _case_quality(evidence: Mapping[str, Any], subsystem: str, case_key: str) -> dict[str, Any]:
    case = _evidence_case(evidence, subsystem, case_key)
    if not case:
        return {
            "provided": False,
            "passed": False,
            "score": 0.0,
            "issues": ["evidence case is missing"],
            "required_scenarios": [],
            "missing_scenarios": [],
        }

    requirements = EVIDENCE_CASE_REQUIREMENTS.get((subsystem, case_key), {})
    required_scenarios = [_scenario_key(item) for item in _list(requirements.get("required_scenarios")) if _scenario_key(item)]
    covered = _covered_scenarios(case)
    missing_scenarios = [item for item in required_scenarios if item not in covered]
    min_case_count = int(_number(requirements.get("min_case_count"), default=1))
    case_count = _case_count(case)
    report_uri = _string(case.get("report_uri") or case.get("artifact_uri"))
    generated_at = _string(case.get("generated_at"))
    recovery_actions = _list(case.get("recovery_actions") or case.get("recoveryActions"))
    issues: list[str] = []

    if not _case_signal_passed(case):
        issues.append("evidence status is not passed")
    if case_count < min_case_count:
        issues.append(f"case_count {case_count} is below required {min_case_count}")
    if required_scenarios and missing_scenarios:
        issues.append("missing required scenarios: " + ", ".join(missing_scenarios))
    if not report_uri:
        issues.append("report_uri or artifact_uri is required")
    if not generated_at:
        issues.append("generated_at is required")
    if not recovery_actions:
        issues.append("recovery_actions are required")

    requirement_count = 6
    passed_requirements = 0
    if _case_signal_passed(case):
        passed_requirements += 1
    if case_count >= min_case_count:
        passed_requirements += 1
    if not required_scenarios or not missing_scenarios:
        passed_requirements += 1
    if report_uri:
        passed_requirements += 1
    if generated_at:
        passed_requirements += 1
    if recovery_actions:
        passed_requirements += 1

    return {
        "provided": True,
        "passed": not issues,
        "score": round(passed_requirements / requirement_count, 4),
        "issues": issues,
        "case_count": case_count,
        "min_case_count": min_case_count,
        "required_scenarios": required_scenarios,
        "covered_scenarios": sorted(covered),
        "missing_scenarios": missing_scenarios,
        "report_uri": report_uri,
        "generated_at": generated_at,
        "recovery_action_count": len(recovery_actions),
    }


def _case_summary(evidence: Mapping[str, Any], subsystem: str, case_key: str) -> dict[str, Any]:
    case = _evidence_case(evidence, subsystem, case_key)
    if not case:
        return {"provided": False}
    quality = _case_quality(evidence, subsystem, case_key)
    return {
        "provided": True,
        "status": case.get("status"),
        "passed": case.get("passed"),
        "score": case.get("score"),
        "case_count": case.get("case_count") or case.get("cases") or case.get("total"),
        "sample_size": case.get("sample_size") or case.get("samples"),
        "generated_at": case.get("generated_at"),
        "report_uri": case.get("report_uri") or case.get("artifact_uri"),
        "summary": case.get("summary") or case.get("message"),
        "quality": quality,
    }


def _check(
    *,
    subsystem: str,
    key: str,
    passed: bool,
    severity: str,
    summary: str,
    recovery_actions: list[str],
    evidence: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    warning: bool = False,
) -> dict[str, Any]:
    status = "pass" if passed else "warn" if warning else "fail"
    return {
        "subsystem": subsystem,
        "key": key,
        "status": status,
        "passed": passed,
        "severity": severity,
        "summary": summary,
        "recovery_actions": recovery_actions if not passed else [],
        "evidence": evidence or {},
        "details": details or {},
    }


def _subsystem_result(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = sum(1 for item in checks if item["status"] == "fail")
    warning = sum(1 for item in checks if item["status"] == "warn")
    passed = sum(1 for item in checks if item["status"] == "pass")
    critical_failures = [
        item
        for item in checks
        if item["status"] == "fail" and item.get("severity") in {"critical", "high"}
    ]
    if critical_failures:
        status = "blocked"
    elif failed:
        status = "failed"
    elif warning:
        status = "warning"
    else:
        status = "ready"
    return {
        "name": name,
        "status": status,
        "ready": status == "ready",
        "passed": passed,
        "warning": warning,
        "failed": failed,
        "checks": checks,
        "blocking_checks": [
            {"key": item["key"], "severity": item["severity"], "summary": item["summary"]}
            for item in checks
            if item["status"] == "fail" and item.get("severity") in {"critical", "high"}
        ],
    }


def _evidence_quality_summary(all_checks: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_checks = [
        item
        for item in all_checks
        if isinstance(item.get("evidence"), dict)
        and item["evidence"].get("provided") is True
        and isinstance(item["evidence"].get("quality"), dict)
    ]
    required_evidence_checks = [
        item
        for item in all_checks
        if isinstance(item.get("evidence"), dict) and (
            item["evidence"].get("provided") is True
            or item.get("key") in {case_key for _subsystem, case_key in EVIDENCE_CASE_REQUIREMENTS}
        )
    ]
    failing_quality = []
    scores: list[float] = []
    for item in evidence_checks:
        quality = _dict(item["evidence"].get("quality"))
        scores.append(_number(quality.get("score")))
        if not quality.get("passed"):
            failing_quality.append({
                "subsystem": item.get("subsystem"),
                "key": item.get("key"),
                "issues": _list(quality.get("issues")),
                "missing_scenarios": _list(quality.get("missing_scenarios")),
            })
    return {
        "provided_case_count": len(evidence_checks),
        "required_case_count": len(required_evidence_checks),
        "quality_passed_count": len(evidence_checks) - len(failing_quality),
        "quality_failed_count": len(failing_quality),
        "average_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "failing_quality": failing_quality,
    }


def _sandbox_checks(status: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    sandbox = _dict(_nested(status, "providers", "sandbox"))
    isolation = _dict(sandbox.get("isolation"))
    isolation_ready = bool(isolation.get("production_ready")) and _string(isolation.get("status")) == "ready"
    return [
        _check(
            subsystem="sandbox",
            key="runner_isolation_profile",
            passed=isolation_ready,
            severity="critical",
            summary="Sandbox runner isolation profile is production-ready.",
            recovery_actions=isolation.get("recovery_actions")
            or ["Configure Docker runner isolation and rerun sandbox_isolation_check."],
            details={"isolation": isolation},
        ),
        _check(
            subsystem="sandbox",
            key="escape_drill",
            passed=_case_passed(evidence, "sandbox", "escape_drill"),
            severity="critical",
            summary="Container escape and forbidden capability drills have passed.",
            recovery_actions=["Run sandbox escape/preflight drills and attach the signed report as readiness evidence."],
            evidence=_case_summary(evidence, "sandbox", "escape_drill"),
        ),
        _check(
            subsystem="sandbox",
            key="resource_exhaustion_drill",
            passed=_case_passed(evidence, "sandbox", "resource_exhaustion_drill"),
            severity="high",
            summary="CPU, memory, PID and output exhaustion drills have passed.",
            recovery_actions=["Run resource exhaustion drills for timeout, memory, PID and output limits."],
            evidence=_case_summary(evidence, "sandbox", "resource_exhaustion_drill"),
        ),
        _check(
            subsystem="sandbox",
            key="concurrent_dev_server_drill",
            passed=_case_passed(evidence, "sandbox", "concurrent_dev_server_drill"),
            severity="medium",
            summary="Concurrent dev server startup, log collection and process cleanup have passed.",
            recovery_actions=["Replay concurrent run_dev_server/process_stop scenarios and store the report."],
            evidence=_case_summary(evidence, "sandbox", "concurrent_dev_server_drill"),
        ),
    ]


def _workspace_checks(status: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    workspace = _dict(_nested(status, "providers", "workspace"))
    inspection = _dict(workspace.get("inspection"))
    lifecycle = _dict(status.get("workspace_lifecycle"))
    lifecycle_health = _dict(_nested(lifecycle, "last_run", "inspection", "health"))
    workspace_enabled = bool(workspace.get("enabled"))
    no_active_risk = (
        int(_number(inspection.get("expired_count"))) == 0
        and int(_number(inspection.get("quota_exceeded_count"))) == 0
        and int(_number(_nested(inspection, "lock_summary", "stale_lock_count"))) == 0
    )
    lifecycle_has_signal = _string(lifecycle.get("last_completed_at")) or lifecycle_health
    return [
        _check(
            subsystem="workspace",
            key="manager_enabled",
            passed=workspace_enabled,
            severity="high",
            summary="Workspace manager is enabled for isolated run workspaces.",
            recovery_actions=["Enable AGENT_WORKSPACE_MANAGER_ENABLED and configure managed workspace roots."],
            details={"base_root": workspace.get("base_root"), "max_files": workspace.get("max_files"), "max_bytes": workspace.get("max_bytes")},
        ),
        _check(
            subsystem="workspace",
            key="lifecycle_health_signal",
            passed=bool(lifecycle_has_signal),
            severity="medium",
            summary="Workspace lifecycle inspection has produced health telemetry.",
            recovery_actions=["Run workspace lifecycle inspection or enable AGENT_WORKSPACE_LIFECYCLE_ENABLED."],
            details={"last_completed_at": lifecycle.get("last_completed_at"), "health": lifecycle_health},
            warning=workspace_enabled,
        ),
        _check(
            subsystem="workspace",
            key="current_workspace_risk",
            passed=no_active_risk,
            severity="medium",
            summary="No expired workspaces, quota breaches or stale cleanup locks are currently reported.",
            recovery_actions=["Run workspace cleanup/lock cleanup and review quota settings."],
            details={"inspection": inspection},
            warning=workspace_enabled,
        ),
        _check(
            subsystem="workspace",
            key="large_repo_pressure_drill",
            passed=_case_passed(evidence, "workspace", "large_repo_pressure_drill"),
            severity="high",
            summary="Large repository indexing, search and bounded output pressure tests have passed.",
            recovery_actions=["Replay a large repository workspace pressure test and attach the report."],
            evidence=_case_summary(evidence, "workspace", "large_repo_pressure_drill"),
        ),
        _check(
            subsystem="workspace",
            key="writeback_rehearsal",
            passed=_case_passed(evidence, "workspace", "writeback_rehearsal"),
            severity="high",
            summary="Dry-run and confirmed workspace writeback rehearsal has passed.",
            recovery_actions=["Run writeback dry-run plus confirmed rehearsal on a disposable repository."],
            evidence=_case_summary(evidence, "workspace", "writeback_rehearsal"),
        ),
    ]


def _web_checks(status: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    web = _dict(_nested(status, "providers", "web"))
    browser = _dict(_nested(status, "providers", "browser"))
    web_quality = _dict(_nested(web, "search_quality", "evaluation"))
    custom_web_cases = _list(_nested(evidence, "web_browser_pdf", "search_quality_cases")) or _list(_nested(evidence, "web", "search_quality_cases"))
    evaluated_web_quality = evaluate_default_web_search_quality_suite(custom_web_cases) if custom_web_cases else web_quality
    browser_sessions = _dict(web.get("browser_sessions"))
    browser_health = _dict(browser_sessions.get("health"))
    browser_ok = (
        not browser.get("enabled")
        or (browser.get("configured") and browser.get("runtime_available") and _string(browser_health.get("status") or "healthy") in {"healthy", "baseline", ""})
    )
    return [
        _check(
            subsystem="web_browser_pdf",
            key="network_policy_configured",
            passed=bool(web.get("enabled")) and bool(web.get("network_configured")),
            severity="high",
            summary="Web tools are enabled only with explicit network configuration.",
            recovery_actions=["Set AGENT_WEB_NETWORK_CONFIGURED after domain, scheme, size and timeout policy review."],
            details={"enabled": web.get("enabled"), "network_configured": web.get("network_configured"), "allowed_domains": web.get("allowed_domains")},
        ),
        _check(
            subsystem="web_browser_pdf",
            key="search_quality_suite",
            passed=_string(evaluated_web_quality.get("status")) == "passed",
            severity="medium",
            summary="Web search quality suite passes policy boundary checks.",
            recovery_actions=["Expand and rerun web search quality cases until rejected/accepted counts match expectations."],
            details={"quality": evaluated_web_quality},
            warning=True,
        ),
        _check(
            subsystem="web_browser_pdf",
            key="browser_runtime_health",
            passed=bool(browser_ok),
            severity="medium",
            summary="Browser runtime and active session telemetry are healthy when browser tools are enabled.",
            recovery_actions=["Install browser runtime dependencies, close stale sessions and rerun browser_verify."],
            details={"browser": browser, "browser_sessions": browser_sessions},
            warning=not browser.get("enabled"),
        ),
        _check(
            subsystem="web_browser_pdf",
            key="long_session_drill",
            passed=_case_passed(evidence, "web_browser_pdf", "long_session_drill"),
            severity="medium",
            summary="Long browser session leak and TTL cleanup drill has passed.",
            recovery_actions=["Run long browser session leak and TTL cleanup drills."],
            evidence=_case_summary(evidence, "web_browser_pdf", "long_session_drill"),
        ),
        _check(
            subsystem="web_browser_pdf",
            key="download_safety_drill",
            passed=_case_passed(evidence, "web_browser_pdf", "download_safety_drill"),
            severity="high",
            summary="Download MIME, size, domain and content-risk safety drill has passed.",
            recovery_actions=["Run download safety tests, including blocked MIME/type and oversize files."],
            evidence=_case_summary(evidence, "web_browser_pdf", "download_safety_drill"),
        ),
    ]


def _observability_checks(status: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    observability = _dict(_nested(status, "providers", "observability"))
    audit_report = _dict(observability.get("audit_report"))
    checks = _list(audit_report.get("checks") or observability.get("checks"))
    failing_checks = [item for item in checks if _dict(item).get("status") == "fail"]
    warning_checks = [item for item in checks if _dict(item).get("status") in {"warning", "not_configured"}]
    recommendations = _list(audit_report.get("recommendations") or observability.get("recommendations"))
    return [
        _check(
            subsystem="observability",
            key="tool_policy_audit",
            passed=bool(observability.get("enabled")) and not failing_checks,
            severity="high",
            summary="Observability read-only tool policy audit has no failing checks.",
            recovery_actions=recommendations
            or ["Review SQL, Redis, HTTP, logs and metrics observability policy."],
            details={"available_tools": observability.get("available_tools"), "failing_checks": failing_checks, "warning_checks": warning_checks},
            warning=bool(observability.get("enabled")) and bool(warning_checks),
        ),
        _check(
            subsystem="observability",
            key="readonly_account_drill",
            passed=_case_passed(evidence, "observability", "readonly_account_drill"),
            severity="critical",
            summary="Production database read-only account and permission boundary drill has passed.",
            recovery_actions=["Exercise a real read-only DB account against allowed and forbidden SQL examples."],
            evidence=_case_summary(evidence, "observability", "readonly_account_drill"),
        ),
        _check(
            subsystem="observability",
            key="redaction_drill",
            passed=_case_passed(evidence, "observability", "redaction_drill"),
            severity="high",
            summary="Logs, DB output and tool-call redaction drill has passed.",
            recovery_actions=["Run audit redaction evaluation with production-like secret samples."],
            evidence=_case_summary(evidence, "observability", "redaction_drill"),
        ),
    ]


def _subagent_checks(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    custom_cases = _list(_nested(evidence, "subagents", "quality_cases")) or _list(_nested(evidence, "subagent", "quality_cases"))
    quality = evaluate_default_subagent_quality_suite(custom_cases)
    return [
        _check(
            subsystem="subagents",
            key="quality_contract_suite",
            passed=_string(quality.get("status")) == "passed",
            severity="high",
            summary="Subagent deterministic quality contract suite passes.",
            recovery_actions=["Fix failing reviewer/tester/worker/collaboration quality cases before scale rollout."],
            details={"quality": quality},
        ),
        _check(
            subsystem="subagents",
            key="multi_worker_replay",
            passed=_case_passed(evidence, "subagents", "multi_worker_replay"),
            severity="high",
            summary="Real multi-worker partial failure and successful sibling replay has passed.",
            recovery_actions=["Replay multi-worker runs with one failed and one successful worker, then attach the report."],
            evidence=_case_summary(evidence, "subagents", "multi_worker_replay"),
        ),
        _check(
            subsystem="subagents",
            key="complex_write_scope_replay",
            passed=_case_passed(evidence, "subagents", "complex_write_scope_replay"),
            severity="high",
            summary="Complex write_scope overlap, rename, delete and writeback replay has passed.",
            recovery_actions=["Run complex write_scope replay covering overlap, rename, delete and writeback confirmation."],
            evidence=_case_summary(evidence, "subagents", "complex_write_scope_replay"),
        ),
        _check(
            subsystem="subagents",
            key="resume_waiting_user_replay",
            passed=_case_passed(evidence, "subagents", "resume_waiting_user_replay"),
            severity="medium",
            summary="Parent resume and child waiting_user propagation replay has passed.",
            recovery_actions=["Replay parent resume and child waiting_user flows and verify stale child data stays hidden."],
            evidence=_case_summary(evidence, "subagents", "resume_waiting_user_replay"),
        ),
    ]


def evaluate_production_readiness(
    status: Mapping[str, Any],
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate whether the runtime has enough evidence for controlled production trial."""

    evidence_payload = evidence if isinstance(evidence, Mapping) else {}
    subsystem_checks = {
        "sandbox": _sandbox_checks(status, evidence_payload),
        "workspace": _workspace_checks(status, evidence_payload),
        "web_browser_pdf": _web_checks(status, evidence_payload),
        "observability": _observability_checks(status, evidence_payload),
        "subagents": _subagent_checks(evidence_payload),
    }
    subsystems = {
        name: _subsystem_result(name, checks)
        for name, checks in subsystem_checks.items()
    }
    all_checks = [check for result in subsystems.values() for check in result["checks"]]
    evidence_quality = _evidence_quality_summary(all_checks)
    failed = sum(1 for item in all_checks if item["status"] == "fail")
    warning = sum(1 for item in all_checks if item["status"] == "warn")
    passed = sum(1 for item in all_checks if item["status"] == "pass")
    blockers = [
        {
            "subsystem": item["subsystem"],
            "key": item["key"],
            "severity": item["severity"],
            "summary": item["summary"],
            "recovery_actions": item["recovery_actions"],
        }
        for item in all_checks
        if item["status"] == "fail" and item.get("severity") in {"critical", "high"}
    ]
    if blockers:
        status_value = "failed"
        readiness = "blocked"
        summary = f"{len(blockers)} production readiness blocker(s) remain"
    elif failed:
        status_value = "failed"
        readiness = "needs_work"
        summary = f"{failed} non-critical readiness check(s) failed"
    elif warning:
        status_value = "warning"
        readiness = "trial_with_caution"
        summary = f"{warning} readiness warning(s) remain"
    else:
        status_value = "passed"
        readiness = "controlled_trial_ready"
        summary = "all production readiness checks passed"

    return {
        "protocol_version": PRODUCTION_READINESS_PROTOCOL_VERSION,
        "suite_name": "runtime.production_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status_value,
        "readiness": readiness,
        "summary": summary,
        "total": len(all_checks),
        "passed": passed,
        "warning": warning,
        "failed": failed,
        "average_score": round(passed / len(all_checks), 4) if all_checks else 1.0,
        "subsystems": subsystems,
        "blocking_checks": blockers,
        "evidence_summary": {
            "provided": bool(evidence_payload),
            "subsystems": sorted(key for key, value in evidence_payload.items() if isinstance(value, Mapping)),
            "quality": evidence_quality,
        },
    }
