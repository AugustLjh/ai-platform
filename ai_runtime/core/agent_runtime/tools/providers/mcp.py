from __future__ import annotations

from typing import Any, Dict

from ai_runtime.core.agent_runtime.mcp.registry import MCPRegistry
from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec


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
        if context is None:
            return []
        entries = await self.registry.list_catalog_tools(
            tenant_id=context.tenant_id,
            agent_definition_id=context.agent_definition_id,
        )
        return [
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
                },
            }
            for entry in entries
            if self._is_allowed(entry, context)
        ]

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
            },
        )
