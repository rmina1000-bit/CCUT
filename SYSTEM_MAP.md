# CCUT 1.0.4 시스템 구조 맵

## 1. 시스템 아키텍처 (EXECUTION_SPEC 기준)

```
[영상 입력]
    ↓
[P1: Evidence Board 생성]
    scene_detector
    audio_detector
    boundary_merge
    fragment_generator
    ↓
[P2: 데이터 저장]
    decision_log
    projection_store
    ↓
[P3: Semantic Fragment 생성]
    (신규 구현 필요)
    ↓
[P4: Proposal 생성]
    proposal_engine (현재 매우 단순함)
    ↓
[P5: UI 선택]
    CenterPanel (사용자 인터페이스)
    ↓
[P6: 렌더링]
    render_executor
    smart_render
    ffmpeg
    ↓
[MP4 출력]
```

---

## 2. 현재 활성 시스템

### Backend Stack (ccut_ui/app/server.py:30)

```
FastAPI Server (port 8765)
├── Fragment Router
│   └── POST /generate-fragments → fragment_api.py
├── Proposal Router
│   └── POST /generate-proposals → proposal_api.py
└── Decision Router
    └── POST /decision/* → decision_api.py
```

### Frontend Stack (ui/main.jsx → ui/src/pages/Index.tsx)

```
React App (port 3000)
├── Index.tsx (Main Container)
├── CenterPanel.tsx (제안 선택)
├── OriginalPanorama.tsx (원본 보기)
├── FragmentMap.tsx (편집 영역)
└── ReservedFragments.tsx (보류 조각)
```

---

## 3. 데이터 흐름 (현재 vs 목표)

### 현재 (1.0.3 + 초기 1.0.4)

```
영상 → fragment_generator → Fragment[] (Mock 데이터)
            ↓
       CenterPanel (UI 상태만)
            ↓
       proposal_engine (JSON 조합)
            ↓
       사용자 선택
```

**문제:** 
- Evidence Board 없음
- Semantic Fragment 없음
- Mock 데이터만 사용

### 목표 (1.0.4 완성)

```
영상 → [P1 Evidence Board]
        ├─ scene_detector (HSV 기반)
        ├─ audio_detector (RMS 에너지)
        ├─ speech_detector (Whisper)
        └─ → decision_log 저장
            ↓
       [P3 Semantic Fragment]
        ├─ Evidence Board 분석
        ├─ Role 판단 (HOOK, BODY, RESOLUTION)
        ├─ Summary 생성
        └─ → projection_store 저장
            ↓
       [P4 Proposal]
        ├─ Semantic Fragment[] 조합
        ├─ Style 적용 (market, documentary, humor)
        └─ A/B 제안
            ↓
       UI 선택 (사용자)
            ↓
       [P6 렌더]
        ├─ Export Model 생성
        ├─ FFmpeg 호출
        └─ MP4 생성
```

---

## 4. 핵심 데이터 구조

### Evidence Board (시간축 기반 분석)

**위치:** `/ccut_core/decision_log.py` (구현 있음)

**스키마:**
```python
{
    "time": float,           # 초 단위
    "text": str,             # Whisper 결과 (미구현)
    "audio_energy": float,   # 0~1
    "scene_change": bool,    # HSV 히스토그램
    "motion_score": float,   # 0~1 (미구현)
    "silence": bool,
    "speaker": str,          # 화자 ID (미구현)
    "source_id": str         # video_01 등
}
```

**현재 상태:** decision_log만 있고, 실제 Evidence 데이터 구조 미정의

---

### Semantic Fragment (의미 단위)

**위치:** `/ccut_ui/semantic/` (구조만 있음)

**필요 스키마:**
```python
{
    "fragment_id": str,      # SF_001
    "start": float,          # 초
    "end": float,
    "role": str,             # HOOK, BODY, RESOLUTION, TRANSITION
    "summary": str,
    "confidence": float,     # 0~1
    "evidence_refs": list,   # Evidence Board row index
    "emotion": str,          # 선택: happy, sad, neutral, etc
    "pacing": str,           # slow, normal, fast
    "visual_style": str      # talking_head, b_roll, montage
}
```

**현재 상태:** 
- /ccut_ui/semantic/ 디렉토리 있음
- semantic_analyzer.py, semantic_view.py (미구현)
- UI/src/types/boundaryTypes.ts에 이름만 있음 (fragmentData.ts 더미 데이터)

---

### Proposal (조각 조합)

**위치:** `/ccut_core/proposal_engine/proposal_engine.py`

**현재 구현:**
- Duration 기반 scoring
- Positional salience (처음/끝 20% 가중치)
- Interleave pattern (top/bottom)

**문제:**
- Style 개념 없음 (market, documentary, humor)
- Semantic Fragment 미사용 (Fragment[] 직접 조합만 함)
- Role 고려 없음

---

### Export Input (렌더링 모델)

**위치:** `/ccut_core/render/render_models.py`

**필요:**
- Proposal + Resource (영상, 음악, SFX)
- Timeline 정의
- Transition, Effect

