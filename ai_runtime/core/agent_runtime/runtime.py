from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from core.agent_runtime.executor import AgentExecutor
from core.agent_runtime.llm_service import AgentLLMService
from core.agent_runtime.memory import RuntimeStateStore
from core.agent_runtime.mcp.registry import MCPRegistry
from core.agent_runtime.models import (
    AgentArtifact,
    AgentRun,
    AgentRunEvent,
    AgentRunEventListResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    AgentRunTreeEdge,
    AgentRunTreeNode,
    AgentRunTreeResponse,
    AgentRunTreeRunSummary,
    AgentSubagentInvocation,
    AgentSubagentInvocationListResponse,
    RuntimeCreateRunRequest,
)
from core.agent_runtime.orchestrator import AgentOrchestrator
from core.agent_runtime.skills.registry import SkillRegistry
from core.agent_runtime.planner import AgentPlanner
from core.agent_runtime.result_contract import hydrate_legacy_result, merge_artifacts
from core.agent_runtime.subagents.governance import prune_runtime_governance_ledger_for_resume
from core.agent_runtime.summarizer import AgentSummarizer
from core.agent_runtime.repositories.agent_repository import AgentRepository
from core.agent_runtime.repositories.run_repository import RunRepository
from core.agent_runtime.repositories.subagent_invocation_repository import SubagentInvocationRepository
from core.agent_runtime.subagents.handoff import SubagentHandoff
from core.agent_runtime.subagents.registry import SubagentRegistry
from core.agent_runtime.subagents.router import SubagentRouter
from core.agent_runtime.repositories.tool_call_repository import ToolCallRepository
from core.agent_runtime.tools.base import ToolLookupContext
from core.agent_runtime.tools.providers.bootstrap import configure_tool_registry
from core.agent_runtime.tools.registry import ToolRegistry
from core.agent_runtime.tracing import AgentTracer
from core.uploads.bundle_store import get_attachment_bundle_store, normalize_bundle_ids


