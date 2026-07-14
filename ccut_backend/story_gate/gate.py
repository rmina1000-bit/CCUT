# -*- coding: utf-8 -*-
"""[STORY-GATE P2] 단일 게이트 — CCUT_STORY_GATE (기본 OFF).

OFF = 현행 동작과 바이트 동일. 승인 검사·403 가드·story_state 필드 전부 비활성이며
DB 쓰기 0 (story_approval 테이블조차 만들지 않는다).
"""
import os

GATE_ENV = "CCUT_STORY_GATE"


def is_enabled() -> bool:
    """환경변수 CCUT_STORY_GATE=1 일 때만 ON. 그 외 전부 OFF."""
    return os.getenv(GATE_ENV, "0") == "1"
