from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

from ai_runtime.core.agent_runtime.context_compressor import PROMPT_CONTEXT_KEY
from ai_runtime.core.agent_runtime.models import (
    AgentDefinition,
    PlannerAction,
    PlannerResult,
    PlannerStep,
)
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig
from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget
from ai_runtime.llm import OPENAI_COMPATIBLE_PROVIDERS

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class AgentPlanner:
    def __init__(self, optimization_config: AgentRuntimeOptimizationConfig | None = None) -> None:
        self.optimization_config = optimization_config or AgentRuntimeOptimizationConfig.from_env()

    def _supports_native_json_mode(self, llm_resolution: Dict[str, Any]) -> bool:
        candidates = llm_resolution.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return False
        supported_providers = {"deepseek", *OPENAI_COMPATIBLE_PROVIDERS}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                return False
            provider = str(candidate.get("provider") or "").strip().lower()
            if provider not in supported_providers:
                return False
        return True

    def _is_recoverable_format_error(self, error: Exception) -> bool:
        message = str(error)
        return (
            "planner returned an empty response" in message
            or "planner did not return valid JSON" in message
            or "planner response is missing action" in message
        )

    def _build_repair_prompt(self) -> str:
        return (
            "Your previous reply was not valid planner JSON.\n"
            "Return exactly one valid JSON object and nothing else.\n"
            "Do not use markdown code fences.\n"
            "The JSON must include: reasoning, steps, and action.\n"
            "Keep reasoning and steps compact."
        )

    def _build_tool_strategy_notes(self, available_tools: List[Dict[str, Any]]) -> List[str]:
        tool_names = {str(tool.get("name") or "").strip() for tool in available_tools}
        notes: List[str] = []

        if {"project_list_context", "project_search_context"} & tool_names:
            notes.append(
                "For project-context tasks, inspect the current conversation or uploaded documents first instead of assuming missing details."
            )
        if "project_search_context" in tool_names and "project_read_context_item" in tool_names:
            notes.append(
                "Prefer searching for the relevant message or document before reading a specific item in full."
            )
        if "knowledge_search" in tool_names and (
            "knowledge_fetch_document" in tool_names or "knowledge_fetch_segments" in tool_names
        ):
            notes.append(
                "Prefer searching the knowledge base first, then fetch the exact document or segments that support the answer."
            )
        return notes

    def _compact_value(self, value: Any, limit: int = 1200) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value if len(value) <= limit else value[: limit - 3] + "..."
        try:
            serialized = json.dumps(value, ensure_ascii=False)
        except TypeError:
            serialized = str(value)
        return serialized if len(serialized) <= limit else serialized[: limit - 3] + "..."

    def _summarize_recent_steps(
        self,
        step_history: Any,
        *,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        if not isinstance(step_history, Sequence) or isinstance(step_history, (str, bytes, bytearray)):
            return []

        recent_steps = []
        for raw_step in list(step_history)[-limit:]:
            if not isinstance(raw_step, dict):
                continue
            recent_steps.append(
                {
                    "step_index": raw_step.get("step_index"),
                    "title": raw_step.get("title"),
                    "kind": raw_step.get("kind"),
                    "status": raw_step.get("status"),
                    "tool_name": raw_step.get("tool_name"),
                    "tool_arguments": raw_step.get("tool_arguments"),
                    "result": self._compact_value(raw_step.get("result")),
                    "error": str(raw_step.get("error") or "").strip() or None,
                }
            )
        return recent_steps

    def _build_system_prompt(
        self,
        *,
        definition: AgentDefinition,
        available_tools: List[Dict[str, Any]],
        available_subagents: List[SubagentTarget] | None = None,
    ) -> str:
        tools_json = json.dumps(available_tools, ensure_ascii=False, indent=2)
        subagents_json = json.dumps(
            [
                {
                    "slug": target.slug,
                    "name": target.name,
                    "publication_id": target.publication_id,
                    "version_id": target.version_id,
                    "description": target.description,
                    "review_policy": target.review_policy,
                }
                for target in (available_subagents or [])
            ],
            ensure_ascii=False,
            indent=2,
        )
        instructions = [
            "You are Codex-style planning brain for an autonomous engineering agent.",
            "Decide the single best next action for the current iteration.",
            "Operate with a direct, execution-first mindset: inspect available context before acting, avoid unsupported assumptions, and keep the run moving on the critical path.",
            "Assume the user wants action, not discussion, unless the execution state proves the task is blocked.",
            "Be deeply pragmatic: choose the action that most directly advances the task right now, not a side quest or a generic planning detour.",
            "Choose the action that most directly reduces uncertainty or advances the main task right now.",
            "Persist until the task is actually complete within the current run whenever the available tools make that possible.",
            "You must not claim a task is done unless the execution record supports it.",
            "If tool use is needed, choose exactly one tool_call action.",
            "When context is incomplete, prefer discovery actions that inspect conversation history, uploaded documents, or retrieved knowledge before synthesis.",
            "Use recent conversation and resolved references to handle pronouns, omitted subjects, and shorthand requests.",
            "If pending_subagent_invocations is non-empty, those child runs are still executing or awaiting aggregation; do not claim their delegated work is complete until a terminal subagent observation appears in step_history.",
            "Incomplete user input alone is not sufficient reason to choose ask_user.",
            "If the task can proceed under reasonable assumptions, prefer tool_call or final_answer and carry the assumptions forward.",
            "Prefer narrow, evidence-gathering tool calls over broad speculative ones.",
            "Prefer making progress with the existing tools before asking the user.",
            "Use delegate only when a configured specialist capability is clearly the best bounded next action and the handoff can be described concretely.",
            "If a tool failed or returned insufficient results, attempt exactly one self-recovery iteration before ask_user.",
            "A self-recovery iteration means choosing one more tool_call that adjusts the query, arguments, or tool choice using the latest step history.",
            "Choose ask_user only when the missing information is still required after available tools have been tried and one self-recovery attempt has been used, or when the user must make a decision that tools cannot infer safely.",
            "Do not ask the user for information that can be recovered from current context, previous tool results, or a better-targeted tool call.",
            "If ask_user_guard is present, treat it as a hard runtime rejection of a previous clarification attempt and choose a different action.",
            "If enough information has been gathered, choose final_answer.",
            "Choose final_answer only when the objective is actually satisfied, or when the remaining blocker must be explained to the user explicitly.",
            "Avoid repeating the same failed tool call with materially identical arguments.",
            "Use the steps field to show a compact execution plan with completed, in_progress, and pending work.",
            "Keep steps implementation-oriented and concrete; mention validation or verification as a pending step when relevant.",
            "Use the provided step_history, pending_question, and tool_failures to avoid repeating failed actions or asking the user too early.",
            "Keep reasoning compact, explicit, and evidence-backed.",
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
                        "type": "tool_call|ask_user|final_answer|delegate",
                        "title": "human readable title",
                        "tool_name": "required for tool_call",
                        "tool_arguments": {},
                        "question": "required for ask_user",
                        "delegate_target": "required for delegate",
                        "delegate_task": "required for delegate",
                        "delegate_input": {},
                        "content": "optional note for final_answer or delegate rationale",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "Planner heuristics:",
            "\n".join(f"- {note}" for note in self._build_tool_strategy_notes(available_tools)) or "- No extra tool-specific heuristics.",
            "Available tools:",
            tools_json,
        ]
        if available_subagents:
            instructions.extend(
                [
                    "Available subagents:",
                    subagents_json,
                    "Delegate only to one of the configured capability targets above. Choose the target by slug or exact name.",
                ]
            )
        if definition.system_prompt.strip():
            instructions.extend(["Agent instructions:", definition.system_prompt.strip()])
        return "\n\n".join(instructions)

    def _build_user_prompt(
        self,
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
        iteration: int,
        available_subagents: List[SubagentTarget] | None = None,
    ) -> str:
        prompt_context = runtime_context.get(PROMPT_CONTEXT_KEY, {})
        if not isinstance(prompt_context, dict):
            prompt_context = {}
        prompt_mode = str(prompt_context.get("mode") or "full")
        conversation = prompt_context.get("conversation", runtime_context.get("conversation", []))
        step_history = prompt_context.get("step_history", runtime_context.get("step_history", []))
        compressed_context = prompt_context.get("compressed_context")
        recent_observations = self._summarize_recent_steps(step_history)
        payload = {
            "iteration": iteration,
            "task_input": run_input,
            "prompt_mode": prompt_mode,
            "conversation": conversation,
            "step_history": step_history,
            "recent_observations": recent_observations,
            "latest_observation": recent_observations[-1] if recent_observations else None,
            "compressed_context": compressed_context,
            "intent_state": prompt_context.get("intent_state", runtime_context.get("intent_state", {})),
            "ask_user_guard": prompt_context.get("ask_user_guard", runtime_context.get("ask_user_guard")),
            "context_state": {
                "conversation_message_count": len(runtime_context.get("conversation", []))
                if isinstance(runtime_context.get("conversation"), list)
                else 0,
                "step_history_count": len(runtime_context.get("step_history", []))
                if isinstance(runtime_context.get("step_history"), list)
                else 0,
                "prompt_conversation_count": len(conversation) if isinstance(conversation, list) else 0,
                "prompt_step_history_count": len(step_history) if isinstance(step_history, list) else 0,
                "execution_count": runtime_context.get("execution_count", 0),
                "tool_failures": runtime_context.get("tool_failures", 0),
                "mounted_knowledge_base_ids": runtime_context.get("mounted_knowledge_base_ids", []),
            },
            "tool_failures": runtime_context.get("tool_failures", 0),
            "pending_question": prompt_context.get("pending_question", runtime_context.get("pending_question")),
            "pending_subagent_invocations": runtime_context.get("pending_subagent_invocations", []),
            "available_subagents": [
                {
                    "slug": target.slug,
                    "name": target.name,
                    "description": target.description,
                    "publication_id": target.publication_id,
                    "version_id": target.version_id,
                }
                for target in (available_subagents or [])
            ],
        }
        return (
            "Decide the single best next action from the execution state below.\n"
            "Work in a Codex-style execution loop: inspect evidence first, act directly on the critical path, avoid repetition, and only ask the user if the blocker cannot be removed with current tools.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

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

        hints: List[str] = []
        if text.count("{") != text.count("}"):
            hints.append("unbalanced braces")
        if text.count("[") != text.count("]"):
            hints.append("unbalanced brackets")
        if text.count("```") % 2 != 0:
            hints.append("unclosed code fence")

        suffix = f" ({', '.join(hints)})" if hints else ""
        raise ValueError(f"planner did not return valid JSON{suffix}: {text[:400]}")

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
        available_subagents: List[SubagentTarget] | None = None,
    ) -> PlannerAction:
        action_type = str(raw_action.get("type") or "").strip().lower()
        if action_type not in {"tool_call", "ask_user", "final_answer", "delegate"}:
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

        if action_type == "delegate":
            delegate_target = str(raw_action.get("delegate_target") or "").strip()
            delegate_task = str(raw_action.get("delegate_task") or "").strip()
            delegate_input = raw_action.get("delegate_input")
            if not isinstance(delegate_input, dict):
                delegate_input = {}
            if not available_subagents:
                raise ValueError("planner selected delegate but no subagents are configured")
            allowed_targets = {
                item
                for target in (available_subagents or [])
                for item in {
                    target.slug,
                    target.name,
                    target.agent_definition_id,
                    target.subagent_definition_id,
                    target.publication_id,
                    target.version_id,
                    target.authorization_id,
                }
                if item
            }
            if not delegate_target:
                raise ValueError("planner selected delegate without delegate_target")
            if allowed_targets and delegate_target not in allowed_targets:
                raise ValueError(f"planner selected unavailable subagent target: {delegate_target}")
            if not delegate_task and not delegate_input:
                raise ValueError("planner selected delegate without delegate_task or delegate_input")
            return PlannerAction(
                type="delegate",
                title=title or f"Delegate to {delegate_target}",
                content=str(raw_action.get("content") or "").strip() or None,
                delegate_target=delegate_target,
                delegate_task=delegate_task or None,
                delegate_input=delegate_input,
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
        available_subagents: List[SubagentTarget] | None = None,
        iteration: int,
        model_info: Dict[str, Any],
    ) -> PlannerResult:
        payload = self._extract_json_payload(raw_response)
        raw_action = payload.get("action")
        if not isinstance(raw_action, dict):
            raise ValueError("planner response is missing action")

        return PlannerResult(
            action=self._normalize_action(raw_action, available_tools, available_subagents),
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
        available_subagents: List[SubagentTarget] | None = None,
    ) -> PlannerResult:
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    definition=definition,
                    available_tools=available_tools,
                    available_subagents=available_subagents,
                ),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(
                    run_input=run_input,
                    runtime_context=runtime_context,
                    iteration=iteration,
                    available_subagents=available_subagents,
                ),
            },
        ]
        chat_kwargs: dict[str, Any] = {
            "temperature": 0.1,
            "max_tokens": self.optimization_config.planner_max_tokens,
        }
        if self._supports_native_json_mode(llm_resolution):
            chat_kwargs["response_format"] = {"type": "json_object"}
        raw_response, model_info = await llm_service.chat_with_candidates(
            llm_resolution,
            messages,
            **chat_kwargs,
        )
        try:
            return self._parse_planner_response(
                raw_response,
                available_tools=available_tools,
                available_subagents=available_subagents,
                iteration=iteration,
                model_info=model_info,
            )
        except ValueError as exc:
            should_repair = (
                not self.optimization_config.disable_planner_repair
                or not self._supports_native_json_mode(llm_resolution)
            )
            if not should_repair:
                raise
            if not self._is_recoverable_format_error(exc):
                raise

            repair_messages = [
                *messages,
                {
                    "role": "assistant",
                    "content": raw_response,
                },
                {
                    "role": "user",
                    "content": self._build_repair_prompt(),
                },
            ]
            repaired_response, repaired_model_info = await llm_service.chat_with_candidates(
                llm_resolution,
                repair_messages,
                temperature=0.0,
                max_tokens=1800,
            )
            try:
                return self._parse_planner_response(
                    repaired_response,
                    available_tools=available_tools,
                    available_subagents=available_subagents,
                    iteration=iteration,
                    model_info={
                        **repaired_model_info,
                        "repair_attempted": True,
                        "initial_raw_response": raw_response,
                    },
                )
            except ValueError as repair_exc:
                raise ValueError(
                    f"{exc}; planner retry also failed: {repair_exc}"
                ) from repair_exc
