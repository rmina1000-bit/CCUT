# CCUT 1.0.4 Runtime Audit — STEP 1-R2
# Cognitive Fragment 원인 추적 보고서

**감사 일시:** 2026-05-11 21:24 KST  
**감사자:** Antigravity  
**전제 DB:** `ccut_backend/ccut_app.db`  
**전제 사실:** sources 64, fragments 296, evidence_board 296, semantic_fragments 942, proposals 128

---

## 작업 1. SF 재귀 분할 원인 확인

### 원인 코드 위치

**파일:** `ccut_backend/engine/semantic_engine.py` L270~359  
**함수:** `apply_merge_split()`

### 재귀 구조 분석

```python
# L323~358 (2. Split 블록)
for frag in res:
    duration = frag["structural"]["duration"]
    if duration > 20.0:
        mid = frag["start"] + (duration / 2.0)
        cuts = [b for b in boundaries if frag["start"] + 5.0 < b < frag["end"] - 5.0]

        if cuts:
            cut = sorted(cuts, key=lambda x: abs(x - mid))[0]
        else:
            # ← 경계 없을 때 강제 분할 (random 10±2s)
            import random
            cut = round(frag["start"] + 10.0 + random.uniform(-2.0, 2.0), 2)
            if not (frag["start"] + 5.0 < cut < frag["end"] - 5.0):
                cut = round(mid, 2)

        f1["fragment_id"] = f"{frag['fragment_id']}_S1"   # ← suffix 누적 지점
        f2["fragment_id"] = f"{frag['fragment_id']}_S2"   # ← suffix 누적 지점

        # 재귀 호출 조건:
        if f1["structural"]["duration"] > 20.0 or f2["structural"]["duration"] > 20.0:
            sub_final = self.apply_merge_split([f1, f2], boundaries, total_duration)
            #                                   ^^^^
            #                         f1/f2는 이미 _S1/_S2 suffix가 붙은 상태
            #                         다시 20s 초과면 → _S1_S1, _S1_S2, _S2_S1, _S2_S2 ...
            final.extend(sub_final)
```

### 재현 조건

| 조건 | 내용 |
|------|------|
| 트리거 | `duration > 20.0`인 fragment 존재 |
| 가속 조건 | `boundaries` 내에 해당 구간 내 유효 경계가 없을 때 강제 `cut = start + 10±2s` 적용 |
| 재귀 조건 | split 후 `f1` 또는 `f2`의 duration이 다시 20s 초과 |
| depth limit | **없음** — `apply_merge_split()` 재귀 호출에 depth 카운터 없음 |
| SRC_E07CD8DF 40단계 원인 | 영상이 길고 whisper_segments evidence가 없거나 경계가 희박 → 모든 cut이 강제 분할(random 10s) → 분할 후 duration이 계속 20s 초과 → 40회 이상 재귀 |

### suffix 누적 경로 (예시: 100초 조각)

```
SF_XXXX_SRC_E07CD8DF              (100s, duration > 20s)
  → apply_merge_split([f1, f2])
      f1 = SF_XXXX_SRC_E07CD8DF_S1   (50s, > 20s)
      f2 = SF_XXXX_SRC_E07CD8DF_S2   (50s, > 20s)
        → apply_merge_split([f1_S1, f2])
            f1_S1_S1 = SF_XXXX_SRC_E07CD8DF_S1_S1   (25s, > 20s)
            ...
              → 계속 재귀 → _S1_S1_S1_S2_S2_S2_... 40단계
```

### 영향 범위

| 항목 | 내용 |
|------|------|
| DB 오염 | `semantic_fragments` 테이블에 `_S2_S2_S2...` ID 실제 저장 (DB 확인됨) |
| 썸네일 오염 | `storage/thumbnails/`에 22~40단계 suffix 파일 대량 생성 |
| Proposal 사용 | proposal sequence는 SF_id를 그대로 참조 → 오염된 ID가 proposal에도 진입 |
| 성능 | 재귀 깊이에 따라 SF 수가 기하급수적으로 증가 (942개의 상당 부분이 split 파생 조각) |

### 수정 난이도

| 항목 | 판단 |
|------|------|
| 수정 위치 | `apply_merge_split()` 단 1곳 |
| 수정 내용 | `max_depth` 파라미터 추가 또는 재귀 전 duration 재확인 없이 그냥 append |
| 난이도 | **낮음** (5줄 이내 변경) |
| 분류 | **버그 수정** — 의도된 재귀이나 depth limit이 누락된 결함. 새 기능이 아님. |

