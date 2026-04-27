import sqlite3
out = []
try:
    conn = sqlite3.connect(r'D:\CCUT_1.0.3\ccut_database.db')
    c = conn.cursor()
    last_src = c.execute("SELECT source_id FROM fragments ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    out.append(f"Latest source_id: {last_src}")
    rows = c.execute("SELECT fragment_id, json_extract(intelligence, '$.transcript') FROM fragments WHERE source_id=? ORDER BY fragment_id", (last_src,)).fetchall()
    for r in rows:
        out.append(f"{r[0]} | {r[1]}")
    conn.close()
except Exception as e:
    out.append(str(e))
with open('db_proof.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
