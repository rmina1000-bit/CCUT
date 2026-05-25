import sqlite3
import json

conn = sqlite3.connect('ccut_backend/ccut_app.db')
cur = conn.cursor()
rows = cur.execute('SELECT source_id, structural_json FROM semantic_fragments WHERE source_id IN ("SRC_616AEFBA", "SRC_AA6C87D2", "SRC_B1A26714")').fetchall()

dist = {}
for sid, s_json in rows:
    s = json.loads(s_json) if s_json else {}
    ev = s.get('edit_value', 0.5)
    
    if sid not in dist:
        dist[sid] = {'total': 0, 'valid': 0, 'values': []}
    
    dist[sid]['total'] += 1
    dist[sid]['values'].append(ev)
    if ev >= 0.1:
        dist[sid]['valid'] += 1

for sid, stats in dist.items():
    print(f"Source: {sid}")
    print(f"  Total fragments: {stats['total']}")
    print(f"  Valid fragments (edit_value >= 0.1): {stats['valid']}")
    print(f"  Max edit_value: {max(stats['values']) if stats['values'] else None}")
    print(f"  Min edit_value: {min(stats['values']) if stats['values'] else None}")

conn.close()