---

## 작업 2. motion_score 미작동 원인 확인

### motion_score writer 존재 여부

전체 코드베이스에서 `motion_score`를 실제로 기록하는 경로를 추적:

| 경로 | 코드 | 실제 기록 여부 |
|------|------|--------------|
| `signal_processor.py::build_dynamic_segments()` | scene/silence 감지만. motion_score 할당 없음 | ❌ 없음 |
| `qwen_vl_visual_worker.py::_parse_vl_response()` | `perception`, `visual_role`, `thinking_trace` 저장. motion_score 없음 | ❌ 없음 |
| `main.py::_background_signal_analysis()` | `audio_energy`, `scene_change`만 update_evidence. motion_score 없음 | ❌ 없음 |
| `main.py::_background_vl_perception()` | `update_fragment_intelligence("perception")`만. motion_score 없음 | ❌ 없음 |
| `archive/db_models.py` | `EvidenceTable.motion_score = Column(Float, default=0.0)` — 스키마만 존재 | — |

**결론: motion_score를 0 이외의 값으로 쓰는 코드가 코드베이스 전체에 존재하지 않는다.**

### motion_score reader 존재 여부

**파일:** `semantic_engine.py` L245

```python
# calculate_edit_value() 내부
s_vis = ev.get("motion_score", 0.0)     # ← 읽음
ev_score = (s_sp * w_speech * 0.4) + (s_vis * w_visual * 0.3) + (s_em * w_emotion * 0.2)
```

reader는 존재하나 값이 항상 0.0이므로 `s_vis * w_visual * 0.3` 항이 항상 0.

### Proposal 품질 영향

| 항목 | 영향 |
|------|------|
| `edit_value` 계산 | visual 가중치 항(30%)이 항상 0 → speech + audio_energy만으로 scoring |
| `market_value` 계산 | 동일. visual 기여분 소멸 |
| `role` 분류 | `edit_value`가 낮아지므로 hook/payoff 판정 역치(0.6/0.8)에 미달 → 대부분 `context` role로 떨어짐 |
| Proposal 선택 | ProposalEngine이 edit_value 기준으로 SF 선택 → visual이 강한 영상에서도 speech만 있는 조각 우선 선택 |

### 판정

| 항목 | 판정 |
|------|------|
| writer | ❌ 없음 (설계 미구현) |
| reader | ✅ 있음 (semantic_engine.py L245) |
| DB 증거 | motion_score 296개 전부 0.0 (사용자 확인) |
| 현재 PASS 단계 | **FAIL** — 스키마 정의만 있고 데이터 없음 |

---

## 작업 3. Visual/Audio Context 반복 원인 확인

### summary = "Visual/Audio Context" 발생 위치

**파일:** `semantic_engine.py` L197

```python
# build_fragments() 내부
"summary": (combined_text[:50] + "...") if combined_text else "Visual/Audio Context",
```

**`combined_text`가 비어 있을 때 → 무조건 `"Visual/Audio Context"` 고정 문자열로 fallback.**

`combined_text`는:
```python
combined_text = " ".join([e.get("text", "") for e in overlapping_evs if e.get("text")]).strip()
```

즉 `EvidenceTable.text`가 비어 있거나 None인 Evidence만 있을 때 `combined_text = ""` → fallback.

### topic = "general" 고정 조건

**파일:** `semantic_engine.py` L198

```python
"topic": primary_ev.get("topic", "general"),
```

`EvidenceTable`에는 `topic` 컬럼이 없다 (`db_models.py` 확인).  
`primary_ev`는 `get_evidence_board()` 결과이며 Evidence row에 `topic` 키가 없음 → `.get("topic", "general")` → 항상 `"general"`.

### Whisper 결과 약할 때 흐름

```
transcribe_fragments() 결과가 없거나 빈 text → EvidenceTable.text = None/""
  → create_fragment_boundaries()에서 whisper_segment evidence 수 = 0
    → 경계 후보가 희박
      → build_fragments()에서 combined_text = ""
        → summary = "Visual/Audio Context"
          → topic = "general"
            → confidence = 0.7 (낮음)
              → fallback_reason = "continuity_placeholder" (sentiment_continuity == 0.5 고정)
```

### QwenVL perception이 summary에 들어가는지

