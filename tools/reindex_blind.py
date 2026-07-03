# -*- coding: utf-8 -*-
"""[SENSOR-REPAIR] 인덱스 공백(BLIND/PARTIAL) 프로젝트 일괄 재인덱싱.

배경(2026-07-04): AUTO-REINDEX가 SQLite 잠금으로 연쇄 실패 → 16개 중 12개
프로젝트가 센서 공백 → hub judge가 장님 판정(keep 과소/0) → honest-empty 빈발.
busy_timeout 수리 후, 남은 공백을 이 러너로 상환한다.

사용: python tools/reindex_blind.py [--dry]
  - semantic_fragments 대비 fragment_index 커버리지 90% 미만 소스만 재인덱싱
  - 소스 단위 순차 (VL 포함, GPU 경합 방지)
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "ccut_backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main(dry=False):
    from engine.fragment_indexer import reindex_source
    con = sqlite3.connect("ccut_app.db")
    rows = list(con.execute("""
        SELECT sf.source_id, COUNT(DISTINCT sf.fragment_id) AS n_sf,
               COUNT(DISTINCT fi.fragment_id) AS n_idx
        FROM semantic_fragments sf
        LEFT JOIN fragment_index fi ON fi.fragment_id = sf.fragment_id
        GROUP BY sf.source_id
    """))
    con.close()
    targets = [(sid, n_sf, n_idx) for sid, n_sf, n_idx in rows
               if n_sf > 0 and n_idx < n_sf * 0.9]
    print(f"[SENSOR-REPAIR] targets={len(targets)} / total_sources={len(rows)}")
    for sid, n_sf, n_idx in targets:
        print(f"[SENSOR-REPAIR] {sid} coverage {n_idx}/{n_sf}", flush=True)
        if dry:
            continue
        try:
            reindex_source(sid)
        except Exception as e:
            print(f"[SENSOR-REPAIR][FAIL] {sid}: {e}", flush=True)
    print("[SENSOR-REPAIR] ALL DONE", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
