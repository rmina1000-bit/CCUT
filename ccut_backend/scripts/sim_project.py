"""[NIGHT-1 2026-08-08] 시뮬레이션 전용 프로젝트 — 실 프로젝트를 안 건드린다.

국장 지시: "실제 DB에 흔적이 남는 실행은 시뮬레이션용 프로젝트에서만.
실 프로젝트(Daffodil·Marigold·Clover) 오염 금지."

천 명이 아무 말이나 하면 원고가 바뀌고 wish 가 쌓이고 Receipt 가 남는다.
그걸 실 프로젝트에 남기면 국장의 작업이 오염된다. 그래서 사본을 만든다.

무엇을 복제하나 (새 테이블 0 · 스키마 변경 0):
  programs         행 하나          — 새 program_id
  project_sources  같은 source 를 가리킴 — 원본 영상·조각은 공유(읽기만)
  story_approval   승인 원고 복사     — 이게 있어야 편집 손이 산다

지우기도 이 파일이 한다 — 밤이 끝나면 흔적을 걷어낸다.
"""
import argparse
import datetime
import sqlite3
import sys

DB = "D:/CCUT1.0.4/ccut_backend/ccut_app.db"
SIM_PREFIX = "proj_sim"


def _con():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def create(src_program, sim_id, name):
    con = _con()
    try:
        row = con.execute("SELECT * FROM programs WHERE program_id=?",
                          (src_program,)).fetchone()
        if not row:
            print(f"원본 없음: {src_program}")
            return False
        now = datetime.datetime.now().isoformat()
        con.execute("DELETE FROM programs WHERE program_id=?", (sim_id,))
        con.execute(
            "INSERT INTO programs (program_id, name, fragments_sequence, status, "
            " last_updated_at, created_at, schema_version) VALUES (?,?,?,?,?,?,?)",
            (sim_id, name, row["fragments_sequence"] or "[]",
             row["status"], now, now, row["schema_version"]))
        con.execute("DELETE FROM project_sources WHERE program_id=?", (sim_id,))
        n = 0
        for s in con.execute("SELECT source_id, display_order FROM project_sources "
                             "WHERE program_id=?", (src_program,)).fetchall():
            con.execute("INSERT INTO project_sources (program_id, source_id, "
                        "display_order, added_at) VALUES (?,?,?,?)",
                        (sim_id, s["source_id"], s["display_order"], now))
            n += 1
        # 승인 원고 — 이게 없으면 편집 손이 "아직 원고가 없어요"만 낸다
        con.execute("DELETE FROM story_approval WHERE program_id=?", (sim_id,))
        ap = con.execute(
            "SELECT * FROM story_approval WHERE program_id=? AND superseded_by IS NULL "
            "ORDER BY approval_id DESC LIMIT 1", (src_program,)).fetchone()
        cnt = 0
        if ap:
            con.execute(
                "INSERT INTO story_approval (program_id, sequence_hash, mode, "
                " fragment_ids, item_count, running_ms, actor, approved_at, note) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (sim_id, ap["sequence_hash"], ap["mode"], ap["fragment_ids"],
                 ap["item_count"], ap["running_ms"], "sim", now,
                 f"[SIM] {src_program} 복제"))
            cnt = ap["item_count"]
        con.commit()
        print(f"만듦: {sim_id} ({name}) · 소스 {n}개 · 승인 원고 {cnt}조각")
        return True
    finally:
        con.close()


def drop(sim_id):
    """밤이 끝나면 흔적을 걷는다 — 원본 영상·조각은 건드리지 않는다."""
    if not sim_id.startswith(SIM_PREFIX):
        print(f"거부: {sim_id} 는 시뮬 프로젝트가 아니다")
        return False
    con = _con()
    try:
        n = {}
        for t, col in (("programs", "program_id"), ("project_sources", "program_id"),
                       ("story_approval", "program_id"),
                       ("project_timeline", "program_id"),
                       ("fragment_edit_state", "program_id")):
            try:
                c = con.execute(f"DELETE FROM {t} WHERE {col}=?", (sim_id,))
                n[t] = c.rowcount
            except sqlite3.OperationalError as e:
                n[t] = f"skip({e})"
        con.commit()
        print(f"지움: {sim_id} → {n}")
        return True
    finally:
        con.close()


def status(sim_id):
    con = _con()
    try:
        for t in ("programs", "project_sources", "story_approval",
                  "project_timeline", "fragment_edit_state"):
            try:
                c = con.execute(f"SELECT COUNT(*) FROM {t} WHERE program_id=?",
                                (sim_id,)).fetchone()[0]
                print(f"  {t:22} {c}")
            except sqlite3.OperationalError:
                print(f"  {t:22} (테이블 없음)")
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["create", "drop", "status"])
    ap.add_argument("--from", dest="src", default="proj_ff8c890650e4")
    ap.add_argument("--id", default="proj_sim_night1")
    ap.add_argument("--name", default="[SIM] 천 명의 밤")
    a = ap.parse_args()
    if a.cmd == "create":
        sys.exit(0 if create(a.src, a.id, a.name) else 1)
    if a.cmd == "drop":
        sys.exit(0 if drop(a.id) else 1)
    status(a.id)
