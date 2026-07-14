# -*- coding: utf-8 -*-
"""[STORY-GATE P2] 단일 게이트 — CCUT_STORY_GATE (기본 ON).

CCUT_STORY_GATE=0/false/off/no면 OFF. 미설정은 ON.
"""
import os

GATE_ENV = "CCUT_STORY_GATE"


def is_enabled() -> bool:
    """환경변수 미설정 시 ON. 명시적 0/false/off/no일 때만 OFF."""
    value = os.getenv(GATE_ENV)
    if value is None or value.strip() == "":
        return True
    return value.strip().lower() not in {"0", "false", "off", "no"}
