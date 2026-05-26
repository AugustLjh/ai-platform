"""Tests for audit view with field-level permission boundaries and redaction."""

from __future__ import annotations

import pytest

from ai_runtime.core.agent_runtime.audit_view import (
    AuditViewPolicy,
    DEFAULT_AUDIT_VIEW_POLICY,
    FieldPolicy,
    FieldVisibility,
    RedactionResult,
    ViewerRole,
    apply_audit_view,
    build_audit_view_for_run,
    build_audit_view_for_events,
    build_audit_view_for_tool_calls,
    evaluate_redaction_rules,
)


def _sample_run_data() -> dict:
    return {
        "id": "run-1",
        "status": "completed",
        "input": {"message": "Fix the login bug"},
        "final_output": "I fixed the login bug by updating the auth middleware.",
        "final_output_text": "Fixed login bug.",
        "final_output_json": {"answer": "Fixed"},
        "error_message": "Internal: connection pool exhausted at db:5432",
        "context": {
            "workspace": {
                "root": "/tmp/ai-platform-workspaces/tenant-1/run-1/workspace",
                "source": {"path": "/srv/repos/my-project", "type": "existing"},
            },
            "workspace_root": "/tmp/ai-platform-workspaces/tenant-1/run-1/workspace",
        },
        "metadata": {
            "delegation": {
                "parent_context": {"secret_key": "sk-abc123", "task": "parent task"},
                "policy_snapshot": {"max_depth": 3, "budget": 10000},
            },
        },
        "tool_calls": [
            {
                "id": "tc-1",
                "name": "workspace_read_file",
                "arguments": {"path": "src/auth.py", "api_key": "sk-secret-key-123"},
                "result": {"content": "def login(): pass", "password": "hunter2"},
            },
        ],
        "events": [
            {
                "event_type": "tool.completed",
                "payload": {"tool_name": "shell_exec", "token": "ghp_abc123xyz"},
            },
        ],
        "artifacts": [
            {
                "artifact_type": "code_patch",
                "payload": {"diff": "+fixed line"},
                "metadata": {"internal_trace_id": "trace-123"},
            },
        ],
    }


async def test_user_view_hides_workspace_paths():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.USER)

    assert "[HIDDEN:" in result["context"]["workspace"]["root"]
    assert "[HIDDEN:" in result["context"]["workspace"]["source"]["path"]
    assert "[HIDDEN:" in result["context"]["workspace_root"]


async def test_user_view_shows_input_and_output():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.USER)

    assert result["input"]["message"] == "Fix the login bug"
    assert "fixed the login bug" in result["final_output"]
    assert result["final_output_text"] == "Fixed login bug."


async def test_user_view_hides_error_message():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.USER)

    assert "[HIDDEN:" in result["error_message"]


async def test_operator_view_shows_workspace_paths():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.OPERATOR)

    assert "/tmp/ai-platform-workspaces" in result["context"]["workspace"]["root"]
    assert "/srv/repos/my-project" in result["context"]["workspace"]["source"]["path"]


async def test_operator_view_shows_error_message():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.OPERATOR)

    assert "connection pool exhausted" in result["error_message"]


async def test_operator_view_hides_delegation_context():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.OPERATOR)

    assert "[HIDDEN:" in result["metadata"]["delegation"]["parent_context"]
    assert "[HIDDEN:" in result["metadata"]["delegation"]["policy_snapshot"]


async def test_admin_view_shows_delegation_context():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.ADMIN)

    assert isinstance(result["metadata"]["delegation"]["parent_context"], dict)
    assert isinstance(result["metadata"]["delegation"]["policy_snapshot"], dict)


async def test_sensitive_key_redaction():
    data = {
        "username": "alice",
        "password": "hunter2",
        "api_key": "sk-abc123",
        "authorization": "Bearer token123",
        "name": "test",
    }
    result = RedactionResult()
    filtered = apply_audit_view(data, viewer_role=ViewerRole.USER, result=result)

    assert filtered["username"] == "alice"
    assert filtered["name"] == "test"
    assert filtered["password"] == "[REDACTED]"
    assert filtered["api_key"] == "[REDACTED]"
    assert filtered["authorization"] == "[REDACTED]"
    assert result.redacted_field_count >= 3


