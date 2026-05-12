from __future__ import annotations

import asyncio
import json
import os
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
    return max(minimum, min(parsed, maximum))


@dataclass(frozen=True)
class AgentRuntimeOptimizationConfig:
    default_max_iterations: int = 5
    planner_max_tokens: int = 500
    intent_max_tokens: int = 700
    synthesis_max_tokens: int = 1400
    enable_intent_preprocess_short_circuit: bool = True
    enable_summarizer_short_circuit: bool = True
    enable_tool_result_cache: bool = True
    tool_cache_max_entries: int = 128
    enable_async_noncritical_events: bool = True
    disable_planner_repair: bool = False

    @classmethod
    def from_env(cls) -> "AgentRuntimeOptimizationConfig":
        return cls(
            default_max_iterations=_env_int("AGENT_DEFAULT_MAX_ITERATIONS", 5, minimum=2, maximum=20),
            planner_max_tokens=_env_int("AGENT_PLANNER_MAX_TOKENS", 500, minimum=200, maximum=2000),
            intent_max_tokens=_env_int("AGENT_INTENT_MAX_TOKENS", 700, minimum=200, maximum=1600),
            synthesis_max_tokens=_env_int("AGENT_SYNTHESIS_MAX_TOKENS", 1400, minimum=400, maximum=3200),
            enable_intent_preprocess_short_circuit=_env_bool("AGENT_ENABLE_INTENT_SHORT_CIRCUIT", True),
            enable_summarizer_short_circuit=_env_bool("AGENT_ENABLE_SUMMARIZER_SHORT_CIRCUIT", True),
            enable_tool_result_cache=_env_bool("AGENT_ENABLE_TOOL_RESULT_CACHE", True),
            tool_cache_max_entries=_env_int("AGENT_TOOL_CACHE_MAX_ENTRIES", 128, minimum=16, maximum=1024),
            enable_async_noncritical_events=_env_bool("AGENT_ENABLE_ASYNC_NONCRITICAL_EVENTS", True),
            disable_planner_repair=_env_bool("AGENT_DISABLE_PLANNER_REPAIR", False),
        )


class ToolResultCache:
    SESSION_SCOPED_TOOL_NAMES = {
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

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max(1, max_entries)
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _normalize_argument_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._normalize_argument_value(value[key])
                for key in sorted(value.keys(), key=str)
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize_argument_value(item) for item in value]
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    def resolve_scope(self, *, tool_name: str, session_id: str | None) -> str:
        normalized_name = str(tool_name or "").strip()
        if session_id and normalized_name in self.SESSION_SCOPED_TOOL_NAMES:
            return "session"
        return "run"

    def build_key(
        self,
        *,
        tool_name: str,
        tenant_id: str,
        user_id: str | None,
        agent_definition_id: str | None,
        run_id: str,
        session_id: str | None = None,
        allowed_knowledge_base_ids: tuple[str, ...] = (),
        allowed_mcp_server_ids: tuple[str, ...] = (),
        allowed_mcp_tool_names: tuple[str, ...] = (),
        workspace_root: str | None = None,
        arguments: dict[str, Any] | None = None,
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
            "allowed_knowledge_base_ids": list(allowed_knowledge_base_ids),
            "allowed_mcp_server_ids": list(allowed_mcp_server_ids),
            "allowed_mcp_tool_names": list(allowed_mcp_tool_names),
            "workspace_root": workspace_root,
            "arguments": self._normalize_argument_value(arguments or {}),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
    ) -> tuple[dict[str, Any], bool]:
        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached, True

        result = await compute()

        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached, True
            self._entries[key] = result
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return result, False
