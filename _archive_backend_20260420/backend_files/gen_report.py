import sqlite3
import os

out = []
out.append("### 1. uvicorn.log 최근 내역")
try:
    with open(r"D:\CCUT_1.0.3\ccut_backend\uvicorn.log", "r", encoding="utf-8", errors="replace") as f:
        log_content = f.read()
        lines = log_content.splitlines()[-2000:]
        out.append("```text\n" + "\n".join(lines) + "\n```")
except Exception as e:
    out.append(f"Log Read Error: {e}")

out.append("### 2. DB Schema Error 및 Data(intelligence)")
out.append("명령하신 `transcript` 컬럼은 스키마 상 존재하지 않아 쿼리 에러가 발생했습니다. DB 테이블에는 `intelligence` (JSON) 컬럼만 존재함을 확인하여 이를 대신 추출합니다.")
out.append("```text")
try:
    conn = sqlite3.connect(r"D:\CCUT_1.0.3\ccut_database.db")
    c = conn.cursor()
    c.execute("SELECT fragment_id, length(intelligence), intelligence FROM fragments WHERE source_video LIKE '%48FDD88F%' LIMIT 3;")
    for r in c.fetchall():
        out.append(f"[{r[0]}] length={r[1]}\nJSON: {r[2]}\n---")
    conn.close()
except Exception as e:
    out.append(f"DB Error: {e}")
out.append("```")

with open(r"D:\CCUT_1.0.3\ccut_backend\report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
