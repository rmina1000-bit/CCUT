# -*- coding: utf-8 -*-
"""story_approval 제거 스크립트 (rollback) — 격리 테스트 DB 전용. 운영 DB 하드 거부."""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import TABLE  # noqa: E402

FORBIDDEN_PROD_DB = os.path.normcase(os.path.abspath(r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    db = os.path.normcase(os.path.abspath(args.db))
    if db == FORBIDDEN_PROD_DB:
        # 콘솔 인코딩(cp949)에서 죽지 않도록 ASCII만 — 거부는 반드시 exit 2로 끝나야 한다.
        print("[REFUSED] production DB path - schema change forbidden")
        sys.exit(2)
    con = sqlite3.connect(db)
    try:
        con.execute(f"DROP TABLE IF EXISTS {TABLE}")
        con.commit()
        print(f"[DROPPED] {TABLE} from {args.db}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
