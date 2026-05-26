from __future__ import annotations

from copy import deepcopy
from typing import Any, Sequence


_FAILURE_TAXONOMY: dict[str, dict[str, dict[str, Any]]] = {
    "sandbox-exec": {
        "timeout": {
            "summary": "Command exceeded the configured sandbox timeout.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Retry with a narrower selector or target.",
                "Increase timeout_seconds only after confirming the command is expected to run longer.",
                "Inspect stdout and stderr before retrying to avoid repeating the same long-running command.",
            ],
        },
        "non_zero_exit": {
            "summary": "Command finished with a non-zero exit code.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Use the structured verification report and logs to identify the failing test, lint, build, or audit step.",
                "Fix the reported failure before retrying the same command.",
            ],
        },
        "runner_unavailable": {
            "summary": "The configured sandbox runner executable or backend is unavailable.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Verify the runner backend is installed and available on PATH.",
                "Run sandbox_isolation_check before exposing execution tools again.",
            ],
        },
        "unsupported_backend": {
            "summary": "The requested sandbox operation is not supported by the configured backend.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Switch to a supported backend for this operation.",
                "Use short-lived run_tests, run_lint, or run_build when long-running process sessions are unavailable.",
            ],
        },
        "unknown_session": {
            "summary": "The requested managed sandbox process session was not found.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Call process_list to discover active managed sessions.",
                "Start a new dev server session if the prior session expired or was already stopped.",
            ],
        },
        "policy_denied": {
            "summary": "Sandbox policy denied the requested command or path.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Choose a command and cwd that stay inside the configured workspace.",
                "Ask an operator to review policy only when the denied capability is required.",
            ],
        },
    },
    "web": {
        "timeout": {
            "summary": "Network request exceeded the configured web timeout.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Retry once with a narrower URL, query, or smaller max_bytes limit.",
                "Inspect domain health before increasing AGENT_WEB_TIMEOUT_SECONDS.",
            ],
        },
        "network_error": {
            "summary": "Network request failed before a usable response was received.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Retry once after checking the URL and allowed domain policy.",
                "Use another source when the remote endpoint remains unavailable.",
            ],
        },
        "content_type_denied": {
            "summary": "Response content type is outside the configured allowlist.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Use a URL that returns an allowed content type.",
                "Ask an operator to review AGENT_WEB_ALLOWED_CONTENT_TYPES or AGENT_WEB_ALLOWED_DOWNLOAD_CONTENT_TYPES before broadening policy.",
            ],
        },
        "policy_denied": {
            "summary": "Web policy denied the requested URL or search result.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Use an http or https URL within the configured allowed domains.",
                "Ask an operator to review allowed and denied domain policy only when the source is required.",
            ],
        },
        "search_no_results": {
            "summary": "Search completed but produced no acceptable results after quality checks.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Retry with a more specific query.",
                "Review rejected search results and domain policy before changing quality rules.",
            ],
        },
        "browser_unavailable": {
            "summary": "Browser runtime is disabled, unconfigured, or unavailable.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Set AGENT_BROWSER_ENABLED=true and AGENT_BROWSER_CONFIGURED=true after reviewing browser policy.",
                "Install and verify the configured browser runtime, for example: playwright install chromium.",
            ],
        },
        "browser_session_limit": {
            "summary": "Browser session limit has been reached.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Close unused sessions with browser_close.",
                "Wait for stale sessions to expire or tune AGENT_BROWSER_MAX_SESSIONS after capacity review.",
            ],
        },
        "unknown_session": {
            "summary": "The requested browser session was not found.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Open a new browser session or use the latest session_id returned by browser_open.",
                "Check browser session TTL if sessions expire during long verification flows.",
            ],
        },
        "pdf_dependency_missing": {
            "summary": "PDF extraction dependency is not installed.",
            "severity": "error",
            "recoverable": True,
            "recovery_actions": [
                "Install PyPDF2 in the runtime environment and add it to dependency version control if newly introduced.",
                "Use download_file as a fallback when text extraction is unavailable.",
            ],
        },
        "parse_error": {
            "summary": "Downloaded content could not be parsed into the requested representation.",
            "severity": "warning",
            "recoverable": True,
            "recovery_actions": [
                "Retry with a smaller page or byte limit.",
                "Use the raw downloaded artifact for manual review when parsing keeps failing.",
            ],
        },
    },
}


def build_failure_taxonomy(provider: str, categories: Sequence[str] | None = None) -> dict[str, Any]:
    provider_key = str(provider or "").strip()
    catalog = _FAILURE_TAXONOMY.get(provider_key, {})
    selected = list(categories or catalog.keys())
    entries = []
    for category in selected:
        key = str(category or "").strip()
        if not key or key not in catalog:
            continue
        entry = deepcopy(catalog[key])
        entry["category"] = key
        entries.append(entry)
    return {
        "provider": provider_key,
        "categories": entries,
    }


def build_failure_recovery(provider: str, category: str, *, message: str | None = None) -> dict[str, Any]:
    provider_key = str(provider or "").strip()
    category_key = str(category or "").strip() or "unknown"
    entry = deepcopy(_FAILURE_TAXONOMY.get(provider_key, {}).get(category_key, {}))
    summary = str(message or entry.get("summary") or f"{provider_key or 'tool'} failed with {category_key}").strip()
    return {
        "primary_code": f"{provider_key.replace('-', '_')}_{category_key}" if provider_key else category_key,
        "failure_category": category_key,
        "summary": summary,
        "severity": entry.get("severity") or "warning",
        "recoverable": bool(entry.get("recoverable", True)),
        "actions": list(entry.get("recovery_actions") or []),
    }


def failure_recovery_actions(provider: str, category: str) -> list[str]:
    recovery = build_failure_recovery(provider, category)
    return list(recovery.get("actions") or [])
