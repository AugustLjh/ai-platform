import sys
from pathlib import Path

import pytest

from ai_runtime.core.agent_runtime.tools.base import ToolContext
from ai_runtime.core.agent_runtime.tools.base import ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.sandbox_exec import SandboxExecToolProvider, build_sandbox_isolation_profile


def _context(workspace_root: Path) -> ToolContext:
    return ToolContext(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        workspace_root=str(workspace_root),
    )


async def test_sandbox_exec_provider_hides_tools_until_runner_is_configured():
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec", "run_tests"], runner_configured=False)

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root="/tmp/workspace"))

    assert specs == []
    assert await provider.get("shell_exec", context=None) is None


async def test_sandbox_exec_provider_exposes_policy_metadata_when_configured():
    provider = SandboxExecToolProvider(
        enabled_tool_names=[
            "sandbox_isolation_check",
            "shell_exec",
            "run_tests",
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
        ],
        runner_configured=True,
    )

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root="/tmp/workspace"))
    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}

    assert {
        "shell_exec",
        "run_tests",
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
        "sandbox_isolation_check",
    } == set(metadata_by_name)
    assert metadata_by_name["shell_exec"]["provider"] == "sandbox-exec"
    assert metadata_by_name["shell_exec"]["requires_workspace"] is True
    assert metadata_by_name["shell_exec"]["requires_sandbox"] is True
    assert metadata_by_name["shell_exec"]["side_effect"] == "process"
    assert metadata_by_name["shell_exec"]["risk_level"] == "high"
    assert metadata_by_name["shell_exec"]["failure_taxonomy"]["provider"] == "sandbox-exec"
    assert {
        item["category"] for item in metadata_by_name["shell_exec"]["failure_taxonomy"]["categories"]
    } >= {"timeout", "non_zero_exit", "runner_unavailable", "unsupported_backend", "unknown_session"}
    assert metadata_by_name["run_tests"]["capability"] == "test"
    assert metadata_by_name["test_discover"]["capability"] == "test_discovery"
    assert metadata_by_name["test_discover"]["access_level"] == "read"
    assert metadata_by_name["typecheck_run"]["capability"] == "typecheck"
    assert metadata_by_name["coverage_run"]["capability"] == "coverage"
    assert metadata_by_name["dependency_audit"]["capability"] == "dependency_audit"
    assert metadata_by_name["process_logs"]["capability"] == "process_logs"
    assert metadata_by_name["process_logs"]["access_level"] == "read"
    assert metadata_by_name["process_list"]["access_level"] == "read"
    assert metadata_by_name["process_stop"]["side_effect"] == "process"
    assert metadata_by_name["sandbox_isolation_check"]["capability"] == "sandbox_governance"
    assert metadata_by_name["sandbox_isolation_check"]["requires_workspace"] is False


async def test_sandbox_exec_provider_prefers_env_tool_list(monkeypatch):
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_TOOLS", "run_lint")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")

    provider = SandboxExecToolProvider.from_env()
    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", workspace_root="/tmp/workspace"))

    assert [spec["name"] for spec in specs] == ["run_lint"]


