# Narrative Model Selection Matrix

## 1. Candidate Comparison

| Candidate | License Safety | Korean Proficiency | JSON Compliance | Runtime | VRAM Req | Status |
|-----------|----------------|--------------------|-----------------|---------|----------|--------|
| **Qwen3-4B-Instruct** | Apache-2.0* | High | High | Ollama/llama | 4GB - 8GB | **Primary Validation** |
| **Qwen3-8B-Instruct** | Apache-2.0* | High | High | Ollama/llama | 8GB - 12GB | **Product Target** |
| **Mistral-7B-v0.3** | Apache-2.0 | Medium | High | Ollama/llama | 6GB - 10GB | **Secondary** |
| **Gemma-2-9B** | **CAUTION** | Medium/High | Medium | Ollama | 8GB - 14GB | **Caution** |
| **Llama-3.1-8B** | **CAUTION** | High | High | Ollama/llama | 6GB - 10GB | **Caution** |
| **Mock Adapter** | MIT | N/A | Perfect | Python | < 10MB | **Fallback** |

*\*Note: Actual model LICENSE must be checked at the selected model repository.*

## 2. Selection Rationale

### Primary: Qwen3-Instruct
Chosen for its synergy with the existing Qwen3-ASR pipeline, excellent Korean instruction following, and strong adherence to structured JSON outputs required for `StoryIntentPatch`.

### Secondary: Mistral
A reliable fallback with a clean Apache-2.0 license, widely supported across all local runtimes.

### Caution: Gemma / Llama
These models are high-performance but governed by model-specific community licenses (Google Gemma Terms / Meta Llama 3.1 License). They require legal review before commercial integration and are marked as **CAUTION_CANDIDATE** in the registry.

### Fallback: Mock / Rule-Based
Ensures CCUT remains functional even in environments without compatible GPUs or model runtimes.
