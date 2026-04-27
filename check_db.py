import sqlite3
import os

db_path = 'd:/CCUT1.0.4/ccut_backend/ccut_app.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    if ('evidence_board',) in tables:
        cursor.execute("SELECT count(*) FROM evidence_board")
        print("Evidence count:", cursor.fetchone()[0])
    else:
        print("evidence_board table MISSING")
    conn.close()
