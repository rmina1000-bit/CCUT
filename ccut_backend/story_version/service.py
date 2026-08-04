# -*- coding: utf-8 -*-
"""[SAVE-SPINE 2-B] 버전 저장 — 한 덩어리로 저장되거나, 아무것도 안 남거나.

원자성이 이 모듈의 존재 이유다.
  반쪽 저장이 남으면 사용자는 저장했다고 믿는데 실제로는 없는 상태가 된다.
  그래서 (1) 쓰기 전에 전부 해석해 보고, (2) 한 트랜잭션에 넣고,
  (3) 하나라도 어긋나면 되돌린 뒤 "저장 실패"라고 말한다.

무엇을 누가 주는가 (반쪽 진실 방지):
  클라가 주는 것 — 조각 순서(fids) · 전사 선택(span_ids) · 이름 · display_id
    화면의 결정이라 서버가 알 수 없다.
  서버가 채우는 것 — 좌표(anchor_ms) · trim · 숨김 · 값 스냅샷
    `semantic_fragments` 와 `fragment_edit_state` 가 권위다. 클라가 보낸 값을
    믿으면 화면과 원장이 어긋난 채로 굳는다.
  → 클라가 보낸 fid 중 서버가 해석 못 하는 것이 하나라도 있으면 저장 전체가 실패한다.
"""
import datetime
import json
import os
import sqlite3

from .models import ITEM_TABLE, SCHEMA_VERSION, TABLE

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


