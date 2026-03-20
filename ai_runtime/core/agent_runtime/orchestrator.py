from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from core.agent_runtime.executor import AgentExecutor
from core.agent_runtime.models import AgentDefinition, AgentRun, PlannerResult
from core.agent_runtime.planner import AgentPlanner
from core.agent_runtime.tools.base import ToolContext
from core.agent_runtime.tracing import AgentTracer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        planner: AgentPlanner,
        executor: AgentExecutor,
        tracer: AgentTracer,
        agent_repository,
        run_repository,
        tool_call_repository,
        state_store,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.tracer = tracer
        self.agent_repository = agent_repository
        self.run_repository = run_repository
        self.tool_call_repository = tool_call_repository
        self.state_store = state_store

    async def start_run(self, run_id: str) -> AgentRun:
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

        try:
            result = await self._execute_run(definition, run)
            updated = await self.run_repository.update_run_status(
                run.id,
                result["status"],
                plan=result.get("plan"),
                final_output=result.get("final_output"),
                error_message=result.get("error_message"),
            )
            if result["status"] == "completed":
                await self.tracer.emit_event(
                    run.id,
                    "run.completed",
                    status=result["status"],
                    final_output=result.get("final_output"),
                )
            elif result["status"] == "waiting_user":
                await self.tracer.emit_event(
                    run.id,
                    "run.waiting_user",
                    status=result["status"],
                    question=result.get("final_output"),
                )
            return AgentRun.model_validate(updated)
        except asyncio.CancelledError:
            updated = await self.run_repository.update_run_status(
                run.id,
                "cancelled",
                error_message="Run cancelled",
            )
            await self.tracer.emit_event(run.id, "run.cancelled", status="cancelled")
            return AgentRun.model_validate(updated)
        except Exception as exc:
            logger.exception("Agent run failed")
            updated = await self.run_repository.update_run_status(
                run.id,
                "failed",
                error_message=str(exc),
            )
            await self.tracer.emit_event(run.id, "run.failed", status="failed", error=str(exc))
            return AgentRun.model_validate(updated)
        finally:
            self.state_store.clear_task(run.id)
            await self.state_store.close(run.id)

    async def _execute_run(self, definition: AgentDefinition, run: AgentRun) -> Dict[str, Any]:
        available_tools = self.executor.registry.list_specs()
        planner_result = self.planner.plan(definition, run.input, available_tools)
        await self.run_repository.update_run_status(run.id, "running", plan=planner_result.model_dump(mode="json"))
        await self.tracer.emit_event(
            run.id,
            "plan.created",
            plan=planner_result.model_dump(mode="json"),
        )

        action = planner_result.action
        if action.type == "ask_user":
            step = await self.tracer.create_step(
                run.id,
                kind="ask_user",
                title=action.title,
                status="completed",
                input_payload=run.input,
                metadata={"question": action.question},
            )
            await self.run_repository.update_step(
                step["id"],
                status="completed",
                output_payload={"question": action.question},
            )
            await self.tracer.emit_event(
                run.id,
                "step.completed",
                step_id=step["id"],
                kind="ask_user",
                question=action.question,
            )
            return {
                "status": "waiting_user",
                "plan": planner_result.model_dump(mode="json"),
                "final_output": action.question,
            }

        step = await self.tracer.create_step(
            run.id,
            kind=action.type,
            title=action.title,
            status="running",
            input_payload=run.input,
        )
        await self.tracer.emit_event(
            run.id,
            "step.started",
            step_id=step["id"],
            step_index=step["step_index"],
            kind=action.type,
            title=action.title,
        )

        if self.state_store.is_cancelled(run.id):
            raise asyncio.CancelledError()

        if action.type == "tool_call":
            tool_call = await self.tool_call_repository.create_tool_call(
                run_id=run.id,
                step_id=step["id"],
                tool_name=action.tool_name or "",
                tool_kind="builtin",
                arguments=action.tool_arguments,
            )
            await self.tracer.emit_event(
                run.id,
                "tool.started",
                step_id=step["id"],
                tool_call_id=tool_call["id"],
                tool_name=action.tool_name,
                arguments=action.tool_arguments,
            )

            result = await self.executor.execute_tool(
                planner_result,
                tool_context=ToolContext(
                    run_id=run.id,
                    tenant_id=run.tenant_id,
                    user_id=run.user_id,
                    agent_definition_id=run.agent_definition_id,
                    step_id=step["id"],
                ),
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
                tool_name=action.tool_name,
                result=result,
            )
            final_output = self.executor.build_final_answer(planner_result, result)
            await self.run_repository.update_step(
                step["id"],
                status="completed",
                output_payload={"tool_result": result, "final_output": final_output},
            )
            await self.tracer.emit_event(
                run.id,
                "step.completed",
                step_id=step["id"],
                kind=action.type,
                output={"tool_result": result},
            )
            return {
                "status": "completed",
                "plan": planner_result.model_dump(mode="json"),
                "final_output": final_output,
            }

        final_output = self.executor.build_final_answer(planner_result)
        await self.run_repository.update_step(
            step["id"],
            status="completed",
            output_payload={"final_output": final_output},
        )
        await self.tracer.emit_event(
            run.id,
            "step.completed",
            step_id=step["id"],
            kind=action.type,
            output={"final_output": final_output},
        )
        return {
            "status": "completed",
            "plan": planner_result.model_dump(mode="json"),
            "final_output": final_output,
        }
