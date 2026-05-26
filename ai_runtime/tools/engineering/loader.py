"""Loader for engineering / project-context tools.

The legacy ``engineering.py`` module exposes ``ENGINEERING_TOOL_TYPES`` (6
project-context tools). These tools take no constructor arguments — they pull
configuration from the dependency-injection container at execute time.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

EXPECTED_TOOL_COUNT = 6


def load_tools():
    """Load and wrap legacy engineering / project-context tools."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.engineering import (  # type: ignore[import]
            ENGINEERING_TOOL_TYPES,
        )
    except ImportError:
        logger.warning(
            "engineering loader: legacy module not available; no tools loaded"
        )
        return []

    base_tools = []
    for name, tool_cls in ENGINEERING_TOOL_TYPES.items():
        try:
            legacy_tool = tool_cls()
        except Exception:
            logger.debug(
                "engineering loader: failed to instantiate %s", name, exc_info=True
            )
            continue
        base_tools.append(legacy_to_base_tool(legacy_tool))
    return base_tools


def register_into(registry: "ToolRegistry") -> int:
    tools = load_tools()
    for tool in tools:
        registry.register(
            tool,
            kind="engineering",
            provider="project-context",
            risk_level="low",
            metadata={"capability": "project_context"},
        )
    return len(tools)
