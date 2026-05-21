from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


BUILTIN_SUBAGENT_TEMPLATE_VERSION = "builtin-subagent-template.v1"

_READ_WORKSPACE_TOOLS = [
    "workspace_list_files",
    "workspace_read_file",
    "workspace_search_text",
    "workspace_file_info",
    "workspace_tree",
    "git_status",
    "git_diff",
    "git_show",
    "git_log",
    "git_branch",
]

_WRITE_WORKSPACE_TOOLS = [
    "workspace_apply_patch",
    "workspace_create_file",
    "workspace_write_file",
    "workspace_rename_path",
    "workspace_delete_path",
]

_SANDBOX_VERIFY_TOOLS = [
    "run_tests",
    "run_lint",
    "run_build",
    "test_discover",
    "test_run",
    "lint_run",
    "typecheck_run",
    "coverage_run",
    "dependency_audit",
]

_WEB_RESEARCH_TOOLS = [
    "web_search",
    "open_page",
    "fetch_url",
    "extract_page_text",
]


def _template(
    *,
    slug: str,
    name: str,
    description: str,
    system_prompt: str,
    tool_allowlist: list[str],
    output_schema: dict[str, Any],
    handoff_input_schema: dict[str, Any],
    runtime_policy: dict[str, Any],
    review_policy: dict[str, Any] | None = None,
    knowledge_policy: dict[str, Any] | None = None,
    budget_policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "system_prompt": system_prompt.strip(),
        "tool_allowlist": tool_allowlist,
        "skill_allowlist": [],
        "mcp_allowlist": [],
        "knowledge_policy": knowledge_policy or {"mode": "inherit"},
        "review_policy": review_policy or {},
        "runtime_policy": runtime_policy,
        "budget_policy": budget_policy or {},
        "output_schema": output_schema,
        "handoff_input_schema": handoff_input_schema,
        "metadata": {
            "template_slug": slug,
            "template_version": BUILTIN_SUBAGENT_TEMPLATE_VERSION,
            "source": "runtime_builtin_template",
            **(metadata or {}),
        },
    }


_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                },
            },
        },
        "review_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string"},
                    "description": {"type": "string"},
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                },
            },
        },
        "test_gaps": {"type": "array", "items": {"type": "string"}},
        "progress": {"type": "object"},
    },
}

_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "verification": {"type": "object"},
        "progress": {"type": "object"},
    },
}

_VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "verification": {"type": "object"},
        "failures": {"type": "array", "items": {"type": "object"}},
        "progress": {"type": "object"},
    },
}

_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "progress": {"type": "object"},
    },
}

