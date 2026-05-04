# QWEN3:4B OLLAMA PROBE RESULT

## Status
**HOLD** (BLOCKED_BY_MODEL_NOT_INSTALLED)

## Reason
`qwen3:4b` is not installed in the local Ollama environment.

## Required Action
User must manually install the model:
```powershell
ollama pull qwen3:4b
ollama list
```

## Prepared Probe Script
`tools/probe_ollama_timeout_stabilization.py` has been updated to:
- Support `--model` and `--output-dir` arguments.
- Include a pre-check using `/api/tags` to distinguish between `OLLAMA_NOT_RUNNING` and `MODEL_NOT_FOUND`.
- Automatically use extended timeouts (20s~60s) for 4B models.

## Simulation Plan (Once model is installed)
```powershell
python tools/probe_ollama_timeout_stabilization.py --model qwen3:4b --output-dir artifacts/ollama_qwen3_4b_probe
```

## Target Metrics
- JSON Parse Success: 100%
- StoryIntentPatch Contract Validation: 100%
- Acceptable Latency: < 45s for CASE 3
