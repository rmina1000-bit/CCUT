# -*- coding: utf-8 -*-
"""story_approval 생성 스크립트 — 격리 테스트 DB 전용.

사용: python create_table.py --db <절대경로>
운영 DB(D:\\CCUT1.0.4\\ccut_backend\\ccut_app.db) 경로는 하드 거부 — Cutover 승인 전 실행 불가.
rollback 병기: drop_table.py (동일 가드).
edit_contract/create_table.py와 같은 규율.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DDL_SQL, INDEX_SQL, TABLE, self_check  # noqa: E402

FORBIDDEN_PROD_DB = os.path.normcase(os.path.abspath(r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="대상 SQLite 파일 절대경로 (격리 테스트 DB만)")
    args = ap.parse_args()
    db = os.path.normcase(os.path.abspath(args.db))
    if db == FORBIDDEN_PROD_DB:
        # 콘솔 인코딩(cp949)에서 죽지 않도록 ASCII만 — 거부는 반드시 exit 2로 끝나야 한다.
        print("[REFUSED] production DB path - schema change forbidden before Cutover")
        sys.exit(2)
    ok, cols = self_check()
    print(f"[SELF-CHECK] DDL == 선언 컬럼: {ok}")
    if not ok:
        print(f"[SELF-CHECK 상세] {cols}")
        sys.exit(3)
    con = sqlite3.connect(db)
    try:
        con.execute(DDL_SQL)
        for sql in INDEX_SQL:
            con.execute(sql)
        con.commit()
        print(f"[CREATED] {args.db}")
        for r in con.execute(f"PRAGMA table_info({TABLE})"):
            print("   ", tuple(r))
        print("[INDEXES]", [tuple(r) for r in con.execute(f"PRAGMA index_list({TABLE})")])
    finally:
        con.close()


if __name__ == "__main__":
    main()
