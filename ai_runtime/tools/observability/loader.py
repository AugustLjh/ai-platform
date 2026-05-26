"""Loader for observability tools — wraps legacy observability provider tools.

The legacy ``observability.py`` module exposes ``OBSERVABILITY_TOOL_TYPES`` (5
tools: db_query_readonly, redis_inspect, http_health_check, service_logs,
metrics_query). Each takes ``(policy, db_pool=None)``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

EXPECTED_TOOL_COUNT = 5


def load_tools(db_pool: Any | None = None):
    """Load and wrap legacy observability tools."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.observability import (  # type: ignore[import]
            OBSERVABILITY_TOOL_TYPES,
            ObservabilityPolicy,
        )
    except ImportError:
        logger.warning(
            "observability loader: legacy module not available; no tools loaded"
        )
        return []

    try:
        policy = ObservabilityPolicy(
            enabled_tool_names=tuple(OBSERVABILITY_TOOL_TYPES.keys()),
        )
    except Exception:
        logger.warning(
            "observability loader: failed to build default policy", exc_info=True
        )
        return []

    base_tools = []
    for name, tool_cls in OBSERVABILITY_TOOL_TYPES.items():
        try:
            legacy_tool = tool_cls(policy, db_pool)
        except Exception:
            logger.debug(
                "observability loader: failed to instantiate %s", name, exc_info=True
            )
            continue
        base_tools.append(legacy_to_base_tool(legacy_tool))
    return base_tools


def register_into(registry: "ToolRegistry", *, db_pool: Any | None = None) -> int:
    tools = load_tools(db_pool=db_pool)
    for tool in tools:
        registry.register(
            tool,
            kind="observability",
            provider="observability",
            risk_level="medium",
            metadata={"capability": "observability"},
        )
    return len(tools)
