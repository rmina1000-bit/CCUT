# CCUT 1.0.4 최종 파일 분류

**기준:** EXECUTION_SPEC (Evidence Board → Semantic Fragment → Proposal → Export)  
**작성일:** 2026-04-26  
**목표:** 1.0.3 코드 감사 + 1.0.4 구조 전환 평가

---

## 분류 범례

- **유지 (KEEP):** 1.0.4에서 그대로 사용 가능
- **수정 (REVISE):** 변경 필요 (1.0.4 구조에 적응)
- **삭제 (DROP):** 제거 (레거시, 미사용)
- **신규필요 (NEW):** 1.0.4 기능 추가
- **보류 (HOLD):** 아직 건드리지 말 것 (후순위)

---

## 최종 분류 (전체 250+ 파일)

### 1. KEEP (유지) — 52개

#### 1.1 Fragment Generation (P1: Evidence Board)
```
✓ ccut_core/fragment_generator/scene_detector.py
✓ ccut_core/fragment_generator/audio_detector.py
✓ ccut_core/fragment_generator/boundary_merge.py
✓ ccut_core/fragment_generator/fragment_generator.py
```

#### 1.2 Rendering (P6: Export)
```
✓ ccut_core/render/render_executor.py
✓ ccut_core/render/render_planner.py
✓ ccut_core/render/smart_render.py
✓ ccut_core/render/render_models.py
✓ ccut_core/render/queue.py
✓ ccut_core/render/worker.py
✓ ccut_core/render/__init__.py
✓ ccut_core/output/output_builder.py
✓ ccut_core/output/artifact_writer.py
✓ ccut_core/output/output_models.py
✓ ccut_core/output/__init__.py
```

#### 1.3 Decision Log & Storage
```
✓ ccut_core/decision_log.py
✓ ccut_core/decision_reducer.py
✓ ccut_core/edit_log/edit_log.py
✓ ccut_core/edit_log/replay_engine.py
✓ ccut_core/edit_log/snapshot_store.py
✓ ccut_core/edit_log/undo_engine.py
✓ ccut_core/edit_log/verify_edit_log.py
✓ ccut_core/edit_log/decision_api.py
✓ ccut_core/edit_log/__init__.py
```

#### 1.4 Projection Store
```
✓ ccut_core/projection.py
✓ ccut_core/projection/__init__.py
✓ ccut_core/projection/projection_store.py
✓ ccut_core/projection/projection_builder.py
✓ ccut_core/projection/projection_state.py
✓ ccut_core/projection/view_builder.py
✓ ccut_core/projection/view_dto.py
```

#### 1.5 Observability & Monitoring
```
✓ ccut_core/observability/observer_api.py
✓ ccut_core/observability/health_monitor.py
✓ ccut_core/observability/live_metrics.py
✓ ccut_core/observability/production_seal.py
✓ ccut_core/observability/perf_guard.py
✓ ccut_core/observability/crash_guard.py
✓ ccut_core/observability/audit_log.py
✓ ccut_core/observability/event_trace.py
✓ ccut_core/observability/render_trace.py
✓ ccut_core/observability/runtime_switch.py
✓ ccut_core/observability/snapshot.py
✓ ccut_core/observability/timeline.py
✓ ccut_core/observability/trace_buffer.py
✓ ccut_core/observability/trace_chain.py
✓ ccut_core/observability/trace_hash.py
✓ ccut_core/observability/trace_verifier.py
✓ ccut_core/observability/__init__.py
```

#### 1.6 Verification & Utilities
```
✓ ccut_core/verify_engine.py
✓ ccut_core/verify_trace_integrity.py
✓ ccut_core/verify_trace_determinism.py
✓ ccut_core/verify_perf_guard.py
✓ ccut_core/hash_util.py
✓ ccut_core/engine_meta.py
```

