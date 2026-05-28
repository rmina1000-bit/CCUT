import os
import sys
import uuid

# Add ccut_backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ccut_backend')))

from database import SessionLocal
from learning.learning_models import init_learning_db, TemporalFlowMemoryTable, UserEditDecisionTable
from learning.temporal_flow_learner import TemporalFlowLearner

def run_temporal_flow_test():
    print("==================================================")
    print("[TEST] Launching Temporal Narrative Flow Learning Test")
    print("==================================================")
    
    # 1. Initialize DB tables (creates temporal_flow_memory table if not exists)
    init_learning_db()
    
    project_id = f"FLOW_PROJ_{uuid.uuid4().hex[:6].upper()}"
    
    # 2. Setup mock proposal with transition sequence: Hook -> Setup -> Tension -> Payoff -> Pause
    mock_proposal = {
        "proposal_id": f"PROP_FLOW_{uuid.uuid4().hex[:4].upper()}",
        "mode": "FLOW_A",
        "duration": 22.0,
        "sequence": [
            {"fragment_id": "FRAG_F1", "duration": 2.0, "structural": {"role": "reaction"}}, # idx 0 & dur <= 3 -> hook
            {"fragment_id": "FRAG_F2", "duration": 5.0, "structural": {"role": "scenery"}},  # scenery -> setup
            {"fragment_id": "FRAG_F3", "duration": 4.0, "structural": {"role": "action"}},   # action -> tension
            {"fragment_id": "FRAG_F4", "duration": 3.0, "structural": {"role": "reaction"}}, # reaction -> payoff
            {"fragment_id": "FRAG_F5", "duration": 8.0, "structural": {"role": "main"}}      # main & dur > 6 -> pause
        ]
    }
    
    expected_flow = ["hook", "setup", "tension", "payoff", "pause"]
    
    # Check initial flow multiplier
    init_mult = TemporalFlowLearner.get_flow_multiplier(expected_flow)
    print(f"Initial flow multiplier (should be 1.0): {init_mult}")
    assert init_mult == 1.0, f"Expected multiplier 1.0, got {init_mult}"
    
    # 3. Learn proposal flow sequence (Success case)
    print("\n--- Learning Flow Sequence (Success Case) ---")
    res = TemporalFlowLearner.analyze_and_learn_proposal_flow(project_id, mock_proposal, success=True)
    print(f"Flow learning result: {res}")
    
    assert res["status"] == "SUCCESS", "Flow learning failed!"
    assert res["flow_sequence"] == expected_flow, f"Expected flow sequence {expected_flow}, got {res['flow_sequence']}"
    
    # 4. Verify DB updates
    db = SessionLocal()
    try:
        # Check flow memory record
        flow_hash = res["flow_hash"]
        row = db.query(TemporalFlowMemoryTable).filter_by(flow_id=flow_hash).first()
        assert row is not None, "Flow sequence row not found in temporal_flow_memory!"
        print(f"Found Flow memory: flow_id={row.flow_id} | sequence={row.flow_sequence} | success_count={row.success_count} | Acceptance={row.avg_user_acceptance}")
        assert row.success_count == 1, "Success count did not increment!"
        
        # Check decision log
        decision = db.query(UserEditDecisionTable).filter_by(decision_id=res["decision_id"]).first()
        assert decision is not None, "Decision log not found in user_edit_decisions!"
        assert decision.decision_type == "TEMPORAL_FLOW_LEARN"
        print(f"Decision Log verified: {decision.decision_id} | Type: {decision.decision_type}")
        
    finally:
        db.close()
        
    # 5. Simulate multiple successes to trigger multiplier boost (>0.65 acceptance)
    print("\n--- Simulating Boosted Flow Acceptance ---")
    for _ in range(2):
        TemporalFlowLearner.record_flow_feedback(expected_flow, success=True)
        
    boosted_mult = TemporalFlowLearner.get_flow_multiplier(expected_flow)
    print(f"New boosted multiplier (should be 1.2): {boosted_mult}")
    assert boosted_mult == 1.20, f"Expected boosted multiplier 1.2, got {boosted_mult}"
    
    # 6. Simulate multiple failures to trigger penalty (<0.35 acceptance)
    print("\n--- Simulating Penalized Flow Acceptance ---")
    for _ in range(6):
        TemporalFlowLearner.record_flow_feedback(expected_flow, success=False)
        
    penalized_mult = TemporalFlowLearner.get_flow_multiplier(expected_flow)
    print(f"New penalized multiplier (should be 0.75): {penalized_mult}")
    assert penalized_mult == 0.75, f"Expected penalized multiplier 0.75, got {penalized_mult}"
    
    print("\n==================================================")
    print("[SUCCESS] All Temporal Narrative Flow tests passed!")
    print("==================================================")

if __name__ == "__main__":
    run_temporal_flow_test()
