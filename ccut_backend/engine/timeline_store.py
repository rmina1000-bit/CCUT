# -*- coding: utf-8 -*-
"""[TIMELINE] 중앙창 영속 타임라인 — append-only 이벤트 로그 (상용 채팅 동형).

행 하나 = 사건 하나(message | generation). 과거 행은 불변 — 역사 파괴가 구조적으로
불가능하다. client_id 멱등(중복 전송 안전, 멀티탭 안전), entry_id 단조증가 =
시간순 보장 + 커서 페이지네이션. 기존 chat_state blob(v1)은 첫 조회 때 행으로
자동 이관(lazy migration) 후 비운다.
"""
import datetime
import json
import os
import sqlite3

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

_KINDS = ("message", "generation")


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS project_timeline (
        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
        program_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        client_id TEXT NOT NULL,
        ts REAL NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_timeline_prog "
                "ON project_timeline(program_id, entry_id)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_timeline_client "
                "ON project_timeline(program_id, client_id)")
    con.commit()


def append_entries(program_id, entries):
    """멱등 벌크 append — client_id 중복은 skip(이미 기록된 사건). 추가 수 반환."""
    con = _connect()
    ensure_schema(con)
    now = datetime.datetime.now().isoformat()
    added = 0
    for e in entries or []:
        kind, cid = e.get("kind"), e.get("client_id")
        if kind not in _KINDS or not cid:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO project_timeline "
            "(program_id, kind, client_id, ts, payload, created_at) VALUES (?,?,?,?,?,?)",
            (program_id, kind, str(cid), float(e.get("ts") or 0),
             json.dumps(e.get("payload"), ensure_ascii=False), now))
        added += cur.rowcount
    con.commit()
    con.close()
    return added


def fetch(program_id, limit=300, before=None):
    """최근 limit개를 시간순으로. before(entry_id) 커서로 더 과거 페이지."""
    con = _connect()
    ensure_schema(con)
    q = ("SELECT entry_id, kind, client_id, ts, payload FROM project_timeline "
         "WHERE program_id=?")
    args = [program_id]
    if before:
        q += " AND entry_id < ?"
        args.append(int(before))
    q += " ORDER BY entry_id DESC LIMIT ?"
    args.append(int(limit))
    rows = list(con.execute(q, args))
    con.close()
    rows.reverse()
    return [{"entry_id": r[0], "kind": r[1], "client_id": r[2], "ts": r[3],
             "payload": json.loads(r[4]) if r[4] else None} for r in rows]


def migrate_from_blob(program_id, chat_state_json):
    """v1 blob(chat_state) → 행 이관. client_id 멱등이라 중복 실행 안전. 이관 수 반환."""
    try:
        blob = (json.loads(chat_state_json)
                if isinstance(chat_state_json, str) else (chat_state_json or {}))
    except Exception:
        return 0
    entries = []
    for m in ((blob.get("story_plan") or {}).get("messages") or []):
        cid = m.get("id") or f"mig_m_{m.get('timestamp')}"
        entries.append({"kind": "message", "client_id": str(cid),
                        "ts": float(m.get("timestamp") or 0), "payload": m})
    for g in (blob.get("proposal_history") or []):
        cid = g.get("id") or f"mig_{g.get('ts')}"
        entries.append({"kind": "generation", "client_id": f"gen_{cid}",
                        "ts": float(g.get("ts") or 0), "payload": g})
    return append_entries(program_id, entries)
