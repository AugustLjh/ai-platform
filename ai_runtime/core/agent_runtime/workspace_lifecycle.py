"""Workspace lifecycle scheduler: background cleanup, quota enforcement, alerting hooks."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Sequence

from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager, WorkspaceManagerConfig

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 86400


@dataclass(frozen=True)
class WorkspaceLifecyclePolicy:
    enabled: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    dry_run: bool = False
    max_delete_per_cycle: int = 100
    quota_alert_threshold_bytes: int = 500 * 1024 * 1024
    quota_alert_threshold_count: int = 200
    expired_alert_threshold: int = 20

    def normalized(self) -> "WorkspaceLifecyclePolicy":
        return WorkspaceLifecyclePolicy(
            enabled=self.enabled,
            interval_seconds=max(MIN_INTERVAL_SECONDS, min(int(self.interval_seconds), MAX_INTERVAL_SECONDS)),
            dry_run=self.dry_run,
            max_delete_per_cycle=max(1, int(self.max_delete_per_cycle)),
            quota_alert_threshold_bytes=max(1, int(self.quota_alert_threshold_bytes)),
            quota_alert_threshold_count=max(1, int(self.quota_alert_threshold_count)),
            expired_alert_threshold=max(1, int(self.expired_alert_threshold)),
        )


AlertCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
InspectionCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass
class WorkspaceLifecycleRun:
    status: str
    inspection: dict[str, Any]
    cleanup: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkspaceLifecycleScheduler:
    def __init__(
        self,
        manager: WorkspaceManager,
        policy: WorkspaceLifecyclePolicy | None = None,
        *,
        alert_callback: AlertCallback | None = None,
        inspection_callback: InspectionCallback | None = None,
    ) -> None:
        self.manager = manager
        self.policy = (policy or WorkspaceLifecyclePolicy()).normalized()
        self.alert_callback = alert_callback
        self.inspection_callback = inspection_callback
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._last_run_at: float | None = None
        self._last_completed_at: str | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_run_at(self) -> float | None:
        return self._last_run_at

    @property
    def last_completed_at(self) -> str | None:
        return self._last_completed_at

    async def start(self) -> None:
        if not self.policy.enabled:
            return
        async with self._lock:
            if self.running:
                return
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._run_loop(), name="workspace-lifecycle-scheduler")

    async def stop(self) -> None:
        async with self._lock:
            task = self._task
            self._task = None
            self._stop_event.set()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run_once(self, *, now: datetime | None = None) -> WorkspaceLifecycleRun:
        inspection = self.manager.inspect_workspaces(now=now)
        alerts = await self._emit_alerts(inspection)
        cleanup: dict[str, Any] | None = None
        if inspection.get("expired_count", 0) or inspection.get("quota_exceeded_count", 0):
            cleanup = self.manager.cleanup_expired_workspaces(
                now=now,
                dry_run=self.policy.dry_run,
                max_delete=self.policy.max_delete_per_cycle,
            )
        self._last_run_at = time.monotonic()
        generated_at = datetime.now(timezone.utc).isoformat()
        self._last_completed_at = generated_at
        if self.inspection_callback is not None:
            await self._maybe_await(
                self.inspection_callback(
                    {
                        "inspection": inspection,
                        "cleanup": cleanup,
                        "alerts": alerts,
                        "generated_at": generated_at,
                    }
                )
            )
        return WorkspaceLifecycleRun(
            status="completed" if not cleanup or cleanup.get("failed_count", 0) == 0 else "partial",
            inspection=inspection,
            cleanup=cleanup,
            alerts=alerts,
            generated_at=generated_at,
        )

    async def _emit_alerts(self, inspection: dict[str, Any]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if inspection.get("expired_count", 0) >= self.policy.expired_alert_threshold:
            alerts.append(
                {
                    "type": "expired_workspaces",
                    "severity": "warning",
                    "message": "Expired workspace count exceeds threshold",
                    "count": inspection.get("expired_count", 0),
                    "threshold": self.policy.expired_alert_threshold,
                }
            )
        if inspection.get("quota_exceeded_count", 0) >= self.policy.quota_alert_threshold_count:
            alerts.append(
                {
                    "type": "quota_exceeded_workspaces",
                    "severity": "warning",
                    "message": "Workspace quota-exceeded count exceeds threshold",
                    "count": inspection.get("quota_exceeded_count", 0),
                    "threshold": self.policy.quota_alert_threshold_count,
                }
            )
        if inspection.get("total_size_bytes", 0) >= self.policy.quota_alert_threshold_bytes:
            alerts.append(
                {
                    "type": "quota_bytes",
                    "severity": "warning",
                    "message": "Workspace storage usage exceeds threshold",
                    "bytes": inspection.get("total_size_bytes", 0),
                    "threshold": self.policy.quota_alert_threshold_bytes,
                }
            )
        for alert in alerts:
            if self.alert_callback is not None:
                await self._maybe_await(self.alert_callback(alert))
        return alerts

    async def _maybe_await(self, value: Awaitable[None] | None) -> None:
        if value is None:
            return
        await value

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("workspace lifecycle scheduler cycle failed")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.policy.interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass


def build_workspace_lifecycle_scheduler(
    *,
    manager_config: WorkspaceManagerConfig | None = None,
    policy: WorkspaceLifecyclePolicy | None = None,
    alert_callback: AlertCallback | None = None,
    inspection_callback: InspectionCallback | None = None,
) -> WorkspaceLifecycleScheduler:
    manager = WorkspaceManager(manager_config)
    return WorkspaceLifecycleScheduler(
        manager,
        policy,
        alert_callback=alert_callback,
        inspection_callback=inspection_callback,
    )
