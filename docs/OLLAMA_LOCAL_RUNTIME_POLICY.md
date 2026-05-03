# Ollama Local Runtime Policy

## 1. Role of Ollama
Ollama is the primary local runtime candidate for the CCUT Narrative LLM. It provides a standardized API for managing and running large language models in a local environment.

## 2. Adoption Strategy
- **Standard Runtime**: We prefer Ollama for its ease of use on Windows and its robust model management.
- **Independence**: CCUT Core must not depend on Ollama-specific features. All calls must go through the AI Boundary using the `StoryIntentPatch` contract.
- **Model Flexibility**: While Qwen3-Instruct is the primary candidate, the policy allows any model available via Ollama (e.g., Mistral, Llama, Gemma) as long as it adheres to the contract.

## 3. Configuration & Fallback
- **Endpoint**: The default endpoint is `http://127.0.0.1:11434`.
- **Failure Mode**: If Ollama is not detected or the model fails, the system must immediately fall back to the internal rule-based logic without blocking the user experience.

## 4. Resource Management
- **VRAM Control**: CCUT expects Ollama to handle VRAM allocation. However, CCUT's AI Boundary should provide a "compatibility probe" (R8) to warn the user if VRAM is insufficient for the selected model.
- **Local Only**: By default, CCUT treats Ollama as a local-only service. External network calls to remote Ollama instances are prohibited unless explicitly configured by the user.

## 5. Licensing
- The use of Ollama itself is subject to its own license.
- The models run via Ollama (Qwen, Mistral, etc.) have their own specific licenses which must be reviewed per model.
