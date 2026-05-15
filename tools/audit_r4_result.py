import sqlite3, json, re

def group_key(fid):
    return re.sub(r'_P\d+$', '', fid or "")

con = sqlite3.connect("ccut_backend/ccut_app.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

sid = "SRC_616AEFBA"

props = cur.execute("""
    SELECT proposal_id, mode, sequence, duration, created_at
    FROM proposals
    WHERE source_id=?
    ORDER BY created_at DESC
    LIMIT 4
""", (sid,)).fetchall()

a_groups = set()
b_groups = set()

for p in props:
    seq = json.loads(p["sequence"]) if p["sequence"] else []
    mode = p["mode"]

    print(f"\n[{mode}] {p['proposal_id']} count={len(seq)} duration={p['duration']}")

    for x in seq:
        fid = x.get("fragment_id", "")
        gk = group_key(fid)
        sem = x.get("semantic") or {}
        struct = x.get("structural") or {}

        print({
            "fragment_id": fid,
            "group": gk,
            "start": x.get("start"),
            "end": x.get("end"),
            "edit_value": struct.get("edit_value"),
            "summary": (sem.get("summary") or "")[:50],
            "evidence_refs": sem.get("evidence_refs"),
        })

        if mode == "A":
            a_groups.add(gk)
        elif mode == "B":
            b_groups.add(gk)

print("\n=== Group Diversity ===")
print("A groups:", sorted(a_groups))
print("B groups:", sorted(b_groups))
print("common groups:", sorted(a_groups & b_groups))
print("B exclusive groups:", sorted(b_groups - a_groups))

con.close()
