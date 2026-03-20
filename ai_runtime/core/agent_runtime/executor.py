from __future__ import annotations

import json
from typing import Any, Dict

from core.agent_runtime.models import PlannerResult
from core.agent_runtime.policy import RuntimePolicy
from core.agent_runtime.tools.base import ToolContext
from core.agent_runtime.tools.registry import ToolRegistry


class AgentExecutor:
    def __init__(self, registry: ToolRegistry, policy: RuntimePolicy | None = None) -> None:
        self.registry = registry
        self.policy = policy or RuntimePolicy()

    async def execute_tool(
        self,
        planner_result: PlannerResult,
        *,
        tool_context: ToolContext,
    ) -> Dict[str, Any]:
        action = planner_result.action
        if action.type != "tool_call" or not action.tool_name:
            raise ValueError("planner_result does not contain a tool_call action")
        if not self.policy.is_tool_allowed(action.tool_name):
            raise PermissionError(f"Tool {action.tool_name} is not allowed by policy")

        tool = self.registry.get(action.tool_name)
        if tool is None:
            raise ValueError(f"Tool {action.tool_name} is not registered")
        return await tool.execute(tool_context, action.tool_arguments)

    def build_final_answer(self, planner_result: PlannerResult, tool_result: Dict[str, Any] | None = None) -> str:
        action = planner_result.action
        if action.type == "ask_user":
            return action.question or "More input is required."
        if action.type == "tool_call":
            return json.dumps(
                {
                    "tool_name": action.tool_name,
                    "tool_result": tool_result or {},
                },
                ensure_ascii=False,
            )
        return action.content or ""
