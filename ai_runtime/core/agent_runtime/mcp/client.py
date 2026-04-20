from __future__ import annotations

from ai_runtime.core.agent_runtime.mcp.models import (
    MCPCallToolResponse,
    MCPConnectionTestResult,
    MCPServerDefinition,
    MCPToolCatalogEntry,
)
from ai_runtime.core.agent_runtime.mcp.session import ManagedMCPSession


class MCPClient:
    async def test_connection(self, session: ManagedMCPSession) -> MCPConnectionTestResult:
        await session.ping()
        tools = await self.list_tools(session)
        initialize_result = session.initialize_result
        if initialize_result is None:
            raise RuntimeError("MCP session is not initialized")
        return MCPConnectionTestResult.from_initialize(
            server=session.server,
            result=initialize_result,
            tool_count=len(tools),
            session_id=session.session_id,
        )

    async def list_tools(self, session: ManagedMCPSession) -> list[MCPToolCatalogEntry]:
        cursor: str | None = None
        items: list[MCPToolCatalogEntry] = []
        while True:
            if cursor is None:
                page = await session.list_tools()
            else:
                client_session = await session.ensure_ready()
                page = await client_session.list_tools(cursor=cursor)
            for tool in page.tools:
                runtime_name = self.build_runtime_tool_name(session.server.id, tool.name)
                items.append(
                    MCPToolCatalogEntry.from_mcp_tool(
                        server=session.server,
                        runtime_name=runtime_name,
                        tool=tool,
                    )
                )
            cursor = page.nextCursor
            if not cursor:
                break
        return items

    async def call_tool(
        self,
        *,
        session: ManagedMCPSession,
        runtime_name: str,
        tool_name: str,
        arguments: dict[str, object] | None = None,
    ) -> MCPCallToolResponse:
        result = await session.call_tool(tool_name, arguments=arguments or {})
        return MCPCallToolResponse.from_result(
            server_id=session.server.id,
            runtime_name=runtime_name,
            tool_name=tool_name,
            result=result,
        )

    @staticmethod
    def build_runtime_tool_name(server_id: str, tool_name: str) -> str:
        return f"mcp__{server_id.replace('-', '')[:12]}__{tool_name}"

    @staticmethod
    def validate_server(server: MCPServerDefinition) -> None:
        if server.status == "disabled":
            raise ValueError(f"MCP server {server.id} is disabled")
        if server.transport == "stdio" and not (server.command or "").strip():
            raise ValueError("stdio transport requires command")
        if server.transport in {"http", "sse"} and not (server.endpoint or "").strip():
            raise ValueError(f"{server.transport} transport requires endpoint")
