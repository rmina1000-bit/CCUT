# R10-H-R2 Free Conversation Mode Probe

## Purpose
To evaluate the performance of `qwen3:4b` in a non-restricted conversational mode, where it can reply naturally while identifying editing intents and generating `StoryIntentPatch` objects when applicable.

## Schema
```json
{
  "reply": "Natural language response in Korean",
  "intent_type": "greeting | system_question | complaint | editing_instruction | editing_feedback | confirmation | unknown",
  "needs_story_patch": boolean,
  "story_patch": {
    "patch_type": "story_intent_patch",
    "tone": "string",
    "target_length": "string",
    "must_keep": ["string"],
    "avoid": ["string"],
    "reason": "string"
  },
  "requires_user_confirmation": boolean,
  "reason": "Classification rationale"
}
```

## Test Inputs
1. 안녕 (Greeting)
2. 너 누구야? (System Question)
3. 대화가 좀 이상한데? (Complaint)
4. 앞부분이 좀 늘어져 (Editing Feedback)
5. 애가 웃는 장면 살리고 싶어 (Editing Instruction)
6. 이 영상은 기록용이야 (Context / Instruction)
7. 모든 영상에서 하나씩은 꼭 넣어줘 (Instruction)
8. 아니 그건 아니고 좀 더 감성적으로 (Correction / Feedback)
9. 이대로 해 (Confirmation)
10. 그냥 알아서 잘 해봐 (Delegation / Instruction)

## Execution
Run the following command:
```powershell
python tools/free_conversation_probe.py
```

## Status
- Adapter: Method `get_free_conversation` implemented.
- Probe Tool: `tools/free_conversation_probe.py` created.
- Target Model: `qwen3:4b` (Ollama).
