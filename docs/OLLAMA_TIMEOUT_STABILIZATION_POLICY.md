# Ollama Timeout & Stabilization Policy

## 1. Context
During initial smoke-tests with `qwen3:0.6b`, CCUT observed timeouts at the default 10s threshold on developer hardware. To ensure a stable user experience, the following stabilization policies are established.

## 2. Timeout Hierarchies
- **Baseline (10s)**: Reserved for ultra-fast models or high-end GPUs.
- **Extended (20s)**: Recommended for 4B-class models on mid-range hardware.
- **Safe (30s)**: Default for validation phases (R10-C/D) to distinguish between model slowness and system failure.

## 3. Parameter Stabilization
To minimize latency and maximize predictability:
- **`num_predict`**: Capped at **128** for Narrative Consultation. Most `StoryIntentPatch` responses are < 100 tokens.
- **`stream`**: Must be set to **false**. CCUT requires the full JSON response before proceeding.
- **`keep_alive`**: Default to **5m**. Prevents frequent model unloading/reloading cycles during a consultation session.
- **`format`**: Must be set to **json**.

## 4. Failure Classification (Safe Failure)
Model failures must not crash the CCUT backend. The following status codes are used within the AI Boundary:
- `OK`: Successful generation and contract validation.
- `OLLAMA_NOT_RUNNING`: Local Ollama server is offline.
- `MODEL_NOT_FOUND`: The requested model (e.g., qwen3:4b) is not in the registry.
- `MODEL_CALL_TIMEOUT`: Request exceeded the configured timeout (e.g., 30s).
- `MODEL_CALL_FAILED`: Other runtime errors (e.g., VRAM exhaustion).
- `JSON_PARSE_FAILED`: Model returned text instead of valid JSON.
- `CONTRACT_INVALID`: JSON parsed but missing mandatory `StoryIntentPatch` keys.

## 5. Fallback Rule
If any status other than `OK` is returned:
1. Return a **safe default** `StoryIntentPatch` (No-op).
2. Log the error in the Decision Log.
3. Fall back to the **Mock Narrative LLM Adapter** if configured.
