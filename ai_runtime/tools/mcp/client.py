"""MCP multi-client wrapper using langchain-mcp-adapters.

This module provides a thin lifecycle wrapper around
``langchain_mcp_adapters.client.MultiServerMCPClient`` (when available) or
falls back to a no-op stub so that the rest of the tools layer can import
unconditionally.

The client is responsible for:

- Connecting to one or more MCP servers at registry-load time.
- Exposing ``list_tools() -> list[BaseTool]`` that returns native LangChain
  ``BaseTool`` instances (as produced by the adapters library).
- Managing reconnection on transient failures.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from langchain_core.tools import BaseTool


__all__ = ["MCPMultiClient"]

logger = logging.getLogger(__name__)


# Attempt to import the real adapters library; fall back gracefully.
try:
    from langchain_mcp_adapters.client import MultiServerMCPClient as _RealClient  # type: ignore[import-untyped]

    _HAS_MCP_ADAPTERS = True
except ImportError:
    _RealClient = None  # type: ignore[assignment, misc]
    _HAS_MCP_ADAPTERS = False


class MCPMultiClient:
    """Thin lifecycle wrapper around ``MultiServerMCPClient``.

    Usage::

        client = MCPMultiClient(server_configs={
            "my-server": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@my/mcp-server"],
            }
        })
        await client.connect()
        tools = client.list_tools()
        # ... use tools ...
        await client.disconnect()

    If ``langchain-mcp-adapters`` is not installed, the client operates as a
    no-op: ``connect()`` logs a warning and ``list_tools()`` returns ``[]``.
    """

    def __init__(
        self,
        server_configs: Optional[dict[str, dict[str, Any]]] = None,
        *,
        connect_timeout: float = 30.0,
    ) -> None:
        self._server_configs = server_configs or {}
        self._connect_timeout = connect_timeout
        self._client: Any = None
        self._tools: list[BaseTool] = []
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def available(self) -> bool:
        """Whether the underlying adapters library is installed."""
        return _HAS_MCP_ADAPTERS

    async def connect(self) -> None:
        """Connect to all configured MCP servers.

        Idempotent — calling when already connected is a no-op.
        """
        if self._connected:
            return

        if not _HAS_MCP_ADAPTERS:
            logger.warning(
                "langchain-mcp-adapters not installed; MCP tools will be unavailable. "
                "Install with: pip install langchain-mcp-adapters"
            )
            return

        if not self._server_configs:
            logger.debug("MCPMultiClient: no server configs provided; skipping connect")
            return

        async with self._lock:
            if self._connected:
                return
            try:
                self._client = _RealClient(self._server_configs)
                await asyncio.wait_for(
                    self._client.__aenter__(),
                    timeout=self._connect_timeout,
                )
                self._tools = self._client.get_tools()
                self._connected = True
                logger.info(
                    "MCPMultiClient connected to %d server(s), discovered %d tool(s)",
                    len(self._server_configs),
                    len(self._tools),
                )
            except asyncio.TimeoutError:
                logger.error(
                    "MCPMultiClient: connection timed out after %.1fs",
                    self._connect_timeout,
                )
                self._client = None
                self._tools = []
            except Exception:
                logger.error("MCPMultiClient: connection failed", exc_info=True)
                self._client = None
                self._tools = []

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.__aexit__(None, None, None)
                except Exception:
                    logger.debug("MCPMultiClient: error during disconnect", exc_info=True)
                finally:
                    self._client = None
                    self._tools = []
                    self._connected = False

    async def reconnect(self) -> None:
        """Disconnect then reconnect."""
        await self.disconnect()
        await self.connect()

    def list_tools(self) -> list[BaseTool]:
        """Return the list of LangChain ``BaseTool`` instances from MCP servers.

        Returns an empty list if not connected or if the adapters library is
        unavailable.
        """
        return list(self._tools)

    async def __aenter__(self) -> "MCPMultiClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.disconnect()
