# -*- coding: utf-8 -*-
"""edit_version · edit_version_item 생성 — 국장 G1 개방 (EDIT-SAVE-1).

사용:
  python create_table.py --db <절대경로> --gate G1-2026-08-06-EDIT-SAVE-1

story_version/create_table.py 와 동일 구조. 실수 실행을 막기 위해 게이트 토큰을
정확히 대야만 돈다. rollback 병기: drop_table.py.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import (  # noqa: E402
    DDL_SQL, ITEM_DDL_SQL, INDEX_SQL, TABLE, ITEM_TABLE, self_check,
)

GATE_TOKEN = "G1-2026-08-06-EDIT-SAVE-1"


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
        print(f"[TABLE COUNT] {len(before)} -> {len(after)}")
        for t in (TABLE, ITEM_TABLE):
            print(f"  -- {t}")
            for r in con.execute(f"PRAGMA table_info({t})"):
                print("     ", tuple(r))
            print("     indexes:", [r[1] for r in con.execute(f"PRAGMA index_list({t})")])
            print("     foreign_keys:", list(con.execute(f"PRAGMA foreign_key_list({t})")))
    finally:
        con.close()


if __name__ == "__main__":
    main()
