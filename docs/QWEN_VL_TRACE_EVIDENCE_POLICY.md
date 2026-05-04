# Qwen3-VL Trace Evidence Policy

## Policy Definition
Current testing of `qwen3-vl:4b` via Ollama reveals that the model is configured with a `qwen3-vl-thinking` renderer/parser. This causes the model to prioritize detailed visual reasoning in the `thinking` trace while leaving the `response` field empty.

**Official Stance (Step 10-J-R4) - PASS:**
CCUT adopts **Thinking Trace-based Visual Evidence Extraction** (v0) as the primary multi-modal bridge.

## Verification Result (2026-05-04)
- **Batch Test**: 5/5 images processed successfully.
- **Success Rate**: 100% (OK_TRACE_VISUAL).
- **Avg Latency**: ~26.1s (at resize_max=384, timeout=120).
- **Status**: **PASS (R4)**

## Key Principles
1. **Trace as Source**: The `thinking` field is the primary diagnostic signal for visual evidence.
2. **Extraction Ladder**:
   - Primary: JSON extraction from the thinking trace.
   - Fallback: Rule-based heuristic parsing of the trace text.
3. **Operational Parameters**:
   - `resize_max`: 384 (Recommended for stability and lower latency).
   - `timeout_sec`: 120 (Sufficient for complex scene analysis).
4. **Mandatory Principles**:
   - **Selective Analysis**: Never analyze entire videos; only keyframes/thumbnails.
   - **Cache Policy**: Always use `skip-existing` logic to prevent redundant expensive inference.
5. **Data Classification**:
   - `status`: `OK_TRACE_VISUAL`
   - `source_channel`: `thinking_trace`
   - `evidence_grade`: `trace_visual_candidate`
   - `production_usable`: `false` (Experimental grounding).

## Transition Plan
Once a non-thinking or instruction-tuned model (e.g., `qwen3-vl-instruct`) is available via Ollama that reliably populates the `response` field, CCUT will migrate back to response-based extraction.

## Tools
- **Worker**: `ccut_backend/ai/vision/qwen_vl_visual_worker.py`
- **Batch Validation**: `tools/probe_qwen_vl_trace_batch.py`
