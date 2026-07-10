# -*- coding: utf-8 -*-
"""[서사층] 말의 원장(narrative_notes) + 촬영일(shot_date) — 아카이브 v2.1 §2.1/§2.2.

원칙: 사용자가 CCUT에게 들려준 말은 시스템이 계산한 어떤 값보다 격이 높은
영구 자산이다(Tier A급 기록). 원본은 '업로드된 순서'가 아니라 '살아진 날'에 속한다.

- narrative_notes: 대상(source/person/program/fragment)에 붙은 사람의 말.
  append-only. 재조각화·재인덱싱에 불멸(파생 테이블과 분리된 원장).
- sources.shot_date: 파일명 파싱(실측 93% 커버) → mtime 폴백. 멱등 백필.
"""
import datetime
import os
import re
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

_TARGETS = ("source", "person", "program", "fragment")
_DATE_RE = re.compile(r"(20[0-3]\d)[-_.]?(\d{2})[-_.]?(\d{2})")


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def ensure_schema(con):
    con.execute("""CREATE TABLE IF NOT EXISTS narrative_notes (
        note_id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_kind TEXT NOT NULL,
        target_id TEXT NOT NULL,
        text TEXT NOT NULL,
        origin TEXT,
        said_at TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nn_target "
                "ON narrative_notes(target_kind, target_id)")
    # 같은 대상에 같은 말이 중복 적재되지 않게 (재업로드·재시도 멱등)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_nn_dedup "
                "ON narrative_notes(target_kind, target_id, text)")
    try:
        con.execute("ALTER TABLE sources ADD COLUMN shot_date TEXT")
    except sqlite3.OperationalError:
        pass  # 이미 있음
    con.commit()


def parse_shot_date(title, file_path=None):
    """파일명에서 촬영일 추출(YYYYMMDD 계열). 실패 시 파일 mtime. 둘 다 없으면 None."""
    m = _DATE_RE.search(title or "")
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            pass  # 20151199 같은 오탐
    if file_path and os.path.exists(file_path):
        try:
            return datetime.date.fromtimestamp(os.path.getmtime(file_path)).isoformat()
        except OSError:
            pass
    return None


def add_notes(entries):
    """[말의 원장] 배치 적재 — entries: [{target_kind, target_id, text, origin}].
    빈 말·무효 대상은 조용히 건너뜀. 멱등(dedup 인덱스). 적재 수 반환."""
    con = _connect()
    ensure_schema(con)
    now = datetime.datetime.now().isoformat()
    added = 0
    for e in entries or []:
        kind = (e.get("target_kind") or "").strip()
        tid = (e.get("target_id") or "").strip()
        text = (e.get("text") or "").strip()
        if kind not in _TARGETS or not tid or not text:
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO narrative_notes "
            "(target_kind, target_id, text, origin, said_at) VALUES (?,?,?,?,?)",
            (kind, tid, text, e.get("origin") or "chat", e.get("said_at") or now))
        added += cur.rowcount
    con.commit()
    con.close()
    return added


def notes_for(target_kind, target_id):
    con = _connect()
    ensure_schema(con)
    rows = [{"note_id": r[0], "text": r[1], "origin": r[2], "said_at": r[3]}
            for r in con.execute(
                "SELECT note_id, text, origin, said_at FROM narrative_notes "
                "WHERE target_kind=? AND target_id=? ORDER BY note_id",
                (target_kind, target_id))]
    con.close()
    return rows


def source_note_map():
    """source_id → 첫 노트 텍스트 (아카이브 목록 캡션용, 가볍게 1개만)."""
    con = _connect()
    ensure_schema(con)
    out = {}
    for sid, text in con.execute(
            "SELECT target_id, text FROM narrative_notes "
            "WHERE target_kind='source' ORDER BY note_id"):
        out.setdefault(sid, text)
    con.close()
    return out


def source_note_tokens(source_ids) -> dict[str, set[str]]:
    """source_id → 전체 source 노트 토큰 집합. 선별 보조용 read-only 리더."""
    ids = []
    for sid in source_ids or []:
        sid = (sid or "").strip()
        if sid and sid not in ids:
            ids.append(sid)
    if not ids:
        return {}

    out = {sid: set() for sid in ids}
    placeholders = ",".join("?" for _ in ids)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    try:
        rows = con.execute(
            f"SELECT target_id, text FROM narrative_notes "
            f"WHERE target_kind='source' AND target_id IN ({placeholders})",
            ids,
        )
        stopwords = {"영상"}
        for sid, text in rows:
            tokens = out.setdefault(sid, set())
            for tok in re.split(r"[\s,，、]+", text or ""):
                tok = tok.strip()
                if len(tok) >= 2 and tok not in stopwords:
                    tokens.add(tok)
    finally:
        con.close()
    return {sid: toks for sid, toks in out.items() if toks}


def backfill_shot_dates():
    """[연대기] sources.shot_date 멱등 백필 — NULL인 행만. 채운 수 반환."""
    con = _connect()
    ensure_schema(con)
    rows = list(con.execute(
        "SELECT source_id, title, file_path FROM sources "
        "WHERE shot_date IS NULL OR shot_date = ''"))
    n = 0
    for sid, title, fpath in rows:
        d = parse_shot_date(title, fpath)
        if d:
            con.execute("UPDATE sources SET shot_date=? WHERE source_id=?", (d, sid))
            n += 1
    con.commit()
    con.close()
    if n:
        print(f"[NARRATIVE] shot_date 백필: {n}건")
    return n


def backfill_intake_notes_from_timeline():
    """[말의 원장 소급] timeline에 표류 중인 '영상 소개/알려주신 내용' 메시지에서
    'X · 제목: 설명' 줄을 추출해 source 노트로 귀속(제목 매칭). 멱등. 적재 수 반환."""
    con = _connect()
    ensure_schema(con)
    import json as _json
    # 제목(확장자 제거·소문자) → source_id
    title_map = {}
    for sid, t in con.execute("SELECT source_id, title FROM sources"):
        base = os.path.splitext(t or "")[0].strip().lower()
        if base:
            title_map.setdefault(base, sid)
    rows = list(con.execute(
        "SELECT payload FROM project_timeline WHERE kind='message' AND "
        "(payload LIKE '%영상 소개%' OR payload LIKE '%알려주신 내용%' OR payload LIKE '%문진 정리%')"))
    line_re = re.compile(r"^\s*(?:[A-Z]{1,2}\s*·\s*)?(.+?):\s*(.+)$")
    entries = []
    for (payload,) in rows:
        try:
            text = (_json.loads(payload) or {}).get("text") or ""
        except Exception:
            continue
        for line in text.split("\n"):
            if line.startswith(("화면 기준", "영상 소개", "알려주신", "문진")):
                continue
            m = line_re.match(line)
            if not m:
                continue
            name = os.path.splitext(m.group(1).strip())[0].strip().lower()
            note = m.group(2).strip()
            if not note or note.startswith("(설명 없음"):
                continue
            sid = title_map.get(name)
            if sid:
                entries.append({"target_kind": "source", "target_id": sid,
                                "text": note, "origin": "intake_backfill"})
    con.close()
    n = add_notes(entries)
    if n:
        print(f"[NARRATIVE] intake 노트 소급: {n}건")
    return n
