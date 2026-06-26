import sqlite3
import json

conn = sqlite3.connect('ccut_backend/ccut_app.db')
cursor = conn.cursor()

# Find non-mock source_ids
cursor.execute("SELECT DISTINCT source_id FROM fragments WHERE source_id NOT LIKE '%mock%' AND source_id != 'SRC_12C414A7' LIMIT 10")
source_ids = [row[0] for row in cursor.fetchall()]
print("Non-mock source IDs in database:", source_ids)

# Let's inspect fragments for these source_ids
for sid in source_ids[:3]:
    cursor.execute("SELECT fragment_id, source_id, intelligence FROM fragments WHERE source_id = ? LIMIT 3", (sid,))
    rows = cursor.fetchall()
    print(f"\nFragments for source {sid}:")
    for r in rows:
        intel = json.loads(r[2]) if r[2] else {}
        print(f"  ID: {r[0]}")
        print(f"    thumb_url: {intel.get('thumb_url')}")
        print(f"    keys: {list(intel.keys())}")
