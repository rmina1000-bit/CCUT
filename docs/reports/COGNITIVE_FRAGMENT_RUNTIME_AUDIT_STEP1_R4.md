# CCUT 1.0.4 Runtime Audit — STEP 1-R4
# Proposal Refresh Link Audit

**감사 일시:** 2026-05-11 21:47 KST  
**감사자:** Antigravity  
**대상 source_id:** SRC_E3BFC963  
**전제 DB:** `ccut_backend/ccut_app.db`  

---

## 현재 확인 사실 (전제)

| 항목 | 값 |
|------|-----|
| semantic_fragments 신규 생성 | 53개 (2026-05-11 21:39:50) |
| recursive_S2_count | 0 ✅ |
| SF ID 정상 | id_len 22 ✅ |
| proposals 기존 생성 | 2026-05-03 13:38:00 (구버전) |
| proposal sequence | 예전 SF ID 참조 (불일치) |

---

## 작업 1. SF 재생성 후 ProposalEngine 호출 여부

### 핵심 흐름 추적

#### 경로 A — 최초 분석 파이프라인 (`_background_whisper()`)

```
main.py L394-419
  sem_gen.generate(source_id)    # SF 재생성
  prop_eng.generate_proposals(source_id)  # Proposal 즉시 연결
  → save_proposals(): 기존 삭제 후 재저장 (REPLACE 방식)
```

**판정:** 최초 분석 시에는 SF → Proposal 자동 연결됨.

---

#### 경로 B — `/semantic-fragments/{source_id}` POST 호출 시

```
main.py L1076-1103
  @app.post("/semantic-fragments/{source_id}")
  async def generate_semantic_fragments(source_id: str):
      gen = SemanticFragmentGenerator(bams)
      fragments = gen.generate(source_id)   # SF 재생성 ✅
      # → inject_semantic_thumbnails(fragments)
      return {"fragments": fragments}
      # ← Proposal 재생성 호출 없음 ❌
```

**핵심 발견:**  
`POST /semantic-fragments/{source_id}` 는 SF를 재생성하지만  
**ProposalEngine을 호출하지 않는다.**  
SF는 새로 갱신되지만 Proposal은 이전 DB 값 그대로.

---

#### 경로 C — 프론트엔드 분석 완료 흐름

```
Index.tsx L405-415
  for (const sid of completedSourceIds) {
    const semanticRes = await fetch(`${API_BASE_URL}/semantic-fragments/${sid}`, { method: "POST" })
    // → POST /semantic-fragments/{sid} 호출 → SF 재생성
  }

Index.tsx L562-565
  // 단일 소스인 경우
  const res = await fetch(`${API_BASE_URL}/proposals/${sid}`, { method: "POST" })
  // → POST /proposals/{sid} 호출 → ProposalEngine.generate_proposals() 실행
```

**분기 조건:**

```
if (completedSourceIds.length >= 2):
  → POST /proposals/project  ← ProposalEngine.generate_proposals_from_fragments() 호출
else:
  → POST /proposals/{sid}    ← ProposalEngine.generate_proposals() 호출
```

---

#### 핵심 문제 — SRC_E3BFC963의 실제 상황

SRC_E3BFC963는 **이전 Session에서 이미 분석 완료된 source**.  
현재 감사에서 `sem_gen.generate(source_id)`를 **수동/직접** 실행하여 SF만 재생성했다.  
그러나 그 이후 `POST /proposals/{sid}` 또는 `POST /proposals/project`는 **호출되지 않았다.**

→ proposals DB는 2026-05-03 기준 구버전 SF ID로 남아 있음.

---

## 작업 2. DB 저장 로직 확인

### save_proposals() 동작 방식

```python
# archive/manager.py L417-436
def save_proposals(self, source_id: str, proposals: list):
    with SessionLocal() as db:
        # 기존 제안 삭제 (덮어쓰기)        ← L422
        db.query(ProposalTable).filter_by(source_id=source_id).delete()
        for p in proposals:
            db.add(db_p)
        db.commit()
```

