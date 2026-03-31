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
from core.agent_runtime.result_contract import build_structured_run_result
from core.agent_runtime.skills.models import SkillRuntimeContext
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
    ) -> SkillRuntimeContext | None:
        return await self.skill_registry.resolve_for_agent(run.agent_definition_id, run.tenant_id) if self.skill_registry else None

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

    async def _resolve_accessible_mounted_knowledge_base_ids(self, run: AgentRun) -> list[str]:
        return await self.agent_repository.list_accessible_knowledge_bindings(
            run.agent_definition_id,
            run.tenant_id,
            run.user_id,
        )

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
        return sum(1 for step in step_history if isinstance(step, dict) and str(step.get("tool_name") or "").strip())

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
        return observation

    async def _get_tool_kind(self, run: AgentRun, tool_name: str) -> str:
        spec = await self.executor.registry.get_spec(
            tool_name,
            context=ToolLookupContext(
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                agent_definition_id=run.agent_definition_id,
                run_id=run.id,
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
            latest = await self.run_repository.get_run(run_id)
            if latest is not None and latest["status"] == "cancelled":
                updated = latest
            else:
                updated = await self.run_repository.update_run_status(
                    run_id,
                    "cancelled",
                    error_message="Run cancelled",
                )
                await self.tracer.emit_event(run_id, "run.cancelled", status="cancelled")
            return AgentRun.model_validate(updated)
        except Exception as exc:
            logger.exception("Agent run failed")
            updated = await self.run_repository.update_run_status(
                run_id,
                "failed",
                error_message=str(exc),
            )
            await self.tracer.emit_event(run_id, "run.failed", status="failed", error=str(exc))
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
        tool_kind = await self._get_tool_kind(run, tool_name)
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
                tool_context=ToolContext(
                    run_id=run.id,
                    tenant_id=run.tenant_id,
                    user_id=run.user_id,
                    agent_definition_id=run.agent_definition_id,
                    step_id=step["id"],
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
        step_output = {"tool_result": result}
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

    async def _execute_final_answer(
        self,
        *,
        definition: AgentDefinition,
        run: AgentRun,
        runtime_context: Dict[str, Any],
        skill_context: SkillRuntimeContext | None,
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

        try:
            summary, model_info = await self.summarizer.summarize(
                llm_service=self.llm_service,
                llm_resolution=synthesis_resolution,
                system_prompt=definition.system_prompt,
                run_input=run.input,
                runtime_context=runtime_context,
                skill_context=skill_context,
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

        output_schema = skill_context.output_schema if skill_context else None
        final_value: Any = summary
        if output_schema:
            try:
                final_value = json.loads(summary)
            except json.JSONDecodeError:
                final_value = summary
            final_value = self.executor.shape_output(final_value, output_schema)
        structured_result = build_structured_run_result(final_value, fallback_text=summary)
        final_output = structured_result["final_output"] or self.executor.format_output(final_value, output_schema)

        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload={
                "final_output": final_output,
                "final_output_text": structured_result.get("final_output_text"),
                "final_output_json": structured_result.get("final_output_json"),
                "artifacts": structured_result.get("artifacts") or [],
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
                "artifacts": structured_result.get("artifacts") or [],
            },
        )
        self._append_conversation_message(runtime_context, role="assistant", content=final_output)
        runtime_context["last_summary_model"] = model_info
        runtime_context["last_result_contract"] = {
            "final_output_text": structured_result.get("final_output_text"),
            "final_output_json": structured_result.get("final_output_json"),
            "artifact_count": len(structured_result.get("artifacts") or []),
        }
        return {
            "status": "completed",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": final_output,
            "final_output_text": structured_result.get("final_output_text"),
            "final_output_json": structured_result.get("final_output_json"),
            "artifacts": structured_result.get("artifacts") or [],
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
        return {
            "status": "waiting_user",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": action.question,
            "final_output_text": action.question,
            "final_output_json": None,
            "artifacts": [],
            "context": runtime_context,
        }

    async def _execute_run(self, definition: AgentDefinition, run: AgentRun) -> Dict[str, Any]:
        raw_skill_context = await self._resolve_skill_context(run)

        available_tools = await self.executor.registry.list_specs(
            context=ToolLookupContext(
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                agent_definition_id=run.agent_definition_id,
                run_id=run.id,
            )
        )
        runtime_policy = RuntimePolicy()
        mounted_knowledge_base_ids = await self._resolve_accessible_mounted_knowledge_base_ids(run)
        if not mounted_knowledge_base_ids:
            available_tools = [tool for tool in available_tools if tool.get("kind") != "knowledge"]
        runtime_context = self._prepare_runtime_context(run)
        runtime_context["mounted_knowledge_base_ids"] = mounted_knowledge_base_ids

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
                output_schema=output_skill_context.output_schema if output_skill_context else {},
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
                output_schema=output_skill_context.output_schema if output_skill_context else {},
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
                    planner_result=planner_result,
                    synthesis_resolution=synthesis_resolution,
                )

            observation = await self._execute_tool_action(
                definition=definition,
                run=run,
                runtime_context=runtime_context,
                planner_result=planner_result,
                runtime_policy=runtime_policy,
            )
            runtime_context.setdefault("step_history", []).append(observation)
            await self._persist_run_state(
                run.id,
                status="running",
                runtime_context=runtime_context,
                plan=last_plan,
            )

        raise RuntimeError(f"Agent exceeded maximum iterations ({max_iterations}) before reaching a final answer")
