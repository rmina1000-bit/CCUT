# CCUT Task Board

## 2026-05-10 — Proposal Preview Render (PRODUCT PASS ✅)
- [x] `proposal_preview_engine.py` 신규 생성
- [x] `inject_proposal_previews()` main.py 연결
- [x] `proposalTypes.ts` preview_url 타입 추가
- [x] `Index.tsx` proposal 매핑 시 preview_url 보존
- [x] `CenterPanel.tsx` previewUrlA/B 우선 재생 (currentTime=0, seek 없음)
- [x] faststart 일괄 적용 (55/57)
- [x] `PROPOSAL_PREVIEW_RENDER_POLICY.md` 문서화

## NEXT — 전체 파이프라인 Runtime Audit 📋
- [ ] **PART A** — 인지조각 생성 감사 (signal_processor, semantic_engine)
- [ ] **PART B** — 편집 파이프라인 감사 (export_engine, render_engine)
- [ ] **PART C** — A/B 제안 품질 감사 (proposal_engine, story_template_resolver)
- [ ] **PART D** — 오픈소스 AI 런타임 감사 (ASR, VL, Narrative, Factory/Governor)

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
