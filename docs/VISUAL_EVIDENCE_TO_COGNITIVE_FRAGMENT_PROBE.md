# Visual Evidence to Cognitive Fragment Probe

## Overview
This probe validates the transition from **Visual Evidence** (raw visual signals extracted from VL thinking traces) to **Cognitive Fragments** (structured editorial building blocks for CCUT).

## Pipeline
1. **Visual Signal Capture**: `qwen3-vl:4b` identifies objects and actions in its `thinking` trace.
2. **Evidence Extraction**: `tools/extract_visual_evidence_from_vl_thinking.py` parses the trace into a structured `Visual Evidence` JSON.
3. **Cognitive Mapping (Current Step)**: `tools/probe_visual_evidence_to_cognitive_fragment.py` maps the visual metadata to the `Cognitive Fragment` schema, assigning editorial roles and values.

## Mapping Logic
- **`fragment_id`**: Derived from the source image filename.
- **`semantic_tags`**: Cumulative list of main subjects, scene type, and action level.
- **`edit_role`**: Maps `cognitive_role_hint` (context, hook, etc.) to the fragment's structural role.
- **`edit_value`**: Direct mapping of the visual utility score.
- **`must_keep_reason`**: Generated based on high human presence or critical visual signals.

## Cognitive Fragment Schema
The output matches the internal CCUT fragment contract, allowing it to be consumed by the `Proposal Engine` for A/B testing or EDL generation.

## Results
- Results are saved in `artifacts/qwen_vl_cognitive_fragment_probe/`.
- `evidence_grade` is set to `diagnostic_visual` to indicate that this fragment is grounded in visual analysis rather than just ASR or text metadata.
