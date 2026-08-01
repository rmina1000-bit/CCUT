"""[FID-CENSUS] 조각 참조 무결성 상시 점검 — 2026-08-01 전수 조사의 **실행 가능한 형태**.

왜 스크립트인가:
  2026-08-01 에 에이전트 10명이 40분 걸려 이 표를 만들었다. 그 결과를 문서로만 남기면
  다음 방은 숫자가 낡았는지 알 수 없어 **조사를 처음부터 다시 한다.**
  그리고 그건 이 방이 하루 종일 잡은 병(저장만 하고 읽지 않는 것)을 문서로 반복하는 것이다.
  그래서 '읽는 코드'를 같이 남긴다. 조사하지 말고 **재실행**할 것.

무엇을 재는가:
  저장된 fragment_id 가 현행 semantic_fragments 에 실제로 있는가.
  '있다'의 기준은 dict 유무가 아니라 **조각 실재**다 — 저장된 제안 sequence 는 죽은 조각의
  낡은 dict 를 그대로 들고 있어서, dict 로 세면 멀쩡해 보인다(2026-08-01 실측 함정).

기준(바꾸지 말 것 — 바꾸면 과거 수치와 대조가 깨진다):
  distinct fid · 컬럼/키 단위 · 무정규화.
  (a) 삭제 프로그램(programs.deleted_at) 소속 · (b) VF 계열 구형 id ·
  (c) 분할 접미사(_c/_M/_R/+) 파생 id 는 **따로 세어 '끊김'에서 뺀다.**
  기준 없이 세면 3.7배 과대계상이 난다(2026-08-01: '고아 502' -> 실제 전멸 136).
  _P### 는 정상 시간분절 id 이므로 파생으로 세지 않는다.

read-only. DB 를 쓰지 않는다.

사용:
  python scripts/fid_integrity_census.py
  python scripts/fid_integrity_census.py --db <경로>   (백업 스냅샷 대조용)
  python scripts/fid_integrity_census.py --json        (기계 판독용)
"""
import argparse
import json
import os
import re
import sqlite3
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

FID_RE = re.compile(r"\b(?:SF_[0-9A-Za-z]+_SRC_[0-9A-Za-z]+(?:_P\d+)?|VF\d+_SRC_[0-9A-Za-z]+)\b")
VF_RE = re.compile(r"^VF\d+_")
DERIVED_RE = re.compile(r"(_c\d+|_M|_R|\+)")

# 2026-08-01 전수 조사가 확정한 저장처. (표, 컬럼, 좌표 병기 여부, 비고)
#   좌표 병기 = 같은 행/객체에 source_id + 시각이 함께 저장되는가.
COLUMNS = [
    ("programs",             "ui_state",            False, "story.fids 등 9경로. story.fidAnchors 는 좌표 있음"),
    ("story_approval",       "fragment_ids",        False, "★좌표 없음 — 복구 재료 자체가 없다"),
    ("proposals",            "sequence",            True,  "source_id+start/end 보유"),
    ("project_timeline",     "payload",             True,  "resolved_aliases 는 좌표 보유, key_fragments 는 없음"),
    ("fragment_edit_state",  "parent_fragment_id",  True,  "행 자체가 anchor_ms 앵커 — 세대 교체에 면역"),
    ("edit_overlay",         "fragment_id",         True,  "쓰기 폐쇄(LAB-45)"),
    ("export_input",         "clips",               True,  "좌표 일부 불일치(미확정)"),
    ("archive_result_sets",  "result_ids",          False, "★좌표 없음. 카드가 조용히 사라짐"),
    ("person_faces",         "fragment_id",         False, "★source_id 조차 없음"),
    ("fragment_places",      "fragment_id",         False, "source_id 만"),
    ("fragment_visual_marks","fragment_id",         False, "source_id 만"),
    ("fragment_vault",       "fragment_id",         True,  "anchor_hash+start_ds/end_ds. _upsert 가 fid 를 신세대로 UPDATE"),
    ("fragment_index",       "fragment_id",         True,  "소스 단위 purge 라 끊김 0 유지"),
    ("user_edit_decisions",  "selected_fragments",  False, "읽는 코드 0건"),
    ("preference_pairs",     "winner_sequence",     True,  "읽는 코드 0건"),
    ("mirror_ledger",        "fragment_id",         False, ""),
]


