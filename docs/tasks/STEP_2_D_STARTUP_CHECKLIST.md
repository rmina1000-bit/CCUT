# STEP 2-D Startup Checklist

새 방/새 작업 시작 시 아래 순서로 확인한다.

## 1. Git 상태

```powershell
cd D:\CCUT1.0.4

git status --short
git rev-parse HEAD
git diff --stat
```

## 2. Python compile
```powershell
python -m py_compile ccut_backend/engine/proposal_engine.py
python -m py_compile ccut_backend/engine/semantic_engine.py
python -m py_compile ccut_backend/ai/adapters/qwen3_asr_adapter.py
```

## 3. 서버 상태
```powershell
curl.exe http://127.0.0.1:8000/health
```

## 4. 최신 source 확인
```powershell
@'
import sqlite3
con = sqlite3.connect("ccut_backend/ccut_app.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
rows = cur.execute("""
SELECT source_id, title, duration, created_at
FROM sources
ORDER BY created_at DESC
LIMIT 5
""").fetchall()
for r in rows:
    print(dict(r))
con.close()
'@ | python
```

## 5. 최신 Proposal 확인
```powershell
@'
import sqlite3, json
con = sqlite3.connect("ccut_backend/ccut_app.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

sid = cur.execute("""
SELECT source_id FROM sources ORDER BY created_at DESC LIMIT 1
""").fetchone()["source_id"]

print("source:", sid)

rows = cur.execute("""
SELECT proposal_id, mode, sequence, duration, created_at
FROM proposals
WHERE source_id=?
ORDER BY created_at DESC
LIMIT 4
""", (sid,)).fetchall()

for r in rows:
    d = dict(r)
    seq = json.loads(d["sequence"]) if d["sequence"] else []
    print({
        "proposal_id": d["proposal_id"],
        "mode": d["mode"],
        "count": len(seq),
        "duration": d["duration"],
        "first_ids": [x.get("fragment_id") for x in seq[:5]]
    })

con.close()
'@ | python
```

## 6. Semantic Fragment Boundary 확인
```powershell
@'
import sqlite3, json
con = sqlite3.connect("ccut_backend/ccut_app.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

sid = cur.execute("""
SELECT source_id FROM sources ORDER BY created_at DESC LIMIT 1
""").fetchone()["source_id"]

print("source:", sid)

rows = cur.execute("""
SELECT id, start, end, semantic_json, structural_json
FROM semantic_fragments
WHERE source_id=?
ORDER BY start ASC
LIMIT 20
""", (sid,)).fetchall()

for r in rows:
    sem = json.loads(r["semantic_json"]) if r["semantic_json"] else {}
    st = json.loads(r["structural_json"]) if r["structural_json"] else {}
    print({
        "id": r["id"],
        "start": r["start"],
        "end": r["end"],
        "duration": st.get("duration"),
        "summary": (sem.get("summary") or "")[:80],
        "refs": sem.get("evidence_refs"),
    })

con.close()
'@ | python
```

## 시작 판정
- working tree dirty면 먼저 정리
- proposal_engine.py 미커밋이면 R4 상태 확인
- semantic boundary 수정 전에는 반드시 감사 보고서 작성
- 브라우저 체감만으로 PASS 금지
