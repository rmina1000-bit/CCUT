# Qwen Model Inventory

## 1. Overview
This document catalogs all Qwen-related models currently detected in the CCUT local environment (D:\CCUT1.0.4 and legacy D:\CCUT_1.0.3).

## 2. Model Classification

### A. Qwen3-ASR (Audio-to-Text)
Currently the only active Qwen-based AI service in CCUT.
- **Qwen3-ASR 0.6B**: Available in both 1.0.3 and 1.0.4 directories.
- **Qwen3-ASR 1.7B**: Available in both 1.0.3 and 1.0.4 directories.
- **Status**: ACTIVE (Primary ASR provider).

### B. Qwen3-Instruct (Narrative LLM)
Used for Narrative Consultation and StoryIntentPatch generation.
- **Status**: **MISSING/NOT FOUND**.
- **Observation**: No Instruct-variant GGUF or Safetensors files were detected in the `ai_models` folders.

### C. Qwen2 (Legacy)
- **Status**: FOUND in Ollama registry (`qwen2:latest`).
- **Observation**: Legacy version, not currently used by CCUT 1.0.4 boundary logic.

### D. Qwen-VL (Vision-Language)
- **Status**: MISSING. Only placeholders exist in the codebase.

### E. Qwen-Coder
- **Status**: MISSING.

## 3. Inventory Details

| Location | Model Name | Format | Size/Variant |
|----------|------------|--------|--------------|
| D:\CCUT1.0.4\...\ai_models | qwen3-asr-0.6b | GGUF | 0.6B |
| D:\CCUT1.0.4\...\ai_models | qwen3-asr-1.7b | GGUF | 1.7B |
| D:\CCUT_1.0.3\...\ai_models | qwen3-asr-0.6b | GGUF | 0.6B |
| D:\CCUT_1.0.3\...\ai_models | qwen3-asr-1.7b | GGUF | 1.7B |
| Ollama Registry | qwen2 | Ollama | latest |

## 4. Conclusion
The current inventory confirms that CCUT has **ASR-specialized Qwen3 models** but lacks the **Instruct-specialized Qwen3 models** required for meaningful Narrative Consultation. R10-B must address the strategy for acquiring and registering Qwen3-Instruct models.