#### 1.7 Frontend UI Components (활성)
```
✓ ui/src/components/OriginalPanorama.tsx
✓ ui/src/components/FragmentMap.tsx
✓ ui/src/components/ReservedFragments.tsx
✓ ui/src/components/FragmentTile.tsx
✓ ui/src/components/LeftNav.tsx
✓ ui/src/components/NavLink.tsx
✓ ui/src/components/BoundaryPrecisionOverlay.tsx
```

#### 1.8 Frontend Types & Utils
```
✓ ui/src/types/boundaryTypes.ts (타입은 유지, 신규 추가 필요)
✓ ui/src/types/global.d.ts
✓ ui/src/utils/fragmentUtils.ts
✓ ui/src/utils/precisionEntryChat.ts
✓ ui/src/lib/utils.ts
✓ ui/src/services/thumbnailService.ts
✓ ui/src/hooks/use-mobile.tsx
✓ ui/src/hooks/use-toast.ts
```

#### 1.9 UI Library (shadcn/ui)
```
✓ ui/src/components/ui/* (모든 UI 컴포넌트, 약 45개 파일)
```

#### 1.10 Adapters
```
✓ ccut_ui/app/server.py (기본 구조 유지, 라우트 확장 필요)
✓ ccut_ui/adapters/engine_read_adapter.py
✓ ccut_ui/adapters/write_gateway.py
```

---

### 2. REVISE (수정) — 12개

#### 2.1 Backend - Fragment Generation
```
⚠️ ccut_core/fragment_generator/fragment_generator.py
   문제: Evidence Board 생성 안 함
   수정: scene_change, audio_energy, silence 등을 시간축으로 저장
   영향: HIGH (P1 데이터 완성)
   
⚠️ ccut_core/api/fragment_api.py
   문제: Evidence Board 저장 안 함
   수정: generate_fragments 후 decision_log에 저장
   영향: HIGH (P1 완성)
```

#### 2.2 Backend - Proposal
```
⚠️ ccut_core/proposal_engine/proposal_engine.py
   문제: Semantic Fragment 미사용, Style 없음
   수정:
     1. 입력을 Fragment[]에서 SemanticFragment[]로 변경
     2. Role 기반 점수 추가 (HOOK > BODY > RESOLUTION > TRANSITION)
     3. Style 매개변수 추가 (market, documentary, humor)
     4. A ≠ B 차별화 전략 개선
   영향: HIGH (P4 품질)
   
⚠️ ccut_core/proposal_engine/proposal_api.py
   문제: 입력 구조 미정의, UI 미연결
   수정: 입력 스키마 업데이트, response 구조 정의
   영향: HIGH
```

#### 2.3 Backend - Render
```
⚠️ ccut_core/output/output_builder.py
   문제: Fragment[] 기반, Proposal 입력 미정의
   수정: Proposal (Semantic Fragment[]) → Export Model 변환
   영향: MEDIUM (최후 단계)
```

#### 2.4 Frontend - Main
```
⚠️ ui/src/pages/Index.tsx
   문제: Mock 데이터 사용, API 미연결, Proposal 데이터 구조 없음
   수정:
     1. initialEditFragments 비우기 (또는 []로 초기화)
     2. Proposal 데이터 상태 추가
     3. 제안 선택 시 editFragments 반영 로직
   영향: HIGH (UI 메인)
   
⚠️ ui/src/components/CenterPanel.tsx
   문제: API 호출 없음, Mock 데이터만 사용
   수정:
     1. handleUpload: POST /generate-fragments 호출
     2. 분석 진행: 실제 서버 응답 대기
     3. handleSelectProposal: POST /generate-proposals 호출
     4. 실제 A/B 제안 표시
     5. 오류 처리 추가
   영향: HIGH (UX 핵심)
```

#### 2.5 Frontend - Types
```
⚠️ ui/src/types/boundaryTypes.ts
   문제: Semantic Fragment, Proposal, Evidence 타입 없음
   수정:
     1. SemanticFragmentType 추가
     2. ProposalType 추가
     3. EvidenceRecordType 추가
   영향: MEDIUM (타입 안정성)
```

