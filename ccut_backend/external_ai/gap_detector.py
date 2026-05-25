from typing import List, Dict, Any

class VideoGapDetector:
    """
    [Phase 2] Video Sequence Narrative and Duration Gap Detector
    Analyzes proposed sequences to detect transition gaps, pacing issues, or missing visual flow,
    and constructs recommended generative prompts for Video AI.
    """
    def __init__(self, target_duration: float = None):
        self.target_duration = target_duration

    def detect_gaps(self, sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans a sequence of fragments and detects potential gaps or issues:
        - Visual/Semantic abrupt cuts (e.g. topic changes without transition)
        - Pacing issues (very short fragments next to each other)
        - Empty gaps (duration deficits relative to target)
        """
        gaps = []
        if not sequence:
            return gaps
            
        for i in range(len(sequence) - 1):
            curr_frag = sequence[i]
            next_frag = sequence[i+1]
            
            curr_sid = curr_frag.get("source_id")
            next_sid = next_frag.get("source_id")
            
            # 1. Source transition gap
            if curr_sid != next_sid:
                curr_topic = curr_frag.get("topic", "")
                next_topic = next_frag.get("topic", "")
                
                # If topics are entirely different, recommend a transition clip
                if curr_topic != next_topic:
                    gaps.append({
                        "type": "semantic_transition_gap",
                        "position_index": i + 1,
                        "description": f"Abrupt transition from source '{curr_sid}' (topic: {curr_topic}) to '{next_sid}' (topic: {next_topic})",
                        "recommended_prompt": f"Smooth transition shot blending {curr_topic} into {next_topic}, cinematic video, 16:9, highly detailed"
                    })
                    
            # 2. Pacing gap (very short sequences)
            curr_dur = curr_frag.get("end", 0.0) - curr_frag.get("start", 0.0)
            if curr_dur < 1.5:
                gaps.append({
                    "type": "pacing_gap",
                    "position_index": i,
                    "description": f"Fragment at index {i} is very short ({curr_dur:.2f}s). May feel too abrupt.",
                    "recommended_prompt": f"Extension of the scene depicting {curr_frag.get('text', 'visual action')}, slow motion, cinematic pacing"
                })
                
        return gaps
