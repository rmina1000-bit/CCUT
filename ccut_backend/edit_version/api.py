# -*- coding: utf-8 -*-
"""[EDIT-SAVE-1] 편집 버전 저장/조회 라우터 — main.py 에는 include_router 한 줄만.

실패 응답 계약: { ok:false, error_code, message, retryable, data:null }.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .service import (
    EditSaveError, get_edit_version, list_edit_versions, save_edit_version,
)

router = APIRouter()


def _err(e: EditSaveError):
    return JSONResponse(
        status_code=e.http_status,
        content={"ok": False, "error_code": e.code, "message": e.message,
                 "retryable": e.retryable, "data": None, **e.extra},
    )


@router.get("/edit-version/{program_id}")
async def get_versions(program_id: str):
    """이 프로젝트에 저장된 편집 버전 목록 (0건이면 versions=[])."""
    return list_edit_versions(program_id)


@router.get("/edit-version/detail/{version_id}")
async def get_one(version_id: int):
    """편집 버전 하나 — 저장 시점의 순서·좌표·trim·숨김."""
    try:
        return get_edit_version(version_id)
    except EditSaveError as e:
        return _err(e)


@router.post("/edit-version/{program_id}")
async def post_save(program_id: str, payload: dict = None):
    """저장. 전부 성공하거나, 아무것도 안 남고 실패를 말한다."""
    body = payload or {}
    try:
        return save_edit_version(
            program_id,
            name=body.get("name"),
            fids=body.get("fids"),
            items=body.get("items"),
            proposal_id=body.get("proposal_id"),
            parent_version_id=body.get("parent_version_id"),
            created_by=body.get("created_by", "user"),
        )
    except EditSaveError as e:
        return _err(e)
