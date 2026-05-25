import sqlite3
import json

conn = sqlite3.connect('ccut_backend/ccut_app.db')

requested_sources = [
    'SRC_12C414A7', 'SRC_CB9107CA', 'SRC_B4F09612', 'SRC_0BE783EC',
    'SRC_AA6C87D2', 'SRC_B669588A', 'SRC_2BE80EE2', 'SRC_6F5DEBE2',
    'SRC_634C81D9', 'SRC_9E3E3C7B', 'SRC_B85F1985', 'SRC_EFDBBCFC',
    'SRC_83B87D21', 'SRC_901671A7', 'SRC_563A1B48', 'SRC_F2CFC4DC',
    'SRC_1435727E', 'SRC_E8F4845B', 'SRC_8E415949', 'SRC_616AEFBA',
    'SRC_D5BD47B6', 'SRC_B1A26714'
]

print("| Source ID | Fragment Count | Avg edit_value | Max edit_value | edit_value >= 0.1? | Status |")
print("|---|---|---|---|---|---|")

passed_sources = []
failed_sources = []

for sid in requested_sources:
    rows = conn.execute("SELECT structural_json FROM semantic_fragments WHERE source_id=?", (sid,)).fetchall()
    cnt = len(rows)
    if cnt == 0:
        print(f"| {sid} | 0 | - | - | - | No Fragments |")
        continue
    
    vals = []
    for r in rows:
        s = json.loads(r[0]) if r[0] else {}
        vals.append(s.get("edit_value", 0.5))
        
    avg_v = sum(vals) / cnt
    max_v = max(vals)
    passed = any(v >= 0.1 for v in vals)
    
    passed_str = "Yes" if passed else "No"
    status_str = "Eligible" if passed else "Excluded"
    
    if passed:
        passed_sources.append(sid)
    else:
        failed_sources.append(sid)
        
    print(f"| {sid} | {cnt} | {avg_v:.4f} | {max_v:.4f} | {passed_str} | {status_str} |")

print(f"\nTotal requested: {len(requested_sources)}")
print(f"Total candidate: {len(requested_sources)}")
print(f"Eligible after threshold (>=0.1): {len(passed_sources)}")
print(f"Excluded by threshold (<0.1): {len(failed_sources)}")
print(f"Excluded List: {failed_sources}")

conn.close()
