# NARRATIVE PROVIDER ADAPTER DRY RUN

## Overview
This document records the Dry Run results of the `NarrativeProviderAdapter`, which interfaces between the CCUT backend and the `qwen3:4b` local LLM. The goal is to verify that the adapter correctly transforms natural language user intent into a structured `StoryIntentPatch` while maintaining the production contract (Response-only JSON).

## Adapter Specification
- **Implementation**: `ccut_backend/ai/boundary/narrative_provider_adapter.py`
- **Model**: `qwen3:4b`
- **Configuration**:
  - `think: false` (Force skip thinking process)
  - `format`: JSON Schema (StoryIntentPatch)
  - `temperature: 0`
  - `num_predict: 256`

## Dry Run Results
Results are stored in `artifacts/narrative_provider_adapter_dryrun/`.

### Test Cases
1. "더 빠르게, 사람 중심으로 편집해줘"
2. "모든 영상에서 한 조각씩은 반드시 써줘"
3. "감성적으로, 가족기록처럼 보이게 해줘"
4. "너무 길면 안 되고 쇼츠처럼 빠르게 해줘"
5. "말이 없는 장면은 줄이고 표정이 잘 보이는 장면을 살려줘"

## Verification Logic
- **Production OK**: Valid JSON found in the `response` field.
- **Thinking Only**: JSON found only in the `thinking` field (Rejected).
- **Safe Failure**: Returns status like `JSON_PARSE_FAILED` or `MODEL_CALL_TIMEOUT` instead of crashing.

## Usage
```powershell
python tools/dryrun_narrative_provider_adapter.py
```
