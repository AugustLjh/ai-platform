from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.agent_runtime.schema_utils import normalize_output_schema
from core.agent_runtime.skills.models import SkillRuntimeContext


class AgentSummarizer:
    def _build_schema_example(self, output_schema: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(output_schema, dict) or not isinstance(output_schema.get("properties"), dict):
            return None

        example: Dict[str, Any] = {}
        for key, prop in output_schema["properties"].items():
            if not isinstance(prop, dict):
                continue
            schema_type = prop.get("type")
            if schema_type == "string":
                if key in {"answer", "summary"}:
                    example[key] = "Concise final answer grounded in the execution record."
                else:
                    example[key] = f"{key} text"
            elif schema_type == "array":
                item_schema = prop.get("items") if isinstance(prop.get("items"), dict) else {}
                item_type = item_schema.get("type")
                if item_type == "object":
                    nested: Dict[str, Any] = {}
                    for nested_key, nested_prop in (item_schema.get("properties") or {}).items():
                        if not isinstance(nested_prop, dict):
                            continue
                        nested_type = nested_prop.get("type")
                        if nested_type == "string":
                            nested[nested_key] = f"{nested_key} text"
                        elif nested_type == "integer":
                            nested[nested_key] = 1
                        elif nested_type == "array":
                            nested[nested_key] = []
                        elif nested_type == "object":
                            nested[nested_key] = {}
                    example[key] = [nested]
                else:
                    example[key] = [f"{key} item"]
            elif schema_type == "object":
                object_value: Dict[str, Any] = {}
                for nested_key, nested_prop in (prop.get("properties") or {}).items():
                    if not isinstance(nested_prop, dict):
                        continue
                    nested_type = nested_prop.get("type")
                    if nested_type == "string":
                        object_value[nested_key] = f"{nested_key} text"
                    elif nested_type == "array":
                        object_value[nested_key] = []
                    elif nested_type == "object":
                        object_value[nested_key] = {}
                example[key] = object_value
        return example or None

    def _build_schema_guidance(self, output_schema: Dict[str, Any] | None) -> list[str]:
        if not isinstance(output_schema, dict) or not isinstance(output_schema.get("properties"), dict):
            return []

        keys = list(output_schema["properties"].keys())
        guidance = [
            "Fill every declared top-level field with the correct JSON type, even when some sections are empty.",
            "Prefer concise but information-dense field values over verbose prose outside the schema.",
        ]
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
