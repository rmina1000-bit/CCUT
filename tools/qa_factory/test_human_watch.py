import os
import sys
import uuid

# Add ccut_backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ccut_backend')))

from database import SessionLocal
from learning.learning_models import init_learning_db, HumanWatchSessionTable, UserEditDecisionTable, EditingPatternMemoryTable
from learning.human_watch_session import HumanWatchSession

def run_human_watch_test():
    print("==================================================")
    print("[TEST] Launching Human Watch Session System Test")
    print("==================================================")
    
    # 1. Initialize tables (creates human_watch_sessions table if not exists)
    init_learning_db()
    
    project_id = f"WCH_PROJ_{uuid.uuid4().hex[:6].upper()}"
    viewer_id = "USER_RECON_7"
    
    playback_actions = [
        {"time": 2.5, "action": "pause"},
        {"time": 8.0, "action": "skip", "target": 12.0}
    ]
    
    retention_map = {
        "FRAG_HOOK_1": 1.5,
        "FRAG_REAC_2": 0.1,
        "FRAG_SCE_3": 1.0
    }
    
    # Get initial pattern counts
    db = SessionLocal()
    try:
        initial_patterns = {p.pattern_type: (p.success_count, p.failure_count) for p in db.query(EditingPatternMemoryTable).all()}
        print(f"Initial patterns state: {initial_patterns}")
    finally:
        db.close()
        
    # 2. Log Human Watch Session
    print("\n--- Logging Watch Session ---")
    res = HumanWatchSession.log_watch_session(project_id, viewer_id, playback_actions, retention_map)
    print(f"Log response: {res}")
    
    assert res["status"] == "SUCCESS", "Failed to log watch session!"
    assert "session_id" in res, "Missing session_id"
    assert "decision_id" in res, "Missing decision_id"
    
    # 3. Verify Database records
    print("\n--- Verifying Database Playback Logs ---")
    db = SessionLocal()
    try:
        # Check session log row
        session = db.query(HumanWatchSessionTable).filter_by(session_id=res["session_id"]).first()
        assert session is not None, "HumanWatchSession record not found in DB!"
        assert session.viewer_id == viewer_id, "Viewer ID mismatch!"
        print(f"Session row verified: session_id={session.session_id} | viewer={session.viewer_id} | actions={session.playback_actions}")
        
        # Check decision log row
        decision = db.query(UserEditDecisionTable).filter_by(decision_id=res["decision_id"]).first()
        assert decision is not None, "Decision log row not found!"
        assert decision.decision_type == "HUMAN_WATCH_LOG"
        print(f"Decision Log verified: {decision.decision_id} | Type: {decision.decision_type} | tuned={decision.user_intent.get('tuned_patterns')}")
        
        # Check pattern memory updates
        print("\nChecking Pattern Memory updates:")
        boosted = ["hook_3sec", "scenery_bridge"]
        penalized = ["reaction_hold"]
        
        for pat in boosted:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pat).first()
            init_s, init_f = initial_patterns.get(pat, (0, 0))
            print(f"Pattern {pat}: Initial Success={init_s} -> New Success={row.success_count}")
            assert row.success_count == init_s + 1, f"Expected success count increment for {pat}"
            
        for pat in penalized:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pat).first()
            init_s, init_f = initial_patterns.get(pat, (0, 0))
            print(f"Pattern {pat}: Initial Failure={init_f} -> New Failure={row.failure_count}")
            assert row.failure_count == init_f + 1, f"Expected failure count increment for {pat}"
            
    finally:
        db.close()
        
    print("\n==================================================")
    print("[SUCCESS] All Human Watch Session tests passed!")
    print("==================================================")

if __name__ == "__main__":
    run_human_watch_test()
