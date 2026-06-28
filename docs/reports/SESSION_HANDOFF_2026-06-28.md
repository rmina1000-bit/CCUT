# CCUT 세션 인수인계 — 2026-06-28 (god-file 리팩토링 + 휴지통 + 백엔드 router)

베이스라인: `6d59435` = tag `backup-2026-06-28` (롤백점). 세션 종료 시 **origin/ccut-1.0.4-step9 = `b103b30`**.
분업: 편집=Cowork host Edit / tsc·build·py_compile·git=국장 머신 raw (마운트 오염 회피).

## 이번 세션 커밋 (origin 반영)
1. `270d8b6` refactor(frontend): extract app navigation flow
   - 신규 `hooks/useAppNavigation.ts`; `Index.tsx`의 onHome·resetAnalysisState·onItemClick·onToggleCollapse·onRenameProject·onDeleteProject·onNewProject → hook 이동(verbatim)
2. `3970567` refactor(frontend): dedup ui snapshot builder, reduce nav hook params
   - `Index.tsx` `buildUiSnapshot` 단일 빌더(uiSnap 3→1), hook param 18→11
3. `cef2e93` refactor(frontend): split center panel passive views
   - 신규 `components/views/EmptyProjectView.tsx`·`AnalysisLoadingView.tsx`(props 3); CenterPanel empty/loading 분기 치환
4. `2866a77` docs: 본 핸드오프 + CHECKLIST
5. `bf50e12` fix(trash): live-sync project list and trash panel on delete/restore
   - `Index.tsx` `reloadProjects` 추출; `TrashPanel.tsx` props(onChanged·reloadDep) — 삭제→휴지통 / 복원→메뉴 즉시 반영
6. `b103b30` refactor(backend): split health/debug routes into routers/health
   - 신규 `routers/__init__.py`·`routers/health.py`(/health·/pipeline/status·/system/diagnostics); main.py include_router

## 검증 (머신 raw)
- 각 단계: tsc 0 / vite build ✓ / py_compile PYC_OK / diff 예상 파일만.
- PRODUCT(국장 실화면): 첫화면·프로젝트 클릭/전환·홈버튼·Proposal A/B·Export·휴지통 삭제/복원 즉시반영 = PASS.
- 백엔드: 재기동 정상(순환 import 없음), /health·/pipeline/status·/system/diagnostics 실응답 확인.

## 다음 작업 후보 (남은 분해)
- 프론트: CenterPanel 2차 분리(FragmentMap/ProposalCompare/Export 섹션 — props≥15 예상, 재가설 필요).
- 백엔드: main.py 추가 저위험 router(theme 등; static/P_panorama/export/semantic-fragments/ASR/auth는 금지).
- 휴지통 라이브갱신 = **해결 완료**(bf50e12).
