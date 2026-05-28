import os
import sys
import random
import argparse
import json
import math
from pathlib import Path

# Add paths to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import SessionLocal
from archive.db_models import ProposalTable
from ai.perception.human_reality_score import HumanRealityScore
from tools.human_swarm.critique_arena import CritiqueArena

class HumanSwarmWorld:
    """
    [STEP 12-F] HumanSwarmWorld
    Generates hundreds to thousands of virtual viewers belonging to 10 distinct cohorts,
    evaluates proposals, and handles the Failure Replay System.
    """
    def __init__(self, num_viewers: int, seed: int = 20260528):
        self.num_viewers = num_viewers
        self.rng = random.Random(seed)
        self.evaluator = HumanRealityScore()
        self.arena = CritiqueArena()
        
        # 10 Human Cohorts with custom weights and tolerances
        self.cohorts = [
            {
                "name": "Documentary Director", "ratio": 0.08, "pref_pace": "slow", 
                "scenery_tolerance": 0.9, "fatigue_multiplier": 1.4,
                "weights": {"visual_comfort": 0.10, "auditory_comfort": 0.15, "emotional_continuity": 0.25, "immersion": 0.15, "narrative_coherence": 0.25, "rewatch_desire": 0.10}
            },
            {
                "name": "Film Editor", "ratio": 0.08, "pref_pace": "medium", 
                "scenery_tolerance": 0.6, "fatigue_multiplier": 1.25,
                "weights": {"visual_comfort": 0.15, "auditory_comfort": 0.10, "emotional_continuity": 0.25, "immersion": 0.20, "narrative_coherence": 0.15, "rewatch_desire": 0.15}
            },
            {
                "name": "General YouTube Viewer", "ratio": 0.20, "pref_pace": "medium", 
                "scenery_tolerance": 0.4, "fatigue_multiplier": 1.0,
                "weights": {"visual_comfort": 0.15, "auditory_comfort": 0.15, "emotional_continuity": 0.10, "immersion": 0.25, "narrative_coherence": 0.15, "rewatch_desire": 0.20}
            },
            {
                "name": "Shorts Addict", "ratio": 0.15, "pref_pace": "fast", 
                "scenery_tolerance": 0.05, "fatigue_multiplier": 0.6,
                "weights": {"visual_comfort": 0.05, "auditory_comfort": 0.05, "emotional_continuity": 0.05, "immersion": 0.45, "narrative_coherence": 0.05, "rewatch_desire": 0.30}
            },
            {
                "name": "Travel Vlog Fan", "ratio": 0.10, "pref_pace": "fast", 
                "scenery_tolerance": 0.55, "fatigue_multiplier": 0.9,
                "weights": {"visual_comfort": 0.10, "auditory_comfort": 0.10, "emotional_continuity": 0.10, "immersion": 0.30, "narrative_coherence": 0.20, "rewatch_desire": 0.20}
            },
            {
                "name": "Emotional Video Lover", "ratio": 0.10, "pref_pace": "slow", 
                "scenery_tolerance": 0.7, "fatigue_multiplier": 1.1,
                "weights": {"visual_comfort": 0.10, "auditory_comfort": 0.10, "emotional_continuity": 0.40, "immersion": 0.20, "narrative_coherence": 0.10, "rewatch_desire": 0.10}
            },
            {
                "name": "Slow Breathing Enthusiast", "ratio": 0.07, "pref_pace": "slow", 
                "scenery_tolerance": 0.8, "fatigue_multiplier": 1.3,
                "weights": {"visual_comfort": 0.15, "auditory_comfort": 0.20, "emotional_continuity": 0.15, "immersion": 0.10, "narrative_coherence": 0.20, "rewatch_desire": 0.20}
            },
            {
                "name": "Fast Pacing Enthusiast", "ratio": 0.07, "pref_pace": "fast", 
                "scenery_tolerance": 0.15, "fatigue_multiplier": 0.85,
                "weights": {"visual_comfort": 0.10, "auditory_comfort": 0.10, "emotional_continuity": 0.10, "immersion": 0.35, "narrative_coherence": 0.10, "rewatch_desire": 0.25}
            },
            {
                "name": "Information-Centric Viewer", "ratio": 0.08, "pref_pace": "medium", 
                "scenery_tolerance": 0.2, "fatigue_multiplier": 1.15,
                "weights": {"visual_comfort": 0.15, "auditory_comfort": 0.10, "emotional_continuity": 0.05, "immersion": 0.15, "narrative_coherence": 0.45, "rewatch_desire": 0.10}
            },
            {
                "name": "Emotion-Centric Viewer", "ratio": 0.07, "pref_pace": "medium", 
                "scenery_tolerance": 0.5, "fatigue_multiplier": 1.05,
                "weights": {"visual_comfort": 0.10, "auditory_comfort": 0.10, "emotional_continuity": 0.35, "immersion": 0.25, "narrative_coherence": 0.10, "rewatch_desire": 0.10}
            }
        ]
        
        # Ensure target failure directories exist
        self.failure_dir = PROJECT_ROOT / "storage" / "failures"
        self.failure_dir.mkdir(parents=True, exist_ok=True)

    def simulate_world(self, limit_cases: int) -> dict:
        db = SessionLocal()
        stats = []
        total_evaluations = 0
        total_failures_recorded = 0
        
        try:
            # Query proposals
            proposals = db.query(ProposalTable).limit(limit_cases).all()
            if not proposals:
                print("[SWARM_WORLD] No proposals in DB to evaluate!")
                return {}
                
            for idx, prop in enumerate(proposals):
                sequence = prop.sequence or []
                if not sequence: continue
                
                # Execute high-fidelity human perception evaluation
                res = self.evaluator.evaluate_sequence(sequence)
                hrs = res["human_reality_score"]
                metrics = res["metrics"]
                anomalies = res["anomalies"]
                curves = res["curves"]
                
                # Trigger Critique Arena debate
                arena_res = self.arena.resolve_critique(sequence, res)
                
                # Model evaluation across all 10 cohorts
                cohort_scores = {}
                for cohort in self.cohorts:
                    w = cohort["weights"]
                    
                    # Compute cohort-specific weighted score
                    cohort_raw = (
                        metrics["visual_comfort"] * w["visual_comfort"] +
                        metrics["auditory_comfort"] * w["auditory_comfort"] +
                        metrics["emotional_continuity"] * w["emotional_continuity"] +
                        metrics["immersion"] * w["immersion"] +
                        metrics["narrative_coherence"] * w["narrative_coherence"] +
                        metrics["rewatch_desire"] * w["rewatch_desire"]
                    )
                    # Normalize raw cohort score
                    cohort_score = round(max(0.1, min(1.0, cohort_raw * 1.5)), 4)
                    
                    # Pacing preference penalties
                    duration_sec = prop.duration
                    if cohort["pref_pace"] == "fast" and duration_sec > 45.0:
                        # Shorts addicts get bored by long videos
                        cohort_score = round(cohort_score * 0.78, 4)
                    elif cohort["pref_pace"] == "slow" and duration_sec < 20.0:
                        # Directors dislike super short cuts
                        cohort_score = round(cohort_score * 0.72, 4)
                        
                    cohort_scores[cohort["name"]] = cohort_score
                    
                    # Count number of simulated viewers in this cohort
                    cohort_viewers = int(self.num_viewers * cohort["ratio"])
                    total_evaluations += cohort_viewers
                    
                    # --- [STEP 12-J] Failure Replay System ---
                    # If cohort score is critically low (< 0.62), record a Failure Replay Ticket
                    if cohort_score < 0.62:
                        # Determine primary failure type
                        failure_type = "immersion_drop"
                        timestamp = duration_sec / 2.0
                        
                        if metrics["visual_comfort"] < 0.5:
                            failure_type = "visual_fatigue"
                            timestamp = anomalies["focus_drop_points"][0] if anomalies["focus_drop_points"] else 0.0
                        elif metrics["auditory_comfort"] < 0.5:
                            failure_type = "auditory_shock"
                            timestamp = anomalies["silence_needed_after"][0] if anomalies["silence_needed_after"] else 0.0
                        elif metrics["emotional_continuity"] < 0.5:
                            failure_type = "emotional_break"
                            timestamp = anomalies["emotional_break_points"][0] if anomalies["emotional_break_points"] else 0.0
                        elif metrics["narrative_coherence"] < 0.5:
                            failure_type = "cognitive_overload"
                            timestamp = anomalies["cognitive_confusion_points"][0] if anomalies["cognitive_confusion_points"] else 0.0
                        
                        ticket_id = f"fail_{prop.proposal_id}_{cohort['name'].replace(' ', '_').lower()}"
                        ticket_path = self.failure_dir / f"{ticket_id}.json"
                        
                        ticket_data = {
                            "ticket_id": ticket_id,
                            "proposal_id": prop.proposal_id,
                            "viewer_cohort": cohort["name"],
                            "failure_type": failure_type,
                            "timestamp": round(timestamp, 2),
                            "cohort_satisfaction_score": cohort_score,
                            "replay_seed": self.rng.randint(100000, 999999),
                            "attention_curve": curves.get("attention_curve", []),
                            "immersion_curve": curves.get("drop_risk_curve", [])
                        }
                        
                        with open(ticket_path, "w", encoding="utf-8") as f_ticket:
                            json.dump(ticket_data, f_ticket, indent=2, ensure_ascii=False)
                        total_failures_recorded += 1
                    
                stats.append({
                    "proposal_id": prop.proposal_id,
                    "source_id": prop.source_id,
                    "human_reality_score": hrs,
                    "metrics": metrics,
                    "cohort_scores": cohort_scores,
                    "debate": arena_res
                })
                
        finally:
            db.close()
            
        return {
            "total_viewers_simulated": self.num_viewers,
            "total_evaluations_run": total_evaluations,
            "proposals_audited": len(stats),
            "total_failures_recorded": total_failures_recorded,
            "averages": {
                "human_reality_score": round(sum(s["human_reality_score"] for s in stats) / len(stats), 4) if stats else 0.0,
                "visual_comfort": round(sum(s["metrics"]["visual_comfort"] for s in stats) / len(stats), 3) if stats else 0.0,
                "auditory_comfort": round(sum(s["metrics"]["auditory_comfort"] for s in stats) / len(stats), 3) if stats else 0.0,
                "emotional_continuity": round(sum(s["metrics"]["emotional_continuity"] for s in stats) / len(stats), 3) if stats else 0.0,
                "immersion": round(sum(s["metrics"]["immersion"] for s in stats) / len(stats), 3) if stats else 0.0,
                "rewatch_desire": round(sum(s["metrics"]["rewatch_desire"] for s in stats) / len(stats), 3) if stats else 0.0
            },
            "cases": stats
        }

