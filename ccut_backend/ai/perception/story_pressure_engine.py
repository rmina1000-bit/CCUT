import math
from typing import List, Dict, Any

class StoryPressureEngine:
    """
    [STEP 13-A] StoryPressureEngine
    Models narrative momentum and story compression. Computes narrative pressure,
    emotional density, watchability predictions, and visual memory callbacks.
    """
    def __init__(self):
        pass

    def evaluate_story_pressure(self, clip: Dict[str, Any], prev_clip: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Computes active story scores for a candidate clip.
        """
        role = clip.get("structural", {}).get("role", "main")
        edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
        duration = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
        
        intel = clip.get("intelligence") or {}
        txt = str(intel.get("transcript", "") or clip.get("semantic", {}).get("transcript_refs", ""))
        word_count = len(txt.split())
        
        # --- 1. Narrative Pressure (Forward Story Momentum) ---
        # Dialogue that contains questions or hooks drives story forward
        narrative_pressure = 0.3
        if role == "hook":
            narrative_pressure += 0.45
        elif role == "payoff":
            narrative_pressure += 0.35
            
        lower_txt = txt.lower()
        if "?" in txt or "왜" in lower_txt or "어떻게" in lower_txt or "이유" in lower_txt or "비밀" in lower_txt:
            # Question cues trigger narrative tension
            narrative_pressure += 0.2
            
        narrative_pressure = min(1.0, narrative_pressure)
        
        # --- 2. Emotional Density ---
        # High emotional valence / edit values packed in tight clips
        emotional_density = 0.2
        if edit_val > 0.75:
            emotional_density += 0.3
            if role == "reaction":
                emotional_density += 0.25
        if "!" in txt or "대박" in lower_txt or "진짜" in lower_txt or "충격" in lower_txt:
            emotional_density += 0.15
            
        emotional_density = min(1.0, emotional_density)
        
        # --- 3. Watchability Prediction ---
        # Likelihood of viewer remaining focused. Higher for short, high-value clips,
        # lower for empty text clips without visual action.
        watchability = 0.5
        if duration <= 4.5:
            watchability += 0.15
        if edit_val > 0.8:
            watchability += 0.2
        if role == "scenery" and not txt:
            # Empty visual decays watchability if too long
            watchability -= 0.15 * (duration / 5.0)
            
        watchability = max(0.1, min(1.0, watchability))
        
        # --- 4. Narrative Callback Strength ---
        # Determines visual repetition coherence
        callback_strength = 0.0
        if prev_clip:
            prev_topic = prev_clip.get("semantic", {}).get("topic")
            curr_topic = clip.get("semantic", {}).get("topic")
            if prev_topic and curr_topic and prev_topic == curr_topic:
                callback_strength = 0.75
                
        return {
            "narrative_pressure": round(narrative_pressure, 3),
            "emotional_density": round(emotional_density, 3),
            "watchability": round(watchability, 3),
            "callback_strength": callback_strength
        }
