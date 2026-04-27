import sqlite3
import sys

print("=== 1. DB transcript 샘플 조회 ===")
try:
    conn = sqlite3.connect(r"D:\CCUT_1.0.3\ccut_database.db")
    cur = conn.cursor()
    cur.execute("SELECT fragment_id, substr(transcript, 1, 100) FROM fragments WHERE source_video LIKE '%48FDD88F%' LIMIT 5;")
    for row in cur.fetchall():
        print(f"[{row[0]}] {row[1]}")
    conn.close()
except Exception as e:
    print(f"DB Query Failed: {e}")

print("\n=== 2. uvicorn.log 전체 ===")
try:
    with open("uvicorn.log", "r", encoding="utf-8", errors="replace") as f:
        print(f.read())
except Exception as e:
    print(f"Read Log Failed: {e}")
