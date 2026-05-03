# Adopted Open-Source AI Strategy

## 1. AI Staff Definition
AI is not an "adopted child" but a **Primary AI Staff** or **Core Companion**. This distinction ensures that while AI provides high-value intelligence, the CCUT Core retains ownership of the project's logic and data.

## 2. CCUT Core Assets (Immutable)
The following assets are owned and managed by the CCUT Core, independent of the AI provider:
- **Evidence Board**: Source data and analysis results.
- **Semantic Fragment**: The fundamental units of video understanding.
- **StoryIntent**: The high-level narrative direction.
- **Proposal**: Generated edit sequences.
- **Decision Log**: Audit trail of user and AI choices.
- **ExportInput**: The final data structure for rendering.
- **Render**: The physical output generation.
- **User Selection Data**: Preferences and confirmed choices.

## 3. AI Staff Roles
AI Staff members are specialized providers within the AI Boundary:
- **ASR**: Audio-to-text transcription (e.g., Qwen3-ASR).
- **Narrative / StoryIntentPatch**: Conversational consultation and intent adjustment.
- **Vision / VLM**: Frame and scene understanding.
- **QA**: Quality assessment of cuts and transitions.
- **Code Assist**: (Future) Assistance with EDL or script generation.

## 4. Integration Strategy: Boundary-Based Core Companion
- **Direct Core Embedding (Prohibited)**: We do not hard-code specific LLM logic into the CCUT Core.
- **Boundary-Based Core Companion (Recommended)**: AI providers interact with the Core through a standardized AI Boundary.
- **Provider Swapability**: The system must allow switching between AI families (e.g., Qwen to Mistral) without modifying Core logic.
- **Base Model + Adapter/LoRA Separation**: Foundation models remain clean, while CCUT-specific knowledge is stored in separate adapters or LoRA weights.

## 5. AI Family Classification
- **Primary AI Staff**: Qwen family (Strongest recommendation for all-in-one capability).
- **Secondary AI Staff**: Mistral family (Strong fallback for LLM tasks).
- **Caution AI Staff**: Gemma / Llama (Requires separate license review for commercial use).
