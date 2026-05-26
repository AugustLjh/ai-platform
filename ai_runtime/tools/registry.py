"""Tool registry for the LangChain-native tools layer.

The registry is the single entry point for collecting, filtering, and
materialising the set of ``BaseTool`` instances available to a given agent run.

Key concepts:

- **Registration**: tools (or tool factories) are registered at startup via
  ``register()`` (decorator or direct call). Each registration carries a
  ``ToolRegistration`` with metadata used for filtering.
- **Build-for-run**: ``build_for_run(...)`` applies allowlist, execution_mode,
  and governance budget filters to produce the final ``list[BaseTool]`` that
  gets injected into the LangGraph agent state.
- **Iteration**: ``iter_specs()`` yields lightweight spec dicts (name,
  description, input_schema, kind, metadata) without instantiating heavy tool
  objects — useful for planner prompts and catalog APIs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from langchain_core.tools import BaseTool

from ai_runtime.tools.base import ToolContext


__all__ = [
    "ToolRegistry",
    "ToolRegistration",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolRegistration:
    """Metadata attached to a registered tool for filtering purposes."""

    tool: BaseTool
    kind: str = "builtin"
    provider: str = "builtin"
    # Execution modes in which this tool is available.
    # Empty means "all modes".
    execution_modes: frozenset[str] = field(default_factory=frozenset)
    # Governance tags that must be satisfied for the tool to be included.
    # Empty means "no governance restriction".
    governance_tags: frozenset[str] = field(default_factory=frozenset)
    # If True, the tool requires a workspace_root to be set in the context.
    requires_workspace: bool = False
    # If True, the tool requires sandbox execution environment.
    requires_sandbox: bool = False
    # Risk level for governance budget checks.
    risk_level: str = "low"
    # Additional metadata for spec generation.
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Central registry of all available tools.

    Usage::

        registry = ToolRegistry()

        # Register individual tools
        registry.register(my_tool, kind="workspace", provider="workspace")

        # Or use as a decorator on a factory function
        @registry.register_factory(kind="builtin", provider="builtin")
        def create_calculator() -> BaseTool:
            return CalculatorTool()

        # At run time, build the filtered tool list
        tools = registry.build_for_run(
            context=tool_context,
            allowlist=["calculator", "knowledge_search"],
        )
    """

    def __init__(self) -> None:
        self._registrations: dict[str, ToolRegistration] = {}
        self._factories: list[Callable[[], Iterable[ToolRegistration]]] = []

    # ---------------------------------------------------------------- register

    def register(
        self,
        tool: BaseTool,
        *,
        kind: str = "builtin",
        provider: str = "builtin",
        execution_modes: Iterable[str] = (),
        governance_tags: Iterable[str] = (),
        requires_workspace: bool = False,
        requires_sandbox: bool = False,
        risk_level: str = "low",
        metadata: Optional[dict[str, Any]] = None,
    ) -> BaseTool:
        """Register a tool instance. Returns the tool for chaining."""

        reg = ToolRegistration(
            tool=tool,
            kind=kind,
            provider=provider,
            execution_modes=frozenset(execution_modes),
            governance_tags=frozenset(governance_tags),
            requires_workspace=requires_workspace,
            requires_sandbox=requires_sandbox,
            risk_level=risk_level,
            metadata=metadata or {},
        )
        self._registrations[tool.name] = reg
        return tool

    def register_many(
        self,
        tools: Iterable[BaseTool],
        *,
        kind: str = "builtin",
        provider: str = "builtin",
        execution_modes: Iterable[str] = (),
        governance_tags: Iterable[str] = (),
        requires_workspace: bool = False,
        requires_sandbox: bool = False,
        risk_level: str = "low",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register multiple tools with the same metadata."""
        for tool in tools:
            self.register(
                tool,
                kind=kind,
                provider=provider,
                execution_modes=execution_modes,
                governance_tags=governance_tags,
                requires_workspace=requires_workspace,
                requires_sandbox=requires_sandbox,
                risk_level=risk_level,
                metadata=metadata,
            )

    def register_factory(
        self,
        factory: Callable[[], Iterable[ToolRegistration]],
    ) -> None:
        """Register a lazy factory that produces registrations on demand.

        Factories are called once during ``build_for_run`` and their results
        are merged into the registry. Useful for providers that need runtime
        config (e.g. MCP tools discovered from a remote server).
        """
        self._factories.append(factory)

    # ---------------------------------------------------------------- query

    @property
    def tool_names(self) -> list[str]:
        return list(self._registrations.keys())

    def __len__(self) -> int:
        return len(self._registrations)

    def __contains__(self, name: str) -> bool:
        return name in self._registrations

    def get(self, name: str) -> Optional[ToolRegistration]:
        return self._registrations.get(name)

    def iter_specs(self) -> Iterable[dict[str, Any]]:
        """Yield lightweight spec dicts for all registered tools."""
        for reg in self._registrations.values():
            tool = reg.tool
            schema = {}
            if tool.args_schema is not None:
                if isinstance(tool.args_schema, type):
                    schema = tool.args_schema.model_json_schema()
                elif isinstance(tool.args_schema, dict):
                    schema = tool.args_schema
            yield {
                "name": tool.name,
                "description": tool.description,
                "input_schema": schema,
                "kind": reg.kind,
                "provider": reg.provider,
                "metadata": {
                    **reg.metadata,
                    "requires_workspace": reg.requires_workspace,
                    "requires_sandbox": reg.requires_sandbox,
                    "risk_level": reg.risk_level,
                },
            }

    # ---------------------------------------------------------------- build

    def build_for_run(
        self,
        context: ToolContext,
        *,
        allowlist: Optional[Sequence[str]] = None,
        denylist: Optional[Sequence[str]] = None,
        governance: Optional[dict[str, Any]] = None,
    ) -> list[BaseTool]:
        """Build the filtered tool list for a specific run.

        Filtering rules (applied in order):

        1. **Allowlist**: if provided, only tools whose name is in the
           allowlist are included.
        2. **Denylist**: if provided, tools whose name is in the denylist are
           excluded.
        3. **Execution mode**: if the registration specifies
           ``execution_modes``, the tool is only included when
           ``context.execution_mode`` is in that set.
        4. **Workspace requirement**: if ``requires_workspace`` is True and
           ``context.workspace_root`` is not set, the tool is excluded.
        5. **Governance budget**: if ``governance`` specifies a
           ``max_risk_level``, tools with a higher risk level are excluded.
        """
        # Materialise any lazy factories first.
        for factory in self._factories:
            try:
                for reg in factory():
                    if reg.tool.name not in self._registrations:
                        self._registrations[reg.tool.name] = reg
            except Exception:
                logger.warning("Tool factory %s failed", factory, exc_info=True)

        governance = governance or context.governance or {}
        allow_set = set(allowlist) if allowlist else None
        deny_set = set(denylist) if denylist else None
        max_risk = governance.get("max_risk_level")

        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_risk_rank = risk_order.get(str(max_risk or "").lower(), 999)

        results: list[BaseTool] = []
        for name, reg in self._registrations.items():
            # 1. Allowlist
            if allow_set is not None and name not in allow_set:
                continue
            # 2. Denylist
            if deny_set is not None and name in deny_set:
                continue
            # 3. Execution mode
            if reg.execution_modes and context.execution_mode not in reg.execution_modes:
                continue
            # 4. Workspace requirement
            if reg.requires_workspace and not context.workspace_root:
                continue
            # 5. Governance risk budget
            tool_risk_rank = risk_order.get(reg.risk_level, 0)
            if tool_risk_rank > max_risk_rank:
                continue

            results.append(reg.tool)

        return results
