from __future__ import annotations

from typing import Dict, List

from core.agent_runtime.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_specs(self) -> List[dict]:
        return [
            {
                "name": tool.spec.name,
                "description": tool.spec.description,
                "input_schema": tool.spec.input_schema,
                "kind": tool.spec.kind,
            }
            for tool in self._tools.values()
        ]
