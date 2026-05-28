import random
from typing import List, Dict, Any

class CritiqueArena:
    """
    [STEP 12-K] CritiqueArena
    Simulates a conversational debate among 6 creative AI agent personas:
    1. Director Agent: Focuses on story theme and breathing rhythm.
    2. Viewer Agent: Evaluates raw engagement, boredom, and reading speed.
    3. Editor Agent: Focuses on technical pacing, edit values, and cut points.
    4. Critic Agent: Criticizes artistic aesthetics, flow, and clichés.
    5. Emotion Agent: Assesses reaction preservation and transition harmony.
    6. Narrative Agent: Validates logical layout and memory context switches.
    
    They discuss, clash, and agree on calibration factors.
    """
    
    def resolve_critique(self, sequence: List[Dict[str, Any]], hrs_result: Dict[str, Any]) -> Dict[str, Any]:
        metrics = hrs_result.get("metrics", {})
        anomalies = hrs_result.get("anomalies", {})
        events = hrs_result.get("timeline_events", [])
        
        debates = []
        recommendations = {}
        
        # Extracted metrics
        v_comfort = metrics.get("visual_comfort", 0.5)
        a_comfort = metrics.get("auditory_comfort", 0.5)
        emo_flow = metrics.get("emotional_continuity", 0.5)
        immersion = metrics.get("immersion", 0.5)
        b_res = metrics.get("boredom_resistance", 0.5)
        react_pres = metrics.get("reaction_preservation", 0.5)
        breath = metrics.get("cinematic_breathing", 0.5)
        narrative = metrics.get("narrative_coherence", 0.5)
        
        # Dialogue & duration metadata
        total_duration = sum(float(c.get("duration") or c.get("duration_sec") or 5.0) for c in sequence)
        avg_dur = total_duration / len(sequence) if sequence else 0
        
        # 1. ROUND 1: Director starts the debate
        director_comment = "[Director] "
        if narrative < 0.72:
            director_comment += f"The narrative structure is messy. Cognitive coherence is sitting at {narrative:.2f}. We are jumping context too randomly!"
            recommendations["emotional_continuity_weight_mod"] = 1.25
        elif breath < 0.65:
            director_comment += "This edit doesn't breathe. It's a non-stop wall of sound and dialogue. We need quiet pauses to let the story sink in."
            recommendations["breathing_multiplier_mod"] = 1.35
        else:
            director_comment += "The structural spine of this edit is solid, but the individual performances might need tighter framing."
        debates.append(director_comment)

        # 2. ROUND 2: Viewer reacts to the Director
        viewer_comment = "[Viewer] "
        if v_comfort < 0.7:
            viewer_comment += f"I agree with the Director, but my eyes are burning first! Visual comfort is awful ({v_comfort:.2f}) because of rapid-cut whiplash or tiny fonts in fast subtitles."
            recommendations["increase_cut_duration"] = 1.2
        elif immersion < 0.65:
            viewer_comment += f"Honestly, I'm just bored. Immersion fell to {immersion:.2f}. The pacing is dragging, and I'm losing interest fast."
            recommendations["reduce_scenery_ratio_mod"] = 0.75
        else:
            viewer_comment += "I'm staying engaged, but some parts feel a bit repetitive."
        debates.append(viewer_comment)

        # 3. ROUND 3: Editor jumps in to defend or critique
        editor_comment = "[Editor] "
        if avg_dur < 3.2:
            editor_comment += f"Viewer is right about the whiplash. With an average cut length of {avg_dur:.1f}s, it's edited like a TikTok video. I need to merge short shots."
            recommendations["breathing_multiplier_mod"] = recommendations.get("breathing_multiplier_mod", 1.0) * 1.2
        elif b_res < 0.7:
            editor_comment += f"We have consecutive scenery shots dragging the pacing. I will cut down non-essential b-roll scenery to restore boredom resistance."
            recommendations["reduce_scenery_ratio_mod"] = 0.7
        else:
            editor_comment += "I tried to balance the tempo, but maybe we can clean up the transition points."
        debates.append(editor_comment)

        # 4. ROUND 4: Critic assesses the artistic value
        critic_comment = "[Critic] "
        if a_comfort < 0.72:
            critic_comment += f"Let's talk about the sound design. The auditory comfort is low ({a_comfort:.2f}). We have massive volume shocks between scenes that break cinematic illusion."
            recommendations["breathing_multiplier_mod"] = recommendations.get("breathing_multiplier_mod", 1.0) * 1.15
        elif emo_flow < 0.7:
            critic_comment += f"Artistically, the emotional arc is fragmented. We jump from tense dialogue to generic scenery. There is no resonance."
            recommendations["emotional_continuity_weight_mod"] = recommendations.get("emotional_continuity_weight_mod", 1.0) * 1.2
        else:
            critic_comment += "The pacing rhythm is acceptable, but the narrative transition is slightly predictable."
        debates.append(critic_comment)

        # 5. ROUND 5: Emotion Agent evaluates emotional beats
        emotion_comment = "[Emotion] "
        if react_pres < 0.6:
            emotion_comment += f"Wait, look at the dramatic peaks! We cut away from intense dialogue before showing the listener's reaction shot. Reaction preservation is only {react_pres:.2f}."
            recommendations["reaction_priority_multiplier_mod"] = 1.45
        else:
            emotion_comment += "The emotional carry-over is fine, but the transition harmony between scenes could be smoother."
        debates.append(emotion_comment)

        # 6. ROUND 6: Narrative Agent concludes the argument
        narrative_comment = "[Narrative] "
        narrative_anomalies = [e for e in events if e["type"] == "narrative_disorder"]
        if narrative_anomalies:
            narrative_comment += f"Exactly! We have a critical sequence disorder: {narrative_anomalies[0]['reason']}. We must reposition the hook."
            recommendations["emotional_continuity_weight_mod"] = recommendations.get("emotional_continuity_weight_mod", 1.0) * 1.3
        else:
            narrative_comment += "Agreed. Let's merge these points and calibrate the engine factors."
        debates.append(narrative_comment)
        
        # Normalize and filter recommended modifiers
        final_mods = {}
        for key, val in recommendations.items():
            final_mods[key] = round(val, 2)
            
        return {
            "arena_debates": debates,
            "debate_count": len(debates),
            "suggested_modifications": final_mods
        }
