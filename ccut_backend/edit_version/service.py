# -*- coding: utf-8 -*-
"""[EDIT-SAVE-1] edit_version 저장 — 승인 스토리 한 벌을 통째로 떠서 append.

원자성이 이 모듈의 존재 이유다 (story_version/service.py 와 동일 규율):
  한 트랜잭션에 넣고, 하나라도 어긋나면 되돌린 뒤 실패를 말한다.

무엇을 뜨는가 (STEP 2 계약):
  · 원천 = 승인 스토리(story_approval.superseded_by IS NULL)가 가리키는 story_version 의
    story_version_item 한 벌. 좌표·trim·숨김·display·edit_values 가 이미 그 안에 있다.
  · fragment_edit_state 는 읽지도 쓰지도 않는다 (★F1: 행수 불변).
  · 기존 행 UPDATE 금지 — 원장은 쌓는다 (append-only).
  · sound_role 은 이번 차수엔 비운다(NULL) — SOUND-1 값을 담을 칸만 확보.
"""
import datetime
import json
import os
import sqlite3

from .models import ITEM_TABLE, SCHEMA_VERSION, TABLE

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


class EditSaveError(Exception):
    def __init__(self, code, message, http_status=400, retryable=False, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
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


def _default_name():
    return "편집 " + datetime.datetime.now().strftime("%m. %d. %H:%M")


def _approved_story_version_id(con, program_id):
    """승인 스토리(비대체)가 가리키는 story_version.version_id. 없으면 None."""
    row = con.execute(
        "SELECT sv.version_id AS vid "
        "FROM story_version sv "
        "JOIN story_approval sa "
        "  ON sa.program_id = sv.program_id AND sa.sequence_hash = sv.sequence_hash "
        "WHERE sv.program_id = ? AND sa.superseded_by IS NULL "
        "ORDER BY sv.version_id DESC LIMIT 1",
        (program_id,)).fetchone()
    return row["vid"] if row else None


def _resolve_items(con, story_version_id, fids):
    """승인 story_version_item 한 벌을 뜬다. fids 를 주면 그 순서·부분집합으로 재정렬."""
    src, order = {}, []
    for r in con.execute(
        "SELECT ordinal, fid, source_id, anchor_start_ms, anchor_end_ms, "
        "trim_start_ms, trim_end_ms, hidden, display_id, edit_values "
        "FROM story_version_item WHERE version_id=? ORDER BY ordinal",
        (story_version_id,)
    ):
        src[r["fid"]] = r
        order.append(r["fid"])
    if not src:
        raise EditSaveError("empty_story", "승인 스토리에 조각이 없습니다.", 409)

    seq = [str(f) for f in fids] if fids else order
    items, missing = [], []
    for ordinal, fid in enumerate(seq):
        r = src.get(fid)
        if r is None:
            missing.append(fid)
            continue
        items.append((
            ordinal, fid, str(r["source_id"]),
            int(r["anchor_start_ms"]), int(r["anchor_end_ms"]),
            (None if r["trim_start_ms"] is None else int(r["trim_start_ms"])),
            (None if r["trim_end_ms"] is None else int(r["trim_end_ms"])),
            1 if r["hidden"] else 0,
            None,                       # sound_role — 이번 차수엔 비운다
            r["display_id"],
            r["edit_values"] if r["edit_values"] is not None else "{}",
        ))
    if missing:
        raise EditSaveError(
            "unresolved_fragments",
            f"승인 스토리에 없는 조각 {len(missing)}개가 있어 저장하지 않았습니다.",
            409, missing=missing[:20], missing_count=len(missing))
    return items


def _int_or_none(v):
    return None if v is None else int(v)


def _items_from_payload(payload):
    """[SAVE-TRUTH 2026-08-06] 화면이 보낸 목록을 그대로 받는다 — 서버가 좌표를 다시 계산하지 않는다.

    이 함수가 생긴 이유(실측): 구판은 화면을 무시하고 story_version_item 을 통째로 복사했다.
    화면이 16이든 14든 저장된 것은 언제나 승인 원고 15행이었다(edit_version id=2·3, 전체행동일=True).
    그래서 편집이 하나도 담기지 않았다. 이제 원천은 화면이다.

    ordinal 은 받은 배열 순서로 다시 매긴다 — 구멍·중복이 구조적으로 못 생긴다.
    """
    if not isinstance(payload, (list, tuple)) or not payload:
        raise EditSaveError("empty_items", "저장할 조각이 없습니다.", 400)
    items, bad = [], []
    for ordinal, raw in enumerate(payload):
        if not isinstance(raw, dict):
            bad.append(ordinal)
            continue
        fid = str(raw.get("fid") or "").strip()
        source_id = str(raw.get("source_id") or "").strip()
        try:
            a_start = int(raw["anchor_start_ms"])
            a_end = int(raw["anchor_end_ms"])
        except (KeyError, TypeError, ValueError):
            bad.append(ordinal)
            continue
        # 좌표가 없거나 뒤집힌 조각은 지어내지 않고 통째로 실패시킨다(반쪽 저장 금지).
        if not fid or not source_id or a_end <= a_start:
            bad.append(ordinal)
            continue
        edit_values = raw.get("edit_values")
        if isinstance(edit_values, (dict, list)):
            edit_values = json.dumps(edit_values, ensure_ascii=False)
        elif edit_values is None:
            edit_values = "{}"
        else:
            edit_values = str(edit_values)
        sound_role = raw.get("sound_role")
        display_id = raw.get("display_id")
        items.append((
            ordinal, fid, source_id, a_start, a_end,
            _int_or_none(raw.get("trim_start_ms")),
            _int_or_none(raw.get("trim_end_ms")),
            1 if raw.get("hidden") else 0,
            None if sound_role is None else str(sound_role),
            None if display_id is None else str(display_id),
            edit_values,
        ))
    if bad:
        raise EditSaveError(
            "bad_items",
            f"조각 {len(bad)}개의 좌표를 읽지 못해 저장하지 않았습니다.",
            400, bad_ordinals=bad[:20], bad_count=len(bad))
    return items


def save_edit_version(program_id, *, name=None, fids=None, items=None, proposal_id=None,
                      parent_version_id=None, created_by="user"):
    """편집 버전 하나를 통째로 저장. 전부 성공하거나, 아무것도 안 남는다.

    items 가 오면 그것이 원천이다(SAVE-TRUTH). 없을 때만 옛 경로(승인 원장 복사)로 내려간다.
    """
    if not program_id or not str(program_id).startswith("proj_"):
        raise EditSaveError("bad_program", "프로젝트를 알 수 없습니다.", 400)
    if created_by not in ("user", "ab_a", "ab_b"):
        raise EditSaveError("bad_created_by", "created_by 값이 올바르지 않습니다.", 400)

    con = _connect()
    try:
        if not _tables_ready(con):
            raise EditSaveError("table_missing", "편집 버전 원장을 사용할 수 없습니다.",
                                503, retryable=True)
        if con.execute("SELECT 1 FROM programs WHERE program_id=?",
                       (program_id,)).fetchone() is None:
            raise EditSaveError("program_not_found", "프로젝트가 없습니다.", 404)

        # story_version_id 는 계보용으로만 남긴다. items 가 오면 이 값이 없어도 저장은 성립한다
        # — 편집본의 원천은 화면이지 승인 원장이 아니기 때문이다.
        svid = _approved_story_version_id(con, program_id)
        if svid is None and not items:
            raise EditSaveError("no_approved_story",
                                "승인된 스토리가 없어 저장할 것이 없습니다.", 409)

        if parent_version_id is not None:
            row = con.execute(
                f"SELECT program_id FROM {TABLE} WHERE version_id=?",
                (parent_version_id,)).fetchone()
            if row is None:
                raise EditSaveError("parent_not_found", "부모 버전이 없습니다.", 404)
            if row["program_id"] != program_id:
                raise EditSaveError("parent_other_program",
                                    "다른 프로젝트의 버전은 부모가 될 수 없습니다.", 409)

        # 쓰기 전 전부 해석 — 여기서 실패하면 DB 는 아직 손대지 않은 상태다.
        rows = _items_from_payload(items) if items else _resolve_items(con, svid, fids)
        vname = (name or "").strip() or _default_name()

        con.isolation_level = None
        con.execute("BEGIN IMMEDIATE")
        try:
            cur = con.execute(
                f"INSERT INTO {TABLE} (program_id, name, parent_version_id, "
                f"story_version_id, proposal_id, schema_version, created_by, created_at) "
                f"VALUES (?,?,?,?,?,?,?,?)",
                (program_id, vname, parent_version_id, svid, proposal_id,
                 SCHEMA_VERSION, created_by, _now()))
            version_id = cur.lastrowid
            con.executemany(
                f"INSERT INTO {ITEM_TABLE} (version_id, ordinal, fid, source_id, "
                f"anchor_start_ms, anchor_end_ms, trim_start_ms, trim_end_ms, "
                f"hidden, sound_role, display_id, edit_values) "
                f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(version_id,) + it for it in rows])
            wrote = con.execute(
                f"SELECT COUNT(*) FROM {ITEM_TABLE} WHERE version_id=?",
                (version_id,)).fetchone()[0]
            if wrote != len(rows):
                raise EditSaveError("item_count_mismatch",
                                    f"조각 {len(rows)}개를 적으려 했는데 {wrote}개가 적혔습니다.",
                                    500)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.isolation_level = ""

        origin = "screen" if items else "approved_story"
        print(f"[EDIT-SAVE-1] 저장 완료 version_id={version_id} "
              f"program={program_id} items={len(rows)} origin={origin} name={vname!r}")
        return {"ok": True, "data": {
            "version_id": version_id, "program_id": program_id, "name": vname,
            "parent_version_id": parent_version_id, "story_version_id": svid,
            "proposal_id": proposal_id, "created_by": created_by,
            "item_count": len(rows), "origin": origin,
        }}
    except EditSaveError:
        raise
    except Exception as e:
        raise EditSaveError("save_failed", "저장하지 못했습니다.", 500, retryable=True) from e
    finally:
        con.close()


