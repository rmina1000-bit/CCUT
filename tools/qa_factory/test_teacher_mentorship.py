import os
import sys
import uuid

# Add ccut_backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ccut_backend')))

from database import SessionLocal
from learning.teacher_mentor import TeacherMentor
from learning.learning_models import WeakLabelTable, UserEditDecisionTable, EditingPatternMemoryTable

def run_teacher_mentorship_test():
    print("==================================================")
    print("[TEST] Launching Teacher-Student Mentorship System Test")
    print("==================================================")
    
    project_id = f"PROJ_TEST_{uuid.uuid4().hex[:6].upper()}"
    print(f"Generated test project ID: {project_id}")
    
    # 1. Prepare dummy proposals with high uncertainty (diff = 0.51 - 0.49 = 0.02 <= 0.04)
    prop_a = {
        "proposal_id": f"PROP_A_{uuid.uuid4().hex[:4].upper()}",
        "mode": "A",
        "duration": 15.5,
        "rerank_score": 0.51,
        "human_reality_score_data": {
            "human_reality_score": 0.75,
            "metrics": {"narrative_flow": 0.8, "visual_stability": 0.7}
        },
        "sequence": [
            {"fragment_id": f"FRAG_W_1_{uuid.uuid4().hex[:4].upper()}", "duration": 2.5, "structural": {"role": "reaction"}},
            {"fragment_id": f"FRAG_W_2_{uuid.uuid4().hex[:4].upper()}", "duration": 5.0, "structural": {"role": "scenery"}},
            {"fragment_id": f"FRAG_W_3_{uuid.uuid4().hex[:4].upper()}", "duration": 1.5, "structural": {"role": "reaction"}}
        ]
    }
    
    prop_b = {
        "proposal_id": f"PROP_B_{uuid.uuid4().hex[:4].upper()}",
        "mode": "B",
        "duration": 18.0,
        "rerank_score": 0.49,
        "human_reality_score_data": {
            "human_reality_score": 0.65,
            "metrics": {"narrative_flow": 0.6, "visual_stability": 0.7}
        },
        "sequence": [
            {"fragment_id": f"FRAG_L_1_{uuid.uuid4().hex[:4].upper()}", "duration": 6.0, "structural": {"role": "action"}},
            {"fragment_id": f"FRAG_L_2_{uuid.uuid4().hex[:4].upper()}", "duration": 4.0, "structural": {"role": "main"}}
        ]
    }
    
    # Check initial database state
    db = SessionLocal()
    try:
        initial_weak_labels = db.query(WeakLabelTable).count()
        initial_coaching_logs = db.query(UserEditDecisionTable).filter_by(decision_type="TEACHER_COACHING").count()
        print(f"Initial DB state: weak_labels={initial_weak_labels}, coaching_logs={initial_coaching_logs}")
    finally:
        db.close()
        
    # 2. Run coaching under uncertainty (should trigger coaching)
    print("\n--- Running Coach Student If Uncertain (Uncertainty High) ---")
    result = TeacherMentor.coach_student_if_uncertain(project_id, prop_a, prop_b)
    print(f"Coaching result: {result}")
    
    assert result["status"] == "coached", "Coaching should have been triggered due to high uncertainty!"
    assert "decision_id" in result, "Coaching result should contain decision_id"
    
    # 3. Run coaching under low uncertainty (should skip coaching)
    print("\n--- Running Coach Student If Uncertain (Uncertainty Low) ---")
    prop_a_low = prop_a.copy()
    prop_a_low["rerank_score"] = 0.85 # diff = 0.85 - 0.49 = 0.36 > 0.04
    result_low = TeacherMentor.coach_student_if_uncertain(project_id, prop_a_low, prop_b)
    print(f"Coaching result (low uncertainty): {result_low}")
    assert result_low["status"] == "skipped", "Coaching should have been skipped due to low uncertainty!"

    # 4. Verify DB updates
    print("\n--- Verifying Database Updates ---")
    db = SessionLocal()
    try:
        # Check weak labels injected
        wl_good = db.query(WeakLabelTable).filter_by(source_id=project_id, label_name="teacher_coached_good").all()
        wl_bad = db.query(WeakLabelTable).filter_by(source_id=project_id, label_name="teacher_coached_bad").all()
        print(f"Injected 'teacher_coached_good' count: {len(wl_good)}")
        print(f"Injected 'teacher_coached_bad' count: {len(wl_bad)}")
        
        assert len(wl_good) == len(prop_a["sequence"]), f"Expected {len(prop_a['sequence'])} 'good' weak labels"
        assert len(wl_bad) == len(prop_b["sequence"]), f"Expected {len(prop_b['sequence'])} 'bad' weak labels"
        
        # Check coaching log in UserEditDecisionTable
        logs = db.query(UserEditDecisionTable).filter_by(project_id=project_id, decision_type="TEACHER_COACHING").all()
        print(f"Logged coaching events: {len(logs)}")
        assert len(logs) == 1, "Expected 1 coaching log event in DB"
        print(f"Coaching log detail: decision_id={logs[0].decision_id}, details={logs[0].user_intent}")
        
        # Check pattern memory updates
        pats = db.query(EditingPatternMemoryTable).all()
        print("\n--- Current Pattern Memory State ---")
        for p in pats:
            print(f"Pattern: {p.pattern_type} | Success: {p.success_count} | Acceptance: {p.avg_user_acceptance}")
            
    finally:
        db.close()
        
    print("\n==================================================")
    print("[SUCCESS] All Teacher-Student Mentorship tests passed!")
    print("==================================================")

if __name__ == "__main__":
    run_teacher_mentorship_test()
