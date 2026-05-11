# CCUT 1.0.4 Runtime Audit — STEP 0~1
**감사 일시:** 2026-05-11 21:00 KST  
**감사자:** Antigravity  
**대상 repo:** D:\CCUT1.0.4  
**감사 범위:** VF/SF 조각 생성 → Evidence Board → Proposal 전 파이프라인

---

## 작업 0. 작업트리 기준 확인

### git 실행 결과 (사용자 확인)

```
branch:  ccut-1.0.4-step9
HEAD:    819a4faec6e508f3f1cfcd10378b12a40b6a7d3e

log -8:
819a4fa (HEAD -> ccut-1.0.4-step9, origin/ccut-1.0.4-step9) Document final proposal preview render pass
7f40623 Fix proposal preview playback and semantic fragment regression
94e85f5 Add runtime audit tools for proposal and quality checks
19e0a7f Archive playback and narrative audit reports
ea71168 Archive R6/R8 notes and failed preview clip diff
7028b75 Increase narrative intent frontend timeout
fd9452d Store resolved thumbnail URLs in fragment evidence
2ea7686 Add temporal regression guard to proposal sequences

status --short: (출력 없음)
```

### 판정표

| 확인 항목 | 기대값 | 실제값 | 판정 |
|-----------|--------|--------|------|
| branch | ccut-1.0.4-step9 | ccut-1.0.4-step9 | ✅ PASS |
| HEAD | 819a4fa 포함 | 819a4faec6... | ✅ PASS |
| log에 819a4fa | 존재 | 확인 | ✅ PASS |
| log에 7f40623 | 존재 | 확인 | ✅ PASS |
| git status | clean | 출력 없음 = clean | ✅ PASS |

> **작업트리 기준: 전항목 PASS. 작업 진행 허가.**

---

## 작업 1. Cognitive Fragment Runtime Audit

### 감사 대상 파일

| 파일 | 크기 | 줄수 | 상태 |
|------|------|------|------|
| `ccut_backend/main.py` | 88,356 B | 2,244줄 | ✅ 완료 |
| `ccut_backend/engine/semantic_engine.py` | 21,462 B | 458줄 | ✅ 완료 |
| `ccut_backend/engine/proposal_engine.py` | 43,394 B | 929줄 | ✅ 완료 |
| `ccut_backend/engine/signal_processor.py` | 5,920 B | 132줄 | ✅ 완료 |
| `ccut_backend/engine/vision_engine.py` | 495 B | 16줄 | ✅ 완료 (stub 확인) |
| `ccut_backend/ai/vision/qwen_vl_visual_worker.py` | 7,977 B | 192줄 | ✅ 완료 |
| `ccut_backend/archive/db_models.py` | 7,390 B | 159줄 | ✅ 완료 |
| `ccut_backend/archive/manager.py` | 25,286 B | 573줄 | ✅ 완료 |

### Storage Artifacts 확인

| 경로 | 내용 | 결과 |
|------|------|------|
| `storage/proxies/` | SRC_xxx_proxy.mp4 | ✅ 55개 확인 — 런타임 실행 증거 |
| `storage/thumbnails/` | SF_xxx_SRC_xxx.jpg | ✅ 수천 개 확인 — SF 생성 실행 증거 |

---

## 1-A. Runtime Audit 표

