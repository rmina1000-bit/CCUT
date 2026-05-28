from typing import List, Dict, Any

class EmotionalContinuitySimulator:
    """
    [STEP 12-C] EmotionalContinuitySimulator
    Models emotional transition harmony using state compatibility matrix, reaction carry-overs,
    delayed response integration, emotional fatigue, and lingering resonance.
    """
    
    # Emotional Transition Harmony Matrix
    # Values range from -1.0 (clashing/jarring) to +1.0 (fully harmonic/resolving)
    HARMONY_MATRIX = {
        ("calm", "calm"): 0.8,
        ("calm", "warm"): 0.9,
        ("calm", "joyful"): 0.6,
        ("calm", "tense"): -0.3,   # Jarring start of tension
        
        ("warm", "calm"): 0.7,
        ("warm", "warm"): 0.85,
        ("warm", "joyful"): 0.95,   # Smooth emotional build
        ("warm", "tense"): -0.4,
        
        ("joyful", "calm"): 0.4,
        ("joyful", "warm"): 0.8,
        ("joyful", "joyful"): 0.8,
        ("joyful", "tense"): -0.7,  # Severe crash (laughter to danger)
        
        ("tense", "calm"): -0.6,    # Tension whiplash (sudden drop without resolution)
        ("tense", "warm"): 0.3,     # Resolved tension
        ("tense", "joyful"): -0.4,  # Sudden laughter after tension
        ("tense", "tense"): 0.7,    # Sustained tension (adds to emotional fatigue)
    }

    def simulate_emotion(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluates emotional transitions, continuity scores, and lingering resonance.
        """
        if not sequence:
            return {
                "continuity_score": 0.0,
                "break_points": [],
                "lingering_strength": 0.0,
                "emotional_fatigue": 0.0,
                "emotional_events": []
            }

        continuity_score = 0.85  # Default baseline
        emotional_fatigue = 0.0
        lingering_strength = 0.0
        
        break_points = []
        emotional_events = []
        timeline = 0.0
        
        active_emotion = "calm"
        intense_emotion_duration = 0.0
        
        for idx, clip in enumerate(sequence):
            dur = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
            role = clip.get("structural", {}).get("role", "main")
            edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
            
            # Identify clip emotion (map topic/description, or fallback to mock emotion)
            sem = clip.get("semantic_json") or clip.get("semantic", {}) or {}
            clip_emotion = sem.get("emotion") or sem.get("primary_emotion")
            if not clip_emotion:
                # Mock emotion based on role/edit value
                if edit_val > 0.82 and role in ["hook", "payoff"]:
                    clip_emotion = "tense"
                elif edit_val > 0.65:
                    clip_emotion = "joyful"
                elif role == "scenery":
                    clip_emotion = "calm"
                else:
                    clip_emotion = "warm"
            
            # --- 1. Emotional State Transition Harmony ---
            if idx > 0:
                prev_clip = sequence[idx - 1]
                prev_role = prev_clip.get("structural", {}).get("role", "main")
                prev_ev = float(prev_clip.get("structural", {}).get("edit_value", 0.5))
                
                # Retrieve harmony factor
                harmony = self.HARMONY_MATRIX.get((active_emotion, clip_emotion), 0.5)
                
                # Shifting state impacts continuity score
                if harmony < 0:
                    # Severe transition friction
                    friction_loss = abs(harmony) * 0.15
                    continuity_score -= friction_loss
                    break_points.append(round(timeline, 2))
                    emotional_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "emotional_shock",
                        "reason": f"Friction transition: {active_emotion} -> {clip_emotion} (harmony score: {harmony})"
                    })
                else:
                    # Harmonic resolution adds to narrative satisfaction
                    continuity_score += harmony * 0.03
                
                # --- 2. Reaction Carry-Over & Delayed Response ---
                # Highly dramatic clip (edit_val > 0.8) must be followed by a reaction cut within 1-2 shots
                if prev_ev > 0.81 and prev_role in ["hook", "payoff"]:
                    if role == "reaction":
                        # Perfect emotional preservation
                        lingering_strength = min(1.0, lingering_strength + 0.25)
                        continuity_score += 0.08
                        emotional_events.append({
                            "timestamp": round(timeline, 2),
                            "type": "reaction_preservation",
                            "reason": f"Successful reaction shot after high-impact {prev_role}"
                        })
                    else:
                        # Non-reaction shot cut: emotional whiplash
                        continuity_score -= 0.15
                        break_points.append(round(prev_clip.get("duration", 5.0) + timeline - dur, 2))
                        emotional_events.append({
                            "timestamp": round(timeline, 2),
                            "type": "missing_reaction_carryover",
                            "reason": f"Jarring cut to {role} immediately after dramatic {prev_role} (expected reaction shot)"
                        })
            
            # --- 3. Emotional Fatigue & Lingering Resonance ---
            if clip_emotion in ["tense", "joyful"] and edit_val > 0.75:
                intense_emotion_duration += dur
                emotional_fatigue += 0.015 * dur
                
                # Lingering emotional resonance build up
                lingering_strength = min(1.0, lingering_strength + 0.08 * (dur / 5.0))
                
                if intense_emotion_duration > 15.0:
                    # Emotional exhaustion: viewer is desensitized
                    emotional_fatigue += 0.05
                    continuity_score -= 0.08
                    emotional_events.append({
                        "timestamp": round(timeline + dur, 2),
                        "type": "emotional_exhaustion",
                        "reason": f"Viewer desensitized by continuous intense emotion ({clip_emotion}) for {intense_emotion_duration:.1f}s"
                    })
            else:
                # Calm or warm scenery resets emotional exhaustion
                intense_emotion_duration = 0.0
                emotional_fatigue = max(0.0, emotional_fatigue - 0.06 * dur)
            
            active_emotion = clip_emotion
            timeline += dur
            
        final_continuity = max(0.1, min(1.0, continuity_score))
        final_fatigue = max(0.0, min(1.0, emotional_fatigue))
        final_lingering = max(0.0, min(1.0, lingering_strength))
        
        return {
            "continuity_score": round(final_continuity, 3),
            "break_points": sorted(list(set(break_points))),
            "lingering_strength": round(final_lingering, 3),
            "emotional_fatigue": round(final_fatigue, 3),
            "emotional_events": emotional_events
        }
