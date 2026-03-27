from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from mcp.types import CallToolResult, InitializeResult, Tool as MCPTool
from pydantic import BaseModel, ConfigDict, Field


MCPTransport = Literal["stdio", "http", "sse"]


class MCPServerDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    tenant_id: str
    name: str
    transport: MCPTransport
    endpoint: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    status: str = "active"
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def headers(self) -> Dict[str, str]:
        raw = self.metadata.get("headers")
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    @property
    def cwd(self) -> Optional[str]:
        value = self.metadata.get("cwd")
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def timeout_seconds(self) -> float:
        value = self.metadata.get("timeout_seconds", 30)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = 30.0
        return max(1.0, min(parsed, 300.0))

    @property
    def sse_read_timeout_seconds(self) -> float:
        value = self.metadata.get("sse_read_timeout_seconds", 300)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = 300.0
        return max(5.0, min(parsed, 1800.0))


class MCPToolCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    server_id: str
    server_name: str = ""
    transport: str = ""
    runtime_name: str
    tool_name: str
    title: Optional[str] = None
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    discovered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_mcp_tool(
        cls,
        *,
        server: MCPServerDefinition,
        runtime_name: str,
        tool: MCPTool,
    ) -> "MCPToolCatalogEntry":
        annotations = tool.annotations.model_dump(mode="json") if tool.annotations is not None else {}
        execution = tool.execution.model_dump(mode="json") if tool.execution is not None else {}
        meta = tool.meta or {}
        return cls(
            server_id=server.id,
            server_name=server.name,
            transport=server.transport,
            runtime_name=runtime_name,
            tool_name=tool.name,
            title=tool.title,
            description=tool.description or "",
            input_schema=tool.inputSchema or {},
            output_schema=tool.outputSchema or {},
            metadata={
                "runtime_name": runtime_name,
                "source_tool_name": tool.name,
                "server_id": server.id,
                "server_name": server.name,
                "server_transport": server.transport,
                "title": tool.title,
                "annotations": annotations,
                "execution": execution,
                "meta": meta,
                "output_schema": tool.outputSchema or {},
            },
        )


class MCPConnectionTestResult(BaseModel):
    server_id: str
    transport: str
    ok: bool
    tool_count: int = 0
    session_id: Optional[str] = None
    server_info: Dict[str, Any] = Field(default_factory=dict)
    instructions: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def from_initialize(
        cls,
        *,
        server: MCPServerDefinition,
        result: InitializeResult,
        tool_count: int,
        session_id: str | None = None,
    ) -> "MCPConnectionTestResult":
        return cls(
            server_id=server.id,
            transport=server.transport,
            ok=True,
            tool_count=tool_count,
            session_id=session_id,
            server_info=result.serverInfo.model_dump(mode="json") if result.serverInfo is not None else {},
            instructions=result.instructions,
        )


class MCPCallToolResponse(BaseModel):
    server_id: str
    runtime_name: str
    tool_name: str
    is_error: bool = False
    content: list[Dict[str, Any]] = Field(default_factory=list)
    structured_content: Any = Field(default_factory=dict)
    text: str = ""

    @classmethod
    def from_result(
        cls,
        *,
        server_id: str,
        runtime_name: str,
        tool_name: str,
        result: CallToolResult,
    ) -> "MCPCallToolResponse":
        content = [item.model_dump(mode="json") for item in result.content]
        text_parts = []
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                text_parts.append(str(item["text"]))
        structured = result.structuredContent
        return cls(
            server_id=server_id,
            runtime_name=runtime_name,
            tool_name=tool_name,
            is_error=bool(result.isError),
            content=content,
            structured_content=structured,
            text="\n".join(text_parts).strip(),
        )
