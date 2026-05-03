# StoryIntent Contract

## 1. Definition

StoryIntent is the structured representation of the user's editing intention after Narrative Consultation.

It is not raw chat text.  
It is the distilled editing direction used by ProposalEngine.

## 2. Contract v0

```json
{
  "pace": "slow | medium | fast",
  "mood": "calm | warm | emotional | dynamic",
  "focus": "people | landscape | balanced | memory",
  "coverage": "quality_first | balanced_sources | user_priority",
  "avoid": [],
  "emphasize": [],
  "notes": ""
}
```

## 3. Field Meaning

### pace

Controls editing rhythm.

### mood

Controls emotional tone.

### focus

Controls what kind of content should dominate.

### coverage

Controls source usage policy.

### avoid

Lists content types to reduce.

### emphasize

Lists content types to prioritize.

### notes

Keeps the user’s original natural-language instruction.

## 4. Mapping Rules

| User says | StoryIntent                 |
| --------- | --------------------------- |
| 더 빠르게     | pace = fast                 |
| 천천히       | pace = slow                 |
| 사람 중심     | focus = people              |
| 풍경 중심     | focus = landscape           |
| 여러 영상 골고루 | coverage = balanced_sources |
| 좋은 장면만    | coverage = quality_first    |
| 감성적으로     | mood = emotional            |
| 따뜻하게      | mood = warm                 |
| 흔들림 빼     | avoid += shaky              |
| 어두운 장면 빼  | avoid += dark               |
| 아이 장면 살려  | emphasize += child          |
| 가족 중심     | emphasize += family         |

## 5. Priority

User explicit instruction has priority over automatic assumptions.

However, if the user asks to include risky footage, CCUT should warn but not block.
