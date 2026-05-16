from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from ai_runtime.core.agent_runtime.context_compressor import (
    COMPRESSION_STATE_KEY,
    ContextCompressor,
)
from ai_runtime.core.agent_runtime.executor import AgentExecutor
from ai_runtime.core.agent_runtime.intent import IntentPreprocessor
from ai_runtime.core.agent_runtime.models import AgentDefinition, AgentRun, PlannerAction, PlannerResult
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig, ToolResultCache
from ai_runtime.core.agent_runtime.planner import AgentPlanner
from ai_runtime.core.agent_runtime.policy import RuntimePolicy
from ai_runtime.core.agent_runtime.result_contract import (
    build_artifacts_from_tool_result,
    build_structured_run_result,
    hydrate_legacy_result,
    merge_artifacts,
)
from ai_runtime.core.agent_runtime.schema_utils import merge_output_schema
from ai_runtime.core.agent_runtime.skills.models import SkillRuntimeContext
from ai_runtime.core.agent_runtime.subagents.governance import (
    annotate_governance_policy,
    append_delegation_outcome,
    build_governance_blocker,
    build_governance_gate_recovery,
    build_subagent_failure_strategy,
    build_tool_budget_gate,
    build_review_gate_blockers,
    build_waiting_user_path,
    evaluate_governance_gate,
    merge_governance_usage_snapshots,
    normalize_governance_blockers,
    record_delegation_outcome,
    should_bubble_waiting_user_to_parent,
)
from ai_runtime.core.agent_runtime.subagents.handoff import SubagentHandoff
from ai_runtime.core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget
from ai_runtime.core.agent_runtime.subagents.registry import SubagentRegistry
from ai_runtime.core.agent_runtime.subagents.router import SubagentRouter
from ai_runtime.core.agent_runtime.summarizer import AgentSummarizer
from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tracing import AgentTracer
from ai_runtime.core.agent_runtime.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


