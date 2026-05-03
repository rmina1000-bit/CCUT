# Ollama Model Registration Policy

## 1. Current State
As of the current audit, the only model registered in Ollama is `qwen2:latest`. This is a legacy model used for testing and is **not** a candidate for the Narrative LLM staff.

## 2. Registration Principles
- **No Auto-Pull**: The CCUT backend shall never execute `ollama pull` without user intervention.
- **Explicit Inventory**: The `narrative_provider_registry.py` defines the expected model names.
- **Manual Registration Candidates**:
  - `qwen3:4b` (Primary Validation Target)
  - `qwen3:0.6b` (Experimental/Tested)
- **Manual Registration Command**:
  - `ollama pull qwen3:4b`
  - `ollama list` (to verify)
  - `ollama show <model>` (to check parameters)

## 3. Verification Protocol
After manual registration, the connection must be verified using:
```bash
python tools\probe_ollama_narrative_provider.py
```

## 4. Configuration Guard
- Model names must not be hard-coded in the CCUT Core logic.
- The `ai/config.yaml` or the `provider_registry` should be the only places where model IDs are mapped.

## 5. Swappability & Fallback
Ollama is a runtime provider. If a specific model is too slow or fails schema validation, the AI Boundary must facilitate a swap to another local model or fall back to the rule-based mock provider.
