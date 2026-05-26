"""Loader for web tools — wraps legacy web provider tools as BaseTool.

The legacy ``web.py`` module exposes ``WEB_TOOL_TYPES`` (13 tools including
fetch_url, web_search, browser_open, etc). This loader instantiates each with
a default permissive policy and wraps via ``legacy_to_base_tool``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

# Count from WEB_TOOL_TYPES in legacy web.py.
EXPECTED_TOOL_COUNT = 13

# Browser tool names need access to a shared session map.
BROWSER_TOOL_NAMES = {
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_snapshot",
    "browser_close",
    "browser_verify",
}


def load_tools():
    """Load and wrap legacy web tools."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.web import (  # type: ignore[import]
            WEB_TOOL_TYPES,
            WebPolicy,
            DEFAULT_ALLOWED_CONTENT_TYPES,
            DEFAULT_DOWNLOAD_CONTENT_TYPES,
            DEFAULT_SEARCH_ALLOWED_SCHEMES,
        )
    except ImportError:
        logger.warning("web loader: legacy module not available; no tools loaded")
        return []

    try:
        policy = WebPolicy(
            network_configured=False,
            allowed_domains=(),
            denied_domains=(),
            allowed_content_types=tuple(DEFAULT_ALLOWED_CONTENT_TYPES),
            allowed_download_content_types=tuple(DEFAULT_DOWNLOAD_CONTENT_TYPES),
            search_allowed_schemes=tuple(DEFAULT_SEARCH_ALLOWED_SCHEMES),
        )
    except Exception:
        logger.warning("web loader: failed to build default policy", exc_info=True)
        return []

    browser_sessions: dict = {}
    base_tools = []
    for name, tool_cls in WEB_TOOL_TYPES.items():
        try:
            if name == "pdf_extract":
                legacy_tool = tool_cls(policy)
            elif name in BROWSER_TOOL_NAMES:
                legacy_tool = tool_cls(policy, browser_sessions)
            else:
                legacy_tool = tool_cls(policy)
        except Exception:
            logger.debug("web loader: failed to instantiate %s", name, exc_info=True)
            continue
        base_tools.append(legacy_to_base_tool(legacy_tool))
    return base_tools


def register_into(registry: "ToolRegistry") -> int:
    tools = load_tools()
    for tool in tools:
        risk = "high" if tool.name in {"download_file"} or tool.name.startswith("browser_") else "medium"
        registry.register(
            tool,
            kind="web",
            provider="web",
            risk_level=risk,
            metadata={"capability": "web_access"},
        )
    return len(tools)
