import math
from typing import List, Dict, Any

class ImmersionSimulator:
    """
    [STEP 12-E] ImmersionSimulator
    Simulates timeline-based story immersion, engagement curve spikes, emotional attachment,
    and cumulative boredom drift leading to drops in audience retention.
    """
    def __init__(self, baseline_immersion: float = 0.5):
        self.baseline_immersion = baseline_immersion

    def simulate_immersion(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simulates engagement decay, narrative payoff boosts, and boredom drift.
        """
        if not sequence:
            return {
                "immersion_score": 0.0,
                "drop_risk_curve": [],
                "peak_engagement_points": [],
                "boredom_drift": 0.0,
                "immersion_events": []
            }

        # Initialize tracking states
        current_immersion = self.baseline_immersion
        total_boredom = 0.0
        
        timeline = 0.0
        drop_risk_curve = []
        peak_points = []
        immersion_events = []
        
        consecutive_scenery_time = 0.0
        
        for idx, clip in enumerate(sequence):
            dur = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
            role = clip.get("structural", {}).get("role", "main")
            edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
            
            # Extract transcript text
            intel = clip.get("intelligence") or {}
            txt = str(intel.get("transcript", "") or clip.get("semantic", {}).get("transcript_refs", ""))
            has_dialogue = len(txt.strip()) > 0
            
            # Save step immersion for each second of the clip
            clip_immersion_states = []
            
            # --- 1. Pacing & Role Boredom Drift ---
            if role == "scenery":
                consecutive_scenery_time += dur
                # Scenery without dialogue causes fast immersion decay (boredom drift)
                drift_factor = 0.02 * consecutive_scenery_time
                current_immersion -= drift_factor
                total_boredom += drift_factor
                
                if consecutive_scenery_time > 8.0:
                    immersion_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "boredom_drift",
                        "reason": f"Extended b-roll scenery ({consecutive_scenery_time:.1f}s) without dialogue causes interest drop"
                    })
            else:
                consecutive_scenery_time = 0.0
                
            # --- 2. Narrative Hook / Payoff Engagement Spikes ---
            if role == "hook":
                # Hook triggers a major immersion spike
                boost = 0.18 + (edit_val * 0.1)
                current_immersion += boost
                peak_points.append(round(timeline + (dur / 2.0), 2))
                immersion_events.append({
                    "timestamp": round(timeline, 2),
                    "type": "narrative_hook",
                    "reason": f"Narrative hook spike (boost: +{boost:.2f})"
                })
            elif role == "payoff":
                # Payoff triggers maximum engagement
                boost = 0.22 + (edit_val * 0.12)
                current_immersion += boost
                peak_points.append(round(timeline + (dur / 2.0), 2))
                immersion_events.append({
                    "timestamp": round(timeline, 2),
                    "type": "narrative_payoff",
                    "reason": f"Cinematic payoff peak (boost: +{boost:.2f})"
                })
            elif has_dialogue:
                # Normal dialogue builds slight emotional connection
                current_immersion += 0.035
            else:
                # Idle clip decays attention slightly
                current_immersion -= 0.015
                
            # Cap immersion range [0.1, 1.0]
            current_immersion = max(0.1, min(1.0, current_immersion))
            
            # Record immersion second-by-second
            for t in range(int(math.ceil(dur))):
                # Interpolated immersion values
                decay_val = current_immersion
                if role == "scenery":
                    # Slow decay during the scene
                    decay_val = max(0.1, current_immersion - (0.005 * t))
                clip_immersion_states.append(decay_val)
                
            # Add to drop risk curve (drop risk = 1.0 - immersion)
            for state in clip_immersion_states:
                drop_risk_curve.append(round(1.0 - state, 3))
                
            timeline += dur
            
        final_immersion = max(0.1, min(1.0, current_immersion))
        
        return {
            "immersion_score": round(final_immersion, 3),
            "drop_risk_curve": drop_risk_curve,
            "peak_engagement_points": sorted(list(set(peak_points))),
            "boredom_drift": round(min(1.0, total_boredom), 3),
            "immersion_events": immersion_events
        }
