from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from ai_runtime.core.agent_runtime.models import PlannerAction
from ai_runtime.core.agent_runtime.repositories.subagent_invocation_repository import SubagentInvocationRepository
from ai_runtime.contracts import hydrate_legacy_result
from ai_runtime.core.agent_runtime.subagents.governance import (
    annotate_governance_policy,
    build_governance_policy,
    build_governance_blocker,
    build_subagent_failure_strategy,
    extract_governance_usage,
    merge_governance_usage_snapshots,
    resolve_budget_hard_limit_enabled,
    resolve_timeout_seconds,
)
from ai_runtime.core.agent_runtime.subagents.models import SubagentDelegationResult, SubagentTarget
from ai_runtime.core.agent_runtime.subagents.protocol import (
    build_partial_result_payload,
    build_progress_payload,
    build_requested_progress_payload,
    build_clarification_payload,
)
from ai_runtime.core.agent_runtime.subagents.review import build_review_result


class SubagentHandoff:
    def __init__(
        self,
        run_repository,
        tracer,
        state_store,
        *,
        start_run: Callable[[str], Awaitable[None]],
        invocation_repository: SubagentInvocationRepository | None = None,
    ) -> None:
        self.run_repository = run_repository
        self.tracer = tracer
        self.state_store = state_store
        self.start_run = start_run
        self.invocation_repository = invocation_repository

    def _resolve_parent_depth(self, parent_run) -> int:
        delegation = parent_run.metadata.get("delegation")
        if not isinstance(delegation, dict):
            return 0
        try:
            return max(0, int(delegation.get("depth") or 0))
        except (TypeError, ValueError):
            return 0

    def _resolve_child_message(
        self,
        *,
        parent_run,
        planner_action: PlannerAction,
        target: SubagentTarget,
    ) -> str:
        child_input = dict(planner_action.delegate_input or {})
        parent_message = str(parent_run.input.get("message") or parent_run.input.get("prompt") or "").strip()
        delegate_task = str(planner_action.delegate_task or "").strip()
        child_message = str(child_input.get("message") or child_input.get("prompt") or "").strip()

        if target.handoff_prompt:
            prefix = target.handoff_prompt.strip()
            if delegate_task:
                child_message = f"{prefix}\n\nDelegated task:\n{delegate_task}"
            elif child_message:
                child_message = f"{prefix}\n\nDelegated task:\n{child_message}"
            else:
                child_message = prefix
        elif delegate_task:
            child_message = delegate_task
        elif not child_message:
            child_message = parent_message

        return child_message

    def _build_constraints(
        self,
        *,
        planner_action: PlannerAction,
        target: SubagentTarget,
    ) -> list[str]:
        constraints: list[str] = []
        if target.requires_review():
            constraints.append("A review or verification quality bar is required for this capability.")
        if target.output_schema:
            constraints.append("Return a result that conforms to the configured structured output contract.")
        if target.tool_allowlist:
            constraints.append(f"Use only the allowed tools: {', '.join(target.tool_allowlist)}.")
        if target.skill_allowlist:
            constraints.append(f"Operate only within the allowed skills: {', '.join(target.skill_allowlist)}.")

        delegate_input = planner_action.delegate_input or {}
        raw_constraints = delegate_input.get("constraints")
        if isinstance(raw_constraints, list):
            constraints.extend(str(item).strip() for item in raw_constraints if str(item).strip())
        elif isinstance(raw_constraints, str) and raw_constraints.strip():
            constraints.append(raw_constraints.strip())

        for key in ("focus_paths", "deliverables", "checks"):
            value = delegate_input.get(key)
            if isinstance(value, list):
                values = [str(item).strip() for item in value if str(item).strip()]
                if values:
                    constraints.append(f"{key}: {', '.join(values)}")
            elif isinstance(value, str) and value.strip():
                constraints.append(f"{key}: {value.strip()}")

        return list(dict.fromkeys(item for item in constraints if item))

    def _build_context_slice(
        self,
        *,
        parent_run,
        runtime_context: dict[str, Any],
        target: SubagentTarget,
    ) -> dict[str, Any]:
        max_observations = target.max_context_observations()
        step_history = runtime_context.get("step_history")
        if not isinstance(step_history, list):
            step_history = []
        conversation = runtime_context.get("conversation")
        if not isinstance(conversation, list):
            conversation = []

        return {
            "parent_run_id": parent_run.id,
            "parent_agent_definition_id": parent_run.agent_definition_id,
            "delegation_depth": self._resolve_parent_depth(parent_run),
            "original_user_input": {
                "message": str(parent_run.input.get("message") or parent_run.input.get("prompt") or "").strip(),
                "input": dict(parent_run.input),
            },
            "normalized_task_input": dict(runtime_context.get("normalized_task_input") or {}),
            "intent_state": dict(runtime_context.get("intent_state") or {}),
            "recent_observations": list(step_history)[-max_observations:],
            "conversation_tail": list(conversation)[-4:],
            "mounted_knowledge_base_ids": list(runtime_context.get("mounted_knowledge_base_ids") or []),
            "pending_question": runtime_context.get("pending_question"),
        }

    def _build_policy_snapshot(self, *, target: SubagentTarget) -> dict[str, Any]:
        return {
            "target": {
                "slug": target.slug,
                "name": target.name,
                "description": target.description,
                "subagent_definition_id": target.subagent_definition_id,
                "publication_id": target.publication_id,
                "version_id": target.version_id,
                "authorization_id": target.authorization_id,
            },
            "system_prompt": target.system_prompt,
            "model": target.model,
            "config": dict(target.config or {}),
            "output_schema": dict(target.output_schema or {}),
            "handoff_input_schema": dict(target.handoff_input_schema or {}),
            "tool_allowlist": list(target.tool_allowlist or []),
            "skill_allowlist": list(target.skill_allowlist or []),
            "mcp_allowlist": list(target.mcp_allowlist or []),
            "knowledge_policy": dict(target.knowledge_policy or {}),
            "review_policy": target.normalized_review_policy(),
            "runtime_policy": dict(target.runtime_policy or {}),
            "budget_policy": dict(target.budget_policy or {}),
            "governance_policy": build_governance_policy(target),
            "delegation_mode": target.delegation_mode(),
            "allows_nested_delegation": target.allows_nested_delegation(),
            "metadata": dict(target.metadata or {}),
        }

    def _build_handoff_envelope(
        self,
        *,
        parent_run,
        planner_action: PlannerAction,
        target: SubagentTarget,
        runtime_context: dict[str, Any],
        child_message: str,
        invocation_id: str | None,
    ) -> dict[str, Any]:
        return {
            "protocol_version": "managed-subagent.v1",
            "invocation_id": invocation_id,
            "task": {
                "message": child_message,
                "delegate_task": str(planner_action.delegate_task or "").strip() or None,
                "delegate_input": dict(planner_action.delegate_input or {}),
                "reason": str(planner_action.content or "").strip() or None,
            },
            "constraints": self._build_constraints(
                planner_action=planner_action,
                target=target,
            ),
            "context_slice": self._build_context_slice(
                parent_run=parent_run,
                runtime_context=runtime_context,
                target=target,
            ),
            "progress": build_requested_progress_payload(
                summary=f"{target.name} is taking over the delegated task.",
                delegate_task=str(planner_action.delegate_task or "").strip(),
                delegate_input=planner_action.delegate_input or {},
            ),
            "clarification": None,
            "policy_snapshot": self._build_policy_snapshot(target=target),
            "status": "requested",
            "partial_result": None,
            "final_result": None,
            "error": None,
        }

    def _build_child_input(
        self,
        *,
        parent_run,
        planner_action: PlannerAction,
        target: SubagentTarget,
        runtime_context: dict[str, Any],
        child_message: str,
        handoff_envelope: dict[str, Any],
        invocation_id: str | None,
    ) -> dict[str, Any]:
        child_input = dict(planner_action.delegate_input or {})
        delegate_task = str(planner_action.delegate_task or "").strip()
        parent_depth = self._resolve_parent_depth(parent_run)

        child_input.update(
            {
                "message": child_message,
                "delegation": {
                    "protocol_version": handoff_envelope.get("protocol_version"),
                    "invocation_id": invocation_id,
                    "parent_run_id": parent_run.id,
                    "parent_agent_definition_id": parent_run.agent_definition_id,
                    "host_agent_definition_id": target.agent_definition_id,
                    "subagent_definition_id": target.subagent_definition_id,
                    "publication_id": target.publication_id,
                    "version_id": target.version_id,
                    "authorization_id": target.authorization_id,
                    "target_slug": target.slug,
                    "target_name": target.name,
                    "depth": parent_depth + 1,
                    "delegate_task": delegate_task,
                    "reason": str(planner_action.content or "").strip() or None,
                    "recent_observations": list(runtime_context.get("step_history") or [])[-3:],
                },
                "handoff_envelope": handoff_envelope,
            }
        )
        return child_input

    def _build_child_run_metadata(
        self,
        *,
        parent_run,
        parent_step_id: str,
        target: SubagentTarget,
        handoff_envelope: dict[str, Any],
        invocation_id: str | None,
    ) -> dict[str, Any]:
        child_depth = self._resolve_parent_depth(parent_run) + 1
        delegation_metadata = {
            "protocol_version": handoff_envelope.get("protocol_version"),
            "invocation_id": invocation_id,
            "parent_run_id": parent_run.id,
            "parent_step_id": parent_step_id,
            "depth": child_depth,
            "target_slug": target.slug,
            "target_name": target.name,
            "subagent_definition_id": target.subagent_definition_id,
            "publication_id": target.publication_id,
            "version_id": target.version_id,
            "authorization_id": target.authorization_id,
        }
        metadata: dict[str, Any] = {
            "delegation": delegation_metadata,
            "subagent_handoff": {
                "protocol_version": handoff_envelope.get("protocol_version"),
                "invocation_id": invocation_id,
                "constraints": handoff_envelope.get("constraints") or [],
                "policy_snapshot": handoff_envelope.get("policy_snapshot") or {},
            },
        }
        if target.uses_managed_capability():
            metadata["managed_subagent"] = {
                "slug": target.slug,
                "name": target.name,
                "description": target.description,
                "subagent_definition_id": target.subagent_definition_id,
                "publication_id": target.publication_id,
                "version_id": target.version_id,
                "authorization_id": target.authorization_id,
                "system_prompt": target.system_prompt,
                "model": target.model,
                "config": target.config,
                "output_schema": target.output_schema,
                "handoff_input_schema": target.handoff_input_schema,
                "tool_allowlist": target.tool_allowlist,
                "skill_allowlist": target.skill_allowlist,
                "mcp_allowlist": target.mcp_allowlist,
                "knowledge_policy": target.knowledge_policy,
                "review_policy": target.normalized_review_policy(),
                "runtime_policy": target.runtime_policy,
                "budget_policy": target.budget_policy,
                "metadata": target.metadata,
                "host_agent_definition_id": target.agent_definition_id,
            }
        return metadata

    async def _create_invocation(
        self,
        *,
        parent_run,
        parent_step_id: str,
        target: SubagentTarget,
        request_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.invocation_repository is None or not target.subagent_definition_id:
            return None
        return await self.invocation_repository.create_invocation(
            parent_run_id=parent_run.id,
            parent_step_id=parent_step_id,
            subagent_definition_id=target.subagent_definition_id,
            publication_id=target.publication_id,
            version_id=target.version_id,
            authorization_id=target.authorization_id,
            status="queued",
            request_payload=request_payload,
        )

    async def _update_invocation(
        self,
        invocation_id: str | None,
        *,
        status: str,
        child_run_id: str | None = None,
        request_payload: dict[str, Any] | None = None,
        result_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        if self.invocation_repository is None or not invocation_id:
            return
        await self.invocation_repository.update_invocation(
            invocation_id,
            status=status,
            child_run_id=child_run_id,
            request_payload=request_payload,
            result_payload=result_payload,
            error_message=error_message,
        )

    def _build_terminal_result_payload(
        self,
        *,
        status: str,
        summary: str,
        hydrated: dict[str, Any],
        target: SubagentTarget,
        review_result: dict[str, Any],
        governance_policy: dict[str, Any],
        failure_strategy: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        result_status = str(status or "").strip().lower()
        question = hydrated.get("final_output") if result_status == "waiting_user" else None
        progress = build_progress_payload(
            status=result_status,
            hydrated=hydrated,
            summary=summary,
        )
        clarification = build_clarification_payload(
            status=result_status,
            hydrated=hydrated,
            question=question,
        )
        partial_result = (
            build_partial_result_payload(
                status=result_status,
                hydrated=hydrated,
                summary=summary,
                question=question,
            )
            if result_status == "waiting_user"
            else None
        )
        return {
            "protocol_version": "managed-subagent.v1",
            "status": result_status,
            "review_result": review_result,
            "governance_policy": governance_policy,
            "failure_strategy": failure_strategy
            or build_subagent_failure_strategy(
                status=result_status,
                target=target,
                error_message=error_message,
            ),
            "partial_result": partial_result,
            "final_result": {
                "summary": summary,
                "final_output": hydrated.get("final_output"),
                "final_output_text": hydrated.get("final_output_text"),
                "final_output_json": hydrated.get("final_output_json"),
                "artifacts": hydrated.get("artifacts") or [],
                "progress": progress,
                "clarification": clarification,
            },
            "error": error_message,
        }

    async def _wait_for_terminal_status(self, child_run_id: str) -> dict[str, Any]:
        while True:
            child_run = await self.run_repository.get_run(child_run_id)
            if child_run is None:
                raise ValueError(f"subagent child run {child_run_id} not found")

            status = str(child_run.get("status") or "").strip().lower()
            if status in {"completed", "failed", "cancelled", "waiting_user"}:
                return child_run

            task = self.state_store.get_task(child_run_id)
            if task is not None:
                await asyncio.wait({task}, timeout=0.2)
            else:
                await asyncio.sleep(0.2)

    async def _wait_for_terminal_status_with_policy(
        self,
        child_run_id: str,
        *,
        target: SubagentTarget,
    ) -> dict[str, Any]:
        timeout_seconds = resolve_timeout_seconds(target)
        if timeout_seconds is None:
            return await self._wait_for_terminal_status(child_run_id)
        return await asyncio.wait_for(self._wait_for_terminal_status(child_run_id), timeout=timeout_seconds)

    async def start_delegate(
        self,
        *,
        parent_run,
        parent_step_id: str,
        planner_action: PlannerAction,
        runtime_context: dict[str, Any],
        target: SubagentTarget,
    ) -> SubagentDelegationResult:
        child_message = self._resolve_child_message(
            parent_run=parent_run,
            planner_action=planner_action,
            target=target,
        )
        base_envelope = self._build_handoff_envelope(
            parent_run=parent_run,
            planner_action=planner_action,
            target=target,
            runtime_context=runtime_context,
            child_message=child_message,
            invocation_id=None,
        )
        invocation = await self._create_invocation(
            parent_run=parent_run,
            parent_step_id=parent_step_id,
            target=target,
            request_payload=base_envelope,
        )
        invocation_id = str(invocation.get("id")) if isinstance(invocation, dict) and invocation.get("id") else None
        handoff_envelope = (
            base_envelope
            if invocation_id is None
            else {
                **base_envelope,
                "invocation_id": invocation_id,
            }
        )
        child_input = self._build_child_input(
            parent_run=parent_run,
            planner_action=planner_action,
            target=target,
            runtime_context=runtime_context,
            child_message=child_message,
            handoff_envelope=handoff_envelope,
            invocation_id=invocation_id,
        )
        child_agent_definition_id = target.agent_definition_id or parent_run.agent_definition_id
        if not child_agent_definition_id:
            raise ValueError("managed subagent handoff requires either a host capability target or a parent agent definition")
        try:
            child_run = await self.run_repository.create_run(
                {
                    "agent_definition_id": child_agent_definition_id,
                    "tenant_id": parent_run.tenant_id,
                    "user_id": parent_run.user_id,
                    "session_id": parent_run.session_id,
                    "input": child_input,
                    "metadata": self._build_child_run_metadata(
                        parent_run=parent_run,
                        parent_step_id=parent_step_id,
                        target=target,
                        handoff_envelope=handoff_envelope,
                        invocation_id=invocation_id,
                    ),
                }
            )
            await self._update_invocation(
                invocation_id,
                status="running",
                child_run_id=child_run["id"],
                request_payload=handoff_envelope,
            )
            await self.tracer.emit_event(
                child_run["id"],
                "run.created",
                status=child_run["status"],
                input=child_input,
                parent_run_id=parent_run.id,
                parent_step_id=parent_step_id,
                invocation_id=invocation_id,
            )
            await self.start_run(child_run["id"])

            progress = build_requested_progress_payload(
                summary=f"{target.name} child run is running asynchronously.",
                delegate_task=str(planner_action.delegate_task or "").strip(),
                delegate_input=planner_action.delegate_input or {},
            )
            return SubagentDelegationResult(
                child_run_id=child_run["id"],
                status="running",
                target=target,
                input=child_input,
                summary=f"{target.name} child run started.",
                progress=progress,
                clarification={},
                metadata={
                    "parent_step_id": parent_step_id,
                    "invocation_id": invocation_id,
                    "protocol_version": handoff_envelope.get("protocol_version"),
                    "handoff_envelope": handoff_envelope,
                    "governance_policy": annotate_governance_policy(build_governance_policy(target)),
                    "async_execution": True,
                },
            )
        except asyncio.CancelledError:
            review_result = build_review_result(
                target=target,
                status="cancelled",
                hydrated={},
                error_message="Run cancelled",
            )
            await self._update_invocation(
                invocation_id,
                status="cancelled",
                error_message="Run cancelled",
                result_payload={
                    "protocol_version": "managed-subagent.v1",
                    "status": "cancelled",
                    "review_result": review_result,
                    "partial_result": None,
                    "final_result": None,
                    "error": "Run cancelled",
                    "governance_policy": annotate_governance_policy(build_governance_policy(target)),
                },
            )
            raise
        except Exception as exc:
            review_result = build_review_result(
                target=target,
                status="failed",
                hydrated={},
                error_message=str(exc),
            )
            await self._update_invocation(
                invocation_id,
                status="failed",
                error_message=str(exc),
                result_payload={
                    "protocol_version": "managed-subagent.v1",
                    "status": "failed",
                    "review_result": review_result,
                    "partial_result": None,
                    "final_result": None,
                    "error": str(exc),
                    "governance_policy": annotate_governance_policy(build_governance_policy(target)),
                },
            )
            raise

    async def resolve_delegation_result(
        self,
        *,
        child_run_id: str,
        target: SubagentTarget,
        child_input: dict[str, Any] | None = None,
        parent_step_id: str | None = None,
        invocation_id: str | None = None,
        handoff_envelope: dict[str, Any] | None = None,
    ) -> SubagentDelegationResult | None:
        child_run = await self.run_repository.get_run(child_run_id)
        if child_run is None:
            raise ValueError(f"subagent child run {child_run_id} not found")

        status = str(child_run.get("status") or "").strip().lower()
        if status not in {"completed", "failed", "cancelled", "waiting_user"}:
            return None

        artifacts = await self.run_repository.list_artifacts(child_run_id)
        hydrated = hydrate_legacy_result(
            final_output=child_run.get("final_output"),
            final_output_text=child_run.get("final_output_text"),
            final_output_json=child_run.get("final_output_json"),
            artifacts=artifacts,
        )
        summary = str(hydrated.get("final_output_text") or hydrated.get("final_output") or "").strip()
        if not summary:
            summary = f"{target.name} finished with status {status}."
        review_result = build_review_result(
            target=target,
            status=status,
            hydrated=hydrated,
            error_message=child_run.get("error_message"),
            child_run_id=child_run_id,
        )
        governance_policy = annotate_governance_policy(
            build_governance_policy(target),
            last_invocation_usage=extract_governance_usage(
                child_run=child_run,
                hydrated=hydrated,
            ),
        )
        if (
            resolve_budget_hard_limit_enabled(target)
            and governance_policy.get("enforcement", {}).get("budget_hard_limit_exceeded")
        ):
            status = "failed"
            if not child_run.get("error_message"):
                child_run["error_message"] = governance_policy["enforcement"].get(
                    "budget_hard_limit_reason",
                    "Subagent exceeded hard budget limit",
                )
            governance_policy["blockers"] = [
                {
                    "code": "budget_hard_limit_exceeded",
                    "message": child_run.get("error_message"),
                    "severity": "error",
                    "recoverable": True,
                    "recovery_actions": [
                        "Stop delegation to this capability until prior child usage is reviewed.",
                        "Reduce the delegated scope, raise the hard budget limit, or switch the budget to advisory mode.",
                    ],
                    "details": {
                        "child_run_id": child_run_id,
                        "target_slug": target.slug,
                    },
                }
            ]
            review_result = build_review_result(
                target=target,
                status=status,
                hydrated=hydrated,
                error_message=child_run.get("error_message"),
                child_run_id=child_run_id,
            )
        failure_strategy = build_subagent_failure_strategy(
            status=status,
            target=target,
            blockers=governance_policy.get("blockers") if isinstance(governance_policy.get("blockers"), list) else [],
            error_message=child_run.get("error_message"),
        )
        progress = build_progress_payload(
            status=status,
            hydrated=hydrated,
            summary=summary,
        )
        clarification = build_clarification_payload(
            status=status,
            hydrated=hydrated,
            question=hydrated.get("final_output") if status == "waiting_user" else None,
        )

        invocation_status = status
        await self._update_invocation(
            invocation_id,
            status=invocation_status,
            child_run_id=child_run_id,
            result_payload=self._build_terminal_result_payload(
                status=status,
                summary=summary,
                hydrated=hydrated,
                target=target,
                review_result=review_result,
                governance_policy=governance_policy,
                failure_strategy=failure_strategy,
                error_message=child_run.get("error_message"),
            ),
            error_message=child_run.get("error_message"),
        )

        return SubagentDelegationResult(
            child_run_id=child_run_id,
            status=status,
            target=target,
            input=child_input or {},
            summary=summary,
            final_output=hydrated.get("final_output"),
            final_output_text=hydrated.get("final_output_text"),
            final_output_json=hydrated.get("final_output_json"),
            artifacts=hydrated.get("artifacts") or [],
            progress=progress,
            clarification=clarification or {},
            metadata={
                "parent_step_id": parent_step_id,
                "invocation_id": invocation_id,
                "protocol_version": (handoff_envelope or {}).get("protocol_version"),
                "handoff_envelope": handoff_envelope or {},
                "review_result": review_result,
                "governance_policy": governance_policy,
                "failure_strategy": failure_strategy,
            },
        )

    async def delegate(
        self,
        *,
        parent_run,
        parent_step_id: str,
        planner_action: PlannerAction,
        runtime_context: dict[str, Any],
        target: SubagentTarget,
    ) -> SubagentDelegationResult:
        started = await self.start_delegate(
            parent_run=parent_run,
            parent_step_id=parent_step_id,
            planner_action=planner_action,
            runtime_context=runtime_context,
            target=target,
        )
        invocation_id = started.metadata.get("invocation_id") if isinstance(started.metadata, dict) else None
        try:
            completed = await self._wait_for_terminal_status_with_policy(
                started.child_run_id,
                target=target,
            )
            resolved = await self.resolve_delegation_result(
                child_run_id=completed["id"],
                target=target,
                child_input=started.input,
                parent_step_id=parent_step_id,
                invocation_id=invocation_id,
                handoff_envelope=started.metadata.get("handoff_envelope") if isinstance(started.metadata, dict) else None,
            )
            if resolved is None:
                raise RuntimeError(f"subagent child run {completed['id']} did not reach a terminal status")
            return resolved
        except asyncio.TimeoutError:
            timeout_seconds = resolve_timeout_seconds(target)
            message = f"Subagent execution exceeded timeout of {timeout_seconds:g}s" if timeout_seconds else "Subagent execution timed out"
            blockers = [
                build_governance_blocker(
                    "timeout_exceeded",
                    message,
                    details={
                        "target_slug": target.slug,
                        "timeout_seconds": timeout_seconds,
                    },
                )
            ]
            review_result = build_review_result(
                target=target,
                status="failed",
                hydrated={},
                error_message=message,
            )
            governance_policy = annotate_governance_policy(
                build_governance_policy(target),
                warnings=[message],
            )
            governance_policy["blockers"] = blockers
            governance_policy["recovery"] = {
                "recoverable": True,
                "primary_code": "timeout_exceeded",
                "summary": message,
                "actions": build_subagent_failure_strategy(
                    status="failed",
                    target=target,
                    blockers=blockers,
                    error_message=message,
                )["recovery"]["actions"],
            }
            await self._update_invocation(
                invocation_id,
                status="failed",
                error_message=message,
                result_payload={
                    "protocol_version": "managed-subagent.v1",
                    "status": "failed",
                    "review_result": review_result,
                    "partial_result": None,
                    "final_result": None,
                    "error": message,
                    "governance_policy": governance_policy,
                    "failure_strategy": build_subagent_failure_strategy(
                        status="failed",
                        target=target,
                        blockers=blockers,
                        error_message=message,
                    ),
                },
            )
            raise TimeoutError(message) from None
        except asyncio.CancelledError:
            review_result = build_review_result(
                target=target,
                status="cancelled",
                hydrated={},
                error_message="Run cancelled",
            )
            await self._update_invocation(
                invocation_id,
                status="cancelled",
                error_message="Run cancelled",
                result_payload={
                    "protocol_version": "managed-subagent.v1",
                    "status": "cancelled",
                    "review_result": review_result,
                    "partial_result": None,
                    "final_result": None,
                    "error": "Run cancelled",
                    "governance_policy": annotate_governance_policy(build_governance_policy(target)),
                    "failure_strategy": build_subagent_failure_strategy(
                        status="cancelled",
                        target=target,
                        error_message="Run cancelled",
                    ),
                },
            )
            raise
        except Exception as exc:
            review_result = build_review_result(
                target=target,
                status="failed",
                hydrated={},
                error_message=str(exc),
            )
            await self._update_invocation(
                invocation_id,
                status="failed",
                error_message=str(exc),
                result_payload={
                    "protocol_version": "managed-subagent.v1",
                    "status": "failed",
                    "review_result": review_result,
                    "partial_result": None,
                    "final_result": None,
                    "error": str(exc),
                    "governance_policy": annotate_governance_policy(build_governance_policy(target)),
                    "failure_strategy": build_subagent_failure_strategy(
                        status="failed",
                        target=target,
                        error_message=str(exc),
                    ),
                },
            )
            raise
