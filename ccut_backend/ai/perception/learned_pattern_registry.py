from typing import Dict, Any, List

class LearnedPatternRegistry:
    """
    [STEP 13] LearnedPatternRegistry
    Stores and evaluates human-addictive editing patterns extracted from
    popular YouTube videos, vlogs, and cinematic films.
    """
    PATTERNS = {
        "hook_3sec": {
            "name": "Hook in 3 Seconds",
            "description": "Viewer retention drop-off is highest in the first 3s; requires intense action/dialogue/hook at start.",
            "weight_bonus": 0.35
        },
        "reaction_zoom": {
            "name": "Reaction Zoom Trigger",
            "description": "Identifies emotional shifts (e.g. laughter, surprise) and flags zoom-ins on faces.",
            "weight_bonus": 0.20
        },
        "beat_cut": {
            "name": "Beat-Synced Cutting",
            "description": "Aligns cut transitions with high audio energy peaks.",
            "weight_bonus": 0.15
        },
        "laugh_hold": {
            "name": "Laughter Hold",
            "description": "Ensures the shot holds for at least 1.5 seconds after a laugh to let viewers process it.",
            "weight_bonus": 0.25
        },
        "silence_release": {
            "name": "Silence Release/Cinematic Breathing",
            "description": "Inserts brief quiet scenery/ambient breaks after highly intense dialogue to relieve auditory stress.",
            "weight_bonus": 0.18
        },
        "broll_bridge": {
            "name": "B-Roll Context Bridge",
            "description": "Uses scenery/b-roll clips to bridge context switches between different source files.",
            "weight_bonus": 0.12
        },
        "caption_punch": {
            "name": "Caption Punch Alignment",
            "description": "Aligns critical subtitle words with high-intensity audio frames.",
            "weight_bonus": 0.10
        },
        "fast_question_answer": {
            "name": "Rapid Q&A Pace",
            "description": "narrative pairs representing questions and answers cut rapidly to build momentum.",
            "weight_bonus": 0.22
        },
        "before_after_reveal": {
            "name": "Before/After Visual Reveal",
            "description": "Ensures a preparation shot is directly followed by a result/payoff reveal shot.",
            "weight_bonus": 0.28
        }
    }

    def evaluate_patterns(self, clip: Dict[str, Any], prev_clip: Dict[str, Any] = None, current_timeline: float = 0.0) -> Dict[str, Any]:
        """
        Evaluates which human editing patterns are matched by this clip and returns score bonuses.
        """
        applied_patterns = []
        pattern_bonus = 1.0
        
        role = clip.get("structural", {}).get("role", "main")
        edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
        duration = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
        
        intel = clip.get("intelligence") or {}
        txt = str(intel.get("transcript", "") or clip.get("semantic", {}).get("transcript_refs", "")).lower()
        audio_energy = float(clip.get("audio_energy") or clip.get("evidence", {}).get("audio_energy", 0.4))
        
        # 1. Hook in 3 Seconds (At the start of the timeline, hook or payoff clips are boosted)
        if current_timeline <= 3.0:
            if role == "hook" or edit_val > 0.8:
                applied_patterns.append("hook_3sec")
                pattern_bonus += self.PATTERNS["hook_3sec"]["weight_bonus"]
                
        # 2. Laughter Hold (If laughter is detected, we prefer longer durations)
        if "하하" in txt or "ㅋㅋㅋ" in txt or "laugh" in txt:
            if duration >= 3.0:
                applied_patterns.append("laugh_hold")
                pattern_bonus += self.PATTERNS["laugh_hold"]["weight_bonus"]
                
        # 3. Silence Release (After high-intensity dialogue, ambient/reaction shots get a boost)
        if prev_clip:
            prev_intel = prev_clip.get("intelligence") or {}
            prev_txt = str(prev_intel.get("transcript", "") or prev_clip.get("semantic", {}).get("transcript_refs", "")).lower()
            prev_energy = float(prev_clip.get("audio_energy") or prev_clip.get("evidence", {}).get("audio_energy", 0.4))
            
            if prev_energy > 0.7 and len(prev_txt) > 0:
                if role in ["scenery", "reaction"] and not txt:
                    applied_patterns.append("silence_release")
                    pattern_bonus += self.PATTERNS["silence_release"]["weight_bonus"]
                    
            # 4. B-Roll Context Bridge (When switching source videos, a scenery bridge is helpful)
            prev_sid = prev_clip.get("source_id")
            curr_sid = clip.get("source_id")
            if prev_sid and curr_sid and prev_sid != curr_sid:
                if role == "scenery":
                    applied_patterns.append("broll_bridge")
                    pattern_bonus += self.PATTERNS["broll_bridge"]["weight_bonus"]
                    
            # 5. Before/After visual reveal
            prev_role = prev_clip.get("structural", {}).get("role")
            if prev_role == "main" and role == "payoff" and edit_val > 0.8:
                applied_patterns.append("before_after_reveal")
                pattern_bonus += self.PATTERNS["before_after_reveal"]["weight_bonus"]

        # 6. Beat Cut (Cut aligns with high audio energy)
        if audio_energy > 0.72:
            applied_patterns.append("beat_cut")
            pattern_bonus += self.PATTERNS["beat_cut"]["weight_bonus"]

        return {
            "applied_patterns": applied_patterns,
            "pattern_bonus": round(pattern_bonus, 3)
        }
