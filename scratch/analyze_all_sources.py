import sqlite3
import json

conn = sqlite3.connect('ccut_backend/ccut_app.db')
cur = conn.cursor()

# Get all unique source_ids in semantic_fragments
sources_in_db = [r[0] for r in cur.execute("SELECT DISTINCT source_id FROM semantic_fragments").fetchall()]
print(f"Total sources in semantic_fragments: {len(sources_in_db)}")

all_stats = []

for sid in sources_in_db:
    rows = cur.execute("SELECT structural_json FROM semantic_fragments WHERE source_id=?", (sid,)).fetchall()
    count = len(rows)
    edit_values = []
    for r in rows:
        s_json = r[0]
        s = json.loads(s_json) if s_json else {}
        ev = s.get("edit_value", 0.5)
        edit_values.append(ev)
    
    avg_ev = sum(edit_values) / count if count > 0 else 0.0
    max_ev = max(edit_values) if count > 0 else 0.0
    valid_count = sum(1 for ev in edit_values if ev >= 0.1)
    
    all_stats.append({
        "source_id": sid,
        "count": count,
        "avg_edit_value": avg_ev,
        "max_edit_value": max_ev,
        "valid_count": valid_count
    })

# Print stats
print("\n=== SOURCE STATS ===")
eligible_sources = []
excluded_sources = []

for stat in all_stats:
    passed = stat["valid_count"] > 0
    if passed:
        eligible_sources.append(stat["source_id"])
    else:
        excluded_sources.append(stat["source_id"])
        
    print(f"Source: {stat['source_id']}")
    print(f"  Fragments: {stat['count']}")
    print(f"  Avg Edit Value: {stat['avg_edit_value']:.4f}")
    print(f"  Max Edit Value: {stat['max_edit_value']:.4f}")
    print(f"  Valid Fragments (>=0.1): {stat['valid_count']} ({'PASS' if passed else 'FAIL'})")

print("\n=== SUMMARY ===")
print(f"Total Sources analyzed: {len(all_stats)}")
print(f"Eligible Sources (at least 1 frag >= 0.1): {len(eligible_sources)}")
print(f"Excluded Sources (all frags < 0.1): {len(excluded_sources)}")
print(f"Eligible list: {eligible_sources}")
print(f"Excluded list: {excluded_sources}")

conn.close()
