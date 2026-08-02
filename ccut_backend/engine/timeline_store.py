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

# [TIMELINE-REF 2026-08-02] transcript_ref 추가 — 전사가 대화 흐름의 '언제'였는지.
#   왜 필요했나: 전사 노드는 스트림에서 ts=0 하드코딩이라 늘 맨 위에 몰렸다
#   (CenterPanel.tsx:2953). 실측(Freesia): 전사 앞 msg 0개 / 뒤 183개인데 그 아래
#   첫 구분선이 "7월 31일"이다 — 8/1 에 만들어진 원고가 7/31 대화 위에 있었다.
#   ★roughCut.created_at 은 '산출물이 만들어진 시각'이지 '대화에 등장한 시각'이 아니다
#     (main.py:6325 POST 핸들러가 record 를 새로 만들 때 now(utc) 를 찍고,
#      재생성하면 통째로 갱신된다). 그래서 그 값을 순서로 쓰지 않는다.
#   ★진실을 두 벌 만들지 않는다 — 원문은 복제하지 않는다. 참조(ref_id)만 남긴다.
#   ★client_id 는 결정론(tref_<input_hash>). Date.now() 를 넣으면 STAGE-DUP 과
#     같은 함정에 빠져 열 때마다 한 행씩 쌓인다.
#   ※ 이 튜플은 파이썬 상수다. project_timeline 에 kind CHECK 제약이 없으므로
#     여기 한 줄 추가는 스키마 변경이 아니다(DDL 0 · 마이그레이션 0).
_KINDS = ("message", "generation", "transcript_ref")


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
