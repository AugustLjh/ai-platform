"""Smoke tests for each provider loader.

Each provider has a ``register_into(registry)`` function that imports the
legacy provider module, instantiates each tool, wraps via
``legacy_to_base_tool``, and registers the wrapped tools into a
:class:`ToolRegistry`. These tests verify the expected number of tools is
registered.

If the legacy module is unavailable (e.g. when the worktree does not include
``core/agent_runtime/``), the loaders return 0 tools rather than crashing —
the tests assert the count matches the expected value when legacy is
available, otherwise verifies "0 tools but no error".
"""
from __future__ import annotations

import importlib
import pytest

from ai_runtime.tools.registry import ToolRegistry


def _legacy_available(provider_name: str) -> bool:
    try:
        importlib.import_module(
            f"ai_runtime.core.agent_runtime.tools.providers.{provider_name}"
        )
        return True
    except ImportError:
        return False


class TestBuiltinLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.builtin import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("builtin"):
            assert count == EXPECTED_TOOL_COUNT
            assert "get_current_time" in reg
            assert "calculator" in reg
            assert "echo_json" in reg
        else:
            assert count == 0


class TestKnowledgeLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.knowledge import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("knowledge"):
            assert count == EXPECTED_TOOL_COUNT
            assert "knowledge_search" in reg
            assert "knowledge_fetch_document" in reg
            assert "knowledge_fetch_segments" in reg
        else:
            assert count == 0


class TestWorkspaceLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.workspace import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("workspace"):
            # All tools should register; some may fail at construction time and
            # be skipped, but we expect at least the count matches.
            assert count == EXPECTED_TOOL_COUNT
            assert "workspace_list_files" in reg
        else:
            assert count == 0


class TestSandboxExecLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.sandbox_exec import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("sandbox_exec"):
            assert count == EXPECTED_TOOL_COUNT
            assert "shell_exec" in reg
            assert "run_tests" in reg
        else:
            assert count == 0


class TestWebLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.web import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("web"):
            assert count == EXPECTED_TOOL_COUNT
            assert "fetch_url" in reg
            assert "web_search" in reg
        else:
            assert count == 0


class TestEngineeringLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.engineering import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("engineering"):
            assert count == EXPECTED_TOOL_COUNT
            assert "project_list_context" in reg
        else:
            assert count == 0


class TestObservabilityLoader:
    def test_register_into_runs_without_error(self):
        from ai_runtime.tools.observability import register_into, EXPECTED_TOOL_COUNT
        reg = ToolRegistry()
        count = register_into(reg)
        if _legacy_available("observability"):
            assert count == EXPECTED_TOOL_COUNT
            assert "db_query_readonly" in reg
            assert "metrics_query" in reg
        else:
            assert count == 0


class TestAllLoadersTogether:
    """Regression: registering every provider produces a non-overlapping set."""

    def test_combined_registration(self):
        from ai_runtime.tools.builtin import register_into as bi
        from ai_runtime.tools.knowledge import register_into as kn
        from ai_runtime.tools.workspace import register_into as ws
        from ai_runtime.tools.sandbox_exec import register_into as sb
        from ai_runtime.tools.web import register_into as we
        from ai_runtime.tools.engineering import register_into as en
        from ai_runtime.tools.observability import register_into as ob

        reg = ToolRegistry()
        bi(reg)
        kn(reg)
        ws(reg)
        sb(reg)
        we(reg)
        en(reg)
        ob(reg)
        # Whatever count we got, there should be no name collisions.
        assert len(reg) == len(reg.tool_names)
        # Specs iterable should yield one per registered tool.
        assert len(list(reg.iter_specs())) == len(reg)
