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
    reason: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryIntentPatch":
        return cls(
            patch_type=data.get("patch_type", "story_intent_patch"),
            tone=data.get("tone", "natural"),
            target_length=data.get("target_length", "medium"),
            must_keep=data.get("must_keep", []),
            avoid=data.get("avoid", []),
            reason=data.get("reason", "")
        )

@dataclass
class ConversationIntent:
    input_type: str  # greeting, system_question, editing_instruction, editing_feedback, confirmation, complaint_or_confusion, proposal_request, unknown
    confidence: float = 0.0
    needs_story_patch: bool = False
    reply_type: str = "fallback"  # greeting, explain_role, acknowledge, clarify, fallback
    short_reply: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationIntent":
        return cls(
            input_type=data.get("input_type", "unknown"),
            confidence=data.get("confidence", 0.0),
            needs_story_patch=data.get("needs_story_patch", False),
            reply_type=data.get("reply_type", "fallback"),
            short_reply=data.get("short_reply", ""),
            reason=data.get("reason", "")
        )

@dataclass
class NarrativeLLMResult:
    status: str
    patch: Optional[StoryIntentPatch] = None
    classification: Optional[ConversationIntent] = None
    latency_ms: int = 0
    raw_response: str = ""
    thinking: str = ""
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

def validate_narrative_contract(text: str) -> bool:
    """Check if the text contains a valid Narrative Combined Response JSON."""
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
        # Check for classification
        if "classification" not in data:
            return False
        
        clf = data["classification"]
        required_clf = ["input_type", "needs_story_patch", "short_reply"]
        if not all(k in clf for k in required_clf):
            return False
            
        # If needs_story_patch is true, check for patch fields
        if clf.get("needs_story_patch"):
            patch = data.get("patch", {})
            required_patch = ["tone", "target_length", "must_keep", "avoid"]
            if not all(k in patch for k in required_patch):
                return False
                
        return True
    except:
        return False
