"""[ADMIN-AI-UNMUZZLE 2026-08-02] 관제실 AI 의 손 — 읽기 도구.

왜 만드는가(국장 지시 원문): "오히려 다 풀어줘. 모든 재갈을 풀어."
  재갈을 풀어도 손이 없으면 AI 는 국장에게 심부름을 시킨다 —
  "운영자님이 폴더에서 확인해서 알려주시면 판단해드릴게요".
  국장은 실행자가 아니다. 그러니 AI 가 직접 본다.

★ 재갈과 게이트를 가른다.
  재갈  = "생각하지 마라 / 보지 마라"      → 이 파일에 없다.
  게이트 = "되돌릴 수 없는 행위는 막는다"  → 아래 세 가지만.
     ① db_query 는 읽기 전용 연결(mode=ro)로 연다 — OS 수준 차단이다.
       SQL 문자열 검사는 그 위에 얹는 2차 방어일 뿐, 진짜 방어는 연결 모드다.
     ② read_file 은 D:\\CCUT1.0.4 밖으로 못 나간다 (realpath 로 정규화 후 대조).
     ③ 자격증명 파일(.env, *key*.pem 등)은 읽지 않는다 — 유출은 되돌릴 수 없다.
       ★ 이 하나는 국장 판단 대기 항목이다. 지시서 "읽는 범위에 제한을 두지 말 것"과
         부딪히지만, API 키가 대화 응답에 실려 나가면 회수가 불가능하다.

읽는 범위 자체에는 제한을 두지 않는다 — 어느 테이블이든, 어느 소스 파일이든 본다.
크기 상한은 있으나 그것은 '전송 단위'다: 잘렸으면 반드시 잘렸다고 알리고
다음 조각을 어떻게 가져오는지(LIMIT/OFFSET·offset)를 함께 돌려준다.
조용히 자르지 않는다.
"""

import json
import os
import re
import sqlite3

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.join(ROOT, "ccut_backend")
DB_PATH = os.path.join(BACKEND, "ccut_app.db")
LOG_DIR = os.path.join(BACKEND, "logs")

# 전송 단위 상한 — 재갈이 아니다. 넘치면 잘렸다고 말하고 이어받는 법을 알려준다.
MAX_RESULT_CHARS = 60000
MAX_ROWS = 500
MAX_FILE_CHARS = 60000
MAX_LOG_LINES = 400

# [게이트 ③] 자격증명 — 읽으면 응답에 실려 나가고 회수할 수 없다.
_SECRET_PAT = re.compile(
    r"(^|[\\/])(\.env(\..*)?$|.*secret.*|.*credential.*)|"
    r"\.(pem|key|pfx|p12|keystore)$", re.IGNORECASE)

# [게이트 ①-2차] 읽기 전용 연결을 뚫으려는 시도를 미리 거른다.
_WRITE_PAT = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|"
    r"ATTACH|DETACH|VACUUM|REINDEX|PRAGMA|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE)


# ── 도구 선언 (Anthropic tool use 스키마) ────────────────────────────────
TOOL_DEFS = [
    {
        "name": "db_query",
        "description": (
            "CCUT 운영 DB(ccut_app.db)에 SELECT 를 실행하고 행을 돌려준다. "
            "어느 테이블이든 조회할 수 있다. 스키마를 모르면 먼저 "
            "\"SELECT name, sql FROM sqlite_master WHERE type='table'\" 로 확인하라. "
            "읽기 전용이라 데이터를 바꾸는 문장은 거부된다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "실행할 SELECT 또는 WITH 문 (한 문장)"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "read_log",
        "description": (
            "백엔드 로그 파일을 읽는다. pattern 을 주면 그 문자열이 든 줄만, "
            "없으면 마지막 lines 줄을 돌려준다. file 을 비우면 backend.log 를 읽고, "
            "어떤 로그가 있는지 모르면 list=true 로 목록을 먼저 받아라."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "logs/ 안의 파일명 (기본 backend.log)"},
                "pattern": {"type": "string", "description": "찾을 문자열 (대소문자 무시)"},
                "lines": {"type": "integer", "description": "돌려받을 줄 수 (기본 120)"},
                "list": {"type": "boolean", "description": "true 면 로그 파일 목록만 반환"},
            },
        },
    },
    {
        "name": "read_file",
        "description": (
            "프로젝트(D:\\CCUT1.0.4) 안의 파일을 읽는다. 소스 코드·설정·문서 전부 읽을 수 있다. "
            "경로는 프로젝트 기준 상대경로로 준다 (예: ccut_backend/main.py). "
            "파일이 길면 offset 으로 이어 읽는다. 디렉터리를 주면 그 안의 목록을 돌려준다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "프로젝트 기준 상대경로"},
                "offset": {"type": "integer", "description": "읽기 시작 문자 위치 (기본 0)"},
            },
            "required": ["path"],
        },
    },
]


