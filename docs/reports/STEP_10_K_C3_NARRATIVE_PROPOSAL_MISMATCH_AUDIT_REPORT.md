# Audit Report: Narrative-to-Proposal Mismatch (STEP 10-K-C3)

## 1. 개요
센터 패널의 Narrative Consultation(채팅)을 통해 합의된 편집 방향(예: "여러 영상 골고루 배치")이 실제 생성되는 A/B 편집 제안(Proposal)의 시퀀스에 반영되지 않는 현상을 감사하였다.

---

## 2. 감사 질문 및 확인 결과

| 질문 | 확인 결과 | 상세 내용 |
| :--- | :---: | :--- |
| 1. 사용자의 채팅 입력이 StoryIntent로 저장되는가? | **PASS** | `useProposalState.ts`의 `handleConsultation`에서 `story_intent` 상태를 업데이트함. |
| 2. "골고루 배치" 등의 지시가 user_intent로 변환되는가? | **PASS** | `narrativeService` 또는 정규식 Fallback을 통해 `coverage: "balanced_sources"` 등으로 변환됨. |
| 3. 변환된 user_intent가 API 요청에 포함되는가? | **FAIL** | `Index.tsx`의 `/proposals/project` 호출 시 `user_intent` 파라미터가 누락됨. |
| 4. resolved_story_template은 올바르게 생성되는가? | **HOLD** | 백엔드는 구현되어 있으나, 프론트에서 intent를 보내지 않아 항상 `safe_default`로 폴백됨. |
| 5. ProposalEngine이 지시를 실제 반영하는가? | **PASS** | `proposal_engine.py`에 `balanced_sources` 제약 조건 로직은 존재함 (템플릿 일치 시 작동). |
| 6. 화면의 설명이 실제 sequence와 일치하는가? | **FAIL** | 설명은 고정 템플릿 기반이라 "균형 보정 적용(R1)" 등의 문구가 나오지만, 실제 시퀀스는 보정 전일 수 있음. |
| 7. 설명만 바뀌고 sequence는 안 바뀌는 경로가 있는가? | **YES** | 채팅 완료 후 Proposal을 재요청(Re-request)하는 트리거가 프론트에 부재함. |

---

## 3. 핵심 불일치 원인 (Root Causes)

### [원인 A] 프론트엔드 Intent 전달 누락 (Data Link Broken)
`ccut_frontend/src/pages/Index.tsx`의 제안 생성 로직(`handleStartAnalysis` 내부)에서 백엔드 API `/proposals/project`를 호출할 때, `story_intent` 객체를 `ProjectProposalRequest` 페이로드에 포함하지 않고 있습니다.
*   **현재:** `videoService.requestProjectProposals(projectId, sourceIds, 60.0)`
*   **기대:** `videoService.requestProjectProposals(projectId, sourceIds, 60.0, storyPlan.story_intent)`

### [원인 B] 채팅 확정 후 재제안 트리거 부재 (Trigger Missing)
사용자가 채팅을 통해 편집 방향을 확정(`consultation_status === "confirmed"`)해도, 프론트엔드에서 새로운 Intent가 반영된 Proposal을 백엔드에 다시 요청하는 로직이 없습니다. 사용자는 채팅 전(초기 분석 시) 생성된 "구형" 제안을 계속 보고 있게 됩니다.

### [원인 C] Reproposal 로직의 스텁(Stub) 상태
`useProposalState.ts`의 `handleReproposal`이 백엔드 모드일 때 실제 API를 호출하지 않고 경고 로그만 출력한 뒤 리턴합니다. 이로 인해 사용자 의도 변경이 백엔드 엔진까지 도달하지 못합니다.

---

## 4. 결함 위치 및 수정 제안

### 수정 필요 파일 목록
1.  `ccut_frontend/src/pages/Index.tsx`: 초기 제안 요청 시 `story_intent` 포함.
2.  `ccut_frontend/src/hooks/useProposalState.ts`: `handleConsultation` 완료(Confirm) 시점에 백엔드 재요청 트리거 추가.
3.  `ccut_frontend/src/services/videoService.ts`: `requestProjectProposals`가 `user_intent`를 인자로 받도록 수정.

### 다음 단계 제안 (STEP 10-K-C4)
*   **Linkage Fix:** 채팅 결과(`story_intent`)를 백엔드 제안 엔진과 연결.
*   **Auto-Regeneration:** 사용자가 "이대로 진행해줘" 또는 특정 방향 합의 시, 백엔드로부터 새로운 A/B 제안을 받아와 UI를 갱신.

---

## 5. 최종 판정

### **[RESULT] HOLD (MISMATCH CONFIRMED)**
*   **사유:** 프론트엔드와 백엔드 간의 Intent 데이터 링크가 끊어져 있으며, 채팅 결과에 따른 제안 갱신 메커니즘이 구현되지 않음.
*   **코드 수정 필요성:** 높음 (프론트엔드 API 연동 보정 필요).
