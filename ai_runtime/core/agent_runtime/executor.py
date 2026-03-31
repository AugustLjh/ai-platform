from __future__ import annotations

import json
from typing import Any, Dict

from core.agent_runtime.models import PlannerResult
from core.agent_runtime.policy import RuntimePolicy
from core.agent_runtime.schema_utils import normalize_output_schema
from core.agent_runtime.tools.base import ToolContext, ToolLookupContext
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

        tool = await self.registry.get(
            action.tool_name,
            context=ToolLookupContext(
                tenant_id=tool_context.tenant_id,
                user_id=tool_context.user_id,
                agent_definition_id=tool_context.agent_definition_id,
                run_id=tool_context.run_id,
            ),
        )
        if tool is None:
            raise ValueError(f"Tool {action.tool_name} is not registered")
        return await tool.execute(tool_context, action.tool_arguments)

    def _select_effective_schema(self, output_schema: Dict[str, Any] | None) -> Dict[str, Any]:
        return normalize_output_schema(output_schema)

    def _shape_output(self, value: Any, output_schema: Dict[str, Any] | None) -> Any:
        schema = self._select_effective_schema(output_schema)
        if not schema:
            return value
        return self._coerce_value_to_schema(value, schema)

    def shape_output(self, value: Any, output_schema: Dict[str, Any] | None) -> Any:
        return self._shape_output(value, output_schema)

    def _default_value_for_schema(self, schema: Dict[str, Any]) -> Any:
        if "default" in schema:
            return schema["default"]

        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            return {
                key: self._default_value_for_schema(prop)
                for key, prop in properties.items()
                if isinstance(prop, dict)
            }
        if schema_type == "array":
            return []
        if schema_type == "string":
            return ""
        if schema_type == "integer":
            return 0
        if schema_type == "number":
            return 0
        if schema_type == "boolean":
            return False
        return None

    def _coerce_primitive(self, value: Any, schema_type: str) -> Any:
        if schema_type == "string":
            if isinstance(value, str):
                return value
            if value is None:
                return ""
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

        if schema_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes"}
            return bool(value)

        if schema_type in {"integer", "number"}:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(value) if schema_type == "integer" else value
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return 0
                try:
                    parsed = float(text)
                except ValueError:
                    return 0
                return int(parsed) if schema_type == "integer" else parsed
            return 0

        return value

    def _coerce_value_to_schema(self, value: Any, schema: Dict[str, Any]) -> Any:
        if not isinstance(schema, dict) or not schema:
            return value

        schema_type = schema.get("type")
        if schema_type in {"string", "boolean", "integer", "number"}:
            return self._coerce_primitive(value, schema_type)

        if schema_type == "array":
            items_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
            if isinstance(value, list):
                return [self._coerce_value_to_schema(item, items_schema) for item in value]
            if value is None:
                return []
            return [self._coerce_value_to_schema(value, items_schema)] if items_schema else [value]

        if schema_type != "object":
            return value

        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        shaped: Dict[str, Any] = {}

        if isinstance(value, dict):
            source = value
        else:
            source = {}
            string_targets = [key for key, prop in properties.items() if isinstance(prop, dict) and prop.get("type") == "string"]
            if "answer" in properties:
                source["answer"] = value
            elif "summary" in properties:
                source["summary"] = value
            elif string_targets:
                source[string_targets[0]] = value
            elif "result" in properties:
                source["result"] = value

        for key, prop in properties.items():
            if not isinstance(prop, dict):
                continue
            if key in source:
                shaped[key] = self._coerce_value_to_schema(source[key], prop)
                continue
            if key in required or prop.get("type") in {"array", "object", "boolean", "integer", "number"}:
                shaped[key] = self._default_value_for_schema(prop)

        extra_allowed = schema.get("additionalProperties", True)
        if extra_allowed and isinstance(source, dict):
            for key, item in source.items():
                if key not in shaped:
                    shaped[key] = item

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
