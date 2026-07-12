# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] API 라우터 — main.py에는 include_router 한 줄만 배선.

패치 6: 게이트 OFF = 쓰기 완전 0 — POST는 게이트 OFF에서 무조건 거부(어떤 DB 쓰기도 없음).
GET은 읽기 전용이라 게이트 무관 (운영 DB에 테이블 부재 시 빈 목록).
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import gate
from .service import EditStateError, list_edit_states, upsert_edit_state

router = APIRouter()


@router.get("/edit-state/gate")
async def get_gate():
    return {"enabled": gate.is_enabled(), "gate": gate.GATE_ENV}


@router.post("/edit-state")
async def post_edit_state(payload: dict):
    if not gate.is_enabled():
        # 쓰기 0 보장 — 서비스 계층 진입 자체를 차단
        return JSONResponse(status_code=403, content={"ok": False, "error": "EDIT_CONTRACT_V2_OFF"})
    try:
        return upsert_edit_state(payload or {})
    except EditStateError as e:
        return JSONResponse(status_code=e.http_status,
                            content={"ok": False, "error": e.code, "message": e.message, **e.extra})


@router.get("/edit-state/{program_id}")
async def get_edit_states(program_id: str):
    return {"ok": True, "program_id": program_id, "states": list_edit_states(program_id)}
