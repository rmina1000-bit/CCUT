"""Rollback the SOUND-1 user-correction table.

Usage:
  python drop_table.py --db <absolute-path> --gate G1-2026-08-05-SOUND-1
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DROP_SQL, TABLE  # noqa: E402

GATE_TOKEN = "G1-2026-08-05-SOUND-1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--gate", required=True)
    args = parser.parse_args()
    if args.gate != GATE_TOKEN:
        print("[REFUSED] gate token mismatch")
        return 2

    db_path = os.path.abspath(args.db)
    con = sqlite3.connect(db_path)
    try:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
            print(f"[BEFORE] {TABLE}: {count} rows")
        except sqlite3.OperationalError:
            print(f"[BEFORE] {TABLE}: missing")
        for sql in DROP_SQL:
            con.execute(sql)
        con.commit()
        print(f"[DROPPED] {TABLE} from {db_path}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
