# -*- coding: utf-8 -*-
"""[STORY-GATE P2] 승인 서비스 — 원고의 현재 지문(sequence_hash), 상태, 승인 기록.

진실원 (STORY-LAYER-01 A-1, 국장 승인 2026-07-25):
  원고 순서 = programs.ui_state 의 story.fids — **program 단위 하나**.
  A/B는 그 하나의 스토리를 어떻게 편집할지(기법)일 뿐, 각자의 이야기를 갖지 않는다.
  → 지문(sequence_hash)도 제안축과 무관하다 (compute_hash는 fids만 본다).
  → 승인은 "그 배열을 그 순서로 승인했다"는 기록이다.

  구판(proposalsKeyFragments[mode] = 제안별 스토리)은 폐기됐다. 분석 직후처럼
  story가 아직 없을 때만 proposals를 '씨앗'으로 읽는다 (사용자가 아무것도 누르기
  전에도 원고는 떠야 하므로) — 그 순간부터 진실원은 story.fids 하나다.

게이트 OFF일 때 이 모듈은 어떤 DB 쓰기도 하지 않는다 (테이블 생성조차 안 함).
테이블이 없으면(=Cutover 전 운영 DB) 읽기는 "승인 없음"으로 정직하게 답하고,
쓰기(approve)는 503으로 거절한다 — 운영 DB 스키마 불가침 (edit_contract와 동일 규율).
"""
import datetime
import hashlib
import json
import os
import sqlite3

from .models import TABLE

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

# 상태기계 (STORY_GATE_CONTRACT_V1 §2)
S_SCANNED = "scanned"            # 원고를 만들 재료(제안 sequence)가 아직 없음
S_DRAFT = "story_draft"          # 원고 있음, 아직 승인 안 됨
S_APPROVED = "story_approved"    # 승인 있음 + 원고가 승인 당시와 동일
S_REVIEW = "story_review"        # 승인은 있으나 원고가 그 뒤 바뀜 → 재승인 필요


class StoryGateError(Exception):
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


def mode_gate_enabled():
    return os.getenv("CCUT_MODE_GATE", "").strip().upper() == "ON"


def _ensure_mode_columns(con):
    cols = {r["name"] for r in con.execute("PRAGMA table_info(programs)").fetchall()}
    if "mode_round" not in cols:
        con.execute("ALTER TABLE programs ADD COLUMN mode_round INTEGER DEFAULT 1")
    if "mode_reopen_at" not in cols:
        con.execute("ALTER TABLE programs ADD COLUMN mode_reopen_at TEXT")


def compute_hash(fragment_ids) -> str:
    """I-3 대조 기준. 순서가 바뀌면 해시가 바뀐다 (배치도 승인 대상이므로).

    [STORY-LAYER-01 A-1] 스토리는 program 단위 하나이므로 지문에 제안축(mode)이 없다.
    구판은 mode를 섞어서 A↔B 전환만으로 승인이 stale이 됐다 — 그게 INV-1/2 위반의 씨앗.
    """
    raw = "|".join(str(f) for f in (fragment_ids or []))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def read_story_fids(ui):
    """[STORY-LAYER-01 A-1] ui_state에서 program 단위 스토리(선택 fids + 순서)를 읽는다."""
    if not isinstance(ui, dict):
        return []
    story = ui.get("story")
    fids = story.get("fids") if isinstance(story, dict) else None
    return [str(f) for f in fids if f] if isinstance(fids, list) else []


