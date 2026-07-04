# -*- coding: utf-8 -*-
"""[PLACE-INDEXER P1] 장소 라벨 backfill CLI — 기존 fragment_index 묘사에 소급 파생.

신규 인덱싱은 fragment_indexer가 인덱스 시점에 자동 파생하므로(스테일 불가) 이 모듈은
'이미 인덱싱된 행'의 소급용이다. VL 재분석은 하지 않는다(=묘사 없는 행은 unknown 유지,
조용한 성공 처리 금지) — VL backfill은 별도 승인 사항.

사용: python -m engine.place_indexer [--dry-run]
"""
import datetime
import json
import sqlite3
import sys

from engine import place_taxonomy as pt
from engine.fragment_indexer import DB_PATH, ensure_places_schema


def backfill(dry_run=False, verbose=True):
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    ensure_places_schema(con)
    now = datetime.datetime.now().isoformat()
    rows = list(con.execute(
        "SELECT fragment_id, source_id, visual_desc, search_text FROM fragment_index "
        "WHERE visual_desc IS NOT NULL AND length(visual_desc) > 10"))
    labeled = tagged = 0
    dist = {}
    for fid, sid, vd, st in rows:
        places = pt.derive_places(vd)
        if not places:
            continue
        labeled += 1
        scene_type = places[0][0]
        vd2, st2 = vd, st or ""
        for code, label, _ev in places:
            dist[code] = dist.get(code, 0) + 1
            tag = f"(장소:{label})"
            if code not in ("indoor", "outdoor") and tag not in vd2:
                vd2 = f"{vd2.rstrip()} {tag}"
                if label not in st2:
                    st2 = f"{st2} {label}".strip()
                tagged += 1
        if not dry_run:
            con.execute(
                "UPDATE fragment_index SET scene_type=?, visual_desc=?, search_text=?, "
                "updated_at=? WHERE fragment_id=?", (scene_type, vd2, st2, now, fid))
            con.execute("DELETE FROM fragment_places WHERE fragment_id=?", (fid,))
            for code, label, ev in places:
                con.execute(
                    "INSERT OR REPLACE INTO fragment_places (fragment_id, source_id, "
                    "place_code, place_label, confidence, evidence_json, analyzer, "
                    "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (fid, sid, code, label, 0.6,
                     json.dumps({"keywords": ev}, ensure_ascii=False),
                     "rule_place_v1", "active", now, now))
    if not dry_run:
        con.commit()
    con.close()
    if verbose:
        print(f"[PLACE-BACKFILL] 대상 {len(rows)}행(실묘사) → 라벨 {labeled}행, "
              f"구체태그주입 {tagged}건, dry_run={dry_run}")
        print(f"[PLACE-BACKFILL] 분포: {dict(sorted(dist.items(), key=lambda x: -x[1]))}")
    return {"rows": len(rows), "labeled": labeled, "tagged": tagged, "dist": dist}


if __name__ == "__main__":
    backfill(dry_run="--dry-run" in sys.argv)