# ── 구현 ────────────────────────────────────────────────────────────────
def _truncate(text, limit, hint):
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n\n[잘림] {len(text)}자 중 {limit}자만 보냈다. {hint}", True


def db_query(sql: str = "", **_):
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return {"error": "sql 이 비었다."}
    # 여러 문장을 한 번에 넣어 검사를 우회하는 경로를 막는다.
    if ";" in sql:
        return {"error": "한 번에 한 문장만 실행한다. 세미콜론으로 여러 문장을 넣을 수 없다."}
    head = sql.lstrip("( \t\r\n")[:6].upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        return {"error": f"SELECT/WITH 만 실행한다. 받은 문장 시작: {sql[:40]!r}"}
    m = _WRITE_PAT.search(sql)
    if m:
        return {"error": f"쓰기·구조변경 키워드가 들어 있어 거부한다: {m.group(0).upper()}"}
    try:
        # [게이트 ①] 진짜 방어 — 읽기 전용으로 연다. 쓰기는 OS 가 막는다.
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1)
        cols = [d[0] for d in (cur.description or [])]
        con.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    more = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    out = {
        "columns": cols,
        "row_count": len(rows),
        "rows": [dict(r) for r in rows],
    }
    if more:
        out["truncated"] = (
            f"{MAX_ROWS}행까지만 보냈다. 더 보려면 LIMIT/OFFSET 을 붙여 다시 물어라.")
    text = json.dumps(out, ensure_ascii=False, default=str)
    text, cut = _truncate(text, MAX_RESULT_CHARS,
                          "컬럼을 좁히거나 LIMIT 을 걸어 다시 물어라.")
    return text if cut else out


def read_log(file: str = "", pattern: str = "", lines: int = 120,
             list: bool = False, **_):
    try:
        names = sorted(os.listdir(LOG_DIR))
    except Exception as e:
        return {"error": f"로그 디렉터리를 못 읽는다: {e}"}
    if list:
        return {"log_dir": "ccut_backend/logs", "files": names[:200]}
    name = (file or "backend.log").strip()
    if "/" in name or "\\" in name or name.startswith(".."):
        return {"error": "logs/ 안의 파일명만 준다."}
    path = os.path.join(LOG_DIR, name)
    if not os.path.isfile(path):
        return {"error": f"{name} 이 없다. 있는 파일: {names[:40]}"}
    n = max(1, min(int(lines or 120), MAX_LOG_LINES))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if pattern:
        low = pattern.lower()
        hit = [f"{i+1}: {ln.rstrip()}" for i, ln in enumerate(all_lines)
               if low in ln.lower()]
        total = len(hit)
        picked = hit[-n:]
        body = "\n".join(picked) or "NO ROW — 그 문자열이 든 줄이 없다."
        res = {"file": name, "pattern": pattern, "match_count": total,
               "showing": len(picked), "lines": body}
    else:
        picked = [f"{len(all_lines)-len(all_lines[-n:])+i+1}: {ln.rstrip()}"
                  for i, ln in enumerate(all_lines[-n:])]
        res = {"file": name, "total_lines": len(all_lines),
               "showing_last": len(picked), "lines": "\n".join(picked)}
    text = json.dumps(res, ensure_ascii=False)
    text, cut = _truncate(text, MAX_RESULT_CHARS, "lines 를 줄이거나 pattern 을 좁혀라.")
    return text if cut else res


