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
        enabled_tool_names=[
            "workspace_list_files",
            "workspace_search_text",
            "workspace_read_file",
            "workspace_file_info",
            "workspace_tree",
        ],
        roots=[workspace],
    )

    list_tool = await provider.get("workspace_list_files", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    search_tool = await provider.get("workspace_search_text", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    read_tool = await provider.get("workspace_read_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    info_tool = await provider.get("workspace_file_info", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    tree_tool = await provider.get("workspace_tree", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert list_tool is not None and search_tool is not None and read_tool is not None and info_tool is not None and tree_tool is not None

    listing = await list_tool.execute(_context(workspace), {"recursive": True, "max_entries": 2})
    assert len(listing["entries"]) == 2
    assert listing["truncated"] is True

    search = await search_tool.execute(_context(workspace), {"query": "needle"})
    assert search["matches"][0]["path"] == "src/app.py"
    assert search["matches"][0]["line"] == 2

    read = await read_tool.execute(_context(workspace), {"path": "large.txt", "max_chars": 100})
    assert len(read["content"]) == 100
    assert read["truncated"] is True

    info = await info_tool.execute(_context(workspace), {"path": "src/app.py", "include_hash": True})
    assert info["type"] == "file"
    assert info["sha256"]

    tree = await tree_tool.execute(_context(workspace), {"max_depth": 2, "max_entries": 10})
    assert any(entry["path"] == "src/app.py" for entry in tree["entries"])


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
    provider = WorkspaceToolProvider(enabled_tool_names=["git_status", "git_diff", "git_log", "git_branch"], roots=[workspace])

    status_tool = await provider.get("git_status", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    diff_tool = await provider.get("git_diff", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    log_tool = await provider.get("git_log", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    branch_tool = await provider.get("git_branch", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert status_tool is not None and diff_tool is not None and log_tool is not None and branch_tool is not None

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

    branch = await branch_tool.execute(_context(workspace), {})
    assert branch["exit_code"] == 0
    assert "master" in branch["stdout"] or "main" in branch["stdout"]


async def test_workspace_specs_include_policy_metadata(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_read_file", "workspace_apply_patch", "git_diff"], roots=[workspace])

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))

    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}
    assert metadata_by_name["workspace_read_file"]["requires_workspace"] is True
    assert metadata_by_name["workspace_read_file"]["access_level"] == "read"
    assert metadata_by_name["workspace_apply_patch"]["access_level"] == "write"
    assert metadata_by_name["workspace_apply_patch"]["side_effect"] == "workspace_write"
    assert metadata_by_name["workspace_apply_patch"]["risk_level"] == "medium"
    assert metadata_by_name["git_diff"]["capability"] == "git"
    assert metadata_by_name["git_diff"]["side_effect"] == "none"


async def test_default_workspace_tool_set_covers_internal_alpha_mvp(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.delenv("AGENT_WORKSPACE_TOOLS", raising=False)
    monkeypatch.delenv("AGENT_WORKSPACE_ROOTS", raising=False)
    provider = WorkspaceToolProvider.from_env()
    provider.policy = provider.policy.__class__(roots=(workspace,))

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    names = {spec["name"] for spec in specs}

    assert {
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
    }.issubset(names)


async def test_workspace_apply_patch_uses_hash_guard_and_dry_run(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("print('v1')\n", encoding="utf-8")
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_file_info", "workspace_apply_patch"], roots=[workspace])
    info_tool = await provider.get("workspace_file_info", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    patch_tool = await provider.get("workspace_apply_patch", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert info_tool is not None and patch_tool is not None

    info = await info_tool.execute(_context(workspace), {"path": "app.py", "include_hash": True})
    dry_run = await patch_tool.execute(
        _context(workspace),
        {
            "path": "app.py",
            "content": "print('v2')\n",
            "expected_sha256": info["sha256"],
            "dry_run": True,
        },
    )

    assert dry_run["status"] == "dry_run"
    assert dry_run["changed"] is True
    assert "print('v2')" in dry_run["diff"]
    assert dry_run["artifacts"][0]["artifact_type"] == "code_patch"
    assert target.read_text(encoding="utf-8") == "print('v1')\n"

    target.write_text("print('changed')\n", encoding="utf-8")
    try:
        await patch_tool.execute(
            _context(workspace),
            {"path": "app.py", "content": "print('v3')\n", "expected_sha256": info["sha256"]},
        )
    except ValueError as exc:
        assert "expected_sha256" in str(exc)
    else:
        raise AssertionError("expected stale hash write to be rejected")


async def test_workspace_write_tools_create_and_modify_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_create_file", "workspace_write_file"], roots=[workspace])
    create_tool = await provider.get("workspace_create_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    write_tool = await provider.get("workspace_write_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert create_tool is not None and write_tool is not None

    created = await create_tool.execute(_context(workspace), {"path": "src/new.py", "content": "value = 1\n"})
    assert created["operation"] == "create"
    assert (workspace / "src" / "new.py").read_text(encoding="utf-8") == "value = 1\n"
    assert "--- a/src/new.py" in created["diff"]

    modified = await write_tool.execute(_context(workspace), {"path": "src/new.py", "content": "value = 2\n"})
    assert modified["operation"] == "modify"
    assert modified["changed"] is True
    assert (workspace / "src" / "new.py").read_text(encoding="utf-8") == "value = 2\n"

    created_by_write = await write_tool.execute(_context(workspace), {"path": "src/other.py", "content": "x = 1\n", "create": True})
    assert created_by_write["operation"] == "create"
    assert (workspace / "src" / "other.py").exists()


async def test_workspace_write_tools_reject_escape_excluded_and_protected_files(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (workspace / "node_modules").mkdir()
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_create_file", "workspace_apply_patch"], roots=[workspace])
    create_tool = await provider.get("workspace_create_file", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    patch_tool = await provider.get("workspace_apply_patch", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert create_tool is not None and patch_tool is not None

    try:
        await create_tool.execute(_context(workspace), {"path": "../outside/new.txt", "content": "x"})
    except PermissionError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected traversal outside workspace to be rejected")

    try:
        await create_tool.execute(_context(workspace), {"path": "node_modules/pkg.js", "content": "x"})
    except PermissionError as exc:
        assert "excluded" in str(exc)
    else:
        raise AssertionError("expected excluded path write to be rejected")

    try:
        await patch_tool.execute(_context(workspace), {"path": ".env", "content": "SECRET=2\n"})
    except PermissionError as exc:
        assert "protected" in str(exc)
    else:
        raise AssertionError("expected protected file write to be rejected")


async def test_workspace_rename_path_uses_hash_guard_and_patch_artifact(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    source = workspace / "src" / "old.py"
    source.write_text("value = 1\n", encoding="utf-8")
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_file_info", "workspace_rename_path"], roots=[workspace])
    info_tool = await provider.get("workspace_file_info", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    rename_tool = await provider.get("workspace_rename_path", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert info_tool is not None and rename_tool is not None

    info = await info_tool.execute(_context(workspace), {"path": "src/old.py", "include_hash": True})
    dry_run = await rename_tool.execute(
        _context(workspace),
        {
            "source_path": "src/old.py",
            "target_path": "src/new.py",
            "expected_sha256": info["sha256"],
            "dry_run": True,
        },
    )

    assert dry_run["status"] == "dry_run"
    assert dry_run["operation"] == "rename"
    assert (workspace / "src" / "old.py").exists()
    assert not (workspace / "src" / "new.py").exists()
    assert dry_run["artifacts"][0]["payload"]["merge_policy"] == "manual_review_required"
    assert {file["operation"] for file in dry_run["artifacts"][0]["payload"]["files"]} == {"create", "delete"}

    source.write_text("value = 2\n", encoding="utf-8")
    try:
        await rename_tool.execute(
            _context(workspace),
            {"source_path": "src/old.py", "target_path": "src/new.py", "expected_sha256": info["sha256"]},
        )
    except ValueError as exc:
        assert "expected_sha256" in str(exc)
    else:
        raise AssertionError("expected stale hash rename to be rejected")


async def test_workspace_delete_path_is_file_only_and_reviewable(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "obsolete.py"
    target.write_text("value = 1\n", encoding="utf-8")
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    provider = WorkspaceToolProvider(enabled_tool_names=["workspace_delete_path"], roots=[workspace])
    delete_tool = await provider.get("workspace_delete_path", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert delete_tool is not None

    preview = await delete_tool.execute(_context(workspace), {"path": "obsolete.py", "dry_run": True})
    assert preview["status"] == "dry_run"
    assert target.exists()
    assert "-value = 1" in preview["diff"]
    assert preview["artifacts"][0]["payload"]["review_notes"]

    applied = await delete_tool.execute(_context(workspace), {"path": "obsolete.py"})
    assert applied["status"] == "applied"
    assert not target.exists()

    try:
        await delete_tool.execute(_context(workspace), {"path": ".env"})
    except PermissionError as exc:
        assert "protected" in str(exc)
    else:
        raise AssertionError("expected protected file delete to be rejected")
