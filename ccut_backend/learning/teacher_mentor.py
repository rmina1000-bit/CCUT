import uuid
import datetime
from database import SessionLocal
from .learning_models import UserEditDecisionTable
from .active_learning_selector import ActiveLearningSelector
from .teacher_ai_evaluator import TeacherAIEvaluator

class TeacherMentor:
    """
    [STEP 16] TeacherMentor Orchestrator
    Manages active uncertainty coaching triggers.
    Runs TeacherAIEvaluator when Student heuristics demonstrate high entropy (diff <= 0.04).
    Logs interventions under type "TEACHER_COACHING" inside UserEditDecisionTable.
    """

    @staticmethod
    def coach_student_if_uncertain(project_id: str, prop_a: dict, prop_b: dict) -> dict:
        """
        Evaluates the proposals with the Teacher if the Student shows high uncertainty.
        Saves the decision log with type "TEACHER_COACHING".
        """
        # Determine uncertainty via ActiveLearningSelector
        is_uncertain = ActiveLearningSelector.should_trigger_active_question(prop_a, prop_b)
        
        if not is_uncertain:
            print(f"[TEACHER MENTOR] Low uncertainty for project {project_id}. Skipping teacher intervention.")
            return {
                "status": "skipped",
                "reason": "Entropy low. Student confidence sufficient."
            }
            
        print(f"[TEACHER MENTOR] Uncertainty detected. Launching Teacher Coaching Intervention.")
        
        # Invoke Teacher AI Evaluation
        eval_result = TeacherAIEvaluator.evaluate_proposals_via_teacher(project_id, prop_a, prop_b)
        
        preferred = eval_result.get("preferred_mode")
        reason = eval_result.get("reason")
        confidence = eval_result.get("confidence")
        
        # Save coaching intervention record to DB
        db = SessionLocal()
        decision_id = f"DEC_TCH_{uuid.uuid4().hex[:8].upper()}"
        
        winner_prop = prop_a if preferred == "A" else prop_b
        loser_prop = prop_b if preferred == "A" else prop_a
        
        chosen_fids = [f.get("fragment_id") for f in winner_prop.get("sequence", [])]
        rejected_fids = [f.get("fragment_id") for f in loser_prop.get("sequence", [])]
        
        try:
            coaching_log = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=project_id,
                chosen_proposal_id=winner_prop.get("proposal_id"),
                rejected_proposal_id=loser_prop.get("proposal_id"),
                user_intent={
                    "teacher_reason": reason,
                    "confidence": confidence,
                    "preferred_mode": preferred
                },
                selected_fragments=chosen_fids,
                rejected_fragments=rejected_fids,
                decision_type="TEACHER_COACHING"
            )
            db.add(coaching_log)
            db.commit()
            print(f"[TEACHER MENTOR] Logged coaching intervention {decision_id} for project {project_id}")
        except Exception as e:
            db.rollback()
            print(f"[TEACHER MENTOR][ERROR] Failed to save coaching intervention log: {e}")
        finally:
            db.close()
            
        return {
            "status": "coached",
            "decision_id": decision_id,
            "evaluation": eval_result
        }

    @staticmethod
    def get_coaching_logs() -> list:
        """
        Fetches all logged coaching interventions from database.
        """
        db = SessionLocal()
        try:
            rows = db.query(UserEditDecisionTable).filter_by(decision_type="TEACHER_COACHING").all()
            logs = []
            for r in rows:
                logs.append({
                    "decision_id": r.decision_id,
                    "project_id": r.project_id,
                    "winner_proposal_id": r.chosen_proposal_id,
                    "loser_proposal_id": r.rejected_proposal_id,
                    "coaching_details": r.user_intent,
                    "selected_fragments": r.selected_fragments,
                    "rejected_fragments": r.rejected_fragments,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
            return logs
        except Exception as e:
            print(f"[TEACHER MENTOR][ERROR] Failed to fetch coaching logs: {e}")
            return []
        finally:
            db.close()