async def test_shell_exec_runs_inside_workspace_and_returns_structured_result(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(
        _context(workspace),
        {
            "command": [sys.executable, "-c", "from pathlib import Path; Path('out.txt').write_text('ok'); print(Path.cwd().name)"],
            "timeout_seconds": 5,
        },
    )

    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["purpose"] == "shell"
    assert result["cwd"] == "."
    assert "workspace" in result["stdout"]
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "ok"


async def test_shell_exec_rejects_cwd_escape_and_denied_command(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": [sys.executable, "-c", "print('x')"], "cwd": "../outside"})

    with pytest.raises(PermissionError):
        await tool.execute(_context(workspace), {"command": ["sudo", "true"]})


async def test_shell_exec_timeout_kills_process(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(enabled_tool_names=["shell_exec"], runner_configured=True)
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(
        _context(workspace),
        {"command": [sys.executable, "-c", "import time; time.sleep(2)"], "timeout_seconds": 1},
    )

    assert result["status"] == "timeout"
    assert result["exit_code"] is None
    assert result["failure_category"] == "timeout"
    assert result["recovery"]["primary_code"] == "sandbox_exec_timeout"
    assert result["recovery"]["recoverable"] is True


async def test_run_tests_discovers_pytest_and_reports_failure(tmp_path):
    workspace = tmp_path / "workspace"
    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_sample.py").write_text(
        "def test_sample_failure():\n    assert False\n",
        encoding="utf-8",
    )
    provider = SandboxExecToolProvider(enabled_tool_names=["run_tests"], runner_configured=True)
    tool = await provider.get("run_tests", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"selector": "tests/test_sample.py", "timeout_seconds": 20})

    assert result["purpose"] == "test"
    assert result["status"] == "failed"
    assert result["exit_code"] != 0
    assert result["failure_category"] == "non_zero_exit"
    assert result["recovery"]["primary_code"] == "sandbox_exec_non_zero_exit"
    assert "test_sample_failure" in result["stdout"]
    assert result["structured_report"]["schema_version"] == "verification_report.v1"
    assert result["structured_report"]["summary"]["report_count"] >= 1
    text_report = next(report for report in result["structured_report"]["reports"] if report["format"] == "pytest_text")
    assert text_report["kind"] == "test"
    assert text_report["summary"]["failed"] == 1
    assert text_report["failures"][0]["title"] == "tests/test_sample.py::test_sample_failure"


async def test_run_tests_parses_junit_xml_reports(tmp_path):
    workspace = tmp_path / "workspace"
    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True)
    (workspace / "junit-results.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="sample" tests="2" failures="1" errors="0" skipped="1">
  <testcase classname="tests.test_sample" name="test_ok" time="0.01" />
  <testcase classname="tests.test_sample" name="test_bad" time="0.02">
    <failure message="expected true">assert False</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["run_tests"], runner_configured=True)
    tool = await provider.get("run_tests", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"selector": "tests/test_sample.py", "timeout_seconds": 20})

    junit_report = next(report for report in result["structured_report"]["reports"] if report["format"] == "junit_xml")
    assert junit_report["summary"]["tests"] == 2
    assert junit_report["summary"]["failures"] == 1
    assert junit_report["failures"][0]["title"] == "tests.test_sample.test_bad"
    assert junit_report["files"] == ["junit-results.xml"]


async def test_run_build_discovers_make_target(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Makefile").write_text("build:\n\t@echo built\n", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["run_build"], runner_configured=True)
    tool = await provider.get("run_build", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"target": "build", "timeout_seconds": 10})

    assert result["purpose"] == "build"
    assert result["status"] == "completed"
    assert "built" in result["stdout"]


async def test_test_discover_returns_verification_plan_without_executing(tmp_path):
    workspace = tmp_path / "workspace"
    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True)
    (workspace / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["test_discover"], runner_configured=True)
    tool = await provider.get("test_discover", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"selector": "tests/test_sample.py"})

    assert result["status"] == "completed"
    assert result["purpose"] == "test_discovery"
    assert result["workspace"]["languages"] == ["python"]
    assert result["command_count"] >= 1
    test_command = next(command for command in result["commands"] if command["kind"] == "test")
    assert test_command["available"] is True
    assert "pytest" in test_command["command_text"]
    assert test_command["command"][-1] == "tests/test_sample.py"


async def test_test_run_executes_discovered_pytest_command(tmp_path):
    workspace = tmp_path / "workspace"
    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["test_run"], runner_configured=True)
    tool = await provider.get("test_run", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"selector": "tests/test_sample.py", "timeout_seconds": 20})

    assert result["purpose"] == "test"
    assert result["status"] == "completed"
    assert result["selector"] == "tests/test_sample.py"
    assert result["ecosystem"] == "auto"
    assert result["report_format"] == "plain_text"


async def test_typecheck_run_discovers_python_pyright_dependency(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "requirements.txt").write_text("pyright==1.1.0\n", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["typecheck_run"], runner_configured=True)
    tool = await provider.get("typecheck_run", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"target": ".", "timeout_seconds": 20})

    assert result["purpose"] == "typecheck"
    assert result["command"][1:] == ["-m", "pyright", "."]
    assert result["target"] == "."
    assert result["report_format"] == "plain_text"
    assert result["status"] in {"failed", "completed"}


