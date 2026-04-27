import sqlite3
import subprocess

out = []
out.append("### 1. [Qwen3ASR DEBUG] raw= First 3 Lines")
out.append("```text")
with open('uvicorn.log', 'r', encoding='utf-8', errors='ignore') as f:
    count = 0
    for line in f:
        if "[Qwen3ASR DEBUG] raw=" in line:
            out.append(line.strip())
            count += 1
            if count >= 3:
                break
out.append("```")

out.append("### 2. DB Query json_extract")
out.append("```text")
conn = sqlite3.connect(r'D:\CCUT_1.0.3\ccut_database.db')
c = conn.cursor()
try:
    rows = c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') as transcript FROM fragments WHERE source_id = 'SRC_36482548' LIMIT 5;").fetchall()
    for r in rows:
        out.append(f"ID: {r[0]} | Transcript: {r[1]}")
except Exception as e:
    out.append("Error: " + str(e))
conn.close()
out.append("```")

out.append("### 3. tasklist llama-server")
out.append("```text")
res = subprocess.run("tasklist | findstr llama-server", shell=True, capture_output=True, text=True)
out.append(res.stdout.strip() if res.stdout.strip() else "(No output)")
out.append("```")

with open("proof_clean.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
