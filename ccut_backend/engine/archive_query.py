# -*- coding: utf-8 -*-
"""[ARCHIVE-QUERY P1] filters(인물/장소) → 조각 교집합 검색.

- person: person_faces(사용자 축복 링크) 기준 — canonical name의 모든 군집 포함
  (동명 군집은 헌장 원칙3의 의도된 구조).
- place: fragment_places(파생 캐시) 기준.
- scope: 현재 프로젝트 우선 → 없으면 아카이브 전체에서 후보를 찾아
  프로그램별 분포와 함께 반환 (포함 여부는 사용자 승인 사항 — 여기선 검색만).
- 라벨 커버리지도 함께 반환 (D분기: "장소 라벨이 아직 부족합니다" 판단 근거).
read-only — DB 쓰기 없음.
"""
import os
import sqlite3

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


def _fids_for_person(con, canonical):
    pids = [r[0] for r in con.execute(
        "SELECT person_id FROM persons WHERE status='named' AND name=?", (canonical,))]
    if not pids:
        return set()
    ph = ",".join("?" * len(pids))
    return {r[0] for r in con.execute(
        f"SELECT DISTINCT fragment_id FROM person_faces WHERE person_id IN ({ph})", pids)}


def _fids_for_place(con, code):
    try:
        return {r[0] for r in con.execute(
            "SELECT fragment_id FROM fragment_places WHERE place_code=? AND status='active'",
            (code,))}
    except sqlite3.OperationalError:
        return set()  # 테이블 미생성 = 라벨 0 (조용한 성공 처리 금지 — coverage로 드러남)


def query(filters, project_source_ids=None, db_path=None):
    """filters: [{"type":"person","value":canonical}, {"type":"place","value":code}, ...]
    반환: {scope: project|archive|none, fids: [...], by_program: {이름: n},
           coverage: {place_labeled, total}, filter_counts: {...}}"""
    con = sqlite3.connect("file:" + (db_path or DB_PATH).replace("\\", "/") + "?mode=ro",
                          uri=True)
    try:
        sets = []
        filter_counts = {}
        for f in (filters or []):
            if f.get("type") == "person":
                s = _fids_for_person(con, f.get("value") or "")
            elif f.get("type") == "place":
                s = _fids_for_place(con, f.get("value") or "")
            else:
                continue
            filter_counts[f"{f['type']}:{f['value']}"] = len(s)
            sets.append(s)
        if not sets:
            return {"scope": "none", "fids": [], "by_program": {},
                    "coverage": _coverage(con, project_source_ids), "filter_counts": {}}

        inter = set.intersection(*sets)
        # 살아있는 조각만 (재조각화 고아 제외) + source 매핑
        rows = list(con.execute(
            "SELECT sf.fragment_id, sf.source_id FROM semantic_fragments sf")) if inter else []
        alive = {fid: sid for fid, sid in rows if fid in inter}

        proj_sids = set(project_source_ids or [])
        in_proj = sorted(f for f, s in alive.items() if s in proj_sids)
        if in_proj:
            return {"scope": "project", "fids": in_proj, "by_program": {},
                    "coverage": _coverage(con, project_source_ids),
                    "filter_counts": filter_counts}

        # 아카이브 전체 — 프로그램별 분포
        src2prog = {}
        for sid, pid in con.execute("SELECT source_id, program_id FROM project_sources"):
            src2prog.setdefault(sid, []).append(pid)
        names = dict(con.execute("SELECT program_id, name FROM programs"))
        by_program = {}
        for fid, sid in alive.items():
            for pid in src2prog.get(sid, []):
                nm = names.get(pid, pid)
                by_program[nm] = by_program.get(nm, 0) + 1
        return {"scope": "archive" if alive else "none", "fids": sorted(alive.keys()),
                "by_program": by_program,
                "coverage": _coverage(con, project_source_ids),
                "filter_counts": filter_counts}
    finally:
        con.close()


def _coverage(con, project_source_ids):
    """장소 라벨 커버리지 — D분기 근거 (현재 프로젝트 범위)."""
    if project_source_ids:
        ph = ",".join("?" * len(project_source_ids))
        total = con.execute(
            f"SELECT COUNT(*) FROM fragment_index WHERE source_id IN ({ph})",
            list(project_source_ids)).fetchone()[0]
        try:
            labeled = con.execute(
                f"SELECT COUNT(DISTINCT fragment_id) FROM fragment_places WHERE source_id IN ({ph})",
                list(project_source_ids)).fetchone()[0]
        except sqlite3.OperationalError:
            labeled = 0
    else:
        total = con.execute("SELECT COUNT(*) FROM fragment_index").fetchone()[0]
        try:
            labeled = con.execute(
                "SELECT COUNT(DISTINCT fragment_id) FROM fragment_places").fetchone()[0]
        except sqlite3.OperationalError:
            labeled = 0
    return {"place_labeled": labeled, "total": total}
