"""실패 원장 — 지금까지 CCUT은 실패를 기억하지 못했다.

왜 만드는가: 큐원이 배열에 실패하면 arrangement_exhausted 를 돌려주고 끝이었다.
같은 실패가 어제도 났는지, 이번이 세 번째인지, 어떤 영상에서만 나는지 아무도 몰랐다.
anatomy 의 '최초 발생 · 최근 성공 · 재시도' 세 칸이 UNKNOWN 인 이유가 그것이다.

반드시 참인 것 하나: **실패를 기록하는 원장이 실패를 삼키면 안 된다.**
admin_ai_runs 를 재사용하지 않은 이유가 정확히 이것이다(fail-silent).
그래서 이 모듈에는 `except: pass` 가 하나도 없다 — 기록이 깨지면 예외로 드러낸다.
삼키는 판단은 호출부의 몫이고, 호출부도 삼키지 말고 **표시**해야 한다.

절벽:
  ① append-only — UPDATE·DELETE API 를 만들지 않는다. 잘못 적힌 것도 남기고 새 행으로 정정한다.
  ② 기록 실패는 드러낸다.
  ③ 성공은 적지 않는다 — 원장이 가벼워야 오래 산다. 성공은 결과물이 증명한다.

테이블은 도메인별 분리가 아니라 **하나(domain 컬럼)**다. 이유: 이 원장에 물어볼 질문은
'이 실패가 언제부터인가' '이 입력에서만 나는가' 처럼 도메인을 가로지른다. 표를 쪼개면
질문마다 UNION 을 쓰게 되고, 스키마가 도메인 수만큼 따로 늙는다. 1차는 rough_cut 뿐이지만
확장은 행을 늘리는 일이지 표를 늘리는 일이 아니다.
"""

import json
import os
import sqlite3
from typing import Any, Iterable, Optional

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

TABLE = "failure_ledger"

# 실측된 error_code (rough_cut 계열). 여기 없는 코드도 그대로 적는다 —
# 분류를 모른다고 사실을 버리면 원장이 아니다. 화이트리스트로 막지 않는 이유다.
KNOWN_ERROR_CODES = (
    "pass1_failed",
    "arrangement_exhausted",
    "not_shortened",
    "ungrounded_text",
    "duplicate_id",
    "weak_turn",
    "model_call_failed",
)

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    domain       TEXT    NOT NULL,
    program_id   TEXT,
    source_id    TEXT,
    input_hash   TEXT,
    phase        TEXT,
    attempt      INTEGER,
    error_code   TEXT    NOT NULL,
    detail       TEXT
)
"""

INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_domain_code ON {TABLE}(domain, error_code)",
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_program ON {TABLE}(program_id, created_at)",
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_input ON {TABLE}(input_hash)",
)


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    con = sqlite3.connect(db_path or DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_table(con: sqlite3.Connection) -> None:
    con.execute(DDL)
    for stmt in INDEXES:
        con.execute(stmt)
    con.commit()


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def record(
    domain: str,
    error_code: str,
    *,
    program_id: Optional[str] = None,
    source_id: Optional[str] = None,
    input_hash: Optional[str] = None,
    phase: Optional[str] = None,
    attempt: Optional[int] = None,
    detail: Any = None,
    db_path: Optional[str] = None,
) -> int:
    """실패 1건을 적고 rowid 를 돌려준다. 실패하면 **예외를 올린다** (삼키지 않는다)."""
    return record_many(
        [{
            "error_code": error_code,
            "program_id": program_id,
            "source_id": source_id,
            "input_hash": input_hash,
            "phase": phase,
            "attempt": attempt,
            "detail": detail,
        }],
        domain=domain,
        db_path=db_path,
    )[0]


def record_many(
    rows: Iterable[dict],
    *,
    domain: str,
    db_path: Optional[str] = None,
) -> list:
    """실패 여러 건을 한 트랜잭션으로 적는다 (재시도 1·2·3 처럼 한 사건의 여러 행).

    전부 적히거나 하나도 안 적힌다 — 절반만 남은 이력은 이력을 읽는 사람을 속인다.
    """
    items = list(rows)
    if not items:
        return []
    now = _now()
    con = connect(db_path)
    try:
        ensure_table(con)
        ids = []
        with con:
            for r in items:
                code = r.get("error_code")
                if not code:
                    raise ValueError("failure_ledger: error_code 없는 행은 적을 수 없다")
                detail = r.get("detail")
                if detail is not None and not isinstance(detail, str):
                    detail = json.dumps(detail, ensure_ascii=False, default=str)
                cur = con.execute(
                    f"INSERT INTO {TABLE} "
                    "(created_at, domain, program_id, source_id, input_hash, phase, attempt, error_code, detail) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        r.get("created_at") or now,
                        domain,
                        r.get("program_id"),
                        r.get("source_id"),
                        r.get("input_hash"),
                        r.get("phase"),
                        r.get("attempt"),
                        str(code),
                        detail,
                    ),
                )
                ids.append(cur.lastrowid)
        return ids
    finally:
        con.close()


def record_rough_cut_failure(
    program_id: str,
    result: Any,
    *,
    input_hash: Optional[str] = None,
    source_ids: Optional[Iterable[str]] = None,
    db_path: Optional[str] = None,
) -> list:
    """RoughCutBuildResult(실패) 하나를 원장 행들로 편다.

    한 사건이 여러 행이 되는 이유: 하드캡 3 안의 재시도 하나하나가 사실이다.
    '3번 만에 실패'와 '1번 만에 실패'는 다른 사건인데, 뭉치면 그 차이가 사라진다.
    성공한 시도(rejection 없음·adapter ok)는 적지 않는다 — 절벽 ④.
    """
    if getattr(result, "ok", False):
        raise ValueError("failure_ledger: 성공한 결과는 적지 않는다 (절벽 ④)")

    sid = None
    for s in (source_ids or []):
        sid = s
        break

    status = getattr(getattr(result, "status", None), "value", None) or str(getattr(result, "status", ""))
    rows = []
    for att in (getattr(result, "attempts", ()) or ()):
        codes = list(getattr(att, "rejection_codes", ()) or ())
        adapter_status = getattr(att, "adapter_status", None)
        err = getattr(att, "error_message", None)
        if not codes:
            # 검증 거절이 아니라 어댑터/모델 쪽에서 끝난 시도.
            if adapter_status and adapter_status != "ok":
                codes = ["model_call_failed"]
            elif err:
                codes = ["model_call_failed"]
            else:
                continue    # 통과한 시도 — 성공은 적지 않는다
        for code in codes:
            rows.append({
                "error_code": code,
                "program_id": program_id,
                "source_id": sid,
                "input_hash": input_hash,
                "phase": getattr(att, "stage", None),
                "attempt": getattr(att, "attempt", None),
                "detail": {
                    "build_status": status,
                    "adapter_status": adapter_status,
                    "latency_ms": getattr(att, "latency_ms", None),
                    "error_message": err,
                    "build_error_message": getattr(result, "error_message", None),
                },
            })

    if not rows:
        # 시도 기록이 없는 실패(예: 입력 부족으로 모델을 부르기도 전에 끝남)도 사실이다.
        rows.append({
            "error_code": status or "unknown_failure",
            "program_id": program_id,
            "source_id": sid,
            "input_hash": input_hash,
            "phase": "build",
            "attempt": None,
            "detail": {
                "build_status": status,
                "build_error_message": getattr(result, "error_message", None),
                "note": "attempts 없음",
            },
        })

    return record_many(rows, domain="rough_cut", db_path=db_path)
