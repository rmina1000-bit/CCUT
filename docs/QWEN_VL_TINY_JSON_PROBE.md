# Qwen3-VL Tiny JSON Probe

## Purpose
After confirming that `qwen3-vl:4b` identifies visual signals in its `thinking` trace but fails to output a full schema in the `response` field, we test if a **minimal JSON schema** (Tiny JSON) can be successfully generated in the standard response channel.

## Strategy
1. **Reduce Payload Complexity**: Use a schema with only 3 fields (`visual_summary`, `scene_type`, `has_person`).
2. **Control Tokens**: Test `num_predict` at 128 and 256 to find the threshold where the model switches from reasoning to output.
3. **Prompt Hardening**: Use `/no_think` to discourage excessive reasoning and encourage immediate JSON output.

## Tiny JSON Schema
```json
{
  "visual_summary": "string",
  "scene_type": "string",
  "has_person": "boolean"
}
```

## Success Criteria
- **PASS**: The `response` field contains a valid, parseable JSON object matching the tiny schema.
- **PARTIAL**: The `response` is empty but the `thinking` field contains the visual description or the JSON.
- **FAIL**: Timeout or no visual evidence found in any field.

## Execution
```powershell
python tools/probe_qwen_vl_tiny_json.py --timeout-sec 120 --resize-max 512 --num-predict 256
```
