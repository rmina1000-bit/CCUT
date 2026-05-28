import uuid
import datetime
import hashlib
import json
from database import SessionLocal
from .learning_models import TemporalFlowMemoryTable, UserEditDecisionTable

class TemporalFlowLearner:
    """
    [STEP 18] Temporal Narrative Flow Learner
    Analyzes sequence-level transitions (e.g. Hook -> Setup -> Tension -> Payoff)
    and updates flow acceptance rates.
    """

    @staticmethod
    def get_flow_hash(flow_sequence: list) -> str:
        """
        Generates a unique deterministic hash ID for a given sequence flow list.
        """
        serialized = json.dumps([str(s).lower() for s in flow_sequence])
        return f"FLW_{hashlib.md5(serialized.encode('utf-8')).hexdigest()[:8].upper()}"

    @staticmethod
    def record_flow_feedback(flow_sequence: list, success: bool) -> bool:
        """
        Increments success or failure count for a temporal flow sequence template.
        """
        if not flow_sequence:
            return False
            
        flow_id = TemporalFlowLearner.get_flow_hash(flow_sequence)
        db = SessionLocal()
        
        try:
            row = db.query(TemporalFlowMemoryTable).filter_by(flow_id=flow_id).first()
            if not row:
                row = TemporalFlowMemoryTable(
                    flow_id=flow_id,
                    flow_sequence=flow_sequence,
                    success_count=0,
                    failure_count=0,
                    avg_user_acceptance=0.5
                )
                db.add(row)
                db.flush()
                
            if success:
                row.success_count += 1
            else:
                row.failure_count += 1
                
            total = row.success_count + row.failure_count
            if total > 0:
                row.avg_user_acceptance = round(row.success_count / total, 3)
                
            row.updated_at = datetime.datetime.now()
            db.commit()
            print(f"[TEMPORAL FLOW] Updated flow {flow_id} {flow_sequence}: Success={success} | Acceptance={row.avg_user_acceptance:.2f}")
            return True
        except Exception as e:
            db.rollback()
            print(f"[TEMPORAL FLOW][ERROR] Failed to record flow feedback: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_flow_multiplier(flow_sequence: list) -> float:
        """
        Returns a flow pacing multiplier based on historical user acceptance.
        """
        if not flow_sequence:
            return 1.0
            
        flow_id = TemporalFlowLearner.get_flow_hash(flow_sequence)
        db = SessionLocal()
        try:
            row = db.query(TemporalFlowMemoryTable).filter_by(flow_id=flow_id).first()
            if row:
                acc = row.avg_user_acceptance
                if acc > 0.65:
                    return 1.20
                elif acc < 0.35:
                    return 0.75
            return 1.0
        except Exception as e:
            print(f"[TEMPORAL FLOW][ERROR] Failed to fetch flow multiplier: {e}")
            return 1.0
        finally:
            db.close()

    @staticmethod
    def analyze_and_learn_proposal_flow(project_id: str, proposal: dict, success: bool) -> dict:
        """
        Extracts structural role flow sequence from a proposal and learns the transition pattern.
        Logs the event to UserEditDecisionTable.
        """
        seq = proposal.get("sequence", [])
        flow_sequence = []
        
        # Mapping sequence clip roles into flow segments
        for idx, f in enumerate(seq):
            role = f.get("structural", {}).get("role", "main")
            duration = float(f.get("duration", f.get("duration_sec", 5.0)))
            
            # Identify Hook state
            if idx == 0 and duration <= 3.0:
                flow_sequence.append("hook")
            elif role == "scenery":
                flow_sequence.append("setup")
            elif role == "action":
                flow_sequence.append("tension")
            elif role == "reaction":
                flow_sequence.append("payoff")
            else:
                flow_sequence.append("pause" if duration > 6.0 else "setup")
                
        if not flow_sequence:
            flow_sequence = ["setup"]
            
        # Record feedback in DB
        success_recorded = TemporalFlowLearner.record_flow_feedback(flow_sequence, success)
        
        db = SessionLocal()
        decision_id = f"DEC_FLW_{uuid.uuid4().hex[:8].upper()}"
        try:
            decision_row = UserEditDecisionTable(
                decision_id=decision_id,
                project_id=project_id,
                chosen_proposal_id=proposal.get("proposal_id") if success else None,
                rejected_proposal_id=None if success else proposal.get("proposal_id"),
                user_intent={
                    "flow_sequence": flow_sequence,
                    "success": success,
                    "proposal_details": {
                        "mode": proposal.get("mode"),
                        "duration": proposal.get("duration")
                    }
                },
                selected_fragments=flow_sequence if success else [],
                rejected_fragments=[] if success else flow_sequence,
                decision_type="TEMPORAL_FLOW_LEARN"
            )
            db.add(decision_row)
            db.commit()
            print(f"[TEMPORAL FLOW] Logged flow learning decision: {decision_id}")
        except Exception as e:
            db.rollback()
            print(f"[TEMPORAL FLOW][ERROR] Failed to log flow learning decision: {e}")
        finally:
            db.close()
            
        return {
            "status": "SUCCESS",
            "decision_id": decision_id,
            "flow_sequence": flow_sequence,
            "flow_hash": TemporalFlowLearner.get_flow_hash(flow_sequence),
            "success": success
        }

    @staticmethod
    def get_flow_logs() -> list:
        """
        Retrieves all temporal flow learning logs.
        """
        db = SessionLocal()
        try:
            rows = db.query(UserEditDecisionTable).filter_by(decision_type="TEMPORAL_FLOW_LEARN").all()
            logs = []
            for r in rows:
                logs.append({
                    "decision_id": r.decision_id,
                    "project_id": r.project_id,
                    "flow_sequence": r.user_intent.get("flow_sequence") if r.user_intent else [],
                    "success": r.user_intent.get("success") if r.user_intent else False,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
            return logs
        except Exception as e:
            print(f"[TEMPORAL FLOW][ERROR] Failed to fetch flow logs: {e}")
            return []
        finally:
            db.close()
