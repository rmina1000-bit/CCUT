# STEP 2-C-R1: Proposal Selection Count Audit

**작성일**: 2026-05-14
**branch**: ccut-1.0.4-step9
**HEAD**: 72a5583a889f2bdd29bf9adf5eb28db1f05fac35
**상태**: Backend FAIL 후보 (다중 원인 복합)

---

## 1. 감사 대상

| 파일 | 경로 |
|------|------|
| ProposalEngine | `ccut_backend/engine/proposal_engine.py` |
| SemanticEngine | `ccut_backend/engine/semantic_engine.py` |
| Backend 진입점 | `ccut_backend/main.py` |
| Frontend Hook | `ccut_frontend/src/hooks/useProposalState.ts` |
| Frontend 패널 | `ccut_frontend/src/components/CenterPanel.tsx` |

---

## 2. DB 기준 수치

| source_id | semantic_fragments | proposal A seq | proposal B seq |
|-----------|--------------------|---------------|----------------|
| SRC_CB9107CA | 미확인 (evidence 2, nonempty 0) | 1 | 1 |
| SRC_616AEFBA | 미확인 | 2 | 2 |

### 관찰

- SRC_CB9107CA: evidence nonempty_text = 0. Semantic Fragment의 summary 전체가 `"Visual/Audio Context"` fallback이며, edit_value / market_value는 모두 기본값(0.5) 추정.
- SRC_616AEFBA: nonempty_text = 4 (40자 이하). Semantic Fragment 내 text 기반 evidence가 극소수.

---

## 3. ProposalEngine 코드 감사 결과

### A. max_frags 계산 — 구조적 상한 문제

```python
# proposal_engine.py L139 / L226
is_fast_path = target_len <= 60.0
source_count = len(source_ids) if source_ids else 1
max_frags = min(source_count * 2, 40) if is_fast_path else min(source_count * 3, 60)
```

- `source_count` = 1 (단일 source 호출)
- `is_fast_path` = True (target_len 기본값 60.0 이하)
- **결과**: `max_frags = min(1 * 2, 40) = 2`

**단일 source 단일 영상 기준 최대 선택 가능 fragment 수 = 2.**
이것이 A=2, B=2의 직접 원인.

---

### B. target_len 계산 — 실제 전달 경로

```python
# proposal_engine.py L24
target_len_raw = user_intent.get("target_length", 60.0) if user_intent else 60.0
```

- `user_intent`가 없거나 `target_length` 미설정 시 60.0 고정
- `_safe_target_len(60.0, fragments)`도 60.0 반환 (정상 fragment 있을 때)
- target_len = 60.0 → `is_fast_path = True` → `max_frags = 2`

**60.0초 target_len이 fast_path를 항상 활성화하여 max_frags를 2로 고정한다.**

---

### C. target_len 누락 시 fallback

```python
# proposal_engine.py L797-803
if target_len is None or target_len <= 0:
    total = sum(self._safe_duration(f) for f in fragments)
    if total > 0:
        target_len = min(total, 60.0)  # <-- 역시 60.0 상한
    else:
        target_len = 60.0
```

- 어떤 경우에도 60.0 초과 target_len이 생성되지 않음
- 결과적으로 단일 source는 항상 max_frags = 2

---

### D. duration 기준 필터 (`current_len <= target_len * 1.1`)

```python
# L160 / L247
if current_len + f_dur <= target_len * 1.1:
```

- target_len = 60.0 → 허용 상한 = 66.0초
- SRC_616AEFBA: semantic_fragment 각각 약 29.7초 추정 (1405s / 48 VF 기준)
- 2개 선택 시 약 59.4초 → 3번째 추가 시 약 89초 → 66.0초 초과 → 추가 차단

**target_len=60.0 + fragment 단위 duration이 큰 경우: max_frags=2 + duration 상한 이중 차단.**

---

### E. _hard_guard_final_sequence — 사후 차단 (2차 필터)

```python
# proposal_engine.py L837-885
def _hard_guard_final_sequence(self, sequence, threshold=0.15, min_gap_sec=1.0):
    # 같은 source 내 min_gap_sec(1.0초) 미만 간격 조각 전부 차단
    # 시간 역행(start < prev_start - 0.5) 차단
```

- Semantic Fragment가 모두 단일 source이고, 선택 전 이미 1~2개이므로 이 guard는 추가 영향 없음
- 단, max_frags 제한으로 이미 2개 미만인 경우에도 `_hard_guard`가 추가 제거할 수 있음

---

### F. B Mode edit_value < 0.1 필터

```python
# proposal_engine.py L234
if f.get("structural", {}).get("edit_value", 0.5) < 0.1: continue
```

