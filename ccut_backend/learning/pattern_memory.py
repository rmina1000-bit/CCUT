import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from .learning_models import EditingPatternMemoryTable

class PatternMemory:
    """
    [STEP 14-C] PatternMemory
    Maintains a repository of editing patterns in ccut_app.db.
    Tracks success rates, user acceptance deltas, and stores recommendation parameters.
    """

    @staticmethod
    def record_pattern_feedback(pattern_type: str, success: bool, hrs_delta: float = 0.0) -> bool:
        """
        Increments success or failure counters and updates user acceptance ratio.
        """
        db: Session = SessionLocal()
        try:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pattern_type).first()
            if not row:
                # Initialize default pattern entry if not found
                pattern_id = f"PAT_{pattern_type.upper()}"
                row = EditingPatternMemoryTable(
                    pattern_id=pattern_id,
                    pattern_type=pattern_type,
                    conditions={},
                    recommended_action={"multiplier": 1.0},
                    success_count=0,
                    failure_count=0,
                    avg_user_acceptance=0.5,
                    avg_hrs_delta=0.0
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
                
            # Update running average of HRS delta contribution
            row.avg_hrs_delta = round((row.avg_hrs_delta * (total - 1) + hrs_delta) / total, 4)
            row.updated_at = datetime.datetime.now()
            
            db.commit()
            print(f"[PATTERN MEMORY] Updated feedback for {pattern_type}: Success={success} | Acceptance={row.avg_user_acceptance:.2f}")
            return True
        except Exception as e:
            db.rollback()
            print(f"[PATTERN MEMORY][ERROR] Failed to record pattern feedback: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_pattern_multiplier(pattern_type: str) -> float:
        """
        Returns a score multiplier based on historical user acceptance rates.
        """
        db: Session = SessionLocal()
        try:
            row = db.query(EditingPatternMemoryTable).filter_by(pattern_type=pattern_type).first()
            if row:
                # If acceptance is high, return positive boost; if low, return penalty
                acc = row.avg_user_acceptance
                if acc > 0.65:
                    return 1.15
                elif acc < 0.35:
                    return 0.80
            return 1.0
        except Exception as e:
            print(f"[PATTERN MEMORY][ERROR] Failed to fetch pattern multiplier: {e}")
            return 1.0
        finally:
            db.close()
            
    @staticmethod
    def get_all_patterns() -> list:
        """
        Returns all registered pattern records.
        """
        db: Session = SessionLocal()
        try:
            rows = db.query(EditingPatternMemoryTable).all()
            return [{
                "pattern_type": r.pattern_type,
                "success_count": r.success_count,
                "failure_count": r.failure_count,
                "avg_user_acceptance": r.avg_user_acceptance,
                "avg_hrs_delta": r.avg_hrs_delta
            } for r in rows]
        except Exception as e:
            print(f"[PATTERN MEMORY][ERROR] Failed to fetch patterns list: {e}")
            return []
        finally:
            db.close()