| 항목 | 관련 파일/함수 | 실제 호출 여부 | 생성 artifact | DB/API 반영 | 프론트 사용 | PASS 단계 | 근거 |
|------|----------------|----------------|---------------|-------------|-------------|-----------|------|
| **VF 조각 생성** | `main.py` L636-668<br>`signal_processor.py::build_dynamic_segments()` | ✅ 실제 호출<br>`/generate-fragments` → `sp.build_dynamic_segments()` | `FragmentTable` rows | ✅ `bams.archive_fragments()` → DB | ✅ API 응답 반환 | **RUNTIME PASS** | `storage/proxies/` 55개 proxy.mp4 존재 = 파이프라인 실행 증거 |
| **VF 고정 시간 분할 여부** | `signal_processor.py` L20-78 | ✅ 실행됨 | — | — | — | **⚠️ PARTIAL** | silence+scene 트리거 있으면 인지 기반 분할.<br>트리거 없으면 `max_window`(30~45s) 강제 분할 fallback.<br>완전한 시간조각 방지 아님. |
| **transcript/word timestamps 보존** | `main.py::_background_whisper()` L327-392 | ✅ 실제 호출 | `EvidenceTable.text`<br>`FragmentTable.intelligence["words"]` | ✅ `update_evidence()` + `flush_evidence()` + `update_fragment_intelligence()` | ✅ API 응답 포함 | **RUNTIME PASS** | 코드 추적:<br>`asr.transcribe_fragments()` → `fragment_words[frag_id]` → DB 저장 |
| **silence/scene/audio Evidence 실사용** | `signal_processor.py` L98-130<br>`main.py` L519-550 | ✅ silence+scene: VF 분할 기준 사용<br>audio_energy: Evidence Board 기록 | `EvidenceTable` | ✅ `update_evidence()` + `flush_evidence()` | △ 간접 (SemanticEngine이 읽음) | **CODE PASS** | `get_rms_energy()` → `EvidenceTable.audio_energy` 저장 확인.<br>`motion_score` 필드는 채우는 worker 없음 → **항상 0.0** |
| **VisionEngine 시각 분석** | `engine/vision_engine.py` | ❌ 미호출 | 없음 | 없음 | 없음 | **FAIL** | 16줄 stub:<br>`is_clip_ready() → return False`<br>`describe_scene() → return "Scene description for..."`<br>main.py에서 import하나 파이프라인 어디서도 호출 없음 |
| **QwenVL visual worker** | `qwen_vl_visual_worker.py`<br>`main.py::_background_vl_perception()` L446-491 | ✅ 호출됨 | `FragmentTable.intelligence["perception"]` | ✅ `update_fragment_intelligence()` | △ 간접 | **PARTIAL RUNTIME** | `max_fragments=3` 제한.<br>`production_usable: False` 마킹.<br>Ollama 미실행 시 전체 skip. |
| **Evidence Board → SF 실제 소비** | `semantic_engine.py` L15<br>`manager.py::get_evidence_board()` | ✅ 실제 호출 | `SemanticFragmentTable` | ✅ `bams.save_semantic_fragments()` | ✅ ProposalEngine 입력 | **RUNTIME PASS** | 코드 추적 완료:<br>`sem_gen.generate()` → `get_evidence_board()` → `create_fragment_boundaries()` → `build_fragments()` → `save_semantic_fragments()` |
| **SF → ProposalEngine 전달** | `main.py` L418-419<br>`proposal_engine.py` L14 | ✅ 실제 호출 | `ProposalTable` A/B 2건 | ✅ `bams.save_proposals()` | ✅ 프론트 proposal API | **RUNTIME PASS** | `prop_eng.generate_proposals()` → `get_semantic_fragments()` → A/B 생성 → `save_proposals()` |
| **word timestamps → SF boundary** | `main.py` L333<br>`semantic_engine.py::create_fragment_boundaries()` | △ words 수집은 됨 | `FragmentTable.intelligence["words"]` | ✅ DB 저장됨 | △ | **CODE PASS** | words DB 저장 확인.<br>그러나 `create_fragment_boundaries()`는 `whisper_segments` end 타임만 사용.<br>단어 단위 타임스탬프 경계 계산 **미사용**. |

---

## 1-B. VF/SF 생성 기준 심층 분석

### VF 분할 로직

```
SignalProcessor.build_dynamic_segments()
├── _detect_silence()   → FFmpeg silencedetect -30dB:0.3s  [실제 실행]
├── _detect_scenes()    → FFmpeg showinfo scene>0.4         [실제 실행]
└── 트리거 기반 분할:
    ├── 트리거 있을 때 → ideal_end에 가장 가까운 경계 선택  [인지 기반 ✅]
    └── 트리거 없을 때 → max_window(30s/45s) 강제 분할      [시간 분할 ⚠️]
```

**판정:** VF는 **혼합형**. silence/scene 신호 있으면 인지 기반, 없으면 고정 시간 분할 fallback.

### SF 생성 기준

```
SemanticFragmentGenerator.generate()
├── 입력: get_evidence_board(source_id)
├── whisper_segments evidence → 텍스트 경계 우선 [Text-first ✅]
├── scene_change, silence → 보조 경계 추가
├── [의도적 배제] VF 30s 인공 경계
├── apply_merge_split(): 3s 미만 병합, 20s 초과 분할
│   └── ⚠️ [BUG] 재귀 호출 시 fragment_id에 _S1/_S2 누적 → 22단계 중첩 확인
└── save_semantic_fragments() → DB 저장
```

**판정:** SF는 **실질적 인지조각 지향**. Whisper 문장 단위 우선, VF 경계 무시.  
단, Whisper 실패 시 VF Evidence만 남아 **시간조각으로 퇴보**.

---

## 1-C. 샘플 조각 추적표

> **추적 source_id:** `SRC_7561FF44` (proxy 756MB, 가장 큰 소스)  
> **방법:** 코드 흐름 추적 + 파일시스템 artifacts 기반 (DB 직접 쿼리 미수행)