- text 없는 fragment의 edit_value는 0.0에 가까울 수 있음
- `calculate_edit_value`: `s_sp = 1.0 if ev.get("text") else 0.0`
- evidence text가 없는 경우 speech score = 0 → edit_value < 0.1 가능
- **B Mode에서 추가 fragment 필터링 발생 가능**

---

### G. _is_contiguous_to_selected — 선택 단계 guard

- L162 / L249에서 호출되나, grep 결과 이 함수는 파일 내 정의되지 않음
- 실제 호출 시 `AttributeError` 또는 상위 클래스 메서드 상속 가능성 있음
- **추가 확인 필요**

---

## 4. SemanticEngine 코드 감사 결과

### A. Semantic Fragment 생성 수

```python
# semantic_engine.py L298-321
# Fast path (total_duration <= 60.0): 18개 상한
if is_fast_path and len(res) > 18:
    # 18개로 강제 축소
```

- SRC_616AEFBA: total_duration ≈ 1405초 → fast_path 아님 → 18개 상한 미적용
- 따라서 Semantic Fragment 수 자체가 적은 것은 SemanticEngine 책임 아님

### B. Merge 로직

```python
# semantic_engine.py L287-295
if last["structural"]["duration"] < merge_threshold:  # 3.0초
    # 이전 조각에 병합
```

- VF 단위(약 29초)가 boundary로 사용되면 대형 fragment가 다수 생성됨
- whisper_segments가 없으면 boundary = VF end points만 남음 → fragment = VF 수 = 48개

### C. summary fallback 결정

```python
# semantic_engine.py L197
"summary": (combined_text[:50] + "...") if combined_text else "Visual/Audio Context",
```

- evidence text가 없는 fragment → summary = "Visual/Audio Context" → confidence = 0.7
- edit_value 산출 시 s_sp = 0.0 → edit_value 극소

---

## 5. Frontend 감사 결과

### A. R41_WEAK_SEQUENCE_GUARD

- `ccut_frontend/src`에서 `R41`, `weakSequence`, `sequence_count` 키워드 검색 결과: **없음**
- Frontend에서 sequence를 직접 줄이는 guard 코드 없음

### B. handleProposalCommit / beforeCount / afterCount

- 해당 패턴 없음
- sequence_count는 backend 반환값 그대로 UI에 표시

**Frontend는 sequence count를 변경하지 않는다. Backend가 이미 1~2개를 반환한 것.**

---

## 6. 원인 트리

```
Proposal A/B sequence_count = 1~2
    |
    +-- [1차 원인: CRITICAL] max_frags = 2
    |       source_count=1, is_fast_path=True
    |       -> min(1*2, 40) = 2
    |
    +-- [2차 원인: CONTRIBUTING] duration 상한 이중 차단
    |       target_len=60.0, fragment당 ~29초
    |       2개 선택 후 3번째 추가 불가 (60초 초과)
    |
    +-- [3차 원인: B MODE] edit_value < 0.1 필터
    |       text 없는 fragment 추가 제외
    |
    +-- [4차 원인: MINOR] _hard_guard_final_sequence
            이미 1~2개인 sequence에서 인접 조각 추가 제거 가능
```

---

## 7. 최종 판정

| 항목 | 판정 |
|------|------|
| Frontend Guard가 sequence를 줄이는가 | **없음** — Frontend 무관 |
| Backend에서 1~2개만 생성하는가 | **YES** — Backend 1차 원인 |
| Semantic Fragment 수 부족인가 | **부차적** — max_frags 제한이 우선 |
| ProposalEngine selection policy | **FAIL 후보** |

### 근본 원인

```
max_frags = min(source_count * 2, 40)
           = min(1 * 2, 40)
           = 2
```

**단일 source 처리 시 max_frags가 항상 2로 고정된다.**
이는 멀티소스 균형 설계(`source_count * 2`)가 단일 소스에 그대로 적용된 설계 결함이다.

### 수정 방향 (다음 단계 판단 대기)

- 단일 source일 때 max_frags = `min(len(fragments), 40)` 또는 별도 단일소스 분기 적용
- target_len을 60초 고정이 아닌 source duration의 일정 비율(예: 10~20%)로 산출
- is_fast_path 기준을 target_len이 아닌 source_count 기반으로 재설계

---

## 8. 수정 금지 확인

- ProposalEngine: 미수정 (감사만)
- SemanticEngine: 미수정
- main.py: 미수정
- UI: 미수정
- DB: 미수정
- 커밋: 미수행

---

본 문서는 STEP 2-C-R1 Proposal Selection Count Audit 공식 감사 문서입니다.
수정은 국장님 확인 후 별도 작업지시서에 따릅니다.
