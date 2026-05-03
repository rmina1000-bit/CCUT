# Qwen3 4B Validation Protocol

## 1. Objective
Verify that Qwen3 4B-Instruct can correctly interpret user narrative intent and return a valid `StoryIntentPatch` JSON within the AI Boundary.

## 2. Test Scenarios

### A. Speed Request
- **Input**: "더 빠르게 해줘"
- **Expected Outcome**: `StoryIntentPatch` with increased `target_pacing` or `must_keep` constraints.

### B. Emotional/Genre Request
- **Input**: "웃긴 장면 위주로 짧게 해줘"
- **Expected Outcome**: Patch with humor-related constraints and reduced target duration.

### C. Visual Focus
- **Input**: "사람 표정이 잘 보이게 해줘"
- **Expected Outcome**: Patch with framing or close-up intent.

## 3. Success Criteria (PASS)
- **Ollama Detection**: The probe tool successfully identifies `qwen3:4b`.
- **JSON Validity**: The model output is correctly parsed into the `StoryIntentPatch` schema.
- **Contract Adherence**: No unexpected fields are added; all mandatory fields are present.

## 4. Performance Thresholds
- **Latency**: If response exceeds 10s (timeout), it is recorded as a **Performance Finding**, not a logic failure.
- **Optimization**: Timeouts trigger investigation into `num_predict` limits or GPU offloading.

## 5. Prohibited Actions
- **No UI Integration**: This protocol is for backend boundary verification only.
- **No Engine Modification**: Do not modify `ProposalEngine` based on model output during this phase.