def resolve_sequence(con, program_id):
    """원고의 (mode, fragment_ids, source). 원고를 만드는 단 하나의 규칙 — ledger_r0도 이걸 쓴다.

    1순위 ui_state.story.fids — program 단위 스토리(진실원).
    2순위 proposals 테이블 씨앗 — **분석 직후에는 ui_state가 아직 NULL이다**(실측: Anemone).
      그때도 원고는 떠야 한다. 사용자가 아무것도 누르기 전이 바로 원고를 보여줄 시점이니까.
      추천안은 B(프론트 기본 선택과 동일), 없으면 A.

    반환하는 mode는 '표시용 라벨'일 뿐이다 — 스토리의 정체성이 아니다(지문에 안 들어간다).
    """
    row = con.execute("SELECT ui_state FROM programs WHERE program_id=?", (program_id,)).fetchone()
    if row is None:
        raise StoryGateError("program_not_found", f"program {program_id} 없음", http_status=404)

    mode, fids = None, []
    if row["ui_state"]:
        try:
            ui = json.loads(row["ui_state"])
            while isinstance(ui, str):
                ui = json.loads(ui)
            mode = ui.get("committedProposalId") or ui.get("selectedProposalId")
            fids = read_story_fids(ui)
        except Exception:
            pass
    if fids:
        return mode, list(fids), "ui_state"

    try:
        rows = con.execute(
            "SELECT mode, sequence FROM proposals WHERE program_id=?", (program_id,)).fetchall()
    except sqlite3.OperationalError:
        return mode, [], "none"
    by_mode = {}
    for r in rows:
        seq = r["sequence"]
        if isinstance(seq, str):
            try:
                seq = json.loads(seq)
            except Exception:
                seq = []
        by_mode[(r["mode"] or "").upper()] = seq or []
    pick = mode if mode in by_mode else ("B" if "B" in by_mode else ("A" if "A" in by_mode else None))
    if pick:
        fids = [s.get("fragment_id") for s in by_mode[pick]
                if isinstance(s, dict) and s.get("fragment_id")]
        if fids:
            return pick, fids, "proposals"

    # [GATE-LOOP-01 2-1] 3순위 — 분석 결과(조각) 시간순.
    #   왜: 제안(A/B)은 '승인된 스토리의 편집 방식'이므로 승인 전에는 만들지 않는다.
    #   그러면 스토리의 씨앗이 사라지므로, 씨앗을 제안에서 떼어 분석 결과에 둔다.
    #   전부 고른 상태에서 사용자가 빼는 방식 — 헌장의 '전사를 보고 고른다'와 같은 방향이다.
    fids = _program_fragment_fids(con, program_id)
    return mode, fids, ("fragments" if fids else "none")


