from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class ToolContext:
    run_id: str
    tenant_id: str
    user_id: str | None = None
    agent_definition_id: str | None = None
    step_id: str | None = None


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    kind: str = "builtin"


class BaseTool(ABC):
    spec: ToolSpec

    @abstractmethod
    async def execute(self, context: ToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
