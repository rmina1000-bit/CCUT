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
                    limit=None, vl_timeout=60, verbose=True, dry_run=False):
    """조각 인덱싱 실행.

    use_vl: Qwen VL 시각묘사 사용 (False면 메타만)
    only_curated: 내보낸 조각만
    dry_run: DB 쓰기 없이 결과만 반환
    """
    from engine import embedding_model as em
    from engine import fragment_vl_describer as vl

    con = sqlite3.connect(DB_PATH)
    rows = load_fragment_rows(con, source_filter)
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
        print(f"[INDEXER] 대상 {len(targets)}개, curated={len(curated)}, "
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

        search_text = build_search_text(meta, visual_desc)
        emb = em.encode_one(search_text) if search_text else np.zeros(em.DIM, dtype=np.float32)

        rec = {
            **meta,
            "visual_desc": visual_desc,
            "search_text": search_text,
            "desc_source": desc_source,
            "is_curated": fid in curated,
            "embedding": em.to_bytes(emb),
        }
        results.append(rec)

        if not dry_run:
            _upsert(con, rec, em)

        if verbose and (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(targets)}] vl_ok={vl_ok} vl_fail={vl_fail}")

    if not dry_run:
        con.commit()
    con.close()
    if verbose:
        print(f"[INDEXER] 완료: {len(results)}개 인덱싱, vl_ok={vl_ok}, vl_fail={vl_fail}")
    return {"indexed": len(results), "vl_ok": vl_ok, "vl_fail": vl_fail,
            "results": results if dry_run else None}


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
           search_text=excluded.search_text, embedding=excluded.embedding,
           desc_source=excluded.desc_source, is_curated=excluded.is_curated,
           keyframe=excluded.keyframe, role=excluded.role,
           hook_score=excluded.hook_score, motion_score=excluded.motion_score,
           updated_at=excluded.updated_at
    """, (
        rec["fragment_id"], rec["source_id"], rec["start"], rec["end"], rec["duration"],
        rec["role"], 0.0, rec["hook_score"], rec["motion_score"],
        rec["visual_desc"], rec.get("transcript"), None,
        json.dumps([]), rec["search_text"], rec["embedding"],
        em.MODEL_NAME, em.DIM, 1 if rec["is_curated"] else 0, 0,
        rec.get("keyframe"), rec["desc_source"], now, now,
    ))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None)
    ap.add_argument("--no-vl", action="store_true")
    ap.add_argument("--curated", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    index_fragments(source_filter=args.source, use_vl=not args.no_vl,
                    only_curated=args.curated, limit=args.limit, dry_run=args.dry_run)