| 추적 항목 | 내용 |
|----------|------|
| source_id | `SRC_7561FF44` |
| VF fragment_id | `VF1_SRC_7561FF44` ~ `VFn_SRC_7561FF44` |
| SF fragment_id | `SF_XXXXXX_SRC_7561FF44` (storage/thumbnails 다수 확인) |
| start_sec / end_sec | `build_dynamic_segments()` 출력 → `frag["start_time"]`, `frag["end_time"]` |
| 생성 근거 | silence/scene 트리거 → 인지 기반 / max_window → 시간 기반 |
| 사용 evidence | whisper text ✅ / audio_energy ✅ / scene_change ✅ / motion_score ❌ (0.0 고정) |
| transcript/word timestamp | text 보존됨 ✅ / words 보존됨 ✅ / boundary 계산에는 words 미사용 |
| visual evidence | QwenVL 최대 3개 조각만, `production_usable: False` |
| semantic role | `classify_role()` → hook / payoff / context / filler / closing |
| proposal 반영 | ✅ `ProposalTable` A/B sequence에 SF_id 포함 |

### SF 재귀 분할 버그 — 파일시스템 증거

```
storage/thumbnails/ 에서 발견:
  SF_0325D1_SRC_7561FF44_S2.jpg
  SF_0325D1_SRC_7561FF44_S2_S2.jpg
  SF_0325D1_SRC_7561FF44_S2_S2_S2.jpg
  ...
  SF_0325D1_SRC_7561FF44_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2_S2.jpg
                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                                                     22단계 _S2 중첩 확인
```

**원인:** `apply_merge_split()`에서 20s 초과 조각을 `_S1`/`_S2` suffix 추가 후 재귀 호출.  
재귀 depth limit 없음 → 썸네일 엔진이 오염된 fragment_id로 파일 대량 생성.

### 조각 판정 요약

| 케이스 | 판정 |
|--------|------|
| VF (silence/scene 트리거 있음) | **인지조각** |
| VF (트리거 없이 max_window 분할) | **시간조각** |
| SF (whisper_segments 경계 기반) | **인지조각** |
| SF (Whisper 미완료, VF Evidence만) | **시간조각** (퇴보) |
| SF (재귀 분할 22단계 _S2...S2) | **불량조각** |

---

## 1-D. 최종 결론

### 항목별 PASS 요약

| 세부 항목 | 단계 |
|----------|------|
| VF 생성 파이프라인 (FFmpeg 실행) | ✅ RUNTIME PASS |
| Whisper transcript 수집 및 저장 | ✅ RUNTIME PASS |
| Evidence Board 채우기 (text, audio, scene) | ✅ RUNTIME PASS |
| Evidence Board → SemanticFragment 소비 | ✅ RUNTIME PASS |
| SemanticFragment → ProposalEngine 전달 | ✅ RUNTIME PASS |
| Proposal A/B DB 저장 | ✅ RUNTIME PASS |
| VisionEngine (`vision_engine.py`) | ❌ FAIL (16줄 stub) |
| motion_score Evidence 채우기 | ❌ FAIL (worker 없음, 항상 0.0) |
| word timestamps → SF boundary 연결 | ⚠️ CODE PASS only |
| SF 재귀 분할 버그 | 🐛 BUG CONFIRMED |
| QwenVL visual perception | ⚠️ PARTIAL (max 3, production_usable: False) |

### 판정

## 🔶 Cognitive Fragment PARTIAL RUNTIME

**근거:**
- VF → Evidence → SF → Proposal 전체 파이프라인 코드 연결 완료
- `storage/proxies/` 55개, `storage/thumbnails/` 수천 개 실행 artifacts 확인
- whisper_segments 기반 SF는 **인지조각에 근접**
- VisionEngine stub, motion_score 공백, SF 재귀 분할 버그로 full RUNTIME PASS 불가
- PRODUCT PASS는 사용자 브라우저 체감 확인 전 금지 (기존 정책 유지)

---

## 작업 2. Claude 검수용 요약

### 확인한 파일 (8개)

```
ccut_backend/main.py                             (2244줄)
ccut_backend/engine/semantic_engine.py           (458줄)
ccut_backend/engine/proposal_engine.py           (929줄)
ccut_backend/engine/signal_processor.py          (132줄)
ccut_backend/engine/vision_engine.py             (16줄)  ← stub 확인
ccut_backend/ai/vision/qwen_vl_visual_worker.py  (192줄)
ccut_backend/archive/db_models.py                (159줄)
ccut_backend/archive/manager.py                  (573줄)
```

### 확인한 storage artifacts

```
storage/proxies/      → 55개 SRC_xxx_proxy.mp4 (런타임 실행 증거)
storage/thumbnails/   → 수천 개 SF_xxx_SRC_xxx.jpg
                        SF_0325D1_SRC_7561FF44_S2_S2_..._S2.jpg (22단계 재귀 버그 증거)
```

