import math
from typing import List, Dict, Any

class AuditoryFatigueSimulator:
    """
    [STEP 12-B] AuditoryFatigueSimulator
    Models virtual viewer auditory pressure, speech density, decibel loudness transitions,
    and identifies critical moments where quiet/silence breaks are required.
    """
    def __init__(self, target_speech_density: float = 0.65):
        # Target threshold: if speech takes up > 65% of the video time, it causes listening fatigue
        self.target_speech_density = target_speech_density

    def simulate_audio(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simulates human auditory processing to assess audio fatigue and transition shocks.
        """
        if not sequence:
            return {
                "audio_fatigue": 0.0,
                "breathing_recommended": False,
                "silence_needed_after": [],
                "loudness_instability": 0.0,
                "auditory_events": []
            }

        audio_fatigue = 0.1  # Starting base fatigue
        silence_needed_after = []
        auditory_events = []
        
        timeline = 0.0
        continuous_speech_duration = 0.0
        total_speech_duration = 0.0
        total_duration = 0.0
        
        energy_values = []
        
        for idx, clip in enumerate(sequence):
            dur = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
            total_duration += dur
            
            # Extract transcript presence and audio energy
            intel = clip.get("intelligence") or {}
            has_speech = bool(intel.get("transcript"))
            audio_energy = float(clip.get("audio_energy") or clip.get("evidence", {}).get("audio_energy", 0.4))
            
            # Save energy value for instability tracking
            energy_values.append(audio_energy)
            
            # --- 1. Speech Density & Pacing Pressure ---
            if has_speech:
                total_speech_duration += dur
                continuous_speech_duration += dur
                
                # Speech increases listening fatigue linearly over time
                # High energy speech increases it faster
                speech_pressure = 0.015 * dur * (1.0 + audio_energy)
                audio_fatigue += speech_pressure
                
                # Warn if speech continues unbroken for over 14 seconds
                if continuous_speech_duration > 14.0:
                    audio_fatigue += 0.06
                    silence_needed_after.append(round(timeline + dur, 2))
                    auditory_events.append({
                        "timestamp": round(timeline + dur, 2),
                        "type": "speech_pressure",
                        "reason": f"Continuous unbroken speech for {continuous_speech_duration:.1f}s without pauses"
                    })
            else:
                # Silence / music breaks recover auditory comfort
                # Deeper recovery for quiet scenes (low audio energy)
                recovery = 0.06 * dur * (1.0 - audio_energy)
                audio_fatigue = max(0.0, audio_fatigue - recovery)
                continuous_speech_duration = 0.0
                
            # --- 2. Decibel (dB) transition shock ---
            if idx > 0:
                prev_clip = sequence[idx - 1]
                prev_energy = float(prev_clip.get("audio_energy") or prev_clip.get("evidence", {}).get("audio_energy", 0.4))
                
                # Prevent math domain errors on zero or extremely low values
                p_e = max(0.001, prev_energy)
                c_e = max(0.001, audio_energy)
                
                # Logarithmic decibel difference approximation: dB = 20 * log10(E1 / E2)
                db_diff = abs(20 * math.log10(c_e / p_e))
                
                if db_diff > 12.0:
                    # Loudness shock (abrupt jump or drop)
                    shock_weight = (db_diff - 12.0) * 0.02
                    audio_fatigue += min(0.2, 0.05 + shock_weight)
                    
                    auditory_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "loudness_shock",
                        "reason": f"Abrupt decibel change of {db_diff:.1f} dB at clip boundary"
                    })
            
            timeline += dur
            
        # --- 3. Loudness Instability Calculation ---
        # Compute standard deviation of audio energy values
        mean_energy = sum(energy_values) / len(energy_values) if energy_values else 0.0
        variance = sum((x - mean_energy) ** 2 for x in energy_values) / len(energy_values) if energy_values else 0.0
        loudness_instability = round(math.sqrt(variance), 3)
        
        # Instability adds to overall fatigue
        audio_fatigue += loudness_instability * 0.25
        
        # --- 4. Speech Ratio Overuse Penalty ---
        speech_ratio = total_speech_duration / total_duration if total_duration > 0 else 0.0
        if speech_ratio > self.target_speech_density:
            overuse_multiplier = (speech_ratio - self.target_speech_density) / (1.0 - self.target_speech_density)
            audio_fatigue += 0.15 * overuse_multiplier
            auditory_events.append({
                "timestamp": round(total_duration, 2),
                "type": "speech_overload",
                "reason": f"Overall speech density too high ({speech_ratio*100:.1f}%), exceeding target {self.target_speech_density*100:.1f}%"
            })
            
        final_fatigue = max(0.0, min(1.0, audio_fatigue))
        breathing_recommended = final_fatigue > 0.55 or len(silence_needed_after) > 0
        
        return {
            "audio_fatigue": round(final_fatigue, 3),
            "breathing_recommended": breathing_recommended,
            "silence_needed_after": sorted(list(set(silence_needed_after))),
            "loudness_instability": loudness_instability,
            "auditory_events": auditory_events
        }