**파일:** `main.py::_background_vl_perception()`

QwenVL 결과는 `FragmentTable.intelligence["perception"]`에 저장됨.  
`SemanticFragmentGenerator.build_fragments()`는 `EvidenceTable` evidence만 읽음 (`get_evidence_board(source_id)`).  
→ **QwenVL perception은 SF semantic.summary에 전혀 반영되지 않는다.**

### 원인 정리

| 원인 | 위치 | 내용 |
|------|------|------|
| summary fallback | `semantic_engine.py` L197 | `combined_text` 비어 있으면 무조건 `"Visual/Audio Context"` |
| topic 항상 general | `semantic_engine.py` L198 | `EvidenceTable`에 `topic` 컬럼 없음 → `.get("topic", "general")` → 항상 `"general"` |
| QwenVL 미반영 | `build_fragments()` 입력 경로 | `get_evidence_board()`만 읽음. `FragmentTable.intelligence["perception"]` 미사용 |
| continuity_placeholder 반복 | `semantic_engine.py` L368 | `sentiment_continuity == 0.5` → 항상 True (초기값 0.5 고정, 갱신 로직 없음) |

---

## 작업 4. Evidence → SF → Proposal 연결 재분류

### 분류표

| 연결 단계 | 상태 | 근거 |
|----------|------|------|
| Evidence 수집 (text, audio, scene) | **연결됨** | `evidence_board` 296개 row 확인, text/audio_energy/scene_change 존재 |
| Evidence → SF 경계 계산 | **연결됨 (약함)** | whisper_segments 기반 경계 동작하나, motion/visual 기여 0 |
| SF 생성 | **연결됨 (오염)** | `semantic_fragments` 942개. 단 상당수가 _S2_S2 재귀 파생 |
| SF → Proposal | **연결됨** | `proposals` 128개, sequence에 SF_id 사용 확인 |
| motion_score Evidence → SF scoring | **버그 (미작동)** | writer 없음, 항상 0.0 |
| visual evidence (QwenVL) → SF summary | **버그 (미연결)** | `build_fragments()`가 `EvidenceTable`만 읽음. `FragmentTable.intelligence["perception"]` 미사용 |
| topic field → SF topic | **버그** | `EvidenceTable`에 topic 컬럼 없음 → 항상 "general" |
| word timestamps → SF boundary | **미연결** | words DB 저장됨, 그러나 `create_fragment_boundaries()` 미사용 |
| SF 재귀 분할 ID 오염 | **버그** | _S2_S2_..._S2 ID DB 실 저장 확인 |
| Browser/Product 검증 | **미검증** | API 동작 확인됨, 브라우저 체감 미확인 |

---

## 최종 보고

### 확인 파일

| 파일 | 핵심 확인 위치 |
|------|--------------|
| `semantic_engine.py` | L197(summary fallback), L245(motion_score reader), L270~359(apply_merge_split 재귀), L368(continuity_placeholder) |
| `signal_processor.py` | motion_score 기록 코드 없음 확인 |
| `main.py` | `_background_vl_perception()` L446-491: perception → FragmentTable만 저장 |
| `qwen_vl_visual_worker.py` | motion_score 기록 없음 확인 |
| `archive/db_models.py` | `EvidenceTable.motion_score = Column(Float, default=0.0)` 스키마만 존재 |
| `archive/manager.py` | `get_evidence_board()` 반환 필드에 topic 없음 확인 |

### 원인 코드 위치 요약

| 버그/결함 | 파일:라인 | 코드 |
|----------|----------|------|
| SF 재귀 depth limit 없음 | `semantic_engine.py:350~352` | `if f1 or f2 > 20.0: self.apply_merge_split(...)` |
| suffix 누적 지점 | `semantic_engine.py:344,347` | `f1["fragment_id"] = f"{frag['fragment_id']}_S1"` |
| motion_score writer 없음 | 코드베이스 전체 | 해당 컬럼 write 코드 부재 |
| summary "Visual/Audio Context" | `semantic_engine.py:197` | `if combined_text else "Visual/Audio Context"` |
| topic 항상 "general" | `semantic_engine.py:198` | `primary_ev.get("topic", "general")` — EvidenceTable에 topic 컬럼 없음 |
| continuity_placeholder 항상 발생 | `semantic_engine.py:368` | `sentiment_continuity == 0.5` 초기값 고정, 갱신 없음 |
| QwenVL perception SF 미반영 | `semantic_engine.py:185~210` | `build_fragments()`가 `EvidenceTable`만 읽음 |

