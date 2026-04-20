from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Implementation, InitializeResult, ListToolsResult

from ai_runtime.core.agent_runtime.mcp.models import MCPServerDefinition


class ManagedMCPSession:
    def __init__(self, server: MCPServerDefinition) -> None:
        self.server = server
        self.last_used_at = datetime.now(timezone.utc)
        self.initialize_result: InitializeResult | None = None
        self.session_id: str | None = None

        self._lock = asyncio.Lock()
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._session_id_getter = None

    async def ensure_ready(self) -> ClientSession:
        async with self._lock:
            self.last_used_at = datetime.now(timezone.utc)
            if self._session is not None:
                return self._session

            stack = AsyncExitStack()
            try:
                read_stream, write_stream = await self._open_transport(stack)
                session = await stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                        client_info=Implementation(name="ai-platform-runtime", version="1.0.0"),
                    )
                )
                self.initialize_result = await session.initialize()
                if self._session_id_getter is not None and self.session_id is None:
                    self.session_id = self._session_id_getter()
                self._session = session
                self._exit_stack = stack
                return session
            except Exception:
                await stack.aclose()
                raise

    async def _open_transport(self, stack: AsyncExitStack):
        if self.server.transport == "stdio":
            cm = stdio_client(
                StdioServerParameters(
                    command=self.server.command or "",
                    args=self.server.args,
                    env=self.server.env,
                    cwd=self.server.cwd,
                )
            )
            return await stack.enter_async_context(cm)

        if self.server.transport == "sse":
            return await stack.enter_async_context(
                sse_client(
                    self.server.endpoint or "",
                    headers=self.server.headers or None,
                    timeout=self.server.timeout_seconds,
                    sse_read_timeout=self.server.sse_read_timeout_seconds,
                    on_session_created=self._capture_session_id,
                )
            )

        if self.server.transport == "http":
            read_stream, write_stream, get_session_id = await stack.enter_async_context(
                streamablehttp_client(
                    self.server.endpoint or "",
                    headers=self.server.headers or None,
                    timeout=self.server.timeout_seconds,
                    sse_read_timeout=self.server.sse_read_timeout_seconds,
                )
            )
            self._session_id_getter = get_session_id
            return read_stream, write_stream

        raise ValueError(f"unsupported MCP transport: {self.server.transport}")

    def _capture_session_id(self, session_id: str) -> None:
        self.session_id = session_id

    async def ping(self) -> None:
        session = await self.ensure_ready()
        await session.send_ping()
        self.last_used_at = datetime.now(timezone.utc)

    async def list_tools(self) -> ListToolsResult:
        session = await self.ensure_ready()
        self.last_used_at = datetime.now(timezone.utc)
        return await session.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, object] | None = None):
        session = await self.ensure_ready()
        self.last_used_at = datetime.now(timezone.utc)
        return await session.call_tool(name, arguments=arguments or {})

    async def close(self) -> None:
        async with self._lock:
            stack = self._exit_stack
            self._exit_stack = None
            self._session = None
            self.initialize_result = None
            self.session_id = None
            self._session_id_getter = None
            if stack is not None:
                await stack.aclose()
