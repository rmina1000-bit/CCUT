import sys
import os
import json
import sqlite3

sys.path.append(os.path.abspath("ccut_backend"))
from engine.proposal_engine import ProposalEngine

# Connect to database
db_path = "ccut_backend/ccut_app.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# 22 requested source IDs
requested_sources = [
    'SRC_12C414A7', 'SRC_CB9107CA', 'SRC_B4F09612', 'SRC_0BE783EC',
    'SRC_AA6C87D2', 'SRC_B669588A', 'SRC_2BE80EE2', 'SRC_6F5DEBE2',
    'SRC_634C81D9', 'SRC_9E3E3C7B', 'SRC_B85F1985', 'SRC_EFDBBCFC',
    'SRC_83B87D21', 'SRC_901671A7', 'SRC_563A1B48', 'SRC_F2CFC4DC',
    'SRC_1435727E', 'SRC_E8F4845B', 'SRC_8E415949', 'SRC_616AEFBA',
    'SRC_D5BD47B6', 'SRC_B1A26714'
]

# Fetch semantic fragments for these sources
fragments = []
for sid in requested_sources:
    rows = conn.execute("SELECT * FROM semantic_fragments WHERE source_id=?", (sid,)).fetchall()
    for r in rows:
        f = dict(r)
        f["structural"] = json.loads(f["structural_json"]) if f.get("structural_json") else {}
        f["semantic"] = json.loads(f["semantic_json"]) if f.get("semantic_json") else {}
        f["continuity"] = json.loads(f["continuity_json"]) if f.get("continuity_json") else {}
        fragments.append(f)

print(f"Total fragments retrieved from DB: {len(fragments)}")

# Initialize mock BAMS
class MockBAMS:
    def get_user_intent(self, source_id):
        return None

bams = MockBAMS()
engine = ProposalEngine(bams)

# Analyze candidate fragment counts and edit values per source
print("\n--- Auditing requested sources (22 total) ---")
candidate_sources = set()
threshold_passed_sources = []
threshold_failed_sources = []

for sid in requested_sources:
    source_frags = [f for f in fragments if f.get("source_id") == sid]
    cnt = len(source_frags)
    if cnt > 0:
        candidate_sources.add(sid)
        
    edit_vals = [f.get("structural", {}).get("edit_value", 0.5) for f in source_frags]
    max_ev = max(edit_vals) if cnt > 0 else 0.0
    avg_ev = sum(edit_vals) / cnt if cnt > 0 else 0.0
    valid_cnt = sum(1 for ev in edit_vals if ev >= 0.1)
    
    if cnt > 0:
        print(f"Source: {sid} | Frags: {cnt} | Avg EV: {avg_ev:.4f} | Max EV: {max_ev:.4f} | Valid (>=0.1): {valid_cnt}")
        if valid_cnt > 0:
            threshold_passed_sources.append(sid)
        else:
            threshold_failed_sources.append(sid)
    else:
        print(f"Source: {sid} | No fragments found in DB")

print("\n--- Audit Summary ---")
print(f"Requested sources: {len(requested_sources)}")
print(f"Candidate sources (have fragments): {len(candidate_sources)}")
print(f"Eligible sources (at least 1 frag >= 0.1): {len(threshold_passed_sources)} / {len(candidate_sources)}")
print(f"Excluded by threshold sources (all frags < 0.1): {len(threshold_failed_sources)}")
print(f"Excluded source list: {threshold_failed_sources}")

# 1. Run BASE proposals (no balanced_sources)
story_ctx_base = {
    "template_id": "default",
    "user_intent": {
        "coverage": "default",
        "instruction_text": "일반 편집",
        "target_length": 60.0
    }
}
print("\n--- Generating Base Proposals ---")
proposals_base = engine.generate_proposals_from_fragments(
    project_id="proj_1779591776013",
    source_ids=requested_sources,
    fragments=fragments,
    target_len=60.0,
    story_context=story_ctx_base
)

p_a_base = proposals_base[0]
p_b_base = proposals_base[1]

# 2. Run BALANCED proposals (coverage == 'balanced_sources')
story_ctx_bal = {
    "template_id": "default",
    "user_intent": {
        "coverage": "balanced_sources",
        "instruction_text": "골고루",
        "target_length": 60.0
    }
}
print("\n--- Generating Balanced Proposals ---")
proposals_bal = engine.generate_proposals_from_fragments(
    project_id="proj_1779591776013",
    source_ids=requested_sources,
    fragments=fragments,
    target_len=60.0,
    story_context=story_ctx_bal
)

p_a_bal = proposals_bal[0]
p_b_bal = proposals_bal[1]

def print_prop_info(label, prop):
    seq = prop.get("sequence", [])
    sids = [f.get("source_id") for f in seq]
    unique_sids = set(sids)
    print(f"\n[{label}]")
    print(f"  Sequence Length: {len(seq)}")
    print(f"  Used Source Count: {len(unique_sids)}")
    print(f"  Used Sources: {list(unique_sids)}")
    # We calculate the distribution ourselves to make sure it matches
    counts = {}
    for s in sids:
        counts[s] = counts.get(s, 0) + 1
    dist = {s: {"count": c, "ratio": round(c / len(seq), 3)} for s, c in counts.items()}
    print(f"  Distribution: {json.dumps(dist)}")

print_prop_info("Base A Mode", p_a_base)
print_prop_info("Base B Mode", p_b_base)
print_prop_info("Balanced A Mode", p_a_bal)
print_prop_info("Balanced B Mode", p_b_bal)

conn.close()
