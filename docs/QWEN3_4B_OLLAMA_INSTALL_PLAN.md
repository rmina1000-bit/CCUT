# Qwen3 4B Ollama Candidate Install Plan

## 1. Overview
This plan defines the manual installation and registration of **Qwen3 4B-Instruct** as the primary validation baseline for CCUT Narrative LLM.

## 2. Selection Rationale
- **Validation Baseline**: Qwen3 4B is designated as the balance point between resource efficiency (dev-PC) and quality (structured JSON).
- **Comparison Findings**: 
  - `qwen2:latest` is legacy/test-only.
  - `qwen3:0.6b` (tested by user) showed high latency/timeout on the current environment.
  - `qwen3:4b` is the next logical step to test if a larger model with proper parameter tuning can meet the quality bar.

## 3. Manual Installation Steps
Installation must be performed manually by the user. The CCUT backend will not trigger these commands automatically.

### Command
```bash
ollama pull qwen3:4b
```

### Verification
```bash
ollama list
ollama show qwen3:4b
python tools\probe_ollama_narrative_provider.py
```

## 4. Integration Guard
- **No Hard-coding**: The model ID `qwen3:4b` is managed via the provider registry, not hard-coded in core logic.
- **Timeout Management**: If 4B also times out (as 0.6B did), R10-D will focus on `keep_alive`, `num_predict`, and hardware acceleration settings.

## 5. Rollback Policy
If installation fails or system stability is compromised:
- Revert to **Mock Narrative LLM Adapter**.
- No code rollback required as this is a runtime configuration change.
