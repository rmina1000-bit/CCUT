import uuid
import datetime
from database import SessionLocal
from .learning_models import HumanWatchSessionTable, UserEditDecisionTable
from .pattern_memory import PatternMemory

class HumanWatchSession:
    """
    [STEP 19] Human Watch Session System
    Logs real-world player activities (skips, rewatches, pauses)
    and maps them to editing pattern retention scores.
    """

    @staticmethod
    def log_watch_session(project_id: str, viewer_id: str, playback_actions: list, retention_map: dict) -> dict:
        """
        Saves a viewer's playback actions and updates pattern memory weights
        based on the actual retention rates per fragment.
        """
        session_id = f"WCH_{uuid.uuid4().hex[:8].upper()}"
        db = SessionLocal()
        
        try:
            # 1. Store the watch session record
            session_row = HumanWatchSessionTable(
                session_id=session_id,
                project_id=project_id,
                viewer_id=viewer_id,
                playback_actions=playback_actions,
                retention_map=retention_map
            )
            db.add(session_row)
            db.commit()
            print(f"[HUMAN WATCH] Saved watch session {session_id} for project {project_id}")
            
            # 2. Update pattern memory weights based on retention rates
            # We map fragments to their editing pattern types. In production, we query FragmentTable.
            # Here we apply heuristic mapping for demonstration & integration testing:
            # - If fragment name starts with "FRAG_REAC" -> reaction_hold
            # - If fragment name starts with "FRAG_SCE" -> scenery_bridge
            # - If fragment name starts with "FRAG_HOOK" -> hook_3sec
            
            tuned_patterns = {}
            for frag_id, retention in retention_map.items():
                pattern_type = None
                if "REAC" in frag_id:
                    pattern_type = "reaction_hold"
                elif "SCE" in frag_id:
                    pattern_type = "scenery_bridge"
                elif "HOOK" in frag_id:
                    pattern_type = "hook_3sec"
                else:
                    # Default mapping for testing
                    pattern_type = "reaction_hold"
                    
                if pattern_type:
                    # High retention (>=1.0) -> Boost success
                    if retention >= 1.0:
                        PatternMemory.record_pattern_feedback(pattern_type, success=True, hrs_delta=0.08)
                        tuned_patterns[pattern_type] = "boosted"
                    # Low retention (<0.3) -> Penalize with failure
                    elif retention < 0.3:
                        PatternMemory.record_pattern_feedback(pattern_type, success=False, hrs_delta=-0.05)
                        tuned_patterns[pattern_type] = "penalized"
            
            # 3. Save a log event to user_edit_decisions
            decision_id = f"DEC_WCH_{uuid.uuid4().hex[:8].upper()}"
            decision_row = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=project_id,
                chosen_proposal_id=session_id,
                rejected_proposal_id=None,
                user_intent={
                    "viewer_id": viewer_id,
                    "playback_actions": playback_actions,
                    "retention_map": retention_map,
                    "tuned_patterns": tuned_patterns
                },
                selected_fragments=list(retention_map.keys()),
                rejected_fragments=[],
                decision_type="HUMAN_WATCH_LOG"
            )
            db.add(decision_row)
            db.commit()
            print(f"[HUMAN WATCH] Logged watch session decision: {decision_id}")
            
            return {
                "status": "SUCCESS",
                "session_id": session_id,
                "decision_id": decision_id,
                "tuned_patterns": tuned_patterns
            }
        except Exception as e:
            db.rollback()
            print(f"[HUMAN WATCH][ERROR] Failed to save watch session: {e}")
            return {"status": "ERROR", "message": str(e)}
        finally:
            db.close()

    @staticmethod
    def get_watch_logs() -> list:
        """
        Retrieves historical human watch sessions.
        """
        db = SessionLocal()
        try:
            rows = db.query(HumanWatchSessionTable).all()
            logs = []
            for r in rows:
                logs.append({
                    "session_id": r.session_id,
                    "project_id": r.project_id,
                    "viewer_id": r.viewer_id,
                    "playback_actions": r.playback_actions,
                    "retention_map": r.retention_map,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
            return logs
        except Exception as e:
            print(f"[HUMAN WATCH][ERROR] Failed to fetch watch logs: {e}")
            return []
        finally:
            db.close()