**판정:**  
`save_proposals()`는 **무조건 delete → insert** 방식.  
같은 source_id의 기존 proposal을 전부 삭제하고 새로 쓴다.  
→ 재생성 API가 호출되기만 하면 최신 SF 기준으로 갱신된다.

### 기존 proposal cache/reuse 조건

```python
# main.py L169-178 (upload 시 fingerprint hit 경우)
proposals = bams.get_proposals(source_id)
if proposals:
    _fragment_job_registry[source_id] = {
        "status": "ANALYSIS_COMPLETE",
        ...
    }
    # ← 기존 proposal이 있으면 재분석하지 않음
```

**판정:**  
업로드 시 `fingerprint hit` + 기존 proposal DB 존재 → `ANALYSIS_COMPLETE`로 즉시 반환.  
`_background_whisper`도, `generate_proposals`도 호출하지 않는다.  
→ **기존 파일을 재업로드해도 Proposal이 갱신되지 않는다.**

---

## 작업 3. API 직접 검증 명령

### SF 재생성 후 Proposal 갱신 검증

```powershell
# 1. SF 재생성 (현재 코드: Proposal 갱신 없음)
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/semantic-fragments/SRC_E3BFC963" | ConvertTo-Json

# 2. Proposal 수동 갱신
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/proposals/SRC_E3BFC963" | ConvertTo-Json

# 3. 최신 SF ID와 Proposal sequence 일치 확인
@'
import sqlite3, json

db = "ccut_backend/ccut_app.db"
con = sqlite3.connect(db)
cur = con.cursor()

print("[최신 SF ID top 5]")
rows = cur.execute("""
SELECT fragment_id, start, end, updated_at FROM semantic_fragments
WHERE source_id='SRC_E3BFC963'
ORDER BY updated_at DESC LIMIT 5
""").fetchall()
for r in rows: print(r)

print("\n[최신 Proposal sequence top 5 조각]")
row = cur.execute("""
SELECT proposal_id, created_at, sequence FROM proposals
WHERE source_id='SRC_E3BFC963'
ORDER BY created_at DESC LIMIT 1
""").fetchone()
if row:
    print("proposal:", row[0], "created:", row[1])
    seq = json.loads(row[2]) if isinstance(row[2], str) else row[2]
    for item in seq[:5]: print(" ", item.get("fragment_id"))
'@ | python
```

---

## 작업 4. 최종 보고

### 관련 코드 경로 요약

| 코드 위치 | 역할 | SF→Proposal 연결 여부 |
|----------|------|---------------------|
| `main.py L394-419` (`_background_whisper` 내) | 최초 분석 파이프라인 | ✅ SF 생성 후 즉시 Proposal 생성 |
| `main.py L1076-1103` (`POST /semantic-fragments/{sid}`) | SF 재생성 endpoint | ❌ Proposal 갱신 없음 |
| `main.py L1431-1479` (`POST /proposals/{sid}`) | Proposal 단독 재생성 | ✅ 호출 시 최신 SF로 재생성 |
| `main.py L1315-1428` (`POST /proposals/project`) | 멀티소스 Proposal 생성 | ✅ 호출 시 최신 SF로 재생성 |
| `Index.tsx L405-415` | 분석 완료 후 SF 요청 | POST /semantic-fragments → SF 갱신 |
| `Index.tsx L561-565` | 분석 완료 후 Proposal 요청 | POST /proposals/{sid} → Proposal 갱신 |
| `main.py L169-178` | 재업로드 시 캐시 판단 | ❌ proposal DB 존재 시 재분석 skip |

---

### ProposalEngine 호출 여부

| 상황 | ProposalEngine 호출 여부 |
|------|------------------------|
| 최초 분석 완료 (`_background_whisper`) | ✅ 자동 호출 |
| `POST /semantic-fragments/{sid}` | ❌ **미호출** |
| `POST /proposals/{sid}` (수동) | ✅ 호출됨 |
| `POST /proposals/project` (수동) | ✅ 호출됨 |
| 동일 파일 재업로드 (fingerprint hit + proposal 존재) | ❌ **전체 skip** |

---

### 기존 proposal 재사용 조건