BUILTIN_SUBAGENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "explorer": _template(
        slug="explorer",
        name="Explorer",
        description="Read-only project investigator for code location, facts, and bounded implementation plans.",
        system_prompt="""
You are a read-only project explorer. Locate relevant code, verify facts with file references, and return concise findings.
Do not write files, run shell commands, or expand the task beyond the delegated scope.
""",
        tool_allowlist=_READ_WORKSPACE_TOOLS + ["project_search_context", "project_read_context_item"],
        output_schema=_FINDINGS_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "focus_paths": {"type": "array", "items": {"type": "string"}},
                "questions": {"type": "array", "items": {"type": "string"}},
            },
        },
        runtime_policy={
            "delegation_mode": "parallel",
            "async_execution": True,
            "allow_delegation": False,
            "max_concurrent_delegations": 4,
            "max_parent_delegations": 8,
            "timeout_seconds": 180,
            "max_context_observations": 6,
            "waiting_user_propagation": "continue_parent_non_blocking",
        },
        budget_policy={"max_tokens": 6000},
        metadata={"capability": "workspace_read", "user_visible_stage": "reading_project"},
    ),
    "reviewer": _template(
        slug="reviewer",
        name="Reviewer",
        description="Read-only reviewer for diffs, test gaps, regression risks, and blocking findings.",
        system_prompt="""
You are a strict reviewer. Prioritize bugs, regressions, safety risks, and missing verification.
Do not rewrite code. Return structured findings with severity and file references.
""",
        tool_allowlist=_READ_WORKSPACE_TOOLS,
        output_schema=_FINDINGS_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "focus_paths": {"type": "array", "items": {"type": "string"}},
                "diff_summary": {"type": "string"},
            },
        },
        runtime_policy={
            "delegation_mode": "reviewer",
            "allow_delegation": False,
            "max_concurrent_delegations": 2,
            "max_parent_delegations": 4,
            "timeout_seconds": 180,
            "max_context_observations": 8,
        },
        review_policy={
            "required": True,
            "requires_reviewer": True,
            "blocking_severities": ["high", "critical"],
        },
        budget_policy={"max_tokens": 5000},
        metadata={"capability": "review", "user_visible_stage": "reviewing_changes"},
    ),
    "worker": _template(
        slug="worker",
        name="Worker",
        description="Scoped implementation worker that may write only inside delegated workspace paths.",
        system_prompt="""
You are a scoped implementation worker. Modify only the delegated paths and produce reviewable patch artifacts.
Respect the write scope exactly. Do not publish, deploy, access production systems, or change unrelated files.
""",
        tool_allowlist=_READ_WORKSPACE_TOOLS + _WRITE_WORKSPACE_TOOLS + _SANDBOX_VERIFY_TOOLS,
        output_schema=_PATCH_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "required": ["message"],
            "properties": {
                "message": {"type": "string"},
                "write_scope": {"type": "array", "items": {"type": "string"}},
                "focus_paths": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        runtime_policy={
            "delegation_mode": "parallel_worker",
            "async_execution": True,
            "allow_delegation": False,
            "max_concurrent_delegations": 2,
            "max_parent_delegations": 4,
            "timeout_seconds": 600,
            "max_context_observations": 8,
        },
        review_policy={
            "required": True,
            "requires_reviewer": True,
            "blocking_severities": ["high", "critical"],
        },
        budget_policy={"max_tokens": 10000, "max_tool_calls": 30},
        metadata={
            "capability": "workspace_write",
            "requires_write_scope": True,
            "requires_workspace": True,
            "user_visible_stage": "editing_workspace",
        },
    ),
    "tester": _template(
        slug="tester",
        name="Tester",
        description="Verification specialist for tests, lint, builds, and failure analysis.",
        system_prompt="""
You are a verification specialist. Run delegated checks, summarize failures, and recommend the smallest useful next check.
Do not write source files unless the task explicitly delegates test fixture changes.
""",
        tool_allowlist=_READ_WORKSPACE_TOOLS + _SANDBOX_VERIFY_TOOLS,
        output_schema=_VERIFICATION_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "checks": {"type": "array", "items": {"type": "string"}},
                "focus_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
        runtime_policy={
            "delegation_mode": "parallel",
            "async_execution": True,
            "allow_delegation": False,
            "max_concurrent_delegations": 3,
            "max_parent_delegations": 6,
            "timeout_seconds": 900,
            "max_context_observations": 6,
        },
        budget_policy={"max_tokens": 7000, "max_tool_calls": 20},
        metadata={"capability": "sandbox_verify", "requires_sandbox": True, "user_visible_stage": "running_checks"},
    ),
    "researcher": _template(
        slug="researcher",
        name="Researcher",
        description="Network-enabled researcher for current public documentation and cited source summaries.",
        system_prompt="""
You are a cited researcher. Use web tools only for the delegated research question and cite sources in the result.
Do not write workspace files or call external systems beyond allowed web retrieval.
""",
        tool_allowlist=_WEB_RESEARCH_TOOLS + ["knowledge_search", "knowledge_fetch_document"],
        output_schema=_RESEARCH_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "domains": {"type": "array", "items": {"type": "string"}},
                "questions": {"type": "array", "items": {"type": "string"}},
            },
        },
        runtime_policy={
            "delegation_mode": "parallel",
            "async_execution": True,
            "allow_delegation": False,
            "max_concurrent_delegations": 3,
            "max_parent_delegations": 6,
            "timeout_seconds": 240,
            "max_context_observations": 4,
        },
        budget_policy={"max_tokens": 7000, "max_network_calls": 12},
        metadata={"capability": "web_research", "requires_network": True, "user_visible_stage": "researching_sources"},
    ),
    "devops": _template(
        slug="devops",
        name="DevOps",
        description="Sandbox-only diagnostics specialist for test environment health checks and logs.",
        system_prompt="""
You are a sandbox diagnostics specialist. Inspect only delegated test or sandbox services.
Do not access production systems, mutate databases, deploy, or change infrastructure.
""",
        tool_allowlist=["shell_exec", "process_list", "process_stop"] + _SANDBOX_VERIFY_TOOLS,
        output_schema=_VERIFICATION_SCHEMA,
        handoff_input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "service": {"type": "string"},
                "checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        runtime_policy={
            "delegation_mode": "high_risk",
            "allow_delegation": False,
            "max_concurrent_delegations": 1,
            "max_parent_delegations": 3,
            "timeout_seconds": 600,
            "max_context_observations": 6,
        },
        review_policy={
            "required": True,
            "requires_reviewer": True,
            "blocking_severities": ["medium", "high", "critical"],
        },
        budget_policy={"max_tokens": 6000, "max_shell_calls": 10},
        metadata={
            "capability": "sandbox_operations",
            "requires_sandbox": True,
            "risk_level": "high",
            "user_visible_stage": "checking_sandbox_service",
        },
    ),
}


def list_builtin_subagent_template_slugs() -> list[str]:
    return list(BUILTIN_SUBAGENT_TEMPLATES)


def get_builtin_subagent_template(slug: str) -> dict[str, Any] | None:
    template = BUILTIN_SUBAGENT_TEMPLATES.get(str(slug or "").strip().lower())
    return deepcopy(template) if template is not None else None


def _merge_mapping(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_mapping(merged[key], value)
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def build_builtin_subagent_target(
    slug: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> SubagentTarget | None:
    payload = get_builtin_subagent_template(slug)
    if payload is None:
        return None
    overrides = overrides if isinstance(overrides, dict) else {}
    metadata = {
        **dict(payload.get("metadata") or {}),
        **dict(overrides.get("metadata") if isinstance(overrides.get("metadata"), dict) else {}),
    }
    merge_keys = {
        "config",
        "output_schema",
        "handoff_input_schema",
        "knowledge_policy",
        "review_policy",
        "runtime_policy",
        "budget_policy",
    }
    for key, value in overrides.items():
        if key in {"id", "template", "builtin_template", "metadata"}:
            continue
        if key in merge_keys and isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = _merge_mapping(payload[key], value)
            continue
        if value not in (None, "", [], {}):
            payload[key] = value
    payload["metadata"] = metadata
    return SubagentTarget.model_validate(payload)