async def test_lint_run_parses_structured_findings(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[tool.ruff]\nline-length = 88\n", encoding="utf-8")
    (workspace / "sample.py").write_text("import os\n", encoding="utf-8")
    (workspace / "ruff.py").write_text(
        "import sys\nprint('sample.py:1:1: F401 unused import')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    provider = SandboxExecToolProvider(enabled_tool_names=["lint_run"], runner_configured=True)
    tool = await provider.get("lint_run", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"target": "sample.py", "timeout_seconds": 20})

    assert result["purpose"] == "lint"
    lint_report = next(report for report in result["structured_report"]["reports"] if report["kind"] == "lint")
    assert lint_report["summary"]["finding_count"] == 1
    assert lint_report["findings"][0]["path"] == "sample.py"
    assert lint_report["findings"][0]["line"] == 1


async def test_coverage_run_parses_terminal_coverage_summary(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "tests").mkdir()
    (workspace / "requirements.txt").write_text("pytest-cov\n", encoding="utf-8")
    (workspace / "pytest.py").write_text(
        "print('Name      Stmts   Miss  Cover')\n"
        "print('-----------------------------')\n"
        "print('sample.py     2      0   100%')\n"
        "print('TOTAL         2      0   100%')\n",
        encoding="utf-8",
    )
    provider = SandboxExecToolProvider(enabled_tool_names=["coverage_run"], runner_configured=True)
    tool = await provider.get("coverage_run", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"selector": "tests/test_sample.py", "timeout_seconds": 30})

    assert result["purpose"] == "coverage"
    coverage_report = next(report for report in result["structured_report"]["reports"] if report["kind"] == "coverage")
    assert coverage_report["summary"]["coverage_percent"] == 100.0
    assert any(file["path"] == "sample.py" for file in coverage_report["files"])


async def test_dependency_audit_runs_python_pip_check(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "requirements.txt").write_text("", encoding="utf-8")
    provider = SandboxExecToolProvider(enabled_tool_names=["dependency_audit"], runner_configured=True)
    tool = await provider.get("dependency_audit", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"timeout_seconds": 20})

    assert result["purpose"] == "dependency_audit"
    assert result["command"][1:] == ["-m", "pip", "check"]
    assert result["ecosystem"] == "auto"
    assert result["report_format"] == "plain_text"


async def test_sandbox_exec_env_configures_runner_limits(monkeypatch):
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_TOOLS", "shell_exec")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.delenv("AGENT_SANDBOX_RUNNER_BACKEND", raising=False)
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_IMAGE", "python:3.12-alpine")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_NETWORK", "none")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_MEMORY", "512m")
    monkeypatch.setenv("AGENT_SANDBOX_DOCKER_CPUS", "0.5")
    monkeypatch.setenv("AGENT_SANDBOX_MAX_OUTPUT_CHARS", "1234")
    monkeypatch.setenv("AGENT_SANDBOX_MAX_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("AGENT_SANDBOX_DENY_COMMANDS", "sudo,python")

    provider = SandboxExecToolProvider.from_env()

    assert provider.policy.runner_configured is True
    assert provider.policy.runner_backend == "docker"
    assert provider.policy.docker_image == "python:3.12-alpine"
    assert provider.policy.docker_memory == "512m"
    assert provider.policy.docker_cpus == "0.5"
    assert provider.policy.docker_pids_limit == 256
    assert provider.policy.docker_read_only_rootfs is True
    assert provider.policy.docker_tmpfs_mounts[0].startswith("/tmp:")
    assert provider.policy.docker_drop_capabilities == ("ALL",)
    assert provider.policy.max_output_chars == 1234
    assert provider.policy.max_timeout_seconds == 7
    assert provider.policy.deny_commands == ("sudo", "python")


async def test_sandbox_exec_env_can_select_local_subprocess_for_development(monkeypatch):
    monkeypatch.setenv("AGENT_SANDBOX_EXEC_TOOLS", "shell_exec")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_SANDBOX_RUNNER_BACKEND", "local_subprocess")

    provider = SandboxExecToolProvider.from_env()

    assert provider.policy.runner_backend == "local_subprocess"


async def test_sandbox_isolation_profile_marks_default_docker_runner_ready():
    provider = SandboxExecToolProvider(
        enabled_tool_names=["sandbox_isolation_check"],
        runner_configured=True,
        runner_backend="docker",
    )

    profile = build_sandbox_isolation_profile(provider.policy)

    assert profile["status"] == "ready"
    assert profile["production_ready"] is True
    assert profile["failed"] == 0
    assert profile["warning"] == 0
    assert profile["limits"]["docker"]["network"] == "none"
    assert profile["limits"]["docker"]["pids_limit"] == 256


async def test_sandbox_isolation_profile_reports_unsafe_docker_limits():
    provider = SandboxExecToolProvider(
        enabled_tool_names=["sandbox_isolation_check"],
        runner_configured=True,
        runner_backend="docker",
        docker_network="bridge",
        docker_pids_limit=2048,
        docker_read_only_rootfs=False,
        docker_drop_capabilities=["NET_RAW"],
        docker_tmpfs_mounts=[],
    )

    profile = build_sandbox_isolation_profile(provider.policy)
    checks_by_key = {check["key"]: check for check in profile["checks"]}

    assert profile["status"] == "failed"
    assert profile["production_ready"] is False
    assert checks_by_key["docker_network"]["status"] == "fail"
    assert checks_by_key["docker_pids_limit"]["status"] == "fail"
    assert checks_by_key["docker_drop_capabilities"]["status"] == "fail"
    assert checks_by_key["docker_read_only_rootfs"]["status"] == "warn"
    assert checks_by_key["docker_tmpfs"]["status"] == "warn"


async def test_sandbox_isolation_check_tool_returns_profile_without_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["sandbox_isolation_check"],
        runner_configured=True,
        runner_backend="docker",
    )
    tool = await provider.get("sandbox_isolation_check", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=None))
    assert tool is not None

    result = await tool.execute(_context(workspace), {})

    assert result["status"] == "completed"
    assert result["purpose"] == "sandbox_isolation_check"
    assert result["production_ready"] is True
    assert result["profile"]["status"] == "ready"