def apply_skill_tool_policy(
    available_tools: list[dict[str, Any]],
    skill_context: SkillRuntimeContext | None,
) -> tuple[list[dict[str, Any]], RuntimePolicy, list[str] | None]:
    if skill_context is None or not skill_context.skills:
        return available_tools, RuntimePolicy(), None

    effective_allowlist = [tool_name for tool_name in skill_context.tool_allowlist if str(tool_name).strip()]
    managed_tool_kinds = {
        str(kind).strip()
        for contract in skill_context.metadata.get("skill_contracts", [])
        if isinstance(contract, dict)
        for kind in contract.get("managed_tool_kinds", [])
        if str(kind).strip()
    }
    if not effective_allowlist and not managed_tool_kinds:
        return available_tools, RuntimePolicy(), None

    filtered_tools = [
        tool for tool in available_tools
        if tool["name"] in effective_allowlist
        or str(tool.get("kind") or "").strip() in managed_tool_kinds
        or str((tool.get("metadata") or {}).get("legacy_provider") or "").strip() in managed_tool_kinds
    ]
    managed_tool_names = [tool["name"] for tool in filtered_tools if tool["name"] not in effective_allowlist]
    return filtered_tools, RuntimePolicy([*effective_allowlist, *managed_tool_names]), [*effective_allowlist, *managed_tool_names]


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
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.summarizer = summarizer
        self.context_compressor = ContextCompressor()
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
        self.workspace_manager = workspace_manager
        self.optimization_config = AgentRuntimeOptimizationConfig.from_env()
        self.tool_result_cache = ToolResultCache(self.optimization_config.tool_cache_max_entries)

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

    def _extract_phase_requested_model(
        self,
        definition: AgentDefinition,
        run_input: Dict[str, Any],
        *,
        phase: str,
    ) -> Optional[str]:
        run_models = run_input.get("models") if isinstance(run_input.get("models"), dict) else {}
        definition_models = definition.config.get("models") if isinstance(definition.config.get("models"), dict) else {}
        candidates = [
            run_input.get(f"{phase}_model"),
            run_models.get(phase),
            definition.config.get(f"{phase}_model"),
            definition_models.get(phase),
            run_input.get("model"),
            definition.model,
        ]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
        return None

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
        value = definition.config.get("max_iterations", self.optimization_config.default_max_iterations)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = self.optimization_config.default_max_iterations
        return max(2, min(parsed, 20))

    async def _flush_tracer(self) -> None:
        flush = getattr(self.tracer, "flush", None)
        if callable(flush):
            await flush()

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
        if not isinstance(runtime_context.get("subagent_governance_ledger"), dict):
            runtime_context["subagent_governance_ledger"] = {
                "protocol_version": "managed-subagent.governance.v1",
                "targets": {},
            }

        current_message = str(run.input.get("message") or run.input.get("prompt") or "").strip()
        last_user_message = str(runtime_context.get("last_user_message") or "").strip()
        if current_message and current_message != last_user_message:
            self._append_conversation_message(runtime_context, role="user", content=current_message)
            runtime_context["last_user_message"] = current_message
            runtime_context.pop("pending_question", None)
            runtime_context.pop("pending_subagent_clarification", None)
            runtime_context.pop("ask_user_guard", None)

        runtime_context.setdefault("execution_count", 0)
        runtime_context.setdefault("tool_failures", 0)
        return runtime_context

    def _refresh_prompt_context(
        self,
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
        phase: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self.context_compressor.compress(
            run_input=run_input,
            runtime_context=runtime_context,
            phase=phase,
            force=force,
        )

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
        self._refresh_prompt_context(
            run_input=runtime_context.get("normalized_task_input") or run.input,
            runtime_context=runtime_context,
            phase="intent",
        )
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
        self._refresh_prompt_context(
            run_input=runtime_context.get("normalized_task_input") or run.input,
            runtime_context=runtime_context,
            phase=f"planning.iteration_{iteration}",
        )
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

    def _tool_recovery_actions(self, *, metadata: dict[str, Any], denied: bool = False) -> list[str]:
        configured_actions = metadata.get("recovery_actions")
        actions = [str(item).strip() for item in configured_actions if str(item).strip()] if isinstance(configured_actions, list) else []
        requires_workspace = bool(metadata.get("requires_workspace"))
        requires_sandbox = bool(metadata.get("requires_sandbox"))
        if requires_workspace:
            actions.append("Bind a run workspace or upload a project bundle before using this tool.")
        if requires_sandbox:
            actions.append("Configure and enable a sandbox runner before using execution tools.")
        if denied:
            actions.append("Enable the tool in the agent skill/runtime policy or choose a lower-risk execution mode.")
        return list(dict.fromkeys(actions))

    def _build_tool_recovery(
        self,
        *,
        primary_code: str,
        summary: str,
        actions: list[str] | None = None,
    ) -> dict[str, Any]:
        deduped_actions = list(dict.fromkeys(str(item).strip() for item in (actions or []) if str(item).strip()))
        return {
            "recoverable": bool(deduped_actions),
            "primary_code": str(primary_code or "").strip() or "unknown",
            "summary": str(summary or "").strip(),
            "actions": deduped_actions,
        }

    def _build_tool_failure_result(
        self,
        *,
        tool_name: str,
        tool_kind: str,
        failure_category: str,
        error_message: str,
        recovery: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "failed",
            "tool_name": tool_name,
            "tool_kind": tool_kind,
            "failure_category": str(failure_category or "unknown").strip() or "unknown",
            "error": str(error_message or "").strip(),
        }
        if recovery:
            payload["recovery"] = recovery
        if details:
            payload["details"] = details
        return payload

    async def _evaluate_tool_policy(
        self,
        *,
        run: AgentRun,
        tool_name: str,
        runtime_policy: RuntimePolicy,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> dict[str, Any]:
        lookup_context = self._build_tool_lookup_context(
            run,
            mounted_knowledge_base_ids=mounted_knowledge_base_ids,
            managed_subagent=managed_subagent,
        )
        spec = await self.executor.registry.get_spec(tool_name, context=lookup_context)
        metadata = dict((spec or {}).get("metadata") or {})
        reasons: list[str] = []
        unavailable_reasons: list[str] = []
        allowed_by_policy = runtime_policy.is_tool_allowed(tool_name)
        if not allowed_by_policy:
            reasons.append("tool is not allowed by the active runtime policy")
        if spec is None:
            unavailable_reasons.append("tool is not registered or is hidden by provider configuration")
        if metadata.get("requires_workspace") and not lookup_context.workspace_root:
            unavailable_reasons.append("workspace is not bound to this run")
        if metadata.get("status") == "unavailable" and metadata.get("unavailable_reason"):
            unavailable_reasons.append(str(metadata.get("unavailable_reason")))

        allowed = allowed_by_policy and spec is not None and not unavailable_reasons
        return {
            "allowed": allowed,
            "decision": "approved" if allowed else "denied",
            "tool_name": tool_name,
            "tool_kind": str((spec or {}).get("kind") or "builtin"),
            "metadata": metadata,
            "policy": {
                "runtime_policy_allows": allowed_by_policy,
                "requires_workspace": bool(metadata.get("requires_workspace")),
                "requires_sandbox": bool(metadata.get("requires_sandbox")),
                "capability": metadata.get("capability"),
                "access_level": metadata.get("access_level"),
                "side_effect": metadata.get("side_effect"),
                "risk_level": metadata.get("risk_level"),
            },
            "reasons": reasons,
            "unavailable_reasons": unavailable_reasons,
            "recovery_actions": self._tool_recovery_actions(metadata=metadata, denied=not allowed_by_policy),
        }

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
            "progress": envelope.get("progress") or {},
            "clarification": envelope.get("clarification"),
            "context_slice": {
                "delegation_depth": context_slice.get("delegation_depth"),
                "recent_observation_count": len(context_slice.get("recent_observations") or []),
                "conversation_tail_count": len(context_slice.get("conversation_tail") or []),
                "mounted_knowledge_base_ids": context_slice.get("mounted_knowledge_base_ids") or [],
            },
            "policy_snapshot": envelope.get("policy_snapshot") or {},
            "governance_policy": (
                envelope.get("policy_snapshot", {}).get("governance_policy")
                if isinstance(envelope.get("policy_snapshot"), dict)
                else {}
            ),
        }

    def _build_waiting_user_context_patch(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        patch: dict[str, Any] = {}
        for key in ("pending_question", "pending_subagent_clarification", "subagent_governance_ledger"):
            if key in context:
                patch[key] = context[key]
        return patch

    def _build_parent_waiting_user_result(
        self,
        *,
        planner_result: PlannerResult,
        runtime_context: Dict[str, Any],
        delegation: Any,
        handoff_summary: dict[str, Any],
        review_result: dict[str, Any] | None,
        governance_policy: dict[str, Any],
    ) -> dict[str, Any]:
        question = str(delegation.final_output or delegation.final_output_text or "").strip() or None
        clarification = delegation.clarification or None
        progress = delegation.progress or {}
        waiting_user_policy = governance_policy.get("waiting_user") if isinstance(governance_policy, dict) else {}
        promoted_artifacts = merge_artifacts(
            runtime_context.get("promoted_artifacts"),
            delegation.artifacts,
        )
        runtime_context["promoted_artifacts"] = promoted_artifacts
        runtime_context["pending_question"] = question
        runtime_context["pending_subagent_clarification"] = {
            "child_run_id": delegation.child_run_id,
            "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
            "target": delegation.target.model_dump(mode="json"),
            "question": question,
            "progress": progress,
            "clarification": clarification,
            "review_result": review_result,
            "governance_policy": governance_policy,
            "waiting_user_policy": waiting_user_policy if isinstance(waiting_user_policy, dict) else {},
            "waiting_user_path": (
                governance_policy.get("latest_waiting_user", {}).get("waiting_user_path")
                if isinstance(governance_policy.get("latest_waiting_user"), dict)
                else []
            ),
            "handoff": handoff_summary,
            "artifacts": delegation.artifacts,
            "promoted_artifacts": promoted_artifacts,
        }
        self._append_conversation_message(runtime_context, role="assistant", content=question or delegation.summary or "")
        return {
            "status": "waiting_user",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": question,
            "final_output_text": question,
            "final_output_json": {
                "source": "subagent_waiting_user",
                "child_run_id": delegation.child_run_id,
                "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                "target": {
                    "slug": delegation.target.slug,
                    "name": delegation.target.name,
                },
                "question": question,
                "progress": progress,
                "clarification": clarification,
                "review_result": review_result,
                "governance_policy": governance_policy,
                "waiting_user_policy": waiting_user_policy if isinstance(waiting_user_policy, dict) else {},
                "waiting_user_path": (
                    governance_policy.get("latest_waiting_user", {}).get("waiting_user_path")
                    if isinstance(governance_policy.get("latest_waiting_user"), dict)
                    else []
                ),
                "handoff": handoff_summary,
                "artifacts": delegation.artifacts,
                "promoted_artifacts": promoted_artifacts,
            },
            "artifacts": promoted_artifacts,
            "context": runtime_context,
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
        governance = evaluate_governance_gate(
            run=run,
            runtime_context=runtime_context,
            target=target,
            delegate_input=delegate_input,
        )

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
        blockers: list[dict[str, Any]] = []
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

        if available_tools and not step_history and not target.requires_review() and not any(scope_counts.values()):
            blockers.append(
                build_governance_blocker(
                    "single_agent_first",
                    "single-agent-first gate rejected delegation before any parent execution evidence was gathered",
                    details={
                        "available_tool_count": len(available_tools),
                        "step_history_count": len(step_history),
                    },
                )
            )
        if not signals and available_tools:
            blockers.append(
                build_governance_blocker(
                    "delegation_not_justified",
                    "no concrete isolation, complexity, parallelism, or quality signal justifies delegation",
                    details={
                        "available_tool_count": len(available_tools),
                        "step_history_count": len(step_history),
                    },
                )
            )

        gate_blockers = normalize_governance_blockers(governance.get("blockers") or [])
        existing_blocker_signatures = {(blocker.get("code"), blocker.get("message")) for blocker in blockers}
        for blocker in gate_blockers:
            signature = (blocker.get("code"), blocker.get("message"))
            if signature not in existing_blocker_signatures:
                blockers.append(blocker)
                existing_blocker_signatures.add(signature)
        for warning in governance.get("warnings") or []:
            if warning not in signals:
                signals.append(warning)

        return {
            "allowed": not blockers,
            "decision": "approved" if not blockers else "rejected",
            "reason": "; ".join(blocker["message"] for blocker in blockers) if blockers else "; ".join(signals) or "delegation accepted",
            "signals": signals,
            "blockers": blockers,
            "recovery": build_governance_gate_recovery(blockers),
            "current_depth": current_depth,
            "max_depth": max_depth,
            "available_tool_count": len(available_tools),
            "step_history_count": len(step_history),
            "scope_counts": scope_counts,
            "target_slug": target.slug,
            "target_name": target.name,
            "target_mode": mode or None,
            "review_required": target.requires_review(),
            "governance": governance,
        }

    def _build_tool_lookup_context(
        self,
        run: AgentRun,
        *,
        mounted_knowledge_base_ids: list[str] | None = None,
        managed_subagent: SubagentTarget | None = None,
    ) -> ToolLookupContext:
        allowed_mcp_server_ids, allowed_mcp_tool_names = self._resolve_managed_mcp_filters(managed_subagent)
        run_context = run.context if isinstance(run.context, dict) else {}
        workspace_payload = run_context.get("workspace") if isinstance(run_context.get("workspace"), dict) else {}
        workspace_root = str(run_context.get("workspace_root") or workspace_payload.get("root") or "").strip() or None
        return ToolLookupContext(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            agent_definition_id=run.agent_definition_id,
            run_id=run.id,
            session_id=run.session_id,
            allowed_knowledge_base_ids=tuple(mounted_knowledge_base_ids or []),
            allowed_mcp_server_ids=allowed_mcp_server_ids,
            allowed_mcp_tool_names=allowed_mcp_tool_names,
            workspace_root=workspace_root,
        )

    def _pending_subagent_invocations(self, runtime_context: Dict[str, Any]) -> list[dict[str, Any]]:
        pending = runtime_context.get("pending_subagent_invocations")
        if not isinstance(pending, list):
            pending = []
            runtime_context["pending_subagent_invocations"] = pending
        return pending

    def _resolved_subagent_invocations(self, runtime_context: Dict[str, Any]) -> list[dict[str, Any]]:
        resolved = runtime_context.get("resolved_subagent_invocations")
        if not isinstance(resolved, list):
            resolved = []
            runtime_context["resolved_subagent_invocations"] = resolved
        return resolved

    def _promote_subagent_artifacts(
        self,
        runtime_context: Dict[str, Any],
        artifacts: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        promoted = merge_artifacts(runtime_context.get("promoted_artifacts"), artifacts)
        if promoted:
            runtime_context["promoted_artifacts"] = promoted
        return promoted

    def _record_resolved_subagent_invocation(
        self,
        runtime_context: Dict[str, Any],
        *,
        step: Dict[str, Any],
        target: SubagentTarget,
        delegation: SubagentDelegationResult,
        review_result: dict[str, Any] | None,
        governance_policy: dict[str, Any],
        failure_strategy: dict[str, Any],
        promoted_artifacts: list[dict[str, Any]],
        step_status: str,
        pending_completion: bool,
        review_gate_blocked: bool,
    ) -> None:
        resolved = self._resolved_subagent_invocations(runtime_context)
        resolved.append(
            {
                "child_run_id": delegation.child_run_id,
                "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                "target": target.model_dump(mode="json"),
                "parent_step_id": step["id"],
                "parent_step_index": step.get("step_index"),
                "status": delegation.status,
                "step_status": step_status,
                "summary": delegation.summary,
                "final_output": delegation.final_output,
                "final_output_text": delegation.final_output_text,
                "final_output_json": delegation.final_output_json,
                "artifacts": delegation.artifacts,
                "promoted_artifacts": promoted_artifacts,
                "progress": delegation.progress,
                "clarification": delegation.clarification or None,
                "review_result": review_result,
                "governance_policy": governance_policy,
                "failure_strategy": failure_strategy,
                "pending_completion": pending_completion,
                "review_gate_blocked": review_gate_blocked,
            }
        )
        runtime_context["resolved_subagent_invocations"] = resolved[-20:]

    def _register_pending_subagent_invocation(
        self,
        runtime_context: Dict[str, Any],
        *,
        target: SubagentTarget,
        step: Dict[str, Any],
        planner_result: PlannerResult,
        gate: dict[str, Any],
        delegation: SubagentDelegationResult,
    ) -> None:
        metadata = delegation.metadata if isinstance(delegation.metadata, dict) else {}
        pending = self._pending_subagent_invocations(runtime_context)
        pending.append(
            {
                "child_run_id": delegation.child_run_id,
                "target": target.model_dump(mode="json"),
                "parent_step_id": step["id"],
                "parent_step_index": step.get("step_index"),
                "planner_result": planner_result.model_dump(mode="json"),
                "delegation_gate": gate,
                "invocation_id": metadata.get("invocation_id"),
                "handoff_envelope": metadata.get("handoff_envelope") if isinstance(metadata.get("handoff_envelope"), dict) else {},
                "child_input": delegation.input,
                "started_observation": {
                    "child_run_id": delegation.child_run_id,
                    "status": delegation.status,
                    "summary": delegation.summary,
                    "progress": delegation.progress,
                },
            }
        )

    async def _complete_delegate_action(
        self,
        *,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        planner_result: PlannerResult,
        target: SubagentTarget,
        step: Dict[str, Any],
        gate: dict[str, Any],
        delegation: SubagentDelegationResult,
        pending_completion: bool = False,
    ) -> tuple[Dict[str, Any], dict[str, Any] | None]:
        handoff_envelope = delegation.metadata.get("handoff_envelope") if isinstance(delegation.metadata, dict) else None
        review_result = delegation.metadata.get("review_result") if isinstance(delegation.metadata, dict) else None
        handoff_summary = self._summarize_handoff_envelope(handoff_envelope)
        partial_result = None
        child_question = None
        resolved_governance_policy = (
            delegation.metadata.get("governance_policy")
            if isinstance(delegation.metadata, dict)
            else None
        )
        if not isinstance(resolved_governance_policy, dict):
            resolved_governance_policy = (
                handoff_summary.get("governance_policy")
                or gate.get("governance", {}).get("policy")
                or {}
            )
        waiting_user_policy = resolved_governance_policy.get("waiting_user") if isinstance(resolved_governance_policy, dict) else {}
        if not isinstance(waiting_user_policy, dict):
            waiting_user_policy = {}
        prior_usage = gate.get("governance", {}).get("prior_usage") if isinstance(gate.get("governance"), dict) else {}
        last_invocation_usage = {}
        budget_payload = resolved_governance_policy.get("budget") if isinstance(resolved_governance_policy.get("budget"), dict) else {}
        if isinstance(budget_payload, dict):
            candidate = budget_payload.get("last_invocation_usage")
            if not isinstance(candidate, dict) or not candidate:
                candidate = budget_payload.get("usage")
            if isinstance(candidate, dict):
                last_invocation_usage = candidate
        cumulative_usage = merge_governance_usage_snapshots(
            prior_usage if isinstance(prior_usage, dict) else {},
            last_invocation_usage if isinstance(last_invocation_usage, dict) else {},
            source="step_history + last_invocation",
        )
        waiting_user_path = []
        if delegation.status == "waiting_user":
            clarification_path = (
                delegation.clarification.get("waiting_user_path")
                if isinstance(delegation.clarification, dict)
                else None
            )
            progress_path = (
                delegation.progress.get("waiting_user_path")
                if isinstance(delegation.progress, dict)
                else None
            )
            metadata_path = (
                delegation.metadata.get("waiting_user_path")
                if isinstance(delegation.metadata, dict)
                else None
            )
            child_waiting_user_path = None
            for candidate in (metadata_path, clarification_path, progress_path):
                if isinstance(candidate, list) and candidate:
                    child_waiting_user_path = candidate
                    break
            waiting_user_path = build_waiting_user_path(
                parent_run_id=run.id,
                child_run_id=delegation.child_run_id,
                child_waiting_user_path=child_waiting_user_path,
            )
        ledger_entry = record_delegation_outcome(
            runtime_context,
            target_slug=target.slug,
            status=delegation.status,
            child_run_id=delegation.child_run_id,
            invocation_id=delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
            usage=last_invocation_usage if isinstance(last_invocation_usage, dict) else {},
            waiting_user_propagation=waiting_user_policy.get("propagation"),
            waiting_user_counts_as_active_child=bool(waiting_user_policy.get("counts_as_active_child", True)),
            question=delegation.final_output or delegation.final_output_text,
            waiting_user_path=waiting_user_path,
            write_scope=delegation.input.get("write_scope") if isinstance(delegation.input, dict) else None,
            count_attempt=not pending_completion,
        )
        history = ledger_entry.get("history") or append_delegation_outcome(
            gate.get("governance", {}).get("history") if isinstance(gate.get("governance"), dict) else {},
            status=delegation.status,
            waiting_user_propagation=waiting_user_policy.get("propagation"),
            waiting_user_counts_as_active_child=bool(waiting_user_policy.get("counts_as_active_child", True)),
        )
        cumulative_usage = ledger_entry.get("usage") or cumulative_usage
        last_invocation_usage = ledger_entry.get("last_invocation_usage") or last_invocation_usage
        resolved_governance_policy = annotate_governance_policy(
            {
                **dict(resolved_governance_policy or {}),
                "latest_waiting_user": dict(ledger_entry.get("latest_waiting_user") or {}),
            },
            history=history,
            usage=cumulative_usage,
            prior_usage=prior_usage if isinstance(prior_usage, dict) else {},
            last_invocation_usage=last_invocation_usage if isinstance(last_invocation_usage, dict) else {},
        )
        review_gate_blockers = build_review_gate_blockers(review_result)
        review_gate_recovery = build_governance_gate_recovery(review_gate_blockers)
        review_gate_blocked = bool(review_gate_blockers) and delegation.status not in {
            "failed",
            "cancelled",
            "waiting_user",
        }
        if review_gate_blocked:
            existing_blockers = normalize_governance_blockers(resolved_governance_policy.get("blockers") or [])
            blocker_signatures = {(item.get("code"), item.get("message")) for item in existing_blockers}
            for blocker in review_gate_blockers:
                signature = (blocker.get("code"), blocker.get("message"))
                if signature not in blocker_signatures:
                    existing_blockers.append(blocker)
                    blocker_signatures.add(signature)
            resolved_governance_policy["blockers"] = existing_blockers
            resolved_governance_policy["recovery"] = build_governance_gate_recovery(existing_blockers)
            if isinstance(review_result, dict):
                review_result = {
                    **review_result,
                    "decision": "review_gate_blocked",
                    "approved": False,
                    "gate_blocked": True,
                    "gate_blockers": review_gate_blockers,
                    "recovery": review_gate_recovery,
                }
            runtime_context["last_review_gate_block"] = {
                "target_slug": target.slug,
                "child_run_id": delegation.child_run_id,
                "review_result": review_result,
                "blockers": review_gate_blockers,
                "recovery": review_gate_recovery,
            }
        if delegation.status == "waiting_user":
            partial_result = {
                "question": delegation.final_output or delegation.final_output_text,
                "artifacts": delegation.artifacts,
                "progress": delegation.progress,
                "clarification": delegation.clarification or None,
            }
            child_question = delegation.final_output or delegation.final_output_text
        failure_strategy = build_subagent_failure_strategy(
            status="review_blocked" if review_gate_blocked else delegation.status,
            target=target,
            blockers=(
                review_gate_blockers
                if review_gate_blocked
                else resolved_governance_policy.get("blockers") if isinstance(resolved_governance_policy, dict) else []
            ),
            error_message=delegation.metadata.get("error_message") if isinstance(delegation.metadata, dict) else None,
        )
        step_output = {
            "delegate_result": delegation.model_dump(mode="json"),
            "delegation_gate": gate,
            "handoff": handoff_summary,
            "review_result": review_result,
            "governance_policy": resolved_governance_policy,
            "failure_strategy": failure_strategy,
            "progress": delegation.progress,
            "clarification": delegation.clarification or None,
            "artifacts": delegation.artifacts,
        }
        promoted_artifacts: list[dict[str, Any]] = []
        if delegation.status in {"completed", "waiting_user"}:
            promoted_artifacts = self._promote_subagent_artifacts(runtime_context, delegation.artifacts)
            if promoted_artifacts:
                step_output["promoted_artifacts"] = promoted_artifacts
        if review_gate_blocked or delegation.status == "failed":
            step_status = "failed"
        elif delegation.status == "cancelled":
            step_status = "cancelled"
        else:
            step_status = "completed"
        step_error = (
            f"Review gate blocked: {review_gate_blockers[0]['message']}"
            if review_gate_blocked
            else delegation.metadata.get("error_message") if delegation.status in {"failed", "cancelled"} and isinstance(delegation.metadata, dict) else None
        )
        await self.run_repository.update_step(
            step["id"],
            status=step_status,
            output_payload=step_output,
            error_message=step_error,
            metadata={
                "delegate_target": target.slug,
                "delegation_gate": gate,
                "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                "child_run_id": delegation.child_run_id,
                "async_completion": pending_completion,
                "review_gate": {
                    "blocked": review_gate_blocked,
                    "blockers": review_gate_blockers,
                    "recovery": review_gate_recovery,
                },
                "failure_strategy": failure_strategy,
            },
        )
        subagent_event_type = "subagent.completed"
        if review_gate_blocked:
            subagent_event_type = "subagent.review_blocked"
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
            handoff_envelope=handoff_envelope,
            governance_policy=resolved_governance_policy,
            partial_result=partial_result,
            progress=delegation.progress,
            clarification=delegation.clarification or None,
            question=child_question,
            review_gate={
                "blocked": review_gate_blocked,
                "blockers": review_gate_blockers,
                "recovery": review_gate_recovery,
            },
            failure_strategy=failure_strategy,
        )
        if step_status in {"failed", "cancelled"}:
            await self._emit_step_event(
                run.id,
                "step.cancelled" if step_status == "cancelled" else "step.failed",
                step,
                error=step_error,
                output=step_output,
                delegate_target=target.slug,
                delegation_gate=gate,
                review_gate={
                    "blocked": True,
                    "blockers": review_gate_blockers,
                    "recovery": review_gate_recovery,
                },
                failure_strategy=failure_strategy,
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
        else:
            await self._emit_step_event(
                run.id,
                "step.completed",
                step,
                output=step_output,
                delegate_target=target.slug,
                delegation_gate=gate,
                failure_strategy=failure_strategy,
            )
            runtime_context["tool_failures"] = 0
        if review_gate_blocked or delegation.status == "failed":
            observation_status = "failed"
        elif delegation.status == "cancelled":
            observation_status = "cancelled"
        else:
            observation_status = "completed"
        observation = self._build_observation(
            step=step,
            planner_result=planner_result,
            status=observation_status,
            result={
                "child_run_id": delegation.child_run_id,
                "status": "review_blocked" if review_gate_blocked else delegation.status,
                "summary": delegation.summary,
                "final_output_text": delegation.final_output_text,
                "artifacts": delegation.artifacts,
                "promoted_artifacts": promoted_artifacts,
                "review_result": review_result,
                "governance_policy": resolved_governance_policy,
                "governance_usage": cumulative_usage,
                "waiting_user_policy": waiting_user_policy,
                "failure_strategy": failure_strategy,
                "review_gate": {
                    "blocked": review_gate_blocked,
                    "blockers": review_gate_blockers,
                    "recovery": review_gate_recovery,
                },
            },
            error=step_error,
            delegate_target=target.slug,
        )
        self._record_resolved_subagent_invocation(
            runtime_context,
            step=step,
            target=target,
            delegation=delegation,
            review_result=review_result,
            governance_policy=resolved_governance_policy,
            failure_strategy=failure_strategy,
            promoted_artifacts=promoted_artifacts,
            step_status=step_status,
            pending_completion=pending_completion,
            review_gate_blocked=review_gate_blocked,
        )
        if review_gate_blocked or delegation.status in {"failed", "cancelled"}:
            return observation, None
        if delegation.status != "waiting_user":
            return observation, None

        propagation = ""
        waiting_user_policy = resolved_governance_policy.get("waiting_user")
        if isinstance(waiting_user_policy, dict):
            propagation = str(waiting_user_policy.get("propagation") or "").strip()
        if should_bubble_waiting_user_to_parent(propagation):
            return observation, self._build_parent_waiting_user_result(
                planner_result=planner_result,
                runtime_context=runtime_context,
                delegation=delegation,
                handoff_summary=handoff_summary,
                review_result=review_result,
                governance_policy=resolved_governance_policy,
            )
        return observation, None

    async def _collect_pending_subagent_invocations(
        self,
        *,
        run: AgentRun,
        runtime_context: Dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.subagent_handoff is None:
            return None
        pending = self._pending_subagent_invocations(runtime_context)
        if not pending:
            return None

        remaining: list[dict[str, Any]] = []
        terminal_result: dict[str, Any] | None = None
        for item in pending:
            if not isinstance(item, dict):
                continue
            target_payload = item.get("target")
            if not isinstance(target_payload, dict):
                continue
            try:
                target = SubagentTarget.model_validate(target_payload)
            except Exception:
                logger.exception("Failed to hydrate pending subagent target for run %s", run.id)
                remaining.append(item)
                continue
            child_run_id = str(item.get("child_run_id") or "").strip()
            if not child_run_id:
                continue
            delegation = await self.subagent_handoff.resolve_delegation_result(
                child_run_id=child_run_id,
                target=target,
                child_input=item.get("child_input") if isinstance(item.get("child_input"), dict) else {},
                parent_step_id=str(item.get("parent_step_id") or "").strip() or None,
                invocation_id=str(item.get("invocation_id") or "").strip() or None,
                handoff_envelope=item.get("handoff_envelope") if isinstance(item.get("handoff_envelope"), dict) else {},
            )
            if delegation is None:
                remaining.append(item)
                continue

            planner_payload = item.get("planner_result") if isinstance(item.get("planner_result"), dict) else {}
            planner_result = PlannerResult.model_validate(planner_payload)
            step = {
                "id": str(item.get("parent_step_id") or ""),
                "run_id": run.id,
                "step_index": item.get("parent_step_index"),
                "kind": "delegate",
                "title": planner_result.action.title,
                "status": "running",
                "input": {},
                "metadata": {},
            }
            observation, delegated_result = await self._complete_delegate_action(
                run=run,
                runtime_context=runtime_context,
                planner_result=planner_result,
                target=target,
                step=step,
                gate=item.get("delegation_gate") if isinstance(item.get("delegation_gate"), dict) else {},
                delegation=delegation,
                pending_completion=True,
            )
            runtime_context.setdefault("step_history", []).append(observation)
            if delegated_result is not None and terminal_result is None:
                terminal_result = delegated_result

        runtime_context["pending_subagent_invocations"] = remaining
        return terminal_result

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
            session_id=run.session_id,
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            agent_definition_id=run.agent_definition_id,
            step_id=step_id,
            allowed_knowledge_base_ids=lookup_context.allowed_knowledge_base_ids,
            allowed_mcp_server_ids=lookup_context.allowed_mcp_server_ids,
            allowed_mcp_tool_names=lookup_context.allowed_mcp_tool_names,
            workspace_root=lookup_context.workspace_root,
            tool_result_cache=self.tool_result_cache if self.optimization_config.enable_tool_result_cache else None,
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
            await self._flush_tracer()
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
                waiting_context_patch = self._build_waiting_user_context_patch(result.get("context"))
                await self.tracer.emit_event(
                    run.id,
                    "run.waiting_user",
                    status=result["status"],
                    question=result.get("final_output"),
                    final_output_text=result.get("final_output_text"),
                    final_output_json=result.get("final_output_json"),
                    artifacts=result.get("artifacts") or [],
                    context_patch=waiting_context_patch,
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
                await self._flush_tracer()
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
            await self._flush_tracer()
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
        policy_decision = await self._evaluate_tool_policy(
            run=run,
            tool_name=tool_name,
            runtime_policy=runtime_policy,
            mounted_knowledge_base_ids=mounted_knowledge_base_ids,
            managed_subagent=managed_subagent,
        )
        tool_kind = policy_decision["tool_kind"]
        await self.tracer.emit_event(
            run.id,
            "policy.requested",
            step_id=step["id"],
            policy_type="tool",
            subject=tool_name,
            decision=policy_decision["decision"],
            tool_name=tool_name,
            tool_kind=tool_kind,
            policy=policy_decision["policy"],
            metadata=policy_decision["metadata"],
        )
        if policy_decision["allowed"]:
            await self.tracer.emit_event(
                run.id,
                "policy.approved",
                step_id=step["id"],
                policy_type="tool",
                subject=tool_name,
                tool_name=tool_name,
                tool_kind=tool_kind,
                policy=policy_decision["policy"],
            )
        else:
            error_message = "; ".join(
                [
                    *(policy_decision.get("reasons") or []),
                    *(policy_decision.get("unavailable_reasons") or []),
                ]
            ) or f"Tool {tool_name} is unavailable under the active policy"
            await self.tracer.emit_event(
                run.id,
                "policy.denied",
                step_id=step["id"],
                policy_type="tool",
                subject=tool_name,
                tool_name=tool_name,
                tool_kind=tool_kind,
                policy=policy_decision["policy"],
                reasons=policy_decision.get("reasons") or [],
                unavailable_reasons=policy_decision.get("unavailable_reasons") or [],
                recovery_actions=policy_decision.get("recovery_actions") or [],
                error=error_message,
            )
            denied_recovery = self._build_tool_recovery(
                primary_code="tool_policy_denied",
                summary=error_message,
                actions=policy_decision.get("recovery_actions") or [],
            )
            denied_result = {
                "policy_decision": policy_decision,
                "tool_result": self._build_tool_failure_result(
                    tool_name=tool_name,
                    tool_kind=tool_kind,
                    failure_category="policy_denied",
                    error_message=error_message,
                    recovery=denied_recovery,
                    details={
                        "reasons": policy_decision.get("reasons") or [],
                        "unavailable_reasons": policy_decision.get("unavailable_reasons") or [],
                        "policy": policy_decision.get("policy") or {},
                    },
                ),
                "recovery": denied_recovery,
            }
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
                output_payload=denied_result,
                metadata={
                    "iteration": planner_result.iteration,
                    "reasoning": planner_result.reasoning,
                    "policy_decision": policy_decision,
                },
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
                policy_decision=policy_decision,
                recovery=denied_result["recovery"],
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return self._build_observation(
                step=step,
                planner_result=planner_result,
                status="failed",
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                error=error_message,
                result=denied_result,
            )
        if managed_subagent is not None:
            tool_budget_gate = build_tool_budget_gate(
                target=managed_subagent,
                runtime_context=runtime_context,
                requested_tool_name=tool_name,
            )
            if not tool_budget_gate["allowed"]:
                error_message = f"Tool budget rejected: {tool_budget_gate['reason']}"
                await self.tracer.emit_event(
                    run.id,
                    "policy.denied",
                    step_id=step["id"],
                    policy_type="managed_subagent_tool_budget",
                    subject=tool_name,
                    tool_name=tool_name,
                    tool_kind=tool_kind,
                    subagent_target=managed_subagent.model_dump(mode="json"),
                    governance_policy=tool_budget_gate["policy"],
                    blockers=tool_budget_gate.get("blockers") or [],
                    recovery=tool_budget_gate.get("recovery") or {},
                    error=error_message,
                )
                tool_recovery = tool_budget_gate.get("recovery") or self._build_tool_recovery(
                    primary_code="tool_budget_exceeded",
                    summary=error_message,
                )
                step_output = {
                    "governance_policy": tool_budget_gate["policy"],
                    "tool_budget_gate": tool_budget_gate,
                    "tool_result": self._build_tool_failure_result(
                        tool_name=tool_name,
                        tool_kind=tool_kind,
                        failure_category="tool_budget_exceeded",
                        error_message=error_message,
                        recovery=tool_recovery,
                        details={
                            "blockers": tool_budget_gate.get("blockers") or [],
                            "governance_policy": tool_budget_gate.get("policy") or {},
                        },
                    ),
                    "recovery": tool_recovery,
                }
                await self.run_repository.update_step(
                    step["id"],
                    status="failed",
                    error_message=error_message,
                    output_payload=step_output,
                    metadata={
                        "iteration": planner_result.iteration,
                        "reasoning": planner_result.reasoning,
                        "managed_subagent": managed_subagent.model_dump(mode="json"),
                        "tool_budget_gate": tool_budget_gate,
                    },
                )
                await self._emit_step_event(
                    run.id,
                    "step.failed",
                    step,
                    error=error_message,
                    output=step_output,
                    governance_policy=tool_budget_gate["policy"],
                    blockers=tool_budget_gate.get("blockers") or [],
                    recovery=tool_budget_gate.get("recovery") or {},
                )
                runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
                runtime_context["last_tool_budget_block"] = {
                    "tool_name": tool_name,
                    "target_slug": managed_subagent.slug,
                    "governance_policy": tool_budget_gate["policy"],
                    "blockers": tool_budget_gate.get("blockers") or [],
                    "recovery": tool_budget_gate.get("recovery") or {},
                }
                return self._build_observation(
                    step=step,
                    planner_result=planner_result,
                    status="failed",
                    tool_name=tool_name,
                    tool_arguments=tool_arguments,
                    error=error_message,
                    result=step_output,
                )
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
                result=self._build_tool_failure_result(
                    tool_name=tool_name,
                    tool_kind=tool_kind,
                    failure_category="cancelled",
                    error_message="Run cancelled",
                    recovery=self._build_tool_recovery(
                        primary_code="run_cancelled",
                        summary="Run cancelled",
                        actions=[],
                    ),
                ),
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
                result=self._build_tool_failure_result(
                    tool_name=tool_name,
                    tool_kind=tool_kind,
                    failure_category="cancelled",
                    error_message="Run cancelled",
                    recovery=self._build_tool_recovery(
                        primary_code="run_cancelled",
                        summary="Run cancelled",
                        actions=[],
                    ),
                ),
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
            metadata = dict(policy_decision.get("metadata") or {})
            tool_recovery = self._build_tool_recovery(
                primary_code="tool_execution_failed",
                summary=error_message,
                actions=self._tool_recovery_actions(metadata=metadata),
            )
            failure_result = self._build_tool_failure_result(
                tool_name=tool_name,
                tool_kind=tool_kind,
                failure_category="execution_error",
                error_message=error_message,
                recovery=tool_recovery,
            )
            await self.tool_call_repository.update_tool_call(
                tool_call["id"],
                status="failed",
                result=failure_result,
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
                result=failure_result,
                recovery=tool_recovery,
            )
            await self.run_repository.update_step(
                step["id"],
                status="failed",
                error_message=error_message,
                output_payload={"tool_result": failure_result, "recovery": tool_recovery},
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
                output={"tool_result": failure_result, "recovery": tool_recovery},
                recovery=tool_recovery,
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return self._build_observation(
                step=step,
                planner_result=planner_result,
                status="failed",
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                error=error_message,
                result={"tool_result": failure_result, "recovery": tool_recovery},
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
    ) -> tuple[Dict[str, Any], dict[str, Any] | None]:
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
                blockers=gate.get("blockers") or [],
                recovery=gate.get("recovery") or {},
                error=error_message,
            )
            await self._emit_step_event(
                run.id,
                "step.failed",
                step,
                error=error_message,
                delegate_target=target.slug,
                delegation_gate=gate,
                blockers=gate.get("blockers") or [],
                recovery=gate.get("recovery") or {},
            )
            runtime_context["tool_failures"] = int(runtime_context.get("tool_failures", 0)) + 1
            return (
                self._build_observation(
                    step=step,
                    planner_result=planner_result,
                    status="failed",
                    error=error_message,
                    delegate_target=target.slug,
                ),
                None,
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
            progress={"state": "in_progress"},
        )

        try:
            if target.uses_async_execution():
                delegation = await self.subagent_handoff.start_delegate(
                    parent_run=run,
                    parent_step_id=step["id"],
                    planner_action=action,
                    runtime_context=runtime_context,
                    target=target,
                )
            else:
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
            return (
                self._build_observation(
                    step=step,
                    planner_result=planner_result,
                    status="failed",
                    error=error_message,
                    delegate_target=target.slug,
                ),
                None,
            )

        if delegation.status in {"queued", "running"}:
            ledger_entry = record_delegation_outcome(
                runtime_context,
                target_slug=target.slug,
                status=delegation.status,
                child_run_id=delegation.child_run_id,
                invocation_id=delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                usage={},
                waiting_user_propagation=None,
                waiting_user_counts_as_active_child=True,
                write_scope=delegation.input.get("write_scope") if isinstance(delegation.input, dict) else None,
            )
            self._register_pending_subagent_invocation(
                runtime_context,
                target=target,
                step=step,
                planner_result=planner_result,
                gate=gate,
                delegation=delegation,
            )
            step_output = {
                "delegate_result": delegation.model_dump(mode="json"),
                "delegation_gate": gate,
                "governance_policy": delegation.metadata.get("governance_policy") if isinstance(delegation.metadata, dict) else {},
                "progress": delegation.progress,
                "recovery": gate.get("recovery") or {},
                "pending": True,
            }
            await self.run_repository.update_step(
                step["id"],
                status="running",
                output_payload=step_output,
                metadata={
                    "delegate_target": target.slug,
                    "delegation_gate": gate,
                    "invocation_id": delegation.metadata.get("invocation_id") if isinstance(delegation.metadata, dict) else None,
                    "child_run_id": delegation.child_run_id,
                    "async_execution": True,
                },
            )
            observation = self._build_observation(
                step=step,
                planner_result=planner_result,
                status="running",
                result={
                    "child_run_id": delegation.child_run_id,
                    "status": delegation.status,
                    "summary": delegation.summary,
                    "progress": delegation.progress,
                    "recovery": gate.get("recovery") or {},
                    "governance_policy": delegation.metadata.get("governance_policy") if isinstance(delegation.metadata, dict) else {},
                    "governance_history": ledger_entry.get("history") if isinstance(ledger_entry, dict) else {},
                },
                delegate_target=target.slug,
            )
            return observation, None

        return await self._complete_delegate_action(
            run=run,
            runtime_context=runtime_context,
            planner_result=planner_result,
            target=target,
            step=step,
            gate=gate,
            delegation=delegation,
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

        self._refresh_prompt_context(
            run_input=runtime_context.get("normalized_task_input") or run.input,
            runtime_context=runtime_context,
            phase="synthesis",
            force=bool(runtime_context.get("step_history")),
        )

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
        runtime_context.pop("pending_subagent_clarification", None)
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
        runtime_context = self._prepare_runtime_context(run)
        if self.workspace_manager is not None:
            runtime_context, workspace_events = self.workspace_manager.ensure_workspace_context(
                run_id=run.id,
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                run_input=run.input,
                metadata=run.metadata,
                agent_config=definition.config,
                existing_context=runtime_context,
            )
            for event in workspace_events:
                await self.tracer.emit_event(
                    run.id,
                    event["event_type"],
                    **event["payload"],
                )
            if workspace_events:
                run = run.model_copy(update={"context": runtime_context})

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
        runtime_context["mounted_knowledge_base_ids"] = mounted_knowledge_base_ids
        runtime_context["available_subagents"] = [target.model_dump(mode="json") for target in available_subagents]
        if managed_subagent is not None:
            runtime_context["managed_subagent"] = managed_subagent.model_dump(mode="json")

        planning_requested_model = self._extract_phase_requested_model(definition, run.input, phase="planning")
        synthesis_requested_model = self._extract_phase_requested_model(definition, run.input, phase="synthesis")
        knowledge_base_id = self._extract_knowledge_base_id(run.input)
        planning_resolution = await self.llm_service.resolve_candidates(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene="agent_planning",
            requested_model=planning_requested_model,
        )
        synthesis_resolution = await self.llm_service.resolve_candidates(
            tenant_id=run.tenant_id,
            user_id=run.user_id,
            knowledge_base_id=knowledge_base_id,
            route_scene="agent_synthesis",
            requested_model=synthesis_requested_model,
        )
        runtime_context["planning_model"] = {
            "route_scene": "agent_planning",
            "requested_model": planning_resolution.get("requested_model"),
            "candidate_count": len(planning_resolution.get("candidates", [])),
        }
        runtime_context["synthesis_model"] = {
            "route_scene": "agent_synthesis",
            "requested_model": synthesis_resolution.get("requested_model"),
            "candidate_count": len(synthesis_resolution.get("candidates", [])),
        }
        self._refresh_prompt_context(
            run_input=run.input,
            runtime_context=runtime_context,
            phase="bootstrap",
        )
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
        await self.tracer.emit_event(
            run.id,
            "context.compression.updated",
            phase="bootstrap",
            state=runtime_context.get(COMPRESSION_STATE_KEY, {}),
        )

        max_iterations = self._resolve_max_iterations(definition)
        last_plan: Dict[str, Any] | None = None
        for iteration in range(1, max_iterations + 1):
            self._raise_if_cancelled(run.id)
            runtime_context["execution_count"] = iteration
            pending_terminal_result = await self._collect_pending_subagent_invocations(
                run=run,
                runtime_context=runtime_context,
            )
            await self._persist_run_state(
                run.id,
                status="running",
                runtime_context=runtime_context,
                plan=last_plan,
            )
            if pending_terminal_result is not None:
                return pending_terminal_result

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
                observation, delegated_result = await self._execute_delegate_action(
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
                if delegated_result is not None:
                    return delegated_result
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
