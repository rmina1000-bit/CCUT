import sqlite3
import subprocess
import os

print("=== (1) config.yaml ===")
try:
    with open('ai/config.yaml', 'r', encoding='utf-8') as f:
        print(f.read())
except Exception as e:
    print(e)
    
print("=== (2) dir config.yaml* ===")
for f in os.listdir('ai'):
    if f.startswith('config.yaml'):
        print(f)

print("\n=== (3) uvicorn.log LlamaServer + Qwen3ASR ===")
llama_logs = []
qwen_logs = []
try:
    with open('uvicorn.log', 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '[LlamaServer]' in line:
                llama_logs.append(line.strip())
            if '[Qwen3ASR DEBUG] raw_content' in line:
                qwen_logs.append(line.strip())
    print("\n".join(llama_logs[-3:]))
    print("---")
    print("\n".join(qwen_logs[-5:]))
except Exception as e:
    print(e)

print("\n=== (4) DB Lookup ===")
try:
    conn = sqlite3.connect(r'D:\CCUT_1.0.3\ccut_database.db')
    c = conn.cursor()
    last_src = c.execute("SELECT source_id FROM fragments ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    print(f"Latest source_id: {last_src}")
    rows = c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') FROM fragments WHERE source_id=?", (last_src,)).fetchall()
    for r in rows:
        print(f"{r[0]} | {r[1]}")
    conn.close()
except Exception as e:
    print(e)

print("\n=== (5) tasklist ===")
res = subprocess.run("tasklist | findstr llama-server", shell=True, capture_output=True, text=True)
print(res.stdout.strip())
