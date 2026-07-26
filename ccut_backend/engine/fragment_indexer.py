"""[FRAGMENT-SEARCH 단계2] 조각 인덱서.

각 조각을 검색 가능한 자산으로 만든다:
  키프레임(ffmpeg) -> 시각묘사(Qwen VL) -> 통합텍스트 -> 임베딩 -> fragment_index 저장

설계 원칙:
- read 분리: 기존 fragments/evidence_board/semantic_fragments/proposals는 읽기만.
  쓰기는 신규 fragment_index 테이블에만 (라이브 DB 오염 0).
- 2단계: (A) 메타+transcript 즉시 인덱싱 (빠름)  (B) VL 시각묘사 보강 (느림, 선택적)
- 우선순위: is_curated(실제 내보낸 조각) 먼저.
- graceful: VL/ffmpeg 실패해도 메타 기반으로 인덱싱은 완료.
"""
import os
import json
import subprocess
import datetime
import sqlite3

import numpy as np

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")
KEYFRAME_DIR = os.path.join(BACKEND_DIR, "storage", "search_keyframes")


# ---------- 자산성(curated) 판정 ----------

def compute_curated_set(con) -> set:
    """실제 내보낸(export) 조각 = 진짜 자산. export_input.clips 기준."""
    cur = con.cursor()
    curated = set()
    cur.execute("SELECT clips FROM export_input WHERE clips IS NOT NULL")
    for (clips,) in cur.fetchall():
        if not clips:
            continue
        try:
            arr = json.loads(clips) if isinstance(clips, str) else clips
            for item in arr:
                fid = item.get("fragment_id") or item.get("id")
                if fid:
                    curated.add(fid)
        except Exception:
            pass
    return curated


# ---------- 조각 메타 수집 ----------

def load_fragment_rows(con, source_filter=None):
    """fragments + evidence_board(keyframe/motion/text) + semantic(role) 조인 수집."""
    cur = con.cursor()
    rows = {}

    q = "SELECT fragment_id, source_id, start_time, end_time, duration, intelligence FROM fragments"
    params = ()
    if source_filter:
        q += " WHERE source_id = ?"
        params = (source_filter,)
    cur.execute(q, params)
    for fid, sid, s, e, dur, intel in cur.fetchall():
        role, hook, transcript = None, 0.0, None
        if intel:
            try:
                d = json.loads(intel) if isinstance(intel, str) else intel
                role = d.get("role")
                hook = float(d.get("hook_score") or 0.0)
                transcript = d.get("transcript")
            except Exception:
                pass
        rows[fid] = {
            "fragment_id": fid, "source_id": sid,
            "start": s or 0.0, "end": e or 0.0, "duration": dur or 0.0,
            "role": role, "hook_score": hook, "transcript": transcript,
            "motion_score": 0.0, "keyframe": None,
        }

    # evidence_board 보강
    cur.execute("SELECT fragment_id, motion_score, keyframe, text FROM evidence_board")
    for fid, motion, kf, text in cur.fetchall():
        if fid in rows:
            rows[fid]["motion_score"] = motion or 0.0
            rows[fid]["keyframe"] = kf
            if not rows[fid]["transcript"] and text:
                rows[fid]["transcript"] = text

    return rows


