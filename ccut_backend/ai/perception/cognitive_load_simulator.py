from typing import List, Dict, Any

class CognitiveLoadSimulator:
    """
    [STEP 12-D] CognitiveLoadSimulator
    Simulates human working memory capacity limits (7 +/- 2 chunks), context switching fatigue,
    information entropy density, subtitle reading speed, and narrative role ordering confusion.
    """
    def __init__(self, memory_buffer_capacity: int = 4):
        # Human working memory can actively process roughly 4 visual/conceptual contexts simultaneously
        self.memory_buffer_capacity = memory_buffer_capacity

    def simulate_cognitive_load(self, sequence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates timeline-based cognitive load and viewer confusion drop-off risks.
        """
        if not sequence:
            return {
                "cognitive_load": 0.0,
                "confusion_points": [],
                "viewer_drop_risk": 0.0,
                "context_switching_fatigue": 0.0,
                "cognitive_events": []
            }

        cognitive_load = 0.15  # Baseline cognitive load
        timeline = 0.0
        
        confusion_points = []
        cognitive_events = []
        
        # Working memory buffer: tracks active source video context
        working_memory_sources = []
        context_switch_penalty = 0.0
        
        seen_roles = set()
        has_hooked = False
        
        for idx, clip in enumerate(sequence):
            dur = float(clip.get("duration") or clip.get("duration_sec") or 5.0)
            sid = clip.get("source_id", "SRC_UNKNOWN")
            role = clip.get("structural", {}).get("role", "main")
            edit_val = float(clip.get("structural", {}).get("edit_value", 0.5))
            
            # Extract transcript text
            intel = clip.get("intelligence") or {}
            txt = str(intel.get("transcript", "") or clip.get("semantic", {}).get("transcript_refs", ""))
            word_count = len(txt.split())
            
            # --- 1. Working Memory Buffer & Context Switching Fatigue ---
            # Shifting context (different source_ids) requires cognitive load to recall prior settings
            if idx > 0:
                prev_sid = sequence[idx - 1].get("source_id", "SRC_UNKNOWN")
                if prev_sid != sid:
                    # Switch event!
                    cognitive_load += 0.08
                    context_switch_penalty += 0.05
                    
                    if sid in working_memory_sources:
                        # Context was in working memory, recovery is easier
                        cognitive_load -= 0.03
                        working_memory_sources.remove(sid)
                        working_memory_sources.append(sid)  # Mark as MRU
                    else:
                        # Fresh source context, memory buffer insertion
                        working_memory_sources.append(sid)
                        if len(working_memory_sources) > self.memory_buffer_capacity:
                            # Memory buffer overload! Old context evicted.
                            evicted = working_memory_sources.pop(0)
                            cognitive_load += 0.12  # Memory overload penalty
                            confusion_points.append(round(timeline, 2))
                            cognitive_events.append({
                                "timestamp": round(timeline, 2),
                                "type": "working_memory_eviction",
                                "reason": f"Working memory buffer limit exceeded ({self.memory_buffer_capacity} sources). Evicted context {evicted}."
                            })
                else:
                    # Sustained context decays switching load slightly
                    cognitive_load = max(0.05, cognitive_load - 0.02)
            else:
                working_memory_sources.append(sid)

            # --- 2. Information Density & Entropy ---
            # High transcript words per second + rapid cuts = high load
            words_per_sec = word_count / dur
            if words_per_sec > 3.0:
                # Fast narration overload
                narrative_pressure = (words_per_sec - 3.0) * 0.08
                cognitive_load += narrative_pressure
                if words_per_sec > 4.5 and dur < 3.0:
                    cognitive_load += 0.15
                    confusion_points.append(round(timeline, 2))
                    cognitive_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "narration_overload",
                        "reason": f"Narration speed ({words_per_sec:.1f} words/sec) is too fast for a short cut ({dur:.1f}s)"
                    })

            # --- 3. Narrative Role Sequence Confusion ---
            # A well-formed narrative structure follows a progression.
            # - Hook must occur early (within the first 25% of the video).
            # - Payoff must occur late.
            # - Direct scenery or payoff before a hook triggers confusion.
            if role == "hook":
                has_hooked = True
            
            if not has_hooked and idx > 0 and role in ["payoff", "reaction"]:
                # Jumped straight into reaction/payoff without context setup
                cognitive_load += 0.15
                confusion_points.append(round(timeline, 2))
                cognitive_events.append({
                    "timestamp": round(timeline, 2),
                    "type": "narrative_disorder",
                    "reason": f"Jarring entry: {role} shot presented before any hook or main context was established"
                })
            
            # Multiple fast cuts in a row (e.g. 4 consecutive shots < 2.0s) cause cognitive breakdown
            if dur < 2.0 and idx > 2:
                prev_durs = [float(x.get("duration") or x.get("duration_sec") or 5.0) for x in sequence[idx-3:idx]]
                if all(d < 2.2 for d in prev_durs):
                    cognitive_load += 0.1
                    confusion_points.append(round(timeline, 2))
                    cognitive_events.append({
                        "timestamp": round(timeline, 2),
                        "type": "cognitive_whiplash",
                        "reason": "Rapid sequence cuts (4 consecutive cuts under 2.2s) exceeding viewer digestion rate"
                    })

            seen_roles.add(role)
            timeline += dur
            
        final_load = max(0.05, min(1.0, cognitive_load))
        # Compute exponential viewer drop risk based on load pressure
        viewer_drop_risk = round(1.0 - (1.0 / (1.0 + pow(final_load, 2.5))), 3)
        
        return {
            "cognitive_load": round(final_load, 3),
            "confusion_points": sorted(list(set(confusion_points))),
            "viewer_drop_risk": viewer_drop_risk,
            "context_switching_fatigue": round(min(1.0, context_switch_penalty), 3),
            "cognitive_events": cognitive_events
        }
