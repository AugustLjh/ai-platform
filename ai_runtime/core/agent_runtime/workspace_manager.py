from __future__ import annotations

import ast
import fnmatch
import json
import hashlib
import os
import shutil
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any, Iterable, Sequence

from ai_runtime.core.agent_runtime.tools.providers.workspace import DEFAULT_EXCLUDE_PATTERNS
from ai_runtime.core.uploads.bundle_store import get_attachment_bundle_store, normalize_bundle_ids


DEFAULT_WORKSPACE_BASE_ROOT = Path(os.getenv("AGENT_WORKSPACE_BASE_ROOT", "/tmp/ai-platform-workspaces"))
DEFAULT_MAX_FILES = int(os.getenv("AGENT_WORKSPACE_MANAGER_MAX_FILES", "5000"))
DEFAULT_MAX_BYTES = int(os.getenv("AGENT_WORKSPACE_MANAGER_MAX_BYTES", str(200 * 1024 * 1024)))
DEFAULT_RETENTION_HOURS = int(os.getenv("AGENT_WORKSPACE_RETENTION_HOURS", "168"))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_segment(value: str | None, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or "").strip())
    return cleaned.strip("._") or fallback


def _normalize_relative_path(value: str | None, fallback: str = "file.txt") -> Path:
    parts = []
    for part in str(value or "").replace("\\", "/").split("/"):
        part = part.strip().replace("\x00", "")
        if not part or part in {".", ".."}:
            continue
        parts.append(part)
    if not parts:
        parts = [Path(fallback).name or "file.txt"]
    return Path(*parts)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    limit = max(100, int(max_chars))
    if len(text) <= limit:
        return text, False
    return text[:limit], True


@dataclass(frozen=True)
class WorkspaceManagerConfig:
    enabled: bool
    base_root: Path
    source_roots: tuple[Path, ...]
    max_files: int = DEFAULT_MAX_FILES
    max_bytes: int = DEFAULT_MAX_BYTES
    retention_hours: int = DEFAULT_RETENTION_HOURS
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS
    cleanup_lock_ttl_seconds: int = 300


