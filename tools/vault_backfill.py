# -*- coding: utf-8 -*-
"""[조각 금고] 과거분 일괄 적재 — 수동/스케줄 실행 전용, 서버 부팅과 분리.

기존 backfill_all()을 main.py 부팅 경로에 두면 sources가 늘수록 시작 지연이
선형으로 커진다는 지적(2026-07-05)을 반영해 여기로 뺐다. 신규 적재는
조각화 완료 시점 증분 훅(main.py의 POST /semantic-fragments)이 처리하므로,
이 스크립트는 "vault 도입 이전에 이미 존재하던 원본"을 한 번 채워 넣는 용도다.

실행: python tools/vault_backfill.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ccut_backend"))


def backfill_events():
    """[조각 이력 소급] 현존 원천 3곳에서 과거 사건을 복원해 vault_events에 기록.
    ①proposals.sequence(생존 제안) → adopted  ②edit_overlay → edited
    ③크레딧 매니페스트(storage/archive/*.json) → exported. 멱등."""
    import json
    import sqlite3
    from engine import fragment_vault as fv
    con = sqlite3.connect(fv.DB_PATH)
    prog_name = dict(con.execute("SELECT program_id, name FROM programs"))
    events = []
    # ① 생존 제안의 채택
    for pid, prid, mode, seq_j in con.execute(
            "SELECT program_id, proposal_id, mode, sequence FROM proposals "
            "WHERE sequence IS NOT NULL"):
        try:
            seq = json.loads(seq_j) if isinstance(seq_j, str) else (seq_j or [])
        except Exception:
            continue
        pname = prog_name.get(pid)
        for s in seq:
            events.append({"source_id": s.get("source_id"),
                           "start": s.get("start"), "end": s.get("end"),
                           "fragment_id": s.get("fragment_id"),
                           "event_kind": "adopted", "ref_id": prid,
                           "program_id": pid, "program_name": pname,
                           "proposal_id": prid,
                           "proposal_name": (f"{pname} · {mode}안" if pname and mode else None),
                           "detail": {"mode": mode, "origin": "backfill"}})
    # ② 정밀조정 이력 (조각 원 경계는 semantic_fragments에서 역조회, 없으면 overlay 좌표)
    sf_span = {fid: (st, en) for fid, st, en in con.execute(
        "SELECT fragment_id, start, end FROM semantic_fragments")}
    for oid, sid, fid, es, ee, etype, pid in con.execute(
            "SELECT overlay_id, source_id, fragment_id, effective_start_sec, "
            "effective_end_sec, edit_type, program_id FROM edit_overlay"):
        st, en = sf_span.get(fid, (es, ee))
        events.append({"source_id": sid, "start": st, "end": en, "fragment_id": fid,
                       "event_kind": "edited", "ref_id": oid,
                       "program_id": pid, "program_name": prog_name.get(pid),
                       "detail": {"edit_type": etype, "after": [es, ee],
                                  "origin": "backfill"}})
    # ③ 크레딧 매니페스트의 방송 이력
    adir = os.path.join(os.path.dirname(fv.BACKEND_DIR), "storage", "archive")
    if os.path.isdir(adir):
        for fn in os.listdir(adir):
            if not fn.endswith(".json"):
                continue
            try:
                m = json.load(open(os.path.join(adir, fn), encoding="utf-8"))
            except Exception:
                continue
            for c in (m.get("clips") or []):
                fid = str(c.get("fragment_id", ""))
                csid = ("SRC_" + fid.split("_SRC_")[-1].split("_")[0]
                        if "_SRC_" in fid else None)
                if not csid:
                    continue
                events.append({"source_id": csid, "start": c.get("start"),
                               "end": c.get("end"), "fragment_id": fid,
                               "event_kind": "exported", "ref_id": m.get("render_id") or fn,
                               "program_id": (m.get("program") or {}).get("program_id"),
                               "program_name": (m.get("program") or {}).get("name"),
                               "proposal_id": m.get("proposal_id"),
                               "proposal_name": m.get("display_name")})
    con.close()
    n = fv.record_events(events)
    print(f"[VAULT-EVENT] 소급: 후보 {len(events)}건 → 신규 기록 {n}건 (멱등)")
    return n


def main():
    from engine import fragment_vault as fv
    r = fv.backfill_all()
    n_dead = fv.mark_source_alive()
    print(f"[VAULT] 완료: sources={r['sources']} 신규={r['inserted']} 병합={r['merged']} "
          f"원본유실={n_dead}")
    backfill_events()
    print(fv.stats())
    return 0


if __name__ == "__main__":
    sys.exit(main())