def _table_exists(con, t):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def _cols(con, t):
    return {r[1] for r in con.execute(f"pragma table_info({t})")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"[STOP] DB 없음: {args.db}")
        return 1
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    alive = {r[0] for r in con.execute("SELECT fragment_id FROM semantic_fragments")}
    deleted_progs = {r[0] for r in con.execute(
        "SELECT program_id FROM programs WHERE deleted_at IS NOT NULL")} \
        if _table_exists(con, "programs") and "deleted_at" in _cols(con, "programs") else set()

    rows = []
    for table, col, has_coords, note in COLUMNS:
        if not _table_exists(con, table) or col not in _cols(con, table):
            rows.append({"table": table, "col": col, "coords": has_coords,
                         "stored": None, "broken": None, "note": "표/컬럼 없음"})
            continue
        prog_col = "program_id" if "program_id" in _cols(con, table) else None
        sel = f"SELECT {col}" + (f", {prog_col}" if prog_col else "") + f" FROM {table}"
        stored, broken, in_deleted, vf, derived = set(), set(), set(), set(), set()
        for r in con.execute(sel):
            raw = r[col]
            if raw is None:
                continue
            prog = r[prog_col] if prog_col else None
            for fid in set(FID_RE.findall(str(raw))):
                stored.add(fid)
                if fid in alive:
                    continue
                if VF_RE.match(fid):
                    vf.add(fid); continue
                if DERIVED_RE.search(fid):
                    derived.add(fid); continue
                if prog and prog in deleted_progs:
                    in_deleted.add(fid); continue
                broken.add(fid)
        rows.append({"table": table, "col": col, "coords": has_coords,
                     "stored": len(stored), "broken": len(broken),
                     "deleted_scope": len(in_deleted), "vf": len(vf),
                     "derived": len(derived), "note": note})

    total_stored = sum(r["stored"] or 0 for r in rows)
    total_broken = sum(r["broken"] or 0 for r in rows)
    con.close()

    if args.json:
        print(json.dumps({"db": args.db, "rows": rows,
                          "total_stored": total_stored, "total_broken": total_broken},
                         ensure_ascii=False, indent=1))
        return 0

    print(f"[FID-CENSUS] {args.db}")
    print("기준: distinct fid · 컬럼 단위 · 삭제프로그램/VF/분할접미사는 '끊김'에서 제외해 따로 표기\n")
    print(f"{'저장처':22} {'컬럼/키':20} {'좌표':>4} {'저장':>6} {'끊김':>6} {'(삭제)':>7} {'(VF)':>5}  비고")
    print("-" * 118)
    for r in rows:
        if r["stored"] is None:
            print(f"{r['table']:22} {r['col']:20} {'':>4} {'-':>6} {'-':>6} {'-':>7} {'-':>5}  {r['note']}")
            continue
        mark = "O" if r["coords"] else "X"
        print(f"{r['table']:22} {r['col']:20} {mark:>4} {r['stored']:6} {r['broken']:6} "
              f"{r['deleted_scope']:7} {r['vf']:5}  {r['note'][:44]}")
    print("-" * 118)
    print(f"{'합계(중복 포함)':43} {total_stored:6} {total_broken:6}")
    print()
    print("읽는 법:")
    print("  좌표 X + 끊김 > 0  → 복구 재료가 없다. 저장 형식부터 바꿔야 한다.")
    print("  좌표 O + 끊김 > 0  → 재료는 있다. 읽는 코드가 없거나 안 닿는 것이다.")
    print("  fragment_index 끊김 > 0 → 소스 단위 purge 가 깨졌다는 뜻. 즉시 확인.")
    print()
    print("재연결이 실제로 있는 곳(2026-08-02 기준 3곳 — 저장처 13곳 대비):")
    print("  edit_contract/edit_state.py:128 rematch_anchor   (편집 상태)")
    print("  ccut_frontend/src/pages/Index.tsx STORY-ANCHOR   (원고, tol 3000ms)")
    print("  story_gate/proposal_axis.py _rematch_by_anchor   (제안, 728a4993 에서 추가)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
