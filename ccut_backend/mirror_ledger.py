# -*- coding: utf-8 -*-
import datetime
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")
TABLE = "mirror_ledger"
DEFAULT_SUMMARY_EVENT_LIMIT = 10
MAX_SUMMARY_EVENT_LIMIT = 100
MS_PER_DAY = 24 * 60 * 60 * 1000

ALLOWED_EVENT_KINDS = {"accept", "undo", "edit_again", "continue"}
ALLOWED_VERDICTS = {"pass", "correction"}
ALLOWED_BASES = {"accept", "undo", "edit_again", "continue", "elapsed_time_threshold"}

# ══════════════════════════════════════════════════════════════════════════
#  [MIRROR-FIX-1 2026-07-26] 시계는 사용자 행동이 아니다.
#    국장 원칙(2026-07-22): "거울은 사용자 행동. 엔진이 사실만 기록. 큐원은 읽기만."
#    실사고: proj_f6be58f81e4f 의 수첩 1행이
#      {event_kind:continue, verdict:correction, basis:elapsed_time_threshold,
#       elapsed_ms:5512732(=1시간 32분)}
#    이었고 그 1행이 correction_rate=1.000 으로 매 발화 프롬프트에 주입됐다.
#    사용자가 무엇을 고친 것이 아니라 자리를 비운 것이다.
#
#    원인(프론트 mirrorEventLog.ts:143-167 verdictFor):
#      :145 undo/edit_again        -> correction   (사용자 행동)
#      :152 elapsed >= 10분        -> correction   ★시계 — 아래 분기보다 먼저 온다
#      :159 accept/continue        -> pass         (사용자 행동)
#    시계 분기가 사용자 행동 분기를 **선점**해서, 10분 넘겨 누른 승인(accept)·
#    이어가기(continue)가 전부 "교정"으로 기록됐다. 실측 4/4 건이 이 형상이다.
#
#    ★판정 주체가 프론트라 근본 수리는 프론트지만 이번 차수 수정 금지 파일이다.
#      엔진 경계에서 막는다 — 사실(elapsed_ms)은 그대로 남기고 해석만 바로잡는다.
#    ★새 verdict 값(neutral/none)은 물리적으로 불가능하다. 실제 스키마가
#      verdict TEXT NOT NULL CHECK(verdict IN ('pass','correction')) 이라
#      제3의 값은 테이블 재생성을 요구한다(INV-5 위반). 그래서 새 값을 만들지 않고,
#      시계 분기를 걷어냈을 때 저 코드가 **원래 주었을 값**으로 환산한다.
# ══════════════════════════════════════════════════════════════════════════
CLOCK_BASES = {"elapsed_time_threshold"}


def normalize_verdict(event_kind, verdict, verdict_basis):
    """시계가 찍은 판정을 사용자 행동 기준으로 환산. 반환 (verdict, basis, changed).

    ★시계 근거가 아니면 손대지 않는다. 판정 불가한 event_kind 도 손대지 않는다(INV-3).
    """
    if verdict_basis not in CLOCK_BASES:
        return verdict, verdict_basis, False
    if event_kind in ("undo", "edit_again"):
        return "correction", event_kind, True      # mirrorEventLog.ts:145-150
    if event_kind in ("accept", "continue"):
        return "pass", event_kind, True            # mirrorEventLog.ts:159-164
    return verdict, verdict_basis, False


# 읽기 집계용 SQL — 저장된 행은 건드리지 않고(INV-2) 집계 순간에만 환산한다.
_EFFECTIVE_VERDICT_SQL = (
    "CASE WHEN verdict_basis='elapsed_time_threshold' THEN "
    " CASE WHEN event_kind IN ('accept','continue') THEN 'pass' "
    "      WHEN event_kind IN ('undo','edit_again') THEN 'correction' "
    "      ELSE verdict END "
    "ELSE verdict END"
)
_EFFECTIVE_BASIS_SQL = (
    "CASE WHEN verdict_basis='elapsed_time_threshold' "
    " AND event_kind IN ('accept','continue','undo','edit_again') "
    "THEN event_kind ELSE verdict_basis END"
)

