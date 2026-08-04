# -*- coding: utf-8 -*-
"""story_version · story_version_item 제거 (rollback · 역DDL).

사용:
  python drop_table.py --db <절대경로> --gate G1-2026-08-04

기존 테이블은 건드리지 않으므로 이 두 줄이 되돌리기 전부다.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DROP_SQL, TABLE, ITEM_TABLE  # noqa: E402

GATE_TOKEN = "G1-2026-08-04"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--gate", required=True)
    args = ap.parse_args()
    if args.gate != GATE_TOKEN:
        print("[REFUSED] gate token mismatch")
        sys.exit(2)

    db = os.path.abspath(args.db)
    con = sqlite3.connect(db)
    try:
        for t in (TABLE, ITEM_TABLE):
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"[BEFORE] {t}: {n} 행")
            except sqlite3.OperationalError:
                print(f"[BEFORE] {t}: 없음")
        for sql in DROP_SQL:
            con.execute(sql)
        con.commit()
        print(f"[DROPPED] {TABLE}, {ITEM_TABLE} from {db}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
