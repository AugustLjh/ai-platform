from __future__ import annotations

from typing import Iterable


class RuntimePolicy:
    def __init__(self, allowed_tools: Iterable[str] | None = None) -> None:
        self._allowed_tools = None if allowed_tools is None else set(allowed_tools)

    def is_tool_allowed(self, tool_name: str) -> bool:
        if self._allowed_tools is None:
            return True
        return tool_name in self._allowed_tools
