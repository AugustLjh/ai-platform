from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.agent_runtime.skills.models import SkillRuntimeContext


class AgentSummarizer:
    def _build_system_prompt(
        self,
        *,
        system_prompt: str,
        output_schema: Dict[str, Any] | None,
    ) -> str:
        base = [
            "You are the final response composer for an autonomous agent.",
            "Write the final answer for the user based on the execution record.",
            "Do not invent tool results.",
            "Do not expose internal chain-of-thought or planner internals.",
            "Prefer concise, direct answers unless the task requires structure.",
        ]
        if system_prompt.strip():
            base.append("Agent instructions:")
            base.append(system_prompt.strip())
        if output_schema:
            base.append("Return valid JSON that matches this schema exactly:")
            base.append(json.dumps(output_schema, ensure_ascii=False, indent=2))
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
