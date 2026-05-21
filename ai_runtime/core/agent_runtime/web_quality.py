from __future__ import annotations

from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


WEB_SEARCH_QUALITY_PROTOCOL_VERSION = "managed-web.search-quality-suite.v1"

DEFAULT_WEB_SEARCH_QUALITY_CASES: list[dict[str, Any]] = [
    {
        "name": "search result policy boundary",
        "source": "builtin",
        "policy": {
            "allowed_domains": ["search.example.com", "docs.example.com"],
            "search_require_url": True,
            "search_require_title": True,
            "search_require_snippet": False,
            "search_allowed_schemes": ["https"],
            "search_reject_disallowed_domains": True,
            "search_reject_duplicates": True,
        },
        "actual": [
            {
                "title": "Runtime Plan",
                "url": "https://docs.example.com/runtime",
                "snippet": "Use web artifacts.",
            },
            {
                "title": "Runtime Plan",
                "url": "https://docs.example.com/runtime",
                "snippet": "Duplicate result.",
            },
            {
                "title": "Denied domain",
                "url": "https://evil.example.net/bad",
                "snippet": "Denied by allowlist.",
            },
            {
                "title": "Missing URL",
                "snippet": "Rejected because URL is required.",
            },
        ],
        "expected": {
            "accepted_count": 1,
            "rejected_count": 3,
            "required_accepted_urls": ["https://docs.example.com/runtime"],
            "required_rejection_reasons": [
                "duplicate search result",
                "url host is outside allowed web domains",
                "url is required",
            ],
        },
    },
    {
        "name": "strict snippet requirement",
        "source": "builtin",
        "policy": {
            "allowed_domains": ["docs.example.com"],
            "search_require_url": True,
            "search_require_title": True,
            "search_require_snippet": True,
            "search_allowed_schemes": ["https"],
        },
        "actual": [
            {
                "title": "Missing snippet",
                "url": "https://docs.example.com/no-snippet",
            },
            {
                "title": "Complete result",
                "url": "https://docs.example.com/complete",
                "snippet": "Complete enough for preview.",
            },
        ],
        "expected": {
            "accepted_count": 1,
            "rejected_count": 1,
            "required_accepted_urls": ["https://docs.example.com/complete"],
            "required_rejection_reasons": ["snippet is required"],
        },
    },
    {
        "name": "scheme allowlist",
        "source": "builtin",
        "policy": {
            "allowed_domains": ["docs.example.com"],
            "search_allowed_schemes": ["https"],
        },
        "actual": [
            {
                "title": "HTTPS result",
                "url": "https://docs.example.com/secure",
                "snippet": "Accepted.",
            },
            {
                "title": "HTTP result",
                "url": "http://docs.example.com/insecure",
                "snippet": "Rejected.",
            },
        ],
        "expected": {
            "accepted_count": 1,
            "rejected_count": 1,
            "required_accepted_urls": ["https://docs.example.com/secure"],
            "required_rejection_reasons": ["search result URL uses a disallowed scheme"],
        },
    },
]


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _policy_value(policy: Any, *keys: str, default: Any = None) -> Any:
    if isinstance(policy, Mapping):
        for key in keys:
            if key in policy:
                return policy[key]
    for key in keys:
        if hasattr(policy, key):
            return getattr(policy, key)
    return default


def _policy_bool(policy: Any, snake: str, camel: str, default: bool) -> bool:
    value = _policy_value(policy, snake, camel, default=default)
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _policy_list(policy: Any, snake: str, camel: str, default: Sequence[str] = ()) -> list[str]:
    value = _policy_value(policy, snake, camel, default=default)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [_stringify(item) for item in _list(value) if _stringify(item)]


def _policy_snapshot(policy: Any) -> dict[str, Any]:
    return {
        "allowed_domains": _policy_list(policy, "allowed_domains", "allowedDomains"),
        "denied_domains": _policy_list(policy, "denied_domains", "deniedDomains"),
        "search_require_url": _policy_bool(policy, "search_require_url", "searchRequireUrl", True),
        "search_require_title": _policy_bool(policy, "search_require_title", "searchRequireTitle", True),
        "search_require_snippet": _policy_bool(policy, "search_require_snippet", "searchRequireSnippet", False),
        "search_allowed_schemes": _policy_list(
            policy,
            "search_allowed_schemes",
            "searchAllowedSchemes",
            ("https",),
        ),
        "search_reject_disallowed_domains": _policy_bool(
            policy,
            "search_reject_disallowed_domains",
            "searchRejectDisallowedDomains",
            True,
        ),
        "search_reject_duplicates": _policy_bool(
            policy,
            "search_reject_duplicates",
            "searchRejectDuplicates",
            True,
        ),
    }


