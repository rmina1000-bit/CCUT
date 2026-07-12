# -*- coding: utf-8 -*-
"""fragment_edit_state 제거 스크립트 (rollback 병기분) — 격리 테스트 DB 전용.

운영 DB는 Cutover 후에도 DROP 금지 (패치 2: 게이트 OFF + 테이블 보존 + 구 경로 복귀).
따라서 본 스크립트도 운영 DB 경로를 하드 거부한다.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DROP_SQL  # noqa: E402

FORBIDDEN_PROD_DB = os.path.normcase(os.path.abspath(r"D:\CCUT1.0.4\ccut_backend\ccut_app.db"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="대상 SQLite 파일 절대경로 (격리 테스트 DB만)")
    args = ap.parse_args()
    db = os.path.normcase(os.path.abspath(args.db))
    if db == FORBIDDEN_PROD_DB:
        print("[REFUSED] 운영 DB 경로 — DROP 금지 (패치 2 rollback 재정의)")
        sys.exit(2)
    con = sqlite3.connect(db)
    try:
        con.execute(DROP_SQL)
        con.commit()
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fragment_edit_state'"
        ).fetchone()
        print(f"[DROPPED] {args.db} | 존재 확인: {row}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
