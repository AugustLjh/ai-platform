from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.agent_runtime.schema_utils import normalize_output_schema
from core.agent_runtime.skills.models import SkillRuntimeContext


class AgentSummarizer:
    def _example_value_for_schema(self, schema: Dict[str, Any] | None, field_name: str = "value") -> Any:
        if not isinstance(schema, dict):
            return {}

        if "const" in schema:
            return schema["const"]

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            return enum_values[0]

        schema_type = schema.get("type")
        if schema_type == "string":
            if field_name in {"answer", "summary"}:
                return "Concise final answer grounded in the execution record."
            return f"{field_name} text"
        if schema_type == "integer":
            return 1
        if schema_type == "number":
            return 1
        if schema_type == "boolean":
            return False
        if schema_type == "array":
            item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
            return [self._example_value_for_schema(item_schema, field_name=f"{field_name}_item")]
        if schema_type == "object":
            value: Dict[str, Any] = {}
            for nested_key, nested_prop in (schema.get("properties") or {}).items():
                if not isinstance(nested_prop, dict):
                    continue
                value[nested_key] = self._example_value_for_schema(nested_prop, field_name=nested_key)
            return value
        return {}

    def _build_schema_example(self, output_schema: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(output_schema, dict) or not isinstance(output_schema.get("properties"), dict):
            return None

        example: Dict[str, Any] = {}
        for key, prop in output_schema["properties"].items():
            if not isinstance(prop, dict):
                continue
            example[key] = self._example_value_for_schema(prop, field_name=key)
        return example or None

    def _build_schema_guidance(self, output_schema: Dict[str, Any] | None) -> list[str]:
        if not isinstance(output_schema, dict) or not isinstance(output_schema.get("properties"), dict):
            return []

        keys = list(output_schema["properties"].keys())
        guidance = [
            "Fill every declared top-level field with the correct JSON type, even when some sections are empty.",
            "Prefer concise but information-dense field values over verbose prose outside the schema.",
        ]
        required = output_schema.get("required") if isinstance(output_schema.get("required"), list) else []
        if required:
            guidance.append(f"Do not omit required fields: {', '.join(required)}.")

        enum_notes = []
        for key, prop in output_schema["properties"].items():
            if not isinstance(prop, dict):
                continue
            enum_values = prop.get("enum")
            if isinstance(enum_values, list) and enum_values:
                enum_notes.append(f"When {key} is present, use one of: {', '.join(str(item) for item in enum_values)}.")
        guidance.extend(enum_notes[:4])
        if "task_plan" in keys:
            guidance.append("When task_plan is present, include ordered implementation steps and concrete risks.")
        if "review_findings" in keys:
            guidance.append("When review_findings is present, each finding should be specific, evidence-backed, and actionable.")
        if "citations" in keys:
            guidance.append("When citations is present, include sources that directly support the answer.")
        return guidance

    def _build_system_prompt(
        self,
        *,
        system_prompt: str,
        output_schema: Dict[str, Any] | None,
    ) -> str:
        normalized_schema = normalize_output_schema(output_schema)
        base = [
            "You are the final response composer for a Codex-style autonomous engineering agent.",
            "Write the final answer for the user based on the execution record.",
            "Do not invent tool results.",
            "Do not expose internal chain-of-thought or planner internals.",
            "Use a direct, factual, pragmatic tone.",
            "Prefer concise, direct answers unless the task requires structure.",
            "Default to short paragraphs instead of bloated bullet lists.",
            "If work is incomplete or blocked, state the concrete blocker and the next practical step.",
            "If verification ran, mention it briefly. If verification did not run, say so instead of implying success.",
            "If the run proceeded under assumptions or resolved references, state them briefly instead of turning them into follow-up questions.",
        ]
        if system_prompt.strip():
            base.append("Agent instructions:")
            base.append(system_prompt.strip())
        if normalized_schema:
            base.append("Return valid JSON that matches this schema exactly:")
            base.append(json.dumps(normalized_schema, ensure_ascii=False, indent=2))
            example = self._build_schema_example(normalized_schema)
            if example:
                base.append("Use this output shape as a model for structure and field naming:")
                base.append(json.dumps(example, ensure_ascii=False, indent=2))
            schema_guidance = self._build_schema_guidance(normalized_schema)
            if schema_guidance:
                base.append("Schema guidance:")
                base.extend(schema_guidance)
            base.append("Return JSON only, without markdown fences.")
        return "\n\n".join(base)

    def _build_user_prompt(
        self,
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
        planner_note: Optional[str],
    ) -> str:
        payload = {
            "task_input": run_input,
            "conversation": runtime_context.get("conversation", []),
            "step_history": runtime_context.get("step_history", []),
            "intent_state": runtime_context.get("intent_state", {}),
            "planner_note": planner_note or "",
        }
        return (
            "Generate the final response for the user from this execution state.\n"
            "If the task is incomplete or blocked, explain the concrete blocker.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    async def summarize(
        self,
        *,
        llm_service,
        llm_resolution: Dict[str, Any],
        system_prompt: str,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
        skill_context: SkillRuntimeContext | None,
        planner_note: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        output_schema = skill_context.output_schema if skill_context else None
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    system_prompt=system_prompt,
                    output_schema=output_schema,
                ),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(
                    run_input=run_input,
                    runtime_context=runtime_context,
                    planner_note=planner_note,
                ),
            },
        ]
        return await llm_service.chat_with_candidates(
            llm_resolution,
            messages,
            temperature=0.2,
            max_tokens=1600,
        )
