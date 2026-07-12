# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0 B2-5] shadow 비교 — 구 경로(edit_overlay SPLIT/TRIM) ↔ 신 컴파일 좌표 대조.

Cutover 2단계 도구: 게이트 OFF 상태에서 구 경로가 저장한 결과와 신 계약 컴파일 출력의
ms diff가 0인지 전수 대조한다. 실행은 Cutover 시 (지금은 격리 DB 시연만).

방법: edit_overlay를 (source_id, root) 그룹으로 묶어
  - SPLIT 그룹: 구 행들의 [start,end]×1000(ms) = 기대 span 집합.
    신 상태 재구성: trim=[첫 span 시작, 마지막 span 끝], excluded=span 사이 간극 → compile → 대조.
  - TRIM 단건: trim=[s,e] → compile 1 span → 대조.
사용: python shadow_compare.py --db <절대경로>  (읽기 전용 — mode=ro)
"""
import argparse
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edit_contract.edit_state import compile_spans, normalize  # noqa: E402
from edit_contract.time_units import to_ms  # noqa: E402


def run(db_path):
    con = sqlite3.connect(f"file:{db_path.replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT overlay_id, source_id, fragment_id, effective_start_sec, effective_end_sec,"
        " excluded, edit_type, root_fragment_id FROM edit_overlay ORDER BY source_id, fragment_id"
    ).fetchall()
    groups = {}
    for r in rows:
        key = (r["source_id"], r["root_fragment_id"] or r["fragment_id"], r["edit_type"])
        groups.setdefault(key, []).append(r)

    total = ok = 0
    for (sid, root, etype), members in sorted(groups.items()):
        spans_old = sorted(
            [to_ms(m["effective_start_sec"]), to_ms(m["effective_end_sec"])] for m in members
        )
        trim = [spans_old[0][0], spans_old[-1][1]]
        excluded = [[spans_old[i][1], spans_old[i + 1][0]] for i in range(len(spans_old) - 1)]
        canonical, receipt = normalize({
            "anchor_start_ms": trim[0], "anchor_end_ms": trim[1],
            "trim_start_ms": trim[0], "trim_end_ms": trim[1],
            "excluded_ranges": excluded, "removed": False,
        })
        spans_new = compile_spans(canonical)
        match = spans_new == spans_old
        total += 1
        ok += int(match)
        print(f"[{'PASS' if match else 'FAIL'}] {sid} root={root} type={etype} n={len(members)}")
        print(f"    구(edit_overlay ms) = {spans_old}")
        print(f"    신(compile ms)      = {spans_new}")
        if receipt:
            print(f"    receipt = {receipt}")
    print(f"[SHADOW SUMMARY] groups={total} match={ok} mismatch={total - ok}")
    con.close()
    return 0 if ok == total else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    sys.exit(run(ap.parse_args().db))
