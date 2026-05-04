# Qwen3-VL Thinking Evidence Extractor

## Motivation
Current observations show that `qwen3-vl:4b` provides extremely high-quality visual descriptions within its internal reasoning process (`thinking` field), but often fails to reach the final response due to token length limits or inference time constraints. 

Since CCUT requires **Visual Evidence** (structured data) rather than conversational chat, we can leverage these "thinking traces" as a primary diagnostic source for evidence extraction.

## Strategy: Thinking-as-Evidence
Instead of forcing a final conversational output, we:
1. Trigger the VL model and capture the `thinking` field.
2. Use a rule-based parser (`tools/extract_visual_evidence_from_vl_thinking.py`) to convert the descriptive text into structured `Visual Evidence` JSON.
3. Use these results to ground the `Cognitive Fragment` generation.

## Extraction Ladder
1. **Keyword Analysis**: Identification of objects (kimchi, bowl, elderly person).
2. **Scene Categorization**: Determining setting (restaurant, kitchen, outdoors).
3. **Attribute Mapping**: Assigning scores for human presence, action level, and edit value.
4. **Summary Generation**: Creating a concise Korean summary based on identified visual signals.

## Expected Schema
The extractor populates the standard CCUT Visual Evidence schema:
- `scene_type`: e.g., "restaurant"
- `visible_people_count`: e.g., 1
- `human_presence_score`: e.g., 0.85
- `cognitive_role_hint`: e.g., "context"

## Current Status
- Source: `artifacts/qwen_vl_smoke_ladder/smoke_ladder_summary.json`
- Extractor: `tools/extract_visual_evidence_from_vl_thinking.py`
- Results: `artifacts/qwen_vl_thinking_evidence/`
