from typing import List, Dict, Any

class ReactionSignalDetector:
    """
    [STEP 10-M] ReactionSignalDetector
    Detects semantic reaction signals (e.g., laughter followed by silence, awkward silence,
    delayed reaction, emotional pauses) from video fragments and evidence.
    """
    def __init__(self, bams_manager):
        self.bams = bams_manager

    def detect_signals(self, source_id: str) -> Dict[str, Dict[str, Any]]:
        fragments = self.bams.get_semantic_fragments(source_id)
        evidence = self.bams.get_evidence_board(source_id)
        
        evidence_map = {e["fragment_id"]: e for e in evidence}
        signals = {}
        
        sorted_fragments = sorted(fragments, key=lambda x: x.get("start", 0))
        
        for idx, f in enumerate(sorted_fragments):
            fid = f.get("fragment_id")
            start = f.get("start", 0.0)
            end = f.get("end", 0.0)
            dur = end - start
            role = f.get("structural", {}).get("role", "main")
            
            ev = evidence_map.get(fid, {})
            text = (ev.get("text", "") or "").lower()
            audio_energy = ev.get("audio_energy", 0.0)
            
            # Detect awkward silence
            is_awkward = False
            if role == "reaction" and not text.strip() and dur >= 2.0 and audio_energy < 0.15:
                is_awkward = True
                
            # Detect laughter followed by silence
            laughter_silence = False
            if "하하" in text or "ㅋㅋㅋ" in text or "laugh" in text or "lol" in text:
                # check if next fragment is silence
                if idx + 1 < len(sorted_fragments):
                    next_f = sorted_fragments[idx+1]
                    next_ev = evidence_map.get(next_f.get("fragment_id"), {})
                    next_text = (next_ev.get("text", "") or "").strip()
                    next_energy = next_ev.get("audio_energy", 0.0)
                    if not next_text and next_energy < 0.15:
                        laughter_silence = True
                        
            # Detect delayed reaction
            delayed = False
            if role == "reaction" and idx > 0:
                prev_f = sorted_fragments[idx-1]
                prev_role = prev_f.get("structural", {}).get("role", "main")
                if prev_role == "main" or prev_role == "hook":
                    prev_ev = evidence_map.get(prev_f.get("fragment_id"), {})
                    prev_text = (prev_ev.get("text", "") or "").strip()
                    # Previous had speaker, this one is reaction with no text
                    if prev_text and not text.strip():
                        delayed = True
                        
            # Detect emotional pause
            emotional_pause = False
            if role == "reaction" and idx > 0:
                prev_f = sorted_fragments[idx-1]
                prev_ev = evidence_map.get(prev_f.get("fragment_id"), {})
                prev_text = (prev_ev.get("text", "") or "").lower()
                # Check for high emotion keywords in previous
                if any(w in prev_text for w in ["슬픔", "화남", "울음", "눈물", "sad", "cry", "angry", "shock"]):
                    emotional_pause = True
                    
            # Eye contact shift (Inferred from VL perception metadata)
            eye_shift = False
            perception = f.get("intelligence", {}).get("perception", {}) if isinstance(f.get("intelligence"), dict) else {}
            description = perception.get("description", "").lower()
            if "눈빛" in description or "gaze" in description or "looking away" in description or "eye contact" in description:
                eye_shift = True
                
            sig_types = []
            recommended_hold = 0.0
            
            if is_awkward:
                sig_types.append("awkward_silence")
                recommended_hold = max(recommended_hold, 2.0)
            if laughter_silence:
                sig_types.append("laughter_silence")
                recommended_hold = max(recommended_hold, 1.5)
            if delayed:
                sig_types.append("delayed_reaction")
                recommended_hold = max(recommended_hold, 1.2)
            if emotional_pause:
                sig_types.append("emotional_pause")
                recommended_hold = max(recommended_hold, 1.8)
            if eye_shift:
                sig_types.append("eye_gaze_shift")
                recommended_hold = max(recommended_hold, 1.0)
                
            if sig_types:
                signals[fid] = {
                    "fragment_id": fid,
                    "signals": sig_types,
                    "recommended_hold_sec": recommended_hold,
                    "intensity": 0.8 if emotional_pause or laughter_silence else 0.5
                }
                
        return signals
