# SEMANTIC FRAGMENT v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 정의
Semantic Fragment는 영상 파일 조각이 아니라 Evidence 기반 의미 단위다.

## 생성 조건
- Evidence 30% 이상 완료
- transcript 최소 10% 확보
- Quick Intent Seed 존재 또는 default intent 존재

## 3계층 구조
```json
{
  "fragment_id": "SF_001",
  "source_id": "SRC_001",
  "start": 10.0,
  "end": 18.5,
  "semantic": {
    "summary": "여행 시작 소개",
    "topic": "intro",
    "transcript_refs": ["tr_001"],
    "evidence_refs": ["seg_010", "seg_011"]
  },
  "structural": {
    "role": "hook",
    "edit_value": 0.82,
    "duration": 8.5
  },
  "continuity": {
    "topic_similarity": 0.77,
    "time_proximity": 0.95,
    "sentiment_continuity": 0.68,
    "narrative_flow": 0.72
  },
  "confidence": 0.87,
  "fallback_reason": null
}
```

## Role
- hook
- context
- payoff
- filler
- broll
- closing

## Merge/Split
- 2초 미만: merge 후보
- 60초 초과: split 후보
- merge/split 후에도 evidence_refs 유지

## Intent 반영
- P3-pre intent seed는 edit_value 초기값에 반영
- P3-post intent는 proposal 전 re-score에 반영

## PASS
- 모든 fragment가 evidence_refs 보유
- role 3종 이상 분산
- confidence/fallback_reason 존재
- 영상 파일 생성 없음