**현재 상태:** 미확인 (render_models.py 검토 필요)

---

## 5. 레이어별 상태

### Layer 1: 데이터 획득 (Evidence Board)

| 컴포넌트 | 상태 | 위치 |
|---------|------|------|
| Scene Detection | ✓ 구현 | fragment_generator/scene_detector.py |
| Audio Detection | ✓ 구현 | fragment_generator/audio_detector.py |
| Speech Detection | ❌ 없음 | (신규 필요) |
| Motion Detection | ❌ 없음 | (신규 필요) |
| Storage | ✓ decision_log | decision_log.py |

### Layer 2: 의미 추출 (Semantic Fragment)

| 컴포넌트 | 상태 | 위치 |
|---------|------|------|
| Role Detection | ❌ 없음 | (신규 필요) |
| Summary Generation | ❌ 없음 | (신규 필요) |
| Emotion Scoring | ❌ 없음 | (신규 필요) |
| Storage | ❌ 없음 | projection_store (구조만 있음) |

### Layer 3: 제안 생성 (Proposal)

| 컴포넌트 | 상태 | 위치 |
|---------|------|------|
| Proposal A/B Logic | ✓ 있지만 불완전 | proposal_engine.py |
| Style Selection | ❌ 없음 | (신규 필요) |
| A/B 차별화 | ✓ 있음 | proposal_engine.py |

### Layer 4: UI (사용자 선택)

| 컴포넌트 | 상태 | 위치 |
|---------|------|------|
| Upload Flow | ⚠️ Mock 연결 | CenterPanel.tsx |
| Proposal Display | ✓ UI 있음 | CenterPanel.tsx |
| API Connection | ❌ 없음 | (신규 필요) |
| State Management | ⚠️ 부분적 | Index.tsx |

### Layer 5: 렌더링 (Export)

| 컴포넌트 | 상태 | 위치 |
|---------|------|------|
| Render Planner | ✓ 있음 | render/render_planner.py |
| Render Executor | ✓ 있음 | render/render_executor.py |
| FFmpeg Bridge | ✓ 있음 | (smart_render.py 추정) |
| Output Builder | ✓ 있음 | output/output_builder.py |

---

## 6. 파일 분포

### ccut_core/ (백엔드, 100개+ 파일)

**핵심 영역:**
- `fragment_generator/` - P1 Evidence (부분 구현)
- `proposal_engine/` - P4 Proposal (불완전)
- `projection/` - 저장소 (구조만)
- `render/` - P6 렌더링 (구현됨)
- `decision_log/` - 로그 (구현됨)
- `edit_log/` - 편집 로그 (구현됨)
- `observability/` - 모니터링 (구현됨)

### ccut_ui/ (어댑터, 40개 파일)

**핵심 영역:**
- `app/server.py` - FastAPI 진입점
- `adapters/` - 엔진 읽기/쓰기
- `semantic/` - P3 의미 추출 (미구현)
- `workspace/` - 데이터 뷰

### ui/ (프론트엔드, 100개+ 파일)

**활성 영역:**
- `ui/src/` - 현재 활성 React 앱
- `ui/main.jsx` - 진입점 (Index.tsx 로드)

**비활성 영역:**
- `ui/App.jsx`, `MainLayout.jsx`, 레거시 jsx 파일 (미사용)

---

## 7. 신규 필요 컴포넌트

### Backend

1. **Speech Detection**
   - Whisper API 통합
   - Evidence Board에 텍스트 추가

2. **Motion Detection**
   - Optical Flow 또는 Frame Difference
   - Evidence Board에 motion_score 추가

3. **Semantic Fragment Generator**
   - Evidence Board → Semantic Fragment 변환
   - Role, Summary, Emotion 판단

4. **Semantic Fragment Store**
   - projection_store에 저장
   - 조회 API

### Frontend

1. **Evidence Board Viewer**
   - 시간축 기반 Evidence 시각화
   - Scene/Audio/Motion 그래프

2. **Semantic Fragment Editor**
   - Role, Summary 수정 가능
   - Confidence 표시

3. **Proposal Preview**
   - A/B 비교
   - Style 선택 UI

---

## 8. 주요 연결 고리

### 연결 확인 필요

| 항목 | 상태 |
|------|------|
| /generate-fragments → Evidence Board 저장 | ❌ 확인 필요 |
| Evidence Board → Semantic Fragment 생성 | ❌ 미구현 |
| Semantic Fragment → Proposal 입력 | ❌ 미구현 |
| Proposal 선택 → Export 입력 | ❌ 미구현 |

---

## 9. 절대 보류 항목

- **PBE** (Parametric B-Roll Engine) - EXECUTION_SPEC에 없음
- **Export UI** - 렌더링 패널 (후순위)
- **Direct Editing** - 타임라인 편집 (1.0.3 레거시)

---

**작성일:** 2026-04-26
**목적:** EXECUTION_SPEC 기준 1.0.4 구조 감사
**다음:** CODE_ANALYSIS.md 작성
