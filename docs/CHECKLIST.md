# CCUT 1.0.4 CHECKLIST — 2026-06-25

브라우저에서 직접 확인한 항목만 [x] 표시.

---

## 재생 / 플레이백

- [x] A/B 소스 원본 영상 재생 (proxy h264)
- [x] H 소스 proxy 재생 — `/static/proxies/play_SRC_47E44193.mp4` 확인
- [x] 조각 전환 플리커 수리 — opacity 0 통제 (CODE PASS, 브라우저 확인 대기)
- [ ] G1+ 조각 플레이 — G_clips=0, proposal 재생성 필요
- [ ] C/D/F/G 원본 영상 재생 확인

## 내보내기

- [ ] Electra B안 내보내기 PRODUCT PASS — R3 수정 후 실측 미완료
- [ ] 재편집 후 내보내기 2회 이상 성공

## 편집 상태 복원

- [ ] 내보내기 → 다시 편집하기 → editFragments 유지 (FIX-EXPORT-UISTATE CODE PASS, 브라우저 확인 대기)

## sourceEntries / 복원

- [ ] Electra 11개 영상 복원 — `data.status = "NO_SEMANTIC_DATA"` 미해결
- [ ] storyPlan "11개의 영상" 표시

## ASR / 분석

- [x] R1 ASR_MODEL_CHANGED 오판 수리 — EVIDENCE PASS (6 sources needs=False)

## git / 빌드

- [x] push 064e74aa..075b30e → ccut-1.0.4-step9 ✅
- [x] SYNTAX OK: render_engine.py, Index.tsx, CenterPanel.tsx

## god-file 리팩토링 (2026-06-28, baseline 6d59435)

- [x] STEP1 useAppNavigation 추출 — `270d8b6` (tsc 0, diff 2파일)
- [x] STEP2 uiSnap dedup 3→1 + hook param 18→11 — `3970567` (tsc 0, diff 2파일)
- [x] STEP3 CenterPanel passive view 2개 분리(props 3·3) — `cef2e93` (tsc 0, diff 3파일)
- [x] 전체 회귀: tsc 0 / vite build ✓ built / py_compile PYC_OK / 누적 diff 5파일
- [x] PRODUCT 실화면: F5 첫화면·프로젝트 클릭/전환·홈버튼·Proposal A/B·Export·휴지통 = PASS
- [ ] 휴지통 라이브갱신(삭제→휴지통 / 복원→프로젝트메뉴 즉시반영) — 범위 밖, 미구현. 새로고침 시 정상. 별도 작업 예정
