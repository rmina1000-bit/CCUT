import os
import sys
from pathlib import Path

# Add backend to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import SessionLocal
from learning.learning_models import UserEditDecisionTable, PreferencePairTable, WeakLabelTable, EditingPatternMemoryTable

def main():
    print("=== CCUT 1.0.4 Poor-Man Learning Memory Inspector ===")
    
    db = SessionLocal()
    try:
        # 1. Inspect Patterns
        patterns = db.query(EditingPatternMemoryTable).all()
        print(f"\n[PATTERNS] Total Patterns Registered: {len(patterns)}")
        print("-" * 70)
        print(f"{'Pattern Type':<20} | {'Success':<8} | {'Failure':<8} | {'Acceptance':<10} | {'HRS Delta':<10}")
        print("-" * 70)
        for p in patterns:
            print(f"{p.pattern_type:<20} | {p.success_count:<8} | {p.failure_count:<8} | {p.avg_user_acceptance:<10.2f} | {p.avg_hrs_delta:<10.4f}")
            
        # 2. Inspect Decisions
        decisions = db.query(UserEditDecisionTable).all()
        print(f"\n[DECISIONS] Total Decisions Logged: {len(decisions)}")
        dec_types = {}
        for d in decisions:
            dec_types[d.decision_type] = dec_types.get(d.decision_type, 0) + 1
        for k, v in dec_types.items():
            print(f" - {k}: {v} logs")
            
        # 3. Inspect Preference Pairs
        pairs = db.query(PreferencePairTable).all()
        print(f"\n[PREFERENCE PAIRS] Total Preference Pairs: {len(pairs)}")
        pair_hints = {}
        for p in pairs:
            pair_hints[p.reason_hint] = pair_hints.get(p.reason_hint, 0) + 1
        for k, v in pair_hints.items():
            print(f" - {k}: {v} records")
            
        # 4. Inspect Weak Labels
        labels = db.query(WeakLabelTable).all()
        print(f"\n[WEAK LABELS] Total Weak Labels: {len(labels)}")
        label_names = {}
        for l in labels:
            label_names[l.label_name] = label_names.get(l.label_name, 0) + 1
        for k, v in label_names.items():
            print(f" - {k}: {v} labels")
            
    except Exception as e:
        print(f"[INSPECT ERROR] {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