async def test_run_dev_server_process_list_and_stop_manage_session(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_list", "process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup_context = ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace))
    run_dev_server = await provider.get("run_dev_server", context=lookup_context)
    process_list = await provider.get("process_list", context=lookup_context)
    process_stop = await provider.get("process_stop", context=lookup_context)
    assert run_dev_server is not None
    assert process_list is not None
    assert process_stop is not None

    started = await run_dev_server.execute(
        _context(workspace),
        {"command": [sys.executable, "-c", "import time; time.sleep(30)"], "timeout_seconds": 30},
    )
    listed = await process_list.execute(_context(workspace), {})
    stopped = await process_stop.execute(_context(workspace), {"session_id": started["session_id"], "timeout_seconds": 2})
    listed_after_stop = await process_list.execute(_context(workspace), {})

    assert started["status"] == "running"
    assert started["session_id"].startswith("sandbox-session-")
    assert listed["process_count"] == 1
    assert listed["processes"][0]["session_id"] == started["session_id"]
    assert listed["processes"][0]["status"] == "running"
    assert stopped["status"] == "completed"
    assert stopped["stopped"] is True
    assert listed_after_stop["process_count"] == 0


async def test_run_dev_server_captures_logs_and_process_logs_returns_tail(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_logs", "process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup_context = ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace))
    run_dev_server = await provider.get("run_dev_server", context=lookup_context)
    process_logs = await provider.get("process_logs", context=lookup_context)
    process_stop = await provider.get("process_stop", context=lookup_context)
    assert run_dev_server is not None
    assert process_logs is not None
    assert process_stop is not None

    started = await run_dev_server.execute(
        _context(workspace),
        {
            "command": [
                sys.executable,
                "-c",
                "import sys,time; print('ready', flush=True); print('warn', file=sys.stderr, flush=True); time.sleep(30)",
            ],
            "timeout_seconds": 30,
            "ports": [8000, 8000],
        },
    )
    import asyncio

    await asyncio.sleep(0.2)
    logs = await process_logs.execute(_context(workspace), {"session_id": started["session_id"], "max_chars": 100})
    await process_stop.execute(_context(workspace), {"session_id": started["session_id"], "timeout_seconds": 2})

    assert started["ports"] == [8000]
    assert started["logs"]["stdout_path"].endswith(".stdout.log")
    assert started["browser_verify_hint"]["enabled"] is True
    assert started["browser_verify_hint"]["suggested_url"] == "http://127.0.0.1:8000"
    assert logs["process_status"] == "running"
    assert "ready" in logs["stdout"]
    assert "warn" in logs["stderr"]


