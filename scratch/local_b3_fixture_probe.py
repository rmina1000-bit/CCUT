import sys
import os
import uuid

# Add project root to sys.path
# Using absolute path for safety
project_root = r'D:\CCUT1.0.4'
if project_root not in sys.path:
    sys.path.append(project_root)

# [STEP 10-K-B3-R1] Actual codebase import
try:
    from ccut_backend.engine.proposal_engine import ProposalEngine
    print("[SUCCESS] Imported ProposalEngine from ccut_backend")
except ImportError as e:
    print(f"[ERROR] Failed to import ProposalEngine: {e}")
    sys.exit(1)

# Mock BAMS (Backend Asset Management System)
class MockBAMS:
    def get_semantic_fragments(self, sid): return []
    def get_user_intent(self, sid): return {}
    def get_quick_scan(self, sid): return {}
    def save_proposals(self, sid, props): pass
    def get_fragments_by_source(self, sid): return []

def create_fragment(fid, sid, start, duration, edit_value=0.8):
    return {
        "fragment_id": fid,
        "id": fid,
        "source_id": sid,
        "start": start,
        "end": start + duration,
        "structural": {
            "duration": duration,
            "edit_value": edit_value,
            "market_value": 0.8,
            "role": "content"
        },
        "continuity": {
            "time_proximity": 0.9
        },
        "confidence": 0.9
    }

# Create Fixture Fragments (3 sources, 4+ fragments each)
fragments = []
# Source A
for i in range(5):
    fragments.append(create_fragment(f"SF_A{i}", "SRC_A", i * 10, 5, edit_value=0.95))
# Source B
for i in range(4):
    fragments.append(create_fragment(f"SF_B{i}", "SRC_B", i * 10, 5, edit_value=0.85))
# Source C
for i in range(4):
    fragments.append(create_fragment(f"SF_C{i}", "SRC_C", i * 10, 5, edit_value=0.75))

engine = ProposalEngine(MockBAMS())

story_context = {
    "template_id": "balanced_multi_source_record",
    "hard_constraints": {
        "min_source_coverage_ratio": 0.6,
        "min_fragments_per_selected_source": 1,
        "max_single_source_clip_ratio": 0.35
    },
    "editing_technique_ids": [
        "source_rotation",
        "source_diversity_guard"
    ]
}

print("\n--- [STEP 10-K-B3-R1] Calling generate_proposals_from_fragments ---")
proposals = engine.generate_proposals_from_fragments(
    project_id="TEST_LOCAL_PROB",
    source_ids=["SRC_A", "SRC_B", "SRC_C"],
    fragments=fragments,
    target_len=60.0,
    story_context=story_context
)

# [STEP 10-K-B3-R2] Handle proposals return type safely
if isinstance(proposals, dict):
    proposals_list = proposals.get("proposals", [])
else:
    proposals_list = proposals

# Identify User Proposal (Mode B)
p_b = next((p for p in proposals_list if p.get("mode") == "B"), None)

if not p_b:
    print("[ERROR] User Proposal (B) not found in result")
    sys.exit(1)

print("\n--- User Proposal (B) Result ---")
print(f"Proposal ID: {p_b.get('proposal_id')}")
print(f"Duration: {p_b.get('duration')}s")

source_dist = p_b.get("source_distribution", {})
print("\n--- Source Distribution ---")
print(f"Source Count: {source_dist.get('source_count')}")
print(f"Max Ratio: {source_dist.get('max_single_source_ratio')}")
print("By Source:")
for sid, data in source_dist.get("by_source", {}).items():
    print(f"  {sid}: {data['count']} frags, ratio {data['ratio']}")

balance_policy = p_b.get("balance_policy", {})
print("\n--- Balance Policy ---")
print(f"Applied: {balance_policy.get('applied')}")
print(f"Warnings: {balance_policy.get('warnings')}")

print("\n--- Sequence (Source Rotation Check) ---")
seq = p_b.get("sequence", [])
source_seq = [f.get("source_id") for f in seq]
print(f"Source Sequence: {source_seq}")

# Calculate max consecutive length
max_consecutive = 0
if source_seq:
    curr = 1
    for i in range(len(source_seq)-1):
        if source_seq[i] == source_seq[i+1]:
            curr += 1
        else:
            max_consecutive = max(max_consecutive, curr)
            curr = 1
    max_consecutive = max(max_consecutive, curr)
print(f"Max consecutive source length: {max_consecutive}")

print("\n--- PASS/FAIL CHECK ---")
passed = True
# [STEP 10-K-B3-R2] Fixed undefined variables
if source_dist.get('source_count', 0) < 2: 
    print("[FAIL] source_count < 2")
    passed = False
if not balance_policy.get('applied'):
    print("[FAIL] balance_policy.applied is False")
    passed = False

if passed:
    print("[RESULT] PASS")
else:
    print("[RESULT] FAIL")
