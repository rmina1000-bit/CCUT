# CCUT Task Board

## 2026-05-10 — Proposal Preview Render (PRODUCT PASS ✅ 최종 확정)
- [x] `proposal_preview_engine.py` 신규 생성
- [x] `inject_proposal_previews()` main.py 연결
- [x] `proposalTypes.ts` preview_url 타입 추가
- [x] `Index.tsx` proposal 매핑 시 preview_url 보존
- [x] `CenterPanel.tsx` previewUrlA/B 우선 재생 (currentTime=0, seek 없음)
- [x] `[PREVIEW_MODE_GUARD]` A/B onTimeUpdate fragment seq 개입 차단
- [x] `[DUAL_PLAY_GUARD]` stopOtherPlayer A/B 동시 재생 차단
- [x] letterbox pad filter 적용 (세로 영상 비율 정상화)
- [x] POST/GET `/semantic-fragments` `inject_preview_clips` 제거 (ImportError→500 해소)
- [x] faststart 일괄 적용 (55/57)
- [x] `PROPOSAL_PREVIEW_RENDER_POLICY.md` 문서화
- [x] **push 완료: `git push origin ccut-1.0.4-step9`** (2026-05-10)

## 2026-05-25 — Guard 모듈화 & 편집 파이프라인 정밀 진단 (DONE ✅)
- [x] 아키텍처 감사 — docs/ 명세 전체 코드 대조 검증
- [x] 시뮬레이터 작성 및 실행 — 시간역행 가드 80% 누수 발견 및 pre-sort 보정
- [x] `proposal_guards.py` 신설 — temporal_regression_guard, contiguous_guard, response_level_guard 통합
- [x] 미세조각 최소 갭 완화: 30프레임 → 15프레임 (0.5초)
- [x] B안 소스 점유 한도 완화: 0.4 → 0.55
- [x] `proposal_engine.py` 가드 메서드 제거 및 proposal_guards 위임 리팩토링
- [x] `main.py` _response_level_sequence_guard 제거 및 모듈 통합
- [x] DB 분석 데이터 전체 초기화 (sources 32개만 보존)
- [x] storage 파생 파일 전부 정리 (uploads 31개 보존)
- [x] D드라이브 사본 백업 동기화 완료
- [x] **git push 완료: `ccut-1.0.4-step9`** (2026-05-25)

## NEXT — 소스 다양성 & 시각 증거 통합 📋
- [ ] **새 영상 인제스트** — 초기화된 DB에 영상 새로 등록 및 분석
- [ ] **소스 편향 근원 분석** — 일부 소스만 극단적으로 선택되는 원인 규명
- [ ] **STEP 10-K-B3** — Balanced Sources Proposal Constraint 구현
- [ ] **STEP 10-K-C** — Visual Evidence Scoring Integration
- [ ] **PART A** — 인지조각 생성 감사 (signal_processor, semantic_engine)
- [ ] **PART B** — 편집 파이프라인 감사 (export_engine, render_engine)

---

## STEP 10-K — Deep Visual Analysis Stage (PASS ✅)
- [x] Stage 0-7 Factory Layer Definition
- [x] VL Factory Stage Policy established
- [x] Visual Evidence Cache Policy defined
- [x] Deep Stage Probe tool implemented
- [x] **STEP 10-K-A**: Proposal Intent / Source Diversity Audit (Reported: Disconnect identified)
- [x] **STEP 10-K-B1**: Story Direction Template Registry (Minimal Contract)
- [x] **STEP 10-K-B1-R1**: Editing Technique Library & Hard Rules Binding (DONE)
- [x] **STEP 10-K-B2**: Intent Pipeline Bridge / balanced_sources Connection (DONE)
- [x] **STEP 10-K-B2-R1**: Resolver Metadata on Early Return (DONE)
- [ ] **STEP 10-K-B3**: Balanced Sources Proposal Constraint (NEXT 📋)
- [ ] **STEP 10-K-C**: Visual Evidence Scoring Integration (TODO)
- [ ] Integration with Semantic Fragment Board (Stage 6)
- [ ] Production Cache Layer verification

## STEP 10-I.5.28 — Narrative Consultation Transition

### DONE ✅
- E7-M1 Snapshot / Memory / Debug Log Audit
- E7-M2 Debug Log Guard
- E7-M3/R1 Thumbnail Static Path Repair
- E8 Proposal Diversity Audit
- E8-R1 Lightweight Proposal Diversity Pass
- E8-R2-PRE Qualified Source Coverage Gate Design
- E8-R2-N1 Fragment Map Footer Cleanup / Network Canceled Audit
- E9-PRE Story Direction Confirmation Design
- E9-R1 Story Direction Preview Skeleton
- E9-R1-R1 Story Direction Card Placement Repair
- E9-R2 Pre-Proposal Narrative Consultation Flow
- E9-R2-R5B AI Staff Strategy Docs Creation
- E9-R2-R6 Mock Narrative LLM Adapter Implementation
- E9-R2-R7 Swappable Local Narrative LLM Provider Design
- E9-R2-R8 Target Hardware Profile and Compatibility Probe
- E9-R2-R9 Ollama Local Narrative Provider Probe
- R10-A Qwen Model Inventory and Path Hygiene Review
- R10-B Qwen3-Instruct Acquisition and Ollama Registration Plan
- R10-C Qwen3 4B Ollama Candidate Install Plan
- R10-D Ollama Timeout / keep_alive / num_predict / JSON Response Stabilization

### HOLD / REWORK ⏸
- E9-R2-R1 Narrative Chat History Repair
- E9-R2-R2 ChatGPT-like Conversation UX Repair

> **Reason:** The structure works, but UX does not yet match the desired ChatGPT-form conversational model.

### NEXT 📋
- STEP 10-K-B3: Balanced Sources Proposal Constraint
- STEP 10-K-C: Visual Evidence Scoring Integration
- Integration with Semantic Fragment Board (Stage 6)
- Production Cache Layer verification
- E9-R2-R3: ChatGPT Form Narrative Chat Repair (on hold)

---

## DONE (Legacy) ✅
... (이하 기존 내용 유지)

## NEXT (Legacy) 📋
... (이하 기존 내용 유지)

## HOLD ⏸
- Resource Governor 연동
- 병렬 Worker 렌더링
- PBE(Precision Boundary Editor) 재연결
... (이하 기존 내용 유지)
