"""Loader for builtin tools — wraps legacy builtin provider tools as BaseTool.

The legacy module at ``ai_runtime.core.agent_runtime.tools.providers.builtin``
exposes:
- ``GetCurrentTimeTool``
- ``CalculatorTool``
- ``EchoJSONTool``
- ``register_builtin_tools(registry)``

This loader imports those classes, instantiates them, and wraps each via
``legacy_to_base_tool`` to produce LangChain-native ``BaseTool`` instances.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

# Expected tool count for smoke tests.
EXPECTED_TOOL_COUNT = 3


def load_tools():
    """Load and wrap legacy builtin tools. Returns list of BaseTool."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.builtin import (  # type: ignore[import]
            GetCurrentTimeTool,
            CalculatorTool,
            EchoJSONTool,
        )
    except ImportError:
        logger.warning(
            "builtin loader: legacy module not available; no tools loaded"
        )
        return []

    legacy_tools = [
        GetCurrentTimeTool(),
        CalculatorTool(),
        EchoJSONTool(),
    ]
    return [legacy_to_base_tool(t) for t in legacy_tools]


def register_into(registry: "ToolRegistry") -> int:
    """Register all builtin tools into the given registry.

    Returns the number of tools registered.
    """
    tools = load_tools()
    for tool in tools:
        registry.register(tool, kind="builtin", provider="builtin", risk_level="low")
    return len(tools)
