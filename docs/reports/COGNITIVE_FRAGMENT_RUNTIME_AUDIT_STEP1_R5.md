# CCUT 1.0.4 Runtime Audit — STEP 1-R5
# Proposal Refresh Link Minimal Fix — 검증 보고서

**감사 일시:** 2026-05-11 23:32 KST  
**감사자:** Antigravity  
**대상 source_id:** SRC_E3BFC963  
**전제 DB:** `ccut_backend/ccut_app.db`  
**수정 파일:** `ccut_backend/main.py` (1개만)

---

## 판정

> ## 🔶 Proposal Refresh Link — **제한적 RUNTIME PASS**

BROWSER PASS 금지 / PRODUCT PASS 금지  
UI A/B preview 확인 전까지는 Runtime 단계로만 기록.

---

## 1. 배경

### STEP 1-R4에서 확인된 문제

```
POST /semantic-fragments/{source_id}
  → SF 재생성 ✅
  → ProposalEngine 호출 없음 ❌
  → 기존 Proposal은 구버전 SF ID 참조 그대로 유지
```

### 수정 요구 (STEP 1-R5 지시)

- `refresh_proposals: bool = False` 쿼리 파라미터 추가
- 기본값 `False` → 기존 동작 완전 유지
- `True` 시에만 ProposalEngine 호출
- Proposal 실패해도 SF 응답 200 유지 (proposal_error 포함)
- Proposal Preview PRODUCT PASS 흐름 불변

---

## 2. 수정 내역

### 2-A. `ccut_backend/main.py`

**수정 위치:** L1076-1118  
**수정 함수:** `generate_semantic_fragments()`

```python
# 수정 전
@app.post("/semantic-fragments/{source_id}")
async def generate_semantic_fragments(source_id: str):
    ...
    return {
        "status": "SEMANTIC_FRAGMENT_READY",
        "fragment_count": len(fragments),
        ...
        # proposal_refreshed 없음
    }

# 수정 후
@app.post("/semantic-fragments/{source_id}")
async def generate_semantic_fragments(source_id: str, refresh_proposals: bool = False):
    ...
    response = {
        "status": "SEMANTIC_FRAGMENT_READY",
        "fragment_count": len(fragments),
        ...
        "proposal_refreshed": False,        # 신규 필드
    }

    if refresh_proposals:
        try:
            from engine.proposal_engine import ProposalEngine
            prop_eng = ProposalEngine(bams)
            proposals = prop_eng.generate_proposals(source_id)
            response["proposal_refreshed"] = True
            response["proposal_count"] = len(proposals)
            response["proposal_ids"] = [p.get("proposal_id") for p in proposals]
        except Exception as e:
            response["proposal_refreshed"] = False
            response["proposal_error"] = str(e)

    return response
```

**변경 원칙:**
- `ProposalEngine` 수정 없음
- `semantic_engine.py` 추가 수정 없음
- 기존 응답 필드 전부 유지
- DB 삭제/마이그레이션 없음
- Proposal Preview 생성 로직(`inject_proposal_previews`) 불변

### 2-B. `ccut_backend/engine/semantic_engine.py`

**수정 위치:** L323-387  
**수정 내용:** `apply_merge_split()` 내 SF 재귀 분할 버그 수정 (STEP 1-R3)

```python
# 수정 전: _S1/_S2 suffix 무한 재귀
f1["fragment_id"] = f"{frag['fragment_id']}_S1"
f2["fragment_id"] = f"{frag['fragment_id']}_S2"
# depth limit 없이 재귀 호출 → _S2_S2_S2... suffix 오염 발생

# 수정 후: _split_long_fragment() 위임 (반복문 기반, 재귀 없음)
def _split_long_fragment(self, frag, boundaries, max_duration=20.0):
    # 1. 기존 _S1/_S2 suffix가 붙어있으면 strip → clean base_id 확보
    base_id = frag["fragment_id"]
    while base_id.endswith("_S1") or base_id.endswith("_S2"):
        base_id = base_id[:-3]

    # 2. while 반복문으로 cursor 이동하며 구간 분할
    #    boundaries 내 구간 중앙에 가장 가까운 경계점 선택
    #    없으면 max_duration(20초)로 단순 절단
    #    마지막 조각 3초 미만이면 이전 파트에 흡수

    # 3. 분할 ID 형식: {base_id}_P001, _P002, ... (결정론적, 재귀 없음)
    child["fragment_id"] = f"{base_id}_P{index:03d}"
```

**수정 원칙:**
- 재귀 호출 완전 제거 (depth limit 방식 아님)
- 반복문(`while cursor < end - 0.5`) 기반 분할
- 기존 `_S1`/`_S2` suffix → strip 후 `_P001`/`_P002` 형식으로 교체
- 기존 오염 ID(`_S2_S2_S2...`)가 있어도 base_id strip으로 정리

---

## 3. API 검증 결과

### 3-1. 서버 health

```
GET http://127.0.0.1:8000/health

→ {"status": "OK", "timestamp": 1778509740.163}

판정: ✅ 서버 정상
```

### 3-2. 기본 호출 (`refresh_proposals` 미포함)

```
POST http://127.0.0.1:8000/semantic-fragments/SRC_E3BFC963

응답 Keys:
  status, source_id, fragment_count, role_distribution, fragments, proposal_refreshed

결과:
  status:               SEMANTIC_FRAGMENT_READY ✅
  fragment_count:       53 ✅
  proposal_refreshed:   false ✅   ← 기본값 정상
  proposal_count:       (없음) ✅
  proposal_ids:         (없음) ✅
  has_proposal_refreshed_key: true ✅

판정: ✅ 기존 동작 유지 확인
```

