# CCUT 1.0.4 코드 상세 분석

## 분석 기준

각 파일을 아래 형식으로 분석:

```
[파일경로]
역할: 무엇을 하는가
상태: 구현 정도 (✓ 완성 / ⚠️ 부분 / ❌ 없음)
EXECUTION_SPEC 적합성: 기준 충족 여부
분류: 유지/수정/삭제/신규필요/보류
근거: 판정 이유
```

---

## 1. Fragment Generator (P1: Evidence Board)

### 1.1 scene_detector.py
**역할:** HSV 히스토그램 기반 장면 전환 감지  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓ Evidence Board에 scene_change 데이터 제공  
**분류:** 유지  
**근거:**
- EXECUTION_SPEC 요구: "scene_change: bool"
- 구현: HSV threshold 0.45 기준 장면 변화 감지
- 건드릴 이유 없음

**코드 확인:**
```python
# fragment_generator.py:47
detect_scenes(video_path) → (scenes, total_duration)
# scenes: list[tuple(start, end)]
# EXECUTION_SPEC: Evidence Board 입력 데이터
```

---

### 1.2 audio_detector.py
**역할:** RMS 에너지 기반 음성/음향 경계 감지  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓ Evidence Board에 audio_energy, silence 데이터 제공  
**분류:** 유지  
**근거:**
- EXECUTION_SPEC 요구: "audio_energy: float, silence: bool"
- 구현: RMS threshold 1.8 기준 음향 변화 감지
- 현재 구현이 충분함

**코드 확인:**
```python
# fragment_generator.py:48
detect_audio_changes(video_path) → audio_events
# audio_events: list[dict] with energy scores
```

---

### 1.3 boundary_merge.py
**역할:** Scene + Audio 경계 통합, 최소 길이 강제  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓ Fragment[] 생성  
**분류:** 유지  
**근거:**
- MIN_FRAGMENT_LENGTH 0.8초 강제 (합리적)
- 중복 제거, 정렬 등 수행
- 안정적 구현

---

### 1.4 fragment_generator.py (메인)
**역할:** 비디오 입력 → Fragment[] 출력  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ⚠️ Fragment만 생성, **Evidence Board 미생성**  
**분류:** 수정  
**근거:**
- 현재: Fragment[] 만 반환
```python
# fragment_generator.py:51-59
return [
    {"id": f"frag_{i}", "start": start, "end": end, "editStack": []},
    ...
]
```
- **문제:** Evidence Board 없음
- **필요:** scene_change, audio_energy, silence 등을 시간축 기반으로 저장
- **수정 내용:**
  1. Evidence Board 자료구조 생성
  2. decision_log에 저장
  3. Fragment + Evidence 함께 반환

---

### 1.5 fragment_api.py
**역할:** FastAPI 라우트 `/generate-fragments`  
**상태:** ✓ 구현되어 있으나 **UI 미연결**  
**EXECUTION_SPEC 적합성:** ⚠️ 기본은 맞지만 Evidence Board 저장 필요  
**분류:** 수정  
**근거:**
```python
# fragment_api.py:31-58
@router.post("/generate-fragments")
async def generate(file: UploadFile = File(...)):
    fragments = generate_fragments(tmp_path)
    return {"fragments": fragments, "count": len(fragments)}
```
- **현재:** Fragment[] 만 반환
- **필요:** Evidence Board + Semantic Fragment 도 반환 또는 저장
- **수정 내용:**
  1. Evidence Board 생성
  2. decision_log에 저장
  3. 필요시 클라이언트에도 전송

---

## 2. Proposal Engine (P4: Proposal)

### 2.1 proposal_engine.py
**역할:** Fragment[] → Proposal A/B  
**상태:** ⚠️ 구현되어 있으나 **매우 불완전**  
**EXECUTION_SPEC 적합성:** ❌ Semantic Fragment 미사용, Style 없음  
**분류:** 수정  
**근거:**

**현재 구현 (제한사항):**
```python
# proposal_engine.py:29-40
def _score(frag: dict, idx: int, total: int) -> float:
    dur = frag.get("duration", 0.0)
    pos_ratio = idx / max(total - 1, 1)
    positional = 1.0 if (pos_ratio <= 0.20 or pos_ratio >= 0.80) else 0.0
    return dur + positional
```

**문제점:**
1. Duration 기반만 고려 (Semantic Fragment 무시)
2. Style 개념 없음 (market, documentary, humor)
3. Role 고려 없음 (HOOK, BODY, RESOLUTION)
4. Semantic Fragment 입력 구조 없음

