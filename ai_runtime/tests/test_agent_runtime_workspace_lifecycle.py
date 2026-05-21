from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_runtime.core.agent_runtime.memory import RuntimeStateStore
from ai_runtime.core.agent_runtime.workspace_lifecycle import (
    WorkspaceLifecyclePolicy,
    WorkspaceLifecycleScheduler,
)
from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager, WorkspaceManagerConfig


def _manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(
        WorkspaceManagerConfig(
            enabled=True,
            base_root=tmp_path / "managed",
            source_roots=(),
            max_files=10,
            max_bytes=10_000,
            retention_hours=1,
        )
    )


async def test_workspace_lifecycle_scheduler_runs_inspection_and_cleanup(tmp_path):
    manager = _manager(tmp_path)
    workspace = tmp_path / "managed" / "tenant-1" / "run-1" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "old.txt").write_text("old", encoding="utf-8")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    workspace.touch()
    timestamp = old_time.timestamp()
    os.utime(workspace, (timestamp, timestamp))

    alerts: list[dict] = []
    inspections: list[dict] = []

    async def alert_callback(payload: dict) -> None:
        alerts.append(payload)

    async def inspection_callback(payload: dict) -> None:
        inspections.append(payload)

    scheduler = WorkspaceLifecycleScheduler(
        manager,
        WorkspaceLifecyclePolicy(
            enabled=True,
            dry_run=True,
            expired_alert_threshold=1,
            quota_alert_threshold_count=1,
            quota_alert_threshold_bytes=1,
        ),
        alert_callback=alert_callback,
        inspection_callback=inspection_callback,
    )

    result = await scheduler.run_once(now=datetime.now(timezone.utc))

    assert result.inspection["workspace_count"] == 1
    assert result.inspection["expired_count"] == 1
    assert result.cleanup["dry_run"] is True
    assert result.cleanup["candidate_count"] == 1
    assert result.generated_at
    assert scheduler.last_completed_at == result.generated_at
    assert alerts
    assert inspections
    assert inspections[0]["generated_at"] == result.generated_at


async def test_workspace_lifecycle_scheduler_stop_is_idempotent(tmp_path):
    scheduler = WorkspaceLifecycleScheduler(_manager(tmp_path), WorkspaceLifecyclePolicy(enabled=False))

    await scheduler.start()
    await scheduler.stop()
    await scheduler.stop()

    assert scheduler.running is False


async def test_runtime_state_store_close_all_cancels_tasks():
    store = RuntimeStateStore()
    task = __import__("asyncio").create_task(__import__("asyncio").sleep(0.01))
    store.register_task("run-1", task)

    await store.close_all()

    assert store.get_task("run-1") is None
