from typing import Protocol, Optional, Dict, Any
from dataclasses import dataclass
from .story_intent_patch_contract import NarrativeLLMResult

@dataclass
class NarrativeLLMProviderInfo:
    """Metadata for a Narrative LLM Provider."""
    provider_id: str
    provider_name: str
    provider_family: str
    runtime: str
    model_id: Optional[str] = None
    license_name: Optional[str] = None
    license_review_required: bool = True
    local_only: bool = True
    supports_json: bool = True
    supports_korean: str = "yes"
    status: str = "candidate"

class NarrativeLLMProvider(Protocol):
    """Protocol for all Narrative LLM Providers."""
    
    def get_provider_info(self) -> NarrativeLLMProviderInfo:
        """Returns metadata about the provider."""
        ...
        
    def generate_story_intent(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> NarrativeLLMResult:
        """Generates a StoryIntentPatch based on user input and context."""
        ...