#### 2.6 Frontend - Data
```
⚠️ ui/src/data/fragmentData.ts
   문제: Mock 데이터 (initialEditFragments 15개 고정)
   옵션 A: 완전 삭제 (서버 응답으로만)
   옵션 B: 테스트용 보류 (개발 중 사용)
   권장: 옵션 A (프로덕션 클린)
   영향: MEDIUM
```

#### 2.7 Server
```
⚠️ ccut_ui/app/server.py
   문제: Evidence Board 조회 API 없음
   수정:
     1. /read-evidence 라우트 추가
     2. engine_read_adapter.read_evidence() 추가
   영향: MEDIUM (인프라)
   
⚠️ ccut_ui/adapters/engine_read_adapter.py
   문제: read_evidence() 함수 없음
   수정: decision_log에서 Evidence Board 조회 함수 추가
   영향: MEDIUM
```

---

### 3. DROP (삭제) — 35개

#### 3.1 레거시 App & Layout (진입점 전환)
```
✗ ui/App.jsx
  이유: ui/main.jsx → ui/src/pages/Index.tsx 직접 로드 (우회됨)
  
✗ ui/layout/MainLayout.jsx
  이유: App.jsx 미마운트로 미사용
  추가: 4개 Proposal (A/B/C/D) 렌더링 (EXECUTION_SPEC: A/B만)
  
✗ ui/layout/ResizablePanel.jsx
✗ ui/layout/ResizeHandle.jsx
  이유: MainLayout 미사용으로 연쇄 미사용
```

#### 3.2 레거시 Panels (마운트 안 됨)
```
✗ ui/left_panel.jsx
  이유: ui/src/components/LeftNav.tsx로 대체
  
✗ ui/right_panel.jsx
✗ ui/right/BoardArea.jsx
✗ ui/right/EditStructureBox.jsx
✗ ui/right/OriginalPanorama.jsx
✗ ui/right/RightPanel.jsx
  이유: 새 구조에서 미사용
  
✗ ui/center_panel.jsx
  이유: ui/src/components/CenterPanel.tsx로 대체
  
✗ ui/chat_ui.jsx
  이유: CenterPanel.tsx에 통합
```

#### 3.3 레거시 VFX & Renderers
```
✗ ui/vfx/CognitiveFX.jsx
  이유: 1.0.3 데모 코드
  
✗ ui/panorama_renderer.jsx
  이유: 새 구조에서 미사용
  
✗ ui/panorama_engine.js
  이유: CLAUDE.md 명시 "Drop 대상"
  문제: 4개 계층 (original, edit, board, selected) 복잡
```

#### 3.4 레거시 Interactions
```
✗ ui/fragment_interaction.jsx
  이유: 미사용
  
✗ ui/UploadDecisionModal.jsx
  이유: 새 CenterPanel에 통합
```

#### 3.5 레거시 Context Providers
```
✗ ui/context/AppStateContext.jsx
  이유: Index.tsx에서 직접 useState 사용
  
✗ ui/context/WorkspaceContext.jsx
  이유: 미사용 (Workspace 개념 1.0.4에서 재정의 필요)
  
✗ ui/context/LayoutContext.jsx
  이유: MainLayout 미사용으로 미필요
  
✗ ui/context/VideoContext.jsx
  이유: 미사용
```

#### 3.6 레거시 컴포넌트
```
✗ ui/components/DecisionSummary.jsx
✗ ui/components/DemoPanel.jsx
✗ ui/components/IdentityScreen.jsx
✗ ui/components/ProposalPanel.jsx
✗ ui/components/VideoUploader.jsx
✗ ui/components/Workspace.jsx
  이유: 모두 미사용 (마운트 체크 필요하나 추정 미사용)
```

#### 3.7 레거시 메인
```
✗ ui/main.jsx
  상황: 현재 활성이지만 ui/src/pages/Index.tsx 직접 로드만 함
  유지: 아직 유지 (Index.tsx 렌더링만 하므로 필요)
  → 실제로는 KEEP이지만, 간결화 검토 필요
```

