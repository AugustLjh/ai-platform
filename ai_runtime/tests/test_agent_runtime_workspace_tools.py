from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.workspace import WorkspaceToolProvider


def _context(workspace_root: Path) -> ToolContext:
    return ToolContext(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        workspace_root=str(workspace_root),
    )


async def test_workspace_provider_hides_tools_without_configured_workspace(tmp_path):
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_list_files"], roots=[])

    specs = await provider.list_specs(
        ToolLookupContext(
            tenant_id="tenant-1",
            workspace_root=str(tmp_path),
        )
    )

    assert specs == []
    assert await provider.get("workspace_list_files", context=None) is None


async def test_workspace_read_rejects_path_traversal_and_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "safe.txt").write_text("safe content", encoding="utf-8")
    (outside / "secret.txt").write_text("do not read", encoding="utf-8")
    os.symlink(outside / "secret.txt", workspace / "secret-link.txt")
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_read_file"], roots=[workspace])
    tool = await provider.get("workspace_read_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"path": "safe.txt"})
    assert result["content"] == "safe content"

    try:
        await tool.execute(_context(workspace), {"path": "../outside/secret.txt"})
    except PermissionError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected traversal outside workspace to be rejected")

    try:
        await tool.execute(_context(workspace), {"path": "secret-link.txt"})
    except PermissionError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected symlink outside workspace to be rejected")


async def test_workspace_list_search_and_read_are_bounded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("alpha\nneedle is here\n", encoding="utf-8")
    (workspace / "large.txt").write_text("x" * 1200, encoding="utf-8")
    provider = WorkspaceToolProvider(
        enabled_tool_names=["workspace_list_files", "workspace_search_text", "workspace_read_file"],
        roots=[workspace],
    )

    list_tool = await provider.get("workspace_list_files", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    search_tool = await provider.get("workspace_search_text", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    read_tool = await provider.get("workspace_read_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert list_tool is not None and search_tool is not None and read_tool is not None

    listing = await list_tool.execute(_context(workspace), {"recursive": True, "max_entries": 2})
    assert len(listing["entries"]) == 2
    assert listing["truncated"] is True

    search = await search_tool.execute(_context(workspace), {"query": "needle"})
    assert search["matches"][0]["path"] == "src/app.py"
    assert search["matches"][0]["line"] == 2

    read = await read_tool.execute(_context(workspace), {"path": "large.txt", "max_chars": 100})
    assert len(read["content"]) == 100
    assert read["truncated"] is True


async def test_workspace_git_tools_are_read_only_and_bounded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True)
    (workspace / "app.py").write_text("print('v1')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "app.py").write_text("print('v2')\n", encoding="utf-8")
    provider = WorkspaceToolProvider(enabled_tool_names=["git_status", "git_diff", "git_log"], roots=[workspace])

    status_tool = await provider.get("git_status", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    diff_tool = await provider.get("git_diff", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    log_tool = await provider.get("git_log", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert status_tool is not None and diff_tool is not None and log_tool is not None

    status = await status_tool.execute(_context(workspace), {})
    assert status["exit_code"] == 0
    assert "M app.py" in status["stdout"]

    diff = await diff_tool.execute(_context(workspace), {"max_chars": 500})
    assert diff["exit_code"] == 0
    assert "print('v2')" in diff["stdout"]

    truncated_diff = await diff_tool.execute(_context(workspace), {"max_chars": 120})
    assert truncated_diff["truncated"] is True

    log = await log_tool.execute(_context(workspace), {"limit": 1})
    assert log["exit_code"] == 0
    assert "initial" in log["stdout"]


async def test_workspace_specs_include_policy_metadata(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_read_file", "git_diff"], roots=[workspace])

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))

    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}
    assert metadata_by_name["workspace_read_file"]["requires_workspace"] is True
    assert metadata_by_name["workspace_read_file"]["access_level"] == "read"
    assert metadata_by_name["git_diff"]["capability"] == "git"
    assert metadata_by_name["git_diff"]["side_effect"] == "none"