async def test_sensitive_value_pattern_redaction():
    data = {
        "header": "Bearer sk-1234567890abcdef1234567890",
        "github_token": "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
        "aws_key": "AKIAIOSFODNN7EXAMPLE1",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
        "normal_value": "hello world",
    }
    result = RedactionResult()
    filtered = apply_audit_view(data, viewer_role=ViewerRole.USER, result=result)

    assert filtered["normal_value"] == "hello world"
    assert filtered["header"] == "[REDACTED]"
    assert filtered["github_token"] == "[REDACTED]"
    assert filtered["aws_key"] == "[REDACTED]"
    assert filtered["jwt"] == "[REDACTED]"


async def test_depth_limit_prevents_infinite_recursion():
    data: dict = {"level": {}}
    current = data["level"]
    for i in range(15):
        current["nested"] = {}
        current = current["nested"]
    current["value"] = "deep"

    policy = AuditViewPolicy(max_field_depth=5)
    filtered = apply_audit_view(data, viewer_role=ViewerRole.ADMIN, policy=policy)

    found_limit = False

    def _check(obj):
        nonlocal found_limit
        if obj == "[DEPTH_LIMIT]":
            found_limit = True
        elif isinstance(obj, dict):
            for v in obj.values():
                _check(v)

    _check(filtered)
    assert found_limit


async def test_array_truncation():
    data = {"items": list(range(100))}
    policy = AuditViewPolicy(max_array_items_visible=10)
    filtered = apply_audit_view(data, viewer_role=ViewerRole.ADMIN, policy=policy)

    assert len(filtered["items"]) == 11
    assert "90 more items" in filtered["items"][-1]


async def test_audit_metadata_included_in_run_view():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.USER)

    assert "_audit_metadata" in result
    meta = result["_audit_metadata"]
    assert meta["viewer_role"] == "user"
    assert meta["original_field_count"] > 0
    assert meta["redacted_field_count"] > 0
    assert "applied_at" in meta


async def test_tool_call_view_respects_role():
    tool_calls = [
        {
            "id": "tc-1",
            "name": "shell_exec",
            "arguments": {"command": ["ls"], "secret": "hidden"},
            "result": {"stdout": "file.txt", "token": "abc123"},
        },
    ]
    user_view = build_audit_view_for_tool_calls(tool_calls, viewer_role=ViewerRole.USER)
    operator_view = build_audit_view_for_tool_calls(tool_calls, viewer_role=ViewerRole.OPERATOR)

    assert "[HIDDEN:" in str(user_view[0].get("arguments"))
    assert "[HIDDEN:" in str(user_view[0].get("result"))
    assert "ls" in str(operator_view[0]["arguments"])


async def test_event_view_respects_role():
    events = [
        {
            "event_type": "tool.completed",
            "payload": {"tool_name": "fetch_url", "api_key": "sk-secret"},
        },
    ]
    user_view = build_audit_view_for_events(events, viewer_role=ViewerRole.USER)
    operator_view = build_audit_view_for_events(events, viewer_role=ViewerRole.OPERATOR)

    assert "[HIDDEN:" in str(user_view[0].get("payload"))
    assert "fetch_url" in str(operator_view[0]["payload"])


async def test_redaction_rule_evaluation_detects_true_positives():
    test_cases = [
        {"key": "password", "value": "hunter2", "expected_redacted": True, "rule_name": "password_key"},
        {"key": "api_key", "value": "sk-abc123", "expected_redacted": True, "rule_name": "api_key_key"},
        {"key": "name", "value": "alice", "expected_redacted": False, "rule_name": "normal_key"},
        {"key": "data", "value": "ghp_abcdefghijklmnopqrstuvwxyz1234567890", "expected_redacted": True, "rule_name": "github_token_value"},
    ]
    result = evaluate_redaction_rules(test_cases)

    assert result["status"] == "passed"
    assert result["total"] == 4
    assert result["passed"] == 4
    assert result["failed"] == 0
    assert result["false_positive_count"] == 0
    assert result["false_negative_count"] == 0


async def test_redaction_rule_evaluation_detects_false_negatives():
    test_cases = [
        {"key": "data", "value": "short", "expected_redacted": True, "rule_name": "too_short_value"},
    ]
    result = evaluate_redaction_rules(test_cases)

    assert result["status"] == "failed"
    assert result["false_negative_count"] == 1


async def test_system_role_sees_everything():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.SYSTEM)

    meta = result["_audit_metadata"]
    assert meta["redacted_field_count"] == 0


async def test_anonymous_role_sees_minimal():
    data = _sample_run_data()
    result = build_audit_view_for_run(data, viewer_role=ViewerRole.ANONYMOUS)

    meta = result["_audit_metadata"]
    assert meta["redacted_field_count"] > 5
