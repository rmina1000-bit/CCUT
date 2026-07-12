# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] canonical 정규화 + 컴파일러 — 순수 함수 (I/O·상태·임계값 없음).

TS 대응 구현: ccut_frontend/src/utils/editContract.ts — fixtures JSON으로 동등성 증명.

정규화 규칙 (v0.4 §"canonical form" — v0.2 §4 + 코워크 보완 2건):
  1) excluded_ranges 정렬
  2) 겹치거나 맞닿은 구간 → 합집합 병합 (오류 아님)
  3) trim 앞·뒤 경계에 닿는 제외 → trim 경계 이동으로 흡수
  4) 생존 창 전체가 제거되면 → removed=true 로 변환
  5) 최종 excluded_ranges = trim 내부의 중간 구간만
  + 창 완전 밖의 제외 → 무시(no-op) / 창 경계에 걸친 제외 → 창으로 절단 후 1~5 적용
  정규화 결과가 입력과 다르면 Receipt에 표시 (조용한 숨김 금지).

계약 미규정 사항의 결정론 처리 (본 구현이 고정 — V-gate 확인 대상):
  - removed 전환 시 trim은 입력값 보존, excluded=[] (표현 유일성: removed와 전체제외 공존 불가)
  - trim_start >= trim_end 입력 → removed=true 전환 (empty_trim_to_removed)
  - s >= e 인 제외 구간 → 무시 + Receipt (ignored_invalid)
"""

SCHEMA_VERSION = 1

LAST_ORIGIN_VALUES = ("PBE", "TEXT_EDITOR", "NATURAL_LANGUAGE", "MIGRATION", "SYSTEM", "INHERIT")


def _canonical(anchor, trim, excluded, removed_flag):
    return {
        "anchor_start_ms": anchor[0],
        "anchor_end_ms": anchor[1],
        "trim_start_ms": trim[0],
        "trim_end_ms": trim[1],
        "excluded_ranges": excluded,
        "removed": removed_flag,
    }


def normalize(state):
    """입력 편집 상태 → (canonical 상태, receipt 목록). anchor는 절대 불변."""
    receipt = []
    anchor = [int(state["anchor_start_ms"]), int(state["anchor_end_ms"])]
    trim_in = [int(state["trim_start_ms"]), int(state["trim_end_ms"])]
    excluded_in = [[int(r[0]), int(r[1])] for r in state.get("excluded_ranges", [])]
    removed = bool(state.get("removed", False))

    if removed:
        if excluded_in:
            receipt.append({"rule": "removed_input_clears_excluded"})
        return _canonical(anchor, trim_in, [], True), receipt

    ts, te = trim_in
    if ts >= te:
        receipt.append({"rule": "empty_trim_to_removed"})
        return _canonical(anchor, trim_in, [], True), receipt

    # 창 밖 무시 / 걸침 절단 / 무효 무시 (입력 순서대로 판정)
    kept = []
    for s, e in excluded_in:
        if s >= e:
            receipt.append({"rule": "ignored_invalid", "range": [s, e]})
            continue
        if e <= ts or s >= te:
            receipt.append({"rule": "ignored_outside", "range": [s, e]})
            continue
        cs, ce = max(s, ts), min(e, te)
        if [cs, ce] != [s, e]:
            receipt.append({"rule": "clamped", "from": [s, e], "to": [cs, ce]})
        kept.append([cs, ce])

    # 1) 정렬
    swept = sorted(kept)
    if swept != kept:
        receipt.append({"rule": "sorted"})

    # 2) 겹침·맞닿음 병합
    merged = []
    groups = []
    for r in swept:
        if merged and r[0] <= merged[-1][1]:
            groups[-1].append([r[0], r[1]])
            if r[1] > merged[-1][1]:
                merged[-1][1] = r[1]
        else:
            merged.append([r[0], r[1]])
            groups.append([[r[0], r[1]]])
    for g, m in zip(groups, merged):
        if len(g) > 1:
            receipt.append({"rule": "merged", "from": g, "to": [m[0], m[1]]})

    # 4) 전체 제거 → removed (병합 후 전체 덮는 구간은 정확히 [ts,te] 단일 구간)
    if len(merged) == 1 and merged[0][0] == ts and merged[0][1] == te:
        receipt.append({"rule": "fully_excluded_to_removed"})
        return _canonical(anchor, trim_in, [], True), receipt

    # 3) 경계 흡수 (병합 후 구간들은 서로 disjoint·비접촉 — 각 측 1회로 충분)
    if merged and merged[0][0] == ts:
        r = merged.pop(0)
        ts = r[1]
        receipt.append({"rule": "absorbed_start", "range": r, "trim_start_ms": ts})
    if merged and merged[-1][1] == te:
        r = merged.pop()
        te = r[0]
        receipt.append({"rule": "absorbed_end", "range": r, "trim_end_ms": te})

    # 5) 잔여 = 순내부 구간
    return _canonical(anchor, [ts, te], merged, False), receipt


def compile_spans(canonical_state):
    """compile(state) → removed ? [] : subtract(trim, excluded). 순수 함수."""
    if canonical_state["removed"]:
        return []
    spans = []
    cur = canonical_state["trim_start_ms"]
    for s, e in canonical_state["excluded_ranges"]:
        if s > cur:
            spans.append([cur, s])
        cur = e
    if cur < canonical_state["trim_end_ms"]:
        spans.append([cur, canonical_state["trim_end_ms"]])
    return spans


def ed_ids(edit_state_id, spans):
    """ed_id = "{edit_state_id}_k{순번}" (1-기점, 결정론). 저장하지 않는 계산 결과."""
    return [f"{edit_state_id}_k{i + 1}" for i in range(len(spans))]


def rematch_anchor(anchor, candidates, tol_ms=10):
    """재조각화 시 anchor(±tol_ms) 재매칭. anchor는 덮어쓰지 않는다 — 매칭 인덱스만 반환.

    candidates: [[start_ms, end_ms], ...] (호출자가 소스 순서로 정렬해 전달)
    반환: 첫 매칭 인덱스 또는 None.
    """
    a_s, a_e = anchor
    for i, (c_s, c_e) in enumerate(candidates):
        if abs(c_s - a_s) <= tol_ms and abs(c_e - a_e) <= tol_ms:
            return i
    return None
