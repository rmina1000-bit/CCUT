# -*- coding: utf-8 -*-
"""story_version · story_version_item 생성 — 국장 G1 개방 2026-08-04.

사용:
  python create_table.py --db <절대경로> --gate G1-2026-08-04

운영 DB 를 대상으로 하려면 --gate 를 정확히 대야 한다.
story_approval 쪽 스크립트는 운영 DB 를 하드 거부하는데, 그 가드는 그 테이블의
Cutover 미승인 상태를 지키는 것이라 손대지 않는다. 이 테이블은 국장이 연 것이고,
그 개방을 인자에 적어야만 실행된다 — 실수로 도는 것을 막는다.

rollback 병기: drop_table.py (역DDL 2줄).
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import (  # noqa: E402
    DDL_SQL, ITEM_DDL_SQL, INDEX_SQL, TABLE, ITEM_TABLE, self_check,
)

GATE_TOKEN = "G1-2026-08-04"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="대상 SQLite 파일 절대경로")
    ap.add_argument("--gate", required=True, help=f"국장 개방 토큰 ({GATE_TOKEN})")
    args = ap.parse_args()
    if args.gate != GATE_TOKEN:
        print("[REFUSED] gate token mismatch - schema change forbidden")
        sys.exit(2)

    ok, cols = self_check()
    print(f"[SELF-CHECK] DDL == 선언 컬럼: {ok}")
    if not ok:
        print(f"[SELF-CHECK 상세] {cols}")
        sys.exit(3)

    db = os.path.abspath(args.db)
    con = sqlite3.connect(db)
    try:
        before = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.execute(DDL_SQL)
        con.execute(ITEM_DDL_SQL)
        for sql in INDEX_SQL:
            con.execute(sql)
        con.commit()
        after = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        print(f"[CREATED] {db}")
        print("[NEW TABLES]", sorted(after - before) or "(이미 있었음)")
        for t in (TABLE, ITEM_TABLE):
            print(f"  -- {t}")
            for r in con.execute(f"PRAGMA table_info({t})"):
                print("     ", tuple(r))
            print("     indexes:", [r[1] for r in con.execute(f"PRAGMA index_list({t})")])
    finally:
        con.close()


if __name__ == "__main__":
    main()
