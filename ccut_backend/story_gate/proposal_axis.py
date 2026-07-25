# -*- coding: utf-8 -*-
"""[PROPOSAL-AXIS-01] 제안 축 — proposal = f(승인 스냅샷, 기법팩).

실측으로 확정된 위반 (Merope, 승인 id=51):
    승인 11조각 / 제안 A 9조각(교집합 2) / 제안 B 15조각(교집합 7) / A∩B = 2
    → 승인 시퀀스가 제안 생성에 전혀 들어가지 않았다. engine/ 전체에 승인 참조 0건.

이 모듈의 계약:
    조각·순서는 **승인 스냅파샷이 유일 출처**다 (story_approval.fragment_ids, live 행).
      선정(HRS)·재정렬(arrange/hook_first) 결과는 채택하지 않는다 — 덮어쓴다.
    A/B가 갈리는 축은 **기법팩 하나**뿐이다 (technique_id).
      현재 기법은 as_is 하나이므로 결과적으로 A == B가 된다. 그게 정상이고 정직하다.

불가침:
    INV-1  A.조각집합 == B.조각집합 == 승인 조각집합
    INV-2  A.순서     == B.순서     == 승인 순서
    INV-3  기법은 조각을 추가·삭제·재정렬하지 못한다 (경계·전환·호흡·리듬만).
"""
import json
import sqlite3

from .models import TABLE
from .service import _connect

# 현재 유일한 기법. 승인 시퀀스를 그대로 쓴다 — 경계도 손대지 않는다.
TECHNIQUE_AS_IS = "as_is"


