"""Loader for sandbox_exec tools — wraps legacy sandbox execution tools as BaseTool.

The legacy ``sandbox_exec.py`` module exposes ``SANDBOX_EXEC_TOOL_TYPES`` (15 tools
including shell_exec, run_tests, run_lint, etc). This loader instantiates each
with a default policy and wraps via ``legacy_to_base_tool``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

# Count from SANDBOX_EXEC_TOOL_TYPES in legacy sandbox_exec.py.
EXPECTED_TOOL_COUNT = 15


def load_tools():
    """Load and wrap legacy sandbox execution tools."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.sandbox_exec import (  # type: ignore[import]
            SANDBOX_EXEC_TOOL_TYPES,
            SandboxExecPolicy,
        )
    except ImportError:
        logger.warning(
            "sandbox_exec loader: legacy module not available; no tools loaded"
        )
        return []

    try:
        policy = SandboxExecPolicy(
            runner_configured=False,
        )
    except Exception:
        logger.warning(
            "sandbox_exec loader: failed to build default policy", exc_info=True
        )
        return []

    base_tools = []
    for name, tool_cls in SANDBOX_EXEC_TOOL_TYPES.items():
        try:
            legacy_tool = tool_cls(policy)
        except Exception:
            logger.debug(
                "sandbox_exec loader: failed to instantiate %s", name, exc_info=True
            )
            continue
        base_tools.append(legacy_to_base_tool(legacy_tool))
    return base_tools


def register_into(registry: "ToolRegistry") -> int:
    tools = load_tools()
    for tool in tools:
        registry.register(
            tool,
            kind="sandbox_exec",
            provider="sandbox-exec",
            requires_sandbox=True,
            risk_level="high",
            metadata={"capability": "code_execution"},
        )
    return len(tools)
