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
# [MEMORY-SPINE 2026-08-02] 기억 3종 복구 — 이 문이 큐원의 장기 기억을 막고 있었다.
#   chat_summary   12턴 밖의 대화를 요약해 남기는 유일한 통로 (converse.py:725)
#   active_intent  국장이 정한 선별 기준 ("사람 중심으로")   (converse.py:637)
#   chat_pref      분량 선호 (조각 수·목표 길이)            (converse.py:643)
#   쓰는 코드도 읽는 코드도 다 있는데 이 튜플이 append 를 조용히 skip 했다
#   (append_entries:`if kind not in _KINDS: continue` — 예외도 없고 added 에도 안 잡혀
#    호출자는 200 OK 로 본다). 실측: 그 세 kind 는 2026-07-19~07-22 이후 새 행이 0이고
#   message 만 08-02 까지 이어졌다.
#   ※ project_timeline 에 kind CHECK 제약이 없다 — 스키마 변경 아님(DDL 0).
_KINDS = ("message", "generation", "transcript_ref",
          "chat_summary", "active_intent", "chat_pref",
          # [2026-08-08] 사용자가 센서를 고친 것 — VL 은 틀릴 수 있고 사람이 맞다.
          #   국장 실화면: 14번 장면 라벨이 '산'인데 실제는 바닷가 바위였다.
          "scene_label_fix",
          # [HANDS-1 2026-08-08] 젬마의 손이 실제로 한 일 — Receipt.
          #   ★이 줄이 없어서 또 조용히 버려졌다(실측: 17→14 로 실제 뺐는데
          #     '뺐나?' 에 답할 기록이 0건). 위 주석의 사고를 그대로 반복했다.
          #     그래서 아래에 미등록 kind 경고를 붙였다 — 다음엔 안 조용하게.
          "hand_done",
          # [2026-08-08] 아직 못 하는 일을 사용자가 부탁한 기록.
          #   개념서 §8 "불가능하다는 말로 대화를 끝내지 않는다" —
          #   못 한다고만 하고 잊으면 그 요구는 영영 안 만들어진다.
          "wish",
          # [HOUSE-1 2026-08-08 국장 지시 "고자질이 아니라 수다"]
          #   시스템이 조용히 한 일 — 막은 것, 대신 처리한 것, 어긋나서 내린 것.
          #   지금까지 이런 건 콘솔에만 찍혀서 개발자만 알았다. 같은 집에 사는
          #   AI 도 몰랐다. 이제 같은 관에 태워 AI 의 귀에 들어가게 한다.
          #   ★말할지 말지는 AI 가 정한다. 여기서 거르지 않는다.
          "system_event")


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
            # 조용히 버리지 않는다 — 이 침묵이 같은 사고를 두 번 냈다.
            print(f"[TIMELINE][DROP] 등록 안 된 kind={kind!r} — _KINDS 에 넣어야 "
                  f"기록된다 (program={program_id})")
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
