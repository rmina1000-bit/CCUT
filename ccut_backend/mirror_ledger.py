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


@router.post("/mirror/events")
async def post_mirror_event(payload: MirrorEventPayload):
    try:
        return append_event(payload)
    except MirrorLedgerError as e:
        return JSONResponse(status_code=e.http_status, content={"ok": False, "error": e.code, "message": e.message})
