# -*- coding: utf-8 -*-
"""[SAVE-SPINE 2-B] 버전 저장/조회 라우터 — main.py 에는 include_router 한 줄만.

실패는 조용하지 않다. 저장이 안 됐으면 안 됐다고 말하고, 무엇이 없었는지 함께 준다.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .service import SaveVersionError, get_version, list_versions, save_version

router = APIRouter()


def _err(e: SaveVersionError):
    return JSONResponse(
        status_code=e.http_status,
        content={"ok": False, "error": e.code, "message": e.message, **e.extra},
    )


@router.get("/story-version/{program_id}")
async def get_versions(program_id: str):
    """이 프로젝트에 저장된 버전 목록 (설계 ②·⑤)."""
    return list_versions(program_id)


@router.get("/story-version/detail/{version_id}")
async def get_one(version_id: int):
    """버전 하나 — 저장 시점의 순서·좌표·trim·숨김·전사 선택."""
    try:
        return get_version(version_id)
    except SaveVersionError as e:
        return _err(e)


@router.post("/story-version/{program_id}")
async def post_save(program_id: str, payload: dict = None):
    """저장. 전부 성공하거나, 아무것도 안 남고 실패를 말한다."""
    body = payload or {}
    try:
        return save_version(
            program_id,
            name=body.get("name"),
            fids=body.get("fids") or [],
            selected_span_ids=body.get("selected_span_ids"),
            rough_cut_input_hash=body.get("rough_cut_input_hash"),
            parent_version_id=body.get("parent_version_id"),
            display_ids=body.get("display_ids"),
            source_ids=body.get("source_ids"),
            actor=body.get("actor", "user"),
            note=body.get("note"),
        )
    except SaveVersionError as e:
        return _err(e)