def _program_fragment_fids(con, program_id):
    """이 프로그램에 붙은 소스들의 조각 fid — 소스 순서 · 그 안은 시간순."""
    try:
        rows = con.execute(
            'SELECT sf.fragment_id FROM semantic_fragments sf '
            'JOIN project_sources ps ON ps.source_id = sf.source_id '
            'WHERE ps.program_id=? ORDER BY ps.display_order, sf.start',
            (program_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows if r[0]]


def current_story(program_id):
    """지금 화면에 뜨는 원고의 (mode, fragment_ids, sequence_hash)."""
    con = _connect()
    try:
        mode, fids, _src = resolve_sequence(con, program_id)
        return mode, list(fids), compute_hash(fids)
    finally:
        con.close()


def sequence_source(program_id):
    con = _connect()
    try:
        return resolve_sequence(con, program_id)[2]
    finally:
        con.close()


def live_approval(program_id):
    """현재 유효한 승인 1건 (superseded 안 된 것). 테이블 없으면 None (쓰기 0)."""
    con = _connect()
    try:
        row = con.execute(
            f"SELECT * FROM {TABLE} WHERE program_id=? AND superseded_by IS NULL "
            f"ORDER BY approval_id DESC LIMIT 1", (program_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None  # Cutover 전 운영 DB — 테이블 부재 = 승인 없음
    finally:
        con.close()


def story_state(program_id):
    """{state, sequence_hash, mode, item_count, approved}. 읽기 전용."""
    mode, fids, h = current_story(program_id)
    appr = live_approval(program_id)
    mode_round = 1
    mode_reopen_at = None
    if mode_gate_enabled():
        con = _connect()
        try:
            _ensure_mode_columns(con)
            row = con.execute(
                "SELECT mode_round, mode_reopen_at FROM programs WHERE program_id=?",
                (program_id,),
            ).fetchone()
            if row:
                mode_round = int(row["mode_round"] or 1)
                mode_reopen_at = row["mode_reopen_at"]
            con.commit()
        finally:
            con.close()
    if not fids:
        state = S_SCANNED
    elif appr is None:
        state = S_DRAFT
    elif mode_reopen_at and str(mode_reopen_at) > str(appr["approved_at"]):
        state = S_REVIEW
    elif appr["sequence_hash"] == h:
        state = S_APPROVED
    else:
        state = S_REVIEW  # 승인 후 원고가 바뀜 — 재승인 전까지 렌더 금지
    return {
        "story_state": state,
        "sequence_hash": h,
        "mode": mode,
        "item_count": len(fids),
        "mode_round": mode_round,
        "mode_reopen_at": mode_reopen_at,
        "sequence_source": sequence_source(program_id),  # ui_state | proposals | none (정직 표기)
        "approved": ({
            "approval_id": appr["approval_id"],
            "sequence_hash": appr["sequence_hash"],
            "approved_at": appr["approved_at"],
            "actor": appr["actor"],
            "stale": appr["sequence_hash"] != h,
            # [APPROVAL-SYNC 2026-08-03] 승인 당시 조각 수 — 이미 조회하고 있었는데(:324)
            #   응답에만 안 실려 프론트가 "무엇이 달라졌는지"를 말할 수 없었다.
            #   실측(Freesia): 승인 9조각 vs 현재 8조각인데 화면에는 그 차이가 어디에도 없고
            #   채팅만 "원고를 먼저 승인해 주세요"라고 했다. 무엇을 승인하라는지 알 수 없다.
            "item_count": appr["item_count"],
        } if appr else None),
    }


def is_render_allowed(program_id) -> bool:
    """I-1: 렌더가 허용되는가 = 유효 승인이 있고, 그 승인이 지금 원고와 같은가."""
    try:
        st = story_state(program_id)
    except StoryGateError:
        return False
    return st["story_state"] == S_APPROVED


def is_edit_locked(program_id) -> bool:
    return mode_gate_enabled() and story_state(program_id)["story_state"] == S_APPROVED


def reopen_review(program_id):
    if not mode_gate_enabled():
        raise StoryGateError("CCUT_MODE_GATE_OFF", "CCUT_MODE_GATE is OFF", http_status=403)
    now = datetime.datetime.now().isoformat()
    con = _connect()
    try:
        row = con.execute("SELECT program_id FROM programs WHERE program_id=?", (program_id,)).fetchone()
        if row is None:
            raise StoryGateError("program_not_found", f"program {program_id} not found", http_status=404)
        _ensure_mode_columns(con)
        con.execute(
            "UPDATE programs SET mode_round=COALESCE(mode_round, 1)+1, mode_reopen_at=? WHERE program_id=?",
            (now, program_id),
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "program_id": program_id, **story_state(program_id)}


def approve(program_id, sequence_hash, actor="user", running_ms=None, note=None):
    """승인 기록. I-5: actor는 사람만. 409 = 그새 원고가 바뀜(낙관적 잠금)."""
    if actor != "user":
        raise StoryGateError("actor_not_user", "승인은 사람만 한다 (I-5)", http_status=403)

    mode, fids, h = current_story(program_id)
    if not fids:
        raise StoryGateError("no_story", "승인할 원고가 없다 (조각 0개)", http_status=409,
                             sequence_hash=h)
    if sequence_hash and sequence_hash != h:
        # 사용자가 본 원고와 지금 원고가 다르다 — 못 본 것을 승인시키지 않는다.
        raise StoryGateError("sequence_changed",
                             "그새 원고가 바뀌었습니다. 다시 보고 저장해 주세요.",
                             http_status=409, expected=h, received=sequence_hash)

    now = datetime.datetime.now().isoformat()
    con = _connect()
    try:
        prev = con.execute(
            f"SELECT approval_id FROM {TABLE} WHERE program_id=? AND superseded_by IS NULL",
            (program_id,)).fetchall()
        # uq_story_approval_live(program_id) WHERE superseded_by IS NULL 은 프로그램당
        # '유효한 승인 1건'을 DB가 강제한다. 그래서 새 행을 NULL로 바로 넣으면 이전 승인과
        # 순간적으로 둘 다 NULL이 되어 UNIQUE 위반이 난다.
        # → 새 행을 sentinel(-1)로 넣고 → 이전 승인들을 무효화한 뒤 → 새 행만 NULL로 푼다.
        #   (SQLite는 문장 단위로 제약을 검사하므로 이 순서면 NULL이 항상 최대 1건)
        cur = con.execute(
            f"INSERT INTO {TABLE} (program_id, sequence_hash, mode, fragment_ids, item_count, "
            f"running_ms, actor, approved_at, superseded_by, note) "
            f"VALUES (?,?,?,?,?,?,?,?,-1,?)",
            (program_id, h, mode, json.dumps(fids, ensure_ascii=False), len(fids),
             running_ms, actor, now, note))
        new_id = cur.lastrowid
        # append-only: 이전 승인은 지우지 않고 무효화 표시만 (무엇을 승인했었는지가 남아야 한다)
        for r in prev:
            con.execute(f"UPDATE {TABLE} SET superseded_by=? WHERE approval_id=?",
                        (new_id, r["approval_id"]))
        con.execute(f"UPDATE {TABLE} SET superseded_by=NULL WHERE approval_id=?", (new_id,))
        con.commit()
    except sqlite3.OperationalError as e:
        raise StoryGateError("table_missing",
                             f"{TABLE} 접근 불가 (Cutover 전): {e}", http_status=503)
    finally:
        con.close()

    return {
        "ok": True, "approval_id": new_id, "program_id": program_id,
        "sequence_hash": h, "mode": mode, "item_count": len(fids),
        "superseded": [r["approval_id"] for r in prev],
        "approved_at": now, "actor": actor,
        "story_state": S_APPROVED,
    }


def history(program_id):
    con = _connect()
    try:
        rows = con.execute(
            f"SELECT approval_id, sequence_hash, mode, item_count, actor, approved_at, "
            f"superseded_by FROM {TABLE} WHERE program_id=? ORDER BY approval_id DESC",
            (program_id,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
