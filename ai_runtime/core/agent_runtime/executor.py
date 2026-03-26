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
        policy: RuntimePolicy | None = None,
    ) -> Dict[str, Any]:
        action = planner_result.action
        if action.type != "tool_call" or not action.tool_name:
            raise ValueError("planner_result does not contain a tool_call action")
        active_policy = policy or self.policy
        if not active_policy.is_tool_allowed(action.tool_name):
            raise PermissionError(f"Tool {action.tool_name} is not allowed by policy")

        tool = self.registry.get(action.tool_name)
        if tool is None:
            raise ValueError(f"Tool {action.tool_name} is not registered")
        return await tool.execute(tool_context, action.tool_arguments)

    def _select_effective_schema(self, output_schema: Dict[str, Any] | None) -> Dict[str, Any]:
        if not isinstance(output_schema, dict):
            return {}
        for key in ("allOf", "anyOf", "oneOf"):
            schemas = output_schema.get(key)
            if isinstance(schemas, list):
                for schema in schemas:
                    if isinstance(schema, dict):
                        return schema
        return output_schema

    def _shape_output(self, value: Any, output_schema: Dict[str, Any] | None) -> Any:
        schema = self._select_effective_schema(output_schema)
        if not schema:
            return value

        schema_type = schema.get("type")
        if schema_type == "string":
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        if schema_type == "array":
            return value if isinstance(value, list) else [value]

        if schema_type != "object":
            return value

        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if isinstance(value, dict):
            shaped = dict(value)
        else:
            shaped = {}

        if not isinstance(value, dict):
            string_keys = [key for key, prop in properties.items() if isinstance(prop, dict) and prop.get("type") == "string"]
            array_keys = [key for key, prop in properties.items() if isinstance(prop, dict) and prop.get("type") == "array"]
            object_keys = [key for key, prop in properties.items() if isinstance(prop, dict) and prop.get("type") == "object"]

            if "result" in properties:
                shaped["result"] = value
            elif string_keys:
                shaped[string_keys[0]] = value
            else:
                shaped["result"] = value

            for key in array_keys:
                shaped.setdefault(key, [])
            for key in object_keys:
                shaped.setdefault(key, {})

        return shaped

    def format_output(self, value: Any, output_schema: Dict[str, Any] | None = None) -> str:
        shaped_output = self._shape_output(value, output_schema)
        if isinstance(shaped_output, str):
            return shaped_output
        return json.dumps(shaped_output, ensure_ascii=False)

    def build_final_answer(
        self,
        planner_result: PlannerResult,
        tool_result: Dict[str, Any] | None = None,
        output_schema: Dict[str, Any] | None = None,
    ) -> str:
        action = planner_result.action
        if action.type == "ask_user":
            return action.question or "More input is required."

        raw_output: Any
        if action.type == "tool_call":
            raw_output = {
                "tool_name": action.tool_name,
                "tool_result": tool_result or {},
            }
        else:
            raw_output = action.content or ""

        return self.format_output(raw_output, output_schema)
