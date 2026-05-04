# STEP 10-J Qwen3-VL Visual Evidence Worker

## Strategy Overview
CCUT 1.0.4 utilizes **Visual Evidence-driven** grounding for its cognitive editing engine. 

- **Qwen3-VL (Local/Edge)**: Functions as the core **Visual Evidence Worker**. It is deployed as a **non-blocking Deep Worker** in Stage 5 of the analysis factory. Due to current model configurations, it operates primarily via **Thinking Trace-based Visual Evidence Extraction** (see `docs/QWEN_VL_TRACE_EVIDENCE_POLICY.md`).
- **Grounding Pillar**: Visual evidence is a mandatory pillar for both free and paid editing modes, providing semantic tags, emotion detection, and scene categorization.

## Operational Constraints
To maintain performance and resource efficiency:
1. **No Indiscriminate Analysis**: The system MUST NOT analyze the entire raw video stream.
2. **Keyframe-Centric**: Analysis is restricted to specific keyframes, thumbnails, or candidate fragments identified by the temporal engine.
3. **Trace Extraction**: The worker extracts structured metadata from the model's internal reasoning traces.

## Visual Evidence Schema
- `visual_summary`: Descriptive summary of the frame.
- `scene_type`: Categorization (e.g., family, travel, talking head, restaurant).
- `visible_people_count`: Number of distinct people identified.
- `cognitive_role_hint`: Hint for fragment utility (hook, context, payoff, filler, broll).
- `edit_value`: Quality/utility score (0.0 - 1.0).

## Experimental PASS (R4)
The trace-based extraction has been validated with a 100% success rate on representative CCUT thumbnails (Avg 26s per frame at 384px).

## Integration
These results feed directly into the `Evidence Board`, allowing the `Proposal Engine` to generate A/B versions based on actual visual content.