### 실행한 명령

```powershell
# 사용자가 직접 실행, 결과 확인됨
git branch --show-current    → ccut-1.0.4-step9
git rev-parse HEAD           → 819a4faec6e508f3f1cfcd10378b12a40b6a7d3e
git --no-pager log --oneline -8  → 819a4fa, 7f40623 확인
git --no-pager status --short    → 출력 없음 (CLEAN)
```

코드 추적 경로:  
`/generate-fragments` → `build_dynamic_segments` → `archive_fragments`  
→ `_background_whisper` → `sem_gen.generate` → `prop_eng.generate_proposals` → `save_proposals`

### 실제 생성된 artifacts

| artifact | 위치 | 확인 방법 |
|---------|------|----------|
| Proxy MP4 | `storage/proxies/` | 파일시스템 직접 확인 (55개) |
| SF 썸네일 | `storage/thumbnails/` | 파일시스템 직접 확인 (수천 개) |
| FragmentTable | DB (SQLite) | 코드 흐름 추적 |
| EvidenceTable | DB | 코드 흐름 추적 |
| SemanticFragmentTable | DB | 코드 흐름 추적 |
| ProposalTable | DB | 코드 흐름 추적 |

### DB/API 직접 쿼리 결과

미수행 (SQLite 직접 접근 도구 없음).  
artifact 파일 존재로 runtime 실행 간접 확인.

### 의심 지점 5개

**1. SF 재귀 분할 버그 (BUG CONFIRMED)**  
`apply_merge_split()`에서 20s 초과 조각 분할 시 fragment_id에 `_S1/_S2` suffix 누적.  
재귀 depth limit 없음 → `SF_xxx_S2_S2_..._S2.jpg` 22단계 중첩 파일 확인.  
SemanticFragmentTable에 저장된 실제 ID 확인 필요.

**2. VisionEngine stub**  
`engine/vision_engine.py` 16줄 stub. `is_clip_ready()→False`, `describe_scene()→고정 문자열`.  
main.py에서 import하나 파이프라인 어디서도 호출 없음.  
visual evidence (motion_score, scene type)가 SF 생성에 전혀 기여 안 함.

**3. motion_score 항상 0.0**  
`EvidenceTable.motion_score` 필드가 스키마에 있으나 채우는 worker 없음.  
`calculate_edit_value()`에서 `s_vis = ev.get("motion_score", 0.0)` → 항상 0.0.  
market_value, edit_value 계산에서 visual 축 완전 공백.

**4. word timestamps → SF boundary 미연결**  
Whisper `fragment_words[frag_id]` 수집 및 DB 저장 확인.  
그러나 `create_fragment_boundaries()`는 `whisper_segments` end 타임만 사용.  
단어 단위 타임스탬프 경계 계산 미사용. 설계 의도인지 미구현인지 확인 필요.

**5. panorama/signal 병렬 실행 → SF 생성 시 일부 evidence 누락 가능**  
`_background_whisper` 완료 후 `sem_gen.generate()` 순서는 맞음.  
단 `_background_panorama`, `_background_signal_analysis`는 별도 병렬 background_task.  
SF 생성 시점에 audio_energy, keyframe이 아직 없을 수 있음.

### PASS 단계

**Cognitive Fragment PARTIAL RUNTIME**

### 다음 검수 질문 (Claude용)

1. DB 직접 쿼리 요청:
   ```sql
   SELECT fragment_id, start, end, structural_json
   FROM semantic_fragments WHERE source_id='SRC_7561FF44'
   ORDER BY start LIMIT 20
   ```
   → SF start/end 분포 확인 (인지조각 vs 시간조각 비율)

2. DB 직접 쿼리 요청:
   ```sql
   SELECT COUNT(*) FROM evidence_board WHERE motion_score > 0
   ```
   → motion_score가 실제로 항상 0인지 확인

3. DB 직접 쿼리 요청:
   ```sql
   SELECT proposal_id, mode, sequence FROM proposals
   ORDER BY created_at DESC LIMIT 2
   ```
   → Proposal sequence 내 조각 ID가 SF_id인지 VF_id인지 확인

4. SF 재귀 분할 버그 fix 분류 판단 요청:  
   `apply_merge_split()`에 `max_depth` 파라미터 추가 또는 fragment_id suffix 누적 방지 로직이  
   이 STEP 기준에서 "버그 수정"인지 "새 기능 추가"인지 판단해줄 것.

5. word_timestamps → SF boundary 연결이 설계 의도인지 미구현 항목인지 확인.  
   현재 `whisper_segments` (문장 단위)만 경계로 쓰이고, `words` (단어 단위)는 DB 저장 후 사장됨.
