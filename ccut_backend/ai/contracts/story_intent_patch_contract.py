from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class StoryIntentPatch:
    """Represents a set of proposed changes to the narrative intent."""
    tone: List[str] = field(default_factory=list)
    target_length: Optional[str] = None
    pacing: Optional[str] = None
    must_keep: List[str] = field(default_factory=list)
    avoid: List[str] = field(default_factory=list)
    source_balance: Optional[str] = None
    constraints: List[str] = field(default_factory=list)

@dataclass
class NarrativeLLMResult:
    """The complete result returned by a Narrative LLM provider."""
    assistant_reply: str
    story_intent_patch: StoryIntentPatch
    provider: str
    confidence: float
    latency_ms: int
    fallback_used: bool
    fallback_reason: Optional[str] = None
    schema_valid: bool = True
