import os
import time
import requests
from typing import Optional, Dict, Any
from .narrative_director_contract import NarrativeDirection

class ExternalNarrativeAdapter:
    """
    [STEP 10-L-ADAPTER] ExternalNarrativeAdapter (Enhanced for STEP 10-M)
    Handles communication with external LLM APIs (Gemini, Claude, GPT) to obtain creative directing options.
    Limits transmission to metadata only. Supports timeout & retries, and falls back gracefully to standard directions.
    """
    def __init__(self, provider: str = "mock", api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.provider = provider or "mock"
        self.api_key = api_key or os.getenv("EXTERNAL_AI_API_KEY", "")
        self.endpoint = endpoint or os.getenv("EXTERNAL_AI_ENDPOINT", "https://api.openai.com/v1/chat/completions")

    def build_directing_prompt(self, context_metadata: Dict[str, Any]) -> str:
        """
        Builds a prompting payload focusing ONLY on metadata. No full videos, raw transcribing, or ffmpeg variables are exposed.
        Uses emotional timeline and reaction intelligence to provide high-quality cinematic context.
        """
        source_summary = context_metadata.get("source_summary", "No details")
        num_fragments = context_metadata.get("num_fragments", 0)
        scenery_count = context_metadata.get("scenery_count", 0)
        reaction_count = context_metadata.get("reaction_count", 0)
        
        # 1. Emotional Flow Summary
        emotional_timeline = context_metadata.get("emotional_timeline", [])
        emotions_summary = []
        for item in emotional_timeline[:15]:
            emotions_summary.append(f"Time {item['timestamp']}s: {item['emotion']} (intensity: {item['intensity']}, transition: {item['transition']})")
            
        # 2. Reaction Signals Summary
        reaction_signals = context_metadata.get("reaction_signals", {})
        reactions_summary = []
        for fid, sig in list(reaction_signals.items())[:10]:
            reactions_summary.append(f"Frag {fid}: {', '.join(sig['signals'])} (suggested hold: {sig['recommended_hold_sec']}s)")
            
        # 3. Scene Rhythm Flow (Roles sequence)
        scene_rhythm = context_metadata.get("scene_rhythm", [])
        
        prompt = (
            f"You are the Creative Film and Documentary Editing Director.\n"
            f"Based on the following metadata of the video project, determine the editing directing guidelines.\n"
            f"--- Video Project Metadata ---\n"
            f"Source Description Summary: {source_summary}\n"
            f"Total Semantic Fragments available: {num_fragments}\n"
            f"Scenery shots: {scenery_count}, Reaction shots: {reaction_count}\n"
            f"Aesthetic/Emotion sequence outline:\n"
            f"{chr(10).join(emotions_summary) if emotions_summary else 'None'}\n"
            f"Special Reaction Signals detected:\n"
            f"{chr(10).join(reactions_summary) if reactions_summary else 'None'}\n"
            f"Scene Rhythm Flow (Clip Roles): {', '.join(scene_rhythm[:20])}\n"
            f"Pacing metrics desired: {context_metadata.get('target_length', 60.0)} seconds target length.\n"
            f"-------------------------------\n"
            f"Provide your directing decisions strictly in JSON format matching this schema:\n"
            f"{{\n"
            f"  \"pacing_style\": \"fast\" | \"medium\" | \"slow\" | \"slow_to_fast\" | \"fast_to_slow\",\n"
            f"  \"emotion_curve\": \"steady\" | \"dramatic\" | \"peak_at_end\" | \"calm\" | \"dynamic\",\n"
            f"  \"scenery_policy\": \"establishing_only\" | \"high_coverage\" | \"low_coverage\" | \"medium\",\n"
            f"  \"reaction_policy\": \"emphasized\" | \"standard\" | \"minimized\",\n"
            f"  \"breathing_policy\": \"loose\" | \"tight\" | \"standard\",\n"
            f"  \"transition_style\": \"jumpcut\" | \"crossfade\" | \"standard\",\n"
            f"  \"narrative_priority\": \"dialogue\" | \"action\" | \"emotion\" | \"scenery\"\n"
            f"}}\n"
            f"JSON ONLY."
        )
        return prompt

    def get_narrative_direction(self, context_metadata: Dict[str, Any], max_retries: int = 3, timeout_sec: float = 15.0) -> NarrativeDirection:
        """
        Invoke external AI to get creative directing response.
        Enforces 15s timeout limit and 3 retries.
        Falls back to a safe default if API calls fail or is in 'mock' mode.
        """
        print(f"[NARRATIVE_DIRECTOR_REQUEST] Provider: {self.provider}, SourceCount: {context_metadata.get('num_fragments', 0)}")
        
        # Guard if provider is mock or missing api key
        if self.provider == "mock" or not self.api_key:
            # Safe mocking fallback based on user intent keywords
            intent_text = context_metadata.get("user_intent_text", "").lower()
            pacing = "medium"
            scenery = "medium"
            reaction = "standard"
            priority = "dialogue"
            emotion_curve = "steady"
            breathing = "standard"
            
            if any(w in intent_text for w in ["빠르게", "fast", "짧게", "스피디"]):
                pacing = "fast"
                reaction = "minimized"
                breathing = "tight"
            elif any(w in intent_text for w in ["감성", "slow", "느리게", "여운", "다큐"]):
                pacing = "slow"
                reaction = "emphasized"
                priority = "emotion"
                emotion_curve = "dramatic"
                breathing = "loose"
            
            if any(w in intent_text for w in ["풍경은 줄", "no scenery", "배경 줄", "인물 위주"]):
                scenery = "low_coverage"
            elif any(w in intent_text for w in ["풍경", "경치", "scenery"]):
                scenery = "high_coverage"
                priority = "scenery"
                
            mock_dir = NarrativeDirection(
                pacing_style=pacing,
                emotion_curve=emotion_curve,
                scenery_policy=scenery,
                reaction_policy=reaction,
                breathing_policy=breathing,
                transition_style="standard",
                narrative_priority=priority
            )
            print(f"[NARRATIVE_DIRECTOR_RESPONSE] Mocked fallback applied: {mock_dir.dict()}")
            return mock_dir

        prompt = self.build_directing_prompt(context_metadata)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4-turbo" if self.provider == "gpt" else "claude-3-opus" if self.provider == "claude" else "gemini-pro",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 300
        }

        for attempt in range(1, max_retries + 1):
            try:
                # 15s timeout enforced
                response = requests.post(self.endpoint, headers=headers, json=payload, timeout=timeout_sec)
                if response.status_code == 200:
                    data = response.json()
                    raw_content = data["choices"][0]["message"]["content"].strip()
                    # Clean markdown code blocks if any
                    if raw_content.startswith("```"):
                        parts = raw_content.split("```")
                        if len(parts) > 1:
                            raw_content = parts[1]
                        if raw_content.startswith("json"):
                            raw_content = raw_content[4:]
                        raw_content = raw_content.strip()
                    
                    import json
                    parsed = json.loads(raw_content)
                    res_direction = NarrativeDirection(**parsed)
                    print(f"[NARRATIVE_DIRECTOR_RESPONSE] Attempt {attempt} Success: {res_direction.dict()}")
                    return res_direction
            except Exception as e:
                print(f"[NARRATIVE_DIRECTOR_ADAPTER] Attempt {attempt} failed: {e}")
                time.sleep(0.5)

        # Final fallback
        fallback_dir = NarrativeDirection()
        print(f"[NARRATIVE_DIRECTOR_RESPONSE] All attempts failed or timed out. Default fallback: {fallback_dir.dict()}")
        return fallback_dir
