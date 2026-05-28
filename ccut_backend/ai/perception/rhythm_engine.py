from typing import Dict, Any, List

class RhythmEngine:
    """
    [STEP 13] RhythmEngine
    Orchestrates target cut lengths, pacing templates, and time-zone structural scoring.
    Supports templates: YouTube Vlog, Shorts, Documentary, Review, Cinematic Film.
    """
    
    TEMPLATES = {
        "Documentary": {
            "pacing_preference": "slow",
            "ideal_cut_range": (5.0, 12.0),
            "scenery_multiplier": 1.2,
            "reaction_multiplier": 1.3,
            "max_consecutive_scenery": 2
        },
        "YouTube Vlog": {
            "pacing_preference": "fast",
            "ideal_cut_range": (2.0, 5.0),
            "scenery_multiplier": 0.5,
            "reaction_multiplier": 1.0,
            "max_consecutive_scenery": 1
        },
        "Cinematic Film": {
            "pacing_preference": "medium",
            "ideal_cut_range": (3.5, 8.0),
            "scenery_multiplier": 0.8,
            "reaction_multiplier": 1.4,
            "max_consecutive_scenery": 1
        },
        "Shorts": {
            "pacing_preference": "fast",
            "ideal_cut_range": (1.2, 3.2),
            "scenery_multiplier": 0.1,
            "reaction_multiplier": 0.8,
            "max_consecutive_scenery": 0
        }
    }

    def evaluate_rhythm(self, clip: Dict[str, Any], template_name: str, elapsed_time: float) -> Dict[str, Any]:
        """
        Evaluates pacing compatibility based on style template and elapsed timeline position.
        """
        temp = self.TEMPLATES.get(template_name, self.TEMPLATES["YouTube Vlog"])
        role = clip.get("structural", {}).get("role", "main")
        duration = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
        
        rhythm_bonus = 1.0
        pacing_state = "neutral"
        
        # 1. Timeline Pacing Zones Logic
        # - Zone 0-5s: Hook Zone (prefers hooks/high value)
        # - Zone 5-20s: Buildup Zone (prefers fast cuts, dialog)
        # - Zone 20-40s: Breathing Zone (prefers scenery/reaction)
        # - Zone 40s+: Payoff Zone (prefers payoff)
        
        if elapsed_time <= 5.0:
            if role == "hook":
                rhythm_bonus *= 1.35
                pacing_state = "ideal_hook"
            elif role == "scenery":
                rhythm_bonus *= 0.4  # Penalize slow scenery at the very start
                pacing_state = "slow_start_penalty"
        elif 5.0 < elapsed_time <= 20.0:
            # Buildup zone: fast pacing preferred
            if temp["pacing_preference"] == "fast" and duration <= 4.0:
                rhythm_bonus *= 1.2
                pacing_state = "fast_buildup"
            elif duration > 8.0:
                rhythm_bonus *= 0.8
                pacing_state = "slow_buildup_penalty"
        elif 20.0 < elapsed_time <= 40.0:
            # Breathing zone: b-roll/reaction/scenery preferred to relax the eyes
            if role in ["scenery", "reaction"]:
                rhythm_bonus *= temp["scenery_multiplier"] * 1.3
                pacing_state = "breathing_comfort"
        else:
            # Payoff zone: prefers payoff / intense clips
            if role == "payoff":
                rhythm_bonus *= 1.4
                pacing_state = "ideal_payoff"
                
        # 2. Duration Fit Scoring
        min_ideal, max_ideal = temp["ideal_cut_range"]
        if min_ideal <= duration <= max_ideal:
            rhythm_bonus *= 1.15
        elif duration < min_ideal * 0.7:
            # Too fast for this template
            rhythm_bonus *= 0.8
        elif duration > max_ideal * 1.3:
            # Too slow for this template
            rhythm_bonus *= 0.75

        return {
            "rhythm_bonus": round(rhythm_bonus, 3),
            "pacing_state": pacing_state
        }
