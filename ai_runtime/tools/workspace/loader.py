"""Loader for workspace tools — wraps legacy workspace provider tools as BaseTool.

The legacy ``workspace.py`` module exposes a ``WORKSPACE_TOOL_TYPES`` dict
mapping name → class. This loader instantiates each tool with a permissive
policy (only used for spec discovery) and wraps it via ``legacy_to_base_tool``.

The legacy tool's ``_run_*`` methods take the policy from ``__init__`` so we
need to construct a policy first; we use a minimal policy with no roots so the
tools fail at execution time if no workspace is bound. This is acceptable —
the loader's job is to wire metadata, not to enforce policy.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_runtime.tools.from_legacy import legacy_to_base_tool

if TYPE_CHECKING:
    from ai_runtime.tools.registry import ToolRegistry

__all__ = ["register_into", "load_tools"]

logger = logging.getLogger(__name__)

# Count derived from WORKSPACE_TOOL_TYPES in legacy workspace.py.
EXPECTED_TOOL_COUNT = 22


def load_tools():
    """Load and wrap legacy workspace tools using their default policy."""
    try:
        from ai_runtime.core.agent_runtime.tools.providers.workspace import (  # type: ignore[import]
            WORKSPACE_TOOL_TYPES,
            WorkspacePolicy,
        )
    except ImportError:
        logger.warning(
            "workspace loader: legacy module not available; no tools loaded"
        )
        return []

    # Build a minimal policy: no roots, no lifecycle. Tools will fail
    # at execute time if a workspace_root is required but not bound; this is
    # intentional — they need a real policy at run time via the provider's
    # ``from_env`` factory. Here we only need the spec.
    try:
        policy = WorkspacePolicy(
            roots=(),
            lifecycle_base_root=None,
            lifecycle_source_roots=(),
            lifecycle_max_files=5000,
            lifecycle_max_bytes=200 * 1024 * 1024,
            lifecycle_retention_hours=168,
        )
    except Exception:
        logger.warning("workspace loader: failed to build default policy", exc_info=True)
        return []

    base_tools = []
    for name, tool_cls in WORKSPACE_TOOL_TYPES.items():
        try:
            legacy_tool = tool_cls(policy)
        except Exception:
            logger.debug(
                "workspace loader: failed to instantiate %s; skipping", name, exc_info=True
            )
            continue
        base_tools.append(legacy_to_base_tool(legacy_tool))
    return base_tools


def register_into(registry: "ToolRegistry") -> int:
    tools = load_tools()
    for tool in tools:
        # Workspace tools require a workspace_root in the context.
        is_write = any(
            keyword in tool.name
            for keyword in ("apply_patch", "create_file", "write_file", "rename_path", "delete_path", "cleanup_expired")
        )
        registry.register(
            tool,
            kind="workspace",
            provider="workspace",
            requires_workspace=True,
            risk_level="medium" if is_write else "low",
        )
    return len(tools)
