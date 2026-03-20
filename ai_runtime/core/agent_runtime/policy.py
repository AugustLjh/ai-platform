from __future__ import annotations

from typing import Iterable


class RuntimePolicy:
    def __init__(self, allowed_tools: Iterable[str] | None = None) -> None:
        self._allowed_tools = set(allowed_tools or [])

    def is_tool_allowed(self, tool_name: str) -> bool:
        if not self._allowed_tools:
            return True
        return tool_name in self._allowed_tools