DDL_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    mirror_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK(event_kind IN ('accept','undo','edit_again','continue')),
    verdict TEXT NOT NULL CHECK(verdict IN ('pass','correction')),
    verdict_basis TEXT NOT NULL CHECK(verdict_basis IN ('accept','undo','edit_again','continue','elapsed_time_threshold')),
    elapsed_ms INTEGER,
    ts INTEGER NOT NULL,
    at TEXT NOT NULL,
    proposal_id TEXT,
    fragment_id TEXT,
    timeline_item_id TEXT,
    verdict_for_pending_id TEXT,
    created_at TEXT NOT NULL
)
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_mirror_ledger_project_ts ON {TABLE}(project_id, ts)",
    f"CREATE INDEX IF NOT EXISTS idx_mirror_ledger_verdict ON {TABLE}(verdict)",
]

router = APIRouter()


class MirrorEventPayload(BaseModel):
    project_id: str
    event_kind: str
    verdict: str
    verdict_basis: str
    elapsed_ms: Optional[int] = None
    ts: int
    at: str
    proposal_id: Optional[str] = None
    fragment_id: Optional[str] = None
    timeline_item_id: Optional[str] = None
    verdict_for_pending_id: Optional[str] = None


class MirrorLedgerError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_schema(con=None):
    owns = con is None
    con = con or _connect()
    try:
        con.execute(DDL_SQL)
        for sql in INDEX_SQL:
            con.execute(sql)
        con.commit()
    finally:
        if owns:
            con.close()


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate(payload: MirrorEventPayload):
    project_id = _clean_text(payload.project_id)
    event_kind = _clean_text(payload.event_kind)
    verdict = _clean_text(payload.verdict)
    verdict_basis = _clean_text(payload.verdict_basis)
    at = _clean_text(payload.at)

    if not project_id:
        raise MirrorLedgerError("missing_required", "project_id required")
    if event_kind not in ALLOWED_EVENT_KINDS:
        raise MirrorLedgerError("format_violation", f"event_kind not allowed: {event_kind!r}")
    if verdict not in ALLOWED_VERDICTS:
        raise MirrorLedgerError("format_violation", f"verdict not allowed: {verdict!r}")
    if verdict_basis not in ALLOWED_BASES:
        raise MirrorLedgerError("format_violation", f"verdict_basis not allowed: {verdict_basis!r}")
    if not isinstance(payload.ts, int) or isinstance(payload.ts, bool) or payload.ts < 0:
        raise MirrorLedgerError("format_violation", f"ts must be non-negative integer: {payload.ts!r}")
    if not at:
        raise MirrorLedgerError("missing_required", "at required")
    if payload.elapsed_ms is not None:
        if not isinstance(payload.elapsed_ms, int) or isinstance(payload.elapsed_ms, bool) or payload.elapsed_ms < 0:
            raise MirrorLedgerError("format_violation", f"elapsed_ms must be non-negative integer: {payload.elapsed_ms!r}")

    # [MIRROR-FIX-1] 쓰기 경계 — 시계가 찍은 판정은 들이지 않는다.
    #   ★이벤트를 버리는 것이 아니다. 사실(event_kind·elapsed_ms·ts)은 전부 그대로 저장하고
    #    해석(verdict)만 사용자 행동 기준으로 바로잡는다. 조용히 바꾸지 않는다 — raw 로 남긴다.
    _v, _b, _changed = normalize_verdict(event_kind, verdict, verdict_basis)
    if _changed:
        print(f"[MIRROR-FIX-1][쓰기환산] project_id={project_id} event_kind={event_kind} "
              f"{verdict}:{verdict_basis} -> {_v}:{_b} elapsed_ms={payload.elapsed_ms} "
              f"(시계는 사용자 행동이 아니다)")
        verdict, verdict_basis = _v, _b

    return {
        "project_id": project_id,
        "event_kind": event_kind,
        "verdict": verdict,
        "verdict_basis": verdict_basis,
        "elapsed_ms": payload.elapsed_ms,
        "ts": payload.ts,
        "at": at,
        "proposal_id": _clean_text(payload.proposal_id),
        "fragment_id": _clean_text(payload.fragment_id),
        "timeline_item_id": _clean_text(payload.timeline_item_id),
        "verdict_for_pending_id": _clean_text(payload.verdict_for_pending_id),
    }


