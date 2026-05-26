from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from ai_runtime.core.agent_runtime.tools.failure_taxonomy import build_failure_recovery, build_failure_taxonomy


DEFAULT_SANDBOX_EXEC_TOOL_NAMES = (
    "sandbox_isolation_check",
    "shell_exec",
    "run_tests",
    "run_lint",
    "run_build",
    "test_discover",
    "test_run",
    "lint_run",
    "typecheck_run",
    "coverage_run",
    "dependency_audit",
    "run_dev_server",
    "process_logs",
    "process_list",
    "process_stop",
)
DEFAULT_DENY_COMMANDS = (
    "sudo",
    "su",
    "docker",
    "kubectl",
    "shutdown",
    "reboot",
    "mount",
    "umount",
    "mkfs",
    "dd",
)
DEFAULT_DOCKER_IMAGE = "python:3.12-slim"
DEFAULT_DOCKER_PIDS_LIMIT = 256
DEFAULT_DOCKER_TMPFS_MOUNTS = ("/tmp:rw,noexec,nosuid,size=128m", "/run:rw,noexec,nosuid,size=32m")
DEFAULT_DOCKER_DROP_CAPABILITIES = ("ALL",)
SUPPORTED_RUNNER_BACKENDS = ("docker", "local_subprocess")


def _parse_csv(value: str | None, default: Sequence[str]) -> list[str]:
    if value is None or not value.strip():
        return [item for item in default]
    return [item.strip() for item in value.split(",") if item.strip()]


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tool_metadata(
    *,
    capability: str = "sandbox",
    access_level: str = "execute",
    side_effect: str = "process",
    risk_level: str = "high",
    requires_workspace: bool = True,
    requires_sandbox: bool = True,
    available: bool = False,
) -> dict[str, Any]:
    metadata = {
        "provider": "sandbox-exec",
        "capability": capability,
        "access_level": access_level,
        "side_effect": side_effect,
        "requires_workspace": requires_workspace,
        "requires_sandbox": requires_sandbox,
        "risk_level": risk_level,
        "failure_taxonomy": build_failure_taxonomy("sandbox-exec"),
    }
    if not available:
        metadata.update(
            {
                "status": "unavailable",
                "unavailable_reason": "sandbox runner is not configured",
                "recovery_actions": [
                    "Configure a sandbox runner before exposing execution tools.",
                    "Keep AGENT_SANDBOX_EXEC_ENABLED=false until runner isolation is verified.",
                ],
            }
        )
    return metadata


def _check_item(
    key: str,
    *,
    status: str,
    severity: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    recovery_actions: Sequence[str] | None = None,
) -> dict[str, Any]:
    item = {
        "key": key,
        "status": status,
        "severity": severity,
        "message": message,
        "expected": expected,
        "actual": actual,
    }
    actions = [action for action in (recovery_actions or []) if str(action).strip()]
    if actions:
        item["recovery_actions"] = actions
    return item


def build_sandbox_isolation_profile(policy: "SandboxExecPolicy") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(
        _check_item(
            "runner_configured",
            status="pass" if policy.runner_configured else "fail",
            severity="error",
            expected=True,
            actual=policy.runner_configured,
            message="Sandbox runner configuration flag is enabled."
            if policy.runner_configured
            else "Sandbox runner configuration flag is disabled.",
            recovery_actions=["Set AGENT_SANDBOX_RUNNER_CONFIGURED=true only after runner isolation has passed preflight."],
        )
    )
    checks.append(
        _check_item(
            "runner_backend",
            status="pass" if policy.runner_backend == "docker" else "warn" if policy.runner_backend == "local_subprocess" else "fail",
            severity="warning" if policy.runner_backend == "local_subprocess" else "error",
            expected="docker",
            actual=policy.runner_backend,
            message="Docker sandbox backend is selected."
            if policy.runner_backend == "docker"
            else "local_subprocess is acceptable for development but is not a production isolation boundary."
            if policy.runner_backend == "local_subprocess"
            else "Unsupported sandbox runner backend is configured.",
            recovery_actions=["Set AGENT_SANDBOX_RUNNER_BACKEND=docker for production execution."],
        )
    )

    if policy.runner_backend == "docker":
        drop_caps = {item.strip().upper() for item in policy.docker_drop_capabilities if item.strip()}
        tmpfs_mounts = [item.strip() for item in policy.docker_tmpfs_mounts if item.strip()]
        checks.extend(
            [
                _check_item(
                    "docker_network",
                    status="pass" if policy.docker_network == "none" else "fail",
                    severity="error",
                    expected="none",
                    actual=policy.docker_network,
                    message="Docker network is disabled."
                    if policy.docker_network == "none"
                    else "Docker sandbox network is not disabled.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_NETWORK=none unless a narrowly reviewed network policy is in place."],
                ),
                _check_item(
                    "docker_memory",
                    status="pass" if bool(str(policy.docker_memory or "").strip()) else "fail",
                    severity="error",
                    expected="non-empty Docker memory limit",
                    actual=policy.docker_memory,
                    message="Docker memory limit is configured."
                    if bool(str(policy.docker_memory or "").strip())
                    else "Docker memory limit is missing.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_MEMORY to a bounded value such as 1g."],
                ),
                _check_item(
                    "docker_cpus",
                    status="pass" if bool(str(policy.docker_cpus or "").strip()) else "fail",
                    severity="error",
                    expected="non-empty Docker CPU limit",
                    actual=policy.docker_cpus,
                    message="Docker CPU limit is configured."
                    if bool(str(policy.docker_cpus or "").strip())
                    else "Docker CPU limit is missing.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_CPUS to a bounded value such as 1."],
                ),
                _check_item(
                    "docker_pids_limit",
                    status="pass" if 1 <= policy.docker_pids_limit <= 512 else "fail",
                    severity="error",
                    expected="1..512",
                    actual=policy.docker_pids_limit,
                    message="Docker PID limit is within the production guardrail."
                    if 1 <= policy.docker_pids_limit <= 512
                    else "Docker PID limit is missing or too high.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_PIDS_LIMIT to 256 or another reviewed bounded value."],
                ),
                _check_item(
                    "docker_no_new_privileges",
                    status="pass",
                    severity="info",
                    expected=True,
                    actual=True,
                    message="Docker command builder applies no-new-privileges.",
                ),
                _check_item(
                    "docker_drop_capabilities",
                    status="pass" if "ALL" in drop_caps else "fail",
                    severity="error",
                    expected=["ALL"],
                    actual=sorted(drop_caps),
                    message="Docker sandbox drops all Linux capabilities."
                    if "ALL" in drop_caps
                    else "Docker sandbox does not drop all Linux capabilities.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_CAP_DROP=ALL."],
                ),
                _check_item(
                    "docker_read_only_rootfs",
                    status="pass" if policy.docker_read_only_rootfs else "warn",
                    severity="warning",
                    expected=True,
                    actual=policy.docker_read_only_rootfs,
                    message="Docker root filesystem is read-only."
                    if policy.docker_read_only_rootfs
                    else "Docker root filesystem remains writable.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_READ_ONLY_ROOTFS=true and provide explicit tmpfs mounts for writable scratch paths."],
                ),
                _check_item(
                    "docker_tmpfs",
                    status="pass" if any(mount.startswith("/tmp:") for mount in tmpfs_mounts) else "warn",
                    severity="warning",
                    expected="tmpfs mount for /tmp",
                    actual=tmpfs_mounts,
                    message="Docker sandbox provides tmpfs scratch space."
                    if any(mount.startswith("/tmp:") for mount in tmpfs_mounts)
                    else "Docker sandbox has no explicit /tmp tmpfs mount.",
                    recovery_actions=["Set AGENT_SANDBOX_DOCKER_TMPFS=/tmp:rw,noexec,nosuid,size=128m,/run:rw,noexec,nosuid,size=32m."],
                ),
            ]
        )

    failed = sum(1 for check in checks if check["status"] == "fail")
    warning = sum(1 for check in checks if check["status"] == "warn")
    passed = sum(1 for check in checks if check["status"] == "pass")
    recovery_actions: list[str] = []
    for check in checks:
        for action in check.get("recovery_actions", []):
            if action not in recovery_actions:
                recovery_actions.append(action)
    status = "ready" if failed == 0 and warning == 0 else "warning" if failed == 0 else "failed"
    return {
        "status": status,
        "production_ready": status == "ready" and policy.runner_backend == "docker",
        "backend": policy.runner_backend,
        "passed": passed,
        "failed": failed,
        "warning": warning,
        "checks": checks,
        "recovery_actions": recovery_actions,
        "limits": {
            "max_output_chars": policy.max_output_chars,
            "max_timeout_seconds": policy.max_timeout_seconds,
            "deny_commands": list(policy.deny_commands),
            "docker": {
                "image": policy.docker_image,
                "network": policy.docker_network,
                "memory": policy.docker_memory,
                "cpus": policy.docker_cpus,
                "pids_limit": policy.docker_pids_limit,
                "read_only_rootfs": policy.docker_read_only_rootfs,
                "tmpfs_mounts": list(policy.docker_tmpfs_mounts),
                "drop_capabilities": list(policy.docker_drop_capabilities),
            }
            if policy.runner_backend == "docker"
            else None,
        },
    }


