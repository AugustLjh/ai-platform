from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from core.dependencies import get_current_tenant_id, get_current_user_id
from core.uploads import get_attachment_bundle_store

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.post("/bundles")
async def create_upload_bundle(
    files: list[UploadFile] = File(..., description="上传的文件列表"),
    paths: Optional[list[str]] = Form(default=None, description="与文件顺序对应的相对路径列表"),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    store = get_attachment_bundle_store()
    try:
        bundle = await store.create_bundle(
            tenant_id=tenant_id,
            user_id=user_id,
            files=files,
            relative_paths=paths,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return bundle
