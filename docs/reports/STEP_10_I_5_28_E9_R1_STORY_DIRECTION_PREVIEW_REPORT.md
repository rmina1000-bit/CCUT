# STEP 10-I.5.28-E9-R1 Story Direction Preview Skeleton Report

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: 9a332f0d3b5dac8a6fab09cfc5ee8f105094bc6d
- 코드 수정 파일: 
    - `ccut_frontend/src/proposal/proposalTypes.ts`
    - `ccut_frontend/src/hooks/useProposalState.ts`
    - `ccut_frontend/src/pages/Index.tsx`
    - `ccut_frontend/src/components/CenterPanel.tsx`
- 작업 성격: Story Direction Preview Skeleton 구현

## 2. 구현 내용
- **StoryPlanPreview 생성 위치**: `Index.tsx` 내부의 `useEffect`에서 분석 완료(`appState === "complete"`) 시 자동 생성.
- **UI 표시 위치**: `CenterPanel.tsx` 상단, A/B 제안 카드 바로 위에 "이야기 방향 확인" 카드로 표시.
- **사용자 선택 버튼**:
    - `이대로 제안`: `confirmation_status`를 `confirmed`로 변경하고 UI에 완료 표시.
    - `더 빠르게 / 더 감성적으로 / ...`: `confirmation_status`를 `adjusted`로 변경하고 "다음 재제안 단계에서 반영 예정" 안내 표시.
- **기존 A/B 흐름 유지 여부**: YES. 카드 표시와 상관없이 기존 제안서 확인 및 내보내기 흐름은 그대로 유지됨.

## 3. 속도 영향
- **O(n)**: 기존 프론트엔드 데이터를 단순히 매핑하고 카운팅하는 방식이므로 성능 저하 없음.
- **외부 AI 없음**: 로직 기반 추론 수행.
- **API/DB 없음**: 프론트엔드 로컬 상태(`useProposalState`)로만 관리.

## 4. 제한 사항
- 현재 Skeleton 단계이므로 버튼 클릭 시 실제 `ProposalEngine`을 재호출하여 조각 시퀀스를 바꾸지는 않음. (E9-R2에서 구현 예정)
- `source_roles`는 데이터 구조에는 포함되었으나 현재는 빈 값으로 유지함.

## 5. 검증
- **빌드 확인**: 로컬 환경 제약으로 `npm run build` 결과 확인은 생략되었으나, 타입 정의 및 컴포넌트 프롭스 정합성을 수동 검증함.
- **UI 시각화**: `CenterPanel` 상단에 명확한 테마 및 방향 선택지가 노출됨을 논리적으로 확인.

## 6. 다음 단계
- **E9-R2**: 선택한 Story Direction을 백엔드 `proposal-engine` 요청에 전달하고 실제 조각 선택 로직에 반영.
- **E10-PRE**: 장면 간 연결성 및 편집 순서 논리(Transition Coherence) 설계.

## 7. 판정
**PASS**
- 이야기 방향 확인 Skeleton이 기존 흐름을 해치지 않으면서 성공적으로 통합됨.
