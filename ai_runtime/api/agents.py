from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ai_runtime.core.agent_runtime import AgentRuntime
from ai_runtime.core.agent_runtime.execution_modes import normalize_execution_mode
from ai_runtime.core.agent_runtime.models import (
    AgentRunEventListResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    AgentRunTreeResponse,
    AgentSubagentInvocationListResponse,
    RuntimeCreateRunRequest,
    RuntimeResumeRunRequest,
)
from ai_runtime.core.database import get_db_manager
from ai_runtime.core.dependencies import get_current_tenant_id, get_current_user_id

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime(get_db_manager().pool)
    return _runtime


@router.post("/runs", response_model=AgentRunSummaryResponse, status_code=201)
async def create_run(
    request: RuntimeCreateRunRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = get_agent_runtime()
    payload = request.model_copy(update={"tenant_id": tenant_id, "user_id": user_id or request.user_id})
    try:
        return await runtime.create_run(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tools")
async def list_tools(
    agent_definition_id: Optional[str] = Query(default=None),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = get_agent_runtime()
    agent_definition = None
    if agent_definition_id:
        agent_definition = await runtime.agent_repository.get_definition(agent_definition_id, tenant_id)
    execution_mode = normalize_execution_mode(
        agent_definition.get("config") if isinstance(agent_definition, dict) else None
    ).model_dump()
    tools = await runtime.list_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_definition_id=agent_definition_id,
    )
    return {"tools": tools, "total": len(tools), "execution_mode": execution_mode}


@router.get("/workspaces")
async def inspect_workspaces(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = get_agent_runtime()
    inspection = runtime.workspace_manager.inspect_workspaces()
    workspaces = [
        item
        for item in inspection.get("workspaces", [])
        if str(item.get("tenant_id") or "") == tenant_id
    ]
    return {
        **inspection,
        "tenant_id": tenant_id,
        "workspace_count": len(workspaces),
        "expired_count": sum(1 for item in workspaces if item.get("expired")),
        "quota_exceeded_count": sum(1 for item in workspaces if item.get("quota_exceeded")),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in workspaces),
        "total_file_count": sum(int(item.get("file_count") or 0) for item in workspaces),
        "workspaces": workspaces,
        "requested_by": user_id,
    }


@router.post("/workspaces/cleanup")
async def cleanup_workspaces(
    dry_run: bool = Query(default=True),
    confirmed: bool = Query(default=False),
    max_delete: int = Query(default=100, ge=1, le=1000),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    if not dry_run and not confirmed:
        raise HTTPException(status_code=400, detail="workspace cleanup requires confirmed=true when dry_run=false")
    runtime = get_agent_runtime()
    result = runtime.workspace_manager.cleanup_expired_workspaces(
        dry_run=dry_run,
        max_delete=max_delete,
        tenant_id=tenant_id,
    )
    selected = list(result.get("deleted", []))
    failed = list(result.get("failed", []))
    return {
        **result,
        "tenant_id": tenant_id,
        "selected_count": len(selected),
        "deleted_count": sum(1 for item in selected if item.get("deleted")),
        "failed_count": len(failed),
        "deleted": selected,
        "failed": failed,
        "requested_by": user_id,
    }


@router.get("/runs", response_model=AgentRunListResponse)
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = get_agent_runtime()
    return await runtime.list_runs(tenant_id=tenant_id, user_id=user_id, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=AgentRunSummaryResponse)
async def get_run(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = get_agent_runtime()
    try:
        return await runtime.get_run(run_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/invocations", response_model=AgentSubagentInvocationListResponse)
async def get_run_invocations(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = get_agent_runtime()
    try:
        return await runtime.list_subagent_invocations(run_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/tree", response_model=AgentRunTreeResponse)
async def get_run_tree(
    run_id: str,
    max_depth: int = Query(default=4, ge=1, le=8),
    tenant_id: str = Depends(get_current_tenant_id),
):
    runtime = get_agent_runtime()
    try:
        return await runtime.get_run_tree(run_id, tenant_id, max_depth=max_depth)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    stream: bool = Query(default=False),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
    tenant_id: str = Depends(get_current_tenant_id),
):
    runtime = get_agent_runtime()
    if not stream:
        try:
            return await runtime.list_events(run_id, tenant_id, after_sequence=after_sequence, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_generator():
        try:
            async for event in runtime.stream_events(run_id, tenant_id, after_sequence=after_sequence):
                payload = event.model_dump(mode="json")
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as exc:
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/cancel", response_model=AgentRunSummaryResponse)
async def cancel_run(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = get_agent_runtime()
    try:
        return await runtime.cancel_run(run_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/resume", response_model=AgentRunSummaryResponse)
async def resume_run(
    run_id: str,
    request: RuntimeResumeRunRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    runtime = get_agent_runtime()
    try:
        return await runtime.resume_run(run_id, tenant_id, input_patch=request.input_patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