def list_edit_versions(program_id):
    con = _connect()
    try:
        if not _tables_ready(con):
            return {"ok": True, "data": {"program_id": program_id, "versions": []}}
        out = []
        for r in con.execute(
            f"SELECT version_id, name, parent_version_id, story_version_id, "
            f"proposal_id, created_by, created_at FROM {TABLE} "
            f"WHERE program_id=? ORDER BY version_id DESC", (program_id,)):
            d = dict(r)
            d["item_count"] = con.execute(
                f"SELECT COUNT(*) FROM {ITEM_TABLE} WHERE version_id=?",
                (r["version_id"],)).fetchone()[0]
            out.append(d)
        return {"ok": True, "data": {"program_id": program_id, "versions": out}}
    finally:
        con.close()


def get_edit_version(version_id):
    con = _connect()
    try:
        if not _tables_ready(con):
            raise EditSaveError("table_missing", "편집 버전 원장을 사용할 수 없습니다.",
                                503, retryable=True)
        head = con.execute(
            f"SELECT * FROM {TABLE} WHERE version_id=?", (version_id,)).fetchone()
        if head is None:
            raise EditSaveError("version_not_found", "그 편집 버전을 찾지 못했습니다.", 404)
        d = dict(head)
        items = []
        for r in con.execute(
            f"SELECT * FROM {ITEM_TABLE} WHERE version_id=? ORDER BY ordinal",
            (version_id,)):
            it = dict(r)
            it["hidden"] = bool(it["hidden"])
            it["edit_values"] = json.loads(it["edit_values"] or "{}")
            items.append(it)
        d["items"] = items
        d["fids"] = [it["fid"] for it in items]
        d["item_count"] = len(items)
        return {"ok": True, "data": d}
    finally:
        con.close()
