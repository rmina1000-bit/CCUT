# -*- coding: utf-8 -*-
"""[조각 금고 v1] 인지조각의 불멸 원장 — 아카이브 v2.2 증보 (국장 교정 2026-07-05).

CCUT 아카이브의 왕관 자산은 원본이 아니라 '인지조각'이다: 구간 영상에
요약·자막·시각서술·인물·장소·가치평가·임베딩(=인지)이 붙은 것. 현재 구조는
재조각화가 fragment_id를 재발급하며 인지를 버린다(실측: 인물링크 33.5%·
인지잔재 39.9% 사망). 금고는 이 문제의 '자주 벌어지는 경우'만 종결한다:

  자연키 = (원본 내용 hash, 구간 deciseconds — 0.1초 반올림)
  — 경계가 거의 그대로인 재조각화(구간 흔들림 <0.05s)는 fragment_id가
    바뀌어도, 파일명이 바뀌어도, 원본이 유실됐다 재유입돼도(hash 재일치)
    같은 조각으로 이어진다.

  [v1 한계 — 정직히 명시] 자연키가 구간 자체에 묶여 있어, 한 조각이
  둘로 쪼개지거나 여러 조각이 하나로 합쳐지는 재조각화(경계가 실질적으로
  달라지는 경우)는 새 자연키가 되어 별도 행으로 적재된다 — 이 경우 옛
  인지는 승계되지 않는다. "인지의 불멸"은 이번 v1의 코드가 보장하는
  범위가 아니라 지향점이다. 분할/병합 대응은 후속 버전 과제.

  적재는 append/merge only. merge_keep: 새 세대가 오면 비어있는 칸만
  채우고, 채워진 인지는 값이 올 때만 갱신한다(있던 값을 지우지는 않는다).

원본이 유실돼도(자연키가 유지되는 한) 금고의 데이터값은 남는다.
"""
import datetime
import json
import os
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def norm_key(anchor, start, end):
    """자연키 정규화 — 구간은 deciseconds(0.1s) 반올림. 재조각화의 미세한
    경계 흔들림(<0.05s)은 같은 조각으로 본다."""
    return (str(anchor), int(round(float(start or 0) * 10)),
            int(round(float(end or 0) * 10)))


def merge_keep(old, new):
    """인지 병합 — 절대 잃지 않는다: 새 값이 실하면 갱신, 비었으면 옛 값 보존."""
    if new is None:
        return old
    if isinstance(new, str) and not new.strip():
        return old
    return new


