# VL Factory Stage Policy

## Objective
To utilize the high-quality visual reasoning of `Qwen3-VL` without sacrificing the "Fast Path" speed of CCUT.

## Selection Criteria (Input)
`Qwen3-VL` MUST only process a selective subset of the video:
1. **Proposal Candidates**: Fragments that have been selected for the current A/B proposal set.
2. **High-Value Fragments**: Top 10% of fragments based on initial `edit_value`.
3. **Low Confidence Nodes**: Fragments where semantic detection (ASR/Motion) is ambiguous.
4. **Representative Keyframes**: One frame per logical scene (Stage 2 output).
5. **User Focus**: Fragments related to specific user instructions (e.g., "find scenes with people").

## Output Schema (Visual Evidence v0)
The worker outputs a grounded evidence object:
```json
{
  "fragment_id": "string",
  "source_id": "string",
  "keyframe_path": "string",
  "source_channel": "thinking_trace",
  "evidence_grade": "trace_visual_candidate",
  "visual_summary": "string",
  "scene_type": "string",
  "semantic_tags": ["string"],
  "visible_people_count": 0,
  "human_presence_score": 0.0,
  "edit_value": 0.0,
  "cognitive_role_hint": "context",
  "diag": { ... }
}
```

## Performance Guardrails
- **Max Batch Size**: 5 concurrent/sequential images.
- **Image Pre-processing**: Forced resize to 384px.
- **Failure Tolerance**: If VL fails, the system falls back to Stage 3 (Semantic) metadata.
