# INCREMENTAL DISPLAY v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 목적
전체 분석 완료 전에도 신뢰 가능한 부분 결과를 표시한다.

## Partial Evidence
- 조건: Evidence 10% 이상
- status: partial
- progress 표시
- 5초마다 또는 10 segment마다 업데이트

## Partial Fragment
- 조건: Evidence 30% 이상
- confidence 0.5~0.7 낮게 표시
- Evidence 50/70/100% 시점 업데이트

## Partial Proposal
- 조건: Fragment 50% 이상
- note: final 재생성 예정 표시
- Fragment 100%에서 final proposal로 교체

## PASS
- partial/final 구분 가능
- final 교체 가능
- 사용자 대기감 감소