class AgentRuntime:
    def __init__(self, db_pool) -> None:
        self.agent_repository = AgentRepository(db_pool)
        self.run_repository = RunRepository(db_pool)
        self.tool_call_repository = ToolCallRepository(db_pool)
        self.subagent_invocation_repository = SubagentInvocationRepository(db_pool)
        self.state_store = RuntimeStateStore()
        self.registry = ToolRegistry()
        self.mcp_registry = MCPRegistry(db_pool)
        configure_tool_registry(self.registry, mcp_registry=self.mcp_registry)
        self.skill_registry = SkillRegistry(db_pool)
        self.subagent_registry = SubagentRegistry(db_pool, self.agent_repository)
        self.llm_service = AgentLLMService()

        self.tracer = AgentTracer(
            self.run_repository,
            self.tool_call_repository,
            self.state_store,
        )
        self.subagent_handoff = SubagentHandoff(
            self.run_repository,
            self.tracer,
            self.state_store,
            start_run=self.start_run,
            invocation_repository=self.subagent_invocation_repository,
        )
        self.orchestrator = AgentOrchestrator(
            planner=AgentPlanner(),
            executor=AgentExecutor(self.registry),
            summarizer=AgentSummarizer(),
            llm_service=self.llm_service,
            tracer=self.tracer,
            agent_repository=self.agent_repository,
            run_repository=self.run_repository,
            tool_call_repository=self.tool_call_repository,
            state_store=self.state_store,
            skill_registry=self.skill_registry,
            subagent_registry=self.subagent_registry,
            subagent_router=SubagentRouter(),
            subagent_handoff=self.subagent_handoff,
        )

    def _hydrate_upload_context(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        run_input: dict | None,
    ) -> dict:
        payload = dict(run_input or {})
        bundle_ids = normalize_bundle_ids(payload.get("upload_bundle_ids"))
        if not bundle_ids:
            payload.pop("uploaded_attachments", None)
            payload.pop("uploaded_attachments_manifest", None)
            return payload

        query = str(payload.get("message") or payload.get("prompt") or payload.get("original_message") or "").strip()
        store = get_attachment_bundle_store()
        summary = store.summarize_bundles(
            tenant_id=tenant_id,
            user_id=user_id,
            bundle_ids=bundle_ids,
            query=query,
        )
        payload["upload_bundle_ids"] = bundle_ids
        payload["uploaded_attachments_manifest"] = {
            "bundle_ids": summary["bundle_ids"],
            "file_count": summary["file_count"],
            "directory_tree": summary["directory_tree"],
            "files": [
                {
                    "id": item.get("id"),
                    "bundle_id": item.get("bundle_id"),
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "score": item.get("score", 0),
                    "char_count": item.get("char_count"),
                }
                for item in summary["files"]
            ],
        }
        payload["uploaded_attachments"] = {
            "bundle_ids": summary["bundle_ids"],
            "directory_tree": summary["directory_tree"],
            "files": summary["files"],
            "context_text": summary["context_text"],
        }
        return payload

    def _build_resume_context(self, run_row: dict) -> dict:
        context = dict(run_row.get("context") or {})
        if not isinstance(context.get("conversation"), list):
            context["conversation"] = []
        if not isinstance(context.get("step_history"), list):
            context["step_history"] = []

        for key in (
            "pending_question",
            "pending_subagent_clarification",
            "ask_user_guard",
            "last_plan",
            "last_result_contract",
            "last_summary_model",
            "planning_model",
            "synthesis_model",
            "normalized_task_input",
            "mounted_knowledge_base_ids",
            "promoted_artifacts",
        ):
            context.pop(key, None)

        context = prune_runtime_governance_ledger_for_resume(context)
        context["tool_failures"] = 0
        context["execution_count"] = 0
        return context

    def _hydrate_run_row(
        self,
        run_row: dict,
        *,
        artifacts: list[dict] | None = None,
        steps: list[dict] | None = None,
        tool_calls: list[dict] | None = None,
    ) -> AgentRun:
        legacy = hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=artifacts,
        )
        hydrated = {
            **run_row,
            "final_output": legacy.get("final_output"),
            "final_output_text": legacy.get("final_output_text"),
            "final_output_json": legacy.get("final_output_json"),
            "artifacts": legacy.get("artifacts") or [],
            "steps": steps or [],
            "tool_calls": tool_calls or [],
        }
        return AgentRun.model_validate(
            {
                **hydrated,
                "artifacts": [AgentArtifact.model_validate(item) for item in hydrated["artifacts"]],
            }
        )

    def _hydrate_subagent_invocation_row(self, row: dict) -> AgentSubagentInvocation:
        return AgentSubagentInvocation.model_validate(
            {
                **row,
                "request_payload": row.get("request_payload") if isinstance(row.get("request_payload"), dict) else {},
                "result_payload": row.get("result_payload") if isinstance(row.get("result_payload"), dict) else {},
            }
        )

    def _hydrate_tree_run_summary(self, run_row: dict) -> AgentRunTreeRunSummary:
        legacy = hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=[],
        )
        return AgentRunTreeRunSummary.model_validate(
            {
                **run_row,
                "final_output": legacy.get("final_output"),
                "final_output_text": legacy.get("final_output_text"),
                "final_output_json": legacy.get("final_output_json"),
            }
        )

    async def _build_run_tree_node(
        self,
        run_row: dict,
        *,
        tenant_id: str | None,
        depth: int,
        remaining_depth: int,
    ) -> AgentRunTreeNode:
        invocations = await self.subagent_invocation_repository.list_invocations_for_parent_run(run_row["id"])
        invocation_models = [self._hydrate_subagent_invocation_row(item) for item in invocations]

        child_nodes_by_run_id: dict[str, AgentRunTreeNode] = {}
        child_run_ids = [
            invocation.child_run_id
            for invocation in invocation_models
            if invocation.child_run_id
        ]
        if remaining_depth > 0 and child_run_ids:
            child_rows = await self.run_repository.list_runs_by_ids(child_run_ids, tenant_id=tenant_id)
            child_rows_by_id = {str(item.get("id")): item for item in child_rows if item.get("id")}
            for child_run_id in child_run_ids:
                child_row = child_rows_by_id.get(child_run_id)
                if child_row is None:
                    continue
                child_nodes_by_run_id[child_run_id] = await self._build_run_tree_node(
                    child_row,
                    tenant_id=tenant_id,
                    depth=depth + 1,
                    remaining_depth=remaining_depth - 1,
                )

        return AgentRunTreeNode(
            run=self._hydrate_tree_run_summary(run_row),
            depth=depth,
            invocations=[
                AgentRunTreeEdge(
                    invocation=invocation,
                    child_run=child_nodes_by_run_id.get(invocation.child_run_id or ""),
                )
                for invocation in invocation_models
            ],
        )

    async def _load_terminal_run_surface(self, run_row: dict | None) -> dict:
        if not run_row:
            return {
                "final_output": None,
                "final_output_text": None,
                "final_output_json": None,
                "artifacts": [],
            }

        context = run_row.get("context") if isinstance(run_row.get("context"), dict) else {}
        promoted_artifacts = context.get("promoted_artifacts") if isinstance(context.get("promoted_artifacts"), list) else []
        stored_artifacts = await self.run_repository.list_artifacts(run_row["id"])
        return hydrate_legacy_result(
            final_output=run_row.get("final_output"),
            final_output_text=run_row.get("final_output_text"),
            final_output_json=run_row.get("final_output_json"),
            artifacts=merge_artifacts(stored_artifacts, promoted_artifacts),
        )

    async def list_tools(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        agent_definition_id: str | None = None,
    ) -> list[dict]:
        return await self.registry.list_specs(
            context=ToolLookupContext(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_definition_id=agent_definition_id,
            )
        )

    async def test_mcp_server(self, *, tenant_id: str, server_id: str) -> dict:
        return (await self.mcp_registry.test_server(tenant_id=tenant_id, server_id=server_id)).model_dump(mode="json")

    async def refresh_mcp_server_tools(self, *, tenant_id: str, server_id: str) -> list[dict]:
        items = await self.mcp_registry.refresh_server_tools(tenant_id=tenant_id, server_id=server_id)
        return [item.model_dump(mode="json") for item in items]

    async def create_run(self, request: RuntimeCreateRunRequest) -> AgentRunSummaryResponse:
        hydrated_input = self._hydrate_upload_context(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            run_input=request.input,
        )
        run_row = await self.run_repository.create_run(
            {
                "agent_definition_id": request.agent_definition_id,
                "tenant_id": request.tenant_id,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "input": hydrated_input,
                "metadata": request.metadata,
            }
        )
        run = self._hydrate_run_row(run_row, artifacts=[])
        await self.tracer.emit_event(run.id, "run.created", status=run.status, input=run.input)
        if request.auto_start:
            await self.start_run(run.id)
            refreshed = await self.run_repository.get_run(run.id, run.tenant_id)
            artifacts = await self.run_repository.list_artifacts(run.id)
            steps = await self.run_repository.list_steps(run.id)
            tool_calls = await self.tool_call_repository.list_tool_calls(run.id)
            run = self._hydrate_run_row(refreshed, artifacts=artifacts, steps=steps, tool_calls=tool_calls)
        return AgentRunSummaryResponse(run=run)

    async def start_run(self, run_id: str) -> None:
        existing = self.state_store.get_task(run_id)
        if existing and not existing.done():
            return
        self.state_store.reset_cancel(run_id)
        task = asyncio.create_task(self.orchestrator.start_run(run_id))
        self.state_store.register_task(run_id, task)

    async def get_run(self, run_id: str, tenant_id: Optional[str]) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        artifacts = await self.run_repository.list_artifacts(run_id)
        steps = await self.run_repository.list_steps(run_id)
        tool_calls = await self.tool_call_repository.list_tool_calls(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(run, artifacts=artifacts, steps=steps, tool_calls=tool_calls))

    async def list_subagent_invocations(
        self,
        run_id: str,
        tenant_id: Optional[str],
    ) -> AgentSubagentInvocationListResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        rows = await self.subagent_invocation_repository.list_invocations_for_parent_run(run_id)
        invocations = [self._hydrate_subagent_invocation_row(row) for row in rows]
        return AgentSubagentInvocationListResponse(invocations=invocations, total=len(invocations))

    async def get_run_tree(
        self,
        run_id: str,
        tenant_id: Optional[str],
        *,
        max_depth: int = 4,
    ) -> AgentRunTreeResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        bounded_depth = max(1, min(int(max_depth), 8))
        root = await self._build_run_tree_node(
            run,
            tenant_id=tenant_id,
            depth=0,
            remaining_depth=bounded_depth - 1,
        )
        return AgentRunTreeResponse(root=root)

    async def list_runs(
        self,
        tenant_id: str,
        user_id: Optional[str],
        limit: int = 50,
        offset: int = 0,
    ) -> AgentRunListResponse:
        rows = await self.run_repository.list_runs(tenant_id, user_id=user_id, limit=limit, offset=offset)
        artifact_map = await self.run_repository.list_artifacts_for_runs([row["id"] for row in rows])
        runs = [self._hydrate_run_row(row, artifacts=artifact_map.get(row["id"], [])) for row in rows]
        return AgentRunListResponse(runs=runs, total=len(runs))

    async def list_events(
        self,
        run_id: str,
        tenant_id: Optional[str],
        after_sequence: int = 0,
        limit: int = 500,
    ) -> AgentRunEventListResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        rows = await self.run_repository.list_events(run_id, after_sequence=after_sequence, limit=limit)
        events = [AgentRunEvent.model_validate(row) for row in rows]
        return AgentRunEventListResponse(events=events, total=len(events))

    async def stream_events(
        self,
        run_id: str,
        tenant_id: Optional[str],
        after_sequence: int = 0,
    ) -> AsyncIterator[AgentRunEvent]:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")

        snapshot = await self.list_events(run_id, tenant_id, after_sequence=after_sequence)
        last_sequence = after_sequence
        for event in snapshot.events:
            last_sequence = max(last_sequence, event.sequence)
            yield event

        latest_run = await self.run_repository.get_run(run_id, tenant_id)
        if latest_run is None:
            raise ValueError("run not found")

        if latest_run["status"] in {"completed", "failed", "cancelled", "waiting_user"}:
            return

        async for event in self.state_store.subscribe(run_id):
            if event.sequence <= last_sequence:
                continue
            last_sequence = event.sequence
            yield event

    async def cancel_run(self, run_id: str, tenant_id: Optional[str]) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        terminal_surface = await self._load_terminal_run_surface(run)
        self.state_store.request_cancel(run_id)
        task = self.state_store.get_task(run_id)
        if task is not None and not task.done():
            task.cancel()
        updated = await self.run_repository.update_run_status(
            run_id,
            "cancelled",
            plan=run.get("plan") if isinstance(run.get("plan"), dict) else None,
            context=run.get("context") if isinstance(run.get("context"), dict) else None,
            final_output=terminal_surface.get("final_output"),
            final_output_text=terminal_surface.get("final_output_text"),
            final_output_json=terminal_surface.get("final_output_json"),
            error_message="Run cancelled",
        )
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
        artifacts = await self.run_repository.list_artifacts(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(updated, artifacts=artifacts))

    async def resume_run(
        self,
        run_id: str,
        tenant_id: Optional[str],
        input_patch: Optional[dict] = None,
    ) -> AgentRunSummaryResponse:
        run = await self.run_repository.get_run(run_id, tenant_id)
        if run is None:
            raise ValueError("run not found")
        if input_patch:
            merged_input = {
                **(run.get("input") if isinstance(run.get("input"), dict) else {}),
                **input_patch,
            }
            hydrated_input = self._hydrate_upload_context(
                tenant_id=str(run.get("tenant_id") or tenant_id or ""),
                user_id=run.get("user_id"),
                run_input=merged_input,
            )
            run = await self.run_repository.patch_run_input(run_id, hydrated_input)
            await self.tracer.emit_event(run_id, "run.input_patched", input_patch=input_patch)
        updated = await self.run_repository.reset_run_execution(
            run_id,
            context=self._build_resume_context(run),
        )
        await self.tracer.emit_event(run_id, "run.resumed", status="queued")
        await self.start_run(run_id)
        return AgentRunSummaryResponse(run=self._hydrate_run_row(updated, artifacts=[], steps=[], tool_calls=[]))
