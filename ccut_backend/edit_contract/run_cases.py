# -*- coding: utf-8 -*-
"""공유 케이스 벡터 러너 (Python측) — 출력 형식은 TS 러너와 문자 단위 동일 (동등성 diff 대상).

사용: python run_cases.py [fixtures_path]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edit_contract.edit_state import compile_spans, ed_ids, normalize, rematch_anchor  # noqa: E402
from edit_contract.time_units import to_ms  # noqa: E402


def j(obj):
    """정렬 키·압축 JSON — TS stableStringify와 동일 규격."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main():
    fx_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "edit_contract_cases.json")
    with open(fx_path, encoding="utf-8") as f:
        fx = json.load(f)

    fails = 0

    for c in fx["to_ms_cases"]:
        got = to_ms(c["seconds"])
        ok = got == c["expect_ms"]
        if not ok:
            fails += 1
        print(f"[C12] to_ms({c['seconds']!r}) = {got} EXPECT {c['expect_ms']} {'PASS' if ok else 'FAIL'}")

    for c in fx["normalize_cases"]:
        cid = c["id"]
        canonical, receipt = normalize(c["input"])
        spans = compile_spans(canonical)
        ids = ed_ids(c["edit_state_id"], spans)
        out = {"canonical": {**canonical, "excluded_ranges": canonical["excluded_ranges"]},
               "receipt": receipt, "spans": spans, "ed_ids": ids}
        exp = {"canonical": c["expect"]["canonical"], "receipt": c["expect"]["receipt"],
               "spans": c["expect"]["spans"], "ed_ids": c["expect"]["ed_ids"]}
        ok = j(out) == j(exp)
        if not ok:
            fails += 1
        print(f"[{cid}] INPUT{{{j(c['input'])}}}")
        print(f"[{cid}] OUTPUT{{{j(out)}}}")
        if not ok:
            print(f"[{cid}] EXPECT{{{j(exp)}}}")
        print(f"[{cid}] {'PASS' if ok else 'FAIL'}")

    for c in fx["rematch_cases"]:
        cid = c["id"]
        anchor = list(c["anchor"])
        idx = rematch_anchor(anchor, c["candidates"], c["tol_ms"])
        out = {"anchor_after": anchor, "matched_index": idx}
        ok = idx == c["expect_index"] and anchor == c["anchor"]
        if not ok:
            fails += 1
        print(f"[{cid}] INPUT{{{j({'anchor': c['anchor'], 'candidates': c['candidates'], 'tol_ms': c['tol_ms']})}}}")
        print(f"[{cid}] OUTPUT{{{j(out)}}}")
        print(f"[{cid}] {'PASS' if ok else 'FAIL'}")

    print(f"[SUMMARY] fails={fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
