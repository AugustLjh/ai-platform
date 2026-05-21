from __future__ import annotations

from ai_runtime.core.agent_runtime.subagents.quality import (
    DEFAULT_SUBAGENT_QUALITY_CASES,
    evaluate_default_subagent_quality_suite,
    evaluate_collaboration_quality_case,
    evaluate_reviewer_quality_case,
    evaluate_subagent_quality_suite,
    evaluate_worker_quality_case,
    evaluate_tester_quality_case,
)


async def test_reviewer_quality_case_scores_expected_blocking_findings():
    result = evaluate_reviewer_quality_case({
        "name": "critical reviewer case",
        "kind": "reviewer",
        "actual": {
            "decision": "changes_requested",
            "approved": False,
            "blocking_finding_count": 1,
            "conclusion": "A blocking SQL injection risk remains.",
            "findings": [
                {
                    "title": "SQL injection",
                    "severity": "critical",
                    "path": "src/db.py",
                    "line": 42,
                }
            ],
        },
        "expected": {
            "decision": "changes_requested",
            "approved": False,
            "min_blocking_findings": 1,
            "required_severities": ["critical"],
            "findings": [
                {
                    "title": "SQL injection",
                    "path": "src/db.py",
                    "line": 42,
                }
            ],
            "requires_conclusion": True,
        },
    })

    assert result["status"] == "passed"
    assert result["score"] == 1.0
    assert result["finding_count"] == 1


async def test_reviewer_quality_case_detects_missing_expected_findings():
    result = evaluate_reviewer_quality_case({
        "kind": "reviewer",
        "actual": {
            "decision": "approved",
            "approved": True,
            "blocking_finding_count": 0,
            "findings": [],
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
        },
    })

    assert result["status"] == "failed"
    assert result["score"] < 0.75
    assert any(check["name"] == "finding_recall" and not check["passed"] for check in result["checks"])


async def test_tester_quality_case_scores_structured_verification_report():
    result = evaluate_tester_quality_case({
        "name": "pytest failure capture",
        "kind": "tester",
        "actual": {
            "artifact_type": "verification_report",
            "payload": {
                "status": "failed",
                "command": ["python", "-m", "pytest"],
                "logs": {"stdout": "FAILED tests/test_app.py::test_app"},
                "structured_report": {
                    "summary": {"failed": 1},
                    "reports": [
                        {
                            "summary": {"failed": 1},
                            "failures": [
                                {"title": "tests/test_app.py::test_app"}
                            ],
                        }
                    ],
                },
            },
        },
        "expected": {
            "status": "failed",
            "min_failed_tests": 1,
            "required_failure_titles": ["tests/test_app.py::test_app"],
            "require_command": True,
            "require_logs": True,
            "require_structured_report": True,
        },
    })

    assert result["status"] == "passed"
    assert result["score"] == 1.0
    assert result["failed_test_count"] >= 1


async def test_worker_quality_case_scores_scoped_patch_and_verification():
    result = evaluate_worker_quality_case({
        "name": "worker patch with verification",
        "kind": "worker",
        "actual": {
            "input": {"write_scope": ["ai_runtime/core/agent_runtime/subagents"]},
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
                        "review_notes": [],
                        "merge_policy": "manual_review_required",
                    },
                },
                {
                    "artifact_type": "verification_report",
                    "payload": {"status": "passed", "command": ["python", "-m", "pytest"]},
                },
            ],
        },
        "expected": {
            "require_write_scope": True,
            "require_patch_artifact": True,
            "require_verification_report": True,
            "enforce_write_scope": True,
            "required_paths": ["ai_runtime/core/agent_runtime/subagents/governance.py"],
        },
    })

    assert result["status"] == "passed"
    assert result["score"] == 1.0
    assert result["changed_path_count"] == 1
    assert result["patch_count"] == 1
    assert result["verification_count"] == 1


async def test_worker_quality_case_detects_out_of_scope_changes_and_unreviewed_delete():
    result = evaluate_worker_quality_case({
        "kind": "worker",
        "actual": {
            "input": {"write_scope": ["frontend-vue/src/components/agent"]},
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
                            },
                            {
                                "path": "frontend-vue/src/views/AgentExtensions.vue",
                                "operation": "modify",
                                "changed": True,
                            },
                        ],
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
        },
    })

    assert result["status"] == "failed"
    assert any(check["name"] == "write_scope_enforcement" and not check["passed"] for check in result["checks"])
    assert result["out_of_scope_paths"] == ["frontend-vue/src/views/AgentExtensions.vue"]


async def test_worker_quality_case_requires_writeback_confirmation_for_rename():
    result = evaluate_worker_quality_case({
        "kind": "worker",
        "actual": {
            "input": {
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
                        "review_notes": ["Rename requires explicit writeback approval."],
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
            "required_paths": ["frontend-vue/src/components/agent/AgentPatchCard.vue"],
        },
    })

    assert result["status"] == "passed"
    assert result["writeback"]["requires_confirmation"] is True
    assert result["merge_policies"] == ["explicit_user_writeback"]


async def test_worker_quality_case_detects_overlapping_write_scope_governance():
    result = evaluate_worker_quality_case({
        "kind": "worker",
        "actual": {
            "input": {
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
                    }
                ]
            },
        },
        "expected": {
            "require_write_scope": True,
            "require_scope_conflict_detection": True,
            "required_governance_codes": ["write_scope_conflict"],
        },
    })

    assert result["status"] == "passed"
    assert result["governance_codes"] == ["write_scope_conflict"]
    assert result["overlapping_scope_pairs"] == [
        {
            "scope": "ai_runtime/core/agent_runtime/subagents",
            "sibling_scope": "ai_runtime/core/agent_runtime",
        }
    ]