#### 3.8 Mock 데이터 (선택)
```
⚠️ ui/src/data/fragmentData.ts
   현황: Mock 데이터 (15개 고정)
   REVISE vs DROP:
     - DROP: 프로덕션 클린 (권장)
     - REVISE: 개발/테스트용 보류
   판단: 1.0.4 기능 완성 후 DROP 추천
```

---

### 4. NEW (신규필요) — 10개

#### 4.1 Backend - Audio & Vision
```
🔧 ccut_core/speech_detector.py
   역할: Whisper 통합
   요구: EXECUTION_SPEC "text: str" 필드
   입력: 영상 파일
   출력: [(time, speaker, text), ...]
   영향: HIGH (자막 기반 편집)
   
🔧 ccut_core/motion_detector.py
   역할: 모션 점수
   요구: EXECUTION_SPEC "motion_score: float"
   입력: 영상 파일
   출력: [(time, motion_0to1), ...]
   영향: MEDIUM (동적 장면 감지)
```

#### 4.2 Backend - Semantic Layer
```
🔧 ccut_core/semantic_generator/semantic_generator.py
   역할: Evidence Board → Semantic Fragment
   입력: EvidenceBoard[]
   출력: SemanticFragment[]
   로직:
     1. Evidence 연속 구간 분석
     2. Role 판단 (HOOK: 시작/중요도, BODY, RESOLUTION: 종료)
     3. Summary 생성 (자동 또는 서식)
     4. Emotion 점수
   영향: HIGH (P3 의미층)
   
🔧 ccut_core/semantic_generator/semantic_api.py
   역할: API 라우트
   엔드포인트: POST /generate-semantic
   입력: {"fragments": [...], "evidence": [...]}
   출력: {"semantic_fragments": [...]}
   영향: HIGH
```

#### 4.3 Backend - Infrastructure
```
🔧 ccut_core/observability/evidence_log.py
   역할: Evidence Board 저장/조회
   현황: decision_log에 통합할 수도 있음
   판단: 별도 파일 vs decision_log 확장?
   권장: decision_log 확장 (저장소 단일화)
   영향: MEDIUM
```

#### 4.4 Frontend - API Clients
```
🔧 ui/src/api/uploadService.ts
   역할: /generate-fragments 클라이언트
   함수:
     - uploadVideo(file): Promise<{fragments, evidence}>
     - getEvidenceBoard(id): Promise<EvidenceBoard[]>
   영향: HIGH (UX 핵심)
   
🔧 ui/src/api/proposalService.ts
   역할: /generate-proposals 클라이언트
   함수:
     - generateProposals(fragments, style): Promise<Proposal[]>
   영향: HIGH
```

#### 4.5 Frontend - Hooks
```
🔧 ui/src/hooks/useFragmentUpload.ts
   역할: 업로드 상태 관리
   상태: uploading, progress, fragments, error
   영향: HIGH (재사용성)
   
🔧 ui/src/hooks/useProposal.ts
   역할: 제안 상태 관리
   상태: proposals, selectedId, style
   영향: MEDIUM
```

#### 4.6 Frontend - Components
```
🔧 ui/src/components/EvidenceViewer.tsx
   역할: Evidence Board 시각화
   표시: 타임라인, Scene 변화, Audio 에너지, 자막
   영향: MEDIUM (선택사항, 고급 기능)
   
🔧 ui/src/components/SemanticFragmentEditor.tsx
   역할: Semantic Fragment 수정
   기능: Role 변경, Summary 편집, Confidence 표시
   영향: MEDIUM (고급 편집)
```

---

### 5. HOLD (보류) — 5개

