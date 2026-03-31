from __future__ import annotations

import logging
import os
from typing import Iterable

from core.agent_runtime.mcp.registry import MCPRegistry
from core.agent_runtime.tools.providers.builtin import register_builtin_tools
from core.agent_runtime.tools.providers.engineering import EngineeringToolProvider
from core.agent_runtime.tools.providers.knowledge import register_knowledge_tools
from core.agent_runtime.tools.providers.mcp import MCPToolProvider

logger = logging.getLogger(__name__)

DEFAULT_TOOL_PROVIDERS = ("builtin", "knowledge", "mcp", "engineering")


def _parse_csv(value: str | None, default: Iterable[str]) -> list[str]:
    if value is None or not value.strip():
        return [item for item in default]
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_tool_registry(registry, *, mcp_registry: MCPRegistry) -> None:
    provider_names = _parse_csv(os.getenv("AGENT_TOOL_PROVIDERS"), DEFAULT_TOOL_PROVIDERS)
    enabled_providers = set(provider_names)

    if "builtin" in enabled_providers:
        register_builtin_tools(registry)
    if "knowledge" in enabled_providers:
        register_knowledge_tools(registry)
    if "mcp" in enabled_providers:
        registry.register_provider(MCPToolProvider(mcp_registry))
    if "engineering" in enabled_providers and _env_bool("AGENT_ENGINEERING_ENABLED", True):
        registry.register_provider(EngineeringToolProvider.from_env())

    unknown_providers = sorted(
        name for name in enabled_providers
        if name not in {"builtin", "knowledge", "mcp", "engineering"}
    )
    if unknown_providers:
        logger.warning("Unknown agent tool providers ignored: %s", ", ".join(unknown_providers))
