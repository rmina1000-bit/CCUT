# Session Handoff — Proposal Preview Render 해결 및 전체 파이프라인 감사 전환

> 날짜: 2026-05-10  
> 이전 상태: A/B preview 조각 누적 재생 BROWSER FAIL  
> 현재 상태: Proposal Preview Render 구조 전환 완료, PRODUCT PASS

---

## 이번 세션 완료 작업

### 1. Proposal Preview Render 구조 전환 (PRODUCT PASS)

**핵심 변경:**
- `ccut_backend/engine/proposal_preview_engine.py` 신규 생성
  - `ensure_proposal_preview(proposal_id, variant, clips)` — clips → re-encode → concat → faststart mp4
  - idempotent: 존재 시 캐시 재사용
- `ccut_backend/main.py` — `inject_proposal_previews()` 추가
  - `/proposals/project`, `/proposals/{source_id}` 응답에 `preview_url` 주입
- `ccut_frontend/src/proposal/proposalTypes.ts` — `preview_url?`, `preview_duration?` 추가
- `ccut_frontend/src/pages/Index.tsx` — proposal 매핑 시 `preview_url` 보존
- `ccut_frontend/src/components/CenterPanel.tsx`
  - `previewUrlA/B` 우선 재생: `src=preview_url, currentTime=0, play()`
  - preview_url 없을 때만 `startSeq/playFrag` fallback (console.warn 포함)

**저장소:**
- `storage/proposal_previews/PREV_{proposal_id}_{variant}.mp4`

**검증:**
- Backend RUNTIME PASS: PREV_PROP_A/B.mp4 생성 확인
- Frontend CODE PASS: npm build ✅ (1700 modules)
- Browser PASS: `[PROPOSAL_PREVIEW_PLAY]` 콘솔 확인
- Product PASS: 조각 누적 없음, 에코 없음

### 2. Faststart 일괄 적용
- `tools/apply_faststart.ps1` 실행: 55/57 파일 OK (2개 빈 더미 정상 실패)

### 3. 정책 문서 신규 작성
- `docs/PROPOSAL_PREVIEW_RENDER_POLICY.md`

---

## 이번 세션 핵심 교훈

> 브라우저 `<video>`는 편집 타임라인 플레이어가 아니다.  
> `currentTime` seek로 조각 편집본을 조립하는 것은 구조적으로 불가능하다.  
> Backend가 artifact를 만들고, Frontend는 그 artifact를 재생만 해야 한다.

**금지 확정 (proposal preview mode에서):**
- `video.currentTime = startSec` 방식
- `onTimeUpdate/endSec` 기반 조각 전환
- `video_url` (uploads) fallback 재생

---

## 다음 세션 목표 — 전체 파이프라인 Runtime Audit

현재 문제해결 방식("증거가 남는 시스템")을 CCUT 전체에 적용한다.

### 감사 순서
1. **PART A** — 인지조각 생성 감사 (Cognitive Fragment Audit)
2. **PART B** — 편집 파이프라인 감사 (Edit Pipeline Audit)  
3. **PART C** — A/B 제안 품질 감사 (A/B Proposal Audit)
4. **PART D** — 오픈소스 AI 런타임 감사 (Open Source AI Runtime Audit)

### 각 감사 판정 기준
```
코드가 있는가?          → DESIGN PASS
실제로 호출되는가?      → CODE PASS
산출물이 생기는가?      → RUNTIME PASS
API로 전달되는가?       → RUNTIME PASS
프론트가 실제로 쓰는가? → BROWSER PASS
사용자가 체감하는가?    → PRODUCT PASS
```

---

## 환경 정보

- **Branch:** `ccut-1.0.4-step9`
- **Backend:** uvicorn main:app (D:\CCUT1.0.4\ccut_backend)
- **Frontend:** Vite dev (D:\CCUT1.0.4\ccut_frontend)
- **Ollama Models:** `qwen3:4b`, `qwen3-vl:4b`
- **preview_previews 저장소:** `D:\CCUT1.0.4\storage\proposal_previews\`
- **faststart 적용 완료:** 55/57 uploads

---

## 참조 문서

- `docs/PROPOSAL_PREVIEW_RENDER_POLICY.md` — 이번 해결 전체 기록
- `docs/RENDER_ENGINE.md` — Export Render 정책
- `docs/VALIDATION_PROTOCOL.md` — 검증 기준
