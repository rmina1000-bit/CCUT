# QWEN3:4B OLLAMA PROBE RESULT

## Status
**HOLD** (R10-E-R1 required)

## R10-E Results
- model qwen3:4b installed
- Ollama call success: 4/4
- timeout: 0
- latency: 3.7s ~ 6.2s
- raw.response: **empty**
- raw.thinking: contains valid StoryIntentPatch-shaped JSON
- contract_validation: **JSON_PARSE_FAILED** (Response-only policy)

## R10-E-R2 Results
- model: qwen3:4b
- CASE 8: **OK**, 3717ms
- CASE 9: **OK**, 3767ms
- CASE 10: **OK**, 3795ms (JSON Schema)
- Success Count: 3
- Thinking-only Count: 0
- Failure Count: 0
- **Validated Setting:**
  - `think: false`
  - `format: json` or `JSON Schema`
  - `temperature: 0`
  - `num_predict: 128 ~ 256`
  - `keep_alive: 10m`
- **Conclusion:** `qwen3:4b` is viable for the Narrative LLM contract probe. Ready for Contract Harness (R10-F).

## Next Priority (R10-F)
Implement the **Narrative Provider Contract Harness** to standardize inputs/outputs and safe failures.

## Required Action
Create `narrative_provider_contract.py` and its harness.

## Prepared Probe Script (R2)
`tools/probe_ollama_timeout_stabilization.py` is fully operational with R1/R2 repair support.

## Target Metrics
- JSON Parse Success: 100%
- StoryIntentPatch Contract Validation: 100%
- Acceptable Latency: < 45s for CASE 3
