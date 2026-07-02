import json
import os
import requests
from .narrative_director_contract import NarrativeDirection

OLLAMA_BASE_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL = os.getenv("CCUT_NARRATIVE_DIRECTOR_MODEL", "qwen2:latest")
KEEP_ALIVE = os.getenv("CCUT_NARRATIVE_DIRECTOR_KEEP_ALIVE", "10m")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


TIMEOUT = _env_float("CCUT_NARRATIVE_DIRECTOR_TIMEOUT", 45.0)

ALLOWED_PACING = {"fast", "medium", "slow", "slow_to_fast", "fast_to_slow"}
ALLOWED_EMOTION = {"steady", "dramatic", "peak_at_end", "calm", "dynamic"}
ALLOWED_SCENERY = {"establishing_only", "high_coverage", "low_coverage", "medium"}
ALLOWED_REACTION = {"emphasized", "standard", "minimized"}
ALLOWED_BREATHING = {"loose", "tight", "standard"}
ALLOWED_TRANSITION = {"jumpcut", "crossfade", "standard"}
ALLOWED_PRIORITY = {"dialogue", "action", "emotion", "scenery"}

PROMPT_TEMPLATE = """You are a film editing director.
Given the following video metadata, return editing direction as JSON only.
No explanation. No markdown. JSON only.

Metadata:
- Fragments: {num_fragments}
- Scenery shots: {scenery_count}
- Reaction shots: {reaction_count}
- Target length: {target_length}s
- User intent: {user_intent}

Return exactly this JSON schema:
{{
  "pacing_style": "fast"|"medium"|"slow"|"slow_to_fast"|"fast_to_slow",
  "emotion_curve": "steady"|"dramatic"|"peak_at_end"|"calm"|"dynamic",
  "scenery_policy": "establishing_only"|"high_coverage"|"low_coverage"|"medium",
  "reaction_policy": "emphasized"|"standard"|"minimized",
  "breathing_policy": "loose"|"tight"|"standard",
  "transition_style": "jumpcut"|"crossfade"|"standard",
  "narrative_priority": "dialogue"|"action"|"emotion"|"scenery"
}}"""


class QwenNarrativeAdapter:
    def get_narrative_direction(self, context_metadata: dict) -> NarrativeDirection:
        print(f"[NARRATIVE_DIRECTOR_REQUEST] Provider: qwen model={MODEL}, "
              f"SourceCount: {context_metadata.get('num_fragments', 0)}")
        try:
            prompt = PROMPT_TEMPLATE.format(
                num_fragments=context_metadata.get("num_fragments", 0),
                scenery_count=context_metadata.get("scenery_count", 0),
                reaction_count=context_metadata.get("reaction_count", 0),
                target_length=context_metadata.get("target_length", 60.0),
                user_intent=context_metadata.get("user_intent_text", "")
            )
            payload = {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": KEEP_ALIVE,
                "options": {"temperature": 0, "num_predict": 256},
            }
            resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
            # strip markdown fences if any
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            parsed = json.loads(raw)
            direction = NarrativeDirection(
                pacing_style=parsed.get("pacing_style", "medium")
                    if parsed.get("pacing_style") in ALLOWED_PACING else "medium",
                emotion_curve=parsed.get("emotion_curve", "steady")
                    if parsed.get("emotion_curve") in ALLOWED_EMOTION else "steady",
                scenery_policy=parsed.get("scenery_policy", "medium")
                    if parsed.get("scenery_policy") in ALLOWED_SCENERY else "medium",
                reaction_policy=parsed.get("reaction_policy", "standard")
                    if parsed.get("reaction_policy") in ALLOWED_REACTION else "standard",
                breathing_policy=parsed.get("breathing_policy", "standard")
                    if parsed.get("breathing_policy") in ALLOWED_BREATHING else "standard",
                transition_style=parsed.get("transition_style", "standard")
                    if parsed.get("transition_style") in ALLOWED_TRANSITION else "standard",
                narrative_priority=parsed.get("narrative_priority", "dialogue")
                    if parsed.get("narrative_priority") in ALLOWED_PRIORITY else "dialogue",
            )
            print(f"[NARRATIVE_DIRECTOR_RESPONSE] Provider: qwen model={MODEL}, "
                  f"direction: {direction.dict()}")
            return direction
        except Exception as e:
            print(f"[NARRATIVE_DIRECTOR_ERROR] QwenNarrativeAdapter failed: {e}. "
                  f"Using default NarrativeDirection.")
            return NarrativeDirection()
