from __future__ import annotations

from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.mcp import MCPToolProvider


class _FakeRegistry:
    async def list_catalog_tools(self, *, tenant_id: str, agent_definition_id: str | None = None):
        class _Entry:
            server_id = "server-1"
            server_name = "Docs MCP"
            tool_name = "search_docs"
            runtime_name = "mcp__server1__search_docs"
            description = "Search docs"
            input_schema = {"type": "object"}
            metadata = {"source_tool_name": "search_docs"}

        return [_Entry()]

    async def get_catalog_tool(self, *, tenant_id: str, runtime_name: str, agent_definition_id: str | None = None):
        entries = await self.list_catalog_tools(tenant_id=tenant_id, agent_definition_id=agent_definition_id)
        for entry in entries:
            if entry.runtime_name == runtime_name:
                return entry
        return None

    async def call_tool(self, *, tenant_id: str, agent_definition_id: str | None, runtime_name: str, arguments: dict | None = None):
        class _Response:
            def model_dump(self, mode: str = "json"):
                return {"runtime_name": runtime_name, "arguments": arguments or {}}

        return _Response()

    async def get_governance_snapshot(self, *, tenant_id: str):
        return {
            "tenant_id": tenant_id,
            "generated_at": "2026-05-19T00:00:00+00:00",
            "summary": {"total_servers": 1},
            "servers": [
                {
                    "server": {"id": "server-1", "name": "Docs MCP", "transport": "http", "status": "active"},
                    "availability": {"status": "available"},
                    "recovery": {"summary": "ok", "status": "healthy"},
                    "security_score": {"risk_level": "low", "score": 92},
                }
            ],
        }

    async def refresh_server_tools_summary(self, *, tenant_id: str, server_id: str):
        return {"server": {"id": server_id, "name": "Docs MCP"}, "catalog": {"summary": "refreshed"}, "total": 2, "tools": []}

    async def test_server_summary(self, *, tenant_id: str, server_id: str):
        return {"server": {"id": server_id, "name": "Docs MCP"}, "result": {"ok": True}, "connection": {"status": "healthy"}}

    async def get_recovery_plan(self, *, tenant_id: str, server_id: str):
        return {"server_id": server_id, "status": "blocked", "summary": "repair first", "actions": [{"type": "test"}]}

    def normalize_tool_result(self, value):
        return {"status": "normalized", "summary": "normalized", "text": "safe", "payload": {"value": "safe"}}


def _context() -> ToolContext:
    return ToolContext(run_id="run-1", tenant_id="tenant-1", agent_definition_id="agent-1")


async def test_mcp_provider_exposes_catalog_and_governance_tools():
    provider = MCPToolProvider(_FakeRegistry())

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1", agent_definition_id="agent-1"))
    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}

    assert "mcp__server1__search_docs" in metadata_by_name
    assert "mcp_catalog_status" in metadata_by_name
    assert metadata_by_name["mcp_catalog_status"]["provider"] == "mcp"
    assert metadata_by_name["mcp_recovery_plan"]["capability"] == "mcp_recovery_plan"


async def test_mcp_governance_tools_execute_against_registry():
    provider = MCPToolProvider(_FakeRegistry())

    snapshot_tool = await provider.get("mcp_catalog_status", context=ToolLookupContext(tenant_id="tenant-1"))
    recovery_tool = await provider.get("mcp_recovery_plan", context=ToolLookupContext(tenant_id="tenant-1"))
    normalize_tool = await provider.get("mcp_tool_result_normalize", context=ToolLookupContext(tenant_id="tenant-1"))

    snapshot = await snapshot_tool.execute(_context(), {})
    recovery = await recovery_tool.execute(_context(), {"server_id": "server-1"})
    normalized = await normalize_tool.execute(_context(), {"value": {"token": "secret"}})

    assert snapshot["summary"]["total_servers"] == 1
    assert recovery["status"] == "blocked"
    assert normalized["status"] == "normalized"


async def test_mcp_runtime_tool_respects_allowlists():
    provider = MCPToolProvider(_FakeRegistry())
    tool = await provider.get(
        "mcp__server1__search_docs",
        context=ToolLookupContext(
            tenant_id="tenant-1",
            agent_definition_id="agent-1",
            allowed_mcp_server_ids=("server-1",),
            allowed_mcp_tool_names=("search_docs",),
        ),
    )

    result = await tool.execute(_context(), {"query": "runtime"})

    assert result["runtime_name"] == "mcp__server1__search_docs"
    assert result["arguments"]["query"] == "runtime"