def ensure_schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS fragment_vault (
        vault_id INTEGER PRIMARY KEY AUTOINCREMENT,
        anchor_hash TEXT NOT NULL,
        start_ds INTEGER NOT NULL,
        end_ds INTEGER NOT NULL,
        start REAL, end REAL,
        source_id TEXT, fragment_id TEXT,
        source_title TEXT, shot_date TEXT, display_name TEXT,
        summary TEXT, transcript TEXT, visual_desc TEXT, scene_type TEXT,
        main_subjects TEXT, search_text TEXT,
        people TEXT, places TEXT,
        role TEXT, edit_value REAL, hook_score REAL,
        embedding BLOB, embedding_model TEXT, embedding_dim INTEGER,
        generations INTEGER DEFAULT 1,
        source_alive INTEGER DEFAULT 1,
        first_seen TEXT, last_seen TEXT)""")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_anchor "
                "ON fragment_vault(anchor_hash, start_ds, end_ds)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_vault_fragment "
                "ON fragment_vault(fragment_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_vault_source "
                "ON fragment_vault(source_id)")
    con.commit()


_MERGE_COLS = ("display_name", "summary", "transcript", "visual_desc", "scene_type",
               "main_subjects", "search_text", "people", "places", "role",
               "edit_value", "hook_score", "embedding", "embedding_model",
               "embedding_dim", "source_title", "shot_date")


def _upsert(con, row):
    """자연키 upsert — 인지 병합(merge_keep), 세대 카운트, last_seen 갱신."""
    anchor, sds, eds = norm_key(row["anchor_hash"], row["start"], row["end"])
    now = datetime.datetime.now().isoformat()
    cur = con.execute(
        "SELECT vault_id, fragment_id, " + ", ".join(_MERGE_COLS) +
        " FROM fragment_vault WHERE anchor_hash=? AND start_ds=? AND end_ds=?",
        (anchor, sds, eds)).fetchone()
    if cur is None:
        cols = ["anchor_hash", "start_ds", "end_ds", "start", "end", "source_id",
                "fragment_id", "first_seen", "last_seen"] + list(_MERGE_COLS)
        vals = [anchor, sds, eds, row["start"], row["end"], row.get("source_id"),
                row.get("fragment_id"), now, now] + [row.get(c) for c in _MERGE_COLS]
        con.execute(f"INSERT INTO fragment_vault ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(cols))})", vals)
        return "insert"
    vid, old_fid = cur[0], cur[1]
    olds = dict(zip(_MERGE_COLS, cur[2:]))
    merged = {c: merge_keep(olds.get(c), row.get(c)) for c in _MERGE_COLS}
    gen_bump = 1 if (row.get("fragment_id") and row["fragment_id"] != old_fid) else 0
    con.execute(
        "UPDATE fragment_vault SET " + ", ".join(f"{c}=?" for c in _MERGE_COLS) +
        ", source_id=?, fragment_id=?, last_seen=?, source_alive=1, "
        "generations=generations+? WHERE vault_id=?",
        [merged[c] for c in _MERGE_COLS] +
        [row.get("source_id"), row.get("fragment_id") or old_fid, now, gen_bump, vid])
    return "merge"


def ingest_source(source_id):
    """한 원본의 현재 인지 전부를 금고에 적재/병합 — 재조각화 직후 호출이 정석.
    (조각화가 몇 번을 갈아엎어도 금고의 인지는 이어진다)"""
    con = _connect()
    ensure_schema(con)
    src = con.execute(
        "SELECT hash_value, title, shot_date FROM sources WHERE source_id=?",
        (source_id,)).fetchone()
    if not src:
        con.close()
        return {"status": "NO_SOURCE", "rows": 0}
    anchor = src[0] or source_id  # hash 없으면 source_id 폴백(내용 앵커보다 약함)
    title, shot_date = src[1], src[2]

    # 인지 조립: semantic + index + people + places
    idx = {r[0]: r for r in con.execute(
        """SELECT fragment_id, visual_desc, transcript, scene_type, main_subjects,
                  search_text, embedding, embedding_model, embedding_dim,
                  role, edit_value, hook_score
           FROM fragment_index WHERE source_id=?""", (source_id,))}
    people = {}
    for fid, name in con.execute(
            """SELECT pf.fragment_id, p.name FROM person_faces pf
               JOIN persons p ON p.person_id = pf.person_id
               WHERE p.status='named' AND p.name IS NOT NULL"""):
        people.setdefault(fid, set()).add(name)
    places = {}
    for fid, label in con.execute(
            "SELECT fragment_id, place_label FROM fragment_places WHERE source_id=?",
            (source_id,)):
        if label:
            places.setdefault(fid, set()).add(label)

    from engine.fragment_show import display_name as _dn
    n_ins, n_mrg = 0, 0
    for fid, start, end, sem_j, str_j in con.execute(
            "SELECT fragment_id, start, end, semantic_json, structural_json "
            "FROM semantic_fragments WHERE source_id=?", (source_id,)):
        try:
            sem = json.loads(sem_j) if isinstance(sem_j, str) else (sem_j or {})
        except Exception:
            sem = {}
        try:
            stru = json.loads(str_j) if isinstance(str_j, str) else (str_j or {})
        except Exception:
            stru = {}
        ix = idx.get(fid)
        row = {
            "anchor_hash": anchor, "start": start, "end": end,
            "source_id": source_id, "fragment_id": fid,
            "source_title": title, "shot_date": shot_date,
            "display_name": _dn(title or source_id, start, end),
            "summary": sem.get("summary"),
            "role": stru.get("role"), "edit_value": stru.get("edit_value"),
            "people": ",".join(sorted(people.get(fid, set()))) or None,
            "places": ",".join(sorted(places.get(fid, set()))) or None,
        }
        if ix:
            row.update({"visual_desc": ix[1], "transcript": ix[2], "scene_type": ix[3],
                        "main_subjects": ix[4] if isinstance(ix[4], str) else
                        (json.dumps(ix[4], ensure_ascii=False) if ix[4] else None),
                        "search_text": ix[5], "embedding": ix[6],
                        "embedding_model": ix[7], "embedding_dim": ix[8],
                        "hook_score": ix[11]})
            row["role"] = row["role"] or ix[9]
            row["edit_value"] = row["edit_value"] if row["edit_value"] is not None else ix[10]
        if _upsert(con, row) == "insert":
            n_ins += 1
        else:
            n_mrg += 1
    con.commit()
    con.close()
    return {"status": "OK", "inserted": n_ins, "merged": n_mrg}


def backfill_all():
    """전 원본 일괄 적재 — 멱등. 시작 시 1회 호출용(가볍게: 수백 행 수준)."""
    con = _connect()
    ensure_schema(con)
    sids = [r[0] for r in con.execute("SELECT source_id FROM sources")]
    con.close()
    ins = mrg = 0
    for sid in sids:
        r = ingest_source(sid)
        ins += r.get("inserted", 0)
        mrg += r.get("merged", 0)
    print(f"[VAULT] 금고 적재: 원본 {len(sids)}개 → 신규 {ins} · 병합 {mrg}")
    return {"sources": len(sids), "inserted": ins, "merged": mrg}


def mark_source_alive():
    """원본 실존 여부 갱신 — 유실돼도 금고 행은 남는다(source_alive=0 표시만).

    [버그 수정 2026-07-05] 기존 구현은 sources 테이블을 기준으로 순회해
    갱신했다 — source row 자체가 삭제되면 그 vault 행은 갱신 대상에서
    빠져 source_alive=1로 방치되고 stats()가 낙관적으로 거짓말했다.
    지금은 vault가 보유한 source_id 집합을 기준으로 sources 존재 여부를
    LEFT JOIN으로 판정 — sources row 삭제·file_path 유실 양쪽 모두 잡는다."""
    con = _connect()
    ensure_schema(con)
    vault_sids = [r[0] for r in con.execute(
        "SELECT DISTINCT source_id FROM fragment_vault WHERE source_id IS NOT NULL")]
    src_paths = dict(con.execute("SELECT source_id, file_path FROM sources"))
    n_dead = 0
    for sid in vault_sids:
        path = src_paths.get(sid)  # sources에 없으면 None → 죽음 판정
        alive = 1 if (path and os.path.exists(path)) else 0
        if not alive:
            n_dead += 1
        con.execute("UPDATE fragment_vault SET source_alive=? WHERE source_id=?",
                    (alive, sid))
    con.commit()
    con.close()
    return n_dead


def stats():
    con = _connect()
    ensure_schema(con)
    out = {
        "rows": con.execute("SELECT COUNT(*) FROM fragment_vault").fetchone()[0],
        "sources": con.execute("SELECT COUNT(DISTINCT source_id) FROM fragment_vault").fetchone()[0],
        "with_people": con.execute("SELECT COUNT(*) FROM fragment_vault WHERE people IS NOT NULL").fetchone()[0],
        "with_embedding": con.execute("SELECT COUNT(*) FROM fragment_vault WHERE embedding IS NOT NULL").fetchone()[0],
        "with_transcript": con.execute("SELECT COUNT(*) FROM fragment_vault WHERE transcript IS NOT NULL AND transcript != ''").fetchone()[0],
        "multi_generation": con.execute("SELECT COUNT(*) FROM fragment_vault WHERE generations > 1").fetchone()[0],
        "source_lost": con.execute("SELECT COUNT(*) FROM fragment_vault WHERE source_alive = 0").fetchone()[0],
    }
    con.close()
    return out
