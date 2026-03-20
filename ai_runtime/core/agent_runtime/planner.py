from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from core.agent_runtime.models import AgentDefinition, PlannerAction, PlannerResult


MATH_EXPRESSION_RE = re.compile(r"^\s*[-+()*/%.\d\s]+\s*$")


class AgentPlanner:
    def plan(
        self,
        definition: AgentDefinition,
        run_input: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
    ) -> PlannerResult:
        message = str(run_input.get("message") or run_input.get("prompt") or "").strip()
        if not message:
            return PlannerResult(
                action=PlannerAction(
                    type="ask_user",
                    title="Need more input",
                    question="Please provide the task you want this agent to run.",
                ),
                reasoning="The run input does not include a user message.",
            )

        lowered = message.lower()
        tool_names = {tool["name"] for tool in available_tools}

        if "get_current_time" in lowered or "current time" in lowered or "现在几点" in message:
            return PlannerResult(
                action=PlannerAction(
                    type="tool_call",
                    title="Get current time",
                    tool_name="get_current_time",
                    tool_arguments={},
                ),
                reasoning="The request explicitly asks for the current time.",
            )

        if "echo_json" in lowered and "echo_json" in tool_names:
            payload = run_input.get("payload", run_input)
            return PlannerResult(
                action=PlannerAction(
                    type="tool_call",
                    title="Echo JSON payload",
                    tool_name="echo_json",
                    tool_arguments={"payload": payload},
                ),
                reasoning="The request explicitly targets the echo_json tool.",
            )

        if "calculator" in tool_names:
            expression = run_input.get("expression")
            if not expression and MATH_EXPRESSION_RE.match(message):
                expression = message
            if expression:
                return PlannerResult(
                    action=PlannerAction(
                        type="tool_call",
                        title="Evaluate expression",
                        tool_name="calculator",
                        tool_arguments={"expression": str(expression)},
                    ),
                    reasoning="The request can be answered with the calculator tool.",
                )

        if "{" in message and "}" in message and "echo_json" in tool_names:
            try:
                payload = json.loads(message)
                return PlannerResult(
                    action=PlannerAction(
                        type="tool_call",
                        title="Echo inline JSON",
                        tool_name="echo_json",
                        tool_arguments={"payload": payload},
                    ),
                    reasoning="The message is a JSON object and can be validated with echo_json.",
                )
            except json.JSONDecodeError:
                pass

        summary = f"{definition.name} received: {message}"
        return PlannerResult(
            action=PlannerAction(
                type="final_answer",
                title="Return direct answer",
                content=summary,
            ),
            reasoning="No tool call is required for this input.",
        )
