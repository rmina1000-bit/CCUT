# -*- coding: utf-8 -*-
"""[EDIT-CONTRACT-B0] edit_state 서비스 계층 — upsert(서버측 재정규화·낙관적 잠금) + 조회 + 이력 기록.

- 저장 대상: BACKEND_DIR/ccut_app.db (제품과 동일 상대 경로 — worktree에서는 격리 테스트 DB).
- 이력: vault_events 재사용 (v0.4 §7) — event_kind='edit_command', ref_id=edit_state_id,
  detail JSON = {schema_version, edit_state_id, timeline_item_id, command_type,
  before{...ms}, after{...ms}, origin, (INHERIT 시 source/target_item_id)}.
  detail 내부 ms 전용 권위 — 레거시 start_ds/end_ds는 norm_key 파생값.
- 필수 필드 결손 = 서비스 계층 쓰기 거부 (스키마 NOT NULL 변경 아님).
- 형식 위반(각 구간 start>=end·음수) = 저장 거부 (미규정 조정 (c) 확정본).
  REMOVE는 removed=true로만 표현한다 (trim 붕괴로 표현 금지).
"""
import datetime
import json
import os
import sqlite3
import uuid

from .edit_state import LAST_ORIGIN_VALUES, SCHEMA_VERSION, compile_spans, ed_ids, normalize

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

REQUIRED_FIELDS = (
    "program_id", "timeline_item_id", "source_id",
    "anchor_start_ms", "anchor_end_ms", "trim_start_ms", "trim_end_ms",
    "command_type", "origin",
)

COMMAND_TYPES = ("TRIM", "EXCLUDE_RANGE", "REMOVE", "RESTORE", "INHERIT", "MIGRATION")


