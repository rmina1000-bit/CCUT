import uuid
import datetime
from database import SessionLocal
from .learning_models import UserEditDecisionTable
from .pattern_memory import PatternMemory

class ContrastLearner:
    """
    [STEP 17] Success-Failure Contrast Learner
    Performs Reverse Editing Analysis to contrast high-performance
    editing rhythm patterns with low-performance ones.
    """

    @staticmethod
    def execute_contrast_learning_session(query: str, limit: int = 2) -> dict:
        """
        Runs a contrast learning loop by extracting metadata features from High-performing (Success)
        and Low-performing (Failure) video styles, updating CCUT student weights accordingly.
        """
        print(f"[CONTRAST LEARNER] Launching success-failure contrast learning for query: '{query}'")
        
        # In a real environment, we search YouTube for high-view (Success) vs low-view (Failure) videos.
        # Here we model this reverse editing analysis based on views criteria.
        
        # 1. Simulate High-Performing (Success) Editing Profile
        # Typically features high hook density, tight silence gaps, and active reaction pacing.
        success_profile = {
            "query": query,
            "profile_type": "SUCCESS",
            "avg_view_count": 850000,
            "metrics": {
                "hook_density": 0.85,       # High hook focus
                "silence_gap_ratio": 0.05,   # Low dead time
                "reaction_spacing": 2.2,     # Tight reactions
                "scene_rhythm_speed": 1.8    # Fast cuts
            },
            "patterns": ["hook_3sec", "reaction_hold", "scenery_bridge"]
        }
        
        # 2. Simulate Low-Performing (Failure) Editing Profile
        # Typically features low hook density, large silence gaps, and long static pacing.
        failure_profile = {
            "query": query,
            "profile_type": "FAILURE",
            "avg_view_count": 450,
            "metrics": {
                "hook_density": 0.20,       # Weak intro
                "silence_gap_ratio": 0.28,   # High dead time
                "reaction_spacing": 8.5,     # Loose reactions
                "scene_rhythm_speed": 6.2    # Extremely slow cuts
            },
            "patterns": ["boredom_prevent"]  # Failed patterns causing abandonment
        }
        
        db = SessionLocal()
        decision_id = f"DEC_CTR_{uuid.uuid4().hex[:8].upper()}"
        
        try:
            # 3. Apply Contrastive Tuning:
            # - Reward Success patterns (+0.08 positive boost)
            for pat in success_profile["patterns"]:
                PatternMemory.record_pattern_feedback(pattern_type=pat, success=True, hrs_delta=0.08)
                
            # - Penalize Failure patterns (Mark as failure to decrease user acceptance ratio)
            for pat in failure_profile["patterns"]:
                # Record as failure to reduce target linear multipliers
                PatternMemory.record_pattern_feedback(pattern_type=pat, success=False, hrs_delta=-0.06)
            
            # 4. Save learning event
            decision_row = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=f"CTR_{uuid.uuid4().hex[:6].upper()}",
                chosen_proposal_id="PROFILE_SUCCESS",
                rejected_proposal_id="PROFILE_FAILURE",
                user_intent={
                    "query": query,
                    "success_metrics": success_profile["metrics"],
                    "failure_metrics": failure_profile["metrics"],
                    "contrastive_tuning": "Applied"
                },
                selected_fragments=success_profile["patterns"],
                rejected_fragments=failure_profile["patterns"],
                decision_type="CONTRAST_LEARN"
            )
            db.add(decision_row)
            db.commit()
            print(f"[CONTRAST LEARNER] Logged contrast session {decision_id} successfully.")
            
        except Exception as e:
            db.rollback()
            print(f"[CONTRAST LEARNER][ERROR] Failed to execute contrast learning: {e}")
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()
            
        return {
            "status": "SUCCESS",
            "decision_id": decision_id,
            "success_patterns_boosted": success_profile["patterns"],
            "failure_patterns_penalized": failure_profile["patterns"]
        }

    @staticmethod
    def get_contrast_logs() -> list:
        """
        Retrieves historical contrastive learning logs.
        """
        db = SessionLocal()
        try:
            rows = db.query(UserEditDecisionTable).filter_by(decision_type="CONTRAST_LEARN").all()
            logs = []
            for r in rows:
                logs.append({
                    "decision_id": r.decision_id,
                    "query": r.user_intent.get("query") if r.user_intent else "",
                    "success_metrics": r.user_intent.get("success_metrics") if r.user_intent else {},
                    "failure_metrics": r.user_intent.get("failure_metrics") if r.user_intent else {},
                    "boosted": r.selected_fragments,
                    "penalized": r.rejected_fragments,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
            return logs
        except Exception as e:
            print(f"[CONTRAST LEARNER][ERROR] Failed to fetch contrast logs: {e}")
            return []
        finally:
            db.close()