### 3-3. Refresh 호출 (`refresh_proposals=true`)

```
POST http://127.0.0.1:8000/semantic-fragments/SRC_E3BFC963?refresh_proposals=true

응답 Keys:
  status, source_id, fragment_count, role_distribution, fragments,
  proposal_refreshed, proposal_count, proposal_ids

결과:
  status:               SEMANTIC_FRAGMENT_READY ✅
  fragment_count:       53 ✅
  proposal_refreshed:   true ✅
  proposal_count:       2 ✅
  proposal_ids:         ["PROP_A_461E60_SRC_E3BFC963", "PROP_B_DC6573_SRC_E3BFC963"] ✅
  proposal_error:       (없음) ✅

판정: ✅ ProposalEngine 정상 호출 확인
```

### 3-4. 응답 key 전체 비교

| 기대 key | 기본 호출 | refresh=true 호출 |
|----------|----------|------------------|
| `status` | ✅ | ✅ |
| `source_id` | ✅ | ✅ |
| `fragment_count` | ✅ | ✅ |
| `role_distribution` | ✅ | ✅ |
| `fragments` | ✅ | ✅ |
| `proposal_refreshed` | ✅ (`false`) | ✅ (`true`) |
| `proposal_count` | — | ✅ (`2`) |
| `proposal_ids` | — | ✅ |
| `proposal_error` | — | — (없음=정상) |

---

## 4. DB 검증 결과

### 실행 명령

```python
# ccut_backend/ccut_app.db 직접 쿼리
source_id = "SRC_E3BFC963"

# 최신 SF top-10
SELECT fragment_id FROM semantic_fragments
WHERE source_id=? ORDER BY updated_at DESC LIMIT 10

# 최신 Proposal
SELECT proposal_id, mode, sequence, created_at FROM proposals
WHERE source_id=? ORDER BY created_at DESC LIMIT 1
```

### DB 결과 (사용자 직접 실행 — 2026-05-11 23:32)

```
proposal_id:          PROP_A_461E60_SRC_E3BFC963
mode:                 A
proposal_created_at:  2026-05-11 23:30:09.846373
overlap_count:        2

latest_sf (top-2):
  SF_40706A_SRC_E3BFC963
  SF_5999FB_SRC_E3BFC963
  ...
  SF_8D87AD_SRC_E3BFC963

proposal_first_10:
  SF_84F238_SRC_E3BFC963
  SF_8D87AD_SRC_E3BFC963
```

### DB 판정

| 항목 | 값 | 기대 | 판정 |
|------|-----|------|------|
| proposal_id | PROP_A_461E60_SRC_E3BFC963 | API 응답과 일치 | ✅ |
| proposal_created_at | 2026-05-11 23:30:09 | refresh 호출 이후 시간 | ✅ |
| overlap_count | 2 | > 0 | ✅ |
| SF_8D87AD 공통 | 양쪽 존재 | 최신 SF 참조 확인 | ✅ |

---

## 5. 판정 근거 요약

### PASS 조건 충족 목록

| 조건 | 상태 |
|------|------|
| `proposal_refreshed` key가 응답에 존재 | ✅ |
| 기본 호출에서 `proposal_refreshed=false` | ✅ |
| `refresh_proposals=true` 시 `proposal_refreshed=true` | ✅ |
| `proposal_count=2` | ✅ |
| `proposal_ids` 배열 반환 | ✅ |
| `proposal_error` 없음 | ✅ |
| DB에 최신 proposal 저장됨 (23:30:09) | ✅ |
| `overlap_count=2` (최신 SF와 Proposal 연결) | ✅ |
| 수정 파일 = `main.py` 1개 | ✅ |
| ProposalEngine 수정 없음 | ✅ |
| semantic_engine.py 추가 수정 없음 | ✅ |
| Proposal Preview 흐름 불변 | ✅ |

### FAIL / 미확인 목록

| 항목 | 상태 |
|------|------|
| UI A/B preview 재생 확인 | ❌ 미검증 |
| 브라우저 실제 Proposal 표시 확인 | ❌ 미검증 |
| `refresh_proposals=true` 호출 후 새 preview_url 유효 여부 | ❌ 미검증 |
| motion_score 개선 | ❌ 미해결 (STEP 1-R2 한계 그대로) |

---

## 6. PASS 단계 최종 정리

| 단계 | 의미 | 상태 |
|------|------|------|
| DESIGN PASS | 문서/설계 존재 | ✅ |
| CODE PASS | 코드 존재/컴파일 가능 | ✅ |
| RUNTIME PASS | 실제 DB/API/파일 결과 생성 | ✅ **제한적** |
| BROWSER PASS | 브라우저 UI 확인 | ❌ 미검증 |
| PRODUCT PASS | 사용자 체감 확인 | ❌ 금지 |

> **판정: 제한적 RUNTIME PASS**  
> API 응답과 DB 모두 최신 SF 기준 Proposal 갱신 확인됨.  
> BROWSER/PRODUCT PASS는 UI A/B preview 확인 전까지 금지.

---

## 7. 다음 단계

```
1. git status 확인 → main.py, semantic_engine.py 수정분 검토
2. compile 확인 (python -m py_compile ccut_backend/main.py)
3. commit 준비 (사용자 판단 후 진행)
4. BROWSER PASS 진행 시:
   - http://localhost:8080/ 에서 영상 업로드 → 분석 → A/B preview 확인
   - UI에서 proposal_refreshed 흐름 체감 확인
```
