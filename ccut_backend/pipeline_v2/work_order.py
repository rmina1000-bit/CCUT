# -*- coding: utf-8 -*-
"""[V2-α] WorkOrderV2 — 사용자 말의 불변 보존 계약.

원칙(헌장 §원문불변): raw_user_text는 어떤 단계도 수정·축약·번역하지 않는다.
해석 불가 어구는 버리지 않고 unresolved_terms로 남긴다.
"""
import uuid
from dataclasses import dataclass, field, asdict


@dataclass
class Selector:
    phrase: str                 # 사용자 원문 그대로의 어구
    mode: str                   # "keep" | "exclude"
    strictness: str = "normal"  # "normal" | "hard" (hard는 조립 단계 결정론 거부권)
    source_span: tuple = None   # raw_user_text 내 (start, end), 못 찾으면 None


@dataclass
class WorkOrderV2:
    request_id: str
    raw_user_text: str          # 불변 보존 — 절대 수정 금지
    action: str                 # "select" | "story" | "count_only" | "unknown"
    selectors: list = field(default_factory=list)   # [Selector]
    count: int = None
    target_duration_sec: float = None
    project_id: str = None
    source_ids: list = field(default_factory=list)
    user_facts: list = field(default_factory=list)        # α: 빈 배열 유지
    user_preferences: list = field(default_factory=list)  # α: 빈 배열 유지
    corrections: list = field(default_factory=list)       # α: 빈 배열 유지
    unresolved_terms: list = field(default_factory=list)  # 버리지 않은 미해석 어구

    def to_dict(self):
        d = asdict(self)
        return d


def new_request_id():
    return "REQ_" + uuid.uuid4().hex[:12].upper()