def live_approval_snapshot(program_id):
    """유효 승인 1건의 (approval_id, fids). 없으면 (None, [])."""
    con = _connect()
    try:
        row = con.execute(
            f"SELECT approval_id, fragment_ids FROM {TABLE} "
            f"WHERE program_id=? AND superseded_by IS NULL "
            f"ORDER BY approval_id DESC LIMIT 1",
            (program_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None, []          # Cutover 전 운영 DB — 승인 없음
    finally:
        con.close()
    if row is None:
        return None, []
    try:
        fids = json.loads(row["fragment_ids"])
    except Exception:
        fids = []
    return row["approval_id"], [str(f) for f in fids if f]


def _fragment_rows(fids):
    """fid → semantic_fragments 행(dict). 승인 조각이 엔진 결과에 없을 때의 보충용.

    [PLAYSTABILITY-FIX-01 2번] video_url을 함께 채운다.
      구판은 좌표·의미만 채워 재생원(video_url)이 빠졌다 — 실측: A 11조각 중 3조각 결손
      (idx 2·4·7). 프론트 playFrag는 video_url이 없고 getVideoUrlForFrag 폴백도 실패하면
      `[PLAYFRAG][BLOCKED]`로 재생을 중단한다. 엔진 경로(proposal_engine:566-572)와 같은
      규칙(프록시 우선 → uploads)을 쓴다 — 재생원 해석이 경로마다 갈리면 안 된다.
    """
    if not fids:
        return {}
    con = _connect()
    try:
        ph = ",".join("?" for _ in fids)
        rows = con.execute(
            f'SELECT sf.fragment_id, sf.source_id, sf.start, sf."end", sf.semantic_json, '
            f'sf.structural_json, sf.continuity_json, sf.confidence, s.file_path '
            f'FROM semantic_fragments sf LEFT JOIN sources s ON s.source_id = sf.source_id '
            f'WHERE sf.fragment_id IN ({ph})',
            list(fids),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    out = {}
    for r in rows:
        def _j(v):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        out[r["fragment_id"]] = {
            "fragment_id": r["fragment_id"],
            "source_id": r["source_id"],
            "start": r["start"],
            "end": r["end"],
            "duration": (r["end"] or 0) - (r["start"] or 0),
            "duration_sec": (r["end"] or 0) - (r["start"] or 0),
            "semantic": _j(r["semantic_json"]),
            "structural": _j(r["structural_json"]),
            "continuity": _j(r["continuity_json"]),
            "confidence": r["confidence"],
            "video_url": _video_url_for(r["file_path"], r["source_id"]),
            "thumbnail_url": _thumb_url_for(r["fragment_id"]),
        }
    return out


def _video_url_for(file_path, source_id):
    """재생원 URL — 엔진 경로(proposal_engine)·원장 경로(fragment_show)와 같은 규칙."""
    try:
        from engine.fragment_show import _video_url
        return _video_url(file_path, source_id)
    except Exception:
        # 폴백: 규칙만 그대로 재현 (프록시 존재 여부는 판단하지 않는다 — 정직하게 uploads)
        import os
        from urllib.parse import quote
        name = os.path.basename(file_path or "") or f"{source_id}.mp4"
        return f"/static/uploads/{quote(name, safe='')}"


def _thumb_url_for(fragment_id):
    """썸네일 — 있으면 붙이고 없으면 None (없는 걸 있다고 하지 않는다)."""
    try:
        from engine.fragment_show import THUMBS_DIR
        import os
        return (f"/static/thumbnails/{fragment_id}.jpg"
                if os.path.exists(os.path.join(THUMBS_DIR, f"{fragment_id}.jpg")) else None)
    except Exception:
        return None


def _seq_fids(sequence):
    return [str(s.get("fragment_id")) for s in (sequence or []) if isinstance(s, dict) and s.get("fragment_id")]


def rebuild_from_approval(proposals, approval_fids, pool_fragments=None):
    """A/B의 sequence를 **승인 fids 순서 그대로** 재구성한다 (INV-1·INV-2 강제).

    조각 dict는 (1) 엔진 결과 (2) 조각 pool (3) DB 순으로 찾아 채운다 — 좌표·썸네일 등
    기존 필드를 최대한 보존해 렌더·EDL·미리보기 경로의 입력 형태를 바꾸지 않는다.
    반환: (proposals, report) — report는 조각을 못 찾은 fid 목록(정직 표기).
    """
    by_fid = {}
    for p in (proposals or []):
        for s in (p.get("sequence") or []):
            if isinstance(s, dict) and s.get("fragment_id"):
                by_fid.setdefault(str(s["fragment_id"]), s)
    for f in (pool_fragments or []):
        if isinstance(f, dict) and f.get("fragment_id"):
            by_fid.setdefault(str(f["fragment_id"]), f)

    missing = [fid for fid in approval_fids if fid not in by_fid]
    if missing:
        by_fid.update(_fragment_rows(missing))

    # [PLAYSTABILITY-FIX-01 2번] '있다'와 '재생할 수 있다'는 다르다.
    #   조각 pool(all_fragments)에는 fid가 있지만 video_url이 없다 — 그 dict가 그대로 채택되면
    #   프론트 playFrag가 `[PLAYFRAG][BLOCKED]`로 재생을 중단한다(실측: idx 2·4·7 결손).
    #   그래서 fid 부재가 아니라 **재생원 부재**를 기준으로 한 번 더 보충한다.
    playable_gap = [fid for fid in approval_fids
                    if fid in by_fid and not (by_fid[fid] or {}).get("video_url")]
    if playable_gap:
        for fid, row in _fragment_rows(playable_gap).items():
            merged = dict(by_fid[fid])          # 기존 필드(좌표·의미·썸네일) 보존
            for k in ("video_url", "thumbnail_url"):
                if not merged.get(k) and row.get(k):
                    merged[k] = row[k]
            by_fid[fid] = merged
        still = [fid for fid in playable_gap if not (by_fid[fid] or {}).get("video_url")]
        print(f"[PROPOSAL-AXIS] video_url 보충: 대상 {len(playable_gap)}건, 남은 결손 {len(still)}건"
              + (f" {still[:3]}" if still else ""))

    unresolved = [fid for fid in approval_fids if fid not in by_fid]

    for p in (proposals or []):
        p["sequence"] = [dict(by_fid[fid]) for fid in approval_fids if fid in by_fid]
        p["duration"] = round(sum(
            float(s.get("duration_sec") or s.get("duration") or 0) for s in p["sequence"]
        ), 2)
        p["technique_id"] = TECHNIQUE_AS_IS
    return proposals, {"unresolved_fids": unresolved}


def verify_or_restore(proposals, approval_fids, approval_id, program_id):
    """[2번 검산기] 저장 직전 최후 방어선.

    A·B의 fids와 순서를 승인 스냅샷과 대조한다. 하나라도 어긋나면 **저장하지 않고**
    승인 시퀀스로 되돌린 뒤 raw 로그를 남긴다. 기법이 INV-3을 위반해도 여기서 멈춘다.
    반환: (proposals, violations) — violations가 비어 있으면 통과.
    """
    violations = []
    for p in (proposals or []):
        got = _seq_fids(p.get("sequence"))
        if got == list(approval_fids):
            continue
        got_set, appr_set = set(got), set(approval_fids)
        violations.append({
            "mode": p.get("mode"),
            "proposal_id": p.get("proposal_id"),
            "technique_id": p.get("technique_id"),
            "approval_id": approval_id,
            "expected_n": len(approval_fids),
            "got_n": len(got),
            "added": sorted(got_set - appr_set)[:5],
            "removed": sorted(appr_set - got_set)[:5],
            "order_only": got_set == appr_set,
        })
        # 로그는 ASCII 안전 문자만 쓰고 실패해도 삼킨다. 콘솔 인코딩(cp949 등) 때문에
        # print가 예외를 던지면 상위 try/except가 그걸 잡아 **되돌림이 실행되지 않는다**
        # — 실측: UnicodeEncodeError('cp949') at em-dash. 보호 로직이 로그에 목숨을 걸지 않는다.
        try:
            print(
                f"[PROPOSAL-AXIS][VERIFY][RESTORE] INV violation, restoring approved sequence. "
                f"program={program_id} approval_id={approval_id} mode={p.get('mode')} "
                f"technique={p.get('technique_id')} expected_n={len(approval_fids)} got_n={len(got)} "
                f"order_only={got_set == appr_set} added={sorted(got_set - appr_set)[:3]} "
                f"removed={sorted(appr_set - got_set)[:3]}"
            )
        except Exception:
            pass
    if violations:
        proposals, _ = rebuild_from_approval(proposals, approval_fids)
        for p in (proposals or []):
            after = _seq_fids(p.get("sequence"))
            try:
                print(f"[PROPOSAL-AXIS][VERIFY][RESTORED] mode={p.get('mode')} "
                      f"n={len(after)} matches_approval={after == list(approval_fids)}")
            except Exception:
                pass
    return proposals, violations


def ensure_columns():
    """[1-1] proposals에 story_approval_id / technique_id 보장 (ADD COLUMN만)."""
    con = _connect()
    try:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(proposals)").fetchall()}
        added = []
        if "story_approval_id" not in cols:
            con.execute("ALTER TABLE proposals ADD COLUMN story_approval_id INTEGER")
            added.append("story_approval_id")
        if "technique_id" not in cols:
            con.execute("ALTER TABLE proposals ADD COLUMN technique_id TEXT")
            added.append("technique_id")
        con.commit()
        return added
    finally:
        con.close()
