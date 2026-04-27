# PROPOSAL ENGINE v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 정의
Proposal은 영상이 아니라 Semantic Fragment ID 조합(JSON)이다.

## 생성 조건
- Semantic Fragment 50% 이상 생성
- User Intent 존재 또는 default intent 존재
- Fragment re-score 완료

## 구조
```json
{
  "proposal_id": "A",
  "mode": "market",
  "sequence": ["SF_001", "SF_004", "SF_009"],
  "order": [1, 2, 3],
  "total_duration": 52.3,
  "proposal_reason": "초반 hook과 payoff를 강조",
  "confidence": 0.81,
  "fallback_reason": null,
  "partial": false
}
```

## A/B
- A: Market Mode, hook/engagement 우선
- B: User Mode, must_keep/촬영 의도 우선

## 금지
- frontend heuristic 생성 금지
- 영상 로딩 금지
- Semantic 없이 생성 금지

## Incremental Proposal
- Fragment 50%: partial proposal
- Fragment 100%: final proposal로 교체

## PASS
- backend에서 semantic 기반 생성
- A/B 차이 존재
- proposal_reason/confidence 존재