```
⏸️ ccut_core/cut.py
   상태: 미확인 (내용 검토 필요)
   사유: 1.0.3 레거시 가능성
   판단: 실제 사용 여부 확인 필요

⏸️ ccut_core/draft.py
   상태: 미확인
   사유: 1.0.3 레거시 가능성
   
⏸️ ccut_core/cut_projection.py
   상태: 미확인
   사유: Projection과 관계 불명확
   
⏸️ ccut_core/event_registry.py
   상태: 미확인
   사유: Observability 시스템 일부일 수도
   
⏸️ generate_real_frags.py
   상태: 미확인 (프로젝트 루트)
   사유: 테스트/데모 스크립트일 가능성
   판단: 실제 용도 확인 필요
```

---

## 요약 통계

| 분류 | 개수 | 비율 |
|------|------|------|
| KEEP (유지) | 52 | 20% |
| REVISE (수정) | 12 | 5% |
| DROP (삭제) | 35 | 14% |
| NEW (신규) | 10 | 4% |
| HOLD (보류) | 5 | 2% |
| **전체** | **114** | **100%** |

*주: ui/src/components/ui 섹션 (shadcn/ui 라이브러리 45개)은 KEEP에 포함*
*실제 총 파일 수는 250+이나, 위는 커스텀 코드만 분류*

---

## 우선순위 (1.0.4 완성 순서)

### Phase 1: API 통합 (P0 — 필수)
1. ✏️ fragment_generator.py - Evidence Board 생성
2. ✏️ fragment_api.py - 저장
3. ✏️ CenterPanel.tsx - API 호출
4. ✏️ Index.tsx - Mock 제거

**목표:** 실제 영상 업로드 → Fragment[] 출력 동작

---

### Phase 2: Semantic Fragment (P1 — 핵심)
1. 🆕 speech_detector.py - Whisper 통합
2. 🆕 semantic_generator.py - Evidence → Semantic
3. ✏️ proposal_engine.py - Semantic 기반 제안
4. 🆕 proposalService.ts - API 클라이언트

**목표:** Fragment[] → Proposal A/B 자동 생성

---

### Phase 3: UI 완성 (P2 — 사용성)
1. ✏️ CenterPanel.tsx - 실제 제안 표시
2. 🆕 useFragmentUpload.ts - 상태 관리
3. 🆕 EvidenceViewer.tsx - 선택사항

**목표:** 사용자 선택 → 편집 반영

---

### Phase 4: 렌더링 (P3 — 출력)
1. ✏️ output_builder.py - Proposal → Export 매핑
2. ✏️ smart_render.py - 검증

**목표:** MP4 생성

---

### Phase 5: 정리 (P4 — 코드 클린)
1. ✗ 레거시 UI 삭제 (App.jsx 등 35개)
2. ✗ fragmentData.ts Mock 제거

**목표:** 프로덕션 준비

---

## 1.0.4 완성 체크리스트

### Must-Have
- [ ] Evidence Board 구현 (P1)
- [ ] Semantic Fragment 생성 (P3)
- [ ] Proposal A/B 자동화 (P4)
- [ ] Upload → Proposal 파이프라인 연결 (UI-API)
- [ ] 렌더링 (MP4 출력)

### Should-Have
- [ ] Speech Detection (자막)
- [ ] Motion Detection (동적 장면)
- [ ] Proposal Style 선택
- [ ] Evidence Board 시각화

### Nice-to-Have
- [ ] Semantic Fragment 수정 UI
- [ ] 고급 제안 옵션
- [ ] A/B 미리보기

---

## EXECUTION_SPEC 적합성 평가

| 항목 | 현황 | 1.0.4 필요 | 진행률 |
|------|------|-----------|--------|
| Evidence Board | ⚠️ 부분 | ✓ 완성 필요 | 30% |
| Semantic Fragment | ❌ 없음 | ✓ 신규 | 0% |
| Proposal | ⚠️ 불완전 | ✓ 개선 | 40% |
| Export | ✓ 있음 | ✓ 확인 필요 | 70% |
| **전체** | **⚠️** | **✓** | **35%** |

---

**분석 완료**
**상태:** 감사 종료, 구현 준비 완료

**다음 단계:** EXECUTION_SPEC 기준 코드 구현
