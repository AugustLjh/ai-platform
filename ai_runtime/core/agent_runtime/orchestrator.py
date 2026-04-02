from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from core.agent_runtime.executor import AgentExecutor
from core.agent_runtime.intent import IntentPreprocessor
from core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from core.agent_runtime.planner import AgentPlanner
from core.agent_runtime.policy import RuntimePolicy
from core.agent_runtime.result_contract import (
    build_artifacts_from_tool_result,
    build_structured_run_result,
    hydrate_legacy_result,
    merge_artifacts,
)
from core.agent_runtime.schema_utils import merge_output_schema
from core.agent_runtime.skills.models import SkillRuntimeContext
from core.agent_runtime.subagents.handoff import SubagentHandoff
from core.agent_runtime.subagents.models import SubagentTarget
from core.agent_runtime.subagents.registry import SubagentRegistry
from core.agent_runtime.subagents.router import SubagentRouter
from core.agent_runtime.summarizer import AgentSummarizer
from core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from core.agent_runtime.tracing import AgentTracer

logger = logging.getLogger(__name__)


def apply_skill_tool_policy(
    available_tools: list[dict[str, Any]],
    skill_context: SkillRuntimeContext | None,
) -> tuple[list[dict[str, Any]], RuntimePolicy, list[str] | None]:
    if skill_context is None or not skill_context.skills:
        return available_tools, RuntimePolicy(), None

    effective_allowlist = [tool_name for tool_name in skill_context.tool_allowlist if str(tool_name).strip()]
    if not effective_allowlist:
        return available_tools, RuntimePolicy(), None

    runtime_policy = RuntimePolicy(effective_allowlist)
    filtered_tools = [
        tool for tool in available_tools
        if runtime_policy.is_tool_allowed(tool["name"])
    ]
    return filtered_tools, runtime_policy, effective_allowlist


