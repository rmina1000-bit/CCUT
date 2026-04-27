import sqlite3
import re

out = []
out.append("### 1. [Qwen3ASR DEBUG] Logs")
out.append("```text")
source_ids = []
try:
    with open('uvicorn.log', 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "[Qwen3ASR DEBUG]" in line:
                out.append(line.strip())
            m = re.search(r"source_id=(SRC_[A-Z0-9]+)", line)
            if m:
                source_ids.append(m.group(1))
except Exception as e:
    out.append("Log error: " + str(e))
out.append("```")

if source_ids:
    last_source_id = source_ids[-1]
    out.append(f"### 2. DB Query for {last_source_id}")
    out.append("```text")
    try:
        conn = sqlite3.connect(r'D:\CCUT_1.0.3\ccut_database.db')
        c = conn.cursor()
        rows = c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') FROM fragments WHERE source_id = ?", (last_source_id,)).fetchall()
        for r in rows:
            out.append(f"{r[0]} | {r[1]}")
        conn.close()
    except Exception as e:
        out.append("DB error: " + str(e))
    out.append("```")
else:
    out.append("No source_id found in logs!")

with open("proof2.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
