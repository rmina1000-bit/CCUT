import sqlite3
import os

print("=== 1. DB 조회 ===")
try:
    conn = sqlite3.connect(r"D:\CCUT_1.0.3\ccut_database.db")
    cur = conn.cursor()
    # If standard user query fails, we fallback to showing schema to prove why
    try:
        cur.execute("SELECT fragment_id, length(transcript), transcript FROM fragments WHERE source_video LIKE '%48FDD88F%' LIMIT 3;")
        for row in cur.fetchall():
            print(f"[{row[0]}] length={row[1]} : {row[2]}")
    except Exception as e:
        print(f"Query Result Error: {e}")
        print("Schema info:")
        for row in cur.execute("PRAGMA table_info(fragments)").fetchall():
            print(row)
    conn.close()
except Exception as e:
    print(f"DB Error: {e}")

print("\n=== 2. uvicorn.log 마지막 2000줄 ===")
try:
    with open("uvicorn.log", "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        for line in lines[-2000:]:
            print(line, end="")
except Exception as e:
    print(f"Log Error: {e}")
