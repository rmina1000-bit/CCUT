# CCUT 1.0.4 PROJECT NAVIGATION v3.4.0

> **현재 기준 SHA:** `d95be59` (2026-05-25)  
> **Branch:** `ccut-1.0.4-step9`  
> **완료 단계:** R10-C -> AI Transition Room (Qwen3-VL, Story Resolver) PASS  
> **핵심 흐름:** 영상 → 분석 → 편집스토리 초안 → 사용자 협의 → StoryIntent → Template/Technique Resolver → A/B 제안 → Render  
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

## Roadmap: STEP 10-I.5.28-E9 & R10 계열

- E9-R2: Pre-Proposal Narrative Consultation Flow (PASS)
- R5A: AI Boundary Unification & Skeleton (PASS)
- R5B: AI Staff Strategy & Model Policy (PASS)
- R6: Mock Narrative LLM Adapter Contract (PASS)
- R7: Swappable Narrative LLM Provider Architecture (PASS)
- R8: Target Hardware Profile & Compatibility Probe (PASS)
- R9: Ollama Local Narrative Provider Probe (PASS)
- R10-A: Qwen Model Inventory & Path Hygiene Review (PASS)
- R10-B: Qwen3-Instruct Acquisition & Ollama Registration Plan (PASS)
- R10-C: Qwen3 4B Ollama Candidate Install Plan (PASS)
- R10-D: Ollama Timeout / keep_alive / JSON Response Stabilization (PASS)
- STEP 10-J-R4: Qwen3-VL Trace Evidence Batch Validation (PASS)
- STEP 10-K: Deep Visual Analysis Stage 정의 (PASS)
- STEP 10-K-B1: Story Direction Template Registry (PASS)
- STEP 10-K-B2: Story Intent -> Template -> Technique Resolver Bridge (PASS)
- **2026-05-10: Proposal Preview Render 전환 (PRODUCT PASS)**
  - currentTime seek 방식 폐기
  - `proposal_preview_engine.py` 신규
  - A/B preview mp4 backend 생성 → frontend 재생
  - 상세: `docs/PROPOSAL_PREVIEW_RENDER_POLICY.md`
- **2026-05-25: Guard 모듈화 & 편집 파이프라인 정밀 진단 (DONE)**
  - `proposal_guards.py` 신설, 가드 완화 (30f→15f, 0.4→0.55)
  - 시뮬레이터 검증: 시간역행 가드 80% 누수 발견 및 pre-sort 보정
  - 상세: `docs/SESSION_HANDOFF.md`
- **2026-05-26: 외부 영상 생성 AI API 로드맵 수립 (계획)**
  - Runway Gen-4.5 / Kling 3.0 기반 B-roll 자동 생성
  - Video-Use 철학 적용: 메타데이터만 외부 전송, 렌더링은 로컬
  - 상세: `docs/EXTERNAL_AI_VIDEO_API_ROADMAP.md`
- STEP 10-K-B3 예정: Balanced Sources Proposal Constraint
- **NEXT: 소스 편향 근원 분석 + 외부 AI API Adapter 설계**

> **주의:** AI는 CCUT Core가 아니라 AI Staff / Boundary Provider로 정의한다. CCUT Core는 StoryIntentPatch 계약을 통해서만 AI의 조언을 수용하며, 최종 제안 생성 로직(ProposalEngine)은 Core가 직접 소유한다.

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
   - 사용자 자연어 의견 수집 (AI Staff/Core Companion 조언 활용)
   - StoryIntent 확정 (StoryIntentPatch 적용)
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
- **AI를 CCUT Core에 Hard-link 금지 (Boundary 필수)**
- 특정 모델(Qwen 등)에 Core 로직 종속 금지
- 사용자 승인 없는 모델 자동 다운로드 금지
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
