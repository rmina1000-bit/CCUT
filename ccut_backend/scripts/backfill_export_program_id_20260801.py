"""[BACKFILL 2026-08-01] export_results 의 program_id 결손 2건 복구 (국장 승인).

무엇을 고치는가:
  2026-07-30 06:57 에 만들어진 export 2건에 program_id 가 비어 있어 아카이브 화면에서
  "다시 편집" 버튼이 뜨지 않았다(버튼 조건이 program_id 존재 여부).

왜 Adhara 라고 단정하는가 — 추측이 아니라 세 갈래 독립 근거가 한 곳을 가리킨다:
  ① proposal_id 에 박힌 값        PROP_A_5DED1A_proj_2b0b23b104b0
  ② proposals 테이블 독립 조회     그 proposal 의 program_id = proj_2b0b23b104b0
  ③ 같은 export_input_id 형제 행   RND_R291C69D(07-29)는 program_id 가 정상이고 Adhara
  ③이 결정적이다. 같은 입력(EXP_48AE36_None)에서 나온 export 3건 중 07-29 것만
  정상이고 07-30 06:57 두 건이 13초 간격으로 비어 있다. 파일 크기(24,062,533 /
  24,062,793)와 길이(49.714s)도 거의 같다 — 같은 것을 두 번 내보낸 것이다.
  규칙 신뢰성: proposal_id 가 있는 정상 행 6건 전부 규칙과 일치(6/6).

무엇을 고치지 않는가:
  source_id / codec / display_name 도 비어 있지만 **역추적 근거가 없다**.
  모르는 것을 채우면 원장이 거짓말한다 — UNKNOWN 으로 남긴다.

절벽:
  ① UPDATE 대상은 render id 2개를 **명시 지정**한다. `WHERE program_id IS NULL` 같은
     조건은 쓰지 않는다 — 나중에 다른 결손이 생기면 함께 물든다.
  ② 백업 없이 실행하지 않는다(sqlite backup API. cp 는 WAL 때문에 불완전하다).
  ③ 전후 대조 없이 완료라고 하지 않는다.

사용:
  python scripts/backfill_export_program_id_20260801.py --dry-run   (기본)
  python scripts/backfill_export_program_id_20260801.py --apply
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

TARGET_IDS = ("RND_CB0AC20C", "RND_A626CAA3")
NEW_PROGRAM_ID = "proj_2b0b23b104b0"
NEW_PROGRAM_TITLE = "Adhara"


def snapshot(con, ids):
    con.row_factory = sqlite3.Row
    q = ",".join("?" * len(ids))
    return [dict(r) for r in con.execute(
        f"SELECT * FROM export_results WHERE id IN ({q}) ORDER BY created_at", ids)]


def totals(con):
    return {
        "export_results_rows": con.execute("SELECT COUNT(*) FROM export_results").fetchone()[0],
        "program_id_null": con.execute(
            "SELECT COUNT(*) FROM export_results WHERE program_id IS NULL OR program_id=''"
        ).fetchone()[0],
    }


def backup(db_path):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{db_path}.PRE_EXPORT_BACKFILL_{stamp}.bak"
    src = sqlite3.connect(db_path)
    dstcon = sqlite3.connect(dst)
    try:
        src.backup(dstcon)          # WAL 포함 일관 사본 — cp 로는 안 된다
    finally:
        dstcon.close()
        src.close()
    chk = sqlite3.connect(dst)
    ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
    rows = chk.execute("SELECT COUNT(*) FROM export_results").fetchone()[0]
    chk.close()
    return dst, ok, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 dry-run)")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")

    before = snapshot(con, TARGET_IDS)
    before_totals = totals(con)
    print("=== 대상 2행 (전)")
    for row in before:
        print(json.dumps({k: str(v)[:60] for k, v in row.items()}, ensure_ascii=False, indent=1))
    print("=== 총계 (전):", before_totals)

    if len(before) != len(TARGET_IDS):
        print(f"[STOP] 대상 {len(TARGET_IDS)}건 중 {len(before)}건만 찾았다. 중단한다.")
        return 1
    if not all((r["program_id"] in (None, "")) for r in before):
        print("[STOP] 이미 program_id 가 채워진 행이 있다. 덮어쓰지 않는다.")
        return 1

    if not args.apply:
        print("\n[DRY-RUN] 쓰지 않았다. 실제 적용은 --apply.")
        con.close()
        return 0

    dst, ok, rows = backup(DB_PATH)
    print(f"\n[BACKUP] {dst}  integrity={ok}  export_results={rows}")
    if ok != "ok":
        print("[STOP] 백업 무결성 실패. 중단한다.")
        con.close()
        return 1

    with con:
        for rid in TARGET_IDS:      # 절벽 ① — id 를 하나씩 명시
            con.execute(
                "UPDATE export_results SET program_id=?, program_title=? WHERE id=?",
                (NEW_PROGRAM_ID, NEW_PROGRAM_TITLE, rid),
            )

    after = snapshot(con, TARGET_IDS)
    after_totals = totals(con)
    print("\n=== 대상 2행 (후)")
    for row in after:
        print(json.dumps({k: str(v)[:60] for k, v in row.items()}, ensure_ascii=False, indent=1))
    print("=== 총계 (후):", after_totals)

    # 전후 대조 — program_id/program_title 외 어떤 컬럼도 바뀌면 안 된다
    changed = []
    for b, a in zip(before, after):
        for k in b:
            if k in ("program_id", "program_title"):
                continue
            if b[k] != a[k]:
                changed.append((a["id"], k, b[k], a[k]))
    print("\n=== 회귀 확인")
    print(f"  총 행 수 전후 동일: {before_totals['export_results_rows'] == after_totals['export_results_rows']}")
    print(f"  결손 {before_totals['program_id_null']} -> {after_totals['program_id_null']}")
    print(f"  다른 컬럼 변경: {changed if changed else '없음'}")
    con.close()
    return 0 if not changed else 1


if __name__ == "__main__":
    sys.exit(main())
