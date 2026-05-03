# USER INTENT v3.3.0

> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.3.0  

# StoryIntent

StoryIntent is the structured editing intention extracted from the user's narrative consultation.

It is created after:
- analysis
- narrative draft
- user natural-language feedback

It should be created before:
- A/B proposal generation
- final proposal selection
- export

## StoryIntent v0 Fields

```json
{
  "pace": "slow | medium | fast",
  "mood": "calm | warm | emotional | dynamic",
  "focus": "people | landscape | balanced | memory",
  "coverage": "quality_first | balanced_sources | user_priority",
  "avoid": ["shaky", "dark", "long_landscape", "repetition"],
  "emphasize": ["people", "child", "family", "emotion", "place"],
  "notes": ""
}
```

## Natural Language Mapping Examples

“더 빠르게”
→ pace: fast

“사람 중심으로”
→ focus: people

“풍경 줄여”
→ avoid: ["long_landscape"]

“여러 영상 골고루”
→ coverage: balanced_sources

“감성적으로”
→ mood: emotional

“아이 장면 살려”
→ emphasize: ["child", "people"]

## User Override

If the user explicitly asks to include a source or fragment, the system should treat that as stronger than automatic exclusion, while still warning about quality risks.

---

## Legacy User Intent Structure (Reference)
```json
{
  "source_id": "SRC_001",
  "must_keep": ["바닷가", "웃는 장면"],
  "avoid": ["흔들린 장면"],
  "tone": "감성형",
  "target_length": 60
}
```
