"""LRU cache for tool invocations.

Ported from ``ai_runtime/core/agent_runtime/optimization.py``'s
``ToolResultCache``, but expressed as a self-contained LRU cache (no env-var
config wiring) and paired with a :func:`cached_tool` wrapper that intercepts
LangChain ``BaseTool`` invocations.

The cache key is canonicalised by:

- normalising argument dicts (sorted keys, recursively),
- collapsing whitespace in string arguments,
- including the run_id / session_id depending on whether the tool is
  session-scoped (which lets read-only knowledge / workspace look-ups share
  cached results across runs that talk to the same session).
"""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, Iterable, Optional

from langchain_core.tools import BaseTool

from ai_runtime.tools.base import ToolContext, current_tool_context_optional


__all__ = [
    "ToolResultCache",
    "cached_tool",
]


DEFAULT_SESSION_SCOPED_TOOL_NAMES = frozenset(
    {
        "knowledge_search",
        "knowledge_fetch_document",
        "knowledge_fetch_segments",
        "project_list_context",
        "project_search_context",
        "project_read_context_item",
        "project_list_uploaded_files",
        "project_search_uploaded_files",
        "project_read_uploaded_file",
        "workspace_list_files",
        "workspace_read_file",
        "workspace_search_text",
        "git_status",
        "git_diff",
        "git_show",
        "git_log",
    }
)


class ToolResultCache:
    """Async-safe LRU cache for tool results.

    Two scopes are supported:

    - ``"run"`` (default): keyed by ``(tool, run_id, args)``.
    - ``"session"`` (for the names in :data:`DEFAULT_SESSION_SCOPED_TOOL_NAMES`):
      keyed by ``(tool, session_id, args)``, allowing reuse across runs that
      share a chat session.
    """

    def __init__(
        self,
        max_entries: int = 128,
        *,
        session_scoped_tool_names: Optional[Iterable[str]] = None,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = asyncio.Lock()
        self.session_scoped_tool_names: frozenset[str] = frozenset(
            session_scoped_tool_names
            if session_scoped_tool_names is not None
            else DEFAULT_SESSION_SCOPED_TOOL_NAMES
        )

    # ------------------------------------------------------------------ keys
    def _normalize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(k): self._normalize(value[k]) for k in sorted(value.keys(), key=str)
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize(item) for item in value]
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    def resolve_scope(self, *, tool_name: str, session_id: Optional[str]) -> str:
        normalized = str(tool_name or "").strip()
        if session_id and normalized in self.session_scoped_tool_names:
            return "session"
        return "run"

    def build_key(
        self,
        *,
        tool_name: str,
        run_id: str,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_definition_id: Optional[str] = None,
        workspace_root: Optional[str] = None,
        allowed_knowledge_base_ids: Iterable[str] = (),
        allowed_mcp_server_ids: Iterable[str] = (),
        allowed_mcp_tool_names: Iterable[str] = (),
        arguments: Optional[dict[str, Any]] = None,
    ) -> str:
        scope = self.resolve_scope(tool_name=tool_name, session_id=session_id)
        payload = {
            "scope": scope,
            "tool_name": tool_name,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "agent_definition_id": agent_definition_id,
            "run_id": run_id if scope == "run" else None,
            "session_id": session_id if scope == "session" else None,
            "workspace_root": workspace_root,
            "allowed_knowledge_base_ids": list(allowed_knowledge_base_ids),
            "allowed_mcp_server_ids": list(allowed_mcp_server_ids),
            "allowed_mcp_tool_names": list(allowed_mcp_tool_names),
            "arguments": self._normalize(arguments or {}),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    # ----------------------------------------------------------------- store
    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        """Return ``(value, hit)``; computes via ``compute()`` on miss."""

        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached, True

        result = await compute()

        async with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                self._entries.move_to_end(key)
                return existing, True
            self._entries[key] = result
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return result, False


def _kwargs_from_invoke_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Coerce LangChain ``BaseTool._arun`` invocation args into a kwargs dict.

    LangChain may pass arguments positionally or as keywords depending on the
    args_schema; for cache key purposes we just need a deterministic mapping.
    """
    payload: dict[str, Any] = {}
    if args:
        # Single positional dict means the caller used ``ainvoke({...})``.
        if len(args) == 1 and isinstance(args[0], dict):
            payload.update(args[0])
        else:
            payload["_positional"] = list(args)
    payload.update(kwargs)
    return payload


def cached_tool(tool: BaseTool, cache: ToolResultCache) -> BaseTool:
    """Return a ``BaseTool`` wrapper that caches results in ``cache``.

    The cache key includes the active :class:`ToolContext` if one is bound;
    otherwise we fall back to a "no context" sentinel run_id, which is rare in
    production but useful in tests / direct invocations.
    """

    if cache is None:
        return tool

    if isinstance(tool, _CachedTool):  # avoid double-wrapping
        return tool

    return _CachedTool(inner=tool, cache=cache)


class _CachedTool(BaseTool):
    """Internal cache wrapper. Delegates everything else to the inner tool."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    inner: BaseTool
    cache: ToolResultCache

    def __init__(self, *, inner: BaseTool, cache: ToolResultCache) -> None:
        super().__init__(
            name=inner.name,
            description=inner.description,
            args_schema=inner.args_schema,
            return_direct=inner.return_direct,
            response_format=getattr(inner, "response_format", "content"),
            metadata=dict(getattr(inner, "metadata", None) or {}),
            tags=list(getattr(inner, "tags", None) or []),
            inner=inner,
            cache=cache,
        )

    def _build_key(self, payload: dict[str, Any]) -> str:
        ctx = current_tool_context_optional()
        if ctx is None:
            run_id = "_no_run"
            session_id = None
            tenant_id = None
            user_id = None
            agent_definition_id = None
            workspace_root = None
            allowed_knowledge_base_ids: tuple[str, ...] = ()
            allowed_mcp_server_ids: tuple[str, ...] = ()
            allowed_mcp_tool_names: tuple[str, ...] = ()
        else:
            run_id = ctx.run_id
            session_id = ctx.session_id
            tenant_id = ctx.tenant_id
            user_id = ctx.user_id
            agent_definition_id = ctx.agent_definition_id
            workspace_root = ctx.workspace_root
            allowed_knowledge_base_ids = tuple(ctx.allowed_knowledge_base_ids)
            allowed_mcp_server_ids = tuple(ctx.allowed_mcp_server_ids)
            allowed_mcp_tool_names = tuple(ctx.allowed_mcp_tool_names)

        return self.cache.build_key(
            tool_name=self.inner.name,
            run_id=run_id,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_definition_id=agent_definition_id,
            workspace_root=workspace_root,
            allowed_knowledge_base_ids=allowed_knowledge_base_ids,
            allowed_mcp_server_ids=allowed_mcp_server_ids,
            allowed_mcp_tool_names=allowed_mcp_tool_names,
            arguments=payload,
        )

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        # The legacy cache is async; for sync paths we just bypass caching.
        return self.inner._run(*args, **kwargs)

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        payload = _kwargs_from_invoke_args(args, kwargs)
        key = self._build_key(payload)

        async def _compute() -> Any:
            return await self.inner._arun(*args, **kwargs)

        result, _ = await self.cache.get_or_compute(key, _compute)
        return result
