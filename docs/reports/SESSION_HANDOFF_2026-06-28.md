# CCUT 세션 인수인계 — 2026-06-28 (god-file 리팩토링)

베이스라인: `6d59435` = tag `backup-2026-06-28` (origin 반영, 롤백점).
작업 성격: REFACTOR — 기능 변경 0, 구조 해체. 분업: 편집=Cowork host Edit / tsc·build·git=국장 머신 raw.

## 이번 세션 커밋 (3건, frontend only)
1. `270d8b6` refactor(frontend): extract app navigation flow
   - 신규 `ccut_frontend/src/hooks/useAppNavigation.ts`
   - `Index.tsx`: onHome·resetAnalysisState·onItemClick·onToggleCollapse·onRenameProject·onDeleteProject·onNewProject → hook 이동(verbatim)
2. `3970567` refactor(frontend): dedup ui snapshot builder, reduce nav hook params
   - `Index.tsx`: `buildUiSnapshot` 단일 빌더 추가, uiSnap 정의 3→1
   - hook param 18→11 (실제 decoupling)
3. `cef2e93` refactor(frontend): split center panel passive views
   - 신규 `views/EmptyProjectView.tsx`(props 3)·`views/AnalysisLoadingView.tsx`(props 3)
   - `CenterPanel.tsx`: empty/loading 분기 JSX → 컴포넌트 치환, Upload import 제거

## 검증 (머신 raw)
- 각 STEP: `tsc --noEmit` 에러 0, diff 예상 파일만.
- 전체 회귀: tsc 0 / `vite build` ✓ built / py_compile main.py PYC_OK / 누적 diff 6d59435→cef2e93 = 정확히 5파일.
- PRODUCT(국장 실화면): F5 첫화면·프로젝트클릭/전환·홈버튼·Proposal A/B·Export·휴지통 = PASS.

## 다음 작업 1순위
- **휴지통 라이브갱신 갭(범위 밖·회귀 아님)**: 좌측 프로젝트 삭제→휴지통 즉시 반영 안 됨 / 휴지통 복원→프로젝트 메뉴 즉시 반영 안 됨. 새로고침하면 정상(데이터 OK, 컴포넌트 간 라이브 동기화만 미구현). TrashPanel/TrashPortal 미구현 영역 — 이번 리팩토링 무관(diff 5파일에 미포함). 별도 수정안→승인→적용 예정.