**EXECUTION_SPEC 요구:**
```json
{
  "proposal_id": "A",
  "fragments": ["SF_001", "SF_010"],
  "style": "market"
}
```

**필요 수정:**
1. Semantic Fragment 입력으로 변경
2. Role 기반 점수 추가 (HOOK 높음, TRANSITION 낮음)
3. Style 매개변수 추가
4. A ≠ B 차별화 전략 개선

---

### 2.2 proposal_api.py
**역할:** FastAPI 라우트 `/generate-proposals`  
**상태:** ✓ 기본은 구현  
**EXECUTION_SPEC 적합성:** ❌ UI 미연결, Semantic Fragment 입력 없음  
**분류:** 수정  
**근거:**
- UI (CenterPanel.tsx)에서 호출 안 함
- 현재 Fragment[] 기반, Semantic Fragment 기반 아님
- 수정: UI 연결 + 입력 구조 변경

---

## 3. Projection & Storage (데이터 저장)

### 3.1 projection_store.py
**역할:** Projection 저장소  
**상태:** ⚠️ 구조는 있으나 **용도 불명확**  
**EXECUTION_SPEC 적합성:** 미확인  
**분류:** 유지 (재사용)  
**근거:**
- 파일 존재하지만 내용 확인 필요
- Semantic Fragment 저장소로 재사용 가능성
- 건드리지 말 것 (현재 working 상태 확인 필요)

---

### 3.2 decision_log.py
**역할:** 편집 결정 로그  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓ Evidence Board 저장소로 재사용 가능  
**분류:** 유지  
**근거:**
- 시간축 기반 이벤트 저장 가능
- APPEND_EVENT 패턴 있음
- Evidence Board 저장에 적합

---

## 4. Render (P6: Export)

### 4.1 render_executor.py
**역할:** 렌더링 실행 엔진  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓  
**분류:** 유지  
**근거:**
- Export Input을 받아 렌더링 실행
- 현재 1.0.3에서 검증됨

---

### 4.2 smart_render.py
**역할:** FFmpeg 브리징  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ✓  
**분류:** 유지  
**근거:**
- Fragment[] 기반 렌더링 로직
- 검증됨

---

### 4.3 output_builder.py
**역할:** Export Model 구성  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ⚠️ Proposal → Export 매핑 필요  
**분류:** 수정  
**근거:**
- 현재 Fragment[] 기반
- Proposal (Semantic Fragment[]) 입력으로 변환 필요

---

## 5. Frontend: ui/src/ (활성 앱)

### 5.1 pages/Index.tsx
**역할:** 메인 컨테이너  
**상태:** ⚠️ 부분 구현  
**EXECUTION_SPEC 적합성:** ⚠️ Mock 데이터 사용, API 미연결  
**분류:** 수정  
**근거:**
```tsx
// Index.tsx:32-33
const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
```
- Mock 데이터로 초기화 (fragmentData.ts:56-73)
- API 호출 없음
- Proposal 데이터 구조 없음

**필요 수정:**
1. initialEditFragments 비움 (서버 응답으로 채우기)
2. Proposal 데이터 구조 추가
3. 제안 선택 후 editFragments 갱신 로직

---

### 5.2 components/CenterPanel.tsx
**역할:** 제안 선택 UI  
**상태:** ✓ UI는 구현, ❌ API 연결 없음  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 수정  
**근거:**

**문제점:**
```jsx
// CenterPanel.tsx:72
const handleUpload = () => setAppState("analyzing");
// → API 호출 없음, 로컬 상태만 변경

// CenterPanel.tsx:28-41
const mockProposals: { a: ProposalOption; b: ProposalOption } = {
    a: { id: "A", title: "내러티브 중심", ... },
    b: { id: "B", title: "비주얼 중심", ... },
};
// → 목업 데이터
```

**필요 수정:**
1. Upload → POST `/generate-fragments` 호출
2. Proposal A/B → POST `/generate-proposals` 호출
3. 실제 데이터로 표시
4. 오류 처리 추가

---

### 5.3 components/OriginalPanorama.tsx
**역할:** 원본 비디오 전시  
**상태:** ✓ 구현 완료  
**EXECUTION_SPEC 적합성:** ✓  
**분류:** 유지  
**근거:**
- 읽기 전용 파노라마
- 타임라인 표시
- 상호작용은 최소한

---

