# -*- coding: utf-8 -*-
"""[STORY-GATE P2] API 라우터 — main.py에는 include_router 한 줄만 배선.

게이트 OFF = 쓰기 0: POST(승인)는 게이트 OFF에서 무조건 403, 서비스 진입 자체를 막는다.
GET은 읽기 전용이라 게이트와 무관 (테이블 부재 시 '승인 없음'으로 정직하게 답한다).
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import gate
from .service import StoryGateError, approve, history, reopen_review, story_state

router = APIRouter()


@router.get("/story/gate")
async def get_gate():
    return {"enabled": gate.is_enabled(), "gate": gate.GATE_ENV}


@router.get("/story/{program_id}")
async def get_story_state(program_id: str):
    try:
        st = story_state(program_id)
    except StoryGateError as e:
        return JSONResponse(status_code=e.http_status,
                            content={"ok": False, "error": e.code, "message": e.message, **e.extra})
    return {"ok": True, "program_id": program_id, "gate_enabled": gate.is_enabled(), **st}


@router.post("/story/{program_id}/approve")
async def post_approve(program_id: str, payload: dict = None):
    if not gate.is_enabled():
        # 쓰기 0 보장 — 게이트 OFF에서는 승인 자체가 존재하지 않는다
        return JSONResponse(status_code=403,
                            content={"ok": False, "error": "CCUT_STORY_GATE_OFF"})
    body = payload or {}
    try:
        return approve(
            program_id,
            sequence_hash=body.get("sequence_hash"),
            actor=body.get("actor", "user"),
            running_ms=body.get("running_ms"),
            note=body.get("note"),
        )
    except StoryGateError as e:
        return JSONResponse(status_code=e.http_status,
                            content={"ok": False, "error": e.code, "message": e.message, **e.extra})


@router.post("/story/{program_id}/reopen")
async def post_reopen(program_id: str):
    try:
        return reopen_review(program_id)
    except StoryGateError as e:
        return JSONResponse(status_code=e.http_status,
                            content={"ok": False, "error": e.code, "message": e.message, **e.extra})


@router.get("/story/{program_id}/history")
async def get_history(program_id: str):
    return {"ok": True, "program_id": program_id, "approvals": history(program_id)}
