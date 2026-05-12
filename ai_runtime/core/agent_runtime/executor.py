from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Dict

from ai_runtime.core.agent_runtime.models import PlannerResult
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig, ToolResultCache
from ai_runtime.core.agent_runtime.policy import RuntimePolicy
from ai_runtime.core.agent_runtime.schema_utils import normalize_output_schema
from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.registry import ToolRegistry


class AgentExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: RuntimePolicy | None = None,
        optimization_config: AgentRuntimeOptimizationConfig | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy or RuntimePolicy()
        self.optimization_config = optimization_config or AgentRuntimeOptimizationConfig.from_env()
        self._tool_result_cache = ToolResultCache()

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
                session_id=tool_context.session_id,
                allowed_knowledge_base_ids=tool_context.allowed_knowledge_base_ids,
                allowed_mcp_server_ids=tool_context.allowed_mcp_server_ids,
                allowed_mcp_tool_names=tool_context.allowed_mcp_tool_names,
                workspace_root=tool_context.workspace_root,
            ),
        )
        if tool is None:
            raise ValueError(f"Tool {action.tool_name} is not registered")
        if not self.optimization_config.enable_tool_result_cache:
            result = await tool.execute(tool_context, action.tool_arguments)
            cached = False
        else:
            cache = tool_context.tool_result_cache or self._tool_result_cache
            cache_key = cache.build_key(
                tool_name=action.tool_name,
                tenant_id=tool_context.tenant_id,
                user_id=tool_context.user_id,
                agent_definition_id=tool_context.agent_definition_id,
                run_id=tool_context.run_id,
                session_id=tool_context.session_id,
                allowed_knowledge_base_ids=tool_context.allowed_knowledge_base_ids,
                allowed_mcp_server_ids=tool_context.allowed_mcp_server_ids,
                allowed_mcp_tool_names=tool_context.allowed_mcp_tool_names,
                workspace_root=tool_context.workspace_root,
                arguments=action.tool_arguments,
            )
            result, cached = await cache.get_or_compute(cache_key, lambda: tool.execute(tool_context, action.tool_arguments))
        if cached:
            result = dict(result)
            result["cache_hit"] = True
        else:
            result = dict(result)
            result["cache_hit"] = False
        return result

    def _select_effective_schema(self, output_schema: Dict[str, Any] | None) -> Dict[str, Any]:
        return normalize_output_schema(output_schema)

    def _schema_type(self, schema: Dict[str, Any] | None) -> str | None:
        if not isinstance(schema, dict):
            return None
        schema_type = schema.get("type")
        return schema_type if isinstance(schema_type, str) else None

    def _maybe_parse_json_string(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        text = value.strip()
        if len(text) < 2:
            return value

        if (text[0], text[-1]) not in {("{", "}"), ("[", "]")}:
            return value

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value

    def _split_string_items(self, value: str) -> list[str]:
        text = value.strip()
        if not text:
            return []

        lines = []
        for raw_line in text.splitlines():
            item = raw_line.strip()
            if not item:
                continue
            item = re.sub(r"^[-*]\s+", "", item)
            item = re.sub(r"^\d+[.)]\s+", "", item)
            if item:
                lines.append(item)
        if len(lines) > 1:
            return lines

        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) > 1:
            return parts

        return [text]

    def _apply_literal_constraints(self, value: Any, schema: Dict[str, Any]) -> Any:
        if "const" in schema:
            return deepcopy(schema["const"])

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            for candidate in enum_values:
                if value == candidate:
                    return deepcopy(candidate)
                if isinstance(value, str) and isinstance(candidate, str) and value.strip().lower() == candidate.strip().lower():
                    return deepcopy(candidate)
            return deepcopy(enum_values[0])

        return value

    def _enforce_array_constraints(self, values: list[Any], items_schema: Dict[str, Any], schema: Dict[str, Any]) -> list[Any]:
        unique_items = schema.get("uniqueItems") is True
        if unique_items:
            unique_values: list[Any] = []
            seen: set[str] = set()
            for item in values:
                try:
                    marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
                except TypeError:
                    marker = str(item)
                if marker in seen:
                    continue
                seen.add(marker)
                unique_values.append(item)
            values = unique_values

        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and max_items >= 0:
            values = values[:max_items]

        min_items = schema.get("minItems")
        if isinstance(min_items, int) and min_items > 0:
            while len(values) < min_items:
                values.append(self._default_value_for_schema(items_schema))

        return values

    def _extract_array_source(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        for key in ("items", "results", "entries", "records", "matches", "documents", "data"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
            if isinstance(candidate, tuple):
                return list(candidate)

        values = list(value.values())
        if values and all(not isinstance(item, (list, tuple, set)) for item in values):
            return values

        return value

    def _project_object_source(self, source: Dict[str, Any], properties: Dict[str, Any]) -> Dict[str, Any]:
        projected = dict(source)

        if "answer" in properties and "answer" not in projected:
            for key in ("final_output_text", "summary", "final_answer", "response", "message", "content", "result"):
                candidate = projected.get(key)
                if candidate is not None:
                    projected["answer"] = candidate
                    break

        alias_groups = {
            "citations": ("sources", "references"),
            "review_findings": ("findings", "issues", "risks"),
            "code_files": ("files",),
            "file_bundle": ("attachments", "resources", "downloads"),
            "media_gallery": ("image_gallery", "images", "media"),
            "paged_collection": ("paged_results", "page", "page_result"),
            "document_excerpt": ("document_excerpts", "excerpts", "excerpt"),
            "table": ("tables",),
        }
        for target, aliases in alias_groups.items():
            if target not in properties or target in projected:
                continue
            for alias in aliases:
                candidate = projected.get(alias)
                if candidate is not None:
                    projected[target] = candidate
                    break

        property_aliases = {
            "title": ("summary", "name", "label", "message"),
            "severity": ("level", "priority"),
            "description": ("details", "detail", "message", "summary"),
            "path": ("file", "file_path", "filename"),
            "url": ("link", "source_url"),
            "text": ("content", "excerpt", "snippet"),
        }
        for target, aliases in property_aliases.items():
            if target not in properties or target in projected:
                continue
            for alias in aliases:
                candidate = projected.get(alias)
                if candidate is not None:
                    projected[target] = candidate
                    break

        if "task_plan" in properties and "task_plan" not in projected:
            for alias in ("plan", "implementation_plan"):
                candidate = projected.get(alias)
                if isinstance(candidate, dict):
                    projected["task_plan"] = candidate
                    break
            else:
                task_plan: Dict[str, Any] = {}
                for key in ("summary", "steps", "decisions"):
                    candidate = projected.get(key)
                    if candidate is not None:
                        task_plan[key] = candidate
                if task_plan:
                    projected["task_plan"] = task_plan

        if "table" in properties and "table" not in projected and isinstance(projected.get("rows"), list):
            projected["table"] = {
                "title": projected.get("title"),
                "columns": projected.get("columns"),
                "rows": projected.get("rows"),
            }

        missing_array_targets = [
            key
            for key, prop in properties.items()
            if key not in projected and isinstance(prop, dict) and self._schema_type(prop) == "array"
        ]
        if len(missing_array_targets) == 1:
            for alias in ("items", "results", "entries", "records", "matches", "documents", "data"):
                candidate = projected.get(alias)
                if candidate is not None:
                    projected[missing_array_targets[0]] = candidate
                    break

        missing_object_targets = [
            key
            for key, prop in properties.items()
            if key not in projected and isinstance(prop, dict) and self._schema_type(prop) == "object"
        ]
        if len(missing_object_targets) == 1:
            for alias in ("payload", "data", "result", "output", "value"):
                candidate = projected.get(alias)
                if isinstance(candidate, dict):
                    projected[missing_object_targets[0]] = candidate
                    break

        return projected

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

        schema_type = self._schema_type(schema)
        if schema_type in {"string", "boolean", "integer", "number"}:
            return self._apply_literal_constraints(self._coerce_primitive(value, schema_type), schema)

        if schema_type == "array":
            items_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
            value = self._maybe_parse_json_string(value)
            value = self._extract_array_source(value)
            if isinstance(value, list):
                shaped = [self._coerce_value_to_schema(item, items_schema) for item in value]
                return self._apply_literal_constraints(self._enforce_array_constraints(shaped, items_schema, schema), schema)
            if value is None:
                return self._apply_literal_constraints(self._enforce_array_constraints([], items_schema, schema), schema)
            if isinstance(value, tuple):
                shaped = [self._coerce_value_to_schema(item, items_schema) for item in value]
                return self._apply_literal_constraints(self._enforce_array_constraints(shaped, items_schema, schema), schema)
            if isinstance(value, str):
                shaped = [self._coerce_value_to_schema(item, items_schema) for item in self._split_string_items(value)]
                return self._apply_literal_constraints(self._enforce_array_constraints(shaped, items_schema, schema), schema)
            shaped = [self._coerce_value_to_schema(value, items_schema)] if items_schema else [value]
            return self._apply_literal_constraints(self._enforce_array_constraints(shaped, items_schema, schema), schema)

        if schema_type != "object":
            return self._apply_literal_constraints(value, schema)

        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        value = self._maybe_parse_json_string(value)
        shaped: Dict[str, Any] = {}

        if isinstance(value, dict):
            source = self._project_object_source(value, properties)
        else:
            source = {}
            array_targets = [key for key, prop in properties.items() if isinstance(prop, dict) and self._schema_type(prop) == "array"]
            string_targets = [key for key, prop in properties.items() if isinstance(prop, dict) and self._schema_type(prop) == "string"]
            if isinstance(value, (list, tuple)) and len(array_targets) == 1:
                source[array_targets[0]] = list(value)
            elif "answer" in properties:
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
            if key in required or "default" in prop or prop.get("type") in {"array", "object", "boolean", "integer", "number"}:
                shaped[key] = self._default_value_for_schema(prop)

        extra_allowed = schema.get("additionalProperties", True)
        if isinstance(extra_allowed, dict) and isinstance(source, dict):
            for key, item in source.items():
                if key not in shaped:
                    shaped[key] = self._coerce_value_to_schema(item, extra_allowed)
        elif extra_allowed and isinstance(source, dict):
            for key, item in source.items():
                if key not in shaped:
                    shaped[key] = item

        return self._apply_literal_constraints(shaped, schema)

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