async def test_worker_quality_case_scores_multi_stage_writeback_reviewability():
    result = evaluate_worker_quality_case({
        "kind": "worker",
        "actual": {
            "input": {
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
                        "review_notes": ["Rename and delete require explicit writeback review."],
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
                        "command": ["npm", "run", "test", "--", "frontend-vue/tests/agentRunTree.test.js"],
                    },
                },
            ],
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
    })

    assert result["status"] == "passed"
    assert result["score"] == 1.0
    assert result["changed_path_count"] == 3
    assert result["verification_count"] == 1
    assert result["operations"] == ["delete", "modify", "rename"]
    assert result["overlapping_scope_pairs"] == []


async def test_collaboration_quality_case_scores_partial_failure_recovery():
    result = evaluate_collaboration_quality_case({
        "kind": "collaboration",
        "actual": {
            "invocations": [
                {
                    "target": "worker-runtime",
                    "status": "completed",
                    "write_scope": ["ai_runtime/core/agent_runtime/subagents"],
                },
                {
                    "target": "worker-frontend",
                    "status": "failed",
                    "write_scope": ["frontend-vue/src/components/agent"],
                    "failure_strategy": {
                        "strategy": "retry_or_fallback",
                        "retry_allowed": True,
                        "recovery": {"actions": ["Retry with a narrower write_scope."]},
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
    })

    assert result["status"] == "passed"
    assert result["completed_count"] == 1
    assert result["failed_count"] == 1


async def test_collaboration_quality_case_detects_missing_failure_strategy():
    result = evaluate_collaboration_quality_case({
        "kind": "collaboration",
        "actual": {
            "invocations": [
                {"target": "worker-runtime", "status": "completed", "write_scope": ["ai_runtime"]},
                {"target": "worker-frontend", "status": "failed", "write_scope": ["frontend-vue"]},
            ],
        },
        "expected": {
            "min_invocations": 2,
            "min_completed": 1,
            "min_failed": 1,
            "require_partial_failure_strategy": True,
            "require_recovery_actions": True,
        },
    })

    assert result["status"] == "failed"
    assert any(check["name"] == "partial_failure_strategy" and not check["passed"] for check in result["checks"])
    assert any(check["name"] == "recovery_actions" and not check["passed"] for check in result["checks"])


async def test_collaboration_quality_case_scores_waiting_user_propagation():
    result = evaluate_collaboration_quality_case({
        "kind": "collaboration",
        "actual": {
            "parent": {"status": "waiting_user", "waiting_user": True},
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
    })

    assert result["status"] == "passed"
    assert result["waiting_user_count"] == 1


async def test_collaboration_quality_case_detects_resume_boundary_leakage():
    result = evaluate_collaboration_quality_case({
        "kind": "collaboration",
        "actual": {
            "resume": {
                "latest_attempt": 2,
                "stale_invocation_count": 1,
                "stale_event_count": 0,
                "stale_artifact_count": 0,
            },
            "invocations": [
                {"target": "tester-old", "status": "completed", "attempt": 1},
                {"target": "tester-new", "status": "completed", "attempt": 2},
            ],
        },
        "expected": {
            "min_invocations": 1,
            "require_resume_boundary_cleanup": True,
        },
    })

    assert result["status"] == "failed"
    assert any(check["name"] == "resume_boundary_cleanup" and not check["passed"] for check in result["checks"])


async def test_quality_suite_aggregates_reviewer_and_tester_cases():
    result = evaluate_subagent_quality_suite([
        {
            "kind": "reviewer",
            "actual": {"decision": "approved", "approved": True},
            "expected": {"decision": "approved", "approved": True},
        },
        {
            "kind": "tester",
            "actual": {"payload": {"status": "completed", "command": ["npm", "test"]}},
            "expected": {"status": "completed", "require_command": True},
        },
        {
            "kind": "worker",
            "actual": {
                "input": {"write_scope": ["src"]},
                "artifacts": [
                    {
                        "artifact_type": "code_patch",
                        "payload": {
                            "operation": "modify",
                            "files": [{"path": "src/app.py", "operation": "modify", "changed": True}],
                            "merge_policy": "manual_review_required",
                        },
                    }
                ],
            },
            "expected": {
                "require_write_scope": True,
                "require_patch_artifact": True,
                "enforce_write_scope": True,
                "required_paths": ["src/app.py"],
            },
        },
        {
            "kind": "collaboration",
            "actual": {
                "invocations": [
                    {
                        "target": "worker-runtime",
                        "status": "completed",
                        "write_scope": ["src"],
                    }
                ],
            },
            "expected": {"min_invocations": 1},
        },
    ])

    assert result["status"] == "passed"
    assert result["total"] == 4
    assert result["passed"] == 4


async def test_default_quality_suite_uses_builtin_cases_when_request_is_empty():
    result = evaluate_default_subagent_quality_suite([])

    assert result["status"] == "passed"
    assert result["suite_name"] == "builtin"
    assert result["suite_source"] == "builtin"
    assert result["protocol_version"] == "managed-subagent.quality-suite.v1"
    assert result["total"] == len(DEFAULT_SUBAGENT_QUALITY_CASES)
    assert result["total"] >= 10


async def test_default_quality_suite_marks_request_source_when_custom_cases_provided():
    result = evaluate_default_subagent_quality_suite([
        {
            "kind": "reviewer",
            "actual": {"decision": "approved", "approved": True},
            "expected": {"decision": "approved", "approved": True},
        }
    ])

    assert result["status"] == "passed"
    assert result["suite_source"] == "request"
    assert result["total"] == 1
