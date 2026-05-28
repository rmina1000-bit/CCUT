import uuid
import datetime
from sqlalchemy.orm import Session
from .learning_models import PreferencePairTable

class PreferencePairBuilder:
    """
    [STEP 14-A/C] PreferencePairBuilder
    Structures proposal pairs into comparison datasets mapping winner vs loser characteristics.
    Used as preference training data for the ranking heuristics.
    """

    @staticmethod
    def build_and_save_pair(db: Session, project_id: str, winner_prop: dict, loser_prop: dict, reason_hint: str = "user_choice") -> str:
        """
        Extracts sequence details and Human Reality metrics to save as a preference pair.
        """
        pair_id = f"PRP_{uuid.uuid4().hex[:8].upper()}"
        
        # Extract sequences safely
        winner_seq = []
        for f in winner_prop.get("sequence", []):
            winner_seq.append({
                "fragment_id": f.get("fragment_id"),
                "source_id": f.get("source_id"),
                "start": float(f.get("start", f.get("start_time", 0.0))),
                "end": float(f.get("end", f.get("end_time", 0.0))),
                "duration": float(f.get("duration", 0.0))
            })
            
        loser_seq = []
        for f in loser_prop.get("sequence", []):
            loser_seq.append({
                "fragment_id": f.get("fragment_id"),
                "source_id": f.get("source_id"),
                "start": float(f.get("start", f.get("start_time", 0.0))),
                "end": float(f.get("end", f.get("end_time", 0.0))),
                "duration": float(f.get("duration", 0.0))
            })

        # Extract HRS metrics safely
        winner_hrs = winner_prop.get("human_reality_score_data", {}).get("metrics") or {}
        loser_hrs = loser_prop.get("human_reality_score_data", {}).get("metrics") or {}

        pair_row = PreferencePairTable(
            pair_id=pair_id,
            project_id=project_id,
            winner_proposal_id=winner_prop.get("proposal_id", "A"),
            loser_proposal_id=loser_prop.get("proposal_id", "B"),
            winner_sequence=winner_seq,
            loser_sequence=loser_seq,
            winner_metrics=winner_hrs,
            loser_metrics=loser_hrs,
            reason_hint=reason_hint
        )
        
        db.merge(pair_row)
        db.commit()
        
        print(f"[PREFERENCE BUILDER] Saved preference pair: {pair_id} for project={project_id} (Reason: {reason_hint})")
        return pair_id
