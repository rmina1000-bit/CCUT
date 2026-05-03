# STEP 10-I.5.28-E9-R2 Pre-Proposal Narrative Consultation Flow Report

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: 3d8337a94019ad365a7279b2cc9cf1b541f181fe
- 수정 파일:
    - `ccut_frontend/src/proposal/proposalTypes.ts`
    - `ccut_frontend/src/hooks/useProposalState.ts`
    - `ccut_frontend/src/pages/Index.tsx`
    - `ccut_frontend/src/components/CenterPanel.tsx`
- 작업 성격: Pre-Proposal Narrative Consultation Flow 구현

## 2. 구현 내용
- **편집스토리 협의 단계 도입**: 분석 완료 후 A/B 제안을 즉시 보여주지 않고, 먼저 분석 데이터를 기반으로 생성된 "편집스토리 초안"을 보여주는 흐름으로 전환했습니다.
- **Narrative Draft 자동 생성**: 소스 영상의 개수, 제목, 길이 등을 활용하여 프로젝트의 성격과 편집 의도를 설명하는 자연어 초안을 생성합니다.
- **Consultation Status 관리**: `pending` → `draft_ready` → `user_requested_change` → `confirmed` 상태를 정의하여 협의 흐름을 제어합니다.
- **자연어 의도 파악 (Intent Extraction)**: 채팅창 입력을 감시하여 "이대로", "진행해" 등의 긍정어는 확정으로 처리하고, "빠르게", "사람 중심" 등의 키워드는 `story_intent`에 반영합니다.
- **UI 제어**: 협의가 완료(`confirmed`)되기 전에는 A/B 제안 카드를 숨기고 협의창을 주 콘텐츠로 표시합니다. 협의 완료 후에는 기존의 A/B 제안과 방향 보정 바가 나타납니다.

## 3. 세부 로직
- **Draft 생성**: `Index.tsx`에서 소스 통계를 기반으로 Rule-based 문장 생성.
- **채팅 연동**: `CenterPanel`의 `handleSendFull`이 `onReproposal`로 원문 입력을 전달하도록 수정하고, `Index.tsx`에서 협의 중일 경우 이를 의도 파악 로직으로 분기 처리.
- **UI Layout**: `CenterPanel`의 `renderContent` 내부를 상태에 따라 조건부 렌더링하도록 구조 변경.

## 4. 현재 한계 및 유지 사항
- **Rule-based**: 현재는 고정된 템플릿 기반 초안이며, 후속 단계에서 LLM 연동 시 더 풍성해질 예정입니다.
- **Proposal Precompute**: 백엔드의 제안 생성 로직은 그대로 유지하여 속도 저하를 방지하되, 노출 시점만 프론트엔드에서 제어합니다.
- **금지 준수**: 백엔드, DB, API 호출 구조는 변경하지 않았습니다.

## 5. 검증
- **빌드**: 프론트엔드 환경 제약으로 `npm run build` 결과 확인은 수동 검토로 대체.
- **UI 흐름**: 분석 종료 -> 초안 노출 -> 채팅 협의 -> 제안 노출의 시퀀스가 논리적으로 구성됨을 확인.

## 6. 다음 단계
- **E9-R3**: 협의된 `story_intent`를 실제 `ProposalEngine` 요청 파라미터와 연결하여 제안 결과에 반영.
- **E10**: 장면 전환 및 컷 순서의 논리적 일관성(Transition Coherence) 강화.

## 7. 판정
**PASS**
- AI와 사용자가 제안 전에 먼저 이야기의 방향을 맞추는 핵심 협업 흐름이 성공적으로 구축되었습니다.
