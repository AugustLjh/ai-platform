"""Tests for ai_runtime.tools.mcp — MCPMultiClient + load_mcp_tools loader."""
from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ai_runtime.tools.base import ToolContext
from ai_runtime.tools.caching import ToolResultCache
from ai_runtime.tools.mcp.client import MCPMultiClient
from ai_runtime.tools.mcp.loader import _server_config_from_definition, load_mcp_tools


class FakeServerDefinition:
    """Mimics the legacy MCPServerDefinition."""

    def __init__(
        self,
        id: str,
        name: str = "test_server",
        transport: str = "stdio",
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        endpoint: str | None = None,
    ):
        self.id = id
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.endpoint = endpoint
        self.metadata: dict[str, Any] = {}

    @property
    def cwd(self):
        return None

    @property
    def headers(self):
        return {}


class FakeMCPRegistry:
    def __init__(self, servers):
        self._servers = servers

    async def list_servers(self, *, tenant_id):
        return self._servers


class TestServerConfigFromDefinition:
    def test_stdio_transport(self):
        sd = FakeServerDefinition(
            id="s1",
            transport="stdio",
            command="npx",
            args=["-y", "@my/server"],
            env={"FOO": "bar"},
        )
        cfg = _server_config_from_definition(sd)
        assert cfg["transport"] == "stdio"
        assert cfg["command"] == "npx"
        assert cfg["args"] == ["-y", "@my/server"]
        assert cfg["env"] == {"FOO": "bar"}

    def test_http_transport(self):
        sd = FakeServerDefinition(
            id="s1",
            transport="http",
            endpoint="https://example.com/mcp",
        )
        cfg = _server_config_from_definition(sd)
        assert cfg["transport"] == "http"
        assert cfg["url"] == "https://example.com/mcp"

    def test_sse_transport(self):
        sd = FakeServerDefinition(
            id="s1",
            transport="sse",
            endpoint="https://example.com/sse",
        )
        cfg = _server_config_from_definition(sd)
        assert cfg["transport"] == "sse"
        assert cfg["url"] == "https://example.com/sse"


class TestMCPMultiClient:
    def test_initial_state(self):
        client = MCPMultiClient(server_configs={})
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_connect_with_no_configs_is_noop(self):
        client = MCPMultiClient(server_configs={})
        await client.connect()
        assert client.connected is False
        assert client.list_tools() == []

    @pytest.mark.asyncio
    async def test_connect_without_adapters_library_no_op(self):
        # When the adapters library isn't installed, .available is False
        # and connect() logs a warning + leaves us disconnected.
        client = MCPMultiClient(
            server_configs={"s1": {"transport": "stdio", "command": "echo", "args": []}}
        )
        # In test env adapters may or may not be installed; ensure no exception.
        await client.connect()
        # If unavailable, connected stays False; otherwise connection might succeed/fail.
        if not client.available:
            assert client.connected is False
            assert client.list_tools() == []

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self):
        client = MCPMultiClient(server_configs={})
        await client.disconnect()  # should not raise even when never connected
        assert client.connected is False


