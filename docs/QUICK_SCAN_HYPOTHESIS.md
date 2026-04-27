# QUICK SCAN + HYPOTHESIS v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 목적
사용자가 분석 완료를 기다리지 않고 영상 성격과 편집 방향을 빠르게 확인하도록 한다.

## 실행 조건
- Evidence 10% 이상 또는 대표 keyframe 3개 이상 확보

## 출력
- 대표 이미지 3~7개
- 짧은 요약
- Hypothesis: 영상 성격, 핵심 요소, 추천 편집 방향

## 사용자 질문
- 이 영상의 핵심이 맞습니까?
- 꼭 살릴 장면은 무엇입니까?
- 삭제할 장면은 무엇입니까?
- 톤은 감성형/정보형/쇼츠형 중 무엇입니까?

## 응답 방식
- 맞다
- 수정
- 아니다

## 미응답 처리
사용자가 응답하지 않아도 default hypothesis 기반으로 백그라운드 Semantic Fragment 생성을 계속한다.
응답이 나중에 들어오면 re-score 또는 Proposal 재생성에 반영한다.

## Proposal 전 설명
Proposal 생성 전 AI는 짧게 설명한다.
```text
이 영상은 {영상 성격}이며, {근거} 때문에 {편집 방향}이 적합합니다.
이 방향으로 A/B 제안을 생성하겠습니다.
```