class WorkspaceManager:
    def __init__(self, config: WorkspaceManagerConfig | None = None) -> None:
        self.config = config or self.from_env_config()
        self.config.base_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env_config(cls) -> WorkspaceManagerConfig:
        base_root = Path(os.getenv("AGENT_WORKSPACE_BASE_ROOT", str(DEFAULT_WORKSPACE_BASE_ROOT))).expanduser()
        source_roots = []
        for raw_root in _parse_csv(os.getenv("AGENT_WORKSPACE_SOURCE_ROOTS")):
            path = Path(raw_root).expanduser()
            if path.exists():
                source_roots.append(path.resolve(strict=True))
        return WorkspaceManagerConfig(
            enabled=_env_bool("AGENT_WORKSPACE_MANAGER_ENABLED", True),
            base_root=base_root.resolve(),
            source_roots=tuple(dict.fromkeys(source_roots)),
            max_files=DEFAULT_MAX_FILES,
            max_bytes=DEFAULT_MAX_BYTES,
            retention_hours=max(1, DEFAULT_RETENTION_HOURS),
        )

    def _run_workspace_root(self, *, tenant_id: str, run_id: str) -> Path:
        return (
            self.config.base_root
            / _safe_segment(tenant_id, "tenant")
            / _safe_segment(run_id, "run")
            / "workspace"
        )

    def _source_allowed(self, source_path: Path) -> bool:
        return any(source_path == root or root in source_path.parents for root in self.config.source_roots)

    def _resolve_managed_workspace_root(self, workspace_root: str | None, *, tenant_id: str | None = None) -> Path:
        if not workspace_root:
            raise ValueError("workspace root is required")
        candidate = Path(workspace_root).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("workspace root must be a directory")
        if candidate == self.config.base_root or self.config.base_root not in candidate.parents:
            raise PermissionError("workspace root is outside managed workspace base root")
        if tenant_id:
            expected_tenant = _safe_segment(tenant_id, "tenant")
            try:
                relative_parts = candidate.relative_to(self.config.base_root).parts
            except ValueError:
                relative_parts = ()
            if not relative_parts or relative_parts[0] != expected_tenant:
                raise PermissionError("workspace root belongs to a different tenant")
        return candidate

    def _excluded(self, relative_path: str) -> bool:
        normalized = relative_path.strip("/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.config.exclude_patterns)

    def _excluded_for_copy(self, relative_path: str, *, include_git_metadata: bool = False) -> bool:
        normalized = relative_path.strip("/")
        if include_git_metadata and (normalized == ".git" or normalized.startswith(".git/")):
            return False
        return self._excluded(normalized)

    def _resolve_existing_workspace(self, root: str | None) -> Path:
        if not root:
            raise ValueError("workspace root is required")
        candidate = Path(root).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("workspace root must be a directory")
        if not self._source_allowed(candidate):
            raise PermissionError("workspace root is outside configured workspace source roots")
        return candidate

    def list_available_sources(
        self,
        *,
        max_entries: int = 200,
        max_depth: int = 2,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _append(path: Path, source_root: Path, depth: int) -> None:
            resolved = path.resolve(strict=True)
            key = str(resolved)
            if key in seen or len(items) >= max_entries:
                return
            seen.add(key)
            writeback_supported = True
            writeback_reason = ""
            if resolved == source_root:
                writeback_reason = "Writeback is allowed only after a run binds this source into an isolated workspace copy."
            items.append(
                {
                    "path": key,
                    "name": resolved.name or key,
                    "source_root": str(source_root),
                    "depth": depth,
                    "is_git_repo": resolved.joinpath(".git").exists(),
                    "binding_type": "existing",
                    "workspace_origin": "source_root",
                    "writeback": {
                        "supported": writeback_supported,
                        "requires_confirmation": True,
                        "mode": "two_phase_user_confirmed",
                        "risk_level": "high",
                        "reason": writeback_reason,
                    },
                }
            )

        bounded_depth = max(0, int(max_depth))
        for source_root in self.config.source_roots:
            if len(items) >= max_entries:
                break
            if not source_root.exists() or not source_root.is_dir():
                continue
            _append(source_root, source_root, 0)
            stack: list[tuple[Path, int]] = [(source_root, 0)]
            while stack and len(items) < max_entries:
                current, depth = stack.pop()
                if depth >= bounded_depth:
                    continue
                try:
                    children = sorted(
                        [candidate for candidate in current.iterdir() if candidate.is_dir()],
                        key=lambda candidate: candidate.name.lower(),
                    )
                except OSError:
                    continue
                for child in children:
                    if child.name in {".git", "__pycache__", "node_modules", ".venv", "venv"}:
                        continue
                    _append(child, source_root, depth + 1)
                    stack.append((child, depth + 1))
                    if len(items) >= max_entries:
                        break

        items.sort(key=lambda item: (item["depth"], item["name"].lower(), item["path"]))
        return {
            "status": "completed",
            "enabled": self.config.enabled,
            "base_root": str(self.config.base_root),
            "source_roots": [str(path) for path in self.config.source_roots],
            "binding_policies": {
                "existing_source": {
                    "writeback_supported": True,
                    "writeback_requires_confirmation": True,
                    "summary": "Existing source roots can be copied into an isolated run workspace and later written back through explicit dry-run plus confirmed apply.",
                },
                "upload_bundle": {
                    "writeback_supported": False,
                    "summary": "Upload bundles can seed an isolated workspace, but they do not have a registered source root and cannot be written back.",
                },
            },
            "count": len(items),
            "max_entries": max_entries,
            "max_depth": bounded_depth,
            "sources": items,
        }

    def _snapshot(self, root: Path, *, source: dict[str, Any]) -> dict[str, Any]:
        files = []
        total_size = 0
        truncated = False
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if self._excluded(relative):
                continue
            stat = path.stat()
            files.append({"path": relative, "size_bytes": stat.st_size})
            total_size += stat.st_size
            if len(files) >= self.config.max_files or total_size >= self.config.max_bytes:
                truncated = True
                break
        return {
            "source": source,
            "file_count": len(files),
            "total_size_bytes": total_size,
            "files": files[:200],
            "truncated": truncated,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }

    def _workspace_root_candidates(self) -> Iterable[Path]:
        if not self.config.base_root.exists():
            return []
        return (
            path
            for path in self.config.base_root.glob("*/*/workspace")
            if path.is_dir() and path.parent.parent.parent == self.config.base_root
        )

    def _cleanup_lock_path(self, workspace_id: str) -> Path:
        lock_name = _safe_segment(workspace_id.replace("/", "__"), "workspace") + ".cleanup.lock"
        return self.config.base_root / ".lifecycle-locks" / lock_name

    def _workspace_id_to_root(self, workspace_id: str) -> Path | None:
        parts = [part for part in str(workspace_id or "").split("/") if part]
        if len(parts) < 2:
            return None
        tenant_id, run_id = parts[0], parts[1]
        return self._run_workspace_root(tenant_id=tenant_id, run_id=run_id)

    def _parse_lock_payload(self, lock_path: Path) -> dict[str, Any]:
        try:
            raw_text = lock_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return {}
        if not raw_text:
            return {}
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(raw_text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return dict(parsed)
        return {"raw": raw_text[:500]}

    def _inspect_cleanup_locks(
        self,
        *,
        now: datetime,
        tenant_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        lock_root = self.config.base_root / ".lifecycle-locks"
        ttl_seconds = max(30, int(self.config.cleanup_lock_ttl_seconds))
        items: list[dict[str, Any]] = []
        lookup: dict[str, dict[str, Any]] = {}
        active_count = 0
        stale_count = 0
        orphan_count = 0
        oldest_age_seconds: int | None = None
        normalized_tenant_id = _safe_segment(tenant_id, "") if tenant_id else ""

        if lock_root.exists():
            for lock_path in sorted(lock_root.glob("*.cleanup.lock"), key=lambda item: item.as_posix()):
                if not lock_path.is_file():
                    continue
                payload = self._parse_lock_payload(lock_path)
                workspace_id = str(payload.get("workspace_id") or "").strip()
                if normalized_tenant_id and workspace_id and not workspace_id.startswith(f"{normalized_tenant_id}/"):
                    continue
                try:
                    stat = lock_path.stat()
                except OSError:
                    continue
                acquired_at = str(payload.get("acquired_at") or "")
                expires_at = str(payload.get("expires_at") or "")
                owner_host = str(payload.get("owner_host") or "").strip() or None
                owner_pid = payload.get("owner_pid")
                lock_age_seconds = max(0, int((now - datetime.fromtimestamp(stat.st_mtime, timezone.utc)).total_seconds()))
                expired_by_age = lock_age_seconds > ttl_seconds
                payload_expired = False
                if expires_at:
                    try:
                        payload_expired = now > datetime.fromisoformat(expires_at)
                    except ValueError:
                        payload_expired = False
                stale = expired_by_age or payload_expired
                root = self._workspace_id_to_root(workspace_id) if workspace_id else None
                workspace_exists = bool(root and root.exists())
                orphan = not workspace_exists
                if stale:
                    stale_count += 1
                elif workspace_exists:
                    active_count += 1
                if orphan:
                    orphan_count += 1
                oldest_age_seconds = lock_age_seconds if oldest_age_seconds is None else max(oldest_age_seconds, lock_age_seconds)
                item = {
                    "lock_path": str(lock_path),
                    "workspace_id": workspace_id or None,
                    "tenant_id": workspace_id.split("/", 1)[0] if workspace_id and "/" in workspace_id else None,
                    "run_id": workspace_id.split("/", 1)[1] if workspace_id and "/" in workspace_id else None,
                    "workspace_root": str(root) if root else None,
                    "workspace_exists": workspace_exists,
                    "age_seconds": lock_age_seconds,
                    "ttl_seconds": ttl_seconds,
                    "status": "stale" if stale else "active",
                    "stale": stale,
                    "orphan": orphan,
                    "owner_host": owner_host,
                    "owner_pid": int(owner_pid) if isinstance(owner_pid, int) else owner_pid,
                    "acquired_at": acquired_at or None,
                    "expires_at": expires_at or None,
                    "payload": payload,
                }
                items.append(item)
                if workspace_id:
                    lookup[workspace_id] = item

        summary = {
            "status": "completed",
            "base_root": str(self.config.base_root),
            "lock_root": str(lock_root),
            "ttl_seconds": ttl_seconds,
            "lock_count": len(items),
            "active_lock_count": active_count,
            "stale_lock_count": stale_count,
            "orphan_lock_count": orphan_count,
            "oldest_lock_age_seconds": oldest_age_seconds,
            "locks": items[:100],
        }
        return summary, lookup

    def build_workspace_health(
        self,
        inspection: dict[str, Any],
        *,
        lock_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return {
                "status": "disabled",
                "score": 0,
                "summary": "workspace manager is disabled",
                "issues": [],
                "recovery_actions": [],
            }

        resolved_lock_summary = lock_summary or inspection.get("lock_summary") or {}
        expired_count = int(inspection.get("expired_count") or 0)
        quota_exceeded_count = int(inspection.get("quota_exceeded_count") or 0)
        total_size_bytes = int(inspection.get("total_size_bytes") or 0)
        total_file_count = int(inspection.get("total_file_count") or 0)
        stale_lock_count = int(resolved_lock_summary.get("stale_lock_count") or 0)
        orphan_lock_count = int(resolved_lock_summary.get("orphan_lock_count") or 0)

        issues: list[dict[str, Any]] = []
        if expired_count > 0:
            issues.append(
                {
                    "code": "expired_workspaces",
                    "severity": "critical" if expired_count >= 10 else "warning",
                    "count": expired_count,
                    "message": "Expired managed workspaces need cleanup",
                }
            )
        if quota_exceeded_count > 0:
            issues.append(
                {
                    "code": "quota_exceeded_workspaces",
                    "severity": "critical" if quota_exceeded_count >= 10 else "warning",
                    "count": quota_exceeded_count,
                    "message": "Managed workspaces are over quota",
                }
            )
        if stale_lock_count > 0:
            issues.append(
                {
                    "code": "stale_cleanup_locks",
                    "severity": "warning" if stale_lock_count < 5 else "critical",
                    "count": stale_lock_count,
                    "message": "Cleanup locks have exceeded their TTL",
                }
            )
        if orphan_lock_count > 0:
            issues.append(
                {
                    "code": "orphan_cleanup_locks",
                    "severity": "warning",
                    "count": orphan_lock_count,
                    "message": "Cleanup locks reference missing workspaces",
                }
            )

        if not issues:
            status = "healthy"
        elif any(issue["severity"] == "critical" for issue in issues):
            status = "critical"
        else:
            status = "warning"

        score = 100
        score -= min(35, expired_count * 4)
        score -= min(25, quota_exceeded_count * 5)
        score -= min(20, stale_lock_count * 4)
        score -= min(10, orphan_lock_count * 2)
        if total_size_bytes > 0 and total_file_count > 0:
            score -= min(10, total_size_bytes // max(1, self.config.max_bytes))
        score = max(0, min(100, score))

        if not issues:
            summary = "workspace lifecycle is healthy"
        else:
            fragments = []
            for issue in issues[:3]:
                fragments.append(f"{issue['code']}={issue['count']}")
            summary = "workspace lifecycle needs attention: " + ", ".join(fragments)

        recovery_actions: list[dict[str, Any]] = []
        if expired_count > 0 or quota_exceeded_count > 0:
            recovery_actions.append(
                {
                    "key": "cleanup_expired_workspaces",
                    "label": "清理过期 workspace",
                    "category": "workspace_cleanup",
                    "priority": "high",
                    "requires_confirmation": True,
                    "tenant_scoped": True,
                }
            )
        if stale_lock_count > 0 or orphan_lock_count > 0:
            recovery_actions.append(
                {
                    "key": "cleanup_stale_locks",
                    "label": "回收陈旧清理锁",
                    "category": "lock_cleanup",
                    "priority": "medium",
                    "requires_confirmation": False,
                    "tenant_scoped": True,
                }
            )

        return {
            "status": status,
            "score": score,
            "summary": summary,
            "issues": issues,
            "recovery_actions": recovery_actions,
        }

    def _acquire_cleanup_lock(
        self,
        workspace_id: str,
        *,
        now: datetime,
    ) -> tuple[bool, Path, dict[str, Any] | None]:
        lock_path = self._cleanup_lock_path(workspace_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        expires_at = now + timedelta(seconds=max(30, int(self.config.cleanup_lock_ttl_seconds)))
        payload = {
            "workspace_id": workspace_id,
            "owner_host": socket.gethostname(),
            "owner_pid": os.getpid(),
            "acquired_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        def _try_create() -> bool:
            try:
                fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            return True

        if _try_create():
            return True, lock_path, payload

        try:
            stat = lock_path.stat()
        except OSError:
            if _try_create():
                return True, lock_path, payload
            return False, lock_path, None

        lock_age = max(0, int((now - datetime.fromtimestamp(stat.st_mtime, timezone.utc)).total_seconds()))
        if lock_age <= max(30, int(self.config.cleanup_lock_ttl_seconds)):
            return False, lock_path, {"age_seconds": lock_age}

        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False, lock_path, {"age_seconds": lock_age}
        if _try_create():
            return True, lock_path, {**payload, "stale_lock_reclaimed": True, "stale_lock_age_seconds": lock_age}
        return False, lock_path, {"age_seconds": lock_age}

    def _directory_size(self, root: Path) -> tuple[int, int, bool]:
        file_count = 0
        total_size = 0
        truncated = False
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if self._excluded(relative):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            file_count += 1
            total_size += stat.st_size
            if file_count > self.config.max_files or total_size > self.config.max_bytes:
                truncated = True
                break
        return file_count, total_size, truncated

    def inspect_workspaces(self, *, now: datetime | None = None) -> dict[str, Any]:
        resolved_now = now or datetime.now(timezone.utc)
        retention_delta = timedelta(hours=max(1, self.config.retention_hours))
        items: list[dict[str, Any]] = []
        total_bytes = 0
        total_files = 0
        quota_exceeded_count = 0
        expired_count = 0
        lock_summary, lock_lookup = self._inspect_cleanup_locks(now=resolved_now)
        for root in self._workspace_root_candidates():
            try:
                stat = root.stat()
            except OSError:
                continue
            modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            age_seconds = max(0, int((resolved_now - modified_at).total_seconds()))
            file_count, size_bytes, truncated = self._directory_size(root)
            quota_exceeded = file_count > self.config.max_files or size_bytes > self.config.max_bytes or truncated
            expired = resolved_now - modified_at > retention_delta
            total_bytes += size_bytes
            total_files += file_count
            quota_exceeded_count += 1 if quota_exceeded else 0
            expired_count += 1 if expired else 0
            tenant_id = root.parent.parent.name
            run_id = root.parent.name
            items.append(
                {
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                    "workspace_id": f"{tenant_id}/{run_id}",
                    "root": str(root),
                    "file_count": file_count,
                    "size_bytes": size_bytes,
                    "modified_at": modified_at.isoformat(),
                    "age_seconds": age_seconds,
                    "expired": expired,
                    "quota_exceeded": quota_exceeded,
                    "truncated": truncated,
                    "cleanup_lock": lock_lookup.get(f"{tenant_id}/{run_id}"),
                }
            )
        items.sort(key=lambda item: (item["expired"], item["quota_exceeded"], item["modified_at"]), reverse=True)
        inspection = {
            "status": "completed",
            "base_root": str(self.config.base_root),
            "retention_hours": self.config.retention_hours,
            "workspace_count": len(items),
            "expired_count": expired_count,
            "quota_exceeded_count": quota_exceeded_count,
            "total_size_bytes": total_bytes,
            "total_file_count": total_files,
            "workspaces": items,
            "generated_at": resolved_now.isoformat(),
            "lock_summary": lock_summary,
        }
        inspection["health"] = self.build_workspace_health(inspection, lock_summary=lock_summary)
        return inspection

    def cleanup_expired_workspaces(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = True,
        max_delete: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_now = now or datetime.now(timezone.utc)
        inspection = self.inspect_workspaces(now=resolved_now)
        normalized_tenant_id = _safe_segment(tenant_id, "") if tenant_id else ""
        candidates = [
            item
            for item in inspection["workspaces"]
            if item.get("expired") and (not normalized_tenant_id or item.get("tenant_id") == normalized_tenant_id)
        ]
        selected = candidates[: max(0, max_delete)]
        deleted: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for item in selected:
            root = Path(str(item.get("root") or ""))
            record = {
                "workspace_id": item.get("workspace_id"),
                "root": str(root),
                "size_bytes": item.get("size_bytes"),
                "file_count": item.get("file_count"),
            }
            if dry_run:
                deleted.append({**record, "deleted": False, "dry_run": True})
                continue
            locked, lock_path, lock_payload = self._acquire_cleanup_lock(
                str(item.get("workspace_id") or ""),
                now=resolved_now,
            )
            if not locked:
                skipped.append(
                    {
                        **record,
                        "reason": "cleanup_lock_held",
                        "lock_path": str(lock_path),
                        "lock": lock_payload or {},
                    }
                )
                continue
            try:
                resolved_root = root.resolve(strict=True)
                if resolved_root == self.config.base_root or self.config.base_root not in resolved_root.parents:
                    raise PermissionError("workspace cleanup target escapes base_root")
                shutil.rmtree(resolved_root)
                deleted.append({**record, "deleted": True, "dry_run": False, "lock": lock_payload or {}})
            except Exception as exc:
                failed.append({**record, "error": str(exc)})
            finally:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        return {
            "status": "completed" if not failed else "partial",
            "dry_run": dry_run,
            "base_root": str(self.config.base_root),
            "tenant_id": normalized_tenant_id or None,
            "retention_hours": self.config.retention_hours,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "deleted_count": sum(1 for item in deleted if item.get("deleted")),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "deleted": deleted,
            "failed": failed,
            "skipped": skipped,
            "generated_at": resolved_now.isoformat(),
        }

    def cleanup_stale_locks(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = True,
        max_delete: int = 100,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_now = now or datetime.now(timezone.utc)
        lock_summary, _ = self._inspect_cleanup_locks(now=resolved_now, tenant_id=tenant_id)
        candidates = [item for item in lock_summary.get("locks", []) if item.get("stale")]
        selected = candidates[: max(0, max_delete)]
        deleted: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for item in selected:
            lock_path = Path(str(item.get("lock_path") or ""))
            record = {
                "lock_path": str(lock_path),
                "workspace_id": item.get("workspace_id"),
                "status": item.get("status"),
                "age_seconds": item.get("age_seconds"),
            }
            if dry_run:
                deleted.append({**record, "deleted": False, "dry_run": True})
                continue
            try:
                lock_path.unlink(missing_ok=False)
                deleted.append({**record, "deleted": True, "dry_run": False})
            except FileNotFoundError:
                failed.append({**record, "error": "lock disappeared before deletion"})
            except OSError as exc:
                failed.append({**record, "error": str(exc)})
        return {
            "status": "completed" if not failed else "partial",
            "dry_run": dry_run,
            "base_root": str(self.config.base_root),
            "tenant_id": _safe_segment(tenant_id, "") or None,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "deleted_count": sum(1 for item in deleted if item.get("deleted")),
            "failed_count": len(failed),
            "deleted": deleted,
            "failed": failed,
            "generated_at": resolved_now.isoformat(),
        }

    def _copy_source_tree(
        self,
        *,
        source_root: Path,
        target_root: Path,
        include_git_metadata: bool = False,
    ) -> dict[str, Any]:
        copied_files = 0
        copied_bytes = 0
        skipped = []
        for source_path in sorted(source_root.rglob("*"), key=lambda item: item.as_posix()):
            if not source_path.is_file():
                continue
            relative = source_path.relative_to(source_root)
            relative_text = relative.as_posix()
            if self._excluded_for_copy(relative_text, include_git_metadata=include_git_metadata):
                continue
            resolved = source_path.resolve(strict=True)
            if resolved != source_root and source_root not in resolved.parents:
                skipped.append({"path": relative_text, "reason": "symlink_escape"})
                continue
            stat = source_path.stat()
            if copied_files + 1 > self.config.max_files or copied_bytes + stat.st_size > self.config.max_bytes:
                skipped.append({"path": relative_text, "reason": "quota_exceeded"})
                break
            target_path = target_root / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied_files += 1
            copied_bytes += stat.st_size
        return {"copied_files": copied_files, "copied_bytes": copied_bytes, "skipped": skipped[:100]}

    def _materialize_upload_bundles(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        bundle_ids: Sequence[str],
        target_root: Path,
    ) -> dict[str, Any]:
        store = get_attachment_bundle_store()
        manifest = store.list_bundle_files(tenant_id=tenant_id, user_id=user_id, bundle_ids=bundle_ids)
        written_files = 0
        written_bytes = 0
        skipped = []
        for item in manifest.get("files") or []:
            attachment_id = str(item.get("id") or "").strip()
            if not attachment_id:
                continue
            content = store.read_bundle_file(
                tenant_id=tenant_id,
                user_id=user_id,
                bundle_ids=bundle_ids,
                attachment_id=attachment_id,
                max_chars=10_000_000,
            )
            relative = _normalize_relative_path(content.get("path"), fallback=content.get("name") or "attachment.txt")
            relative_text = relative.as_posix()
            if self._excluded(relative_text):
                skipped.append({"path": relative_text, "reason": "excluded"})
                continue
            text = str(content.get("content") or "")
            encoded_size = len(text.encode("utf-8"))
            if written_files + 1 > self.config.max_files or written_bytes + encoded_size > self.config.max_bytes:
                skipped.append({"path": relative_text, "reason": "quota_exceeded"})
                break
            target_path = target_root / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(text, encoding="utf-8")
            written_files += 1
            written_bytes += encoded_size
        return {
            "bundle_ids": list(bundle_ids),
            "written_files": written_files,
            "written_bytes": written_bytes,
            "skipped": skipped[:100],
        }

    def _iter_sync_files(self, root: Path) -> dict[str, Path]:
        files: dict[str, Path] = {}
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if self._excluded(relative):
                continue
            resolved = path.resolve(strict=True)
            if resolved != root and root not in resolved.parents:
                continue
            files[relative] = path
        return files

    def _text_file_diff(
        self,
        *,
        relative_path: str,
        before_path: Path | None,
        after_path: Path | None,
        max_chars: int,
    ) -> tuple[str, bool]:
        before = ""
        after = ""
        try:
            if before_path is not None and before_path.exists() and before_path.stat().st_size <= 2 * 1024 * 1024:
                before = before_path.read_text(encoding="utf-8", errors="replace")
            if after_path is not None and after_path.exists() and after_path.stat().st_size <= 2 * 1024 * 1024:
                after = after_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "", False
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        return _truncate_text(diff, max_chars)

    def plan_workspace_writeback(
        self,
        *,
        workspace_root: str,
        source_path: str,
        tenant_id: str | None = None,
        max_diff_chars: int = 40000,
    ) -> dict[str, Any]:
        managed_root = self._resolve_managed_workspace_root(workspace_root, tenant_id=tenant_id)
        source_root = self._resolve_existing_workspace(source_path)
        workspace_files = self._iter_sync_files(managed_root)
        source_files = self._iter_sync_files(source_root)
        all_paths = sorted(set(workspace_files) | set(source_files))

        changes: list[dict[str, Any]] = []
        diff_parts: list[str] = []
        diff_truncated = False
        remaining_chars = max(100, int(max_diff_chars))
        for relative in all_paths:
            workspace_file = workspace_files.get(relative)
            source_file = source_files.get(relative)
            if workspace_file is None and source_file is not None:
                operation = "delete"
                before_sha256 = _file_sha256(source_file)
                after_sha256 = None
                size_bytes = 0
            elif workspace_file is not None and source_file is None:
                operation = "create"
                before_sha256 = None
                after_sha256 = _file_sha256(workspace_file)
                size_bytes = workspace_file.stat().st_size
            elif workspace_file is not None and source_file is not None:
                before_sha256 = _file_sha256(source_file)
                after_sha256 = _file_sha256(workspace_file)
                if before_sha256 == after_sha256:
                    continue
                operation = "modify"
                size_bytes = workspace_file.stat().st_size
            else:
                continue

            file_diff = ""
            file_diff_truncated = False
            if remaining_chars > 100:
                file_diff, file_diff_truncated = self._text_file_diff(
                    relative_path=relative,
                    before_path=source_file,
                    after_path=workspace_file,
                    max_chars=remaining_chars,
                )
                if file_diff:
                    diff_parts.append(file_diff)
                    remaining_chars -= len(file_diff)
                diff_truncated = diff_truncated or file_diff_truncated or remaining_chars <= 100
            else:
                diff_truncated = True

            changes.append(
                {
                    "path": relative,
                    "operation": operation,
                    "before_sha256": before_sha256,
                    "after_sha256": after_sha256,
                    "size_bytes": size_bytes,
                    "changed": True,
                }
            )

        diff, combined_truncated = _truncate_text("".join(diff_parts), max(100, int(max_diff_chars)))
        return {
            "status": "changes_detected" if changes else "no_changes",
            "workspace_root": str(managed_root),
            "source_path": str(source_root),
            "change_count": len(changes),
            "files": changes,
            "diff": diff,
            "truncated": diff_truncated or combined_truncated,
            "writeback": {
                "supported": True,
                "mode": "two_phase_user_confirmed",
                "dry_run": True,
                "requires_confirmation": True,
                "risk_level": "high",
                "summary": "Preview only. No source files are modified until dry_run=false and confirmed=true.",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def apply_workspace_writeback(
        self,
        *,
        workspace_root: str,
        source_path: str,
        tenant_id: str | None = None,
        dry_run: bool = True,
        confirmed: bool = False,
        max_diff_chars: int = 40000,
    ) -> dict[str, Any]:
        plan = self.plan_workspace_writeback(
            workspace_root=workspace_root,
            source_path=source_path,
            tenant_id=tenant_id,
            max_diff_chars=max_diff_chars,
        )
        if dry_run:
            return {**plan, "status": "dry_run", "dry_run": True, "applied_count": 0}
        if not confirmed:
            raise ValueError("workspace writeback requires confirmed=true when dry_run=false")

        managed_root = Path(plan["workspace_root"]).resolve(strict=True)
        source_root = Path(plan["source_path"]).resolve(strict=True)
        applied: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for change in plan["files"]:
            relative = str(change.get("path") or "")
            target_path = (source_root / _normalize_relative_path(relative)).resolve(strict=False)
            if target_path == source_root or source_root not in target_path.parents:
                failed.append({**change, "error": "target path escapes source root"})
                continue
            try:
                if change.get("operation") == "delete":
                    resolved_target = target_path.resolve(strict=True)
                    if resolved_target == source_root or source_root not in resolved_target.parents:
                        raise PermissionError("target path escapes source root")
                    if not resolved_target.is_file():
                        raise ValueError("delete target is not a file")
                    resolved_target.unlink()
                else:
                    source_file = (managed_root / _normalize_relative_path(relative)).resolve(strict=True)
                    if source_file == managed_root or managed_root not in source_file.parents:
                        raise PermissionError("workspace source path escapes managed root")
                    if not source_file.is_file():
                        raise ValueError("workspace source is not a file")
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target_path)
                applied.append(change)
            except Exception as exc:
                failed.append({**change, "error": str(exc)})

        return {
            **plan,
            "status": "completed" if not failed else "partial",
            "dry_run": False,
            "applied_count": len(applied),
            "failed_count": len(failed),
            "applied": applied,
            "failed": failed,
            "writeback": {
                "supported": True,
                "mode": "two_phase_user_confirmed",
                "dry_run": False,
                "requires_confirmation": True,
                "risk_level": "high",
                "summary": "Writeback applied to the registered source root after explicit confirmation.",
            },
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _normalize_configured_default_source(
        self,
        agent_config: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(agent_config, dict):
            return None
        workspace_config = agent_config.get("workspace")
        if not isinstance(workspace_config, dict):
            return None
        configured = (
            workspace_config.get("default_source")
            or workspace_config.get("defaultSource")
            or workspace_config.get("default_binding")
            or workspace_config.get("defaultBinding")
        )
        if not isinstance(configured, dict):
            return None

        source_type = str(configured.get("type") or configured.get("source_type") or configured.get("mode") or "").strip().lower()
        enabled = configured.get("enabled", True)
        if enabled is False or source_type in {"", "none", "context_only", "disabled"}:
            return None

        root = str(configured.get("root") or configured.get("path") or "").strip()
        if source_type in {"existing", "bound", "local_path"} and root:
            return {"type": source_type, "root": root, "configured_default": True}

        bundle_ids = normalize_bundle_ids(configured.get("upload_bundle_ids") or configured.get("bundle_ids"))
        if source_type == "upload_bundle" and bundle_ids:
            return {"type": "upload_bundle", "bundle_ids": bundle_ids, "configured_default": True}

        return None

    def _select_source(
        self,
        *,
        run_input: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        workspace_source = run_input.get("workspace_source")
        if not isinstance(workspace_source, dict):
            workspace_payload = run_input.get("workspace")
            workspace_source = workspace_payload if isinstance(workspace_payload, dict) else {}

        source_type = str(workspace_source.get("type") or workspace_source.get("source_type") or "").strip().lower()
        root = str(workspace_source.get("root") or workspace_source.get("path") or run_input.get("workspace_root") or "").strip()
        if root:
            return {"type": source_type or "existing", "root": root}

        bundle_ids = normalize_bundle_ids(workspace_source.get("upload_bundle_ids") or run_input.get("upload_bundle_ids"))
        if bundle_ids:
            return {"type": "upload_bundle", "bundle_ids": bundle_ids}

        metadata = metadata or {}
        metadata_workspace = metadata.get("workspace")
        if isinstance(metadata_workspace, dict):
            root = str(metadata_workspace.get("root") or metadata_workspace.get("path") or "").strip()
            if root:
                return {"type": "existing", "root": root}

        return self._normalize_configured_default_source(agent_config)

    def ensure_workspace_context(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str | None,
        run_input: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        agent_config: dict[str, Any] | None = None,
        existing_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        context = dict(existing_context or {})
        if isinstance(context.get("workspace"), dict) and context["workspace"].get("root"):
            return context, []
        if not self.config.enabled:
            return context, []

        source = self._select_source(run_input=run_input, metadata=metadata, agent_config=agent_config)
        if source is None:
            return context, []

        events: list[dict[str, Any]] = []
        target_root = self._run_workspace_root(tenant_id=tenant_id, run_id=run_id)
        target_root.mkdir(parents=True, exist_ok=True)

        source_type = str(source.get("type") or "").strip().lower()
        if source_type in {"existing", "bound", "local_path"}:
            source_root = self._resolve_existing_workspace(str(source.get("root") or ""))
            materialized = self._copy_source_tree(
                source_root=source_root,
                target_root=target_root,
                include_git_metadata=True,
            )
            workspace_root = target_root
            source_payload = {
                "type": source_type if source_type in {"bound", "local_path"} else "existing",
                "path": str(source_root),
                "binding": "copied",
            }
            if source.get("configured_default"):
                source_payload["configured_default"] = True
        elif source_type == "upload_bundle":
            bundle_ids = [str(item).strip() for item in source.get("bundle_ids") or [] if str(item).strip()]
            materialized = self._materialize_upload_bundles(
                tenant_id=tenant_id,
                user_id=user_id,
                bundle_ids=bundle_ids,
                target_root=target_root,
            )
            workspace_root = target_root
            source_payload = {"type": "upload_bundle", "bundle_ids": bundle_ids}
            if source.get("configured_default"):
                source_payload["configured_default"] = True
        else:
            raise ValueError(f"unsupported workspace source type: {source_type or 'unknown'}")

        snapshot = self._snapshot(workspace_root, source=source_payload)
        workspace_context = {
            "id": f"{_safe_segment(tenant_id, 'tenant')}/{_safe_segment(run_id, 'run')}",
            "root": str(workspace_root),
            "status": "ready",
            "source": source_payload,
            "materialized": materialized,
            "snapshot": snapshot,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        context["workspace"] = workspace_context
        context["workspace_root"] = str(workspace_root)
        events.append({"event_type": "workspace.bound", "payload": workspace_context})
        return context, events
