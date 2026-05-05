# Deep Visual Analysis Stage

## Purpose
The **Deep Visual Analysis Stage** (Stage 5) is the factory layer where `Qwen3-VL` performs intensive, multi-modal analysis on selective video fragments. 

## Integration Principle: Non-Blocking Refinement
- **Fast Path Isolation**: Initial A/B proposals (Stage 4) must NOT wait for Stage 5. The system remains responsive and fast.
- **Cognitive Refinement**: Stage 5 results are used to upgrade existing `Semantic Fragments` into `Cognitive Fragments` with grounded visual evidence.
- **Usage**: Refined fragments improve future reproposals, editorial reports, and final decision grounding.

## Pipeline Architecture
- **Stage 0**: Upload / Source Registration
- **Stage 1**: Proxy / Thumbnail / Basic Signal Extraction
- **Stage 2**: Scene / Audio / Motion / Text Evidence Board
- **Stage 3**: Quick Scan / Hypothesis / Initial Semantic Fragment
- **Stage 4**: **Fast A/B Proposal** (Immediate UX)
- **Stage 5**: **Deep Visual Analysis (Qwen3-VL)** (Late-stage Background Worker)
- **Stage 6**: Cognitive Fragment Refinement
- **Stage 7**: Reproposal / Report / Archive / Final Decision Support

## Worker Policy
- **Target Selection**: Only analyze high-value candidates (Proposal members, high edit_value, user-requested topics).
- **Graceful Failure**: Timeout or inference failure in Stage 5 must NOT trigger UI errors or block the export pipeline.
- **Evidence Grade**: `trace_visual_candidate` (v0).
- **Status**: **PASS (STEP 10-K)**. Layer defined and verified with batch probe.
