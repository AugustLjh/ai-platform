from __future__ import annotations

from typing import Dict, List, Protocol

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolLookupContext


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
        self._registered_provider_names: List[str] = []
        self._providers: List[tuple[str, ToolProvider]] = []

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.name] = tool

    def register_provider_name(self, name: str) -> None:
        provider_name = str(name or "").strip()
        if provider_name and provider_name not in self._registered_provider_names:
            self._registered_provider_names.append(provider_name)

    def register_provider(self, provider: ToolProvider, *, name: str | None = None) -> None:
        provider_name = str(name or getattr(provider, "provider_name", "") or provider.__class__.__name__).strip()
        self.register_provider_name(provider_name)
        self._providers.append((provider_name, provider))

    @property
    def provider_names(self) -> List[str]:
        return list(self._registered_provider_names)

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        tool = self._tools.get(name)
        if tool is not None:
            return tool
        for _provider_name, provider in self._providers:
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
        for _provider_name, provider in self._providers:
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
        for _provider_name, provider in self._providers:
            items.extend(await provider.list_specs(context=context))
        return items