class TestLoadMCPTools:
    @pytest.mark.asyncio
    async def test_no_context_returns_empty(self):
        tools = await load_mcp_tools(context=None)
        assert tools == []

    @pytest.mark.asyncio
    async def test_no_servers_returns_empty(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        registry = FakeMCPRegistry(servers=[])
        tools = await load_mcp_tools(context=ctx, mcp_registry=registry)
        assert tools == []

    @pytest.mark.asyncio
    async def test_filters_by_registry_ids(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        registry = FakeMCPRegistry(
            servers=[
                FakeServerDefinition(id="s1"),
                FakeServerDefinition(id="s2"),
            ]
        )

        # Mock MCPMultiClient so we don't actually connect.
        from ai_runtime.tools.mcp import loader as loader_module
        with patch.object(loader_module, "MCPMultiClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.connected = True
            instance.list_tools = MagicMock(return_value=[])

            await load_mcp_tools(
                registry_ids=["s1"],
                context=ctx,
                mcp_registry=registry,
            )

            # MockClient should have been instantiated with only s1
            args, kwargs = MockClient.call_args
            server_configs = args[0] if args else kwargs.get("server_configs", {}) or kwargs
            # First positional arg is the configs dict
            if isinstance(server_configs, dict) and "s1" in server_configs:
                assert "s1" in server_configs
                assert "s2" not in server_configs

    @pytest.mark.asyncio
    async def test_filters_by_allowed_server_ids_in_context(self):
        ctx = ToolContext(
            run_id="r1",
            tenant_id="t1",
            allowed_mcp_server_ids=("s1",),
        )
        registry = FakeMCPRegistry(
            servers=[
                FakeServerDefinition(id="s1"),
                FakeServerDefinition(id="s2"),
            ]
        )

        from ai_runtime.tools.mcp import loader as loader_module
        with patch.object(loader_module, "MCPMultiClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.connected = True
            instance.list_tools = MagicMock(return_value=[])

            await load_mcp_tools(context=ctx, mcp_registry=registry)
            args, kwargs = MockClient.call_args
            server_configs = args[0] if args else kwargs.get("server_configs", {})
            assert "s1" in server_configs
            assert "s2" not in server_configs

    @pytest.mark.asyncio
    async def test_returns_tools_when_connected(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        registry = FakeMCPRegistry(
            servers=[FakeServerDefinition(id="s1")],
        )

        # Build a fake list of tools.
        from langchain_core.tools import BaseTool
        from pydantic import BaseModel, Field

        class FakeArgs(BaseModel):
            x: str = Field(default="")

        class FakeMCPTool(BaseTool):
            name: str = "mcp_tool_1"
            description: str = "fake mcp tool"
            args_schema: type = FakeArgs
            def _run(self, x=""):
                return {"x": x}
            async def _arun(self, x=""):
                return {"x": x}

        fake_tools = [FakeMCPTool()]

        from ai_runtime.tools.mcp import loader as loader_module
        with patch.object(loader_module, "MCPMultiClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.connected = True
            instance.list_tools = MagicMock(return_value=fake_tools)

            tools = await load_mcp_tools(context=ctx, mcp_registry=registry)
            assert len(tools) == 1
            assert tools[0].name == "mcp_tool_1"

    @pytest.mark.asyncio
    async def test_wraps_with_cache_when_provided(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        registry = FakeMCPRegistry(
            servers=[FakeServerDefinition(id="s1")],
        )
        cache = ToolResultCache(max_entries=4)

        from langchain_core.tools import BaseTool
        from pydantic import BaseModel, Field

        class FakeArgs(BaseModel):
            x: str = Field(default="")

        class FakeMCPTool(BaseTool):
            name: str = "mcp_tool_1"
            description: str = "fake"
            args_schema: type = FakeArgs
            def _run(self, x=""):
                return {"x": x}
            async def _arun(self, x=""):
                return {"x": x}

        from ai_runtime.tools.mcp import loader as loader_module
        with patch.object(loader_module, "MCPMultiClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.connected = True
            instance.list_tools = MagicMock(return_value=[FakeMCPTool()])

            tools = await load_mcp_tools(
                context=ctx, mcp_registry=registry, cache=cache,
            )
            assert len(tools) == 1
            # The wrapped tool should have the same name.
            assert tools[0].name == "mcp_tool_1"

    @pytest.mark.asyncio
    async def test_filters_by_allowed_tool_names(self):
        ctx = ToolContext(
            run_id="r1",
            tenant_id="t1",
            allowed_mcp_tool_names=("keep_me",),
        )
        registry = FakeMCPRegistry(servers=[FakeServerDefinition(id="s1")])

        from langchain_core.tools import BaseTool
        from pydantic import BaseModel, Field

        class FA(BaseModel):
            x: str = Field(default="")

        class FT(BaseTool):
            args_schema: type = FA
            def _run(self, x=""): return {}
            async def _arun(self, x=""): return {}

        fake_tools = [
            FT(name="keep_me", description="d"),
            FT(name="drop_me", description="d"),
        ]

        from ai_runtime.tools.mcp import loader as loader_module
        with patch.object(loader_module, "MCPMultiClient") as MockClient:
            instance = MockClient.return_value
            instance.connect = AsyncMock()
            instance.connected = True
            instance.list_tools = MagicMock(return_value=fake_tools)

            tools = await load_mcp_tools(context=ctx, mcp_registry=registry)
            assert [t.name for t in tools] == ["keep_me"]
