from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from ai_runtime.core.agent_runtime import AgentRuntime
from ai_runtime.core.agent_runtime.audit_view import evaluate_redaction_rules
from ai_runtime.core.agent_runtime.execution_modes import normalize_execution_mode
from ai_runtime.core.agent_runtime.models import (
    AgentRunEventListResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    AgentRunTreeResponse,
    AgentSubagentInvocationListResponse,
    RuntimeArtifactReviewDecisionRequest,
    RuntimeCreateRunRequest,
    RuntimeResumeRunRequest,
    RuntimeWorkspaceWritebackRequest,
)
from ai_runtime.core.agent_runtime.subagents.quality import evaluate_subagent_quality_suite
from ai_runtime.core.database import get_db_manager
from ai_runtime.core.dependencies import get_current_tenant_id, get_current_user_id

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime(get_db_manager().pool)
    return _runtime


async def get_started_agent_runtime() -> AgentRuntime:
    runtime = get_agent_runtime()
    await runtime.start()
    return runtime


async def get_current_viewer_role(
    x_user_role: Optional[str] = Header(default=None),
) -> str:
    role = str(x_user_role or "user").strip().lower()
    if role not in {"anonymous", "user", "operator", "admin", "system"}:
        return "user"
    return role


def _require_admin_or_operator(role: str) -> None:
    if role not in {"operator", "admin", "system"}:
        raise HTTPException(status_code=403, detail="operator or admin role is required")


