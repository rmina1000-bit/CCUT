# NARRATIVE PROVIDER CONTRACT HARNESS

## Purpose
The Narrative Provider Contract Harness serves as an isolation layer to validate the communication between the CCUT backend and the Local Narrative LLM (Ollama). It ensures that the `StoryIntentPatch` JSON contract is strictly followed before the LLM is integrated into the UI or Proposal Engine.

## Architecture
- **Contract Definition**: `ccut_backend/ai/boundary/narrative_provider_contract.py`
  - Defines `StoryIntentPatch` and `NarrativeLLMResult`.
  - Defines standardized status codes (OK, MODEL_NOT_FOUND, etc.).
- **Harness Tool**: `tools/harness_narrative_provider_contract.py`
  - Simulates 3 real-world user scenarios.
  - Enforces `think: false` and `JSON Schema` validation.

## Target Baseline
- **Model**: `qwen3:4b`
- **Output Channel**: `raw.response` (Thinking-only is rejected).
- **Format**: JSON Schema enforced via Ollama API.

## Status Codes
| Status | Description |
| :--- | :--- |
| `OK` | Valid JSON in response field matching contract. |
| `THINKING_JSON_ONLY` | JSON only found in thinking field (Rejected for Production). |
| `JSON_PARSE_FAILED` | No valid JSON found in either field. |
| `MODEL_CALL_TIMEOUT` | Request timed out (Default 45s). |
| `OLLAMA_NOT_RUNNING` | Cannot reach Ollama service. |

## Run Instruction
```powershell
python tools/harness_narrative_provider_contract.py
```
