import sqlite3
import json

conn = sqlite3.connect(r"D:\CCUT_1.0.3\ccut_database.db")
c = conn.cursor()
c.execute("SELECT fragment_id, length(intelligence), intelligence FROM fragments WHERE source_id LIKE '%48FDD88F%' LIMIT 3;")
for r in c.fetchall():
    print(f"[{r[0]}] length={r[1]}")
    try:
        data = json.loads(r[2])
        print(f"RAW JSON:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
    except:
        print(f"RAW JSON:\n{r[2]}")
    print("---")
conn.close()
