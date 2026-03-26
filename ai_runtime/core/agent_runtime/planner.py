from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

from core.agent_runtime.models import (
    AgentDefinition,
    PlannerAction,
    PlannerResult,
    PlannerStep,
)

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class AgentPlanner:
    def _build_system_prompt(
        self,
        *,
        definition: AgentDefinition,
        available_tools: List[Dict[str, Any]],
    ) -> str:
        tools_json = json.dumps(available_tools, ensure_ascii=False, indent=2)
        instructions = [
            "You are the planning brain for an autonomous agent.",
            "Decide the single best next action for the current iteration.",
            "You must not claim a task is done unless the execution record supports it.",
            "If tool use is needed, choose exactly one tool_call action.",
            "If more user input is required, choose ask_user.",
            "If enough information has been gathered, choose final_answer.",
            "Return JSON only.",
            "JSON schema:",
            json.dumps(
                {
                    "reasoning": "short reason for the next action",
                    "steps": [
                        {
                            "title": "step title",
                            "kind": "analysis|tool|final",
                            "status": "completed|in_progress|pending",
                            "details": "optional",
                        }
                    ],
                    "action": {
                        "type": "tool_call|ask_user|final_answer",
                        "title": "human readable title",
                        "tool_name": "required for tool_call",
                        "tool_arguments": {},
                        "question": "required for ask_user",
                        "content": "optional note for final_answer",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "Available tools:",
            tools_json,
        ]
        if definition.system_prompt.strip():
            instructions.extend(["Agent instructions:", definition.system_prompt.strip()])
        return "\n\n".join(instructions)

    def _build_user_prompt(
        self,
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
        iteration: int,
    ) -> str:
        payload = {
            "iteration": iteration,
            "task_input": run_input,
            "conversation": runtime_context.get("conversation", []),
            "step_history": runtime_context.get("step_history", []),
            "pending_question": runtime_context.get("pending_question"),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _extract_json_payload(self, raw_response: str) -> Dict[str, Any]:
        text = (raw_response or "").strip()
        if not text:
            raise ValueError("planner returned an empty response")

        candidates: List[str] = [text]
        candidates.extend(match.group(1) for match in JSON_BLOCK_RE.finditer(text))

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidates.append(text[first_brace : last_brace + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

        raise ValueError(f"planner did not return valid JSON: {text[:400]}")

    def _normalize_steps(self, raw_steps: Any) -> List[PlannerStep]:
        if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes, bytearray)):
            return []

        steps: List[PlannerStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                continue
            title = str(raw_step.get("title") or "").strip()
            if not title:
                continue
            status = str(raw_step.get("status") or "pending").strip().lower()
            if status not in {"completed", "in_progress", "pending"}:
                status = "pending"
            steps.append(
                PlannerStep(
                    title=title,
                    kind=str(raw_step.get("kind") or "analysis").strip() or "analysis",
                    status=status,  # type: ignore[arg-type]
                    details=str(raw_step.get("details") or "").strip() or None,
                )
            )
        return steps

    def _normalize_action(
        self,
        raw_action: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
    ) -> PlannerAction:
        action_type = str(raw_action.get("type") or "").strip().lower()
        if action_type not in {"tool_call", "ask_user", "final_answer"}:
            raise ValueError(f"planner returned unsupported action type: {action_type or 'empty'}")

        title = str(raw_action.get("title") or "").strip()
        tool_name = str(raw_action.get("tool_name") or "").strip() or None
        tool_arguments = raw_action.get("tool_arguments")
        if not isinstance(tool_arguments, dict):
            tool_arguments = {}

        if action_type == "tool_call":
            allowed_tools = {tool["name"] for tool in available_tools}
            if not tool_name:
                raise ValueError("planner selected tool_call without tool_name")
            if tool_name not in allowed_tools:
                raise ValueError(f"planner selected unavailable tool: {tool_name}")
            return PlannerAction(
                type="tool_call",
                title=title or f"Use {tool_name}",
                tool_name=tool_name,
                tool_arguments=tool_arguments,
            )

        if action_type == "ask_user":
            question = str(raw_action.get("question") or "").strip()
            if not question:
                raise ValueError("planner selected ask_user without question")
            return PlannerAction(
                type="ask_user",
                title=title or "Need more input",
                question=question,
            )

        return PlannerAction(
            type="final_answer",
            title=title or "Prepare final answer",
            content=str(raw_action.get("content") or "").strip() or None,
        )

    def _parse_planner_response(
        self,
        raw_response: str,
        *,
        available_tools: List[Dict[str, Any]],
        iteration: int,
        model_info: Dict[str, Any],
    ) -> PlannerResult:
        payload = self._extract_json_payload(raw_response)
        raw_action = payload.get("action")
        if not isinstance(raw_action, dict):
            raise ValueError("planner response is missing action")

        return PlannerResult(
            action=self._normalize_action(raw_action, available_tools),
            reasoning=str(payload.get("reasoning") or "").strip(),
            steps=self._normalize_steps(payload.get("steps")),
            iteration=iteration,
            metadata={
                **model_info,
                "raw_response": raw_response,
            },
        )

    async def plan(
        self,
        definition: AgentDefinition,
        run_input: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
        *,
        runtime_context: Dict[str, Any],
        iteration: int,
        llm_service,
        llm_resolution: Dict[str, Any],
    ) -> PlannerResult:
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    definition=definition,
                    available_tools=available_tools,
                ),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(
                    run_input=run_input,
                    runtime_context=runtime_context,
                    iteration=iteration,
                ),
            },
        ]
        raw_response, model_info = await llm_service.chat_with_candidates(
            llm_resolution,
            messages,
            temperature=0.1,
            max_tokens=1400,
        )
        return self._parse_planner_response(
            raw_response,
            available_tools=available_tools,
            iteration=iteration,
            model_info=model_info,
        )