class EditStateError(Exception):
    def __init__(self, code, message, http_status=400, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.extra = extra or {}


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _validate(payload):
    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
    if missing:
        raise EditStateError("missing_required", f"필수 필드 결손: {missing}")
    ints = {}
    for k in ("anchor_start_ms", "anchor_end_ms", "trim_start_ms", "trim_end_ms"):
        v = payload[k]
        if not isinstance(v, int) or isinstance(v, bool):
            raise EditStateError("format_violation", f"{k}: 정수 ms 아님 ({v!r})")
        if v < 0:
            raise EditStateError("format_violation", f"{k}: 음수 ({v})")
        ints[k] = v
    if ints["anchor_start_ms"] >= ints["anchor_end_ms"]:
        raise EditStateError("format_violation", "anchor start>=end")
    if ints["trim_start_ms"] >= ints["trim_end_ms"]:
        raise EditStateError("format_violation", "trim start>=end (REMOVE는 removed=true로 표현)")
    excluded = payload.get("excluded_ranges") or []
    if not isinstance(excluded, list):
        raise EditStateError("format_violation", "excluded_ranges: 리스트 아님")
    for r in excluded:
        if (not isinstance(r, (list, tuple))) or len(r) != 2:
            raise EditStateError("format_violation", f"excluded range 형식 위반: {r!r}")
        s, e = r
        for v in (s, e):
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise EditStateError("format_violation", f"excluded range 값 위반: {r!r}")
        if s >= e:
            raise EditStateError("format_violation", f"excluded range start>=end: {r!r}")
    if payload["origin"] not in LAST_ORIGIN_VALUES:
        raise EditStateError("format_violation", f"origin 허용값 아님: {payload['origin']!r}")
    if payload["command_type"] not in COMMAND_TYPES:
        raise EditStateError("format_violation", f"command_type 허용값 아님: {payload['command_type']!r}")
    if payload["command_type"] == "INHERIT":
        if not payload.get("source_item_id") or not payload.get("target_item_id"):
            raise EditStateError("missing_required", "INHERIT: source/target_item_id 필수")


def _row_to_state(row):
    return {
        "anchor_start_ms": row["anchor_start_ms"], "anchor_end_ms": row["anchor_end_ms"],
        "trim_start_ms": row["trim_start_ms"], "trim_end_ms": row["trim_end_ms"],
        "excluded_ranges": json.loads(row["excluded_ranges_json"]),
        "removed": bool(row["removed"]),
    }


def _state_ms_view(state):
    """vault detail의 before/after — ms 전용 권위."""
    return {
        "trim_ms": [state["trim_start_ms"], state["trim_end_ms"]],
        "excluded_ranges_ms": state["excluded_ranges"],
        "removed": state["removed"],
    }


def upsert_edit_state(payload):
    """canonical 재정규화 + revision 낙관적 잠금 upsert. 반환: 전체 결과(Receipt 포함)."""
    _validate(payload)
    raw_state = {
        "anchor_start_ms": payload["anchor_start_ms"], "anchor_end_ms": payload["anchor_end_ms"],
        "trim_start_ms": payload["trim_start_ms"], "trim_end_ms": payload["trim_end_ms"],
        "excluded_ranges": payload.get("excluded_ranges") or [],
        "removed": bool(payload.get("removed", False)),
    }
    canonical, receipt = normalize(raw_state)  # 서버측 재검증 — 클라이언트 산출을 신뢰하지 않는다
    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    con = _connect()
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM fragment_edit_state WHERE program_id=? AND timeline_item_id=?",
            (payload["program_id"], payload["timeline_item_id"])).fetchone()
        if row is None:
            esid = payload.get("edit_state_id") or f"ES_{uuid.uuid4().hex[:12].upper()}"
            before = {"trim_start_ms": payload["anchor_start_ms"], "trim_end_ms": payload["anchor_end_ms"],
                      "excluded_ranges": [], "removed": False}
            revision = 1
            con.execute(
                """INSERT INTO fragment_edit_state
                   (edit_state_id, schema_version, program_id, timeline_item_id, source_id,
                    anchor_start_ms, anchor_end_ms, parent_fragment_id, carried_from_item_id, occurrence,
                    trim_start_ms, trim_end_ms, excluded_ranges_json, removed, revision, last_origin,
                    created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (esid, SCHEMA_VERSION, payload["program_id"], payload["timeline_item_id"],
                 payload["source_id"], canonical["anchor_start_ms"], canonical["anchor_end_ms"],
                 payload.get("parent_fragment_id"), payload.get("carried_from_item_id"),
                 int(payload.get("occurrence", 0)),
                 canonical["trim_start_ms"], canonical["trim_end_ms"],
                 json.dumps(canonical["excluded_ranges"], separators=(",", ":")),
                 int(canonical["removed"]), revision, payload["origin"], now, now))
        else:
            # anchor 불변 — 기존 행의 anchor를 절대 덮어쓰지 않는다 (v0.4 §6)
            client_rev = payload.get("revision")
            if client_rev != row["revision"]:
                raise EditStateError("revision_conflict",
                                     f"낡은 revision: client={client_rev} current={row['revision']}",
                                     http_status=409, extra={"current_revision": row["revision"]})
            esid = row["edit_state_id"]
            before = _row_to_state(row)
            revision = row["revision"] + 1
            canonical["anchor_start_ms"] = row["anchor_start_ms"]
            canonical["anchor_end_ms"] = row["anchor_end_ms"]
            con.execute(
                """UPDATE fragment_edit_state SET trim_start_ms=?, trim_end_ms=?,
                   excluded_ranges_json=?, removed=?, revision=?, last_origin=?, updated_at=?
                   WHERE edit_state_id=?""",
                (canonical["trim_start_ms"], canonical["trim_end_ms"],
                 json.dumps(canonical["excluded_ranges"], separators=(",", ":")),
                 int(canonical["removed"]), revision, payload["origin"], now, esid))
        con.commit()
    except sqlite3.OperationalError as e:
        raise EditStateError("table_missing", f"fragment_edit_state 접근 불가: {e}", http_status=503)
    finally:
        con.close()

    # 이력 — vault_events (v0.4 §7 detail 계약, ms 권위·ds 파생)
    detail = {
        "schema_version": SCHEMA_VERSION,
        "edit_state_id": esid,
        "timeline_item_id": payload["timeline_item_id"],
        "command_type": payload["command_type"],
        "before": _state_ms_view(before),
        "after": _state_ms_view(canonical),
        "origin": payload["origin"],
    }
    if payload["command_type"] == "INHERIT":
        detail["source_item_id"] = payload["source_item_id"]
        detail["target_item_id"] = payload["target_item_id"]
    event_added = 0
    try:
        from engine import fragment_vault as _fv
        event_added = _fv.record_events([{
            "source_id": payload["source_id"],
            "start": canonical["anchor_start_ms"] / 1000.0,
            "end": canonical["anchor_end_ms"] / 1000.0,
            "fragment_id": payload.get("parent_fragment_id"),
            "event_kind": "edit_command",
            # ref는 사건 단위 유일 키 — vault_events의 dedup 인덱스(kind,ref,anchor,ds)와
            # "이력 전체" 요구의 양립: revision 스탬프 포함. detail.edit_state_id = §7 그대로.
            "ref_id": f"{esid}#r{revision}",
            "program_id": payload["program_id"],
            "detail": detail,
        }])
    except Exception as e:  # 이력 실패는 상태 저장을 되돌리지 않되 정직 표기
        detail["_event_error"] = str(e)

    spans = compile_spans(canonical)
    return {
        "ok": True, "edit_state_id": esid, "revision": revision,
        "canonical": canonical, "receipt": receipt,
        "spans": spans, "ed_ids": ed_ids(esid, spans),
        "vault_event_added": event_added,
    }


def list_edit_states(program_id):
    """프로그램의 현재 편집 상태 전량 + 컴파일 결과 동봉 (읽기 전용)."""
    con = _connect()
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT * FROM fragment_edit_state WHERE program_id=? ORDER BY timeline_item_id",
            (program_id,)).fetchall()
    except sqlite3.OperationalError:
        return []  # Cutover 전 운영 DB — 테이블 부재는 빈 목록 (읽기 경로 무해)
    finally:
        con.close()
    out = []
    for row in rows:
        state = _row_to_state(row)
        state["anchor_start_ms"] = row["anchor_start_ms"]
        state["anchor_end_ms"] = row["anchor_end_ms"]
        spans = compile_spans(state)
        out.append({
            "edit_state_id": row["edit_state_id"],
            "program_id": row["program_id"],
            "timeline_item_id": row["timeline_item_id"],
            "source_id": row["source_id"],
            "parent_fragment_id": row["parent_fragment_id"],
            "carried_from_item_id": row["carried_from_item_id"],
            "occurrence": row["occurrence"],
            "anchor_start_ms": row["anchor_start_ms"], "anchor_end_ms": row["anchor_end_ms"],
            "trim_start_ms": row["trim_start_ms"], "trim_end_ms": row["trim_end_ms"],
            "excluded_ranges": state["excluded_ranges"],
            "removed": state["removed"],
            "revision": row["revision"], "last_origin": row["last_origin"],
            "spans": spans, "ed_ids": ed_ids(row["edit_state_id"], spans),
        })
    return out
