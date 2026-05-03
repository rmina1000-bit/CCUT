# CCUT 1.0.4 PROJECT NAVIGATION v3.3.0

> **현재 기준 SHA:** `56554c70e76ad03537193d5b560fd19457ce2477`  
> **Branch:** `ccut-1.0.4-step9`  
> **완료 단계:** STEP 0 ~ STEP 9 모두 PASS  
> **핵심 흐름:** 영상 → 분석 → 편집스토리 초안 → 사용자 협의 → StoryIntent → A/B 제안 → Render  
> **절대 원칙:** 협의 없이 제안 금지 / StoryIntent 없이 Proposal 생성 금지 / Proposal 없이 Export 금지

## Narrative Consultation Layer

CCUT1.0.4는 분석 완료 후 A/B 제안을 즉시 노출하지 않는다.  
분석 결과는 먼저 편집스토리 초안으로 변환되고, 사용자는 이 초안을 보고 자연어로 의견을 제공한다.  
CCUT은 사용자의 자연어 의견을 StoryIntent로 정리한 뒤, 그 StoryIntent를 기준으로 A/B 편집 제안을 생성한다.

기존 흐름:
영상 → 분석 → A/B 제안

새 흐름:
영상 → 분석 → 편집스토리 초안 → 사용자 협의 → StoryIntent → A/B 제안

이 구조는 CCUT을 단순 자동편집툴이 아니라, 영상 데이터를 이해하고 편집 전 사용자와 이야기 방향을 합의하는 로컬 AI 편집 시스템으로 정의한다.

## Roadmap: STEP 10-I.5.28-E9 계열

- E9-PRE: Story Direction Confirmation 설계 (PASS)
- E9-R1: Story Direction Preview Skeleton (PASS)
- E9-R1-R1: Story Direction Card Placement Repair (PASS)
- E9-R2: Pre-Proposal Narrative Consultation Flow (PASS)
- E9-R2-R1/R2: Chat History / ChatGPT-like UX 시도 (HOLD/REWORK)
- E9-R2-R3 예정: ChatGPT Form Narrative Chat Repair
- E9-R3 예정: StoryIntent → Proposal Request 연결

> **주의:** E9-R2는 기능적으로 PASS이나, E9-R2-R1/R2의 채팅 UX는 최종 PASS가 아니다. 다음 작업은 ChatGPT식 익숙한 대화 폼으로 Narrative Consultation UI를 재정렬하는 것이다.

---

## 0. 프로젝트 정의
CCUT 1.0.4는 **영상 데이터를 의미/이야기 데이터로 해석하고, 편집 전 사용자와 대화해 방향을 합의한 뒤 편집 제안을 생성하는 로컬 AI 시스템**이다.

```text
기존: 영상 → 조각 → 편집
변경: 영상 → 분석 → 편집스토리 초안 → 사용자 협의 → StoryIntent → A/B 제안
```

## 1. 최상위 원칙
- 사용자가 최종 결정한다.
- AI는 편집하지 않고 의미를 만든 뒤 제안만 한다.
- **편집 전 사용자와의 이야기 방향 협의(Narrative Consultation)가 제안의 전제조건이다.**
- 모든 산출물은 재사용 가능한 데이터로 저장한다.

## 2. 전체 흐름
1. 영상 입력
2. 분석용 Proxy 생성
3. Segment Partitioning
4. Worker 병렬 분석
5. Evidence Board 생성
6. Quick Scan + Hypothesis 생성
7. **Narrative Consultation (New)**
   - 분석 데이터를 편집스토리 초안으로 변환
   - 사용자 자연어 의견 수집
   - StoryIntent 확정
8. **A/B Proposal 생성 (Guided by StoryIntent)**
9. Partial/Final 결과 표시
10. Preview 시 영상 로딩
11. ExportInput 생성
12. 원본 기반 최종 Export 1회
13. Archive 저장

## 3. 절대 금지
- 분석 직후 A/B 제안 즉시 노출 금지
- 사용자 협의 전 편집 제안 영상 노출 금지
- StoryIntent 없이 ProposalEngine에 사용자 의도를 강하게 반영했다고 주장 금지
- Narrative Consultation 이전 Export/Render 접근 금지
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