@dataclass(frozen=True)
class SandboxExecPolicy:
    runner_configured: bool = False
    runner_backend: str = "docker"
    docker_image: str = DEFAULT_DOCKER_IMAGE
    docker_network: str = "none"
    docker_memory: str = "1g"
    docker_cpus: str = "1"
    docker_pids_limit: int = DEFAULT_DOCKER_PIDS_LIMIT
    docker_read_only_rootfs: bool = True
    docker_tmpfs_mounts: tuple[str, ...] = DEFAULT_DOCKER_TMPFS_MOUNTS
    docker_drop_capabilities: tuple[str, ...] = DEFAULT_DOCKER_DROP_CAPABILITIES
    max_output_chars: int = 40_000
    max_timeout_seconds: int = 1_200
    deny_commands: tuple[str, ...] = DEFAULT_DENY_COMMANDS


@dataclass
class SandboxProcessSession:
    session_id: str
    process: asyncio.subprocess.Process
    command: list[str]
    cwd: str
    started_at: float
    purpose: str
    timeout_seconds: int | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    exposed_ports: list[int] | None = None
    health_check_url: str | None = None
    timed_out: bool = False
    stopped_at: float | None = None


class SandboxExecTool(BaseTool):
    spec: ToolSpec

    def __init__(
        self,
        policy: SandboxExecPolicy,
        sessions: dict[str, SandboxProcessSession] | None = None,
    ) -> None:
        self.policy = policy
        self.sessions = sessions if sessions is not None else {}

    def _metadata(self) -> dict[str, Any]:
        return _tool_metadata(
            capability=str(self.spec.metadata.get("capability") or "sandbox"),
            access_level=str(self.spec.metadata.get("access_level") or "execute"),
            side_effect=str(self.spec.metadata.get("side_effect") or "process"),
            risk_level=str(self.spec.metadata.get("risk_level") or "high"),
            requires_workspace=bool(self.spec.metadata.get("requires_workspace", True)),
            requires_sandbox=bool(self.spec.metadata.get("requires_sandbox", True)),
            available=self.policy.runner_configured,
        )

    def spec_dict(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "input_schema": self.spec.input_schema,
            "kind": self.spec.kind,
            "metadata": self._metadata(),
        }

    def _resolve_workspace_root(self, context: ToolContext | ToolLookupContext | None) -> Path:
        raw_root = str(getattr(context, "workspace_root", None) or "").strip() if context is not None else ""
        if not raw_root:
            raise ValueError("workspace_root is required for sandbox execution")
        root = Path(raw_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("workspace_root must be a directory")
        return root

    def _resolve_cwd(self, context: ToolContext, raw_cwd: str | None) -> tuple[Path, str]:
        workspace_root = self._resolve_workspace_root(context)
        cwd_text = str(raw_cwd or ".").strip() or "."
        if os.path.isabs(cwd_text):
            raise PermissionError("absolute cwd paths are not allowed")
        cwd = workspace_root.joinpath(cwd_text).resolve(strict=True)
        if cwd != workspace_root and workspace_root not in cwd.parents:
            raise PermissionError("cwd escapes the configured workspace root")
        if not cwd.is_dir():
            raise ValueError("cwd must be a directory")
        relative = "." if cwd == workspace_root else cwd.relative_to(workspace_root).as_posix()
        return cwd, relative

    def _truncate_text(self, text: str, max_chars: int | None = None) -> tuple[str, bool]:
        limit = max_chars or self.policy.max_output_chars
        if len(text) <= limit:
            return text, False
        return text[:limit], True

    def _coerce_command(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("command must be a non-empty array of strings")
        command = []
        for item in value:
            if not isinstance(item, str) or "\x00" in item:
                raise ValueError("command entries must be strings without NUL bytes")
            text = item.strip()
            if not text:
                raise ValueError("command entries must not be empty")
            command.append(text)
        executable = Path(command[0]).name
        if executable in set(self.policy.deny_commands):
            raise PermissionError(f"command is denied by sandbox policy: {executable}")
        return command

    def _runner_profile(self) -> dict[str, Any]:
        isolation = build_sandbox_isolation_profile(self.policy)
        return {
            "backend": self.policy.runner_backend,
            "workspace_root": None,
            "image": self.policy.docker_image if self.policy.runner_backend == "docker" else None,
            "network": self.policy.docker_network if self.policy.runner_backend == "docker" else None,
            "memory": self.policy.docker_memory if self.policy.runner_backend == "docker" else None,
            "cpus": self.policy.docker_cpus if self.policy.runner_backend == "docker" else None,
            "pids_limit": self.policy.docker_pids_limit if self.policy.runner_backend == "docker" else None,
            "read_only_rootfs": self.policy.docker_read_only_rootfs if self.policy.runner_backend == "docker" else None,
            "tmpfs_mounts": list(self.policy.docker_tmpfs_mounts) if self.policy.runner_backend == "docker" else [],
            "drop_capabilities": list(self.policy.docker_drop_capabilities) if self.policy.runner_backend == "docker" else [],
            "isolation": {
                "status": isolation["status"],
                "passed": isolation["passed"],
                "failed": isolation["failed"],
                "warning": isolation["warning"],
            },
        }

    def _session_log_dir(self, context: ToolContext) -> Path:
        workspace_root = self._resolve_workspace_root(context)
        log_dir = workspace_root / ".agent-runtime" / "process-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    async def _terminate_session(self, session: SandboxProcessSession, *, timeout: int = 5) -> None:
        if session.process.returncode is not None:
            session.stopped_at = session.stopped_at or time.monotonic()
            return
        if session.process.pid:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                session.process.terminate()
        else:
            session.process.terminate()
        try:
            await asyncio.wait_for(session.process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if session.process.pid:
                try:
                    os.killpg(session.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    session.process.kill()
            else:
                session.process.kill()
            await session.process.wait()
        session.stopped_at = time.monotonic()

    async def _reap_expired_sessions(self) -> None:
        now = time.monotonic()
        for session in list(self.sessions.values()):
            if session.process.returncode is not None:
                session.stopped_at = session.stopped_at or now
                continue
            if session.timeout_seconds is None:
                continue
            if now - session.started_at <= session.timeout_seconds:
                continue
            await self._terminate_session(session, timeout=3)
            session.timed_out = True

    def _read_log_tail(self, path: Path | None, *, max_chars: int) -> tuple[str, bool, int]:
        if path is None or not path.exists():
            return "", False, 0
        size = path.stat().st_size
        read_bytes = min(max(size, 0), max(max_chars * 4, 4096))
        with path.open("rb") as handle:
            if size > read_bytes:
                handle.seek(size - read_bytes)
            data = handle.read(read_bytes)
        text = data.decode("utf-8", errors="replace")
        if len(text) <= max_chars:
            return text, size > read_bytes, size
        return text[-max_chars:], True, size

    async def _probe_health_check(self, url: str, *, timeout_seconds: float) -> dict[str, Any]:
        if not url:
            return {"configured": False}
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return {
                "configured": True,
                "status": "blocked",
                "url": url,
                "error": "health_check_url must target localhost, 127.0.0.1, or ::1",
            }
        request = Request(url, method="GET", headers={"User-Agent": "ai-platform-sandbox-health/1.0"})

        def _fetch() -> dict[str, Any]:
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    return {
                        "configured": True,
                        "status": "healthy" if 200 <= int(response.status) < 500 else "unhealthy",
                        "url": url,
                        "http_status": int(response.status),
                    }
            except URLError as exc:
                return {
                    "configured": True,
                    "status": "unhealthy",
                    "url": url,
                    "error": str(exc.reason if hasattr(exc, "reason") else exc),
                }
            except Exception as exc:
                return {"configured": True, "status": "unhealthy", "url": url, "error": str(exc)}

        return await asyncio.to_thread(_fetch)

    async def _run_command(
        self,
        context: ToolContext,
        *,
        command: list[str],
        cwd: str | None = None,
        timeout_seconds: Any = None,
        default_timeout_seconds: int = 120,
        max_output_chars: Any = None,
        purpose: str = "shell",
    ) -> dict[str, Any]:
        if not self.policy.runner_configured:
            raise RuntimeError("sandbox runner is not configured")
        if self.policy.runner_backend not in SUPPORTED_RUNNER_BACKENDS:
            raise RuntimeError(f"unsupported sandbox runner backend: {self.policy.runner_backend}")

        resolved_cwd, relative_cwd = self._resolve_cwd(context, cwd)
        timeout = _clamp_int(
            timeout_seconds,
            default=default_timeout_seconds,
            minimum=1,
            maximum=self.policy.max_timeout_seconds,
        )
        output_limit = _clamp_int(
            max_output_chars,
            default=self.policy.max_output_chars,
            minimum=1_000,
            maximum=max(self.policy.max_output_chars, 1_000),
        )
        command = self._coerce_command(command)
        started_at = time.monotonic()
        container_name = f"ai-platform-sandbox-{uuid.uuid4().hex}" if self.policy.runner_backend == "docker" else None
        process_command = self._build_process_command(
            command=command,
            workspace_root=self._resolve_workspace_root(context),
            resolved_cwd=resolved_cwd,
            container_name=container_name,
        )
        process_cwd = str(resolved_cwd) if self.policy.runner_backend == "local_subprocess" else None
        try:
            process = await asyncio.create_subprocess_exec(
                *process_command,
                cwd=process_cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            return self._runner_unavailable_result(
                command=command,
                relative_cwd=relative_cwd,
                timeout=timeout,
                purpose=purpose,
                message=f"sandbox runner executable not found: {exc.filename}",
            )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            if container_name:
                await self._cleanup_docker_container(container_name)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        stdout_raw = stdout_bytes.decode("utf-8", errors="replace")
        stderr_raw = stderr_bytes.decode("utf-8", errors="replace")
        stdout, stdout_truncated = self._truncate_text(stdout_raw, output_limit)
        stderr, stderr_truncated = self._truncate_text(stderr_raw, output_limit)
        exit_code = process.returncode
        if timed_out:
            status = "timeout"
            exit_code = None
            failure_category = "timeout"
        elif exit_code == 0:
            status = "completed"
            failure_category = None
        else:
            status = "failed"
            failure_category = "non_zero_exit"

        result: dict[str, Any] = {
            "status": status,
            "exit_code": exit_code,
            "command": command,
            "cwd": relative_cwd,
            "timeout_seconds": timeout,
            "duration_ms": duration_ms,
            "runner": {
                **self._runner_profile(),
                "workspace_root": str(self._resolve_workspace_root(context)),
                "container_name": container_name,
            },
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "purpose": purpose,
            "log": {
                "stdout_preview": stdout,
                "stderr_preview": stderr,
            },
        }
        if failure_category:
            result["failure_category"] = failure_category
            result["recovery"] = build_failure_recovery("sandbox-exec", failure_category)
        structured_report = _build_structured_verification_report(
            workspace_root=self._resolve_workspace_root(context),
            purpose=purpose,
            command=command,
            stdout=stdout_raw,
            stderr=stderr_raw,
            status=status,
            exit_code=exit_code,
        )
        if structured_report:
            result["structured_report"] = structured_report
        return result

    def _runner_unavailable_result(
        self,
        *,
        command: list[str],
        relative_cwd: str,
        timeout: int,
        purpose: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "exit_code": None,
            "command": command,
            "cwd": relative_cwd,
            "timeout_seconds": timeout,
            "duration_ms": 0,
            "runner": {
                **self._runner_profile(),
            },
            "stdout": "",
            "stderr": message,
            "truncated": False,
            "purpose": purpose,
            "failure_category": "runner_unavailable",
            "recovery": build_failure_recovery("sandbox-exec", "runner_unavailable", message=message),
            "log": {
                "stdout_preview": "",
                "stderr_preview": message,
            },
        }

    async def _cleanup_docker_container(self, container_name: str) -> None:
        try:
            cleanup = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(cleanup.communicate(), timeout=10)
        except Exception:
            return

    def _build_process_command(
        self,
        *,
        command: list[str],
        workspace_root: Path,
        resolved_cwd: Path,
        container_name: str | None = None,
    ) -> list[str]:
        if self.policy.runner_backend == "local_subprocess":
            return command

        image = str(self.policy.docker_image or "").strip()
        if not image:
            raise RuntimeError("docker sandbox image is not configured")
        container_cwd = "/workspace"
        if resolved_cwd != workspace_root:
            container_cwd = f"/workspace/{resolved_cwd.relative_to(workspace_root).as_posix()}"
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name or f"ai-platform-sandbox-{uuid.uuid4().hex}",
            "--network",
            self.policy.docker_network,
            "--memory",
            self.policy.docker_memory,
            "--cpus",
            self.policy.docker_cpus,
            "--pids-limit",
            str(self.policy.docker_pids_limit),
            "--security-opt",
            "no-new-privileges",
            *[
                item
                for capability in (self.policy.docker_drop_capabilities or DEFAULT_DOCKER_DROP_CAPABILITIES)
                for item in ("--cap-drop", capability)
            ],
            *(
                ["--read-only"]
                if self.policy.docker_read_only_rootfs
                else []
            ),
            *[
                item
                for mount in self.policy.docker_tmpfs_mounts
                for item in ("--tmpfs", mount)
            ],
            "-v",
            f"{workspace_root}:/workspace:rw",
            "-w",
            container_cwd,
            image,
            *command,
        ]

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        command = self._coerce_command(arguments.get("command"))
        return await self._run_command(
            context,
            command=command,
            cwd=arguments.get("cwd"),
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=120,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="shell",
        )


class RunDevServerTool(SandboxExecTool):
    spec = ToolSpec(
        name="run_dev_server",
        description="Start a long-running development server inside the configured sandbox runner and return a managed session id.",
        input_schema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                "ports": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 65535}},
                "health_check_url": {"type": "string"},
                "startup_timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="dev_server", access_level="execute", side_effect="process", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.policy.runner_configured:
            raise RuntimeError("sandbox runner is not configured")
        await self._reap_expired_sessions()
        command = self._coerce_command(arguments.get("command"))
        resolved_cwd, relative_cwd = self._resolve_cwd(context, arguments.get("cwd"))
        timeout = _clamp_int(
            arguments.get("timeout_seconds"),
            default=1_200,
            minimum=1,
            maximum=self.policy.max_timeout_seconds,
        )
        if self.policy.runner_backend != "local_subprocess":
            return {
                "status": "failed",
                "failure_category": "unsupported_backend",
                "message": "long-running process sessions are only supported by local_subprocess in this runtime build",
                "recovery": build_failure_recovery("sandbox-exec", "unsupported_backend"),
                "runner": {"backend": self.policy.runner_backend},
                "command": command,
                "cwd": relative_cwd,
            }

        ports = []
        for raw_port in arguments.get("ports") or []:
            port = _clamp_int(raw_port, default=0, minimum=0, maximum=65535)
            if port > 0 and port not in ports:
                ports.append(port)
        health_check_url = str(arguments.get("health_check_url") or "").strip() or None
        startup_timeout = _clamp_int(arguments.get("startup_timeout_seconds"), default=2, minimum=1, maximum=60)
        session_id = f"sandbox-session-{uuid.uuid4().hex}"
        log_dir = self._session_log_dir(context)
        stdout_path = log_dir / f"{session_id}.stdout.log"
        stderr_path = log_dir / f"{session_id}.stderr.log"
        stdout_handle = stdout_path.open("ab")
        stderr_handle = stderr_path.open("ab")
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(resolved_cwd),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
        stdout_handle.close()
        stderr_handle.close()
        self.sessions[session_id] = SandboxProcessSession(
            session_id=session_id,
            process=process,
            command=command,
            cwd=relative_cwd,
            started_at=time.monotonic(),
            purpose="dev_server",
            timeout_seconds=timeout,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            exposed_ports=ports,
            health_check_url=health_check_url,
        )
        health_check = {"configured": False}
        if health_check_url:
            deadline = time.monotonic() + startup_timeout
            while time.monotonic() < deadline:
                health_check = await self._probe_health_check(health_check_url, timeout_seconds=1)
                if health_check.get("status") == "healthy":
                    break
                await asyncio.sleep(0.2)
        browser_verify_hint = None
        if ports:
            browser_verify_hint = {
                "enabled": True,
                "session_id": session_id,
                "suggested_url": f"http://127.0.0.1:{ports[0]}",
                "health_check_url": health_check_url,
                "recommended_follow_up": "Use browser_verify against the suggested_url after the dev server reports healthy.",
            }
        return {
            "status": "running",
            "session_id": session_id,
            "pid": process.pid,
            "command": command,
            "cwd": relative_cwd,
            "timeout_seconds": timeout,
            "runner": {"backend": self.policy.runner_backend},
            "purpose": "dev_server",
            "ports": ports,
            "health_check": health_check,
            "browser_verify_hint": browser_verify_hint,
            "logs": {
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            },
        }


class ProcessLogsTool(SandboxExecTool):
    spec = ToolSpec(
        name="process_logs",
        description="Read stdout/stderr tails for a managed long-running sandbox process session.",
        input_schema={
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
                "stream": {"type": "string", "enum": ["stdout", "stderr", "both"]},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="process_logs", access_level="read", side_effect="none", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._reap_expired_sessions()
        session_id = str(arguments.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        session = self.sessions.get(session_id)
        if session is None:
            return {
                "status": "not_found",
                "session_id": session_id,
                "failure_category": "unknown_session",
                "recovery": build_failure_recovery("sandbox-exec", "unknown_session"),
            }

        max_chars = _clamp_int(arguments.get("max_chars"), default=20_000, minimum=100, maximum=100_000)
        stream = str(arguments.get("stream") or "both").strip().lower() or "both"
        if stream not in {"stdout", "stderr", "both"}:
            raise ValueError("stream must be stdout, stderr, or both")
        stdout = ("", False, 0)
        stderr = ("", False, 0)
        if stream in {"stdout", "both"}:
            stdout = self._read_log_tail(session.stdout_path, max_chars=max_chars)
        if stream in {"stderr", "both"}:
            stderr = self._read_log_tail(session.stderr_path, max_chars=max_chars)
        exit_code = session.process.returncode
        status = "timeout" if session.timed_out else "running" if exit_code is None else "completed" if exit_code == 0 else "failed"
        return {
            "status": "completed",
            "session_id": session_id,
            "process_status": status,
            "exit_code": exit_code,
            "stream": stream,
            "stdout": stdout[0],
            "stderr": stderr[0],
            "truncated": stdout[1] or stderr[1],
            "log_sizes": {"stdout_bytes": stdout[2], "stderr_bytes": stderr[2]},
            "runner": {"backend": self.policy.runner_backend},
        }


class ProcessListTool(SandboxExecTool):
    spec = ToolSpec(
        name="process_list",
        description="List managed long-running sandbox process sessions for this runtime worker.",
        input_schema={"type": "object", "properties": {}},
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="process", access_level="read", side_effect="none", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._reap_expired_sessions()
        sessions = []
        for session_id, session in sorted(self.sessions.items()):
            exit_code = session.process.returncode
            status = "timeout" if session.timed_out else "running" if exit_code is None else "completed" if exit_code == 0 else "failed"
            sessions.append(
                {
                    "session_id": session_id,
                    "status": status,
                    "pid": session.process.pid,
                    "command": session.command,
                    "cwd": session.cwd,
                    "purpose": session.purpose,
                    "duration_ms": int((time.monotonic() - session.started_at) * 1000),
                    "exit_code": exit_code,
                    "timeout_seconds": session.timeout_seconds,
                    "ports": session.exposed_ports or [],
                    "health_check_url": session.health_check_url,
                    "logs_available": bool(session.stdout_path or session.stderr_path),
                }
            )
        return {
            "status": "completed",
            "runner": {"backend": self.policy.runner_backend},
            "processes": sessions,
            "process_count": len(sessions),
        }


class ProcessStopTool(SandboxExecTool):
    spec = ToolSpec(
        name="process_stop",
        description="Stop a managed long-running sandbox process session by session id.",
        input_schema={
            "type": "object",
            "required": ["session_id"],
            "properties": {"session_id": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30}},
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="process", access_level="execute", side_effect="process", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._reap_expired_sessions()
        session_id = str(arguments.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        session = self.sessions.get(session_id)
        if session is None:
            return {
                "status": "not_found",
                "session_id": session_id,
                "stopped": False,
                "failure_category": "unknown_session",
                "recovery": build_failure_recovery("sandbox-exec", "unknown_session"),
            }

        timeout = _clamp_int(arguments.get("timeout_seconds"), default=5, minimum=1, maximum=30)
        if session.process.returncode is None:
            await self._terminate_session(session, timeout=timeout)
        exit_code = session.process.returncode
        self.sessions.pop(session_id, None)
        return {
            "status": "completed",
            "session_id": session_id,
            "stopped": True,
            "exit_code": exit_code,
            "runner": {"backend": self.policy.runner_backend},
        }


def _has_any(root: Path, names: Sequence[str]) -> bool:
    return any(root.joinpath(name).exists() for name in names)


def _python_bin() -> str:
    return os.getenv("AGENT_SANDBOX_PYTHON_BIN") or sys.executable or "python"


def _append_selector(command: list[str], selector: str | None) -> list[str]:
    selector_text = str(selector or "").strip()
    if not selector_text:
        return command
    return [*command, selector_text]


def _workspace_has_any(root: Path, names: Sequence[str]) -> list[str]:
    return [name for name in names if root.joinpath(name).exists()]


def _read_text_file(path: Path, *, max_chars: int = 20_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        return ""


def _safe_relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.name


def _coerce_report_int(value: Any) -> int:
    try:
        return int(float(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _coerce_report_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _severity_from_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("error", "failed", "failure", "traceback")):
        return "error"
    if any(token in lowered for token in ("warning", "warn")):
        return "warning"
    return "info"


def _parse_junit_xml_reports(workspace_root: Path, *, max_files: int = 8, max_failures: int = 50) -> dict[str, Any] | None:
    candidates: list[Path] = []
    for pattern in ("junit*.xml", "*junit*.xml", "test-results/**/*.xml", "reports/**/*.xml"):
        candidates.extend(path for path in workspace_root.glob(pattern) if path.is_file())

    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(path)

    if not unique_candidates:
        return None

    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failure_items: list[dict[str, Any]] = []
    report_files: list[str] = []
    for path in unique_candidates[:max_files]:
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError):
            continue
        report_files.append(_safe_relative_path(path, workspace_root))
        suites = [root] if root.tag.endswith("testsuite") else [item for item in root.iter() if item.tag.endswith("testsuite")]
        for suite in suites:
            totals["tests"] += _coerce_report_int(suite.attrib.get("tests"))
            totals["failures"] += _coerce_report_int(suite.attrib.get("failures"))
            totals["errors"] += _coerce_report_int(suite.attrib.get("errors"))
            totals["skipped"] += _coerce_report_int(suite.attrib.get("skipped"))
        for testcase in root.iter():
            if not testcase.tag.endswith("testcase"):
                continue
            failures = [child for child in testcase if child.tag.endswith("failure") or child.tag.endswith("error")]
            if not failures:
                continue
            for failure in failures:
                if len(failure_items) >= max_failures:
                    break
                classname = testcase.attrib.get("classname") or ""
                name = testcase.attrib.get("name") or "testcase"
                message = failure.attrib.get("message") or (failure.text or "").strip().splitlines()[0:1]
                if isinstance(message, list):
                    message = message[0] if message else ""
                failure_items.append(
                    {
                        "title": f"{classname + '.' if classname else ''}{name}",
                        "severity": "error",
                        "message": str(message or "").strip(),
                        "type": "test_failure" if failure.tag.endswith("failure") else "test_error",
                        "suite": classname,
                        "duration_seconds": _coerce_report_float(testcase.attrib.get("time")),
                        "source": _safe_relative_path(path, workspace_root),
                    }
                )
            if len(failure_items) >= max_failures:
                break

    if not report_files:
        return None
    return {
        "format": "junit_xml",
        "summary": totals,
        "failures": failure_items,
        "files": report_files,
        "truncated": len(unique_candidates) > max_files or len(failure_items) >= max_failures,
    }


_PYTEST_FAILED_RE = re.compile(r"^(FAILED|ERROR)\s+([^\s]+)(?:\s+-\s+(.*))?$", re.MULTILINE)
_PYTEST_SUMMARY_RE = re.compile(
    r"(?P<count>\d+)\s+(?P<label>passed|failed|errors?|skipped|xfailed|xpassed|warnings?)",
    re.IGNORECASE,
)
_RUFF_RE = re.compile(r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<column>\d+):\s+(?P<code>[A-Z]+\d+)\s+(?P<message>.+)$")
_GENERIC_LOCATION_RE = re.compile(r"^(?P<path>[^:\n]+):(?P<line>\d+)(?::(?P<column>\d+))?:\s+(?P<message>.+)$")
_COVERAGE_ROW_RE = re.compile(r"^(?P<name>\S.*?)\s+(?P<stmts>\d+)\s+(?P<miss>\d+)\s+(?:(?P<branch>\d+)\s+(?P<brpart>\d+)\s+)?(?P<cover>\d+(?:\.\d+)?)%")


def _parse_pytest_text(text: str, *, max_failures: int = 50) -> dict[str, Any] | None:
    summary: dict[str, int] = {}
    for match in _PYTEST_SUMMARY_RE.finditer(text):
        label = match.group("label").lower()
        if label == "error":
            label = "errors"
        elif label == "warning":
            label = "warnings"
        summary[label] = summary.get(label, 0) + int(match.group("count"))

    failures = []
    for match in _PYTEST_FAILED_RE.finditer(text):
        if len(failures) >= max_failures:
            break
        failures.append(
            {
                "title": match.group(2),
                "severity": "error",
                "message": (match.group(3) or "").strip(),
                "type": "test_failure" if match.group(1) == "FAILED" else "test_error",
            }
        )

    if not summary and not failures:
        return None
    return {
        "format": "pytest_text",
        "summary": summary,
        "failures": failures,
        "truncated": len(failures) >= max_failures,
    }


def _parse_lint_text(text: str, *, max_findings: int = 100) -> dict[str, Any] | None:
    findings: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _RUFF_RE.match(line) or _GENERIC_LOCATION_RE.match(line)
        if not match:
            continue
        groups = match.groupdict()
        message = groups.get("message") or line
        findings.append(
            {
                "title": message[:120],
                "severity": _severity_from_text(message),
                "message": message,
                "path": groups.get("path"),
                "line": _coerce_report_int(groups.get("line")),
                "column": _coerce_report_int(groups.get("column")),
                "code": groups.get("code"),
            }
        )
        if len(findings) >= max_findings:
            break
    if not findings:
        return None
    counts: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity") or "info")
        counts[severity] = counts.get(severity, 0) + 1
    return {
        "format": "lint_text",
        "summary": {"finding_count": len(findings), "severity_counts": counts},
        "findings": findings,
        "truncated": len(findings) >= max_findings,
    }


def _parse_coverage_text(text: str, *, max_files: int = 100) -> dict[str, Any] | None:
    files: list[dict[str, Any]] = []
    total_percent: float | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _COVERAGE_ROW_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        percent = _coerce_report_float(row.get("cover"))
        entry = {
            "path": row["name"],
            "statements": _coerce_report_int(row.get("stmts")),
            "missing": _coerce_report_int(row.get("miss")),
            "coverage_percent": percent,
        }
        if row.get("name", "").upper() == "TOTAL":
            total_percent = percent
        else:
            files.append(entry)
        if len(files) >= max_files:
            break
    if total_percent is None and not files:
        return None
    return {
        "format": "coverage_text",
        "summary": {
            "coverage_percent": total_percent,
            "file_count": len(files),
        },
        "files": files,
        "truncated": len(files) >= max_files,
    }


def _parse_dependency_audit(stdout: str, stderr: str) -> dict[str, Any] | None:
    text = stdout.strip() or stderr.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        vulnerabilities = payload.get("vulnerabilities") if isinstance(payload.get("vulnerabilities"), dict) else {}
        findings = []
        for name, entry in list(vulnerabilities.items())[:100]:
            if not isinstance(entry, dict):
                continue
            findings.append(
                {
                    "title": str(name),
                    "severity": str(entry.get("severity") or "info"),
                    "message": str(entry.get("title") or entry.get("name") or name),
                    "package": str(name),
                    "via": entry.get("via"),
                    "range": entry.get("range"),
                    "fix_available": entry.get("fixAvailable"),
                }
            )
        return {
            "format": "npm_audit_json",
            "summary": {
                "vulnerabilities": metadata.get("vulnerabilities") or {},
                "dependency_count": metadata.get("dependencies", {}).get("total") if isinstance(metadata.get("dependencies"), dict) else None,
                "finding_count": len(findings),
            },
            "findings": findings,
            "truncated": len(vulnerabilities) > len(findings),
        }

    pip_conflicts = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if " has requirement " in stripped or " is not installed" in stripped:
            pip_conflicts.append({"title": stripped[:120], "severity": "error", "message": stripped})
    if pip_conflicts or "No broken requirements found" in text:
        return {
            "format": "pip_check_text",
            "summary": {"finding_count": len(pip_conflicts), "healthy": not pip_conflicts},
            "findings": pip_conflicts[:100],
            "truncated": len(pip_conflicts) > 100,
        }
    return None


def _build_structured_verification_report(
    *,
    workspace_root: Path,
    purpose: str,
    command: Sequence[str],
    stdout: str,
    stderr: str,
    status: str,
    exit_code: int | None,
) -> dict[str, Any] | None:
    text = "\n".join(item for item in (stdout, stderr) if item)
    reports: list[dict[str, Any]] = []
    if purpose in {"test", "coverage"}:
        junit_report = _parse_junit_xml_reports(workspace_root)
        if junit_report:
            reports.append({"kind": "test", **junit_report})
        pytest_report = _parse_pytest_text(text)
        if pytest_report:
            reports.append({"kind": "test", **pytest_report})
    if purpose in {"lint", "typecheck"}:
        lint_report = _parse_lint_text(text)
        if lint_report:
            reports.append({"kind": purpose, **lint_report})
    if purpose == "coverage":
        coverage_report = _parse_coverage_text(text)
        if coverage_report:
            reports.append({"kind": "coverage", **coverage_report})
    if purpose == "dependency_audit":
        audit_report = _parse_dependency_audit(stdout, stderr)
        if audit_report:
            reports.append({"kind": "dependency_audit", **audit_report})

    if not reports:
        return None

    summary: dict[str, Any] = {
        "status": status,
        "exit_code": exit_code,
        "command_text": _command_label(command),
        "report_count": len(reports),
    }
    for report in reports:
        if report.get("kind") == "coverage" and isinstance(report.get("summary"), dict):
            summary["coverage_percent"] = report["summary"].get("coverage_percent")
        if report.get("kind") in {"lint", "typecheck", "dependency_audit"} and isinstance(report.get("summary"), dict):
            summary["finding_count"] = report["summary"].get("finding_count")
    return {
        "schema_version": "verification_report.v1",
        "summary": summary,
        "reports": reports,
        "truncated": any(bool(report.get("truncated")) for report in reports),
    }


def _has_package_script(workspace_root: Path, script_name: str) -> bool:
    import json

    package_json = workspace_root / "package.json"
    if not package_json.exists():
        return False
    try:
        payload = json.loads(_read_text_file(package_json))
    except ValueError:
        return False
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    return isinstance(scripts, dict) and isinstance(scripts.get(script_name), str) and bool(scripts.get(script_name, "").strip())


def _has_python_dependency(workspace_root: Path, dependency_name: str) -> bool:
    needle = dependency_name.lower()
    candidates = [
        workspace_root / "pyproject.toml",
        workspace_root / "setup.cfg",
        workspace_root / "setup.py",
        workspace_root / "requirements.txt",
        workspace_root / "requirements-dev.txt",
        workspace_root / "dev-requirements.txt",
    ]
    return any(needle in _read_text_file(path).lower() for path in candidates if path.exists())


def _pytest_command(selector: str | None = None) -> list[str]:
    return _append_selector([_python_bin(), "-m", "pytest"], selector)


def _node_test_command(workspace_root: Path, selector: str | None = None) -> list[str]:
    command = ["npm", "test"]
    selector_text = str(selector or "").strip()
    if selector_text:
        command = [*command, "--", selector_text]
    return command


def _go_test_command(selector: str | None = None) -> list[str]:
    selector_text = str(selector or "./...").strip() or "./..."
    return ["go", "test", selector_text]


def _command_label(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _detect_project_capabilities(workspace_root: Path) -> dict[str, Any]:
    manifests = _workspace_has_any(
        workspace_root,
        (
            "pyproject.toml",
            "pytest.ini",
            "setup.cfg",
            "tox.ini",
            "requirements.txt",
            "package.json",
            "go.mod",
            "Makefile",
        ),
    )
    languages = []
    if any(name in manifests for name in ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "requirements.txt")) or (workspace_root / "tests").exists():
        languages.append("python")
    if "package.json" in manifests:
        languages.append("node")
    if "go.mod" in manifests:
        languages.append("go")
    return {"languages": languages, "manifests": manifests}


def _discover_test_plan(workspace_root: Path, selector: str | None = None) -> dict[str, Any]:
    capabilities = _detect_project_capabilities(workspace_root)
    commands: list[dict[str, Any]] = []
    if "python" in capabilities["languages"]:
        commands.append(
            {
                "kind": "test",
                "ecosystem": "python",
                "command": _pytest_command(selector),
                "confidence": "high" if (workspace_root / "tests").exists() else "medium",
                "reason": "Detected pytest-compatible Python project files or tests directory.",
            }
        )
    if "node" in capabilities["languages"]:
        commands.append(
            {
                "kind": "test",
                "ecosystem": "node",
                "command": _node_test_command(workspace_root, selector),
                "confidence": "high" if _has_package_script(workspace_root, "test") else "medium",
                "reason": "Detected package.json.",
            }
        )
    if "go" in capabilities["languages"]:
        commands.append(
            {
                "kind": "test",
                "ecosystem": "go",
                "command": _go_test_command(selector),
                "confidence": "high",
                "reason": "Detected go.mod.",
            }
        )
    return {**capabilities, "commands": commands}


def _choose_test_command(workspace_root: Path, selector: str | None = None, ecosystem: str | None = None) -> list[str]:
    requested = str(ecosystem or "auto").strip().lower() or "auto"
    if requested in {"auto", "python"} and (
        _has_any(workspace_root, ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")) or (workspace_root / "tests").exists()
    ):
        return _pytest_command(selector)
    if requested in {"auto", "node", "javascript", "typescript"} and (workspace_root / "package.json").exists():
        return _node_test_command(workspace_root, selector)
    if requested in {"auto", "go"} and (workspace_root / "go.mod").exists():
        return _go_test_command(selector)
    raise ValueError("no supported test command was discovered for this workspace")


def _choose_lint_command(workspace_root: Path, target: str | None = None, ecosystem: str | None = None) -> list[str]:
    requested = str(ecosystem or "auto").strip().lower() or "auto"
    target_text = str(target or ".").strip() or "."
    if requested in {"auto", "node", "javascript", "typescript"} and (workspace_root / "package.json").exists():
        return ["npm", "run", "lint", "--", target_text]
    if requested in {"auto", "go"} and (workspace_root / "go.mod").exists():
        return ["go", "vet", target_text if target_text != "." else "./..."]
    if requested in {"auto", "python"} and _has_any(workspace_root, ("pyproject.toml", "setup.cfg", "ruff.toml", ".ruff.toml")):
        return [_python_bin(), "-m", "ruff", "check", target_text]
    raise ValueError("no supported lint command was discovered for this workspace")


def _choose_typecheck_command(workspace_root: Path, target: str | None = None, ecosystem: str | None = None) -> list[str]:
    requested = str(ecosystem or "auto").strip().lower() or "auto"
    target_text = str(target or ".").strip() or "."
    if requested in {"auto", "node", "javascript", "typescript"} and (workspace_root / "package.json").exists():
        if _has_package_script(workspace_root, "typecheck"):
            return ["npm", "run", "typecheck", "--", target_text]
        if (workspace_root / "tsconfig.json").exists():
            return ["npx", "tsc", "--noEmit"]
    if requested in {"auto", "go"} and (workspace_root / "go.mod").exists():
        return ["go", "test", target_text if target_text != "." else "./..."]
    if requested in {"auto", "python"} and _has_python_dependency(workspace_root, "mypy"):
        return [_python_bin(), "-m", "mypy", target_text]
    if requested in {"auto", "python"} and _has_python_dependency(workspace_root, "pyright"):
        return [_python_bin(), "-m", "pyright", target_text]
    raise ValueError("no supported typecheck command was discovered for this workspace")


def _choose_coverage_command(workspace_root: Path, selector: str | None = None, ecosystem: str | None = None) -> list[str]:
    requested = str(ecosystem or "auto").strip().lower() or "auto"
    if requested in {"auto", "node", "javascript", "typescript"} and (workspace_root / "package.json").exists():
        if _has_package_script(workspace_root, "coverage"):
            return ["npm", "run", "coverage"]
        return ["npm", "test", "--", "--coverage"]
    if requested in {"auto", "go"} and (workspace_root / "go.mod").exists():
        target = str(selector or "./...").strip() or "./..."
        return ["go", "test", "-cover", target]
    if requested in {"auto", "python"} and (
        _has_any(workspace_root, ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")) or (workspace_root / "tests").exists()
    ):
        if _has_python_dependency(workspace_root, "pytest-cov"):
            return [*_pytest_command(selector), "--cov=.", "--cov-report=term-missing"]
        if _has_python_dependency(workspace_root, "coverage"):
            return [_python_bin(), "-m", "coverage", "run", "-m", "pytest", *( [str(selector).strip()] if str(selector or "").strip() else [] )]
        return [*_pytest_command(selector), "--cov=.", "--cov-report=term-missing"]
    raise ValueError("no supported coverage command was discovered for this workspace")


def _choose_dependency_audit_command(workspace_root: Path, ecosystem: str | None = None) -> list[str]:
    requested = str(ecosystem or "auto").strip().lower() or "auto"
    if requested in {"auto", "node", "javascript", "typescript"} and (workspace_root / "package.json").exists():
        return ["npm", "audit", "--json"]
    if requested in {"auto", "go"} and (workspace_root / "go.mod").exists():
        return ["go", "list", "-m", "-u", "-json", "all"]
    if requested in {"auto", "python"} and _has_any(workspace_root, ("requirements.txt", "pyproject.toml")):
        return [_python_bin(), "-m", "pip", "check"]
    raise ValueError("no supported dependency audit command was discovered for this workspace")


class ShellExecTool(SandboxExecTool):
    spec = ToolSpec(
        name="shell_exec",
        description="Execute a command inside a configured sandbox runner. The skeleton is hidden until a runner is configured.",
        input_schema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(),
    )


class RunTestsTool(SandboxExecTool):
    spec = ToolSpec(
        name="run_tests",
        description="Run project tests inside a configured sandbox runner. The skeleton is hidden until a runner is configured.",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="test", risk_level="medium"),
    )

    def _discover_command(self, workspace_root: Path, selector: str | None) -> list[str]:
        return _choose_test_command(workspace_root, selector)

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        command = self._discover_command(workspace_root, arguments.get("selector"))
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=300,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="test",
        )
        result["selector"] = str(arguments.get("selector") or "").strip() or None
        return result


class RunLintTool(SandboxExecTool):
    spec = ToolSpec(
        name="run_lint",
        description="Run project lint checks inside a configured sandbox runner. The skeleton is hidden until a runner is configured.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="lint", risk_level="medium"),
    )

    def _discover_command(self, workspace_root: Path, target: str | None) -> list[str]:
        return _choose_lint_command(workspace_root, target)

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        command = self._discover_command(workspace_root, arguments.get("target"))
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=180,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="lint",
        )
        result["target"] = str(arguments.get("target") or ".").strip() or "."
        return result


class RunBuildTool(SandboxExecTool):
    spec = ToolSpec(
        name="run_build",
        description="Run a project build inside a configured sandbox runner. The skeleton is hidden until a runner is configured.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 1200},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="build", risk_level="medium"),
    )

    def _discover_command(self, workspace_root: Path, target: str | None) -> list[str]:
        target_text = str(target or "").strip()
        if (workspace_root / "package.json").exists():
            return ["npm", "run", target_text or "build"]
        if (workspace_root / "Makefile").exists():
            return ["make", target_text or "build"]
        if (workspace_root / "go.mod").exists():
            return ["go", "build", target_text or "./..."]
        if (workspace_root / "pyproject.toml").exists():
            return [_python_bin(), "-m", "build"]
        raise ValueError("no supported build command was discovered for this workspace")

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        command = self._discover_command(workspace_root, arguments.get("target"))
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=600,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="build",
        )
        result["target"] = str(arguments.get("target") or "").strip() or None
        return result


class TestDiscoverTool(SandboxExecTool):
    spec = ToolSpec(
        name="test_discover",
        description="Discover supported test, lint, typecheck, coverage, and dependency audit commands for the current workspace without executing them.",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="test_discovery", access_level="read", side_effect="none", risk_level="low"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        selector = str(arguments.get("selector") or "").strip() or None
        plan = _discover_test_plan(workspace_root, selector)
        probes: list[tuple[str, Any]] = [
            ("lint", lambda: _choose_lint_command(workspace_root)),
            ("typecheck", lambda: _choose_typecheck_command(workspace_root)),
            ("coverage", lambda: _choose_coverage_command(workspace_root, selector)),
            ("dependency_audit", lambda: _choose_dependency_audit_command(workspace_root)),
        ]
        for kind, factory in probes:
            try:
                command = factory()
            except ValueError as exc:
                plan["commands"].append(
                    {
                        "kind": kind,
                        "ecosystem": "auto",
                        "command": [],
                        "confidence": "none",
                        "reason": str(exc),
                        "available": False,
                    }
                )
                continue
            plan["commands"].append(
                {
                    "kind": kind,
                    "ecosystem": "auto",
                    "command": command,
                    "command_text": _command_label(command),
                    "confidence": "medium",
                    "reason": f"Detected a supported {kind} command.",
                    "available": True,
                }
            )
        for command in plan["commands"]:
            command.setdefault("available", bool(command.get("command")))
            command.setdefault("command_text", _command_label(command.get("command") or []))
        return {
            "status": "completed",
            "purpose": "test_discovery",
            "workspace": {"root": str(workspace_root), "manifests": plan["manifests"], "languages": plan["languages"]},
            "commands": plan["commands"],
            "command_count": len([command for command in plan["commands"] if command.get("available")]),
            "selector": selector,
        }


class TestRunTool(SandboxExecTool):
    spec = ToolSpec(
        name="test_run",
        description="Run discovered project tests inside the configured sandbox runner and return a structured verification report.",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "ecosystem": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="test", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        selector = str(arguments.get("selector") or "").strip() or None
        ecosystem = str(arguments.get("ecosystem") or "auto").strip() or "auto"
        command = _choose_test_command(workspace_root, selector, ecosystem)
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=300,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="test",
        )
        result.update({"selector": selector, "ecosystem": ecosystem, "report_format": "plain_text"})
        return result


class LintRunTool(SandboxExecTool):
    spec = ToolSpec(
        name="lint_run",
        description="Run discovered lint checks inside the configured sandbox runner and return structured status plus logs.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "ecosystem": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="lint", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        target = str(arguments.get("target") or ".").strip() or "."
        ecosystem = str(arguments.get("ecosystem") or "auto").strip() or "auto"
        command = _choose_lint_command(workspace_root, target, ecosystem)
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=180,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="lint",
        )
        result.update({"target": target, "ecosystem": ecosystem, "report_format": "plain_text"})
        return result


class TypecheckRunTool(SandboxExecTool):
    spec = ToolSpec(
        name="typecheck_run",
        description="Run discovered static type checks inside the configured sandbox runner.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "ecosystem": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="typecheck", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        target = str(arguments.get("target") or ".").strip() or "."
        ecosystem = str(arguments.get("ecosystem") or "auto").strip() or "auto"
        command = _choose_typecheck_command(workspace_root, target, ecosystem)
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=300,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="typecheck",
        )
        result.update({"target": target, "ecosystem": ecosystem, "report_format": "plain_text"})
        return result


class CoverageRunTool(SandboxExecTool):
    spec = ToolSpec(
        name="coverage_run",
        description="Run discovered project coverage checks inside the configured sandbox runner.",
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "ecosystem": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 1200},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="coverage", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        selector = str(arguments.get("selector") or "").strip() or None
        ecosystem = str(arguments.get("ecosystem") or "auto").strip() or "auto"
        command = _choose_coverage_command(workspace_root, selector, ecosystem)
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=600,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="coverage",
        )
        result.update({"selector": selector, "ecosystem": ecosystem, "report_format": "plain_text"})
        return result


class DependencyAuditTool(SandboxExecTool):
    spec = ToolSpec(
        name="dependency_audit",
        description="Run a supported dependency audit or dependency health check inside the configured sandbox runner.",
        input_schema={
            "type": "object",
            "properties": {
                "ecosystem": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
            },
        },
        kind="sandbox-exec",
        metadata=_tool_metadata(capability="dependency_audit", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        ecosystem = str(arguments.get("ecosystem") or "auto").strip() or "auto"
        command = _choose_dependency_audit_command(workspace_root, ecosystem)
        result = await self._run_command(
            context,
            command=command,
            cwd=".",
            timeout_seconds=arguments.get("timeout_seconds"),
            default_timeout_seconds=300,
            max_output_chars=arguments.get("max_output_chars"),
            purpose="dependency_audit",
        )
        result.update({"ecosystem": ecosystem, "report_format": "plain_text"})
        return result


class SandboxIsolationCheckTool(SandboxExecTool):
    spec = ToolSpec(
        name="sandbox_isolation_check",
        description="Return the configured sandbox runner isolation profile, resource limits, and production readiness checks without executing user code.",
        input_schema={"type": "object", "properties": {}},
        kind="sandbox-exec",
        metadata=_tool_metadata(
            capability="sandbox_governance",
            access_level="read",
            side_effect="none",
            risk_level="low",
            requires_workspace=False,
            requires_sandbox=False,
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context, arguments
        profile = build_sandbox_isolation_profile(self.policy)
        return {
            "status": "completed",
            "purpose": "sandbox_isolation_check",
            "profile": profile,
            "production_ready": profile["production_ready"],
            "runner": {
                "backend": self.policy.runner_backend,
                "configured": self.policy.runner_configured,
                "image": self.policy.docker_image if self.policy.runner_backend == "docker" else None,
            },
            "recovery_actions": profile["recovery_actions"],
        }


SANDBOX_EXEC_TOOL_TYPES = {
    "sandbox_isolation_check": SandboxIsolationCheckTool,
    "shell_exec": ShellExecTool,
    "run_tests": RunTestsTool,
    "run_lint": RunLintTool,
    "run_build": RunBuildTool,
    "test_discover": TestDiscoverTool,
    "test_run": TestRunTool,
    "lint_run": LintRunTool,
    "typecheck_run": TypecheckRunTool,
    "coverage_run": CoverageRunTool,
    "dependency_audit": DependencyAuditTool,
    "run_dev_server": RunDevServerTool,
    "process_logs": ProcessLogsTool,
    "process_list": ProcessListTool,
    "process_stop": ProcessStopTool,
}


class SandboxExecToolProvider:
    def __init__(
        self,
        *,
        enabled_tool_names: Sequence[str],
        runner_configured: bool = False,
        runner_backend: str = "local_subprocess",
        docker_image: str = DEFAULT_DOCKER_IMAGE,
        docker_network: str = "none",
        docker_memory: str = "1g",
        docker_cpus: str = "1",
        docker_pids_limit: int = DEFAULT_DOCKER_PIDS_LIMIT,
        docker_read_only_rootfs: bool = True,
        docker_tmpfs_mounts: Sequence[str] | None = None,
        docker_drop_capabilities: Sequence[str] | None = None,
        max_output_chars: int = 40_000,
        max_timeout_seconds: int = 1_200,
        deny_commands: Sequence[str] | None = None,
    ) -> None:
        self.enabled_tool_names = [name for name in enabled_tool_names if name in SANDBOX_EXEC_TOOL_TYPES]
        self.sessions: dict[str, SandboxProcessSession] = {}
        self.policy = SandboxExecPolicy(
            runner_configured=runner_configured,
            runner_backend=runner_backend,
            docker_image=docker_image,
            docker_network=docker_network,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            docker_pids_limit=docker_pids_limit,
            docker_read_only_rootfs=docker_read_only_rootfs,
            docker_tmpfs_mounts=tuple(DEFAULT_DOCKER_TMPFS_MOUNTS if docker_tmpfs_mounts is None else docker_tmpfs_mounts),
            docker_drop_capabilities=tuple(DEFAULT_DOCKER_DROP_CAPABILITIES if docker_drop_capabilities is None else docker_drop_capabilities),
            max_output_chars=max_output_chars,
            max_timeout_seconds=max_timeout_seconds,
            deny_commands=tuple(deny_commands or DEFAULT_DENY_COMMANDS),
        )

    @classmethod
    def from_env(cls) -> "SandboxExecToolProvider":
        enabled_tool_names = _parse_csv(os.getenv("AGENT_SANDBOX_EXEC_TOOLS"), DEFAULT_SANDBOX_EXEC_TOOL_NAMES)
        runner_configured = str(os.getenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "")).strip().lower() in {"1", "true", "yes", "on"}
        runner_backend = str(os.getenv("AGENT_SANDBOX_RUNNER_BACKEND") or "docker").strip() or "docker"
        docker_image = str(os.getenv("AGENT_SANDBOX_DOCKER_IMAGE") or DEFAULT_DOCKER_IMAGE).strip() or DEFAULT_DOCKER_IMAGE
        docker_network = str(os.getenv("AGENT_SANDBOX_DOCKER_NETWORK") or "none").strip() or "none"
        docker_memory = str(os.getenv("AGENT_SANDBOX_DOCKER_MEMORY") or "1g").strip() or "1g"
        docker_cpus = str(os.getenv("AGENT_SANDBOX_DOCKER_CPUS") or "1").strip() or "1"
        docker_pids_limit = _clamp_int(
            os.getenv("AGENT_SANDBOX_DOCKER_PIDS_LIMIT"),
            default=DEFAULT_DOCKER_PIDS_LIMIT,
            minimum=1,
            maximum=4096,
        )
        docker_read_only_rootfs = _parse_bool(os.getenv("AGENT_SANDBOX_DOCKER_READ_ONLY_ROOTFS"), True)
        docker_tmpfs_mounts = _parse_csv(os.getenv("AGENT_SANDBOX_DOCKER_TMPFS"), DEFAULT_DOCKER_TMPFS_MOUNTS)
        docker_drop_capabilities = _parse_csv(os.getenv("AGENT_SANDBOX_DOCKER_CAP_DROP"), DEFAULT_DOCKER_DROP_CAPABILITIES)
        max_output_chars = _clamp_int(os.getenv("AGENT_SANDBOX_MAX_OUTPUT_CHARS"), default=40_000, minimum=1_000, maximum=200_000)
        max_timeout_seconds = _clamp_int(os.getenv("AGENT_SANDBOX_MAX_TIMEOUT_SECONDS"), default=1_200, minimum=1, maximum=3_600)
        deny_commands = _parse_csv(os.getenv("AGENT_SANDBOX_DENY_COMMANDS"), DEFAULT_DENY_COMMANDS)
        return cls(
            enabled_tool_names=enabled_tool_names,
            runner_configured=runner_configured,
            runner_backend=runner_backend,
            docker_image=docker_image,
            docker_network=docker_network,
            docker_memory=docker_memory,
            docker_cpus=docker_cpus,
            docker_pids_limit=docker_pids_limit,
            docker_read_only_rootfs=docker_read_only_rootfs,
            docker_tmpfs_mounts=docker_tmpfs_mounts,
            docker_drop_capabilities=docker_drop_capabilities,
            max_output_chars=max_output_chars,
            max_timeout_seconds=max_timeout_seconds,
            deny_commands=deny_commands,
        )

    def _build_tool(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        if not self.policy.runner_configured:
            return None
        tool_type = SANDBOX_EXEC_TOOL_TYPES.get(name)
        if tool_type is None or name not in self.enabled_tool_names:
            return None
        return tool_type(self.policy, self.sessions)

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        return self._build_tool(name, context=context)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = self._build_tool(name, context=context)
        if tool is None:
            return None
        if isinstance(tool, SandboxExecTool):
            return tool.spec_dict()
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": tool.spec.metadata,
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        items = []
        for name in self.enabled_tool_names:
            spec = await self.get_spec(name, context=context)
            if spec is not None:
                items.append(spec)
        return items
