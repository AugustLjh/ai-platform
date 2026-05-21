from __future__ import annotations

from ai_runtime.core.agent_runtime.web_quality import (
    DEFAULT_WEB_SEARCH_QUALITY_CASES,
    evaluate_default_web_search_quality_suite,
    evaluate_search_result_items,
    evaluate_web_search_quality_case,
    evaluate_web_search_quality_suite,
)


async def test_search_result_items_apply_policy_boundaries():
    result = evaluate_search_result_items(
        [
            {"title": "Runtime", "url": "https://docs.example.com/runtime", "snippet": "ok"},
            {"title": "Runtime", "url": "https://docs.example.com/runtime", "snippet": "duplicate"},
            {"title": "Bad", "url": "https://evil.example.net/bad", "snippet": "denied"},
            {"title": "Missing URL", "snippet": "missing"},
        ],
        {
            "allowed_domains": ["docs.example.com"],
            "search_require_url": True,
            "search_require_title": True,
            "search_allowed_schemes": ["https"],
            "search_reject_disallowed_domains": True,
            "search_reject_duplicates": True,
        },
        limit=4,
    )

    assert result["accepted_count"] == 1
    assert result["accepted"][0]["url"] == "https://docs.example.com/runtime"
    assert result["rejected_count"] == 3
    assert {item["reason"] for item in result["rejected"]} == {
        "duplicate search result",
        "url host is outside allowed web domains",
        "url is required",
    }


async def test_web_search_quality_case_scores_expected_rejections():
    result = evaluate_web_search_quality_case(
        {
            "name": "quality boundary",
            "policy": {
                "allowed_domains": ["docs.example.com"],
                "search_require_url": True,
                "search_require_title": True,
                "search_require_snippet": True,
                "search_allowed_schemes": ["https"],
            },
            "actual": [
                {"title": "Complete", "url": "https://docs.example.com/complete", "snippet": "ok"},
                {"title": "Missing snippet", "url": "https://docs.example.com/missing"},
            ],
            "expected": {
                "accepted_count": 1,
                "rejected_count": 1,
                "required_accepted_urls": ["https://docs.example.com/complete"],
                "required_rejection_reasons": ["snippet is required"],
            },
        }
    )

    assert result["status"] == "passed"
    assert result["score"] == 1.0
    assert result["summary"] == "1 accepted / 1 rejected · 4/4 checks passed · score 1.00"
    assert result["policy_snapshot"]["allowed_domains"] == ["docs.example.com"]
    assert result["accepted_ratio"] == 0.5
    assert result["accepted_count"] == 1
    assert any(check["name"] == "rejection_reason_recall" and check["passed"] for check in result["checks"])


async def test_web_search_quality_case_detects_missing_expected_url():
    result = evaluate_web_search_quality_case(
        {
            "policy": {"allowed_domains": ["docs.example.com"]},
            "actual": [
                {"title": "Other", "url": "https://docs.example.com/other", "snippet": "ok"},
            ],
            "expected": {
                "accepted_count": 1,
                "required_accepted_urls": ["https://docs.example.com/expected"],
            },
        }
    )

    assert result["status"] == "failed"
    assert result["score"] < 0.75
    assert any(check["name"] == "accepted_url_recall" and not check["passed"] for check in result["checks"])


async def test_web_search_quality_suite_aggregates_cases():
    result = evaluate_web_search_quality_suite(
        [
            {
                "policy": {"allowed_domains": ["docs.example.com"]},
                "actual": [{"title": "Runtime", "url": "https://docs.example.com/runtime"}],
                "expected": {"accepted_count": 1},
            },
            {
                "policy": {"allowed_domains": ["docs.example.com"]},
                "actual": [{"title": "Bad", "url": "https://evil.example.net/bad"}],
                "expected": {
                    "accepted_count": 0,
                    "rejected_count": 1,
                    "required_rejection_reasons": ["url host is outside allowed web domains"],
                },
            },
        ]
    )

    assert result["status"] == "passed"
    assert result["total"] == 2
    assert result["passed"] == 2
    assert result["summary"] == "2 passed / 0 warning / 0 failed · avg score 1.0000"
    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["accepted_ratio"] == 0.5
    assert result["check_count"] >= 2
    assert result["rejection_reason_counts"]["url host is outside allowed web domains"] == 1
    assert result["case_summaries"][0]["summary"]


async def test_default_web_search_quality_suite_uses_builtin_cases_when_request_is_empty():
    result = evaluate_default_web_search_quality_suite([])

    assert result["status"] == "passed"
    assert result["suite_name"] == "builtin"
    assert result["suite_source"] == "builtin"
    assert result["protocol_version"] == "managed-web.search-quality-suite.v1"
    assert result["total"] == len(DEFAULT_WEB_SEARCH_QUALITY_CASES)


async def test_default_web_search_quality_suite_marks_request_source_when_custom_cases_provided():
    result = evaluate_default_web_search_quality_suite(
        [
            {
                "actual": [{"title": "Runtime", "url": "https://docs.example.com/runtime"}],
                "expected": {"accepted_count": 1},
            }
        ]
    )

    assert result["status"] == "passed"
    assert result["suite_source"] == "request"
    assert result["total"] == 1