### 5.4 components/FragmentMap.tsx
**역할:** 편집 조각 표시  
**상태:** ✓ 기본 구현  
**EXECUTION_SPEC 적합성:** ✓  
**분류:** 유지  
**근거:**
- 조각 배열 표시
- 선택/하이라이트 기능
- 경계 조정 (미사용이지만 구현됨)

---

### 5.5 data/fragmentData.ts
**역할:** Mock 데이터  
**상태:** ❌ Mock  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
```ts
// fragmentData.ts:56-68
export const initialEditFragments: Fragment[] = [
  makeFragment('A2', 'A', 78, 68),
  makeFragment('A3', 'A', 146, 56),
  ...
];
```
- 1.0.4에서는 서버 응답으로 채워야 함
- Mock 데이터는 필요 없음
- 또는 테스트 용도로 보류

---

### 5.6 types/boundaryTypes.ts
**역할:** TypeScript 타입 정의  
**상태:** ✓ 완성  
**EXECUTION_SPEC 적합성:** ⚠️ Semantic Fragment 타입 필요  
**분류:** 수정  
**근거:**

**현재 타입:**
```ts
// boundaryTypes.ts:8-16
export interface FragmentIntelligence {
  narrative: number;
  emotional: number;
  action: number;
  dialogue: number;
  hook: number;
  callback: number;
  confidence: number;
}
```

**문제:** intelligence 필드 정의는 있지만 실제 사용 안 함

**필요 추가:**
1. SemanticFragment 타입
2. EvidenceRecord 타입
3. Proposal 타입

---

## 6. Frontend: ui/ (레거시, 비활성)

### 6.1 App.jsx
**역할:** 레거시 메인 진입점  
**상태:** ❌ 미사용  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
- ui/main.jsx → ui/src/pages/Index.tsx 직접 렌더링
- App.jsx 마운트 안 됨
- Context Provider들도 미사용

---

### 6.2 layout/MainLayout.jsx
**역할:** 레거시 레이아웃  
**상태:** ❌ 미사용  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
- App.jsx와 함께 미사용
- 4개 Proposal (A/B/C/D) 렌더링 → EXECUTION_SPEC에서 A/B만 필요
- CLAUDE.md: "Proposal C/D 추가 금지"

---

### 6.3 left_panel.jsx, right_panel.jsx, center_panel.jsx
**역할:** 레거시 UI  
**상태:** ❌ 미사용  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
- ui/src/ 새 컴포넌트들로 교체됨
- 마운트 안 됨
- 레거시 코드

---

### 6.4 context/* (AppStateContext, WorkspaceContext, etc)
**역할:** 레거시 상태 관리  
**상태:** ❌ 미사용  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
- Index.tsx에서 직접 useState 사용
- Context 미참조
- 레거시 구조

---

### 6.5 panorama_engine.js
**역할:** 레거시 Fragment 상태 관리  
**상태:** ❌ 미사용  
**EXECUTION_SPEC 적합성:** ❌  
**분류:** 삭제  
**근거:**
- CLAUDE.md 명시: "Drop 대상"
- 4개 계층 (original_fragments, edit_structure, board_fragments, selected_fragments) 복잡함
- 현재 구조에서 불필요

---

## 7. Backend UI Adapter (ccut_ui/)

### 7.1 app/server.py
**역할:** FastAPI 메인 서버  
**상태:** ✓ 기본 구현  
**EXECUTION_SPEC 적합성:** ⚠️ API 라우트는 있으나 구현 미흡  
**분류:** 유지 (기본)  
**근거:**
- Fragment, Proposal, Decision 라우터 포함
- CORS 설정 있음
- 확장 가능한 구조

---

### 7.2 adapters/engine_read_adapter.py
**역할:** 백엔드 엔진 읽기  
**상태:** ✓ 기본 구현  
**EXECUTION_SPEC 적합성:** ✓  
**분류:** 유지  
**근거:**
- Projection, Status, Verify, Metrics 등 조회
- Evidence Board 조회 로직 추가 가능

---

### 7.3 workspace/workspace_view.py
**역할:** 작업공간 뷰  
**상태:** 미확인  
**EXECUTION_SPEC 적합성:** 미확인  
**분류:** 유지 (재사용)  
**근거:**
- 파일 존재하나 내용 미확인
- Semantic Fragment 저장소 역할 가능

---

## 8. 신규 필요 파일

### 8.1 Backend

