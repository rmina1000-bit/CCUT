import os
import sys
import uuid

# Add ccut_backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ccut_backend')))

from database import SessionLocal
from learning.contrast_learner import ContrastLearner
from learning.learning_models import UserEditDecisionTable, EditingPatternMemoryTable

def run_contrast_learning_test():
    print("==================================================")
    print("[TEST] Launching Success-Failure Contrastive Learning Test")
    print("==================================================")
    
    query = "vlog edit style"
    
    # 1. Store initial pattern memory states
    db = SessionLocal()
    try:
        initial_patterns = {p.pattern_type: (p.success_count, p.failure_count) for p in db.query(EditingPatternMemoryTable).all()}
        print(f"Initial Pattern Memory states: {initial_patterns}")
    finally:
        db.close()
        
    # 2. Execute Contrastive Learning Session
    print("\n--- Executing Contrast Learning Session ---")
    result = ContrastLearner.execute_contrast_learning_session(query, limit=2)
    print(f"Result: {result}")
    
    assert result["status"] == "SUCCESS", "Contrastive Learning session failed!"
    assert "decision_id" in result, "Result missing decision_id"
    
    # 3. Verify Database updates
    print("\n--- Verifying Database Contrastive Updates ---")
    db = SessionLocal()
    try:
        # Check decision logger
        decision = db.query(UserEditDecisionTable).filter_by(decision_id=result["decision_id"]).first()
        assert decision is not None, "Contrast learning decision not found in DB!"
        assert decision.decision_type == "CONTRAST_LEARN", f"Unexpected decision type: {decision.decision_type}"
        print(f"Decision Log verified: {decision.decision_id} | Type: {decision.decision_type}")
        
        # Verify pattern updates
        boosted_list = ["hook_3sec", "reaction_hold", "scenery_bridge"]
        penalized_list = ["boredom_prevent"]
        
        print("\nChecking Boosted Patterns (Success should increment):")
        for pat in boosted_list:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pat).first()
            init_s, init_f = initial_patterns.get(pat, (0, 0))
            print(f"Pattern {pat}: Initial Success={init_s} -> New Success={row.success_count}")
            assert row.success_count == init_s + 1, f"Pattern {pat} success count did not increment!"

        print("\nChecking Penalized Patterns (Failure should increment):")
        for pat in penalized_list:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pat).first()
            init_s, init_f = initial_patterns.get(pat, (0, 0))
            print(f"Pattern {pat}: Initial Failure={init_f} -> New Failure={row.failure_count}")
            assert row.failure_count == init_f + 1, f"Pattern {pat} failure count did not increment!"

    finally:
        db.close()
        
    print("\n==================================================")
    print("[SUCCESS] All Contrastive Learning tests passed!")
    print("==================================================")

if __name__ == "__main__":
    run_contrast_learning_test()
