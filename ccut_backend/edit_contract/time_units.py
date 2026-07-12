# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] 시간 단위 단일 변환 — v0.4 확정 공식.

전 계층(프론트 TS·백엔드 Py·마이그레이션) 공통. 이 함수 외의 초↔ms 변환 금지.
"""
import math


def to_ms(seconds: float) -> int:
    """to_ms(seconds) = floor(seconds × 1000 + 0.5). 전제: 시간 >= 0."""
    if seconds < 0:
        raise ValueError("time must be >= 0")
    return math.floor(seconds * 1000 + 0.5)


def ms_to_seconds(ms: int) -> float:
    """표시·Preview·Export 전달용: seconds = ms / 1000.0"""
    return ms / 1000.0
