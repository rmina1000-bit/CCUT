# INSTRUCTION_R8.md
# CCUT 1.0.4 — R8 긴급 수정 지시서
# 브라우저 검증 결과 기반
# 2026-05-07 | branch: ccut-1.0.4-step9 | 직전 커밋: b2374a4 (R7)
# [ARCHIVED 2026-05-10] 현재 SESSION_HANDOFF.md로 상태 이전됨

---

## 0. 검증 원칙 (항상 적용)

CCUT 검증 6단계:
  1. DESIGN PASS    → 문서·설계 완료
  2. SIMULATION PASS → 더미·시뮬레이션 확인
  3. CODE PASS      → 빌드·컴파일 성공
  4. RUNTIME PASS   → 실제 호출 경로 확인
  5. BROWSER PASS   → 브라우저 화면·네트워크 확인
  6. PRODUCT PASS   → 사용자 의도 충족 확인

금지: "완료됐습니다 / PASS됐습니다 / 구현했습니다" 단독 사용 금지.
      반드시 어느 단계 PASS인지 명시.

최종 PASS 조건 (8개 모두):
  git clean + SHA 보고 + push + 브라우저 화면 캡처 + 콘솔 에러 없음
  + 네트워크 200 확인 + 국장님 수동 확인 + 사용자 확인

---

## 1. 브라우저 검증 결과 (2026-05-07, 14영상 업로드)

검증 기준 커밋: 60e5f1b (R6)
R7(b2374a4)은 커밋 완료, 브라우저 미검증 상태.

| 우선순위 | 이슈 | 원인 추정 | 판정 |
|---------|------|---------|------|
| P0 | SF 썸네일 전멸 (모든 SF_* 404) | SF thumb URL이 8080 프록시(/api/static/)인데 파일은 8000에만 존재 또는 프록시 미설정 | BROWSER FAIL |
| P0 | NarrativeAI TIMEOUT 15001ms → 저질 fallback | LLM 호출 시 fragment 수 무제한 전달로 인한 병목 추정 | BROWSER FAIL |
| P1 | 채팅창 2개 중복 표시 | CenterPanel.tsx:1586 confirmed 조건 제거 후 legacy bar + new bar 동시 노출 | BROWSER FAIL |
| P1 | Source diversity 편중 — 14개 영상 중 대부분 '제안 사용 조각: 0개' | R6 max_share 로직이 일부에서만 작동 | PRODUCT FAIL |
| P2 | 누적 재생 버그 미수정 | CenterPanel.tsx:1043 endSec가 시퀀스 모드 외 미적용 | BROWSER FAIL |
| P2 | 대화→실행 미연결 (버튼 수동 클릭 필요) | handleConsultation이 setStoryPlan만 실행, onReproposal() 미호출 | PRODUCT FAIL |

종합 판정: PRODUCT FAIL — R8 완료 전 다음 스텝 진행 불가.

---

## 2. 작업 순서

P0를 먼저 해결하지 않으면 나머지 브라우저 검증 불가. 순서 준수 필수.

  1. 2-1 SF 썸네일 404 (P0) ← 가장 먼저
  2. 2-2 NarrativeAI TIMEOUT (P0) ← 2-1과 병행 가능
  3. 2-3 채팅창 중복 (P1)
  4. 2-4 Source Diversity 편중 (P1)
  5. 2-5 누적 재생 버그 (P2)
  6. 2-6 대화→실행 연결 (P2) ← 시간 부족 시 R8b로 분리 가능

---

## 3. 작업 상세

### 2-1. [P0] SF 썸네일 404 해결 (→ 2026-05-10 SESSION_HANDOFF에서 해결 확인됨)

### 2-2. [P0] NarrativeAI TIMEOUT 해결 (→ useProposalState.ts timeout 30s 커밋 7028b75)

### 2-5. [P2] 누적 재생 버그 (→ 2026-05-10 Proposal Preview Render로 최종 해결)
  최종 해결: proposal_preview_engine.py / PROPOSAL_PREVIEW_RENDER_POLICY.md 참조

---

저장 위치 원본: D:\CCUT1.0.4\docs\INSTRUCTION_R8.md
아카이브: docs/reports/archive/INSTRUCTION_R8.md