| 파일 | 용도 | 근거 |
|------|------|------|
| `ccut_core/speech_detector.py` | Whisper 통합 | EXECUTION_SPEC: "text" 필드 |
| `ccut_core/motion_detector.py` | 모션 점수 계산 | EXECUTION_SPEC: "motion_score" 필드 |
| `ccut_core/semantic/semantic_generator.py` | Evidence → Semantic Fragment | Evidence Board → Semantic Fragment 변환 |
| `ccut_core/semantic/semantic_api.py` | API 라우트 | Semantic Fragment 조회 |
| `ccut_core/observability/evidence_log.py` | Evidence Board 저장 | decision_log 또는 별도 저장소 |

### 8.2 Frontend

| 파일 | 용도 | 근거 |
|------|------|------|
| `ui/src/components/EvidenceBoard.tsx` | Evidence 시각화 | P1 데이터 표시 |
| `ui/src/components/SemanticFragment.tsx` | Semantic 편집 | P3 데이터 표시 및 수정 |
| `ui/src/api/upload.ts` | API 클라이언트 | POST /generate-fragments |
| `ui/src/api/proposal.ts` | API 클라이언트 | POST /generate-proposals |
| `ui/src/hooks/useUpload.ts` | 업로드 훅 | 상태 관리 |

---

## 9. 정리

### 삭제 대상 (총 18개)

**레거시 UI:**
- ui/App.jsx
- ui/layout/MainLayout.jsx
- ui/layout/ResizablePanel.jsx
- ui/layout/ResizeHandle.jsx
- ui/left_panel.jsx
- ui/right_panel.jsx
- ui/right/BoardArea.jsx
- ui/right/EditStructureBox.jsx
- ui/right/OriginalPanorama.jsx
- ui/right/RightPanel.jsx
- ui/center_panel.jsx
- ui/chat_ui.jsx
- ui/fragment_interaction.jsx
- ui/panorama_renderer.jsx
- ui/panorama_engine.js
- ui/UploadDecisionModal.jsx

**레거시 Context:**
- ui/context/AppStateContext.jsx
- ui/context/WorkspaceContext.jsx
- ui/context/LayoutContext.jsx
- ui/context/VideoContext.jsx

**Mock 데이터:**
- ui/src/data/fragmentData.ts (또는 테스트용 보류)

---

### 수정 대상 (총 12개)

**Backend:**
1. fragment_generator.py - Evidence Board 생성
2. fragment_api.py - Evidence Board 저장
3. proposal_engine.py - Semantic Fragment 기반, Style 추가
4. proposal_api.py - 입력 구조 변경
5. output_builder.py - Proposal → Export 매핑

**Frontend:**
6. pages/Index.tsx - API 연결, Mock 제거
7. components/CenterPanel.tsx - API 호출, 실제 데이터
8. types/boundaryTypes.ts - SemanticFragment, Proposal 타입 추가
9. data/fragmentData.ts - 비우기 또는 테스트 데이터만

**Server:**
10. ccut_ui/app/server.py - Evidence 조회 API 추가
11. ccut_ui/adapters/engine_read_adapter.py - Evidence 조회 함수 추가

---

### 유지 대상 (총 35개+)

**Fragment Generation:**
- fragment_generator/scene_detector.py
- fragment_generator/audio_detector.py
- fragment_generator/boundary_merge.py

**Rendering:**
- render/render_executor.py
- render/render_planner.py
- render/smart_render.py
- render/queue.py
- output/output_builder.py

**Storage:**
- decision_log.py
- projection_store.py
- edit_log/* (모두)

**Observability:**
- observability/* (모두)

**UI Components:**
- ui/src/components/OriginalPanorama.tsx
- ui/src/components/FragmentMap.tsx
- ui/src/components/ReservedFragments.tsx
- ui/src/components/FragmentTile.tsx
- ui/src/components/LeftNav.tsx
- ui/src/types/boundaryTypes.ts
- ui/src/utils/* (모두)

**UI Library:**
- ui/src/components/ui/* (모두 - shadcn/ui)
- ui/src/hooks/* (기본 훅)
- ui/src/lib/utils.ts
- ui/src/services/thumbnailService.ts

---

### 신규 필요 (총 8개+)

**Backend:**
1. ccut_core/speech_detector.py
2. ccut_core/motion_detector.py
3. ccut_core/semantic/semantic_generator.py
4. ccut_core/semantic/semantic_api.py

**Frontend:**
5. ui/src/components/EvidenceBoard.tsx
6. ui/src/components/SemanticFragmentEditor.tsx
7. ui/src/api/uploadService.ts
8. ui/src/hooks/useFragmentUpload.ts

---

**분석 완료**
**작성일:** 2026-04-26
