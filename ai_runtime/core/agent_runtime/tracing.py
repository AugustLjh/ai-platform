from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from ai_runtime.core.agent_runtime.events import build_event_payload
from ai_runtime.core.agent_runtime.memory import RuntimeStateStore
from ai_runtime.core.agent_runtime.models import AgentRunEvent
from ai_runtime.core.agent_runtime.repositories.run_repository import RunRepository
from ai_runtime.core.agent_runtime.repositories.tool_call_repository import ToolCallRepository
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig


class AgentTracer:
    NONCRITICAL_EVENT_TYPES = {
        "context.compression.updated",
        "plan.created",
        "plan.ask_user_rejected",
        "skills.applied",
        "step.started",
        "step.completed",
        "step.failed",
        "step.cancelled",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "tool.cancelled",
        "subagent.started",
        "subagent.completed",
        "subagent.failed",
        "subagent.cancelled",
        "subagent.waiting_user",
    }

    def __init__(
        self,
        run_repository: RunRepository,
        tool_call_repository: ToolCallRepository,
        state_store: RuntimeStateStore,
    ) -> None:
        self.run_repository = run_repository
        self.tool_call_repository = tool_call_repository
        self.state_store = state_store
        self.optimization_config = AgentRuntimeOptimizationConfig.from_env()
        self._background_tasks: set[asyncio.Task] = set()

    async def _record_event(self, run_id: str, event_type: str, **payload: Any) -> AgentRunEvent:
        event_row = await self.run_repository.append_event(
            run_id,
            event_type,
            build_event_payload(**payload),
        )
        event = AgentRunEvent.model_validate(event_row)
        await self.state_store.publish(run_id, event)
        return event

    async def emit_event(self, run_id: str, event_type: str, **payload: Any) -> AgentRunEvent | None:
        if (
            self.optimization_config.enable_async_noncritical_events
            and event_type in self.NONCRITICAL_EVENT_TYPES
        ):
            task = asyncio.create_task(self._record_event(run_id, event_type, **payload))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return None
        return await self._record_event(run_id, event_type, **payload)

    async def flush(self) -> None:
        if not self._background_tasks:
            return
        await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

    async def create_step(
        self,
        run_id: str,
        *,
        kind: str,
        title: Optional[str],
        status: str,
        input_payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        step_index = await self.run_repository.get_next_step_index(run_id)
        return await self.run_repository.create_step(
            run_id,
            step_index=step_index,
            kind=kind,
            title=title,
            status=status,
            input_payload=input_payload,
            metadata=metadata,
        )
