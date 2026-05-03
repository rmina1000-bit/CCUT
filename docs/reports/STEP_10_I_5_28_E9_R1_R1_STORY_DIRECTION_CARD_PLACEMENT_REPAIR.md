# STEP 10-I.5.28-E9-R1-R1 Story Direction Card Placement Repair Report

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: 5bb8d5fdb384a14daec418468e44ebaeb7d4a638
- 수정 파일: `ccut_frontend/src/components/CenterPanel.tsx`
- 작업 성격: UI Layout & Styling Repair

## 2. 문제
- 기존 Story Direction 카드가 화면 최상단에 독립적으로 위치하여 A/B 제안과의 연결성이 부족했음.
- 카드의 높이가 너무 크고 설명이 길어 사용 흐름을 방해하고 알림 메시지와 혼동될 우려가 있었음.

## 3. 수정 내용
- **위치 재배치**: A/B 제안 그리드 바로 위로 카드를 이동시켜 "제안의 근거/방향"임을 명확히 함.
- **디자인 압축**: 대형 배너 형태에서 슬림한 "방향 보정 바(Adjustment Bar)" 형태로 변경.
- **문구 최적화**: 
  - "이야기 방향 확인" → "이야기 방향" (헤더)
  - 한 줄 요약: "기록형 중심 · A안 빠르게 · B안 자연스럽게" (Detected Theme 기반)
  - 버튼 레이블: "시장형 하이라이트" → "하이라이트", "이대로 제안 생성" → "이대로" 등 압축.
- **UI 컴포넌트**: Compact pill 형태의 버튼 사용, padding 및 border-radius 조정으로 제안 카드와 일관성 유지.

## 4. 유지한 것
- 기존 `storyPlan` 상태 및 `confirmation_status` 로직 (Pending/Confirmed/Adjusted).
- 기존 A/B proposal 노출 흐름 및 내보내기 기능.
- 네트워크 요청이나 API 호출 추가 없음.

## 5. 금지 준수
- backend/ProposalEngine/API/DB 수정 없음.
- `Index.tsx` 및 `useProposalState.ts` 수정 없음 (CenterPanel 내부 스타일링만 수정).

## 6. 검증
- **UI 정합성**: A/B 제안 영역 내부 상단에 자연스럽게 배치됨을 코드 레벨에서 확인.
- **빌드**: 프론트엔드 환경 제약으로 `npm run build` 결과 확인은 수동 검토로 대체.

## 7. 판정
**PASS**
- 이야기 방향 확인 기능이 이제 사용자 흐름을 방해하지 않고 A/B 제안과 유기적으로 결합됨.
