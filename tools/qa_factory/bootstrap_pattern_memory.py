import os
import sys
from pathlib import Path

# Add backend to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import SessionLocal
from learning.learning_models import EditingPatternMemoryTable, init_learning_db

INITIAL_PATTERNS = [
    {
        "pattern_id": "PAT_REACTION_HOLD",
        "pattern_type": "reaction_hold",
        "conditions": {"role": "reaction", "min_duration": 1.2, "max_duration": 3.5},
        "recommended_action": {"multiplier": 1.25},
        "avg_user_acceptance": 0.72 # YouTube Vlog standard bias
    },
    {
        "pattern_id": "PAT_SCENERY_BRIDGE",
        "pattern_type": "scenery_bridge",
        "conditions": {"role": "scenery", "source_switch": True},
        "recommended_action": {"multiplier": 1.15},
        "avg_user_acceptance": 0.68
    },
    {
        "pattern_id": "PAT_HOOK_3SEC",
        "pattern_type": "hook_3sec",
        "conditions": {"elapsed_time": 3.0, "role": "hook"},
        "recommended_action": {"multiplier": 1.35},
        "avg_user_acceptance": 0.81
    },
    {
        "pattern_id": "PAT_BOREDOM_PREVENT",
        "pattern_type": "boredom_prevent",
        "conditions": {"max_scenery_duration": 6.0},
        "recommended_action": {"multiplier": 0.75},
        "avg_user_acceptance": 0.70
    }
]

def main():
    print("[BOOTSTRAP] Initializing learning SQLite databases...")
    init_learning_db()
    
    db = SessionLocal()
    try:
        for pat in INITIAL_PATTERNS:
            existing = db.query(EditingPatternMemoryTable).filter_by(pattern_id=pat["pattern_id"]).first()
            if existing:
                existing.pattern_type = pat["pattern_type"]
                existing.conditions = pat["conditions"]
                existing.recommended_action = pat["recommended_action"]
                existing.avg_user_acceptance = pat["avg_user_acceptance"]
            else:
                row = EditingPatternMemoryTable(
                    pattern_id=pat["pattern_id"],
                    pattern_type=pat["pattern_type"],
                    conditions=pat["conditions"],
                    recommended_action=pat["recommended_action"],
                    success_count=10,
                    failure_count=4,
                    avg_user_acceptance=pat["avg_user_acceptance"]
                )
                db.add(row)
        db.commit()
        print(f"[BOOTSTRAP] Successfully seeded/updated {len(INITIAL_PATTERNS)} default pattern parameters.")
    except Exception as e:
        db.rollback()
        print(f"[BOOTSTRAP][ERROR] Seeding failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
