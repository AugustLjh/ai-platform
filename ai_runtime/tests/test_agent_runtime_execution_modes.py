from ai_runtime.core.agent_runtime.execution_modes import (
    build_execution_mode_surface,
    filter_tool_specs_for_execution_mode,
    normalize_execution_mode,
    resolve_tool_capability_family,
)
from ai_runtime.core.agent_runtime.tools.base import ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.bootstrap import configure_tool_registry
from ai_runtime.core.agent_runtime.tools.registry import ToolRegistry


class _NoopMCPRegistry:
    async def list_catalog_tools(self, **kwargs):
        return []


def test_normalize_execution_mode_defaults_to_context_only():
    mode = normalize_execution_mode({})

    assert mode.name == "context_only"
    assert "project_context" in mode.capabilities
    assert mode.source == "default"


def test_normalize_execution_mode_accepts_runtime_policy_alias():
    mode = normalize_execution_mode({"runtime_policy": {"execution_mode": "sandbox-verified"}})

    assert mode.name == "sandbox_verified"
    assert "sandbox_execute" in mode.capabilities
    assert mode.source == "agent_config"


def test_normalize_execution_mode_rejects_unknown_values():
    mode = normalize_execution_mode({"execution_mode": "host_root_shell"})

    assert mode.name == "context_only"
    assert mode.source == "default_invalid"


def test_resolve_tool_capability_family_maps_core_tool_families():
    assert resolve_tool_capability_family({"kind": "builtin", "metadata": {}}) == "builtin"
    assert resolve_tool_capability_family({"kind": "knowledge", "metadata": {}}) == "knowledge"
    assert resolve_tool_capability_family({"kind": "project-context", "metadata": {}}) == "project_context"
    assert resolve_tool_capability_family({"kind": "workspace", "metadata": {"capability": "workspace", "access_level": "read"}}) == "workspace_read"
    assert resolve_tool_capability_family({"kind": "workspace", "metadata": {"capability": "workspace", "access_level": "write"}}) == "workspace_write"
    assert resolve_tool_capability_family({"kind": "workspace", "metadata": {"capability": "git", "access_level": "read"}}) == "git_read"
    assert resolve_tool_capability_family({"kind": "sandbox-exec", "metadata": {"provider": "sandbox-exec"}}) == "sandbox_execute"
    assert resolve_tool_capability_family({"kind": "web", "metadata": {"provider": "web", "capability": "browser_verify"}}) == "browser_verify"
    assert resolve_tool_capability_family({"kind": "web", "metadata": {"provider": "web", "capability": "web_research"}}) == "web_research"


def test_filter_tool_specs_for_execution_mode_enforces_capability_boundaries():
    tools = [
        {"name": "calculator", "kind": "builtin", "metadata": {}},
        {"name": "project_list_context", "kind": "project-context", "metadata": {"provider": "project-context", "capability": "project_context"}},
        {"name": "workspace_read_file", "kind": "workspace", "metadata": {"provider": "workspace", "capability": "workspace", "access_level": "read"}},
        {"name": "workspace_apply_patch", "kind": "workspace", "metadata": {"provider": "workspace", "capability": "workspace", "access_level": "write"}},
        {"name": "run_tests", "kind": "sandbox-exec", "metadata": {"provider": "sandbox-exec", "capability": "test"}},
        {"name": "web_search", "kind": "web", "metadata": {"provider": "web", "capability": "web_research"}},
    ]

    context_only = filter_tool_specs_for_execution_mode(tools, normalize_execution_mode({"execution_mode": "context_only"}))
    sandbox_verified = filter_tool_specs_for_execution_mode(tools, normalize_execution_mode({"execution_mode": "sandbox_verified"}))

    assert [tool["name"] for tool in context_only] == ["calculator", "project_list_context"]
    assert [tool["name"] for tool in sandbox_verified] == [
        "calculator",
        "project_list_context",
        "workspace_read_file",
        "workspace_apply_patch",
        "run_tests",
    ]


def test_build_execution_mode_surface_reports_blocked_tool_families():
    mode = normalize_execution_mode({"execution_mode": "context_only"})
    tools = [
        {
            "name": "project_list_context",
            "kind": "project-context",
            "metadata": {
                "provider": "project-context",
                "capability": "project_context",
                "execution_mode_allowed": True,
                "execution_mode_capability_family": "project_context",
            },
        },
        {
            "name": "workspace_read_file",
            "kind": "workspace",
            "metadata": {
                "provider": "workspace",
                "capability": "workspace",
                "access_level": "read",
                "execution_mode_allowed": False,
                "execution_mode_capability_family": "workspace_read",
                "execution_mode_block_reason": "blocked by mode",
            },
        },
    ]

    surface = build_execution_mode_surface(tools, mode)

    assert surface["allowed_tool_count"] == 1
    assert surface["blocked_tool_count"] == 1
    assert any(item["key"] == "workspace_read" and item["enabled"] is False for item in surface["capability_details"])
    assert surface["blocked_tools_preview"][0]["name"] == "workspace_read_file"


async def test_bootstrap_keeps_sandbox_exec_hidden_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_TOOL_PROVIDERS", raising=False)
    monkeypatch.delenv("AGENT_SANDBOX_EXEC_ENABLED", raising=False)
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_ENABLED", "false")
    monkeypatch.setenv("AGENT_WORKSPACE_ENABLED", "false")
    registry = ToolRegistry()

    configure_tool_registry(registry, mcp_registry=_NoopMCPRegistry())
    specs = await registry.list_specs(ToolLookupContext(tenant_id="tenant-1"))

    assert all(spec["kind"] != "sandbox-exec" for spec in specs)
