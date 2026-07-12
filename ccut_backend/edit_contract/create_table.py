# -*- coding: utf-8 -*-
"""fragment_edit_state 생성 스크립트 — 격리 테스트 DB 전용 (패치 2).

사용: python create_table.py --db <절대경로>
운영 DB(D:\\CCUT1.0.4\\ccut_backend\\ccut_app.db) 경로는 하드 거부 — Cutover 승인 전 실행 불가.
rollback 병기: drop_table.py (동일 가드).
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DDL_SQL, self_check  # noqa: E402

FORBIDDEN_PROD_DB = os.path.normcase(os.path.abspath(r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="대상 SQLite 파일 절대경로 (격리 테스트 DB만)")
    args = ap.parse_args()
    db = os.path.normcase(os.path.abspath(args.db))
    if db == FORBIDDEN_PROD_DB:
        print("[REFUSED] 운영 DB 경로 — Cutover 승인 전 schema 변경 금지 (패치 2)")
        sys.exit(2)
    ok, cols = self_check()
    print(f"[SELF-CHECK] DDL == 클래스 컬럼: {ok}")
    if not ok:
        print(f"[SELF-CHECK 상세] {cols}")
        sys.exit(3)
    con = sqlite3.connect(db)
    try:
        con.execute(DDL_SQL)
        con.commit()
        rows = con.execute("PRAGMA table_info(fragment_edit_state)").fetchall()
        print(f"[CREATED] {args.db}")
        for r in rows:
            print("   ", r)
        idx = con.execute("PRAGMA index_list(fragment_edit_state)").fetchall()
        print("[INDEXES]", idx)
    finally:
        con.close()


if __name__ == "__main__":
    main()
