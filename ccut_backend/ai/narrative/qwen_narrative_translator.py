from typing import Dict, Any
from .narrative_director_contract import NarrativeDirection

class QwenNarrativeTranslator:
    """
    [STEP 10-L-TRANSLATOR] QwenNarrativeTranslator (Enhanced for STEP 10-M)
    Translates abstract creative directing instructions (NarrativeDirection) into concrete,
    executable proposal constraints and weights that the CCUT Proposal Engine can apply.
    """
    def translate_direction(self, direction: NarrativeDirection) -> Dict[str, Any]:
        """
        Converts NarrativeDirection to ProposalConstraints dictionary.
        """
        constraints = {
            "prefer_reaction_fragments": False,
            "reaction_priority_multiplier": 1.0,
            "hold_after_emotion_sec": 0.0,
            "avoid_fast_cut_after_laughter": False,
            "reduce_scenery_ratio": 1.0,  # 1.0 means no reduction, lower values mean reduced scenery score
            "breathing_multiplier": 1.0,
            "emotional_continuity_weight": 1.0,
            "pace_curve": "stable",
            "pacing_style": direction.pacing_style,
            "narrative_priority": direction.narrative_priority
        }

        # 1. Reaction Policy mapping
        if direction.reaction_policy == "emphasized":
            constraints["prefer_reaction_fragments"] = True
            constraints["reaction_priority_multiplier"] = 1.35
        elif direction.reaction_policy == "minimized":
            constraints["prefer_reaction_fragments"] = False
            constraints["reaction_priority_multiplier"] = 0.5

        # 2. Breathing Policy mapping
        if direction.breathing_policy == "loose":
            constraints["breathing_multiplier"] = 1.35
            constraints["hold_after_emotion_sec"] = 1.5
        elif direction.breathing_policy == "tight":
            constraints["breathing_multiplier"] = 0.6
            constraints["hold_after_emotion_sec"] = 0.0
            
        # 3. Emotion Curve & Priority mapping
        if direction.emotion_curve in ["dramatic", "peak_at_end"] or direction.narrative_priority == "emotion":
            constraints["hold_after_emotion_sec"] = max(constraints["hold_after_emotion_sec"], 1.4)
            constraints["avoid_fast_cut_after_laughter"] = True
            constraints["emotional_continuity_weight"] = 1.5
        elif direction.emotion_curve == "dynamic":
            constraints["hold_after_emotion_sec"] = max(constraints["hold_after_emotion_sec"], 1.0)
            constraints["emotional_continuity_weight"] = 1.2
        elif direction.emotion_curve == "calm":
            constraints["hold_after_emotion_sec"] = max(constraints["hold_after_emotion_sec"], 1.2)
            constraints["emotional_continuity_weight"] = 1.3

        # 4. Scenery Policy mapping
        if direction.scenery_policy == "low_coverage":
            constraints["reduce_scenery_ratio"] = 0.35
        elif direction.scenery_policy == "establishing_only":
            constraints["reduce_scenery_ratio"] = 0.1
        elif direction.scenery_policy == "high_coverage":
            constraints["reduce_scenery_ratio"] = 1.5

        # 5. Pacing Style mapping
        if direction.pacing_style == "fast":
            constraints["pace_curve"] = "fast"
        elif direction.pacing_style == "slow":
            constraints["pace_curve"] = "slow"
        elif direction.pacing_style == "slow_to_fast":
            constraints["pace_curve"] = "accelerating"
        elif direction.pacing_style == "fast_to_slow":
            constraints["pace_curve"] = "decelerating"

        print(f"[NARRATIVE_TRANSLATION] Translated directing decisions to constraints: {constraints}")
        return constraints
