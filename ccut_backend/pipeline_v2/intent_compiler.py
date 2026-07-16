# -*- coding: utf-8 -*-
"""[V2-α] IntentCompiler — 원문 → WorkOrderV2.

핵심 규율:
- 파서 = 본선 C1 hub.parse_compound_intent(결정론 함수) import 호출. 재구현 금지.
- LLM 추론 호출 0회 (헌장 §α-LLM-0).
- 원문 불변: selector.phrase는 원문 부분 문자열, source_span으로 위치 증빙.
- 해석 실패 어구는 unresolved_terms — 버리지 않는다.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from engine.hub import parse_compound_intent  # C1 결정론 파서 (LLM 아님)

from pipeline_v2.work_order import Selector, WorkOrderV2, new_request_id

_STORY_MARKS = ("스토리", "이야기", "주제로")


def _span(text, phrase):
    i = text.find(phrase)
    return (i, i + len(phrase)) if i >= 0 else None


def compile_order(raw_text, project_id=None, source_ids=None,
                  target_duration_sec=None):
    """원문 → WorkOrderV2. 결정론·무LLM."""
    raw = raw_text or ""
    parsed = parse_compound_intent(raw)

    selectors = []
    for term in parsed["keep_terms"]:
        selectors.append(Selector(phrase=term, mode="keep", source_span=_span(raw, term)))
    for term in parsed["exclude_terms"]:
        selectors.append(Selector(phrase=term, mode="exclude", source_span=_span(raw, term)))

    if any(m in raw for m in _STORY_MARKS):
        action = "story"
    elif selectors:
        action = "select"
    elif parsed["count"] is not None:
        action = "count_only"
    else:
        action = "unknown"

    unresolved = []
    if not parsed["found"] and raw.strip():
        unresolved.append(raw.strip())

    return WorkOrderV2(
        request_id=new_request_id(),
        raw_user_text=raw,           # 불변 보존
        action=action,
        selectors=selectors,
        count=parsed["count"],
        target_duration_sec=target_duration_sec,
        project_id=project_id,
        source_ids=list(source_ids or []),
        unresolved_terms=unresolved,
    )
