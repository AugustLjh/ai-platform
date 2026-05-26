"""Loader for knowledge tools — wraps legacy knowledge provider tools as BaseTool.

The legacy ``KnowledgeToolProvider`` exposes a fixed set of tool classes:
- ``KnowledgeSearchTool``
- ``KnowledgeFetchDocumentTool``
- ``KnowledgeFetchSegmentsTool``

This loader instantiates each and wraps via ``legacy_to_base_tool``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

EXPECTED_TOOL_COUNT = 3


def load_tools():
    """Load and wrap legacy knowledge tools."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.knowledge import (  # type: ignore[import]
            KnowledgeSearchTool,
            KnowledgeFetchDocumentTool,
            KnowledgeFetchSegmentsTool,
        )
    except ImportError:
        logger.warning(
            "knowledge loader: legacy module not available; no tools loaded"
        )
        return []

    legacy_tools = [
        KnowledgeSearchTool(),
        KnowledgeFetchDocumentTool(),
        KnowledgeFetchSegmentsTool(),
    ]
    return [legacy_to_base_tool(t) for t in legacy_tools]


def register_into(registry: "ToolRegistry") -> int:
    tools = load_tools()
    for tool in tools:
        registry.register(
            tool,
            kind="knowledge",
            provider="knowledge",
            risk_level="low",
            metadata={"capability": "knowledge_search"},
        )
    return len(tools)
