"""MCP tool loader — discovers MCP servers from the legacy registry and
produces LangChain ``BaseTool`` instances via ``langchain-mcp-adapters``.

This module bridges the existing ``MCPRegistry`` (which stores server
definitions in the database) with the new LangChain tools layer. It:

1. Reads server definitions from the legacy ``MCPRegistry``.
2. Builds a ``MultiServerMCPClient`` config dict from those definitions.
3. Connects and retrieves native ``BaseTool`` instances.
4. Optionally wraps each tool with :func:`cached_tool` and a context-injection
   decorator so that the tools participate in the standard ToolContext flow.

If the legacy ``MCPRegistry`` is not importable (e.g. in isolated test
environments), the loader returns an empty list with a warning.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from langchain_core.tools import BaseTool

from ai_runtime.tools.base import ToolContext
from ai_runtime.tools.caching import ToolResultCache, cached_tool
from ai_runtime.tools.mcp.client import MCPMultiClient


__all__ = ["load_mcp_tools"]

logger = logging.getLogger(__name__)


def _server_config_from_definition(server_def: Any) -> dict[str, Any]:
    """Convert a legacy ``MCPServerDefinition`` to the config dict expected by
    ``MultiServerMCPClient``.
    """
    transport = str(getattr(server_def, "transport", "stdio")).lower()
    config: dict[str, Any] = {"transport": transport}

    if transport == "stdio":
        config["command"] = getattr(server_def, "command", None) or ""
        config["args"] = list(getattr(server_def, "args", None) or [])
        env = dict(getattr(server_def, "env", None) or {})
        if env:
            config["env"] = env
        cwd = getattr(server_def, "cwd", None)
        if cwd:
            config["cwd"] = str(cwd)
    elif transport in ("http", "sse"):
        config["url"] = getattr(server_def, "endpoint", None) or ""
        headers = {}
        if hasattr(server_def, "headers"):
            headers = dict(server_def.headers or {})
        if headers:
            config["headers"] = headers

    return config


async def load_mcp_tools(
    registry_ids: Optional[Sequence[str]] = None,
    *,
    context: Optional[ToolContext] = None,
    cache: Optional[ToolResultCache] = None,
    mcp_registry: Optional[Any] = None,
    connect_timeout: float = 30.0,
) -> list[BaseTool]:
    """Load MCP tools from the legacy registry and return wrapped ``BaseTool`` instances.

    Args:
        registry_ids: Optional list of MCP server IDs to load. If ``None``,
            all active servers for the tenant are loaded.
        context: The active :class:`ToolContext` (used to determine tenant_id
            and allowed server/tool filters).
        cache: Optional :class:`ToolResultCache` to wrap each tool with.
        mcp_registry: An existing legacy ``MCPRegistry`` instance. If not
            provided, the function attempts to import and construct one from
            the legacy module.
        connect_timeout: Timeout in seconds for connecting to MCP servers.

    Returns:
        A list of LangChain ``BaseTool`` instances. Empty if no servers are
        configured, the adapters library is unavailable, or connection fails.
    """
    # Resolve tenant_id from context.
    tenant_id: Optional[str] = None
    agent_definition_id: Optional[str] = None
    allowed_server_ids: set[str] = set()
    allowed_tool_names: set[str] = set()

    if context is not None:
        tenant_id = context.tenant_id
        agent_definition_id = context.agent_definition_id
        allowed_server_ids = {s for s in context.allowed_mcp_server_ids if s}
        allowed_tool_names = {t for t in context.allowed_mcp_tool_names if t}

    # Discover server definitions.
    server_definitions: list[Any] = []
    if mcp_registry is not None:
        try:
            if tenant_id:
                server_definitions = await mcp_registry.list_servers(tenant_id=tenant_id)
            else:
                logger.debug("load_mcp_tools: no tenant_id; skipping registry lookup")
        except Exception:
            logger.warning("load_mcp_tools: failed to list MCP servers", exc_info=True)
    else:
        # Attempt to import the legacy registry.
        try:
            from ai_runtime.core.agent_runtime.mcp.registry import MCPRegistry  # type: ignore[import]
            logger.debug(
                "load_mcp_tools: legacy MCPRegistry imported but no instance provided; "
                "cannot discover servers without a db_pool"
            )
        except ImportError:
            logger.debug("load_mcp_tools: legacy MCPRegistry not available")

    if not server_definitions:
        return []

    # Filter by registry_ids if specified.
    if registry_ids is not None:
        id_set = set(registry_ids)
        server_definitions = [s for s in server_definitions if getattr(s, "id", None) in id_set]

    # Filter by allowed_server_ids from context.
    if allowed_server_ids:
        server_definitions = [
            s for s in server_definitions
            if getattr(s, "id", None) in allowed_server_ids
        ]

    if not server_definitions:
        return []

    # Build config dict for MCPMultiClient.
    server_configs: dict[str, dict[str, Any]] = {}
    for server_def in server_definitions:
        server_id = str(getattr(server_def, "id", ""))
        if not server_id:
            continue
        server_configs[server_id] = _server_config_from_definition(server_def)

    if not server_configs:
        return []

    # Connect and retrieve tools.
    client = MCPMultiClient(server_configs, connect_timeout=connect_timeout)
    await client.connect()

    if not client.connected:
        logger.warning("load_mcp_tools: MCPMultiClient failed to connect")
        return []

    tools = client.list_tools()

    # Filter by allowed_tool_names if specified.
    if allowed_tool_names:
        tools = [t for t in tools if t.name in allowed_tool_names]

    # Wrap with cache if provided.
    if cache is not None:
        tools = [cached_tool(t, cache) for t in tools]

    logger.info(
        "load_mcp_tools: loaded %d tool(s) from %d server(s)",
        len(tools),
        len(server_configs),
    )
    return tools
