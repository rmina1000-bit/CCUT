"""Create the SOUND-1 user-correction table.

Usage:
  python create_table.py --db <absolute-path> --gate G1-2026-08-05-SOUND-1
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DDL_SQL, INDEX_SQL, TABLE, self_check  # noqa: E402

GATE_TOKEN = "G1-2026-08-05-SOUND-1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--gate", required=True)
    args = parser.parse_args()
    if args.gate != GATE_TOKEN:
        print("[REFUSED] gate token mismatch - schema change forbidden")
        return 2

    ok, detail = self_check()
    print(f"[SELF-CHECK] DDL columns match declaration: {ok}")
    if not ok:
        print(f"[SELF-CHECK DETAIL] {detail}")
        return 3

    db_path = os.path.abspath(args.db)
    con = sqlite3.connect(db_path)
    try:
        before = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.execute(DDL_SQL)
        for sql in INDEX_SQL:
            con.execute(sql)
        con.commit()
        after = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        print(f"[CREATED] {db_path}")
        print("[NEW TABLES]", sorted(after - before) or "(already present)")
        print(f"[TABLE] {TABLE}")
        for row in con.execute(f"PRAGMA table_info({TABLE})"):
            print("  ", tuple(row))
        print("[INDEXES]", [r[1] for r in con.execute(f"PRAGMA index_list({TABLE})")])
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
