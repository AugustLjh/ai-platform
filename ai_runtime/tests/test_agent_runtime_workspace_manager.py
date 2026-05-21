from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager, WorkspaceManagerConfig


def _manager(tmp_path: Path, *, source_roots=()) -> WorkspaceManager:
    return WorkspaceManager(
        WorkspaceManagerConfig(
            enabled=True,
            base_root=tmp_path / "workspaces",
            source_roots=tuple(Path(root).resolve() for root in source_roots),
            max_files=20,
            max_bytes=100_000,
            retention_hours=1,
        )
    )


def test_workspace_manager_binds_existing_workspace_under_source_root(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    project.mkdir(parents=True)
    (project / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])

    context, events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"workspace_root": str(project)},
        existing_context={},
    )

    workspace_root = Path(context["workspace_root"])
    assert workspace_root != project.resolve()
    assert context["workspace"]["source"]["type"] == "existing"
    assert context["workspace"]["source"]["binding"] == "copied"
    assert context["workspace"]["snapshot"]["file_count"] == 1
    assert (workspace_root / "app.py").read_text(encoding="utf-8") == "print('ok')\n"
    assert (workspace_root / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert events[0]["event_type"] == "workspace.bound"


def test_workspace_manager_rejects_existing_workspace_outside_source_roots(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    manager = _manager(tmp_path, source_roots=[tmp_path / "allowed"])

    with pytest.raises(PermissionError):
        manager.ensure_workspace_context(
            run_id="run-1",
            tenant_id="tenant-1",
            user_id="user-1",
            run_input={"workspace_root": str(outside)},
            existing_context={},
        )


def test_workspace_manager_copies_local_path_into_run_workspace(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('copied')\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("skip", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])

    context, _events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"workspace_source": {"type": "local_path", "root": str(project)}},
        existing_context={},
    )

    workspace_root = Path(context["workspace_root"])
    assert workspace_root != project.resolve()
    assert (workspace_root / "src" / "app.py").read_text(encoding="utf-8") == "print('copied')\n"
    assert (workspace_root / ".git" / "config").read_text(encoding="utf-8") == "skip"
    assert context["workspace"]["materialized"]["copied_files"] == 2


def test_workspace_manager_uses_agent_default_workspace_when_run_has_no_explicit_source(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    project.mkdir(parents=True)
    (project / "app.py").write_text("print('default')\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])

    context, events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"message": "inspect this project"},
        agent_config={
            "workspace": {
                "default_source": {
                    "enabled": True,
                    "type": "existing",
                    "path": str(project),
                }
            }
        },
        existing_context={},
    )

    workspace_root = Path(context["workspace_root"])
    assert workspace_root != project.resolve()
    assert (workspace_root / "app.py").read_text(encoding="utf-8") == "print('default')\n"
    assert context["workspace"]["source"]["configured_default"] is True
    assert events[0]["event_type"] == "workspace.bound"


def test_workspace_manager_prefers_explicit_run_workspace_over_agent_default(tmp_path):
    source_root = tmp_path / "sources"
    default_project = source_root / "default"
    explicit_project = source_root / "explicit"
    default_project.mkdir(parents=True)
    explicit_project.mkdir()
    (default_project / "app.py").write_text("print('default')\n", encoding="utf-8")
    (explicit_project / "app.py").write_text("print('explicit')\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])

    context, _events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"workspace_source": {"type": "existing", "path": str(explicit_project)}},
        agent_config={
            "workspace": {
                "default_source": {
                    "enabled": True,
                    "type": "existing",
                    "path": str(default_project),
                }
            }
        },
        existing_context={},
    )

    workspace_root = Path(context["workspace_root"])
    assert (workspace_root / "app.py").read_text(encoding="utf-8") == "print('explicit')\n"
    assert context["workspace"]["source"].get("configured_default") is None


