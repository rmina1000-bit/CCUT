# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] 단일 게이트 — EDIT_CONTRACT_V2 (기본 ON).

패치 6: OFF = 쓰기 완전 0 (timeline_item_id 영속·fragment_edit_state 쓰기·vault_events
신규 편집 이벤트·resolver 결과 변경·PBE 복원 방식 변경 일체 금지).
분기 지점은 v0.4 §8 소비 지점 5곳 + API 쓰기 라우트뿐.
"""
import os

GATE_ENV = "EDIT_CONTRACT_V2"


def is_enabled() -> bool:
    """환경변수 미설정은 ON. 명시적 0/false/off/no일 때만 OFF."""
    value = os.getenv(GATE_ENV)
    if value is None or value.strip() == "":
        return True
    return value.strip().lower() not in {"0", "false", "off", "no"}
