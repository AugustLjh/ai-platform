from __future__ import annotations

from typing import Dict, List, Protocol

from core.agent_runtime.tools.base import BaseTool, ToolLookupContext


class ToolProvider(Protocol):
    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        ...

    async def list_specs(self, context: ToolLookupContext | None = None) -> List[dict]:
        ...

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._providers: List[ToolProvider] = []

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.name] = tool

    def register_provider(self, provider: ToolProvider) -> None:
        self._providers.append(provider)

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        tool = self._tools.get(name)
        if tool is not None:
            return tool
        for provider in self._providers:
            resolved = await provider.get(name, context=context)
            if resolved is not None:
                return resolved
        return None

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = self._tools.get(name)
        if tool is not None:
            return {
                "name": tool.spec.name,
                "description": tool.spec.description,
                "input_schema": tool.spec.input_schema,
                "kind": tool.spec.kind,
                "metadata": tool.spec.metadata,
            }
        for provider in self._providers:
            spec = await provider.get_spec(name, context=context)
            if spec is not None:
                return spec
        return None

    async def list_specs(self, context: ToolLookupContext | None = None) -> List[dict]:
        items = [
            {
                "name": tool.spec.name,
                "description": tool.spec.description,
                "input_schema": tool.spec.input_schema,
                "kind": tool.spec.kind,
                "metadata": tool.spec.metadata,
            }
            for tool in self._tools.values()
        ]
        for provider in self._providers:
            items.extend(await provider.list_specs(context=context))
        return items