def test_workspace_manager_inspects_workspace_lifecycle_and_quota(tmp_path):
    manager = _manager(tmp_path)
    workspace = tmp_path / "workspaces" / "tenant-1" / "run-1" / "workspace"
    workspace.mkdir(parents=True)
    for index in range(21):
        (workspace / f"file-{index}.txt").write_text("x", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(workspace, (old_time.timestamp(), old_time.timestamp()))

    result = manager.inspect_workspaces(now=datetime.now(timezone.utc))

    assert result["workspace_count"] == 1
    assert result["expired_count"] == 1
    assert result["quota_exceeded_count"] == 1
    item = result["workspaces"][0]
    assert item["workspace_id"] == "tenant-1/run-1"
    assert item["expired"] is True
    assert item["quota_exceeded"] is True


def test_workspace_manager_cleanup_expired_workspaces_supports_dry_run_and_delete(tmp_path):
    manager = _manager(tmp_path)
    workspace = tmp_path / "workspaces" / "tenant-1" / "run-1" / "workspace"
    other_workspace = tmp_path / "workspaces" / "tenant-2" / "run-2" / "workspace"
    workspace.mkdir(parents=True)
    other_workspace.mkdir(parents=True)
    (workspace / "old.txt").write_text("old", encoding="utf-8")
    (other_workspace / "old.txt").write_text("old", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(workspace, (old_time.timestamp(), old_time.timestamp()))
    os.utime(other_workspace, (old_time.timestamp(), old_time.timestamp()))

    dry_run = manager.cleanup_expired_workspaces(now=datetime.now(timezone.utc), dry_run=True, tenant_id="tenant-1")
    deleted = manager.cleanup_expired_workspaces(now=datetime.now(timezone.utc), dry_run=False, tenant_id="tenant-1")

    assert dry_run["candidate_count"] == 1
    assert dry_run["deleted"][0]["deleted"] is False
    assert deleted["deleted_count"] == 1
    assert not workspace.exists()
    assert other_workspace.exists()


def test_workspace_manager_cleanup_skips_workspace_with_active_lock(tmp_path):
    manager = _manager(tmp_path)
    workspace = tmp_path / "workspaces" / "tenant-1" / "run-locked" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "old.txt").write_text("old", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(workspace, (old_time.timestamp(), old_time.timestamp()))
    lock_path = manager._cleanup_lock_path("tenant-1/run-locked")
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("locked", encoding="utf-8")

    result = manager.cleanup_expired_workspaces(now=datetime.now(timezone.utc), dry_run=False, tenant_id="tenant-1")

    assert result["candidate_count"] == 1
    assert result["deleted_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "cleanup_lock_held"
    assert workspace.exists()


def test_workspace_manager_inspection_includes_lock_summary_and_health(tmp_path):
    manager = _manager(tmp_path)
    workspace = tmp_path / "workspaces" / "tenant-1" / "run-1" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "old.txt").write_text("old", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(workspace, (old_time.timestamp(), old_time.timestamp()))
    lock_path = manager._cleanup_lock_path("tenant-1/run-1")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        '{"workspace_id":"tenant-1/run-1","owner_host":"test-host","owner_pid":123,"acquired_at":"2026-05-16T00:00:00+00:00","expires_at":"2026-05-16T00:00:01+00:00"}',
        encoding="utf-8",
    )

    result = manager.inspect_workspaces(now=datetime.now(timezone.utc))

    assert result["lock_summary"]["lock_count"] == 1
    assert result["lock_summary"]["stale_lock_count"] == 1
    assert result["health"]["status"] in {"warning", "critical"}
    assert result["health"]["recovery_actions"]
    assert result["workspaces"][0]["cleanup_lock"]["workspace_id"] == "tenant-1/run-1"


def test_workspace_manager_cleanup_stale_locks_supports_dry_run_and_delete(tmp_path):
    manager = _manager(tmp_path)
    lock_path = manager._cleanup_lock_path("tenant-1/run-1")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        '{"workspace_id":"tenant-1/run-1","owner_host":"test-host","owner_pid":123,"acquired_at":"2026-05-16T00:00:00+00:00","expires_at":"2026-05-16T00:00:01+00:00"}',
        encoding="utf-8",
    )

    dry_run = manager.cleanup_stale_locks(now=datetime.now(timezone.utc), dry_run=True, tenant_id="tenant-1")
    deleted = manager.cleanup_stale_locks(now=datetime.now(timezone.utc), dry_run=False, tenant_id="tenant-1")

    assert dry_run["candidate_count"] == 1
    assert dry_run["deleted"][0]["deleted"] is False
    assert deleted["deleted_count"] == 1
    assert not lock_path.exists()


def test_workspace_manager_lists_available_sources(tmp_path):
    source_root = tmp_path / "sources"
    source_root.mkdir(parents=True)
    project_a = source_root / "project-a"
    project_b = source_root / "project-b"
    nested = project_a / "packages" / "api"
    nested.mkdir(parents=True)
    project_b.mkdir()
    (project_a / ".git").mkdir()
    manager = _manager(tmp_path, source_roots=[source_root])

    result = manager.list_available_sources(max_entries=20, max_depth=2)

    paths = {item["path"] for item in result["sources"]}
    assert str(source_root.resolve()) in paths
    assert str(project_a.resolve()) in paths
    assert str(project_b.resolve()) in paths
    assert str(nested.resolve()) not in paths
    project_a_item = next(item for item in result["sources"] if item["path"] == str(project_a.resolve()))
    assert project_a_item["is_git_repo"] is True


def test_workspace_manager_previews_and_applies_workspace_writeback(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    project.mkdir(parents=True)
    (project / "app.py").write_text("print('old')\n", encoding="utf-8")
    (project / "remove.txt").write_text("remove me\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])
    context, _events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"workspace_root": str(project)},
        existing_context={},
    )
    workspace_root = Path(context["workspace_root"])
    (workspace_root / "app.py").write_text("print('new')\n", encoding="utf-8")
    (workspace_root / "created.txt").write_text("created\n", encoding="utf-8")
    (workspace_root / "remove.txt").unlink()

    preview = manager.apply_workspace_writeback(
        workspace_root=str(workspace_root),
        source_path=str(project),
        tenant_id="tenant-1",
        dry_run=True,
    )
    assert (project / "app.py").read_text(encoding="utf-8") == "print('old')\n"
    assert not (project / "created.txt").exists()
    assert (project / "remove.txt").exists()

    applied = manager.apply_workspace_writeback(
        workspace_root=str(workspace_root),
        source_path=str(project),
        tenant_id="tenant-1",
        dry_run=False,
        confirmed=True,
    )

    assert preview["status"] == "dry_run"
    assert preview["change_count"] == 3
    assert "app.py" in preview["diff"]
    assert (project / "app.py").read_text(encoding="utf-8") == "print('new')\n"
    assert (project / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert not (project / "remove.txt").exists()
    assert applied["status"] == "completed"
    assert applied["applied_count"] == 3


def test_workspace_manager_writeback_requires_confirmation(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    project.mkdir(parents=True)
    (project / "app.py").write_text("old\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])
    context, _events = manager.ensure_workspace_context(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_input={"workspace_root": str(project)},
        existing_context={},
    )
    workspace_root = Path(context["workspace_root"])
    (workspace_root / "app.py").write_text("new\n", encoding="utf-8")

    with pytest.raises(ValueError):
        manager.apply_workspace_writeback(
            workspace_root=str(workspace_root),
            source_path=str(project),
            tenant_id="tenant-1",
            dry_run=False,
            confirmed=False,
        )

    assert (project / "app.py").read_text(encoding="utf-8") == "old\n"


def test_workspace_manager_writeback_rejects_unmanaged_workspace(tmp_path):
    source_root = tmp_path / "sources"
    project = source_root / "project"
    rogue_workspace = tmp_path / "rogue"
    project.mkdir(parents=True)
    rogue_workspace.mkdir()
    (project / "app.py").write_text("old\n", encoding="utf-8")
    (rogue_workspace / "app.py").write_text("new\n", encoding="utf-8")
    manager = _manager(tmp_path, source_roots=[source_root])

    with pytest.raises(PermissionError):
        manager.apply_workspace_writeback(
            workspace_root=str(rogue_workspace),
            source_path=str(project),
            tenant_id="tenant-1",
            dry_run=True,
        )

    assert (project / "app.py").read_text(encoding="utf-8") == "old\n"
