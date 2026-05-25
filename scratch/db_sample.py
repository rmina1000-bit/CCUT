import sqlite3
import json

db_path = "ccut_backend/ccut_app.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Query all fragments with intelligence
cursor.execute("SELECT fragment_id, source_id, start_time, end_time, intelligence FROM fragments;")
rows = cursor.fetchall()
found = False
for fid, sid, start, end, intel_str in rows:
    if not intel_str:
        continue
    intel = json.loads(intel_str)
    transcript = intel.get("transcript", "")
    words = intel.get("words", [])
    if transcript or words:
        print(f"Found fragment with transcript/words in Source: {sid}, Fragment: {fid}")
        print(f"Transcript: {transcript}")
        print(f"Words Count: {len(words)}")
        if words:
            print(f"Sample words: {words[:10]}")
        found = True
        break

if not found:
    print("No fragments with transcript or words found in ccut_app.db.")
    
conn.close()
