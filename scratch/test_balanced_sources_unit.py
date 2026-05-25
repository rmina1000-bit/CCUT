import sys
import os

sys.path.append(os.path.abspath("ccut_backend"))
from archive.manager import bams
from engine.proposal_engine import ProposalEngine

def test_balanced_source_constraint():
    engine = ProposalEngine(bams)
    
    # 1. Prepare candidates from 3 different sources
    # We have 3 sources: A, B, C.
    # Source A has 8 fragments, B has 2, C has 2.
    candidates = []
    # Source A
    for i in range(8):
        candidates.append({
            "id": f"frag_A_{i}",
            "source_id": "SRC_A",
            "start": i * 10,
            "end": (i + 1) * 10,
            "structural": {"edit_value": 0.9 - (i * 0.05)} # higher index has lower value
        })
    # Source B
    for i in range(2):
        candidates.append({
            "id": f"frag_B_{i}",
            "source_id": "SRC_B",
            "start": i * 10,
            "end": (i + 1) * 10,
            "structural": {"edit_value": 0.8}
        })
    # Source C
    for i in range(2):
        candidates.append({
            "id": f"frag_C_{i}",
            "source_id": "SRC_C",
            "start": i * 10,
            "end": (i + 1) * 10,
            "structural": {"edit_value": 0.75}
        })
        
    # 2. Suppose "selected" initially has 5 fragments all from Source A (violating the 0.35 limit)
    selected = [candidates[0], candidates[1], candidates[2], candidates[3], candidates[4]]
    
    # Check current distribution
    initial_dist = engine._calculate_source_distribution(selected)
    print("Initial distribution:", initial_dist)
    assert initial_dist["by_source"]["SRC_A"]["ratio"] == 1.0
    
    # 3. Apply balanced constraints
    constraints = {
        "min_source_coverage_ratio": 0.6,
        "min_fragments_per_selected_source": 1,
        "max_single_source_clip_ratio": 0.35
    }
    
    balanced_selected, warnings = engine._apply_balanced_source_constraints(selected, candidates, constraints)
    
    final_dist = engine._calculate_source_distribution(balanced_selected)
    print("Final distribution:", final_dist)
    print("Warnings:", warnings)
    print("Balanced Selected IDs:", [f["id"] for f in balanced_selected])
    
    # Check constraint: no single source exceeds 0.35 ratio
    for sid, info in final_dist["by_source"].items():
        assert info["ratio"] <= 0.35, f"Source {sid} ratio {info['ratio']} exceeds 0.35!"
        
    print("SUCCESS: Balanced source constraints verified successfully!")

if __name__ == "__main__":
    test_balanced_source_constraint()
