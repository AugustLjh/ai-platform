"""ai_runtime.tools — LangChain-native tools layer.

Exports the core types (``AiPlatformTool``, ``ToolContext``, ``ToolRegistry``)
so consumers can import directly from the package root.
"""
from ai_runtime.tools.base import (
    AiPlatformTool,
    ToolContext,
    current_tool_context,
    current_tool_context_optional,
)
from ai_runtime.tools.caching import ToolResultCache, cached_tool
from ai_runtime.tools.from_legacy import legacy_to_base_tool
from ai_runtime.tools.registry import ToolRegistration, ToolRegistry

__all__ = [
    "AiPlatformTool",
    "ToolContext",
    "ToolRegistry",
    "ToolRegistration",
    "ToolResultCache",
    "cached_tool",
    "current_tool_context",
    "current_tool_context_optional",
    "legacy_to_base_tool",
]
