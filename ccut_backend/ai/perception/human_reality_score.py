from typing import List, Dict, Any
from .visual_attention_simulator import VisualAttentionSimulator
from .auditory_fatigue_simulator import AuditoryFatigueSimulator
from .emotional_continuity_simulator import EmotionalContinuitySimulator
from .cognitive_load_simulator import CognitiveLoadSimulator
from .immersion_simulator import ImmersionSimulator

class HumanRealityScore:
    """
    [STEP 12-L] HumanRealityScore
    Combines sensory, cognitive, and narrative simulation results to evaluate the
    true comfort, continuity, cognitive load, and rewatch desire of an edit sequence.
    
    Evaluates 10 distinct human reality metrics.
    """
    def __init__(self):
        self.visual_sim = VisualAttentionSimulator()
        self.audio_sim = AuditoryFatigueSimulator()
        self.emotion_sim = EmotionalContinuitySimulator()
        self.cognitive_sim = CognitiveLoadSimulator()
        self.immersion_sim = ImmersionSimulator()

    def evaluate_sequence(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs the 5 simulators on the edit sequence and computes the 10 metrics.
        """
        # Run sub-simulators
        vis = self.visual_sim.simulate_attention(sequence)
        aud = self.audio_sim.simulate_audio(sequence)
        emo = self.emotion_sim.simulate_emotion(sequence)
        cog = self.cognitive_sim.simulate_cognitive_load(sequence)
        imm = self.immersion_sim.simulate_immersion(sequence)
        
        # --- 10 Human Reality Metrics ---
        
        # 1. Visual Comfort
        visual_comfort = round(1.0 - vis["visual_fatigue"], 3)
        
        # 2. Auditory Comfort
        auditory_comfort = round(1.0 - aud["audio_fatigue"], 3)
        
        # 3. Emotional Continuity
        emotional_continuity = emo["continuity_score"]
        
        # 4. Immersion
        immersion = imm["immersion_score"]
        
        # 5. Boredom Resistance
        # Derived from drop risk curve: average resistance to drop-offs
        drop_risk_avg = sum(imm["drop_risk_curve"]) / len(imm["drop_risk_curve"]) if imm["drop_risk_curve"] else 0.0
        boredom_resistance = round(1.0 - drop_risk_avg, 3)
        
        # 6. Reaction Preservation
        # Determined by lingering strength and presence of reaction carry-overs
        reaction_preservation = emo["lingering_strength"]
        
        # 7. Cinematic Breathing
        # Evaluates presence of quiet moments vs loudness instability and breathing suggestions
        cinematic_breathing = round(1.0 - (0.45 if aud["breathing_recommended"] else 0.0) - (aud["loudness_instability"] * 0.15), 3)
        cinematic_breathing = max(0.1, min(1.0, cinematic_breathing))
        
        # 8. Narrative Coherence
        # Evaluates the absence of cognitive load confusion and correct narrative ordering
        narrative_coherence = round(1.0 - cog["cognitive_load"], 3)
        
        # 9. Emotional Memory
        # Retention of emotional resonance vs cognitive context-switching fatigue
        emotional_memory = round((emo["lingering_strength"] * 0.6) + (1.0 - cog["context_switching_fatigue"]) * 0.4, 3)
        emotional_memory = max(0.1, min(1.0, emotional_memory))
        
        # 10. Rewatch Desire
        # A composite desire score: combination of visual/auditory comfort, narrative flow, and immersion
        rewatch_desire = round((
            visual_comfort * 0.15 +
            auditory_comfort * 0.15 +
            emotional_continuity * 0.15 +
            immersion * 0.25 +
            narrative_coherence * 0.15 +
            emotional_memory * 0.15
        ), 3)
        
        # --- Composite Human Reality Score (HRS) ---
        hrs = round((
            visual_comfort * 0.12 +
            auditory_comfort * 0.12 +
            emotional_continuity * 0.12 +
            immersion * 0.16 +
            boredom_resistance * 0.08 +
            reaction_preservation * 0.08 +
            cinematic_breathing * 0.08 +
            narrative_coherence * 0.08 +
            emotional_memory * 0.08 +
            rewatch_desire * 0.08
        ), 4)
        
        # Consolidate all timeline anomalies/events
        events = []
        events.extend(vis.get("gaze_drift_events") or [])
        events.extend(aud.get("auditory_events") or [])
        events.extend(emo.get("emotional_events") or [])
        events.extend(cog.get("cognitive_events") or [])
        events.extend(imm.get("immersion_events") or [])
        # Sort events by timestamp
        events = sorted(events, key=lambda x: x.get("timestamp", 0.0))
        
        return {
            "human_reality_score": hrs,
            "metrics": {
                "visual_comfort": visual_comfort,
                "auditory_comfort": auditory_comfort,
                "emotional_continuity": emotional_continuity,
                "immersion": immersion,
                "boredom_resistance": boredom_resistance,
                "reaction_preservation": reaction_preservation,
                "cinematic_breathing": cinematic_breathing,
                "narrative_coherence": narrative_coherence,
                "emotional_memory": emotional_memory,
                "rewatch_desire": rewatch_desire
            },
            "anomalies": {
                "overstimulated": vis["overstimulated"],
                "focus_drop_points": vis["focus_drop_points"],
                "breathing_recommended": aud["breathing_recommended"],
                "silence_needed_after": aud["silence_needed_after"],
                "emotional_break_points": emo["break_points"],
                "cognitive_confusion_points": cog["confusion_points"],
                "peak_engagement_points": imm["peak_engagement_points"]
            },
            "timeline_events": events,
            "curves": {
                "attention_curve": vis.get("attention_curve", []),
                "drop_risk_curve": imm.get("drop_risk_curve", [])
            }
        }
