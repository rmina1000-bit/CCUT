import sqlite3
import re

print("=== [Qwen3ASR DEBUG] Logs ===")
source_ids = []
try:
    with open('uvicorn.log', 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if '[Qwen3ASR DEBUG]' in line:
                print(line)
            m = re.search(r"source_id=(SRC_[A-Z0-9]+)", line)
            if m:
                source_ids.append(m.group(1))
except Exception as e:
    print("Log read error:", e)

print("\n=== DB INFO ===")
if source_ids:
    last_src = source_ids[-1]
    print(f"Latest source_id: {last_src}")
    try:
        conn = sqlite3.connect("D:/CCUT_1.0.3/ccut_database.db")
        c = conn.cursor()
        count = 0
        for row in c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') FROM fragments WHERE source_id=?", (last_src,)):
            print(f"[{row[0]}] -> {repr(row[1])}")
            count += 1
            if count >= 10:  # Limiting print
                break
        conn.close()
    except Exception as e:
        print("DB error:", e)
else:
    print("No source_id found in logs!")
