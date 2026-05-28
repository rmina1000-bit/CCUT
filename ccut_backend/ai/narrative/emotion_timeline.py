import os
import json
from typing import List, Dict, Any

class EmotionalTimeline:
    """
    [STEP 10-M] EmotionalTimeline
    Analyzes semantic fragments and evidence to construct a continuous emotional flow
    along the video's timeline.
    """
    def __init__(self, bams_manager):
        self.bams = bams_manager

    def build_timeline(self, source_id: str) -> List[Dict[str, Any]]:
        # Fetch fragments & evidence
        fragments = self.bams.get_semantic_fragments(source_id)
        evidence = self.bams.get_evidence_board(source_id)
        
        # Merge evidence and fragments by fragment_id
        evidence_map = {e["fragment_id"]: e for e in evidence}
        
        timeline = []
        last_emotion = "neutral"
        last_intensity = 0.5
        
        # We sort by start time
        sorted_fragments = sorted(fragments, key=lambda x: x.get("start", 0))
        
        for f in sorted_fragments:
            fid = f.get("fragment_id")
            start = f.get("start", 0.0)
            end = f.get("end", 0.0)
            dur = end - start
            
            # Extract evidence
            ev = evidence_map.get(fid, {})
            text = ev.get("text", "") or ""
            audio_energy = ev.get("audio_energy", 0.0)
            motion_score = ev.get("motion_score", 0.0)
            
            # Determine emotion and intensity based on transcript keywords, structural role, and energy
            emotion = "neutral"
            intensity = 0.5
            
            # Simple keyword matching on text (Korean & English)
            text_lower = text.lower()
            
            role = f.get("structural", {}).get("role", "main")
            
            # Base heuristics
            if any(w in text_lower for w in ["웃음", "하하", "ㅋㅋㅋ", "laugh", "funny", "happy", "joy"]):
                emotion = "joyful"
                intensity = 0.8
            elif any(w in text_lower for w in ["슬픔", "울음", "눈물", "sad", "cry", "tear", "pain"]):
                emotion = "sad"
                intensity = 0.75
            elif any(w in text_lower for w in ["화남", "분노", "angry", "mad", "shock", "tension", "scared"]):
                emotion = "tense"
                intensity = 0.85
            elif any(w in text_lower for w in ["평화", "조용", "calm", "peace", "quiet"]):
                emotion = "calm"
                intensity = 0.4
            elif role == "scenery":
                emotion = "reflective"
                intensity = 0.35
            elif role == "reaction":
                emotion = "warm"
                intensity = 0.6
                
            # Refinement based on audio energy and motion
            if audio_energy > 0.6:
                intensity = min(1.0, intensity + 0.15)
                if emotion == "neutral":
                    emotion = "dramatic"
            elif audio_energy < 0.1:
                intensity = max(0.1, intensity - 0.2)
                if emotion == "neutral":
                    emotion = "calm"
                    
            if motion_score > 0.7:
                intensity = min(1.0, intensity + 0.1)
                if emotion in ["neutral", "calm"]:
                    emotion = "dramatic"
                    
            # Transition direction
            if intensity > last_intensity + 0.1:
                transition = "rising"
            elif intensity < last_intensity - 0.1:
                transition = "falling"
            else:
                transition = "steady"
                
            # Lingering check (longer fragments or reaction shots can linger)
            lingering = False
            if role in ["reaction", "scenery"] or dur > 8.0:
                if emotion in ["joyful", "sad", "tense", "warm", "reflective"]:
                    lingering = True
            
            # Keep track for next iteration
            last_emotion = emotion
            last_intensity = intensity
            
            timeline_item = {
                "timestamp": round(start, 2),
                "end_timestamp": round(end, 2),
                "fragment_id": fid,
                "emotion": emotion,
                "intensity": round(intensity, 2),
                "transition": transition,
                "lingering": lingering
            }
            timeline.append(timeline_item)
            
        return timeline