def _domain_matches(host: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        normalized = _stringify(pattern).lower()
        if not normalized:
            continue
        if normalized.startswith("*."):
            suffix = normalized[1:]
            if host.endswith(suffix):
                return True
            continue
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def _validate_search_item_url(raw_url: Any, policy: Any) -> str:
    url = _stringify(raw_url)
    if not url:
        return ""
    parsed = urlparse(url)
    allowed_schemes = [item.lower() for item in _policy_list(policy, "search_allowed_schemes", "searchAllowedSchemes", ("https",))]
    if allowed_schemes and parsed.scheme.lower() not in set(allowed_schemes):
        raise PermissionError("search result URL uses a disallowed scheme")
    if parsed.scheme not in {"http", "https"}:
        raise PermissionError("only http and https URLs are allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("url host is required")
    denied_domains = _policy_list(policy, "denied_domains", "deniedDomains")
    if denied_domains and _domain_matches(host, denied_domains):
        raise PermissionError("url host is denied by web policy")
    allowed_domains = _policy_list(policy, "allowed_domains", "allowedDomains")
    if allowed_domains and not _domain_matches(host, allowed_domains):
        raise PermissionError("url host is outside allowed web domains")
    return url


def evaluate_search_result_items(items: Sequence[Any], policy: Any, *, limit: int) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    require_url = _policy_bool(policy, "search_require_url", "searchRequireUrl", True)
    require_title = _policy_bool(policy, "search_require_title", "searchRequireTitle", True)
    require_snippet = _policy_bool(policy, "search_require_snippet", "searchRequireSnippet", False)
    reject_disallowed_domains = _policy_bool(
        policy,
        "search_reject_disallowed_domains",
        "searchRejectDisallowedDomains",
        True,
    )
    reject_duplicates = _policy_bool(policy, "search_reject_duplicates", "searchRejectDuplicates", True)

    for raw_item in list(items or [])[: max(0, int(_number(limit, 0)))]:
        if not isinstance(raw_item, dict):
            rejected.append(
                {
                    "disposition": "rejected",
                    "reason": "item is not an object",
                    "item": raw_item,
                }
            )
            continue

        title = _stringify(raw_item.get("title") or raw_item.get("name"))
        url = _stringify(raw_item.get("url") or raw_item.get("link") or raw_item.get("href"))
        snippet = _stringify(raw_item.get("snippet") or raw_item.get("summary") or raw_item.get("text"))
        duplicate_key = (title.lower(), url.lower())

        if reject_disallowed_domains and url:
            try:
                _validate_search_item_url(url, policy)
            except Exception as exc:
                rejected.append(
                    {
                        "disposition": "rejected",
                        "reason": str(exc),
                        "item": {"title": title, "url": url, "snippet": snippet},
                    }
                )
                continue

        if require_url and not url:
            rejected.append(
                {
                    "disposition": "rejected",
                    "reason": "url is required",
                    "item": {"title": title, "url": url, "snippet": snippet},
                }
            )
            continue
        if require_title and not title:
            rejected.append(
                {
                    "disposition": "rejected",
                    "reason": "title is required",
                    "item": {"title": title, "url": url, "snippet": snippet},
                }
            )
            continue
        if require_snippet and not snippet:
            rejected.append(
                {
                    "disposition": "rejected",
                    "reason": "snippet is required",
                    "item": {"title": title, "url": url, "snippet": snippet},
                }
            )
            continue
        if reject_duplicates and duplicate_key in seen:
            rejected.append(
                {
                    "disposition": "rejected",
                    "reason": "duplicate search result",
                    "item": {"title": title, "url": url, "snippet": snippet},
                }
            )
            continue

        seen.add(duplicate_key)
        accepted.append(
            {
                "title": title or url,
                "url": url,
                "snippet": snippet,
                "disposition": "accepted",
            }
        )

    return {
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }


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


def evaluate_web_search_quality_case(case: dict[str, Any]) -> dict[str, Any]:
    actual = case.get("actual") or case.get("items") or case.get("results") or []
    if isinstance(actual, dict):
        actual = actual.get("items") or actual.get("results") or actual.get("data") or []
    policy = _dict(case.get("policy"))
    expected = _dict(case.get("expected"))
    limit = int(_number(case.get("limit") or expected.get("limit") or len(_list(actual)) or 10, 10))
    quality = evaluate_search_result_items(_list(actual), policy, limit=limit)
    policy_snapshot = _policy_snapshot(policy)

    checks: list[dict[str, Any]] = []
    if "accepted_count" in expected or "acceptedCount" in expected:
        expected_count = int(_number(expected.get("accepted_count", expected.get("acceptedCount")), 0))
        checks.append(_check(
            "accepted_count",
            quality["accepted_count"] == expected_count,
            1.5,
            "accepted result count matches expectation",
            {"expected": expected_count, "actual": quality["accepted_count"]},
        ))
    if "rejected_count" in expected or "rejectedCount" in expected:
        expected_count = int(_number(expected.get("rejected_count", expected.get("rejectedCount")), 0))
        checks.append(_check(
            "rejected_count",
            quality["rejected_count"] == expected_count,
            1.5,
            "rejected result count matches expectation",
            {"expected": expected_count, "actual": quality["rejected_count"]},
        ))

    accepted_urls = {_stringify(item.get("url")).lower() for item in quality["accepted"] if _stringify(item.get("url"))}
    required_urls = {
        _stringify(item).lower()
        for item in _list(expected.get("required_accepted_urls") or expected.get("requiredAcceptedUrls"))
    }
    if required_urls:
        checks.append(_check(
            "accepted_url_recall",
            required_urls.issubset(accepted_urls),
            2.0,
            "required accepted URLs are preserved",
            {"missing": sorted(required_urls - accepted_urls)},
        ))

    rejection_reasons = {_stringify(item.get("reason")).lower() for item in quality["rejected"] if isinstance(item, dict)}
    required_reasons = {
        _stringify(item).lower()
        for item in _list(expected.get("required_rejection_reasons") or expected.get("requiredRejectionReasons"))
    }
    if required_reasons:
        checks.append(_check(
            "rejection_reason_recall",
            required_reasons.issubset(rejection_reasons),
            2.0,
            "required rejection reasons are emitted",
            {"missing": sorted(required_reasons - rejection_reasons)},
        ))

    if not checks:
        checks.append(_check(
            "has_accepted_results",
            quality["accepted_count"] > 0,
            1.0,
            "search quality case has at least one accepted result",
        ))

    score = _score_checks(checks)
    total_results = quality["accepted_count"] + quality["rejected_count"]
    rejection_reason_counts: dict[str, int] = {}
    for item in quality["rejected"]:
        if not isinstance(item, dict):
            continue
        reason = _stringify(item.get("reason"))
        if not reason:
            continue
        rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
    passed_checks = sum(1 for item in checks if item.get("passed"))
    summary = (
        f"{quality['accepted_count']} accepted / {quality['rejected_count']} rejected"
        f" · {passed_checks}/{len(checks)} checks passed"
        f" · score {score:.2f}"
    )
    return {
        "kind": "web_search",
        "name": case.get("name") or "web search quality case",
        "status": _status_for_score(score),
        "score": score,
        "summary": summary,
        "policy_snapshot": policy_snapshot,
        "total_results": total_results,
        "accepted_ratio": round(quality["accepted_count"] / total_results, 4) if total_results else 1.0,
        "check_count": len(checks),
        "passed_check_count": passed_checks,
        "failed_check_count": len(checks) - passed_checks,
        "rejection_reason_counts": rejection_reason_counts,
        "checks": checks,
        "accepted_count": quality["accepted_count"],
        "rejected_count": quality["rejected_count"],
        "accepted": quality["accepted"],
        "rejected": quality["rejected"],
    }


def evaluate_web_search_quality_suite(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_web_search_quality_case(case) for case in cases]
    total = len(results)
    passed = sum(1 for item in results if item.get("status") == "passed")
    warning = sum(1 for item in results if item.get("status") == "warning")
    failed = sum(1 for item in results if item.get("status") == "failed")
    average_score = round(sum(_number(item.get("score")) for item in results) / total, 4) if total else 1.0
    accepted_count = sum(int(_number(item.get("accepted_count"), 0)) for item in results)
    rejected_count = sum(int(_number(item.get("rejected_count"), 0)) for item in results)
    total_results = accepted_count + rejected_count
    check_count = sum(int(_number(item.get("check_count"), 0)) for item in results)
    passed_check_count = sum(int(_number(item.get("passed_check_count"), 0)) for item in results)
    failed_check_count = sum(int(_number(item.get("failed_check_count"), 0)) for item in results)
    rejection_reason_counts: dict[str, int] = {}
    for item in results:
        raw_counts = item.get("rejection_reason_counts")
        if not isinstance(raw_counts, dict):
            continue
        for reason, count in raw_counts.items():
            normalized_reason = _stringify(reason)
            if not normalized_reason:
                continue
            rejection_reason_counts[normalized_reason] = (
                rejection_reason_counts.get(normalized_reason, 0) + int(_number(count, 0))
            )
    summary = f"{passed} passed / {warning} warning / {failed} failed · avg score {average_score:.4f}"
    return {
        "protocol_version": WEB_SEARCH_QUALITY_PROTOCOL_VERSION,
        "status": "passed" if failed == 0 and warning == 0 else ("warning" if failed == 0 else "failed"),
        "total": total,
        "passed": passed,
        "warning": warning,
        "failed": failed,
        "average_score": average_score,
        "summary": summary,
        "total_results": total_results,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "accepted_ratio": round(accepted_count / total_results, 4) if total_results else 1.0,
        "check_count": check_count,
        "passed_check_count": passed_check_count,
        "failed_check_count": failed_check_count,
        "rejection_reason_counts": rejection_reason_counts,
        "case_summaries": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "score": item.get("score"),
                "summary": item.get("summary"),
                "accepted_count": item.get("accepted_count"),
                "rejected_count": item.get("rejected_count"),
                "failed_check_count": item.get("failed_check_count"),
            }
            for item in results
        ],
        "results": results,
    }


def evaluate_default_web_search_quality_suite(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    suite = cases if cases else DEFAULT_WEB_SEARCH_QUALITY_CASES
    result = evaluate_web_search_quality_suite(suite)
    result["suite_name"] = "builtin"
    result["suite_source"] = "request" if cases else "builtin"
    return result
