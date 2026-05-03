# Narrative LLM Mock Adapter Specification

## 1. Overview
The **Mock Narrative LLM Adapter** is a non-runtime skeleton designed to verify the contract and data flow for the Narrative Consultation pipeline before integrating actual AI models. It resides within the AI Boundary and returns static but structured `StoryIntentPatch` results.

## 2. Objective
- Define the `StoryIntentPatch` and `NarrativeLLMResult` contracts.
- Provide a predictable testing target for backend-to-AI-boundary integration.
- Ensure the schema handles various narrative intent dimensions (tone, pacing, must-keep, etc.).
- Establish a baseline for R7, where actual local LLMs (Qwen3-Instruct) will be connected.

## 3. StoryIntentPatch Contract
The patch represents incremental changes suggested by the AI based on user dialogue.

```python
@dataclass
class StoryIntentPatch:
    tone: List[str]
    target_length: Optional[str]
    pacing: Optional[str]
    must_keep: List[str]
    avoid: List[str]
    source_balance: Optional[str]
    constraints: List[str]
```

## 4. Provider Swap Architecture Integration
- The Mock Adapter is the first **ACTIVE_MOCK** implementation of the `NarrativeLLMProvider` protocol.
- It serves as a test double to verify that the CCUT Core can interact with any provider conforming to the contract.
- In production, the system can swap between this mock, Qwen, or other models defined in the `narrative_provider_registry`.

## 5. Mock Logic Details
The current mock implementation (`mock_narrative_llm.py`) uses simple keyword matching to populate the patch fields:
- "빠르게" -> `pacing: "fast"`
- "짧게" -> `target_length: "short"`
- "웃긴" -> `tone: ["funny"]`
- "사람/표정" -> `must_keep: ["face_expression"]`
- "골고루/섞어" -> `source_balance: "balanced"`

## 6. Runtime Isolation
- This adapter is located in `ccut_backend/ai/boundary/`.
- It is **not** imported by `main.py` or any other production runtime code in this stage.
- Verification is performed through standalone scripts in `tools/`.

## 7. Next Steps (R7)
- Integrate `ccut_backend.ai.adapters.qwen3_llm_adapter`.
- Connect the adapter to a local inference engine (Ollama or llama.cpp).
- Replace the mock logic with actual model inference while maintaining the same contract.
