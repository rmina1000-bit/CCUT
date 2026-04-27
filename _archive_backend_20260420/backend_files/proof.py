import sqlite3
import subprocess

print("=== 1. [Qwen3ASR DEBUG] raw= First 3 Lines ===")
with open('uvicorn.log', 'r', encoding='utf-8', errors='ignore') as f:
    count = 0
    for line in f:
        if "[Qwen3ASR DEBUG] raw=" in line:
            print(line.strip())
            count += 1
            if count >= 3:
                break

print("\n=== 2. DB Query json_extract ===")
conn = sqlite3.connect(r'D:\CCUT_1.0.3\ccut_database.db')
c = conn.cursor()
try:
    rows = c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') as transcript FROM fragments WHERE source_id = 'SRC_36482548' LIMIT 5;").fetchall()
    for r in rows:
        print(f"ID: {r[0]}\nTranscript: {r[1]}\n---")
except Exception as e:
    print("Error:", e)
conn.close()

print("\n=== 3. tasklist llama-server ===")
res = subprocess.run("tasklist | findstr llama-server", shell=True, capture_output=True, text=True)
print(res.stdout.strip() if res.stdout.strip() else "(No output)")
