import uuid
import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from .learning_models import UserEditDecisionTable
from .preference_pair_builder import PreferencePairBuilder

class DecisionLogger:
    """
    [STEP 14-A] DecisionLogger
    Intercepts and logs user editing choices, proposal acceptances, and manual PBE boundary shifts.
    Crucial for accumulating poor-man preference loops.
    """
    
    @staticmethod
    def log_user_proposal_choice(project_id: str, chosen_mode: str, proposals: list) -> bool:
        """
        Logs which proposal (A or B) the user accepted, records Intent, and generates Preference Pairs.
        """
        db: Session = SessionLocal()
        try:
            chosen_prop = next((p for p in proposals if p.get("mode") == chosen_mode), None)
            rejected_prop = next((p for p in proposals if p.get("mode") != chosen_mode), None)
            
            if not chosen_prop:
                print(f"[DECISION LOGGER][WARN] Chosen proposal {chosen_mode} not found in proposal pool.")
                return False
                
            decision_id = f"DEC_{uuid.uuid4().hex[:8].upper()}"
            intent_data = chosen_prop.get("original_reason", {}).get("user_intent") or chosen_prop.get("proposal_explanation", {})
            
            chosen_fids = [f.get("fragment_id") for f in chosen_prop.get("sequence", [])]
            rejected_fids = [f.get("fragment_id") for f in rejected_prop.get("sequence", [])] if rejected_prop else []
            
            # 1. Save edit decision
            decision_row = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=project_id,
                chosen_proposal_id=chosen_prop.get("proposal_id"),
                rejected_proposal_id=rejected_prop.get("proposal_id") if rejected_prop else None,
                user_intent=intent_data,
                selected_fragments=chosen_fids,
                rejected_fragments=rejected_fids,
                decision_type="A_CHOSEN" if chosen_mode == "A" else "B_CHOSEN"
            )
            db.add(decision_row)
            db.commit()
            
            # 2. Build Preference Pair if rejected proposal exists
            if rejected_prop:
                PreferencePairBuilder.build_and_save_pair(
                    db=db,
                    project_id=project_id,
                    winner_prop=chosen_prop,
                    loser_prop=rejected_prop,
                    reason_hint="user_chose_" + chosen_mode.lower()
                )
                
                # 3. Update Pattern Memory weights based on chosen vs rejected proposals
                try:
                    from .pattern_memory import PatternMemory
                    
                    def get_active_patterns(prop):
                        seq = prop.get("sequence", [])
                        roles = [f.get("structural", {}).get("role", "main") for f in seq]
                        active = set()
                        # reaction_hold: reaction count > 2
                        if roles.count("reaction") > 2:
                            active.add("reaction_hold")
                        # scenery_bridge: scenery count > 2
                        if roles.count("scenery") > 2:
                            active.add("scenery_bridge")
                        # hook_3sec: has a hook role at start
                        if roles and roles[0] == "hook":
                            active.add("hook_3sec")
                        return active
                        
                    winner_pats = get_active_patterns(chosen_prop)
                    loser_pats = get_active_patterns(rejected_prop)
                    
                    w_hrs = chosen_prop.get("human_reality_score_data", {}).get("human_reality_score", 0.5) if isinstance(chosen_prop.get("human_reality_score_data"), dict) else 0.5
                    l_hrs = rejected_prop.get("human_reality_score_data", {}).get("human_reality_score", 0.5) if isinstance(rejected_prop.get("human_reality_score_data"), dict) else 0.5
                    hrs_delta = w_hrs - l_hrs
                    
                    # For patterns active in winner: success
                    for wp in winner_pats:
                        PatternMemory.record_pattern_feedback(pattern_type=wp, success=True, hrs_delta=hrs_delta)
                        
                    # For patterns active in loser but NOT in winner: failure
                    for lp in (loser_pats - winner_pats):
                        PatternMemory.record_pattern_feedback(pattern_type=lp, success=False, hrs_delta=0.0)
                except Exception as pat_err:
                    print(f"[DECISION LOGGER][ERROR] Failed to update pattern memory feedback: {pat_err}")
                
            print(f"[DECISION LOGGER] Logged user acceptance choice: Chosen={chosen_mode} for project={project_id}")
            return True
        except Exception as e:
            db.rollback()
            print(f"[DECISION LOGGER][ERROR] Failed to log user choice: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def log_pbe_manual_edit(project_id: str, fragment_id: str, before_start: float, before_end: float, after_start: float, after_end: float) -> bool:
        """
        Logs manual boundary corrections made by users in PBE (Precision Boundary Editor).
        These deltas represent AI prediction errors.
        """
        db: Session = SessionLocal()
        try:
            decision_id = f"DEC_PBE_{uuid.uuid4().hex[:8].upper()}"
            delta_left = after_start - before_start
            delta_right = after_end - before_end
            
            # Ignore micro adjustments less than 0.05 seconds
            if abs(delta_left) < 0.05 and abs(delta_right) < 0.05:
                return False
                
            delta_log = {
                "fragment_id": fragment_id,
                "before_start": round(before_start, 3),
                "before_end": round(before_end, 3),
                "after_start": round(after_start, 3),
                "after_end": round(after_end, 3),
                "delta_left": round(delta_left, 3),
                "delta_right": round(delta_right, 3)
            }
            
            decision_row = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=project_id,
                chosen_proposal_id=None,
                rejected_proposal_id=None,
                user_intent=None,
                selected_fragments=[fragment_id],
                rejected_fragments=None,
                decision_type="PBE_EDIT",
                delta_log=delta_log
            )
            db.add(decision_row)
            db.commit()
            print(f"[DECISION LOGGER] Logged PBE manual edit: Frag={fragment_id} DeltaLeft={delta_left:.2f}s DeltaRight={delta_right:.2f}s")
            return True
        except Exception as e:
            db.rollback()
            print(f"[DECISION LOGGER][ERROR] Failed to log PBE edit: {e}")
            return False
        finally:
            db.close()
