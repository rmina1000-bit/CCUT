from database import SessionLocal
from .learning_models import WeakLabelTable, UserEditDecisionTable
from .pattern_memory import PatternMemory

class ProposalRanker:
    """
    [STEP 14-D] ProposalRanker
    Acts as a post-generation reranking model. Computes dynamic preference weights
    on CPU based on historical user choices, weak labels, and PBE manual adjustments.
    """

    @staticmethod
    def rerank_proposals(proposals: list) -> list:
        """
        Takes a list of proposals, calculates reranking scores, and appends preference details.
        """
        if not proposals:
            return []

        db = SessionLocal()
        try:
            for p in proposals:
                seq = p.get("sequence", [])
                mode = p.get("mode", "A")
                
                # Base score is initial duration or base score heuristics
                base_hrs = p.get("human_reality_score_data", {}).get("human_reality_score", 0.5)
                
                pattern_bonus = 1.0
                weak_label_bonus = 1.0
                boundary_penalty = 1.0
                
                # 1. Weak Label Scoring Heuristics
                for f in seq:
                    fid = f.get("fragment_id")
                    # Query weak labels for this fragment
                    w_labels = db.query(WeakLabelTable).filter_by(fragment_id=fid).all()
                    for wl in w_labels:
                        if wl.label_name in ["hook_candidate", "reaction_hold_good"]:
                            # Reward good patterns
                            weak_label_bonus *= (1.0 + (0.05 * wl.confidence))
                        elif wl.label_name in ["boredom_risk", "cognitive_overload_risk", "audio_cut_bad"]:
                            # Penalize poor visual/audio transitions
                            weak_label_bonus *= (1.0 - (0.08 * wl.confidence))
                
                # 2. PBE Delta Shift Penalty/Reward
                # Check if this project or source has PBE edits
                pbe_edits = db.query(UserEditDecisionTable).filter_by(decision_type="PBE_EDIT").all()
                for edit in pbe_edits:
                    d_log = edit.delta_log or {}
                    match_fid = d_log.get("fragment_id")
                    
                    # If this fragment is included in the sequence
                    match_clip = next((c for c in seq if c.get("fragment_id") == match_fid), None)
                    if match_clip:
                        # Check if the sequence respects the adjusted boundary
                        c_start = float(match_clip.get("start", match_clip.get("start_time", 0.0)))
                        c_end = float(match_clip.get("end", match_clip.get("end_time", 0.0)))
                        target_start = float(d_log.get("after_start", 0.0))
                        target_end = float(d_log.get("after_end", 0.0))
                        
                        # If the proposal matches the PBE correction, give it a reward
                        if abs(c_start - target_start) < 0.1 and abs(c_end - target_end) < 0.1:
                            boundary_penalty *= 1.20
                        else:
                            # If it uses the old uncorrected boundary, penalize it slightly
                            boundary_penalty *= 0.90
                            
                # 3. Pattern Memory Multipliers
                role_counts = {}
                for f in seq:
                    r = f.get("structural", {}).get("role", "main")
                    role_counts[r] = role_counts.get(r, 0) + 1
                    
                if role_counts.get("reaction", 0) > 2:
                    pattern_bonus *= PatternMemory.get_pattern_multiplier("reaction_hold")
                if role_counts.get("scenery", 0) > 2:
                    pattern_bonus *= PatternMemory.get_pattern_multiplier("scenery_bridge")
                    
                # Combine scores into a final Reranked Score
                rerank_score = round(base_hrs * pattern_bonus * weak_label_bonus * boundary_penalty, 4)
                
                p["rerank_score"] = rerank_score
                p["rerank_details"] = {
                    "base_hrs": base_hrs,
                    "pattern_bonus": round(pattern_bonus, 3),
                    "weak_label_bonus": round(weak_label_bonus, 3),
                    "boundary_penalty": round(boundary_penalty, 3)
                }
                
                print(f"[LEARNING_RERANK] Proposal Mode={mode} | Base={base_hrs:.3f} | "
                      f"Rerank={rerank_score:.3f} | Details={p['rerank_details']}")
                      
            # Sort proposals based on rerank_score (descending)
            proposals.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            
        except Exception as e:
            print(f"[LEARNING_RERANK][ERROR] Failed to run proposal reranker: {e}")
        finally:
            db.close()
            
        return proposals
