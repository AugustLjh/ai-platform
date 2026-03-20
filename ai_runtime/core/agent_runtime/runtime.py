from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from core.agent_runtime.executor import AgentExecutor
from core.agent_runtime.memory import RuntimeStateStore
from core.agent_runtime.models import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventListResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    RuntimeCreateRunRequest,
)
from core.agent_runtime.orchestrator import AgentOrchestrator
from core.agent_runtime.planner import AgentPlanner
from core.agent_runtime.repositories.agent_repository import AgentRepository
from core.agent_runtime.repositories.run_repository import RunRepository
from core.agent_runtime.repositories.tool_call_repository import ToolCallRepository
from core.agent_runtime.tools.providers.builtin import register_builtin_tools
from core.agent_runtime.tools.registry import ToolRegistry
from core.agent_runtime.tracing import AgentTracer


class AgentRuntime:
    def __init__(self, db_pool) -> None:
        self.agent_repository = AgentRepository(db_pool)
        self.run_repository = RunRepository(db_pool)
        self.tool_call_repository = ToolCallRepository(db_pool)
        self.state_store = RuntimeStateStore()
        self.registry = ToolRegistry()
        register_builtin_tools(self.registry)

        self.tracer = AgentTracer(
            self.run_repository,
            self.tool_call_repository,
            self.state_store,
        )
        self.orchestrator = AgentOrchestrator(
            planner=AgentPlanner(),
            executor=AgentExecutor(self.registry),
            tracer=self.tracer,
            agent_repository=self.agent_repository,
            run_repository=self.run_repository,
            tool_call_repository=self.tool_call_repository,
            state_store=self.state_store,
        )

    async def create_run(self, request: RuntimeCreateRunRequest) -> AgentRunSummaryResponse:
        run_row = await self.run_repository.create_run(
            {
                "agent_definition_id": request.agent_definition_id,
                "tenant_id": request.tenant_id,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "input": request.input,
                "metadata": request.metadata,
            }
        )
        run = AgentRun.model_validate(run_row)
        await self.tracer.emit_event(run.id, "run.created", status=run.status, input=run.input)
        if request.auto_start:
            await self.start_run(run.id)
            refreshed = await self.run_repository.get_run(run.id, run.tenant_id)
            run = AgentRun.model_validate(refreshed)
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
        return AgentRunSummaryResponse(run=AgentRun.model_validate(run))

    async def list_runs(
        self,
        tenant_id: str,
        user_id: Optional[str],
        limit: int = 50,
        offset: int = 0,
    ) -> AgentRunListResponse:
        rows = await self.run_repository.list_runs(tenant_id, user_id=user_id, limit=limit, offset=offset)
        runs = [AgentRun.model_validate(row) for row in rows]
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
        self.state_store.request_cancel(run_id)
        task = self.state_store.get_task(run_id)
        if task is not None and not task.done():
            task.cancel()
        updated = await self.run_repository.update_run_status(run_id, "cancelled", error_message="Run cancelled")
        await self.tracer.emit_event(run_id, "run.cancelled", status="cancelled")
        return AgentRunSummaryResponse(run=AgentRun.model_validate(updated))

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
            run = await self.run_repository.patch_run_input(run_id, input_patch)
            await self.tracer.emit_event(run_id, "run.input_patched", input_patch=input_patch)
        updated = await self.run_repository.update_run_status(run_id, "queued", error_message=None)
        await self.tracer.emit_event(run_id, "run.resumed", status="queued")
        await self.start_run(run_id)
        return AgentRunSummaryResponse(run=AgentRun.model_validate(updated))
