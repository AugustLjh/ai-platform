from __future__ import annotations

from typing import Any, Dict

from ai_runtime.core.agent_runtime.mcp.registry import MCPRegistry
from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec


_MCP_GOVERNANCE_TOOL_NAMES = (
    "mcp_catalog_status",
    "mcp_refresh_catalog",
    "mcp_test_connection",
    "mcp_recovery_plan",
    "mcp_tool_result_normalize",
)


def _tool_metadata(*, capability: str, access_level: str = "read", side_effect: str = "none", risk_level: str = "low") -> dict[str, Any]:
    return {
        "provider": "mcp",
        "capability": capability,
        "access_level": access_level,
        "side_effect": side_effect,
        "requires_workspace": False,
        "requires_sandbox": False,
        "risk_level": risk_level,
    }


class MCPTool(BaseTool):
    def __init__(
        self,
        *,
        registry: MCPRegistry,
        runtime_name: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.spec = ToolSpec(
            name=runtime_name,
            description=description,
            input_schema=input_schema or {},
            kind="mcp",
            metadata=metadata or {},
        )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        server_id = str(self.spec.metadata.get("server_id") or "").strip()
        source_tool_name = str(self.spec.metadata.get("source_tool_name") or "").strip()
        allowed_server_ids = {str(item).strip() for item in context.allowed_mcp_server_ids if str(item).strip()}
        allowed_tool_names = {str(item).strip() for item in context.allowed_mcp_tool_names if str(item).strip()}
        if allowed_server_ids and server_id and server_id not in allowed_server_ids:
            raise PermissionError(f"MCP server {server_id} is not allowed for this managed capability")
        if allowed_tool_names and self.spec.name not in allowed_tool_names and source_tool_name not in allowed_tool_names:
            raise PermissionError(f"MCP tool {self.spec.name} is not allowed for this managed capability")
        response = await self.registry.call_tool(
            tenant_id=context.tenant_id,
            agent_definition_id=context.agent_definition_id,
            runtime_name=self.spec.name,
            arguments=arguments,
        )
        return response.model_dump(mode="json")


class MCPGovernanceTool(BaseTool):
    def __init__(self, *, registry: MCPRegistry, runtime_name: str, description: str, capability: str, input_schema: dict[str, Any] | None = None) -> None:
        self.registry = registry
        self.spec = ToolSpec(
            name=runtime_name,
            description=description,
            input_schema=input_schema or {},
            kind="mcp-governance",
            metadata=_tool_metadata(capability=capability, access_level="read", side_effect="none", risk_level="low"),
        )

    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self.spec.name == "mcp_catalog_status":
            return await self.registry.get_governance_snapshot(tenant_id=context.tenant_id)
        if self.spec.name == "mcp_refresh_catalog":
            server_id = str(arguments.get("server_id") or "").strip()
            if not server_id:
                raise ValueError("server_id is required")
            return await self.registry.refresh_server_tools_summary(tenant_id=context.tenant_id, server_id=server_id)
        if self.spec.name == "mcp_test_connection":
            server_id = str(arguments.get("server_id") or "").strip()
            if not server_id:
                raise ValueError("server_id is required")
            return await self.registry.test_server_summary(tenant_id=context.tenant_id, server_id=server_id)
        if self.spec.name == "mcp_recovery_plan":
            server_id = str(arguments.get("server_id") or "").strip()
            if not server_id:
                raise ValueError("server_id is required")
            return await self.registry.get_recovery_plan(tenant_id=context.tenant_id, server_id=server_id)
        if self.spec.name == "mcp_tool_result_normalize":
            return self.registry.normalize_tool_result(arguments.get("value"))
        raise ValueError(f"unsupported MCP governance tool {self.spec.name}")


class MCPToolProvider:
    def __init__(self, registry: MCPRegistry) -> None:
        self.registry = registry

    def _is_allowed(self, entry, context: ToolLookupContext | None) -> bool:
        if context is None:
            return True
        allowed_server_ids = {str(item).strip() for item in context.allowed_mcp_server_ids if str(item).strip()}
        if allowed_server_ids and entry.server_id not in allowed_server_ids:
            return False
        allowed_tool_names = {str(item).strip() for item in context.allowed_mcp_tool_names if str(item).strip()}
        if allowed_tool_names and entry.runtime_name not in allowed_tool_names and entry.tool_name not in allowed_tool_names:
            return False
        return True

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        if name in _MCP_GOVERNANCE_TOOL_NAMES:
            return self._build_governance_tool(name)
        if context is None:
            return None
        entry = await self.registry.get_catalog_tool(
            tenant_id=context.tenant_id,
            runtime_name=name,
            agent_definition_id=context.agent_definition_id,
        )
        if entry is None or not self._is_allowed(entry, context):
            return None
        return self._build_tool(entry)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = await self.get(name, context=context)
        if tool is None:
            return None
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": tool.spec.metadata,
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        items: list[dict] = []
        if context is not None:
            try:
                entries = await self.registry.list_catalog_tools(
                    tenant_id=context.tenant_id,
                    agent_definition_id=context.agent_definition_id,
                )
            except Exception:
                entries = []
            items.extend(
                {
                    "name": entry.runtime_name,
                    "description": entry.description or f"MCP tool {entry.tool_name} from {entry.server_name}",
                    "input_schema": entry.input_schema,
                    "kind": "mcp",
                    "metadata": {
                        **entry.metadata,
                        "server_id": entry.server_id,
                        "server_name": entry.server_name,
                        "source_tool_name": entry.tool_name,
                        "runtime_name": entry.runtime_name,
                        "provider": "mcp",
                    },
                }
                for entry in entries
                if self._is_allowed(entry, context)
            )
        items.extend(self._governance_specs())
        return items

    def _governance_specs(self) -> list[dict]:
        return [
            {
                "name": "mcp_catalog_status",
                "description": "Return a tenant-level MCP governance snapshot with hydrated server, security, availability, and recovery data.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "kind": "mcp-governance",
                "metadata": _tool_metadata(capability="mcp_catalog_status"),
            },
            {
                "name": "mcp_refresh_catalog",
                "description": "Refresh one MCP server catalog and return the hydrated governance summary.",
                "input_schema": {
                    "type": "object",
                    "properties": {"server_id": {"type": "string"}},
                    "required": ["server_id"],
                    "additionalProperties": False,
                },
                "kind": "mcp-governance",
                "metadata": _tool_metadata(capability="mcp_refresh_catalog", access_level="write"),
            },
            {
                "name": "mcp_test_connection",
                "description": "Test one MCP server connection and return the hydrated governance summary.",
                "input_schema": {
                    "type": "object",
                    "properties": {"server_id": {"type": "string"}},
                    "required": ["server_id"],
                    "additionalProperties": False,
                },
                "kind": "mcp-governance",
                "metadata": _tool_metadata(capability="mcp_test_connection", access_level="write"),
            },
            {
                "name": "mcp_recovery_plan",
                "description": "Build a server-level MCP recovery plan from the current governance state.",
                "input_schema": {
                    "type": "object",
                    "properties": {"server_id": {"type": "string"}},
                    "required": ["server_id"],
                    "additionalProperties": False,
                },
                "kind": "mcp-governance",
                "metadata": _tool_metadata(capability="mcp_recovery_plan"),
            },
            {
                "name": "mcp_tool_result_normalize",
                "description": "Normalize and redact an arbitrary MCP tool result payload for safe display.",
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {}},
                    "required": ["value"],
                    "additionalProperties": True,
                },
                "kind": "mcp-governance",
                "metadata": _tool_metadata(capability="mcp_tool_result_normalize"),
            },
        ]

    def _build_governance_tool(self, name: str) -> MCPGovernanceTool:
        specs = {spec["name"]: spec for spec in self._governance_specs()}
        spec = specs[name]
        return MCPGovernanceTool(
            registry=self.registry,
            runtime_name=spec["name"],
            description=spec["description"],
            capability=name,
            input_schema=spec["input_schema"],
        )

    def _build_tool(self, entry) -> MCPTool:
        return MCPTool(
            registry=self.registry,
            runtime_name=entry.runtime_name,
            description=entry.description or f"MCP tool {entry.tool_name} from {entry.server_name}",
            input_schema=entry.input_schema,
            metadata={
                **entry.metadata,
                "server_id": entry.server_id,
                "server_name": entry.server_name,
                "source_tool_name": entry.tool_name,
                "runtime_name": entry.runtime_name,
                "provider": "mcp",
            },
        )