@router.post("/runs", response_model=AgentRunSummaryResponse, status_code=201)
async def create_run(
    request: RuntimeCreateRunRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = await get_started_agent_runtime()
    payload = request.model_copy(update={"tenant_id": tenant_id, "user_id": user_id or request.user_id})
    try:
        return await runtime.create_run(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{agent_definition_id}/runs", response_model=AgentRunSummaryResponse, status_code=201)
async def create_run_for_agent(
    agent_definition_id: str,
    request: RuntimeCreateRunRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = await get_started_agent_runtime()
    payload = request.model_copy(
        update={
            "agent_definition_id": agent_definition_id,
            "tenant_id": tenant_id,
            "user_id": user_id or request.user_id,
        }
    )
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
    runtime = await get_started_agent_runtime()
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


@router.get("/workspace-sources")
async def list_workspace_sources(
    max_entries: int = Query(default=200, ge=1, le=1000),
    max_depth: int = Query(default=2, ge=0, le=6),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = await get_started_agent_runtime()
    return await runtime.list_workspace_sources(
        tenant_id=tenant_id,
        user_id=user_id,
        max_entries=max_entries,
        max_depth=max_depth,
    )


@router.get("/runtime-status")
async def get_runtime_status(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    del tenant_id, user_id
    runtime = await get_started_agent_runtime()
    return runtime.runtime_status()


@router.get("/ops-status")
async def get_ops_status(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    return runtime.ops_status()


@router.post("/ops-status/evaluate")
async def evaluate_ops_status(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    return await runtime.evaluate_runtime_health()


@router.get("/ops-status/metrics")
async def get_ops_prometheus_metrics(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    return Response(
        content=runtime.ops_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/ops-status/grafana-dashboard")
async def get_ops_grafana_dashboard(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    return runtime.ops_grafana_dashboard()


@router.post("/ops-status/alerts/{rule_name}/acknowledge")
async def acknowledge_runtime_alert(
    rule_name: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    acknowledged = runtime.alert_manager.acknowledge(rule_name)
    if not acknowledged:
        raise HTTPException(status_code=404, detail="active alert not found")
    return runtime.alert_manager.snapshot()


@router.post("/ops-status/alerts/{rule_name}/resolve")
async def resolve_runtime_alert(
    rule_name: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    runtime = await get_started_agent_runtime()
    resolved = runtime.alert_manager.resolve(rule_name)
    if not resolved:
        raise HTTPException(status_code=404, detail="active alert not found")
    return runtime.alert_manager.snapshot()


@router.post("/audit/redaction/evaluate")
async def evaluate_audit_redaction_rules(
    test_cases: list[dict],
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    return evaluate_redaction_rules(test_cases)


@router.post("/subagents/quality/evaluate")
async def evaluate_subagent_quality_rules(
    test_cases: list[dict],
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    viewer_role: str = Depends(get_current_viewer_role),
):
    del tenant_id, user_id
    _require_admin_or_operator(viewer_role)
    return evaluate_subagent_quality_suite(test_cases)


@router.get("/workspaces")
async def inspect_workspaces(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = await get_started_agent_runtime()
    inspection = runtime.workspace_manager.inspect_workspaces()
    workspaces = [
        item
        for item in inspection.get("workspaces", [])
        if str(item.get("tenant_id") or "") == tenant_id
    ]
    lock_summary = inspection.get("lock_summary") if isinstance(inspection.get("lock_summary"), dict) else {}
    tenant_lock_summary = {
        **lock_summary,
        "locks": [
            item
            for item in lock_summary.get("locks", [])
            if str(item.get("tenant_id") or "") == tenant_id
        ],
    }
    tenant_lock_summary["lock_count"] = len(tenant_lock_summary["locks"])
    tenant_lock_summary["active_lock_count"] = sum(1 for item in tenant_lock_summary["locks"] if not item.get("stale"))
    tenant_lock_summary["stale_lock_count"] = sum(1 for item in tenant_lock_summary["locks"] if item.get("stale"))
    tenant_lock_summary["orphan_lock_count"] = sum(1 for item in tenant_lock_summary["locks"] if item.get("orphan"))
    health = runtime.workspace_manager.build_workspace_health(
        {
            **inspection,
            "workspace_count": len(workspaces),
            "expired_count": sum(1 for item in workspaces if item.get("expired")),
            "quota_exceeded_count": sum(1 for item in workspaces if item.get("quota_exceeded")),
            "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in workspaces),
            "total_file_count": sum(int(item.get("file_count") or 0) for item in workspaces),
        },
        lock_summary=tenant_lock_summary,
    )
    return {
        **inspection,
        "tenant_id": tenant_id,
        "workspace_count": len(workspaces),
        "expired_count": sum(1 for item in workspaces if item.get("expired")),
        "quota_exceeded_count": sum(1 for item in workspaces if item.get("quota_exceeded")),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in workspaces),
        "total_file_count": sum(int(item.get("file_count") or 0) for item in workspaces),
        "workspaces": workspaces,
        "lock_summary": tenant_lock_summary,
        "health": health,
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
    runtime = await get_started_agent_runtime()
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


@router.post("/workspaces/locks/cleanup")
async def cleanup_workspace_locks(
    dry_run: bool = Query(default=True),
    confirmed: bool = Query(default=False),
    max_delete: int = Query(default=100, ge=1, le=1000),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    if not dry_run and not confirmed:
        raise HTTPException(status_code=400, detail="workspace lock cleanup requires confirmed=true when dry_run=false")
    runtime = await get_started_agent_runtime()
    result = runtime.workspace_manager.cleanup_stale_locks(
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
    runtime = await get_started_agent_runtime()
    return await runtime.list_runs(tenant_id=tenant_id, user_id=user_id, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=AgentRunSummaryResponse)
async def get_run(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = await get_started_agent_runtime()
    try:
        return await runtime.get_run(run_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/invocations", response_model=AgentSubagentInvocationListResponse)
async def get_run_invocations(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = await get_started_agent_runtime()
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
    runtime = await get_started_agent_runtime()
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
    runtime = await get_started_agent_runtime()
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


@router.get("/runs/{run_id}/audit-view")
async def get_run_audit_view(
    run_id: str,
    viewer_role: str = Query(default="user"),
    include_events: bool = Query(default=True),
    include_tool_calls: bool = Query(default=True),
    event_limit: int = Query(default=500, ge=1, le=1000),
    tenant_id: str = Depends(get_current_tenant_id),
    current_role: str = Depends(get_current_viewer_role),
):
    allowed_roles = {"anonymous", "user", "operator", "admin", "system"}
    requested_role = viewer_role if viewer_role in allowed_roles else "user"
    if current_role not in {"operator", "admin", "system"} and requested_role not in {"anonymous", "user"}:
        raise HTTPException(status_code=403, detail="operator or admin role is required for elevated audit views")
    runtime = await get_started_agent_runtime()
    try:
        return await runtime.build_run_audit_view(
            run_id,
            tenant_id,
            viewer_role=requested_role,
            include_events=include_events,
            include_tool_calls=include_tool_calls,
            event_limit=event_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=AgentRunSummaryResponse)
async def cancel_run(run_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    runtime = await get_started_agent_runtime()
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
    runtime = await get_started_agent_runtime()
    try:
        return await runtime.resume_run(run_id, tenant_id, input_patch=request.input_patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/artifacts/{artifact_id}/review", response_model=AgentRunSummaryResponse)
async def review_run_artifact(
    run_id: str,
    artifact_id: str,
    request: RuntimeArtifactReviewDecisionRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    runtime = await get_started_agent_runtime()
    try:
        return await runtime.review_artifact(
            run_id=run_id,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            reviewer_id=user_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/workspace/writeback", response_model=AgentRunSummaryResponse)
async def writeback_run_workspace(
    run_id: str,
    request: RuntimeWorkspaceWritebackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    if not request.dry_run and not request.confirmed:
        raise HTTPException(status_code=400, detail="workspace writeback requires confirmed=true when dry_run=false")
    runtime = await get_started_agent_runtime()
    try:
        return await runtime.writeback_run_workspace(
            run_id=run_id,
            tenant_id=tenant_id,
            reviewer_id=user_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