async def test_process_list_reaps_timed_out_sessions(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_list"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup_context = ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace))
    run_dev_server = await provider.get("run_dev_server", context=lookup_context)
    process_list = await provider.get("process_list", context=lookup_context)
    assert run_dev_server is not None
    assert process_list is not None

    await run_dev_server.execute(
        _context(workspace),
        {"command": [sys.executable, "-c", "import time; time.sleep(30)"], "timeout_seconds": 1},
    )
    import asyncio

    await asyncio.sleep(1.2)
    listed = await process_list.execute(_context(workspace), {})

    assert listed["process_count"] == 1
    assert listed["processes"][0]["status"] == "timeout"
    assert listed["processes"][0]["exit_code"] is not None


async def test_process_logs_unknown_session_returns_structured_not_found(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["process_logs"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    tool = await provider.get("process_logs", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"session_id": "missing-session"})

    assert result["status"] == "not_found"
    assert result["failure_category"] == "unknown_session"
    assert result["recovery"]["primary_code"] == "sandbox_exec_unknown_session"


async def test_run_dev_server_blocks_non_local_health_check_url(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server", "process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    lookup_context = ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace))
    run_dev_server = await provider.get("run_dev_server", context=lookup_context)
    process_stop = await provider.get("process_stop", context=lookup_context)
    assert run_dev_server is not None
    assert process_stop is not None

    started = await run_dev_server.execute(
        _context(workspace),
        {
            "command": [sys.executable, "-c", "import time; time.sleep(30)"],
            "timeout_seconds": 30,
            "health_check_url": "https://example.com/health",
        },
    )
    await process_stop.execute(_context(workspace), {"session_id": started["session_id"], "timeout_seconds": 2})

    assert started["health_check"]["status"] == "blocked"
    assert "localhost" in started["health_check"]["error"]


async def test_process_stop_unknown_session_returns_structured_not_found(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["process_stop"],
        runner_configured=True,
        runner_backend="local_subprocess",
    )
    tool = await provider.get("process_stop", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"session_id": "missing-session"})

    assert result["status"] == "not_found"
    assert result["stopped"] is False
    assert result["failure_category"] == "unknown_session"
    assert result["recovery"]["primary_code"] == "sandbox_exec_unknown_session"


async def test_run_dev_server_returns_unsupported_for_docker_sessions(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = SandboxExecToolProvider(
        enabled_tool_names=["run_dev_server"],
        runner_configured=True,
        runner_backend="docker",
    )
    tool = await provider.get("run_dev_server", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"command": ["python", "-m", "http.server"]})

    assert result["status"] == "failed"
    assert result["failure_category"] == "unsupported_backend"
    assert result["recovery"]["primary_code"] == "sandbox_exec_unsupported_backend"
    assert result["runner"]["backend"] == "docker"


async def test_docker_runner_missing_executable_returns_structured_failure(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    provider = SandboxExecToolProvider(
        enabled_tool_names=["shell_exec"],
        runner_configured=True,
        runner_backend="docker",
        docker_image="python:3.12-slim",
    )
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    result = await tool.execute(_context(workspace), {"command": ["python", "-c", "print('ok')"]})

    assert result["status"] == "failed"
    assert result["failure_category"] == "runner_unavailable"
    assert result["recovery"]["primary_code"] == "sandbox_exec_runner_unavailable"
    assert "executable not found" in result["stderr"]


async def test_docker_runner_command_includes_production_isolation_flags(tmp_path):
    workspace = tmp_path / "workspace"
    subdir = workspace / "pkg"
    subdir.mkdir(parents=True)
    provider = SandboxExecToolProvider(
        enabled_tool_names=["shell_exec"],
        runner_configured=True,
        runner_backend="docker",
        docker_image="python:3.12-slim",
        docker_memory="512m",
        docker_cpus="0.5",
        docker_pids_limit=128,
        docker_tmpfs_mounts=["/tmp:rw,noexec,nosuid,size=64m"],
    )
    tool = await provider.get("shell_exec", context=ToolLookupContext(tenant_id="tenant-1", workspace_root=str(workspace)))
    assert tool is not None

    command = tool._build_process_command(
        command=["python", "-c", "print('ok')"],
        workspace_root=workspace.resolve(strict=True),
        resolved_cwd=subdir.resolve(strict=True),
        container_name="sandbox-test",
    )

    assert command[:5] == ["docker", "run", "--rm", "--name", "sandbox-test"]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--memory") + 1] == "512m"
    assert command[command.index("--cpus") + 1] == "0.5"
    assert command[command.index("--pids-limit") + 1] == "128"
    assert "--read-only" in command
    assert "--security-opt" in command
    assert "no-new-privileges" in command
    assert "--cap-drop" in command
    assert "ALL" in command
    assert "--tmpfs" in command
    assert "/tmp:rw,noexec,nosuid,size=64m" in command
    assert command[command.index("-w") + 1] == "/workspace/pkg"
