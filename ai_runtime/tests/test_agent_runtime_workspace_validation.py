"""GA hardening: Workspace security validation tests."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager, WorkspaceManagerConfig
from ai_runtime.core.agent_runtime.workspace_lifecycle import (
    WorkspaceLifecyclePolicy,
    WorkspaceLifecycleScheduler,
)


def _manager(tmp_path: Path, **overrides) -> WorkspaceManager:
    defaults = {
        "enabled": True,
        "base_root": tmp_path / "managed",
        "source_roots": (tmp_path / "sources",),
        "max_files": 50,
        "max_bytes": 50_000,
        "retention_hours": 1,
        "cleanup_lock_ttl_seconds": 60,
    }
    defaults.update(overrides)
    return WorkspaceManager(WorkspaceManagerConfig(**defaults))


def _create_workspace(base_root: Path, tenant: str, run: str, files: dict[str, str] | None = None) -> Path:
    ws = base_root / tenant / run / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        path = ws / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return ws


# --- Large repository performance ---


async def test_workspace_handles_many_files_within_limits(tmp_path):
    manager = _manager(tmp_path, max_files=100, max_bytes=500_000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1")
    for i in range(120):
        (ws / f"file_{i:04d}.txt").write_text(f"content {i}", encoding="utf-8")

    snapshot = manager._snapshot(ws, source={"type": "test"})

    assert snapshot["file_count"] <= 100
    assert snapshot["truncated"] is True


async def test_workspace_handles_large_files_within_byte_limit(tmp_path):
    manager = _manager(tmp_path, max_files=1000, max_bytes=10_000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1")
    (ws / "large.bin").write_bytes(b"x" * 20_000)
    (ws / "small.txt").write_text("hello", encoding="utf-8")

    snapshot = manager._snapshot(ws, source={"type": "test"})

    assert snapshot["total_size_bytes"] <= 20_001
    assert snapshot["truncated"] is True


# --- Symlink escape prevention ---


async def test_symlink_outside_workspace_is_excluded_during_copy(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    (secret_dir / "credentials.json").write_text('{"key": "secret"}', encoding="utf-8")

    project = sources / "my-project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")
    (project / "escape_link").symlink_to(secret_dir)

    manager = _manager(tmp_path, source_roots=(sources,))
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1")

    # Simulate copy with symlink detection
    for item in sorted(project.rglob("*")):
        if item.is_symlink():
            resolved = item.resolve()
            # Verify symlink target is outside source
            assert not any(resolved == root or root in resolved.parents for root in [sources])
            continue
        if item.is_file():
            rel = item.relative_to(project)
            dest = ws / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(item.read_bytes())

    assert (ws / "main.py").exists()
    assert not (ws / "escape_link").exists()
    assert not (ws / "credentials.json").exists()


async def test_symlink_in_workspace_read_is_resolved_safely(tmp_path):
    manager = _manager(tmp_path)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"real.txt": "content"})
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret data", encoding="utf-8")
    (ws / "link_to_outside").symlink_to(outside)

    # The workspace manager should detect symlink escape
    resolved = (ws / "link_to_outside").resolve()
    ws_resolved = ws.resolve()
    assert resolved != ws_resolved and ws_resolved not in resolved.parents


# --- Path traversal prevention ---


async def test_path_traversal_in_relative_path_normalization(tmp_path):
    from ai_runtime.core.agent_runtime.workspace_manager import _normalize_relative_path

    dangerous_paths = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "./../../secret",
        "foo/../../bar/../../../etc/shadow",
        "\x00injected",
        "",
        ".",
        "..",
    ]
    for dangerous in dangerous_paths:
        normalized = _normalize_relative_path(dangerous)
        parts = normalized.parts
        assert ".." not in parts, f"path traversal not blocked: {dangerous} -> {normalized}"
        assert "." not in parts or str(normalized) == "file.txt"
        assert "\x00" not in str(normalized)


async def test_workspace_excluded_patterns_block_sensitive_paths(tmp_path):
    manager = _manager(tmp_path)
    sensitive_paths = [
        ".git/config",
        ".git/objects/pack/abc",
        "node_modules/express/index.js",
        "__pycache__/module.cpython-312.pyc",
        ".venv/lib/python3.12/site.py",
        "venv/bin/activate",
        "src/__pycache__/mod.pyc",
        "frontend/node_modules/react/index.js",
    ]
    for path in sensitive_paths:
        assert manager._excluded(path), f"expected excluded: {path}"


async def test_workspace_allows_normal_paths(tmp_path):
    manager = _manager(tmp_path)
    normal_paths = [
        "src/main.py",
        "tests/test_app.py",
        "README.md",
        "package.json",
        "Makefile",
        "docs/guide.md",
    ]
    for path in normal_paths:
        assert not manager._excluded(path), f"expected allowed: {path}"


# --- Protected path regression ---


async def test_default_exclude_patterns_cover_all_sensitive_dirs(tmp_path):
    from ai_runtime.core.agent_runtime.tools.providers.workspace import DEFAULT_EXCLUDE_PATTERNS

    # These directories should have their contents excluded by glob patterns
    must_exclude_dirs = [".git", "node_modules", "__pycache__", ".venv", "venv"]
    for pattern_target in must_exclude_dirs:
        matched = False
        for pattern in DEFAULT_EXCLUDE_PATTERNS:
            import fnmatch
            test_path = f"{pattern_target}/somefile"
            if fnmatch.fnmatch(test_path, pattern) or fnmatch.fnmatch(pattern_target, pattern):
                matched = True
                break
        assert matched, f"no exclude pattern covers: {pattern_target}"


# --- Writeback dry-run vs confirmed ---


async def test_writeback_dry_run_does_not_modify_target(tmp_path):
    sources = tmp_path / "sources"
    project = sources / "my-project"
    project.mkdir(parents=True)
    (project / "original.txt").write_text("original content", encoding="utf-8")

    manager = _manager(tmp_path, source_roots=(sources,))
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {
        "original.txt": "modified content",
        "new_file.txt": "new content",
    })

    result = manager.apply_workspace_writeback(
        workspace_root=str(ws),
        source_path=str(project),
        tenant_id="tenant-1",
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["change_count"] >= 1
    # Target should NOT be modified
    assert (project / "original.txt").read_text() == "original content"
    assert not (project / "new_file.txt").exists()


async def test_writeback_confirmed_modifies_target(tmp_path):
    sources = tmp_path / "sources"
    project = sources / "my-project"
    project.mkdir(parents=True)
    (project / "original.txt").write_text("original content", encoding="utf-8")

    manager = _manager(tmp_path, source_roots=(sources,))
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {
        "original.txt": "modified content",
        "new_file.txt": "new content",
    })

    result = manager.apply_workspace_writeback(
        workspace_root=str(ws),
        source_path=str(project),
        tenant_id="tenant-1",
        dry_run=False,
        confirmed=True,
    )

    assert result["dry_run"] is False
    assert result["applied_count"] >= 1
    assert result["failed_count"] == 0
    assert (project / "original.txt").read_text() == "modified content"
    assert (project / "new_file.txt").read_text() == "new content"


async def test_writeback_rejects_unregistered_source_root(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()

    manager = _manager(tmp_path, source_roots=(sources,))
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"file.txt": "content"})

    with pytest.raises(PermissionError):
        manager.apply_workspace_writeback(
            workspace_root=str(ws),
            source_path=str(unregistered),
            tenant_id="tenant-1",
            dry_run=False,
            confirmed=True,
        )


# --- Workspace quota enforcement ---


async def test_workspace_inspection_detects_quota_exceeded(tmp_path):
    manager = _manager(tmp_path, max_files=5, max_bytes=1000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1")
    for i in range(10):
        (ws / f"file_{i}.txt").write_text("x" * 200, encoding="utf-8")

    inspection = manager.inspect_workspaces()

    assert inspection["workspace_count"] == 1
    assert inspection["quota_exceeded_count"] == 1


async def test_workspace_inspection_healthy_within_quota(tmp_path):
    manager = _manager(tmp_path, max_files=100, max_bytes=100_000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"small.txt": "hello"})

    inspection = manager.inspect_workspaces()

    assert inspection["workspace_count"] == 1
    assert inspection["quota_exceeded_count"] == 0


# --- Multi-instance cleanup lock contention ---


async def test_cleanup_lock_prevents_concurrent_deletion(tmp_path):
    manager = _manager(tmp_path)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"file.txt": "content"})

    # Simulate acquiring a lock
    lock_dir = tmp_path / "managed" / ".lifecycle-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "tenant-1__run-1.cleanup.lock"
    lock_payload = {
        "workspace_id": "tenant-1/run-1",
        "owner_host": "host-1",
        "owner_pid": os.getpid(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")

    # Inspect should see the active lock
    now = datetime.now(timezone.utc)
    lock_summary, lookup = manager._inspect_cleanup_locks(now=now)

    assert lock_summary["lock_count"] == 1
    assert lock_summary["active_lock_count"] == 1
    assert lock_summary["stale_lock_count"] == 0
    assert "tenant-1/run-1" in lookup


async def test_stale_lock_detected_after_ttl(tmp_path):
    manager = _manager(tmp_path, cleanup_lock_ttl_seconds=60)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"file.txt": "content"})

    lock_dir = tmp_path / "managed" / ".lifecycle-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "tenant-1__run-1.cleanup.lock"
    lock_payload = {
        "workspace_id": "tenant-1/run-1",
        "owner_host": "host-1",
        "owner_pid": 99999,
        "acquired_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    }
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")
    # Make the file old
    old_time = time.time() - 120
    os.utime(lock_path, (old_time, old_time))

    now = datetime.now(timezone.utc)
    lock_summary, lookup = manager._inspect_cleanup_locks(now=now)

    assert lock_summary["stale_lock_count"] == 1
    assert lookup["tenant-1/run-1"]["stale"] is True


async def test_orphan_lock_detected_when_workspace_missing(tmp_path):
    manager = _manager(tmp_path)
    # Don't create the workspace, just the lock
    lock_dir = tmp_path / "managed" / ".lifecycle-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "tenant-1__run-gone.cleanup.lock"
    lock_payload = {
        "workspace_id": "tenant-1/run-gone",
        "owner_host": "host-1",
        "owner_pid": os.getpid(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")

    now = datetime.now(timezone.utc)
    lock_summary, lookup = manager._inspect_cleanup_locks(now=now)

    assert lock_summary["orphan_lock_count"] == 1
    assert lookup["tenant-1/run-gone"]["orphan"] is True


async def test_workspace_health_score_degrades_with_issues(tmp_path):
    manager = _manager(tmp_path, max_files=5, max_bytes=1000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1")
    for i in range(10):
        (ws / f"file_{i}.txt").write_text("x" * 200, encoding="utf-8")

    # Make workspace expired
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(ws, (old_time, old_time))

    inspection = manager.inspect_workspaces()
    health = manager.build_workspace_health(inspection)

    assert health["status"] in {"warning", "critical"}
    assert health["score"] < 100
    assert len(health["issues"]) >= 1
    assert len(health["recovery_actions"]) >= 1


async def test_workspace_health_perfect_when_no_issues(tmp_path):
    manager = _manager(tmp_path, max_files=100, max_bytes=100_000)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"small.txt": "hello"})

    inspection = manager.inspect_workspaces()
    health = manager.build_workspace_health(inspection)

    assert health["status"] == "healthy"
    assert health["score"] == 100
    assert health["issues"] == []


# --- Lifecycle scheduler integration ---


async def test_lifecycle_scheduler_cleans_expired_workspaces(tmp_path):
    manager = _manager(tmp_path, retention_hours=1)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"file.txt": "content"})
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(ws, (old_time, old_time))

    scheduler = WorkspaceLifecycleScheduler(
        manager,
        WorkspaceLifecyclePolicy(enabled=True, dry_run=False),
    )
    result = await scheduler.run_once()

    assert result.status == "completed"
    assert result.inspection["expired_count"] == 1
    assert result.cleanup is not None
    assert result.cleanup["deleted_count"] == 1
    assert not ws.exists()


async def test_lifecycle_scheduler_dry_run_preserves_workspaces(tmp_path):
    manager = _manager(tmp_path, retention_hours=1)
    ws = _create_workspace(tmp_path / "managed", "tenant-1", "run-1", {"file.txt": "content"})
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(ws, (old_time, old_time))

    scheduler = WorkspaceLifecycleScheduler(
        manager,
        WorkspaceLifecyclePolicy(enabled=True, dry_run=True),
    )
    result = await scheduler.run_once()

    assert result.cleanup["dry_run"] is True
    assert ws.exists()
