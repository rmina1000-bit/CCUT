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
                    SUM(CASE WHEN verdict='pass' THEN 1 ELSE 0 END) AS pass_count,
                    SUM(CASE WHEN verdict='correction' THEN 1 ELSE 0 END) AS correction_count,
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
            f"""SELECT verdict, verdict_basis
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
    ledger_total = int((summary or {}).get("ledger_total_count") or total_count)
    omitted_count = int((summary or {}).get("omitted_count") or 0)
    summary_limit = int((summary or {}).get("summary_event_limit") or DEFAULT_SUMMARY_EVENT_LIMIT)
    return (
        "[수첩 요약] mirror_ledger "
        f"project_id={(summary or {}).get('project_id')} "
        f"ledger_total={ledger_total} "
        f"total={total_count} "
        f"omitted={omitted_count} "
        f"summary_limit={summary_limit} "
        f"pass={(summary or {}).get('pass_count', 0)} "
        f"correction={(summary or {}).get('correction_count', 0)} "
        f"accept={(summary or {}).get('accept_count', 0)} "
        f"undo={(summary or {}).get('undo_count', 0)} "
        f"edit_again={(summary or {}).get('edit_again_count', 0)} "
        f"continue={(summary or {}).get('continue_count', 0)} "
        f"pass_rate={(summary or {}).get('pass_rate', 0.0):.3f} "
        f"correction_rate={(summary or {}).get('correction_rate', 0.0):.3f} "
        f"undo_rate={(summary or {}).get('undo_rate', 0.0):.3f} "
        f"recent_verdicts={recent}"
    )


@router.post("/mirror/events")
async def post_mirror_event(payload: MirrorEventPayload):
    try:
        return append_event(payload)
    except MirrorLedgerError as e:
        return JSONResponse(status_code=e.http_status, content={"ok": False, "error": e.code, "message": e.message})