### 실제 DB 증거

| 항목 | DB 확인 결과 |
|------|------------|
| `semantic_fragments` 수 | 942개 (fragments 296의 3.2배 → 재귀 분할 영향) |
| `_S2_S2` 재귀 ID | DB 실 저장 확인됨 |
| `motion_score > 0` | 296개 중 0개 |
| `fallback_reason = continuity_placeholder` | 최근 SF 다수 확인 |
| proposal summary `"Visual/Audio Context"` | 반복 확인 |
| proposal topic `"general"` | 반복 확인 |

### 영향도

| 항목 | 영향도 | 설명 |
|------|--------|------|
| SF 재귀 분할 버그 | **높음** | DB/storage 오염, proposal에 불량 ID 진입 가능 |
| motion_score = 0 | **중간** | visual 가중치 30% 소멸 → edit_value 약화, role 분류 부정확 |
| summary "Visual/Audio Context" | **중간** | ProposalEngine 시맨틱 선택 불가능, 모든 조각 동일 수준으로 평준화 |
| topic = "general" | **중간** | ProposalEngine의 topic 기반 다양성 필터 무력화 |
| continuity_placeholder 반복 | **낮음** | UI 표시 품질 저하, confidence 0.7로 일률 저하 |
| QwenVL perception 미반영 | **낮음** | perception 데이터가 SF scoring에 기여 안 함 (max 3개 제한이라 영향 제한적) |

### 수정 필요 여부

| 항목 | 수정 필요 | 분류 | 난이도 |
|------|----------|------|--------|
| SF 재귀 depth limit | **필요** | 버그 수정 | 낮음 (5줄) |
| motion_score writer 구현 | 필요 (장기) | 미구현 기능 | 높음 |
| summary fallback 개선 | 선택 | 품질 개선 | 낮음 |
| topic 필드 추가 | 선택 | 미구현 기능 | 중간 |
| QwenVL → SF 연결 | 선택 (장기) | 미구현 기능 | 중간 |

### 현재 PASS 단계

| 항목 | PASS 단계 |
|------|----------|
| 파이프라인 연결 | RUNTIME PASS |
| 데이터 품질 (motion/visual) | FAIL |
| SF ID 무결성 | BUG CONFIRMED |
| Proposal 품질 | PARTIAL (speech 기반만 동작) |
| **전체 종합** | **PARTIAL RUNTIME 유지** |

---

## 최종 판정

> ## 🔶 PARTIAL RUNTIME 유지
>
> **근거:**
> - 파이프라인 연결(VF→Evidence→SF→Proposal)은 실제 동작함
> - 그러나 SF ID 오염(재귀 버그), motion_score 전무, visual 미반영, topic 항상 general로 인해
>   생성되는 조각의 **의미적 품질이 보장되지 않음**
> - speech/audio 기반 조각만 선별 가능한 제한적 인지조각 시스템
> - RUNTIME FAIL로 하향하지 않는 이유: text/audio 기반 boundary와 proposal은 실제 동작 중

---

## 다음 권장 작업 (수정 없이 판단 가능한 것)

1. **[즉시 검증 가능] DB 쿼리로 실제 오염 ID 비율 측정**
   ```sql
   SELECT
     COUNT(*) AS total,
     SUM(CASE WHEN fragment_id LIKE '%_S2_S2%' THEN 1 ELSE 0 END) AS recursive_count
   FROM semantic_fragments;
   ```

2. **[즉시 검증 가능] summary 분포 확인**
   ```sql
   SELECT
     CASE WHEN json_extract(semantic_json, '$.summary') = 'Visual/Audio Context' THEN 'fallback' ELSE 'real' END AS type,
     COUNT(*) AS cnt
   FROM semantic_fragments GROUP BY type;
   ```

3. **[버그 수정 대기] `apply_merge_split()` L350-352에 depth limit 추가**
   - 수정 전 이 감사 보고서 사용자 확인 후 진행
   - 새 기능이 아닌 버그 수정으로 분류

4. **[정보 수집] Whisper 실제 작동 확인**
   ```sql
   SELECT COUNT(*) FROM evidence_board WHERE text IS NOT NULL AND text != '';
   ```
   text가 있는 evidence 수 확인 → summary fallback 비율 예측
