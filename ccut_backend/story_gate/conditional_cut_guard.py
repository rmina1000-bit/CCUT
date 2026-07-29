"""[LAB-43 STEP 4] 조건부 기법 3종의 조건을 코드로 강제한다.

대상: sentence_boundary_cut / dead_air_removal / pause_compression
국장 승인 조건(editing_techniques.json authority.condition, LAB-17):
  "조각 가장자리 경계를 안쪽으로 당기는 것만 허용.
   조각이 분할되거나 조각 수가 변하면 즉시 중지.
   중간 삭제는 사용자 기능(PBE 대사 에디터) 소관."

이 모듈은 값을 바꾸지 않는다 — 제안된 경계 변경을 **검사만** 한다.
검사를 통과하지 못하면 그 조각의 변경을 버린다(원본 경계 유지). 조용한 통과 금지.

게이트: CCUT_TECHNIQUE_CONDITIONAL_CUT (기본 OFF — 신규 게이트 표준, LAB-43 국장 확정).
"""
import os

# 조건 위반 코드 — 로그·판정에 그대로 실린다
V_COUNT_CHANGED = "FRAGMENT_COUNT_CHANGED"
V_SPLIT = "FRAGMENT_SPLIT"
V_OUTWARD = "EDGE_MOVED_OUTWARD"
V_MIDDLE = "MIDDLE_DELETE"
V_INVERTED = "SPAN_INVERTED"
V_MISSING = "FRAGMENT_MISSING"


def enabled() -> bool:
    """신규 게이트 표준: 기본 OFF. 국장 PRODUCT PASS 후 ON 승격."""
    return os.getenv("CCUT_TECHNIQUE_CONDITIONAL_CUT", "0") in ("1", "true", "True", "ON")


def check_span_change(before, after):
    """조각 하나의 경계 변경이 조건을 지키는지. (ok, violations) 반환.

    before/after = (start_ms, end_ms) 정수. 안쪽으로 당기는 것만 허용:
      after.start >= before.start  AND  after.end <= before.end
    """
    v = []
    bs, be = int(before[0]), int(before[1])
    as_, ae = int(after[0]), int(after[1])
    if as_ >= ae:
        v.append({"code": V_INVERTED, "detail": f"after {as_}~{ae} 뒤집힘/영길이"})
    if as_ < bs:
        v.append({"code": V_OUTWARD,
                  "detail": f"start 가 밖으로 {bs}->{as_} ({bs - as_}ms 확장)"})
    if ae > be:
        v.append({"code": V_OUTWARD,
                  "detail": f"end 가 밖으로 {be}->{ae} ({ae - be}ms 확장)"})
    return (not v), v


def check_plan(before_spans, after_spans):
    """조각 집합 전체 계획을 검사한다.

    before_spans / after_spans = {fragment_id: [(start_ms, end_ms), ...]}
    한 조각이 2개 이상 span 을 갖게 되면 분할(중간 삭제)로 본다 — 즉시 중지.
    """
    violations = []
    if len(after_spans) != len(before_spans):
        violations.append({
            "fragment_id": None, "code": V_COUNT_CHANGED,
            "detail": f"조각 수 {len(before_spans)} -> {len(after_spans)}",
        })
    for fid, before in before_spans.items():
        after = after_spans.get(fid)
        if after is None:
            violations.append({"fragment_id": fid, "code": V_MISSING,
                               "detail": "계획에서 조각이 사라짐"})
            continue
        if len(after) > 1:
            violations.append({"fragment_id": fid, "code": V_SPLIT,
                               "detail": f"span {len(before)} -> {len(after)} 분할"})
            continue
        if len(before) != 1:
            violations.append({"fragment_id": fid, "code": V_MIDDLE,
                               "detail": f"원본이 이미 다중 span({len(before)}) — 대상 아님"})
            continue
        ok, vs = check_span_change(before[0], after[0])
        for x in vs:
            violations.append({"fragment_id": fid, **x})
    for fid in after_spans:
        if fid not in before_spans:
            violations.append({"fragment_id": fid, "code": V_COUNT_CHANGED,
                               "detail": "계획에 없던 조각이 생김"})
    return (not violations), violations


def apply_guarded(technique_id, before_spans, after_spans):
    """조건 검사를 통과한 변경만 돌려준다. 위반이면 원본 경계를 그대로 반환.

    반환: (spans, report). report 는 항상 로그로 남는다 — 조용한 통과·조용한 폐기 금지.
    """
    if not enabled():
        print(f"[COND-CUT] gate off (CCUT_TECHNIQUE_CONDITIONAL_CUT) "
              f"— {technique_id} 미적용", flush=True)
        return before_spans, {"technique": technique_id, "applied": False,
                              "reason": "gate_off", "violations": []}
    ok, violations = check_plan(before_spans, after_spans)
    if not ok:
        codes = sorted({v["code"] for v in violations})
        print(f"[COND-CUT][STOP] {technique_id} 조건 위반 — 변경 폐기, 원본 경계 유지. "
              f"위반={codes}", flush=True)
        for v in violations[:5]:
            print(f"[COND-CUT][VIOLATION] {v['code']} {v.get('fragment_id')}: "
                  f"{v['detail']}", flush=True)
        return before_spans, {"technique": technique_id, "applied": False,
                              "reason": "condition_violation", "violations": violations}
    moved = sum(1 for fid, b in before_spans.items()
                if after_spans[fid][0] != b[0])
    print(f"[COND-CUT][OK] {technique_id} 조건 통과 — 조각 {len(before_spans)}개 중 "
          f"{moved}개 경계 안쪽 당김", flush=True)
    return after_spans, {"technique": technique_id, "applied": True,
                         "moved": moved, "violations": []}