```
[조건 A] 업로드 fingerprint hit + proposals DB row 존재
  → ANALYSIS_COMPLETE 즉시 반환
  → 재분석, SF 재생성, Proposal 재생성 모두 없음

[조건 B] POST /semantic-fragments/{sid} 호출
  → SF만 재생성, DB 갱신
  → Proposal은 구버전 그대로
```

---

### 최신 SF ID와 Proposal sequence ID 불일치 증거

| 항목 | 값 |
|------|-----|
| 최신 SF 생성 시간 | 2026-05-11 21:39:50 |
| 최신 SF 예시 ID | `SF_6E7779_SRC_E3BFC963` |
| Proposal 생성 시간 | 2026-05-03 13:38:00 (구버전) |
| Proposal sequence 예시 ID | `SF_9867C9_SRC_E3BFC963` |
| 불일치 여부 | **YES** — proposal이 구 SF ID를 참조 |

→ `POST /proposals/{sid}` 한 번만 호출하면 즉시 해소 가능.

---

### 원인 판정

> **원인: `POST /semantic-fragments/{source_id}` endpoint에 ProposalEngine 호출이 없다.**

- 정상 파이프라인(`_background_whisper`)에는 SF→Proposal 자동 연결이 있다.
- 그러나 SF를 **개별 재생성** 할 때는 Proposal이 연동되지 않는다.
- 이것이 버그인지 설계 의도인지는 판단 보류.
  - 버그로 본다면: SF 재생성 endpoint에서 Proposal도 재생성해야 함
  - 설계 의도로 본다면: Proposal은 명시적으로 `POST /proposals/{sid}`를 호출해야 함

---

### 수정 필요 여부

| 상황 | 수정 필요 여부 |
|------|--------------|
| SF 재귀 분할 버그 | ✅ 이미 수정됨 (STEP 1-R3) |
| SF → Proposal 미연결 | **선택적** (운영 정책에 따라) |
| 재업로드 시 재분석 skip | 설계 의도로 보임 (fingerprint cache 정책) |

---

### 최소 수정 지점 (수정 시)

**파일:** `main.py`  
**함수:** `generate_semantic_fragments()` (L1076-1103)  
**위치:** L1081 `fragments = gen.generate(source_id)` 이후

```python
# 추가할 코드 (3줄)
from engine.proposal_engine import ProposalEngine
prop_eng = ProposalEngine(bams)
prop_eng.generate_proposals(source_id)
```

**주의:** 이 수정은 SF 재생성 API 호출 때마다 Proposal도 재생성됨.  
단, `save_proposals()`가 DELETE→INSERT이므로 기존 proposal preview URL도 무효화됨.  
→ 이 수정이 Proposal Preview PASS 상태에 영향을 줄 수 있어 별도 판단 필요.

---

## 최종 판정

> ## 🔶 Proposal Refresh NOT CONNECTED

**근거:**
- `POST /semantic-fragments/{source_id}` 호출 시 Proposal이 자동 갱신되지 않는다
- SF는 최신(2026-05-11)이나 Proposal은 구버전(2026-05-03) 유지
- 수동으로 `POST /proposals/{sid}` 를 호출하면 즉시 최신 SF 기준으로 재생성됨

**즉시 해소 방법 (수정 없이):**

```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/proposals/SRC_E3BFC963"
```

또는 새 영상을 업로드하면 전체 파이프라인이 정상 실행됨.

---

## Cognitive Fragment 전체 PASS 단계 최종 요약

| 항목 | PASS 단계 |
|------|----------|
| VF 생성 파이프라인 | RUNTIME PASS |
| Evidence Board 채우기 | RUNTIME PASS |
| SF 생성 (whisper 기반) | RUNTIME PASS |
| SF 재귀 분할 버그 | ✅ 수정됨 (STEP 1-R3) |
| SF → Proposal 연결 (최초 분석) | RUNTIME PASS |
| SF 재생성 → Proposal 자동 갱신 | **NOT CONNECTED** |
| motion_score | FAIL |
| visual evidence (QwenVL) | PARTIAL |
| Browser/Product 확인 | 미검증 |
| **전체 종합** | **PARTIAL RUNTIME 유지** |
