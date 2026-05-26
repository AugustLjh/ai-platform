from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ai_runtime.core.agent_runtime.optimization import ToolResultCache


@dataclass(slots=True)
class ToolContext:
    run_id: str
    tenant_id: str
    session_id: str | None = None
    user_id: str | None = None
    agent_definition_id: str | None = None
    step_id: str | None = None
    allowed_knowledge_base_ids: tuple[str, ...] = ()
    allowed_mcp_server_ids: tuple[str, ...] = ()
    allowed_mcp_tool_names: tuple[str, ...] = ()
    workspace_root: str | None = None
    tool_result_cache: ToolResultCache | None = None


@dataclass(slots=True)
class ToolLookupContext:
    tenant_id: str
    user_id: Optional[str] = None
    agent_definition_id: Optional[str] = None
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    allowed_knowledge_base_ids: tuple[str, ...] = ()
    allowed_mcp_server_ids: tuple[str, ...] = ()
    allowed_mcp_tool_names: tuple[str, ...] = ()
    workspace_root: str | None = None


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    kind: str = "builtin"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    spec: ToolSpec

    @abstractmethod
    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