def append_event(payload: MirrorEventPayload):
    row = _validate(payload)
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    con = _connect()
    try:
        ensure_schema(con)
        cur = con.execute(
            f"""INSERT INTO {TABLE}
               (project_id, event_kind, verdict, verdict_basis, elapsed_ms, ts, at,
                proposal_id, fragment_id, timeline_item_id, verdict_for_pending_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["project_id"],
                row["event_kind"],
                row["verdict"],
                row["verdict_basis"],
                row["elapsed_ms"],
                row["ts"],
                row["at"],
                row["proposal_id"],
                row["fragment_id"],
                row["timeline_item_id"],
                row["verdict_for_pending_id"],
                created_at,
            ),
        )
        con.commit()
        return {"ok": True, "mirror_event_id": cur.lastrowid}
    finally:
        con.close()


def _empty_summary(project_id: Optional[str]):
    return {
        "project_id": project_id or None,
        "ledger_total_count": 0,
        "total_count": 0,
        "omitted_count": 0,
        "summary_event_limit": DEFAULT_SUMMARY_EVENT_LIMIT,
        "summary_window_days": 0,
        "summary_since_ts": None,
        "pass_count": 0,
        "correction_count": 0,
        "accept_count": 0,
        "undo_count": 0,
        "edit_again_count": 0,
        "continue_count": 0,
        "pass_rate": 0.0,
        "correction_rate": 0.0,
        "undo_rate": 0.0,
        "recent_verdicts": [],
    }


def _connect_readonly():
    con = sqlite3.connect("file:" + DB_PATH.replace("\\", "/") + "?mode=ro",
                          uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _bounded_int(value, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(number, high))


def _summary_event_limit(max_events=None) -> int:
    if max_events is None:
        max_events = os.getenv("CCUT_MIRROR_SUMMARY_MAX_EVENTS")
    return _bounded_int(max_events, DEFAULT_SUMMARY_EVENT_LIMIT, 1, MAX_SUMMARY_EVENT_LIMIT)


def _summary_window_days(window_days=None) -> int:
    if window_days is None:
        window_days = os.getenv("CCUT_MIRROR_SUMMARY_WINDOW_DAYS")
    return _bounded_int(window_days, 0, 0, 3650)


def summarize_project(project_id: str, recent_limit: int = 5, max_events=None,
                      window_days=None, now_ms=None):
    project_id = _clean_text(project_id)
    if not project_id:
        return _empty_summary(None)
    recent_limit = max(0, min(int(recent_limit or 0), 10))
    event_limit = _summary_event_limit(max_events)
    window_days = _summary_window_days(window_days)
    since_ts = None
    if window_days > 0:
        now_value = _bounded_int(
            now_ms,
            int(datetime.datetime.now().timestamp() * 1000),
            0,
            9999999999999,
        )
        since_ts = max(0, now_value - (window_days * MS_PER_DAY))
    con = None
    try:
        con = _connect_readonly()
        ledger_total_count = int(con.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE project_id=?",
            (project_id,),
        ).fetchone()[0] or 0)
        where_sql = "WHERE project_id=?"
        params = [project_id]
        if since_ts is not None:
            where_sql += " AND ts>=?"
            params.append(since_ts)
        scoped_sql = (
            f"SELECT * FROM {TABLE} {where_sql} "
            "ORDER BY ts DESC, mirror_event_id DESC LIMIT ?"
        )
        scoped_params = [*params, event_limit]
        row = con.execute(
            f"""SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN ({_EFFECTIVE_VERDICT_SQL})='pass' THEN 1 ELSE 0 END) AS pass_count,
                    SUM(CASE WHEN ({_EFFECTIVE_VERDICT_SQL})='correction' THEN 1 ELSE 0 END) AS correction_count,
                    SUM(CASE WHEN event_kind='accept' THEN 1 ELSE 0 END) AS accept_count,
                    SUM(CASE WHEN event_kind='undo' THEN 1 ELSE 0 END) AS undo_count,
                    SUM(CASE WHEN event_kind='edit_again' THEN 1 ELSE 0 END) AS edit_again_count,
                    SUM(CASE WHEN event_kind='continue' THEN 1 ELSE 0 END) AS continue_count
                FROM ({scoped_sql})""",
            scoped_params,
        ).fetchone()
        total_count = int((row or {})["total_count"] or 0)
        pass_count = int((row or {})["pass_count"] or 0)
        correction_count = int((row or {})["correction_count"] or 0)
        undo_count = int((row or {})["undo_count"] or 0)
        recent_rows = con.execute(
            f"""SELECT ({_EFFECTIVE_VERDICT_SQL}) AS verdict,
                       ({_EFFECTIVE_BASIS_SQL}) AS verdict_basis
                FROM ({scoped_sql})
                ORDER BY ts DESC, mirror_event_id DESC
                LIMIT ?""",
            [*scoped_params, recent_limit],
        ).fetchall() if recent_limit else []
        return {
            "project_id": project_id,
            "ledger_total_count": ledger_total_count,
            "total_count": total_count,
            "omitted_count": max(0, ledger_total_count - total_count),
            "summary_event_limit": event_limit,
            "summary_window_days": window_days,
            "summary_since_ts": since_ts,
            "pass_count": pass_count,
            "correction_count": correction_count,
            "accept_count": int((row or {})["accept_count"] or 0),
            "undo_count": undo_count,
            "edit_again_count": int((row or {})["edit_again_count"] or 0),
            "continue_count": int((row or {})["continue_count"] or 0),
            "pass_rate": round(pass_count / total_count, 3) if total_count else 0.0,
            "correction_rate": round(correction_count / total_count, 3) if total_count else 0.0,
            "undo_rate": round(undo_count / total_count, 3) if total_count else 0.0,
            "recent_verdicts": [
                f"{str(r['verdict'])}:{str(r['verdict_basis'])}"
                for r in recent_rows
            ],
        }
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        return _empty_summary(project_id)
    finally:
        if con is not None:
            con.close()


def format_summary_fact_line(summary):
    total_count = int((summary or {}).get("total_count") or 0)
    if total_count <= 0:
        return ""
    recent = ",".join((summary or {}).get("recent_verdicts") or []) or "none"
    # [MIRROR-FIX-1 R4(2)] 큐원이 쓸 수 없는 필드를 뺀다.
    #   기준(지시서 R3-3): "큐원이 그 값으로 실제로 다르게 행동할 수 있는 것만 남긴다."
    #   ★R2(4) 실측: 프롬프트 어디에도 큐원에게 수첩으로 무엇을 하라는 지시가 없다.
    #    유일한 언급이 "[수첩 요약]은 pass/correction 집계값으로만 읽어라"(읽는 법)뿐이라
    #    엄밀히는 전 필드가 뺄 후보다. 수첩 기능 폐지는 이번 범위가 아니므로
    #    사용자 행동 집계만 남기고 DB 내부 지표는 전부 뺀다.
    #   뺀 것 — project_id(내부 식별자) / ledger_total·omitted·summary_limit(페이징 내부값)
    #           / accept·undo·edit_again·continue(pass·correction 과 중복)
    #           / pass_rate·undo_rate(total·pass·correction 에서 파생)
    #   ★해석문으로 바꾸지 않는다 — key=value 데이터 형식 그대로 유지한다.
    return (
        "[수첩 요약] "
        f"total={total_count} "
        f"pass={(summary or {}).get('pass_count', 0)} "
        f"correction={(summary or {}).get('correction_count', 0)} "
        f"correction_rate={(summary or {}).get('correction_rate', 0.0):.3f} "
        f"recent_verdicts={recent}"
    )


@router.post("/mirror/events")
async def post_mirror_event(payload: MirrorEventPayload):
    try:
        return append_event(payload)
    except MirrorLedgerError as e:
        return JSONResponse(status_code=e.http_status, content={"ok": False, "error": e.code, "message": e.message})
