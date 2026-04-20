from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ai_runtime.core.dependencies import get_current_tenant_id

from .agents import get_agent_runtime

router = APIRouter(prefix="/api/v1/runtime/mcp", tags=["runtime-mcp"])


@router.post("/servers/{server_id}/test")
async def test_mcp_server(
    server_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    runtime = get_agent_runtime()
    try:
        return await runtime.test_mcp_server(tenant_id=tenant_id, server_id=server_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/servers/{server_id}/refresh-tools")
async def refresh_mcp_server_tools(
    server_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    runtime = get_agent_runtime()
    try:
        tools = await runtime.refresh_mcp_server_tools(tenant_id=tenant_id, server_id=server_id)
        return {"tools": tools, "total": len(tools)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
