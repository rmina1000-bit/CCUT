# USER INTENT v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 구조
```json
{
  "source_id": "SRC_001",
  "must_keep": ["바닷가", "웃는 장면"],
  "avoid": ["흔들린 장면"],
  "tone": "감성형",
  "target_length": 60,
  "priority_axis": {
    "visual": 1.4,
    "speech": 0.8,
    "emotion": 1.2
  }
}
```

## 적용 시점
### P3-pre
Quick Scan에서 받은 must_keep/avoid/tone/target_length를 Semantic Fragment 생성 전 score seed로 반영.

### P3-post
Fragment 50% 이상 생성 후 edit_value 재계산.
- must_keep: +0.2
- avoid: -0.3
- tone 일치: +0.1

## 충돌 처리
- 최신 지시 우선
- 명시적 지시 우선
- 원본 재료 한계 초과 요구는 fallback_reason에 기록

## PASS
- intent 적용 전/후 fragment score 변화
- proposal sequence 변화
- 사용자 미응답 시 default intent 사용