def _loadjson(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def load_semantic_fragment_rows(con, source_filter=None):
    """[R2 재키잉] semantic_fragments(SF) 단위 수집.

    제안엔진(proposal_engine)이 쓰는 바로 그 조각(SF_*)을 인덱싱한다.
    → fragment_index 의 fragment_id 가 제안풀 id 와 1:1 동일 → focus 를
      source 다리(by_source)가 아니라 클립별로 직접 매칭할 수 있다.
    VF(fragments) 경로(load_fragment_rows)는 가역성 위해 남겨둠(unit='vf').
    """
    cur = con.cursor()
    rows = {}
    q = ('SELECT fragment_id, source_id, start, "end", semantic_json, structural_json '
         'FROM semantic_fragments')
    params = ()
    if source_filter:
        q += " WHERE source_id = ?"
        params = (source_filter,)
    cur.execute(q, params)
    for fid, sid, s, e, sem_j, str_j in cur.fetchall():
        sem = _loadjson(sem_j) or {}
        stru = _loadjson(str_j) or {}
        dur = stru.get("duration")
        if dur is None:
            dur = max(0.0, (e or 0.0) - (s or 0.0))
        # 텍스트: 요약 + transcript_refs 합성 (시각묘사는 아래 VL 단계가 채움)
        transcript = sem.get("summary") or None
        refs = sem.get("transcript_refs")
        if isinstance(refs, list) and refs:
            parts = []
            for x in refs:
                if isinstance(x, dict):
                    parts.append(str(x.get("text") or x.get("transcript") or ""))
                else:
                    parts.append(str(x))
            joined = " ".join(p for p in parts if p).strip()
            if joined:
                transcript = (str(transcript) + " " + joined).strip() if transcript else joined
        hook_score = stru.get("hook_score")
        if hook_score is None:
            hook_score = sem.get("hook_score")
        if hook_score is None:
            hook_score = stru.get("edit_value")

        rows[fid] = {
            "fragment_id": fid, "source_id": sid,
            "start": s or 0.0, "end": e or 0.0, "duration": dur or 0.0,
            "role": stru.get("role"),
            "hook_score": float(hook_score or 0.0),
            "transcript": transcript,
            # [PUNCH-1 P1] 상수 0.0 제거 — "모른다"를 0으로 위장하지 않는다(INV-4).
            #   아래 _inject_motion_scores가 SF 조각 경계로 실측해 채우고, 실패하면 NULL로 남는다.
            #   구판은 여기 0.0이 박혀 670/670이 0이었고 재인덱싱이 그 0을 계속 되밀었다.
            "motion_score": None, "keyframe": None,
        }
    _inject_motion_scores(con, rows)
    return rows


def _inject_motion_scores(con, rows):
    """[PUNCH-1 P1] SF 조각 경계로 motion을 실측해 주입 (소스당 곡선 1회 추출).

    VF(evidence_board) 경유는 청크 1개 값이 여러 조각에 복사돼 분별력이 없었다
    (SIGNAL-WAKE-2 X1: 같은 VF 안 두 조각이 SAME). 여기서는 조각 경계로 직접 접는다.
    곡선 추출 실패·구간 샘플 0이면 None을 그대로 둔다 — 0 위장 금지(INV-4).
    """
    from collections import defaultdict
    try:
        from engine.signal_processor import extract_motion_curve, motion_scores_for_spans
    except Exception as e:
        print(f"[INDEXER][MOTION] signal_processor 로드 실패 — motion NULL 유지: {e}")
        return
    by_src = defaultdict(list)
    for fid, r in rows.items():
        by_src[r["source_id"]].append(fid)
    for sid, fids in by_src.items():
        path = source_video_path(con, sid)
        if not path:
            print(f"[INDEXER][MOTION] {sid}: 원본 없음 — motion NULL 유지 ({len(fids)}조각)")
            continue
        fids.sort(key=lambda f: rows[f]["start"])
        spans = [(rows[f]["start"], rows[f]["end"]) for f in fids]
        dur = max((e for _, e in spans), default=0.0)
        try:
            curve = extract_motion_curve(path, dur)
            vals = motion_scores_for_spans(path, dur, spans, curve=curve)
        except Exception as e:
            print(f"[INDEXER][MOTION] {sid}: 추출 실패 — motion NULL 유지: {e}")
            continue
        n_null = sum(1 for v in vals if v is None)
        for f, v in zip(fids, vals):
            rows[f]["motion_score"] = v
        print(f"[INDEXER][MOTION] {sid}: {len(fids)}조각 채움 (NULL {n_null}, curve {len(curve)} samples)")


def ensure_places_schema(con):
    """[PLACE P1] 장소 라벨 저장 — '재생성 가능한 파생 캐시'.
    person_faces(사용자 축복, 무단삭제 불가침)와 달리 이 테이블은 인덱스 시점에
    keyframe 묘사에서 기계 파생되며, 재인덱스 때마다 지우고 다시 만든다."""
    con.execute("""CREATE TABLE IF NOT EXISTS fragment_places (
        fragment_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        place_code TEXT NOT NULL,
        place_label TEXT NOT NULL,
        confidence REAL NOT NULL,
        evidence_json TEXT,
        analyzer TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        updated_at TEXT,
        PRIMARY KEY(fragment_id, place_code))""")
    con.commit()


def _reset_index(con, source_filter=None):
    """[R2] 단위 전환(VF→SF) 시 스테일 행 제거. fragment_id 네임스페이스가
    바뀌므로 첫 SF 재빌드에서 1회 비워 고아 VF 행을 정리한다."""
    cur = con.cursor()
    if source_filter:
        cur.execute("DELETE FROM fragment_index WHERE source_id = ?", (source_filter,))
        n = cur.rowcount
    else:
        cur.execute("DELETE FROM fragment_index")
        n = cur.rowcount
    con.commit()
    return n


# ---------- 키프레임 추출 ----------

def source_video_path(con, source_id) -> str:
    cur = con.cursor()
    cur.execute("SELECT file_path FROM sources WHERE source_id = ?", (source_id,))
    r = cur.fetchone()
    if r and r[0] and os.path.exists(r[0]):
        return r[0]
    # 프록시 폴백
    proxy = os.path.join(BACKEND_DIR, "storage", "proxies", f"{source_id}_proxy.mp4")
    if os.path.exists(proxy):
        return proxy
    return None


def extract_keyframe(video_path, mid_sec, out_path) -> bool:
    """조각 중간 시각에서 1프레임 추출 (512px). 성공 True."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(max(0.0, mid_sec)), "-i", video_path,
             "-frames:v", "1", "-vf", "scale=512:-1", out_path],
            capture_output=True, timeout=30,
        )
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception:
        return False


# ---------- 검색 텍스트 합성 ----------

def build_search_text(meta: dict, visual_desc: str) -> str:
    parts = []
    if visual_desc:
        parts.append(visual_desc)
    if meta.get("transcript"):
        parts.append(str(meta["transcript"]))
    if meta.get("role"):
        parts.append(f"role:{meta['role']}")
    return " | ".join(parts).strip()


# ---------- 메인 인덱싱 ----------

def index_fragments(source_filter=None, use_vl=True, only_curated=False,
                    limit=None, vl_timeout=60, verbose=True, dry_run=False,
                    unit="sf", reset=False):
    """조각 인덱싱 실행.

    unit: 'sf' = semantic_fragments(제안풀과 1:1, R2 기본) / 'vf' = fragments(레거시)
    use_vl: Qwen VL 시각묘사 사용 (False면 메타만)
    only_curated: 내보낸 조각만
    reset: 인덱싱 전 fragment_index 비우기(단위 전환 시 스테일 행 정리)
    dry_run: DB 쓰기 없이 결과만 반환
    """
    from engine import embedding_model as em
    from engine import fragment_vl_describer as vl

    # [LOCK-FIX] 제안 저장(SQLAlchemy) 등 다른 writer와 경합 시 즉사하지 않고 대기.
    # (AUTO-REINDEX "database is locked" 연쇄 실패 → 센서 공백 → judge keep=0 의 뿌리)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    if not dry_run and reset:
        n = _reset_index(con, source_filter)
        # [LOCK-FIX2] purge 직후 즉시 commit — VL 수 분 동안 write lock을 쥐고
        # 제안 저장(SQLAlchemy)을 굶기던 장기 트랜잭션 제거 (PROJECT PROPOSAL ERROR: locked)
        con.commit()
        if verbose:
            print(f"[INDEXER] reset: fragment_index 행 {n}개 삭제 "
                  f"(scope={'source' if source_filter else 'ALL'})")
    if unit == "vf":
        rows = load_fragment_rows(con, source_filter)
    else:
        rows = load_semantic_fragment_rows(con, source_filter)
    curated = compute_curated_set(con)

    targets = list(rows.values())
    if only_curated:
        targets = [r for r in targets if r["fragment_id"] in curated]
    # curated 우선 정렬
    targets.sort(key=lambda r: (r["fragment_id"] not in curated, -r["hook_score"]))
    if limit:
        targets = targets[:limit]

    vl_up = vl.is_ollama_up() if use_vl else False
    if verbose:
        print(f"[INDEXER] unit={unit} 대상 {len(targets)}개, curated={len(curated)}, "
              f"VL={'on' if vl_up else 'off'}, dry_run={dry_run}")

    results = []
    vl_ok, vl_fail = 0, 0
    for i, meta in enumerate(targets):
        fid = meta["fragment_id"]
        visual_desc, desc_source = None, "meta_fallback"

        if vl_up:
            vpath = source_video_path(con, meta["source_id"])
            if vpath:
                mid = (meta["start"] + meta["end"]) / 2.0
                kf_out = os.path.join(KEYFRAME_DIR, f"{fid}.jpg")
                if extract_keyframe(vpath, mid, kf_out):
                    res = vl.describe_keyframe(kf_out, timeout_sec=vl_timeout)
                    if res["desc"]:
                        visual_desc = res["desc"]
                        desc_source = "qwen_vl"
                        vl_ok += 1
                        meta["keyframe"] = f"/search_keyframes/{fid}.jpg"
                    else:
                        vl_fail += 1
        if not visual_desc and meta.get("transcript"):
            desc_source = "transcript"

        # [PLACE P1] 장소 파생 — 인덱스 시점에 묘사에서 생성 (재인덱스에도 스테일 없음).
        # 구체 장소(병원/바다/...)만 "(장소:라벨)"로 desc·검색어에 주입, indoor/outdoor는
        # scene_type까지만. 묘사가 없으면 places=[] = unknown (조용한 성공 처리 금지).
        from engine import place_taxonomy as pt
        places = pt.derive_places(visual_desc)
        scene_type = places[0][0] if places else None
        if visual_desc:
            for code, label, _ev in places:
                _tag = f"(장소:{label})"
                if code not in ("indoor", "outdoor") and _tag not in visual_desc:
                    visual_desc = f"{visual_desc.rstrip()} {_tag}"

        search_text = build_search_text(meta, visual_desc)
        emb = em.encode_one(search_text) if search_text else np.zeros(em.DIM, dtype=np.float32)

        rec = {
            **meta,
            "visual_desc": visual_desc,
            "search_text": search_text,
            "desc_source": desc_source,
            "is_curated": fid in curated,
            "embedding": em.to_bytes(emb),
            "scene_type": scene_type,
            "places": places,
        }
        results.append(rec)

        if not dry_run:
            _upsert(con, rec, em)
            # [LOCK-FIX2] 조각 단위 commit — write lock 보유 시간을 ms 단위로 유지
            con.commit()

        if verbose and (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(targets)}] vl_ok={vl_ok} vl_fail={vl_fail}")

    if not dry_run:
        con.commit()
    con.close()
    if verbose:
        print(f"[INDEXER] 완료: {len(results)}개 인덱싱, vl_ok={vl_ok}, vl_fail={vl_fail}", flush=True)
    return {"indexed": len(results), "vl_ok": vl_ok, "vl_fail": vl_fail,
            "results": results if dry_run else None}


def reindex_source(source_id: str, use_vl: bool = True, verbose: bool = True) -> dict:
    """[AUTO-REINDEX] 소스 단위 purge-then-insert 재인덱싱.

    재조각화(SF 재생성)가 fragment_id를 재발급하면 옛 id 인덱스 행이 고아화되므로,
    ① 해당 source의 fragment_index 행 전부 삭제(소스 단위 purge — 고아 잔존 차단)
    ② 현재 semantic_fragments 기준 재인덱싱(VL 포함)
    ③ 완료 로그 [AUTO-REINDEX] 출력.
    기존 CLI(index_fragments) 동작은 불변 — 이 함수는 reset=True 래퍼다.
    """
    result = index_fragments(source_filter=source_id, use_vl=use_vl,
                             verbose=verbose, unit="sf", reset=True)
    print(f"[AUTO-REINDEX] source={source_id} sf={result.get('indexed', 0)} "
          f"vl_ok={result.get('vl_ok', 0)} vl_fail={result.get('vl_fail', 0)}", flush=True)
    return result


def _upsert(con, rec, em):
    cur = con.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO fragment_index
          (fragment_id, source_id, start, "end", duration, role, edit_value,
           hook_score, motion_score, visual_desc, transcript, scene_type,
           main_subjects, search_text, embedding, embedding_model, embedding_dim,
           is_curated, usage_count, keyframe, desc_source, indexed_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(fragment_id) DO UPDATE SET
           visual_desc=excluded.visual_desc, transcript=excluded.transcript,
           scene_type=excluded.scene_type,
           search_text=excluded.search_text, embedding=excluded.embedding,
           desc_source=excluded.desc_source, is_curated=excluded.is_curated,
           keyframe=excluded.keyframe, role=excluded.role,
           hook_score=excluded.hook_score, motion_score=excluded.motion_score,
           updated_at=excluded.updated_at
    """, (
        rec["fragment_id"], rec["source_id"], rec["start"], rec["end"], rec["duration"],
        rec["role"], 0.0, rec["hook_score"], rec["motion_score"],
        rec["visual_desc"], rec.get("transcript"), rec.get("scene_type"),
        json.dumps([]), rec["search_text"], rec["embedding"],
        em.MODEL_NAME, em.DIM, 1 if rec["is_curated"] else 0, 0,
        rec.get("keyframe"), rec["desc_source"], now, now,
    ))
    # [PLACE P1] 파생 캐시 재생성 — 이 fragment의 기존 장소 행을 지우고 새로 쓴다
    # (person_faces 불가침과 구별: 여기는 기계 파생물이라 삭제-재생성이 정합의 수단)
    ensure_places_schema(con)
    cur.execute("DELETE FROM fragment_places WHERE fragment_id = ?", (rec["fragment_id"],))
    for _code, _label, _ev in rec.get("places") or []:
        cur.execute(
            "INSERT OR REPLACE INTO fragment_places (fragment_id, source_id, place_code, "
            "place_label, confidence, evidence_json, analyzer, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rec["fragment_id"], rec["source_id"], _code, _label, 0.6,
             json.dumps({"keywords": _ev}, ensure_ascii=False), "rule_place_v1",
             "active", now, now))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None)
    ap.add_argument("--unit", choices=["sf", "vf"], default="sf",
                    help="sf=semantic_fragments(제안풀과 1:1, 기본) / vf=fragments(레거시)")
    ap.add_argument("--reset", action="store_true",
                    help="인덱싱 전 fragment_index 비우기 (단위 전환 1회 권장)")
    ap.add_argument("--no-vl", action="store_true")
    ap.add_argument("--curated", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    index_fragments(source_filter=args.source, use_vl=not args.no_vl,
                    only_curated=args.curated, limit=args.limit, dry_run=args.dry_run,
                    unit=args.unit, reset=args.reset)