class SaveVersionError(Exception):
    def __init__(self, code, message, http_status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.extra = extra


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _tables_ready(con):
    names = {r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    return TABLE in names and ITEM_TABLE in names


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _to_ms(seconds):
    """초 -> ms 정수. 시간 좌표의 단일 권위는 ms 정수다 (CLAUDE.md)."""
    return int(round(float(seconds) * 1000))


def _resolve_items(con, program_id, fids, display_ids):
    """저장 전에 전부 해석한다. 여기서 실패하면 DB 는 아직 손대지 않은 상태다.

    반환: [(ordinal, fid, source_id, a_start, a_end, t_start, t_end, hidden, display_id, edit_values)]
    """
    if not fids:
        raise SaveVersionError("empty_story", "저장할 조각이 없습니다.", 400)

    # 조각 좌표 — semantic_fragments 가 권위
    rows = {r["fragment_id"]: r for r in con.execute(
        "SELECT fragment_id, source_id, start, end FROM semantic_fragments")}

    # 편집값 — fragment_edit_state 가 권위 (없으면 '편집 안 함'이 기본)
    edits = {}
    try:
        for r in con.execute(
            "SELECT timeline_item_id, trim_start_ms, trim_end_ms, removed, "
            "excluded_ranges_json, occurrence, parent_fragment_id "
            "FROM fragment_edit_state WHERE program_id=?", (program_id,)
        ):
            edits[r["timeline_item_id"]] = r
    except sqlite3.OperationalError:
        edits = {}

    items, missing = [], []
    for ordinal, fid in enumerate(fids):
        fid = str(fid)
        src = rows.get(fid)
        if src is None:
            missing.append(fid)
            continue
        a_start, a_end = _to_ms(src["start"]), _to_ms(src["end"])
        e = edits.get(fid)
        if e is None:
            t_start, t_end, hidden, extra = a_start, a_end, 0, {}
        else:
            t_start = int(e["trim_start_ms"])
            t_end = int(e["trim_end_ms"])
            hidden = 1 if e["removed"] else 0
            extra = {
                "excluded_ranges": json.loads(e["excluded_ranges_json"] or "[]"),
                "occurrence": e["occurrence"],
                "parent_fragment_id": e["parent_fragment_id"],
            }
        items.append((
            ordinal, fid, str(src["source_id"]), a_start, a_end,
            t_start, t_end, hidden,
            (display_ids or {}).get(fid),
            json.dumps(extra, ensure_ascii=False),
        ))

    if missing:
        # 반쪽 저장 금지 — 하나라도 못 찾으면 전체 실패. 무엇이 없었는지 말한다.
        raise SaveVersionError(
            "unresolved_fragments",
            f"조각 {len(missing)}개를 찾지 못해 저장하지 않았습니다.",
            409, missing=missing[:20], missing_count=len(missing),
        )
    return items


def _log_failure(program_id, phase, code, detail):
    """저장 실패를 원장에 남긴다. ★저장 트랜잭션 밖 — 실패 기록이 실패를 되살리면 안 된다."""
    try:
        con = _connect()
        try:
            con.execute(
                "INSERT INTO failure_ledger (created_at, domain, program_id, phase, error_code, detail) "
                "VALUES (?,?,?,?,?,?)",
                (_now(), "save_version", program_id, phase, code,
                 json.dumps(detail, ensure_ascii=False)),
            )
            con.commit()
        finally:
            con.close()
    except Exception as exc:      # 원장이 고장나도 저장 실패 자체를 가리지 않는다
        print(f"[SAVE-SPINE][LEDGER-FAIL] {exc}")


def save_version(program_id, *, name, fids, selected_span_ids=None,
                 rough_cut_input_hash=None, parent_version_id=None,
                 display_ids=None, source_ids=None, actor="user", note=None,
                 sequence_hash=None):
    """버전 하나를 통째로 저장한다. 전부 성공하거나, 아무것도 안 남는다."""
    # 연결 열기 전 검증도 원장에 남긴다 — 아래 try 밖이라 그냥 두면 이 실패만 기록이 빈다(실측).
    try:
        if not program_id or not str(program_id).startswith("proj_"):
            raise SaveVersionError("bad_program", "프로젝트를 알 수 없습니다.", 400)
        name = (name or "").strip()
        if not name:
            raise SaveVersionError("empty_name", "버전 이름이 필요합니다.", 400)
    except SaveVersionError as e:
        _log_failure(program_id, "validate", e.code, {"message": e.message})
        raise

    con = _connect()
    try:
        if not _tables_ready(con):
            raise SaveVersionError("table_missing", "버전 원장을 사용할 수 없습니다.", 503)

        if con.execute("SELECT 1 FROM programs WHERE program_id=?",
                       (program_id,)).fetchone() is None:
            raise SaveVersionError("program_not_found", "프로젝트가 없습니다.", 404)

        if parent_version_id is not None:
            row = con.execute(
                f"SELECT program_id FROM {TABLE} WHERE version_id=?",
                (parent_version_id,)).fetchone()
            if row is None:
                raise SaveVersionError("parent_not_found", "부모 버전이 없습니다.", 404)
            if row["program_id"] != program_id:
                # 설계 ⑥ — 부모/자식은 같은 폴더(프로젝트) 안의 버전 사이 관계다.
                raise SaveVersionError("parent_other_program",
                                       "다른 프로젝트의 버전은 부모가 될 수 없습니다.", 409)

        # ① 쓰기 전에 전부 해석 — 여기서 터지면 DB 는 무손상이다
        items = _resolve_items(con, program_id, fids, display_ids)

        if source_ids is None:
            source_ids = sorted({it[2] for it in items})
        if sequence_hash is None:
            from story_gate.service import compute_hash
            sequence_hash = compute_hash([it[1] for it in items])

        # ② 한 트랜잭션. 하나라도 실패하면 아무것도 안 남는다.
        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute(
                f"INSERT INTO {TABLE} (program_id, name, parent_version_id, schema_version, "
                f"sequence_hash, item_count, source_ids, selected_span_ids, "
                f"rough_cut_input_hash, actor, note, created_at) "
                f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (program_id, name, parent_version_id, SCHEMA_VERSION,
                 sequence_hash, len(items),
                 json.dumps(list(source_ids), ensure_ascii=False),
                 json.dumps(list(selected_span_ids or []), ensure_ascii=False),
                 rough_cut_input_hash, actor, note, _now()),
            )
            version_id = cur.lastrowid
            con.executemany(
                f"INSERT INTO {ITEM_TABLE} (version_id, ordinal, fid, source_id, "
                f"anchor_start_ms, anchor_end_ms, trim_start_ms, trim_end_ms, "
                f"hidden, display_id, edit_values) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(version_id,) + it for it in items],
            )
            # ③ 커밋 직전 검산 — 적으려던 수와 실제로 적힌 수가 같은가
            wrote = con.execute(
                f"SELECT COUNT(*) FROM {ITEM_TABLE} WHERE version_id=?",
                (version_id,)).fetchone()[0]
            if wrote != len(items):
                raise SaveVersionError(
                    "item_count_mismatch",
                    f"조각 {len(items)}개를 적으려 했는데 {wrote}개가 적혔습니다.", 500)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.isolation_level = ""

        print(f"[SAVE-SPINE] 저장 완료 version_id={version_id} "
              f"program={program_id} items={len(items)} name={name!r}")
        return {
            "ok": True, "version_id": version_id, "program_id": program_id,
            "name": name, "parent_version_id": parent_version_id,
            "item_count": len(items), "sequence_hash": sequence_hash,
        }
    except SaveVersionError as e:
        _log_failure(program_id, "save", e.code, {"message": e.message, **e.extra})
        raise
    except Exception as e:
        _log_failure(program_id, "save", "unexpected", {"message": str(e)})
        raise SaveVersionError("save_failed", "저장하지 못했습니다.", 500) from e
    finally:
        con.close()


def list_versions(program_id):
    """이 프로젝트에 쌓인 버전들 (설계 ②). 최신이 앞."""
    con = _connect()
    try:
        if not _tables_ready(con):
            return {"ok": True, "program_id": program_id, "versions": []}
        out = []
        for r in con.execute(
            f"SELECT version_id, name, parent_version_id, item_count, sequence_hash, "
            f"actor, note, created_at, source_ids FROM {TABLE} "
            f"WHERE program_id=? ORDER BY version_id DESC", (program_id,)
        ):
            d = dict(r)
            d["source_ids"] = json.loads(d.get("source_ids") or "[]")
            out.append(d)
        return {"ok": True, "program_id": program_id, "versions": out}
    finally:
        con.close()


def get_version(version_id):
    """버전 하나를 통째로 — 저장 시점과 같은 순서·좌표·편집값."""
    con = _connect()
    try:
        if not _tables_ready(con):
            raise SaveVersionError("table_missing", "버전 원장을 사용할 수 없습니다.", 503)
        head = con.execute(
            f"SELECT * FROM {TABLE} WHERE version_id=?", (version_id,)).fetchone()
        if head is None:
            raise SaveVersionError("version_not_found", "그 버전을 찾지 못했습니다.", 404)
        d = dict(head)
        d["source_ids"] = json.loads(d.get("source_ids") or "[]")
        d["selected_span_ids"] = json.loads(d.get("selected_span_ids") or "[]")
        items = []
        for r in con.execute(
            f"SELECT * FROM {ITEM_TABLE} WHERE version_id=? ORDER BY ordinal",
            (version_id,)
        ):
            it = dict(r)
            it["hidden"] = bool(it["hidden"])
            it["edit_values"] = json.loads(it.get("edit_values") or "{}")
            items.append(it)
        d["items"] = items
        d["fids"] = [it["fid"] for it in items]
        return {"ok": True, **d}
    finally:
        con.close()
