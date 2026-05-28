import math
from typing import List, Dict, Any

class VisualAttentionSimulator:
    """
    [STEP 12-A] VisualAttentionSimulator
    Simulates high-fidelity human visual attention, gaze drift, screen clutter,
    rapid-cut fatigue, transition shocks, and subtitle reading speed overload.
    
    Uses mathematical modeling of human sensory integration limits.
    """
    def __init__(self, reading_speed_cps: float = 16.0):
        # Human reading limit: average 16 characters per second for optimal comprehension
        self.reading_speed_cps = reading_speed_cps

    def simulate_attention(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Processes an edit sequence and outputs timeline-based visual attention states.
        """
        if not sequence:
            return {
                "attention_retention": 0.0,
                "focus_drop_points": [],
                "visual_fatigue": 0.0,
                "overstimulated": False,
                "attention_curve": [],
                "gaze_drift_events": []
            }

        # Initialize tracking states
        gaze_attention = 1.0  # Range [0.1, 1.0]
        cumulative_fatigue = 0.0  # Range [0.0, 1.0]
        
        focus_drop_points = []
        gaze_drift_events = []
        attention_curve = []
        
        timeline = 0.0
        consecutive_rapid_cuts = 0
        
        for idx, clip in enumerate(sequence):
            dur = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
            role = clip.get("structural", {}).get("role", "main")
            edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
            
            # Retrieve evidence metrics
            intel = clip.get("intelligence") or {}
            txt = str(intel.get("transcript", "") or clip.get("semantic", {}).get("transcript_refs", ""))
            motion_score = float(clip.get("motion_score") or clip.get("evidence", {}).get("motion_score", 0.3))
            
            # --- 1. Dynamic Attention Decay (Gaze Drift) ---
            # Standard attention span decay: human attention drifts after 7-8s of a static shot.
            clip_attention_curve = []
            for t in range(int(math.ceil(dur))):
                second_offset = timeline + t
                # Exponential decay formula for sustained focus
                decay_constant = 0.02
                if dur > 8.0:
                    # Gaze drifts faster on excessively long shots
                    decay_constant += 0.055 * (dur - 8.0) / dur
                
                # Screen complexity/edit_value helps maintain raw attention (interest) but increases fatigue
                interest_factor = 1.0 + (edit_val * 0.1)
                t_att = gaze_attention * math.exp(-decay_constant * t) * interest_factor
                t_att = max(0.1, min(1.0, t_att))
                clip_attention_curve.append(round(t_att, 3))
                
                if t_att < 0.65 and second_offset not in focus_drop_points:
                    focus_drop_points.append(round(second_offset, 2))
                    gaze_drift_events.append({
                        "timestamp": round(second_offset, 2),
                        "type": "gaze_drift",
                        "reason": f"Sustained static shot boredom (duration: {dur:.1f}s)"
                    })
            
            # Update running gaze attention based on final second of this clip
            gaze_attention = clip_attention_curve[-1] if clip_attention_curve else gaze_attention
            attention_curve.extend(clip_attention_curve)
            
            # --- 2. Rapid Cut Fatigue & Compounding Impulses ---
            # Human visual system needs ~2.5s to digest a visual scene change.
            if dur < 2.5:
                consecutive_rapid_cuts += 1
                # Non-linear compounding fatigue for high frequency cuts
                fatigue_impulse = 0.05 * math.pow(1.5, consecutive_rapid_cuts)
                cumulative_fatigue += fatigue_impulse
                
                # Attention drop on visual whiplash
                if consecutive_rapid_cuts >= 3:
                    gaze_attention *= 0.88
                    focus_drop_points.append(round(timeline, 2))
                    gaze_drift_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "visual_whiplash",
                        "reason": f"{consecutive_rapid_cuts} consecutive rapid cuts under 2.5s"
                    })
            else:
                # Slower paced cuts allow the eye to rest and reset fatigue
                consecutive_rapid_cuts = 0
                recovery = 0.04 * (dur / 5.0)
                cumulative_fatigue = max(0.0, cumulative_fatigue - recovery)
            
            # --- 3. Screen Clutter & Motion Overload ---
            # High motion combined with high complexity causes visual overstimulation
            if motion_score > 0.7 or edit_val > 0.85:
                cumulative_fatigue += 0.08 * (motion_score + edit_val)
                if motion_score > 0.85:
                    # Sudden high motion overload
                    gaze_attention *= 0.95
            
            # --- 4. Subtitle Reading Speed Panic ---
            # Check characters per second (CPS)
            char_count = len(txt.strip())
            if char_count > 0:
                cps = char_count / dur
                if cps > self.reading_speed_cps:
                    # Viewer enters "panic reading mode", failing to digest the background visual
                    panic_factor = (cps - self.reading_speed_cps) / self.reading_speed_cps
                    cumulative_fatigue += 0.12 * panic_factor
                    gaze_attention *= (1.0 - 0.08 * panic_factor)
                    focus_drop_points.append(round(timeline + 1.0, 2))
                    gaze_drift_events.append({
                        "timestamp": round(timeline + 1.0, 2),
                        "type": "subtitle_panic",
                        "reason": f"Reading speed overload: {cps:.1f} chars/sec (max recommended {self.reading_speed_cps})"
                    })
            
            # --- 5. Scene Transition Shock ---
            # Abrupt cuts from action/high-motion to slow scenery
            if idx > 0:
                prev_clip = sequence[idx - 1]
                prev_motion = float(prev_clip.get("motion_score") or prev_clip.get("evidence", {}).get("motion_score", 0.3))
                prev_role = prev_clip.get("structural", {}).get("role", "main")
                
                if prev_motion > 0.7 and motion_score < 0.25:
                    # Sensory whiplash: rapid motion to complete freeze
                    gaze_attention *= 0.9
                    cumulative_fatigue += 0.05
                    focus_drop_points.append(round(timeline, 2))
                    gaze_drift_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "transition_shock",
                        "reason": "Motion whiplash: sudden drop from high-motion to static scene"
                    })
                elif prev_role == "scenery" and role == "scenery" and idx > 1 and sequence[idx-2].get("structural", {}).get("role") == "scenery":
                    # Three scenery shots back-to-back causes visual detachment
                    gaze_attention *= 0.8
                    focus_drop_points.append(round(timeline, 2))
                    gaze_drift_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "visual_boredom",
                        "reason": "Three consecutive scenery/b-roll shots causing engagement loss"
                    })
                    
            timeline += dur
            
        # Normalize and package final values
        final_retention = max(0.1, min(1.0, sum(attention_curve) / len(attention_curve))) if attention_curve else gaze_attention
        final_fatigue = max(0.0, min(1.0, cumulative_fatigue))
        overstimulated = final_fatigue > 0.60
        
        return {
            "attention_retention": round(final_retention, 3),
            "focus_drop_points": sorted(list(set(focus_drop_points))),
            "visual_fatigue": round(final_fatigue, 3),
            "overstimulated": overstimulated,
            "attention_curve": [round(x, 3) for x in attention_curve],
            "gaze_drift_events": gaze_drift_events
        }
