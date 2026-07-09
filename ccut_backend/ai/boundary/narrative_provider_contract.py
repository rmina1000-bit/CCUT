import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

class NarrativeLLMStatus:
    OK = "OK"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    OLLAMA_NOT_RUNNING = "OLLAMA_NOT_RUNNING"
    MODEL_CALL_TIMEOUT = "MODEL_CALL_TIMEOUT"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    THINKING_JSON_ONLY = "THINKING_JSON_ONLY"

@dataclass
class StoryIntentPatch:
    patch_type: str = "story_intent_patch"
    tone: str = "natural"
    target_length: str = "medium"
    must_keep: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    coverage: str = "default"
    reason: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryIntentPatch":
        return cls(
            patch_type=data.get("patch_type", "story_intent_patch"),
            tone=data.get("tone", "natural"),
            target_length=data.get("target_length", "medium"),
            must_keep=data.get("must_keep", []),
            avoid=data.get("avoid", []),
            coverage=data.get("coverage", "default"),
            reason=data.get("reason", "")
        )

@dataclass
class NarrativeLLMResult:
    status: str
    patch: Optional[StoryIntentPatch] = None
    latency_ms: int = 0
    raw_response: str = ""
    thinking: str = ""
    error_message: str = ""
    mirror: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

def validate_narrative_contract(text: str) -> bool:
    """Check if the text contains a valid StoryIntentPatch JSON."""
    if not text:
        return False
    
    # Simple markdown stripping
    clean_text = text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text.split("```json")[1].split("```")[0].strip()
    elif clean_text.startswith("```"):
        clean_text = clean_text.split("```")[1].split("```")[0].strip()
        
    try:
        data = json.loads(clean_text)
        required = ["patch_type", "tone", "target_length", "must_keep", "avoid", "coverage", "reason"]
        return all(k in data for k in required)
    except:
        return False
