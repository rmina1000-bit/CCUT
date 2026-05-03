# Qwen Provider Candidate Plan

## 1. Role Definition
Qwen3-Instruct is the **Primary Candidate** for the Narrative LLM provider. Its role is to interpret user messages and generate `StoryIntentPatch` JSON objects.

## 2. Separation from ASR
Qwen3-ASR and Qwen3-Instruct serve different purposes:
- **ASR**: Real-time transcription of audio fragments.
- **Instruct**: Conversational reasoning and intent modeling.
They should be managed as separate provider instances, even if they share the same model family or runtime binary.

## 3. Avoid Hard Dependencies
When implementing the Qwen provider, the following must be avoided:
- **Hard-coded paths**: Model file paths must be configurable via `config.yaml`.
- **Core-embedded prompts**: The system prompt (prompt engineering) must stay inside the provider adapter.
- **Raw Text Dependence**: The ProposalEngine must only receive structured `StoryIntentPatch` objects, never raw model text.

## 4. Why Qwen?
- **Modality Unity**: Same ecosystem as the proven ASR model.
- **JSON Quality**: Strong benchmark performance in structured output.
- **Korean Proficiency**: High accuracy in interpreting Korean narrative nuances.
- **Efficiency**: 7B variant runs comfortably on mid-range local GPUs.

## 5. Implementation Path
1. Define the Qwen adapter in `ccut_backend/ai/adapters/qwen3_llm_adapter.py`.
2. Map the adapter in the Narrative Provider Registry.
3. Use the unified AI Boundary to toggle between the Mock provider and the Qwen provider.
4. (R9 Update) Use the Ollama Provider Probe to detect local Qwen model availability before activation.
