# Qwen3-VL Smoke Ladder Probe

## Background
The initial full-schema Visual Evidence Probe failed with timeouts (120s+). To isolate whether the failure is due to model inference speed, JSON schema complexity, or image delivery issues, we use a "Smoke Ladder" approach.

## Troubleshooting Ladder
1. **Single Image + Free Text (Current Step)**: Can the model see the image and describe it in Korean without any JSON constraints?
2. **Single Image + Tiny JSON**: Can it output a very simple JSON like `{"seen": true}`?
3. **Single Image + Light Schema**: Partial fields from the Visual Evidence schema.
4. **Full Schema**: The complete contract.
5. **Batch Processing**: Multiple images in sequence.

## Hypothesis for Timeout
- **Schema Overload**: Qwen models sometimes struggle with complex JSON schemas in the first call after loading.
- **Inference Time**: 4B-VL might take more than 120s for a full structured analysis on certain hardware.
- **Image Size**: Passing large base64 strings might slow down the Ollama internal processing.

## Current Smoke Test Details
- **Command**: `python tools/smoke_qwen_vl_ladder.py --timeout-sec 120 --resize-max 512`
- **Goal**: Verify if `/api/chat` or `/api/generate` returns a natural language description of the thumbnail.

## Result Codes
- `OK`: Response received.
- `MODEL_CALL_TIMEOUT`: Reached 120s limit.
- `OLLAMA_NOT_RUNNING`: Connection refused.
- `MODEL_CALL_FAILED`: Generic error.
- `IMAGE_NOT_FOUND`: Sample thumbnail missing.