class AgentOrchestrator:
    def __init__(
        self,
        planner: AgentPlanner,
        executor: AgentExecutor,
        summarizer: AgentSummarizer,
        llm_service,
        tracer: AgentTracer,
        agent_repository,
        run_repository,
        tool_call_repository,
        state_store,
        skill_registry=None,
        intent_preprocessor: IntentPreprocessor | None = None,
        subagent_registry: SubagentRegistry | None = None,
        subagent_router: SubagentRouter | None = None,
        subagent_handoff: SubagentHandoff | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.summarizer = summarizer
        self.llm_service = llm_service
        self.tracer = tracer
        self.agent_repository = agent_repository
        self.run_repository = run_repository
        self.tool_call_repository = tool_call_repository
        self.state_store = state_store
        self.skill_registry = skill_registry
        self.intent_preprocessor = intent_preprocessor or IntentPreprocessor()
        self.subagent_registry = subagent_registry
        self.subagent_router = subagent_router or SubagentRouter()
        self.subagent_handoff = subagent_handoff

    async def _emit_step_event(
        self,
        run_id: str,
        event_type: str,
        step: Dict[str, Any],
        **payload: Any,
    ) -> None:
        await self.tracer.emit_event(
            run_id,
            event_type,
            step_id=step["id"],
            step_index=step["step_index"],
            kind=step["kind"],
            title=step.get("title"),
            **payload,
        )

    def _truncate_value(self, value: Any, limit: int = 4000) -> Any:
        if isinstance(value, str):
            return value if len(value) <= limit else value[: limit - 3] + "..."
        try:
            serialized = json.dumps(value, ensure_ascii=False)
        except TypeError:
            serialized = str(value)
        if len(serialized) <= limit:
            return value
        return serialized[: limit - 3] + "..."

    def _extract_requested_model(self, definition: AgentDefinition, run_input: Dict[str, Any]) -> Optional[str]:
        selector = str(run_input.get("model") or definition.model or "").strip()
        return selector or None

    def _extract_knowledge_base_id(self, run_input: Dict[str, Any]) -> Optional[str]:
        knowledge_base_id = str(run_input.get("knowledge_base_id") or "").strip()
        return knowledge_base_id or None

    def _resolve_managed_subagent(self, run: AgentRun) -> SubagentTarget | None:
        payload = run.metadata.get("managed_subagent")
        if not isinstance(payload, dict):
            return None
        try:
            target = SubagentTarget.model_validate(payload)
        except Exception:
            logger.exception("Failed to hydrate managed subagent metadata for run %s", run.id)
            return None
        if not target.uses_managed_capability():
            return None
        return target

    def _apply_managed_subagent_definition(
        self,
        definition: AgentDefinition,
        managed_subagent: SubagentTarget | None,
    ) -> AgentDefinition:
        if managed_subagent is None:
            return definition

        system_prompt_parts = [definition.system_prompt.strip(), managed_subagent.system_prompt.strip()]
        metadata = dict(definition.metadata or {})
        metadata["managed_subagent"] = managed_subagent.model_dump(mode="json")
        return definition.model_copy(
            update={
                "name": managed_subagent.name or definition.name,
                "description": managed_subagent.description or definition.description,
                "system_prompt": "\n\n".join(part for part in system_prompt_parts if part),
                "model": managed_subagent.model or definition.model,
                "config": {
                    **(definition.config or {}),
                    **(managed_subagent.config or {}),
                },
                "metadata": metadata,
            }
        )

    def _resolve_managed_knowledge_base_ids(
        self,
        managed_subagent: SubagentTarget | None,
        mounted_knowledge_base_ids: list[str],
    ) -> list[str]:
        if managed_subagent is None:
            return mounted_knowledge_base_ids

        policy = managed_subagent.knowledge_policy or {}
        mode = str(policy.get("mode") or policy.get("access") or "").strip().lower()
        if mode in {"disabled", "none", "deny"} or policy.get("enabled") is False:
            return []

        allowed_ids = []
        raw_allowlist = policy.get("knowledge_base_ids")
        if not isinstance(raw_allowlist, list):
            raw_allowlist = policy.get("allowed_knowledge_base_ids")
        if not isinstance(raw_allowlist, list):
            raw_allowlist = policy.get("ids")
        if not isinstance(raw_allowlist, list):
            raw_allowlist = policy.get("allowlist")
        if isinstance(raw_allowlist, list):
            allowed_ids = [str(item).strip() for item in raw_allowlist if str(item).strip()]

        if not allowed_ids:
            return mounted_knowledge_base_ids
        allowed_set = set(allowed_ids)
        return [knowledge_base_id for knowledge_base_id in mounted_knowledge_base_ids if knowledge_base_id in allowed_set]

    def _resolve_managed_mcp_filters(
        self,
        managed_subagent: SubagentTarget | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if managed_subagent is None:
            return (), ()

        server_ids: list[str] = []
        tool_names: list[str] = []
        for item in managed_subagent.mcp_allowlist:
            if isinstance(item, dict):
                server_id = str(item.get("server_id") or "").strip()
                runtime_name = str(item.get("runtime_name") or item.get("tool_name") or "").strip()
                if server_id:
                    server_ids.append(server_id)
                if runtime_name:
                    tool_names.append(runtime_name)
                continue

            value = str(item or "").strip()
            if not value:
                continue
            if value.count("-") >= 4 and len(value) >= 32:
                server_ids.append(value)
            else:
                tool_names.append(value)

        return tuple(dict.fromkeys(server_ids)), tuple(dict.fromkeys(tool_names))

    def _resolve_max_iterations(self, definition: AgentDefinition) -> int:
        value = definition.config.get("max_iterations", 8)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 8
        return max(2, min(parsed, 20))

    async def _resolve_skill_context(
        self,
        run: AgentRun,
        managed_subagent: SubagentTarget | None = None,
    ) -> SkillRuntimeContext | None:
        if self.skill_registry is None:
            return None
        if managed_subagent is not None:
            return await self.skill_registry.resolve_for_allowlist(
                tenant_id=run.tenant_id,
                allowlist=managed_subagent.skill_allowlist,
                include_fixed_bindings=True,
            )
        return await self.skill_registry.resolve_for_agent(run.agent_definition_id, run.tenant_id)

    async def _resolve_subagent_targets(
        self,
        definition: AgentDefinition,
        managed_subagent: SubagentTarget | None = None,
    ) -> list[SubagentTarget]:
        if self.subagent_registry is None:
            return []
        if managed_subagent is not None and not managed_subagent.allows_nested_delegation():
            return []
        return await self.subagent_registry.resolve_for_definition(definition)

    def _apply_skill_prompt(
        self,
        definition: AgentDefinition,
        skill_context: SkillRuntimeContext | None,
    ) -> AgentDefinition:
        if skill_context and skill_context.system_prompt:
            system_prompt_parts = [definition.system_prompt.strip(), skill_context.system_prompt.strip()]
            return definition.model_copy(update={"system_prompt": "\n\n".join(part for part in system_prompt_parts if part)})
        return definition

    def _select_skill_context_for_phase(
        self,
        skill_context: SkillRuntimeContext | None,
        *,
        inferred_intent: str | None,
        phase: str,
    ) -> SkillRuntimeContext | None:
        if skill_context is None:
            return None
        if self.skill_registry is None:
            return skill_context
        return self.skill_registry.compose_for_intent_phase(
            skill_context.skills,
            inferred_intent=inferred_intent,
            phase=phase,
        )

    async def _resolve_accessible_mounted_knowledge_base_ids(
        self,
        run: AgentRun,
        managed_subagent: SubagentTarget | None = None,
    ) -> list[str]:
        mounted_knowledge_base_ids = await self.agent_repository.list_accessible_knowledge_bindings(
            run.agent_definition_id,
            run.tenant_id,
            run.user_id,
        )
        return self._resolve_managed_knowledge_base_ids(managed_subagent, mounted_knowledge_base_ids)

    def _append_conversation_message(
        self,
        runtime_context: Dict[str, Any],
        *,
        role: str,
        content: str,
    ) -> None:
        text = str(content or "").strip()
        if not text:
            return
        conversation = runtime_context.setdefault("conversation", [])
        if conversation and conversation[-1].get("role") == role and conversation[-1].get("content") == text:
            return
        conversation.append({"role": role, "content": text})

    def _prepare_runtime_context(self, run: AgentRun) -> Dict[str, Any]:
        runtime_context = dict(run.context or {})
        if not isinstance(runtime_context.get("conversation"), list):
            runtime_context["conversation"] = []
        if not isinstance(runtime_context.get("step_history"), list):
            runtime_context["step_history"] = []

        current_message = str(run.input.get("message") or run.input.get("prompt") or "").strip()
        last_user_message = str(runtime_context.get("last_user_message") or "").strip()
        if current_message and current_message != last_user_message:
            self._append_conversation_message(runtime_context, role="user", content=current_message)
            runtime_context["last_user_message"] = current_message
            runtime_context.pop("pending_question", None)
            runtime_context.pop("ask_user_guard", None)

        runtime_context.setdefault("execution_count", 0)
        runtime_context.setdefault("tool_failures", 0)
        return runtime_context

    async def _preprocess_intent(
        self,
        *,
        definition: AgentDefinition,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        available_tools: list[dict[str, Any]],
        llm_resolution: Dict[str, Any],
    ) -> Dict[str, Any]:
        intent_state = await self.intent_preprocessor.preprocess(
            definition,
            run.input,
            available_tools,
            runtime_context=runtime_context,
            llm_service=self.llm_service,
            llm_resolution=llm_resolution,
        )
        runtime_context["intent_state"] = intent_state
        runtime_context["normalized_task_input"] = {
            **run.input,
            "message": intent_state.get("normalized_message") or run.input.get("message") or run.input.get("prompt") or "",
            "original_message": str(run.input.get("message") or run.input.get("prompt") or "").strip(),
            "intent": intent_state.get("inferred_intent"),
            "assumptions": intent_state.get("assumptions", []),
            "search_queries": intent_state.get("search_queries", []),
            "resolved_references": intent_state.get("resolved_references", []),
        }
        return intent_state

    def _tool_attempt_count(self, runtime_context: Dict[str, Any]) -> int:
        step_history = runtime_context.get("step_history", [])
        if not isinstance(step_history, list):
            return 0
        return sum(
            1
            for step in step_history
            if isinstance(step, dict) and (
                str(step.get("tool_name") or "").strip()
                or str(step.get("delegate_target") or "").strip()
            )
        )

    def _approve_ask_user(
        self,
        *,
        action: PlannerAction,
        runtime_context: Dict[str, Any],
        available_tools: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        intent_state = runtime_context.get("intent_state", {})
        if not isinstance(intent_state, dict):
            intent_state = {}

        blocking_missing = intent_state.get("blocking_missing_information")
        if not isinstance(blocking_missing, list):
            blocking_missing = []
        blocking_missing = [str(item).strip() for item in blocking_missing if str(item).strip()]

        requires_user_decision = bool(intent_state.get("requires_user_decision"))
        should_answer_with_assumptions = bool(
            intent_state.get("should_answer_with_assumptions")
            if intent_state.get("should_answer_with_assumptions") is not None
            else True
        )

        if not blocking_missing and should_answer_with_assumptions:
            return False, "non-blocking ambiguity should be handled with assumptions instead of asking the user"

        tool_attempts = self._tool_attempt_count(runtime_context)
        if available_tools and tool_attempts == 0:
            return False, "available tools have not been used yet"

        if available_tools and tool_attempts < 2 and not requires_user_decision:
            return False, "the run should attempt at least one additional self-directed action before asking the user"

        if not blocking_missing and not requires_user_decision:
            return False, "the missing information is not proven to be blocking"

        return True, "approved"

    async def _plan_next_action(
        self,
        *,
        definition: AgentDefinition,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        available_tools: list[dict[str, Any]],
        available_subagents: list[SubagentTarget],
        llm_resolution: Dict[str, Any],
        iteration: int,
    ) -> PlannerResult:
        for attempt in range(2):
            planner_result = await self.planner.plan(
                definition,
                runtime_context.get("normalized_task_input") or run.input,
                available_tools,
                runtime_context=runtime_context,
                iteration=iteration,
                llm_service=self.llm_service,
                llm_resolution=llm_resolution,
                available_subagents=available_subagents,
            )

            if planner_result.action.type != "ask_user":
                runtime_context.pop("ask_user_guard", None)
                return planner_result

            approved, reason = self._approve_ask_user(
                action=planner_result.action,
                runtime_context=runtime_context,
                available_tools=available_tools,
            )
            if approved:
                runtime_context.pop("ask_user_guard", None)
                return planner_result

            runtime_context["ask_user_guard"] = {
                "attempt": attempt + 1,
                "rejected_question": planner_result.action.question,
                "reason": reason,
                "policy": "Do not ask the user yet. Resolve references, use assumptions, and continue with tools or a best-effort answer.",
            }
            await self.tracer.emit_event(
                run.id,
                "plan.ask_user_rejected",
                iteration=iteration,
                question=planner_result.action.question,
                reason=reason,
            )

        fallback_action = PlannerAction(
            type="final_answer",
            title="Answer with current evidence",
            content=(
                "Provide the best possible answer using the current evidence, resolved references, and explicit assumptions. "
                "Do not ask a follow-up question."
            ),
        )
        return planner_result.model_copy(
            update={
                "action": fallback_action,
                "reasoning": (
                    f"{planner_result.reasoning} "
                    "Ask-user was rejected by runtime policy, so return the best possible answer with explicit assumptions."
                ).strip(),
            }
        )

    async def _persist_run_state(
        self,
        run_id: str,
        *,
        status: str,
        runtime_context: Dict[str, Any],
        plan: Optional[Dict[str, Any]] = None,
        final_output: Optional[str] = None,
        final_output_text: Optional[str] = None,
        final_output_json: Any = None,
        error_message: Optional[str] = None,
    ) -> None:
        await self.run_repository.update_run_status(
            run_id,
            status,
            plan=plan,
            context=runtime_context,
            final_output=final_output,
            final_output_text=final_output_text,
            final_output_json=final_output_json,
            error_message=error_message,
        )

    async def _load_terminal_run_surface(self, run_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        latest = await self.run_repository.get_run(run_id)
        if latest is None:
            return None, {
                "final_output": None,
                "final_output_text": None,
                "final_output_json": None,
                "artifacts": [],
            }

        context = latest.get("context") if isinstance(latest.get("context"), dict) else {}
        promoted_artifacts = context.get("promoted_artifacts") if isinstance(context.get("promoted_artifacts"), list) else []
        stored_artifacts = await self.run_repository.list_artifacts(run_id)
        hydrated = hydrate_legacy_result(
            final_output=latest.get("final_output"),
            final_output_text=latest.get("final_output_text"),
            final_output_json=latest.get("final_output_json"),
            artifacts=merge_artifacts(stored_artifacts, promoted_artifacts),
        )
        return latest, hydrated

    def _build_observation(
        self,
        *,
        step: Dict[str, Any],
        planner_result: PlannerResult,
        status: str,
        tool_name: Optional[str] = None,
        tool_arguments: Optional[Dict[str, Any]] = None,
        result: Any = None,
        error: Optional[str] = None,
        delegate_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        observation = {
            "step_index": step["step_index"],
            "step_id": step["id"],
            "title": step.get("title"),
            "kind": step["kind"],
            "status": status,
            "reasoning": planner_result.reasoning,
        }
        if tool_name:
            observation["tool_name"] = tool_name
        if tool_arguments:
            observation["tool_arguments"] = tool_arguments
        if result is not None:
            observation["result"] = self._truncate_value(result)
        if error:
            observation["error"] = error
        if delegate_target:
            observation["delegate_target"] = delegate_target
        return observation

    def _resolve_current_delegation_depth(self, run: AgentRun) -> int:
        delegation = run.metadata.get("delegation")
        if not isinstance(delegation, dict):
            return 0
        try:
            return max(0, int(delegation.get("depth") or 0))
        except (TypeError, ValueError):
            return 0

    def _summarize_handoff_envelope(self, envelope: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            return {}
        context_slice = envelope.get("context_slice")
        if not isinstance(context_slice, dict):
            context_slice = {}
        return {
            "protocol_version": envelope.get("protocol_version"),
            "invocation_id": envelope.get("invocation_id"),
            "task": envelope.get("task"),
            "constraints": envelope.get("constraints") or [],
            "context_slice": {
                "delegation_depth": context_slice.get("delegation_depth"),
                "recent_observation_count": len(context_slice.get("recent_observations") or []),
                "conversation_tail_count": len(context_slice.get("conversation_tail") or []),
                "mounted_knowledge_base_ids": context_slice.get("mounted_knowledge_base_ids") or [],
            },
            "policy_snapshot": envelope.get("policy_snapshot") or {},
        }

    def _evaluate_delegation_gate(
        self,
        *,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        planner_result: PlannerResult,
        target: SubagentTarget,
        available_tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        action = planner_result.action
        delegate_input = action.delegate_input or {}
        step_history = runtime_context.get("step_history")
        if not isinstance(step_history, list):
            step_history = []

        scope_counts = {
            "focus_paths": len(delegate_input.get("focus_paths") or []) if isinstance(delegate_input.get("focus_paths"), list) else 0,
            "deliverables": len(delegate_input.get("deliverables") or []) if isinstance(delegate_input.get("deliverables"), list) else 0,
            "checks": len(delegate_input.get("checks") or []) if isinstance(delegate_input.get("checks"), list) else 0,
            "constraints": len(delegate_input.get("constraints") or []) if isinstance(delegate_input.get("constraints"), list) else 0,
        }
        current_depth = self._resolve_current_delegation_depth(run)
        max_depth = target.max_delegation_depth()
        task_text = "\n".join(
            part.strip()
            for part in (
                str(action.delegate_task or ""),
                str(action.content or ""),
                str(delegate_input.get("message") or ""),
                str(delegate_input.get("prompt") or ""),
            )
            if str(part or "").strip()
        )
        signals: list[str] = []
        blockers: list[str] = []
        mode = target.delegation_mode()

        if target.requires_review():
            signals.append("capability requires an explicit review or verification pass")
        if mode in {"parallel_worker", "parallel", "worker", "reviewer", "judge", "requires_review", "high_risk"}:
            signals.append(f"capability policy marks this target as {mode}")
        if len(step_history) >= 2:
            signals.append("the parent run has already accumulated execution context worth isolating")
        if int(runtime_context.get("tool_failures", 0)) > 0:
            signals.append("recent parent execution failed and a bounded specialist retry is justified")
        if any(scope_counts.values()):
            signals.append("the delegation request is bounded by explicit scope or deliverables")
        if len(task_text) >= 140 or "\n" in task_text:
            signals.append("the handoff task is detailed enough to support isolated execution")
        if target.output_schema:
            signals.append("the capability has a structured output contract that justifies isolated execution")

        if max_depth is not None and current_depth >= max_depth:
            blockers.append(f"delegation depth {current_depth} already reached the target limit {max_depth}")
        if current_depth > 0 and not target.allows_nested_delegation():
            blockers.append("nested delegation is disabled for this capability")
        if available_tools and not step_history and not target.requires_review() and not any(scope_counts.values()):
            blockers.append("single-agent-first gate rejected delegation before any parent execution evidence was gathered")
        if not signals and available_tools:
            blockers.append("no concrete isolation, complexity, parallelism, or quality signal justifies delegation")

        return {
            "allowed": not blockers,
            "decision": "approved" if not blockers else "rejected",
            "reason": "; ".join(blockers) if blockers else "; ".join(signals) or "delegation accepted",
            "signals": signals,
            "blockers": blockers,
            "current_depth": current_depth,
            "max_depth": max_depth,
            "available_tool_count": len(available_tools),
            "step_history_count": len(step_history),
            "scope_counts": scope_counts,
            "target_slug": target.slug,
            "target_name": target.name,
            "target_mode": mode or None,
            "review_required": target.requires_review(),
        }

    def _build_tool_lookup_context(
        self,
        run: AgentRun,
        *,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> ToolLookupContext:
        allowed_mcp_server_ids, allowed_mcp_tool_names = self._resolve_managed_mcp_filters(managed_subagent)
        return ToolLookupContext(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            agent_definition_id=run.agent_definition_id,
            run_id=run.id,
            allowed_knowledge_base_ids=tuple(mounted_knowledge_base_ids or []),
            allowed_mcp_server_ids=allowed_mcp_server_ids,
            allowed_mcp_tool_names=allowed_mcp_tool_names,
        )

    def _build_tool_context(
        self,
        run: AgentRun,
        *,
        step_id: str,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> ToolContext:
        lookup_context = self._build_tool_lookup_context(
            run,
            mounted_knowledge_base_ids=mounted_knowledge_base_ids,
            managed_subagent=managed_subagent,
        )
        return ToolContext(
            run_id=run.id,
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            agent_definition_id=run.agent_definition_id,
            step_id=step_id,
            allowed_knowledge_base_ids=lookup_context.allowed_knowledge_base_ids,
            allowed_mcp_server_ids=lookup_context.allowed_mcp_server_ids,
            allowed_mcp_tool_names=lookup_context.allowed_mcp_tool_names,
        )

    async def _get_tool_kind(
        self,
        run: AgentRun,
        tool_name: str,
        *,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> str:
        spec = await self.executor.registry.get_spec(
            tool_name,
            context=self._build_tool_lookup_context(
                run,
                mounted_knowledge_base_ids=mounted_knowledge_base_ids,
                managed_subagent=managed_subagent,
            ),
        )
        if spec is None:
            return "builtin"
        return str(spec.get("kind") or "builtin")

    def _raise_if_cancelled(self, run_id: str) -> None:
        if self.state_store.is_cancelled(run_id):
            raise asyncio.CancelledError()

    async def start_run(self, run_id: str) -> AgentRun:
        run: AgentRun | None = None
        try:
            run_row = await self.run_repository.get_run(run_id)
            if run_row is None:
                raise ValueError(f"Run {run_id} not found")
            run = AgentRun.model_validate(run_row)

            definition_row = await self.agent_repository.get_definition(run.agent_definition_id, run.tenant_id)
            if definition_row is None:
                raise ValueError(f"Agent definition {run.agent_definition_id} not found")
            definition = AgentDefinition.model_validate(definition_row)

            await self.run_repository.update_run_status(run.id, "running")
            await self.tracer.emit_event(run.id, "run.started", status="running")

            result = await self._execute_run(definition, run)
            updated = await self.run_repository.update_run_status(
                run.id,
                result["status"],
                plan=result.get("plan"),
                context=result.get("context"),
                final_output=result.get("final_output"),
                final_output_text=result.get("final_output_text"),
                final_output_json=result.get("final_output_json"),
                error_message=result.get("error_message"),
            )
            if result.get("artifacts") is not None:
                await self.run_repository.replace_artifacts(run.id, result.get("artifacts") or [])
            if result["status"] == "completed":
                await self.tracer.emit_event(
                    run.id,
                    "run.completed",
                    status=result["status"],
                    final_output=result.get("final_output"),
                    final_output_text=result.get("final_output_text"),
                    final_output_json=result.get("final_output_json"),
                    artifacts=result.get("artifacts") or [],
                )
            elif result["status"] == "waiting_user":
                await self.tracer.emit_event(
                    run.id,
                    "run.waiting_user",
                    status=result["status"],
                    question=result.get("final_output"),
                    final_output_text=result.get("final_output_text"),
                    artifacts=result.get("artifacts") or [],
                )
            return AgentRun.model_validate(updated)
        except asyncio.CancelledError:
            latest, terminal_surface = await self._load_terminal_run_surface(run_id)
            if latest is not None and latest["status"] == "cancelled":
                updated = latest
            else:
                updated = await self.run_repository.update_run_status(
                    run_id,
                    "cancelled",
                    plan=latest.get("plan") if latest else None,
                    context=latest.get("context") if latest else None,
                    final_output=terminal_surface.get("final_output"),
                    final_output_text=terminal_surface.get("final_output_text"),
                    final_output_json=terminal_surface.get("final_output_json"),
                    error_message="Run cancelled",
                )
                if terminal_surface.get("artifacts") is not None:
                    await self.run_repository.replace_artifacts(run_id, terminal_surface.get("artifacts") or [])
                await self.tracer.emit_event(
                    run_id,
                    "run.cancelled",
                    status="cancelled",
                    final_output=terminal_surface.get("final_output"),
                    final_output_text=terminal_surface.get("final_output_text"),
                    final_output_json=terminal_surface.get("final_output_json"),
                    artifacts=terminal_surface.get("artifacts") or [],
                )
            return AgentRun.model_validate(updated)
        except Exception as exc:
            logger.exception("Agent run failed")
            latest, terminal_surface = await self._load_terminal_run_surface(run_id)
            updated = await self.run_repository.update_run_status(
                run_id,
                "failed",
                plan=latest.get("plan") if latest else None,
                context=latest.get("context") if latest else None,
                final_output=terminal_surface.get("final_output"),
                final_output_text=terminal_surface.get("final_output_text"),
                final_output_json=terminal_surface.get("final_output_json"),
                error_message=str(exc),
            )
            if terminal_surface.get("artifacts") is not None:
                await self.run_repository.replace_artifacts(run_id, terminal_surface.get("artifacts") or [])
            await self.tracer.emit_event(
                run_id,
                "run.failed",
                status="failed",
                error=str(exc),
                final_output=terminal_surface.get("final_output"),
                final_output_text=terminal_surface.get("final_output_text"),
                final_output_json=terminal_surface.get("final_output_json"),
                artifacts=terminal_surface.get("artifacts") or [],
            )
            return AgentRun.model_validate(updated)
        finally:
            self.state_store.clear_task(run_id)
            await self.state_store.close(run_id)

    async def _execute_tool_action(
        self,
        *,
        definition: AgentDefinition,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        planner_result: PlannerResult,
        runtime_policy: RuntimePolicy,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> Dict[str, Any]:
        action = planner_result.action
        step = await self.tracer.create_step(
            run.id,
            kind=action.type,
            title=action.title,
            status="running",
            input_payload={
                "input": run.input,
                "planner": planner_result.model_dump(mode="json"),
            },
            metadata={
                "iteration": planner_result.iteration,
                "reasoning": planner_result.reasoning,
            },
        )
        await self._emit_step_event(run.id, "step.started", step)

        self._raise_if_cancelled(run.id)

        tool_name = action.tool_name or ""
        tool_arguments = action.tool_arguments
        tool_kind = await self._get_tool_kind(
            run,
            tool_name,
            mounted_knowledge_base_ids=mounted_knowledge_base_ids,
            managed_subagent=managed_subagent,
        )
        tool_call = await self.tool_call_repository.create_tool_call(
            run_id=run.id,
            step_id=step["id"],
            tool_name=tool_name,
            tool_kind=tool_kind,
            arguments=tool_arguments,
        )
        await self.tracer.emit_event(
            run.id,
            "tool.started",
            step_id=step["id"],
            tool_call_id=tool_call["id"],
            tool_name=tool_name,
            tool_kind=tool_kind,
            arguments=tool_arguments,
        )

        try:
            result = await self.executor.execute_tool(
                planner_result,
                tool_context=self._build_tool_context(
                    run,
                    step_id=step["id"],
                    mounted_knowledge_base_ids=mounted_knowledge_base_ids,
                    managed_subagent=managed_subagent,
                ),
                policy=runtime_policy,
            )
        except asyncio.CancelledError:
            await self.tool_call_repository.update_tool_call(
                tool_call["id"],
                status="cancelled",
                error_message="Run cancelled",
            )
            await self.tracer.emit_event(
                run.id,
                "tool.cancelled",
                step_id=step["id"],
                tool_call_id=tool_call["id"],
                tool_name=tool_name,
                tool_kind=tool_kind,
                error="Run cancelled",
            )
            await self.run_repository.update_step(
                step["id"],
                status="cancelled",
                error_message="Run cancelled",
            )
            await self._emit_step_event(
                run.id,
                "step.cancelled",
                step,
                error="Run cancelled",
            )
            raise
        except Exception as exc:
            error_message = str(exc)
            await self.tool_call_repository.update_tool_call(
                tool_call["id"],
                status="failed",
                error_message=error_message,
            )
            await self.tracer.emit_event(
                run.id,
                "tool.failed",
                step_id=step["id"],
                tool_call_id=tool_call["id"],
                tool_name=tool_name,
                tool_kind=tool_kind,
                error=error_message,
            )
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return self._build_observation(
                step=step,
                planner_result=planner_result,
                status="failed",
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                error=error_message,
            )

        await self.tool_call_repository.update_tool_call(
            tool_call["id"],
            status="completed",
            result=result,
        )
        await self.tracer.emit_event(
            run.id,
            "tool.completed",
            step_id=step["id"],
            tool_call_id=tool_call["id"],
            tool_name=tool_name,
            tool_kind=tool_kind,
            result=result,
        )
        promoted_artifacts = build_artifacts_from_tool_result(
            result,
            tool_name=tool_name,
            tool_kind=tool_kind,
            step_id=step["id"],
            tool_call_id=tool_call["id"],
            include_answer=False,
        )
        if promoted_artifacts:
            runtime_context["promoted_artifacts"] = merge_artifacts(
                runtime_context.get("promoted_artifacts"),
                promoted_artifacts,
            )
        step_output = {"tool_result": result}
        if promoted_artifacts:
            step_output["artifacts"] = promoted_artifacts
        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload=step_output,
        )
        await self._emit_step_event(
            run.id,
            "step.completed",
            step,
            output=step_output,
        )
        runtime_context["tool_failures"] = 0
        return self._build_observation(
            step=step,
            planner_result=planner_result,
            status="completed",
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            result=result,
        )

    async def _execute_delegate_action(
        self,
        *,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        planner_result: PlannerResult,
        available_subagents: list[SubagentTarget],
        available_tools: list[dict[str, Any]],
    ) -> Dict[str, Any]:
        if self.subagent_handoff is None:
            raise ValueError("delegate requested but subagent handoff is not configured")

        action = planner_result.action
        target = self.subagent_router.select_target(available_subagents, action.delegate_target)
        gate = self._evaluate_delegation_gate(
            run=run,
            runtime_context=runtime_context,
            planner_result=planner_result,
            target=target,
            available_tools=available_tools,
        )
        runtime_context["last_delegate_gate"] = gate
        step = await self.tracer.create_step(
            run.id,
            kind="delegate",
            title=action.title,
            status="running",
            input_payload={
                "input": run.input,
                "planner": planner_result.model_dump(mode="json"),
                "delegate_target": target.model_dump(mode="json"),
            },
            metadata={
                "iteration": planner_result.iteration,
                "reasoning": planner_result.reasoning,
                "delegate_target": target.slug,
                "delegation_gate": gate,
            },
        )
        await self._emit_step_event(
            run.id,
            "step.started",
            step,
            delegate_target=target.slug,
            delegation_gate=gate,
        )
        self._raise_if_cancelled(run.id)

        if not gate["allowed"]:
            error_message = f"Delegation gate rejected: {gate['reason']}"
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
                metadata={
                    "delegate_target": target.slug,
                    "delegation_gate": gate,
                },
            )
            await self.tracer.emit_event(
                run.id,
                "subagent.rejected",
                step_id=step["id"],
                subagent_target=target.model_dump(mode="json"),
                delegation_gate=gate,
                error=error_message,
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
                delegate_target=target.slug,
                delegation_gate=gate,
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return self._build_observation(
                step=step,
                planner_result=planner_result,
                status="failed",
                error=error_message,
                delegate_target=target.slug,
            )

        await self.tracer.emit_event(
            run.id,
            "subagent.started",
            step_id=step["id"],
            subagent_target=target.model_dump(mode="json"),
            delegate_task=action.delegate_task,
            delegate_input=action.delegate_input,
            reason=action.content,
            delegation_gate=gate,
        )

        try:
            delegation = await self.subagent_handoff.delegate(
                parent_run=run,
                parent_step_id=step["id"],
                planner_action=action,
                runtime_context=runtime_context,
                target=target,
            )
        except asyncio.CancelledError:
            await self.run_repository.update_step(
                step["id"],
                status="cancelled",
                error_message="Run cancelled",
            )
            await self.tracer.emit_event(
                run.id,
                "subagent.cancelled",
                step_id=step["id"],
                subagent_target=target.model_dump(mode="json"),
                error="Run cancelled",
            )
            await self._emit_step_event(
                run.id,
                "step.cancelled",
                step,
                error="Run cancelled",
                delegate_target=target.slug,
            )
            raise
        except Exception as exc:
            error_message = str(exc)
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
            )
            await self.tracer.emit_event(
                run.id,
                "subagent.failed",
                step_id=step["id"],
                subagent_target=target.model_dump(mode="json"),
                error=error_message,
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
                delegate_target=target.slug,
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return self._build_observation(
                step=step,
                planner_result=planner_result,
                status="failed",
                error=error_message,
                delegate_target=target.slug,
            )

        handoff_envelope = delegation.metadata.get("handoff_envelope") if isinstance(delegation.metadata, dict) else None
        review_result = delegation.metadata.get("review_result") if isinstance(delegation.metadata, dict) else None
        handoff_summary = self._summarize_handoff_envelope(handoff_envelope)
        step_output = {
            "delegate_result": delegation.model_dump(mode="json"),
            "delegation_gate": gate,
            "handoff": handoff_summary,
            "review_result": review_result,
        }
        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload=step_output,
            metadata={
                "delegate_target": target.slug,
                "delegation_gate": gate,
                "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                "child_run_id": delegation.child_run_id,
            },
        )
        subagent_event_type = "subagent.completed"
        if delegation.status == "waiting_user":
            subagent_event_type = "subagent.waiting_user"
        elif delegation.status == "failed":
            subagent_event_type = "subagent.failed"
        elif delegation.status == "cancelled":
            subagent_event_type = "subagent.cancelled"
        await self.tracer.emit_event(
            run.id,
            subagent_event_type,
            step_id=step["id"],
            subagent_target=target.model_dump(mode="json"),
            child_run_id=delegation.child_run_id,
            child_status=delegation.status,
            summary=delegation.summary,
            final_output_text=delegation.final_output_text,
            final_output_json=delegation.final_output_json,
            artifacts=delegation.artifacts,
            review_result=review_result,
            invocation_id=delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
            delegation_gate=gate,
            handoff=handoff_summary,
        )
        await self._emit_step_event(
            run.id,
            "step.completed",
            step,
            output=step_output,
            delegate_target=target.slug,
            delegation_gate=gate,
        )
        runtime_context["tool_failures"] = 0
        return self._build_observation(
            step=step,
            planner_result=planner_result,
            status="completed",
            result={
                "child_run_id": delegation.child_run_id,
                "status": delegation.status,
                "summary": delegation.summary,
                "final_output_text": delegation.final_output_text,
                "review_result": review_result,
            },
            delegate_target=target.slug,
        )

    async def _execute_final_answer(
        self,
        *,
        definition: AgentDefinition,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        skill_context: SkillRuntimeContext | None,
        managed_subagent: SubagentTarget | None = None,
        planner_result: PlannerResult,
        synthesis_resolution: Dict[str, Any],
    ) -> Dict[str, Any]:
        step = await self.tracer.create_step(
            run.id,
            kind="final_answer",
            title=planner_result.action.title,
            status="running",
            input_payload={
                "input": run.input,
                "planner": planner_result.model_dump(mode="json"),
            },
            metadata={
                "iteration": planner_result.iteration,
                "reasoning": planner_result.reasoning,
            },
        )
        await self._emit_step_event(run.id, "step.started", step)
        self._raise_if_cancelled(run.id)

        output_schema = {}
        if managed_subagent is not None and managed_subagent.output_schema:
            output_schema = merge_output_schema(output_schema, managed_subagent.output_schema)
        if skill_context and skill_context.output_schema:
            output_schema = merge_output_schema(output_schema, skill_context.output_schema)
        effective_skill_context = skill_context
        if skill_context is not None and output_schema != (skill_context.output_schema or {}):
            effective_skill_context = skill_context.model_copy(update={"output_schema": output_schema})
        elif skill_context is None and output_schema:
            effective_skill_context = SkillRuntimeContext(output_schema=output_schema)

        try:
            summary, model_info = await self.summarizer.summarize(
                llm_service=self.llm_service,
                llm_resolution=synthesis_resolution,
                system_prompt=definition.system_prompt,
                run_input=run.input,
                runtime_context=runtime_context,
                skill_context=effective_skill_context,
                planner_note=planner_result.action.content,
            )
        except Exception as exc:
            error_message = str(exc)
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
            )
            raise

        final_value: Any = summary
        if output_schema:
            try:
                final_value = json.loads(summary)
            except json.JSONDecodeError:
                final_value = summary
            final_value = self.executor.shape_output(final_value, output_schema)
        structured_result = build_structured_run_result(final_value, fallback_text=summary)
        final_output = structured_result["final_output"] or self.executor.format_output(final_value, output_schema)
        run_artifacts = merge_artifacts(
            structured_result.get("artifacts") or [],
            runtime_context.get("promoted_artifacts"),
        )

        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload={
                "final_output": final_output,
                "final_output_text": structured_result.get("final_output_text"),
                "final_output_json": structured_result.get("final_output_json"),
                "artifacts": run_artifacts,
                "model": model_info,
            },
        )
        await self._emit_step_event(
            run.id,
            "step.completed",
            step,
            output={
                "final_output": final_output,
                "final_output_text": structured_result.get("final_output_text"),
                "final_output_json": structured_result.get("final_output_json"),
                "artifacts": run_artifacts,
            },
        )
        self._append_conversation_message(runtime_context, role="assistant", content=final_output)
        runtime_context["last_summary_model"] = model_info
        runtime_context["last_result_contract"] = {
            "final_output_text": structured_result.get("final_output_text"),
            "final_output_json": structured_result.get("final_output_json"),
            "artifact_count": len(run_artifacts),
        }
        return {
            "status": "completed",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": final_output,
            "final_output_text": structured_result.get("final_output_text"),
            "final_output_json": structured_result.get("final_output_json"),
            "artifacts": run_artifacts,
            "context": runtime_context,
        }

    async def _execute_ask_user(
        self,
        *,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        planner_result: PlannerResult,
    ) -> Dict[str, Any]:
        action = planner_result.action
        step = await self.tracer.create_step(
            run.id,
            kind="ask_user",
            title=action.title,
            status="completed",
            input_payload={
                "input": run.input,
                "planner": planner_result.model_dump(mode="json"),
            },
            metadata={"question": action.question},
        )
        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload={"question": action.question},
        )
        await self._emit_step_event(
            run.id,
            "step.completed",
            step,
            question=action.question,
            output={"question": action.question},
        )
        runtime_context["pending_question"] = action.question
        self._append_conversation_message(runtime_context, role="assistant", content=action.question or "")
        promoted_artifacts = merge_artifacts(runtime_context.get("promoted_artifacts"))
        return {
            "status": "waiting_user",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": action.question,
            "final_output_text": action.question,
            "final_output_json": None,
            "artifacts": promoted_artifacts,
            "context": runtime_context,
        }

    async def _execute_run(self, definition: AgentDefinition, run: AgentRun) -> Dict[str, Any]:
        managed_subagent = self._resolve_managed_subagent(run)
        definition = self._apply_managed_subagent_definition(definition, managed_subagent)
        raw_skill_context = await self._resolve_skill_context(run, managed_subagent)
        available_subagents = await self._resolve_subagent_targets(definition, managed_subagent)

        mounted_knowledge_base_ids = await self._resolve_accessible_mounted_knowledge_base_ids(run, managed_subagent)
        available_tools = await self.executor.registry.list_specs(
            context=self._build_tool_lookup_context(
                run,
                mounted_knowledge_base_ids=mounted_knowledge_base_ids,
                managed_subagent=managed_subagent,
            )
        )
        if managed_subagent is not None and managed_subagent.tool_allowlist:
            allowed_tool_names = {tool_name for tool_name in managed_subagent.tool_allowlist if str(tool_name).strip()}
            available_tools = [tool for tool in available_tools if tool["name"] in allowed_tool_names]
        if not mounted_knowledge_base_ids:
            available_tools = [tool for tool in available_tools if tool.get("kind") != "knowledge"]
        runtime_policy = (
            RuntimePolicy([tool["name"] for tool in available_tools])
            if managed_subagent is not None
            else RuntimePolicy()
        )
        runtime_context = self._prepare_runtime_context(run)
        runtime_context["mounted_knowledge_base_ids"] = mounted_knowledge_base_ids
        runtime_context["available_subagents"] = [target.model_dump(mode="json") for target in available_subagents]
        if managed_subagent is not None:
            runtime_context["managed_subagent"] = managed_subagent.model_dump(mode="json")

        requested_model = self._extract_requested_model(definition, run.input)
        knowledge_base_id = self._extract_knowledge_base_id(run.input)
        planning_resolution = await self.llm_service.resolve_candidates(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene="agent_planning",
            requested_model=requested_model,
        )
        synthesis_resolution = await self.llm_service.resolve_candidates(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene="agent_synthesis",
            requested_model=requested_model,
        )
        runtime_context["planning_model"] = {
            "requested_model": planning_resolution.get("requested_model"),
            "candidate_count": len(planning_resolution.get("candidates", [])),
        }
        runtime_context["synthesis_model"] = {
            "requested_model": synthesis_resolution.get("requested_model"),
            "candidate_count": len(synthesis_resolution.get("candidates", [])),
        }
        await self._preprocess_intent(
            definition=definition,
            run=run,
            runtime_context=runtime_context,
            available_tools=available_tools,
            llm_resolution=planning_resolution,
        )
        inferred_intent = runtime_context.get("intent_state", {}).get("inferred_intent")
        planning_skill_context = self._select_skill_context_for_phase(
            raw_skill_context,
            inferred_intent=inferred_intent,
            phase="planning",
        )
        execution_skill_context = self._select_skill_context_for_phase(
            raw_skill_context,
            inferred_intent=inferred_intent,
            phase="execution",
        )
        synthesis_skill_context = self._select_skill_context_for_phase(
            raw_skill_context,
            inferred_intent=inferred_intent,
            phase="synthesis",
        )
        output_skill_context = self._select_skill_context_for_phase(
            raw_skill_context,
            inferred_intent=inferred_intent,
            phase="output",
        )
        effective_output_schema = merge_output_schema(
            managed_subagent.output_schema if managed_subagent is not None else {},
            output_skill_context.output_schema if output_skill_context else {},
        )
        planning_definition = self._apply_skill_prompt(definition, planning_skill_context)
        synthesis_definition = self._apply_skill_prompt(definition, synthesis_skill_context)
        if execution_skill_context is not None and execution_skill_context.skills:
            available_tools, runtime_policy, effective_allowlist = apply_skill_tool_policy(
                available_tools,
                execution_skill_context,
            )
            await self.tracer.emit_event(
                run.id,
                "skills.applied",
                planning_skill_slugs=[skill.slug for skill in planning_skill_context.skills] if planning_skill_context else [],
                execution_skill_slugs=[skill.slug for skill in execution_skill_context.skills],
                synthesis_skill_slugs=[skill.slug for skill in synthesis_skill_context.skills] if synthesis_skill_context else [],
                output_skill_slugs=[skill.slug for skill in output_skill_context.skills] if output_skill_context else [],
                tool_allowlist=execution_skill_context.tool_allowlist,
                effective_tool_allowlist=effective_allowlist,
                output_schema=effective_output_schema,
                all_skill_slugs=(raw_skill_context.metadata.get("skill_slugs") if raw_skill_context else None),
                filtered_for_intent=(execution_skill_context.metadata.get("filtered_for_intent") if execution_skill_context else inferred_intent),
            )
        elif raw_skill_context is not None and raw_skill_context.skills:
            await self.tracer.emit_event(
                run.id,
                "skills.applied",
                planning_skill_slugs=[skill.slug for skill in planning_skill_context.skills] if planning_skill_context else [],
                execution_skill_slugs=[],
                synthesis_skill_slugs=[skill.slug for skill in synthesis_skill_context.skills] if synthesis_skill_context else [],
                output_skill_slugs=[skill.slug for skill in output_skill_context.skills] if output_skill_context else [],
                tool_allowlist=[],
                effective_tool_allowlist=None,
                output_schema=effective_output_schema,
                all_skill_slugs=raw_skill_context.metadata.get("skill_slugs"),
                filtered_for_intent=inferred_intent,
            )
        await self._persist_run_state(run.id, status="running", runtime_context=runtime_context)

        max_iterations = self._resolve_max_iterations(definition)
        last_plan: Dict[str, Any] | None = None
        for iteration in range(1, max_iterations + 1):
            self._raise_if_cancelled(run.id)
            runtime_context["execution_count"] = iteration

            planner_result = await self._plan_next_action(
                definition=planning_definition,
                run=run,
                runtime_context=runtime_context,
                available_tools=available_tools,
                available_subagents=available_subagents,
                llm_resolution=planning_resolution,
                iteration=iteration,
            )
            last_plan = planner_result.model_dump(mode="json")
            runtime_context["last_plan"] = last_plan
            await self._persist_run_state(
                run.id,
                status="running",
                runtime_context=runtime_context,
                plan=last_plan,
            )
            await self.tracer.emit_event(
                run.id,
                "plan.created",
                iteration=iteration,
                plan=last_plan,
            )

            action = planner_result.action
            if action.type == "ask_user":
                return await self._execute_ask_user(
                    run=run,
                    runtime_context=runtime_context,
                    planner_result=planner_result,
                )

            if action.type == "final_answer":
                return await self._execute_final_answer(
                    definition=synthesis_definition,
                    run=run,
                    runtime_context=runtime_context,
                    skill_context=output_skill_context,
                    managed_subagent=managed_subagent,
                    planner_result=planner_result,
                    synthesis_resolution=synthesis_resolution,
                )

            if action.type == "delegate":
                observation = await self._execute_delegate_action(
                    run=run,
                    runtime_context=runtime_context,
                    planner_result=planner_result,
                    available_subagents=available_subagents,
                    available_tools=available_tools,
                )
                runtime_context.setdefault("step_history", []).append(observation)
                await self._persist_run_state(
                    run.id,
                    status="running",
                    runtime_context=runtime_context,
                    plan=last_plan,
                )
                continue

            observation = await self._execute_tool_action(
                definition=definition,
                run=run,
                runtime_context=runtime_context,
                planner_result=planner_result,
                runtime_policy=runtime_policy,
                mounted_knowledge_base_ids=mounted_knowledge_base_ids,
                managed_subagent=managed_subagent,
            )
            runtime_context.setdefault("step_history", []).append(observation)
            await self._persist_run_state(
                run.id,
                status="running",
                runtime_context=runtime_context,
                plan=last_plan,
            )

        raise RuntimeError(f"Agent exceeded maximum iterations ({max_iterations}) before reaching a final answer")
