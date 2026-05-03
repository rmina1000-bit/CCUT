import time
from ..contracts.story_intent_patch_contract import StoryIntentPatch, NarrativeLLMResult

def build_mock_narrative_response(user_message: str) -> NarrativeLLMResult:
    """Builds a mock NarrativeLLMResult based on simple keyword rules in the user message."""
    
    start_time = time.time()
    msg = user_message.lower()
    
    patch = StoryIntentPatch()
    
    # Simple rule-based logic for mock
    if "빠르게" in msg or "fast" in msg:
        patch.pacing = "fast"
    elif "천천히" in msg or "slow" in msg:
        patch.pacing = "slow"
        
    if "짧게" in msg or "short" in msg:
        patch.target_length = "short"
    elif "길게" in msg or "long" in msg:
        patch.target_length = "long"
        
    if "웃긴" in msg or "funny" in msg or "재미" in msg:
        patch.tone.append("funny")
        
    if "사람" in msg or "표정" in msg or "face" in msg:
        patch.must_keep.append("face_expression")
        
    if "골고루" in msg or "balanced" in msg or "섞어" in msg:
        patch.source_balance = "balanced"
        
    # Default assistant reply
    reply = f"요청하신 '{user_message}' 내용을 반영하여 편집 방향을 조정하겠습니다."
    
    latency = int((time.time() - start_time) * 1000)
    
    return NarrativeLLMResult(
        assistant_reply=reply,
        story_intent_patch=patch,
        provider="mock_narrative_llm",
        confidence=1.0,
        latency_ms=latency,
        fallback_used=False,
        schema_valid=True
    )