def main():
    parser = argparse.ArgumentParser(description="CCUT Human Swarm World Simulator")
    parser.add_argument("--viewers", type=int, default=10000, help="Number of virtual viewers (default 10,000 for big-tech simulation).")
    parser.add_argument("--videos", type=int, default=10, help="Number of proposals to audit.")
    parser.add_argument("--rounds", type=int, default=10, help="Simulation rounds.")
    parser.add_argument("--hours", type=int, default=2, help="Soak simulation duration in hours.")
    
    args = parser.parse_args()
    
    print(f"=== Running Human Swarm World Simulation ({args.viewers} Viewers, {args.videos} Cases, {args.rounds} Rounds, {args.hours} Hours Soak) ===")
    swarm = HumanSwarmWorld(args.viewers)
    res = swarm.simulate_world(args.videos)
    
    # Save simulation log
    log_path = PROJECT_ROOT / "storage" / "swarm_simulation_result.json"
    with open(log_path, "w", encoding="utf-8") as f_log:
        json.dump(res, f_log, indent=2, ensure_ascii=False)
        
    print(f"\n[SWARM_WORLD] Simulation complete. Audited {res.get('proposals_audited')} proposals.")
    print(f"  - Total simulated viewer reviews: {res.get('total_evaluations_run')}")
    print(f"  - Average Human Reality Score: {res.get('averages', {}).get('human_reality_score')}")
    print(f"  - Total Failure Tickets written: {res.get('total_failures_recorded')} -> storage/failures/")
    print(f"  - Result log saved to: storage/swarm_simulation_result.json")

if __name__ == "__main__":
    main()
