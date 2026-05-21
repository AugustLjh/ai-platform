"""GA hardening: Sandbox Docker runner validation tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.sandbox_exec import (
    SandboxExecPolicy,
    SandboxExecToolProvider,
    build_sandbox_isolation_profile,
)


def _context(workspace_root: Path) -> ToolContext:
    return ToolContext(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        workspace_root=str(workspace_root),
    )


# --- Escape testing ---


async def test_path_traversal_via_cwd_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": [sys.executable, "-c", "print(1)"], "cwd": "../outside"})


async def test_path_traversal_via_dotdot_segments_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": [sys.executable, "-c", "print(1)"], "cwd": "../../.."})


async def test_absolute_cwd_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": [sys.executable, "-c", "print(1)"], "cwd": "/tmp"})


async def test_symlink_escape_via_cwd_is_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "escape"
    link.symlink_to(outside)
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": [sys.executable, "-c", "print(1)"], "cwd": "escape"})


async def test_command_injection_via_denied_commands(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    for cmd in ["sudo", "docker", "kubectl", "shutdown", "reboot", "mount", "dd"]:
        with pytest.raises(PermissionError):
            await tool.execute(_context(workspace), {"command": [cmd, "--help"]})


async def test_empty_command_is_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(ValueError):
        await tool.execute(_context(workspace), {"command": []})


async def test_nul_byte_in_command_is_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    with pytest.raises(ValueError):
        await tool.execute(_context(workspace), {"command": ["echo\x00injected"]})


# --- Network isolation testing ---


async def test_docker_network_none_in_isolation_profile():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_network="none")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_network"]["status"] == "pass"
    assert checks_by_key["docker_network"]["actual"] == "none"


async def test_docker_network_bridge_fails_isolation():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_network="bridge")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_network"]["status"] == "fail"
    assert profile["production_ready"] is False


async def test_docker_network_host_fails_isolation():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_network="host")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_network"]["status"] == "fail"


# --- PID/CPU/memory limit testing ---


async def test_pids_limit_within_range_passes():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_pids_limit=256)
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_pids_limit"]["status"] == "pass"


async def test_pids_limit_too_high_fails():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_pids_limit=1024)
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_pids_limit"]["status"] == "fail"


async def test_memory_limit_missing_fails():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_memory="")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_memory"]["status"] == "fail"


async def test_cpu_limit_missing_fails():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_cpus="")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_cpus"]["status"] == "fail"


async def test_cap_drop_all_passes():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_drop_capabilities=("ALL",))
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_drop_capabilities"]["status"] == "pass"


async def test_cap_drop_partial_fails():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_drop_capabilities=("NET_RAW",))
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_drop_capabilities"]["status"] == "fail"


async def test_read_only_rootfs_warn_when_disabled():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_read_only_rootfs=False)
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_read_only_rootfs"]["status"] == "warn"


async def test_tmpfs_mount_present_passes():
    policy = SandboxExecPolicy(
        runner_configured=True,
        runner_backend="docker",
        docker_tmpfs_mounts=("/tmp:rw,noexec,nosuid,size=128m", "/run:rw,noexec,nosuid,size=32m"),
    )
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_tmpfs"]["status"] == "pass"


async def test_tmpfs_mount_missing_warns():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="docker", docker_tmpfs_mounts=())
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["docker_tmpfs"]["status"] == "warn"


# --- Concurrent execution testing ---


async def test_concurrent_shell_exec_sessions_do_not_interfere(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    async def run_session(index: int):
        return await tool.execute(
            _context(workspace),
            {
                "command": [sys.executable, "-c", f"from pathlib import Path; Path('out_{index}.txt').write_text('{index}'); print({index})"],
                "timeout_seconds": 10,
            },
        )

    results = await asyncio.gather(*[run_session(i) for i in range(5)])

    for i, result in enumerate(results):
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert str(i) in result["stdout"]
        assert (workspace / f"out_{i}.txt").read_text() == str(i)


async def test_concurrent_sessions_have_independent_cwd(tmp_path):
    workspace = tmp_path / "workspace"
    sub_a = workspace / "dir_a"
    sub_b = workspace / "dir_b"
    sub_a.mkdir(parents=True)
    sub_b.mkdir(parents=True)
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="t", workspace_root=str(workspace)))

    result_a, result_b = await asyncio.gather(
        tool.execute(_context(workspace), {"command": [sys.executable, "-c", "import os; print(os.getcwd())"], "cwd": "dir_a"}),
        tool.execute(_context(workspace), {"command": [sys.executable, "-c", "import os; print(os.getcwd())"], "cwd": "dir_b"}),
    )

    assert "dir_a" in result_a["stdout"]
    assert "dir_b" in result_b["stdout"]


# --- Dev server cleanup testing ---


async def test_dev_server_timeout_cleans_up_session(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_list"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup = ToolLookupContext(tenant_id="t", workspace_root=str(workspace))
    dev_server = await provider.get("run_dev_server", context=lookup)
    process_list = await provider.get("process_list", context=lookup)

    started = await dev_server.execute(
        _context(workspace),
        {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout_seconds": 1},
    )

    await asyncio.sleep(2.0)
    listed = await process_list.execute(_context(workspace), {})

    assert started["status"] == "running"
    # After timeout, the session should either be marked timed_out or removed from active list
    # The process_list returns sessions that have been reaped with status != "running"
    active_running = [p for p in listed.get("processes", []) if p.get("status") == "running" and p["session_id"] == started["session_id"]]
    assert len(active_running) == 0


async def test_dev_server_explicit_stop_cleans_up(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_list", "process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup = ToolLookupContext(tenant_id="t", workspace_root=str(workspace))
    dev_server = await provider.get("run_dev_server", context=lookup)
    process_list = await provider.get("process_list", context=lookup)
    process_stop = await provider.get("process_stop", context=lookup)

    started = await dev_server.execute(
        _context(workspace),
        {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout_seconds": 60},
    )
    assert started["status"] == "running"

    stopped = await process_stop.execute(_context(workspace), {"session_id": started["session_id"], "timeout_seconds": 3})
    assert stopped["stopped"] is True

    listed = await process_list.execute(_context(workspace), {})
    active = [p for p in listed.get("processes", []) if p["session_id"] == started["session_id"]]
    assert len(active) == 0


async def test_multiple_dev_servers_can_be_stopped_independently(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_list", "process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup = ToolLookupContext(tenant_id="t", workspace_root=str(workspace))
    dev_server = await provider.get("run_dev_server", context=lookup)
    process_list = await provider.get("process_list", context=lookup)
    process_stop = await provider.get("process_stop", context=lookup)

    s1 = await dev_server.execute(_context(workspace), {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout_seconds": 60})
    s2 = await dev_server.execute(_context(workspace), {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeout_seconds": 60})

    listed = await process_list.execute(_context(workspace), {})
    assert listed["process_count"] == 2

    await process_stop.execute(_context(workspace), {"session_id": s1["session_id"], "timeout_seconds": 3})
    listed_after = await process_list.execute(_context(workspace), {})
    assert listed_after["process_count"] == 1
    assert listed_after["processes"][0]["session_id"] == s2["session_id"]

    await process_stop.execute(_context(workspace), {"session_id": s2["session_id"], "timeout_seconds": 3})
    listed_final = await process_list.execute(_context(workspace), {})
    assert listed_final["process_count"] == 0


# --- Full isolation profile validation ---


async def test_full_production_ready_profile():
    policy = SandboxExecPolicy(
        runner_configured=True,
        runner_backend="docker",
        docker_network="none",
        docker_memory="1g",
        docker_cpus="1",
        docker_pids_limit=256,
        docker_read_only_rootfs=True,
        docker_tmpfs_mounts=("/tmp:rw,noexec,nosuid,size=128m", "/run:rw,noexec,nosuid,size=32m"),
        docker_drop_capabilities=("ALL",),
    )
    profile = build_sandbox_isolation_profile(policy)

    assert profile["status"] == "ready"
    assert profile["production_ready"] is True
    assert profile["failed"] == 0
    assert profile["warning"] == 0
    assert all(c["status"] == "pass" for c in profile["checks"])


async def test_local_subprocess_is_not_production_ready():
    policy = SandboxExecPolicy(runner_configured=True, runner_backend="local_subprocess")
    profile = build_sandbox_isolation_profile(policy)

    assert profile["production_ready"] is False


async def test_unconfigured_runner_fails_isolation():
    policy = SandboxExecPolicy(runner_configured=False, runner_backend="docker")
    profile = build_sandbox_isolation_profile(policy)

    checks_by_key = {c["key"]: c for c in profile["checks"]}
    assert checks_by_key["runner_configured"]["status"] == "fail"
    assert profile["status"] == "failed"
