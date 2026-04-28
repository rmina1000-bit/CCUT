# CCUT 1.0.4 PROJECT NAVIGATION v3.2.1

> **현재 기준 SHA:** `ddbd6e2779e51bf9e45b9d832830ee14b3716340`  
> **Branch:** `ccut-1.0.4-step9`  
> **완료 단계:** STEP 0 ~ STEP 9 모두 PASS  
> **핵심 흐름:** 영상 → Quick Scan → Semantic Fragment → Proposal(JSON) → ExportInput → Render → UI mp4 표시  
> **절대 원칙:** Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

CCUT 1.0.4 장기 구조 보강축:
1. Common Core v1
2. Virtual Fragment Factory
3. Web AI Contract v0.1
4. External Proposal Service

이 4개는 STEP 10 이후 구조 보강 후보이며,
STEP 0~9 PASS 파이프라인을 깨지 않는다.



## 0. 프로젝트 정의
CCUT 1.0.4는 **영상 데이터를 의미 데이터로 변환하는 로컬 AI 시스템**이다. 기존 Fragment-first 구조를 Evidence/Semantic-first 구조로 전환한다.

```text
기존: 영상 → 조각 → 편집
목표: 영상 → Evidence Board → Semantic Fragment → Proposal → ExportInput → Render
```

## 1. 최상위 원칙
- 사용자가 최종 결정한다.
- AI는 편집하지 않고 의미를 만든 뒤 제안만 한다.
- CPU/GPU/RAM/Disk를 적극 사용하되 Resource Governor로 통제한다.
- 모든 산출물은 재사용 가능한 데이터로 저장한다.
- 사용자 응답 대기로 전체 분석을 멈추지 않는다.
- Partial Evidence / Fragment / Proposal을 즉시 표시한다.

## 2. 전체 흐름
1. 영상 입력
2. 분석용 Proxy 생성
3. Segment Partitioning
4. Worker 병렬 분석
5. Evidence Board 생성
6. Quick Scan + Hypothesis 생성
7. User Intent 선반영
8. Semantic Fragment 생성
9. User Intent 최종 재반영 및 re-score
10. Proposal 전 방향 설명
11. A/B Proposal 생성(JSON)
12. Partial/Final 결과 표시
13. Preview 시 영상 로딩
14. ExportInput 생성
15. 원본 기반 최종 Export 1회
16. Archive 저장
17. SNS 업로드
18. 주간/월간 보고서 생성

## 3. 절대 금지
- 코드 먼저 작성 금지
- UI 선행 금지
- 기존 코드 삭제 금지: 1차는 격리만 허용
- Evidence 없이 Semantic 생성 금지
- Semantic 없이 Proposal 생성 금지
- Proposal 없이 Export 직접 연결 금지
- Resource Governor 우회 실행 금지
- 병렬 Worker의 Evidence Board 직접 동시 DB 쓰기 금지
- 원본 영상 반복 분석 금지

## 4. 영상 사용 원칙
분석 단계에서는 최소한의 영상 접근을 허용한다. 가능하면 Proxy/Keyframe 기준으로 대체한다.
편집/Proposal 단계에서는 영상 없이 JSON 데이터만 사용한다.
Preview/Export 단계에서는 영상 로딩과 원본 기반 렌더를 허용한다.

## 5. Worker / Resource 원칙
- 모든 Worker는 segment 단위로 독립 수행한다.
- 모든 Worker 결과는 timestamp 기준으로 Evidence Board에 병합한다.
- Worker 실패는 전체 중단 사유가 아니다.
- 모든 산출물은 confidence와 fallback_reason을 가진다.
- Resource Governor가 worker 수, batch size, cache size, queue throttle을 조절한다.

## 6. 최종 목표
- Quick Scan: 10초 내 표시
- Partial Proposal: 15초 내 시작
- 전체 Proposal: 짧은 영상 20초 / 긴 영상 60초 목표
- 재편집: 5초 이하