def read_file(path: str = "", offset: int = 0, **_):
    rel = (path or "").strip().replace("\\", "/")
    if not rel:
        return {"error": "path 가 비었다."}
    target = os.path.realpath(os.path.join(ROOT, rel))
    root = os.path.realpath(ROOT)
    # [게이트 ②] 프로젝트 밖으로 못 나간다.
    if not (target == root or target.startswith(root + os.sep)):
        return {"error": f"프로젝트({ROOT}) 밖은 읽지 않는다."}
    # [게이트 ③] 자격증명은 읽지 않는다 — 응답에 실리면 회수가 안 된다.
    if _SECRET_PAT.search(target):
        return {"error": "자격증명 파일은 읽지 않는다(키 유출은 되돌릴 수 없다). "
                         "값이 필요하면 국장에게 직접 확인을 요청하라."}
    if os.path.isdir(target):
        try:
            entries = []
            for nm in sorted(os.listdir(target))[:300]:
                p = os.path.join(target, nm)
                entries.append(f"{nm}/" if os.path.isdir(p)
                               else f"{nm} ({os.path.getsize(p)}B)")
            return {"dir": rel, "entries": entries}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
    if not os.path.isfile(target):
        return {"error": f"{rel} 이 없다."}
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    off = max(0, int(offset or 0))
    chunk = content[off:off + MAX_FILE_CHARS]
    res = {"path": rel, "total_chars": len(content), "offset": off,
           "content": chunk}
    if off + len(chunk) < len(content):
        res["truncated"] = (f"{off + len(chunk)}자까지 보냈다. 이어 보려면 "
                            f"offset={off + len(chunk)} 로 다시 불러라.")
    return res


REGISTRY = {"db_query": db_query, "read_log": read_log, "read_file": read_file}


def failure_note(out: str) -> str:
    """[QWEN-02 STEP 1-3] 도구 결과의 '실패·빈결과'를 말로 붙여준다. 문구 단일 출처.

    왜 여기 두는가: 같은 문구가 hub 와 여기 둘로 갈리면 언젠가 다르게 판정한다.
    누가 쓰는가(실측으로 갈렸다):
      · 큐원(qwen2.5:7b) — 필요하다. 표지가 없으면 error 를 받고도 재조회하지 않고
        조각 id·전사를 통째로 날조했다(3/3, 2026-08-02). 표지를 붙이자 3/3 정답.
      · 관제실(claude-fable-5) — 필요 없다. 표지가 없는 상태에서도
        "no such table 오류가 났고" 라고 정확히 말하고 스스로 4회 더 조회했다(3/3).
        그래서 관제실 경로에는 붙이지 않는다 — 모델 차이지 표지 부재가 아니다.
    반환: 붙일 말(없으면 빈 문자열).
    """
    s = (out or "").lstrip()
    if s.startswith('{"error"'):
        return ("\n[이 조회는 실패했다. 위 오류를 읽고 테이블·컬럼 이름을 고쳐 "
                "다시 조회하라. 결과를 지어내지 마라.]")
    if '"row_count": 0' in out or "NO ROW" in out:
        return ("\n[결과가 0건이다. 다른 테이블이나 컬럼에 있을 수 있으니 "
                "한 번 더 조회해 보라. 0건이라고 단정하지 마라.]")
    return ""


def ollama_tool_defs(names=None):
    """[QWEN-01 STEP 1-3] 같은 도구를 Ollama(/api/chat) 형식으로 내준다.

    관제실(Anthropic)은 input_schema, Ollama 는 function.parameters 를 쓴다 —
    이름·설명·스키마는 하나를 공유하고 껍데기만 바꾼다. 도구를 두 벌 만들지 않는다.
    ★ 스키마는 평평하게 유지한다($defs·$ref 중첩 금지 — llama.cpp #8444).
    """
    picked = [t for t in TOOL_DEFS if names is None or t["name"] in names]
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    } for t in picked]


def run(name: str, args: dict) -> str:
    """도구 하나를 실행하고 문자열로 돌려준다. 실패도 감추지 않고 그대로 돌려준다."""
    fn = REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"모르는 도구: {name}"}, ensure_ascii=False)
    try:
        out = fn(**(args or {}))
    except Exception as e:
        out = {"error": f"{type(e).__name__}: {e}"}
    return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
