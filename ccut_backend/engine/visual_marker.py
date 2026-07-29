"""[LAB-41 RETINA] 시각 표식 — 조각 키프레임 CLIP 임베딩.

scratch/retina0 격리 실험(2026-07-29, top-5 같은소스 99.8%, 42ms/장 CPU)의
검증된 방식을 운영 경로에 재이식한다.

설계 원칙:
- 저장은 신설 테이블 fragment_visual_marks 에만 (rollback = DROP TABLE 한 줄).
  기존 fragment_index / fragment_vault(아카이브 트랙 소유)는 읽기만.
- 관문 금지: 표식 실패는 로그만 남기고 조각 생성·인덱싱을 절대 막지 않는다.
- 오프라인 강제: 캐시된 open_clip_model.safetensors 만 사용, 다운로드 0.
- 게이트: CCUT_VISUAL_MARKS (기본 1). 0 이면 자동 찍기 no-op.
"""
import os
import glob
import json
import datetime
import threading
import sqlite3

import numpy as np

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

MODEL_NAME = "ViT-B-32-quickgelu/openai-safetensors"
DIM = 512

_MODEL = None
_PREPROCESS = None
_LOCK = threading.Lock()

TABLE_DDL = """CREATE TABLE IF NOT EXISTS fragment_visual_marks (
    fragment_id TEXT PRIMARY KEY,
    source_id TEXT,
    keyframe TEXT,
    embedding BLOB NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    marked_by TEXT NOT NULL,
    elapsed_ms REAL,
    created_at TEXT,
    updated_at TEXT
)"""


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute(TABLE_DDL)
    return con


def get_model():
    """CLIP ViT-B/32 싱글톤 (lazy, thread-safe, 오프라인)."""
    global _MODEL, _PREPROCESS
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                import torch
                import open_clip
                from safetensors.torch import load_file
                from open_clip.transform import image_transform
                from open_clip.constants import OPENAI_DATASET_MEAN, OPENAI_DATASET_STD
                weights = glob.glob(os.path.expanduser(
                    r"~/.cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai"
                    r"/snapshots/*/open_clip_model.safetensors"))
                if not weights:
                    raise RuntimeError("CLIP 가중치 캐시 없음 (open_clip_model.safetensors)")
                model = open_clip.create_model("ViT-B-32-quickgelu", pretrained=None)
                missing, _unexpected = model.load_state_dict(load_file(weights[0]), strict=False)
                if len(missing) > 5:
                    raise RuntimeError(f"CLIP 가중치 주입 실패: missing={len(missing)}")
                model.eval()
                _PREPROCESS = image_transform(
                    (224, 224), is_train=False,
                    mean=OPENAI_DATASET_MEAN, std=OPENAI_DATASET_STD)
                _MODEL = model
                print(f"[VISUAL-MARK] 모델 로딩 완료: {MODEL_NAME} ({DIM}d)", flush=True)
    return _MODEL


def encode_images(paths: list) -> np.ndarray:
    """키프레임 경로 배치 -> (N, 512) float32 정규화 행렬."""
    import torch
    from PIL import Image
    model = get_model()
    vecs = np.zeros((len(paths), DIM), dtype=np.float32)
    B = 32
    with torch.no_grad():
        for i in range(0, len(paths), B):
            batch = torch.stack([
                _PREPROCESS(Image.open(p).convert("RGB")) for p in paths[i:i + B]])
            out = model.encode_image(batch)
            out = out / out.norm(dim=-1, keepdim=True)
            vecs[i:i + len(paths[i:i + B])] = out.numpy()
    return vecs


def mark_pairs(pairs: list, marked_by: str) -> dict:
    """(fragment_id, source_id, keyframe_abs_path) 목록에 표식.

    절대 raise 하지 않는다 — 관문 금지. 결과 dict 반환.
    """
    import time
    ok, fail = 0, 0
    try:
        valid = [(f, s, p) for f, s, p in pairs
                 if p and os.path.exists(p) and os.path.getsize(p) > 0]
        if not valid:
            return {"ok": 0, "fail": len(pairs), "reason": "no_valid_keyframe"}
        t0 = time.time()
        vecs = encode_images([p for _f, _s, p in valid])
        per_ms = (time.time() - t0) / len(valid) * 1000.0
        now = datetime.datetime.now().isoformat()
        con = _connect()
        for (fid, sid, path), vec in zip(valid, vecs):
            rel = "/search_keyframes/" + os.path.basename(path)
            con.execute("""
                INSERT INTO fragment_visual_marks
                  (fragment_id, source_id, keyframe, embedding, embedding_model,
                   embedding_dim, marked_by, elapsed_ms, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fragment_id) DO UPDATE SET
                   source_id=excluded.source_id, keyframe=excluded.keyframe,
                   embedding=excluded.embedding, embedding_model=excluded.embedding_model,
                   embedding_dim=excluded.embedding_dim, marked_by=excluded.marked_by,
                   elapsed_ms=excluded.elapsed_ms, updated_at=excluded.updated_at
            """, (fid, sid, rel, vec.astype(np.float32).tobytes(),
                  MODEL_NAME, DIM, marked_by, per_ms, now, now))
            ok += 1
            con.commit()
        con.close()
        fail = len(pairs) - ok
        print(f"[VISUAL-MARK] {marked_by}: {ok}표식 완료, 장당 {per_ms:.0f}ms "
              f"(skip {fail})", flush=True)
        return {"ok": ok, "fail": fail, "per_ms": per_ms}
    except Exception as e:
        print(f"[VISUAL-MARK][ERROR] {marked_by}: {e} (조각 생성은 통과)", flush=True)
        return {"ok": ok, "fail": len(pairs) - ok, "error": str(e)}


def fire_background(pairs: list, marked_by: str = "AUTO"):
    """자동 찍기 발사 — 백그라운드 데몬 스레드, 게이트 CCUT_VISUAL_MARKS(기본 1)."""
    if os.getenv("CCUT_VISUAL_MARKS", "1") not in ("1", "true", "True"):
        print(f"[VISUAL-MARK] gate off (CCUT_VISUAL_MARKS) — skip {len(pairs)}", flush=True)
        return
    if not pairs:
        return
    threading.Thread(target=mark_pairs, args=(pairs, marked_by), daemon=True).start()


def similar(fragment_id: str, top_k: int = 5) -> dict:
    """표식 기반 유사 조각 top-k (cosine). 표식 없으면 NOT_MARKED."""
    con = _connect()
    row = con.execute(
        "SELECT embedding FROM fragment_visual_marks WHERE fragment_id=?",
        (fragment_id,)).fetchone()
    if not row:
        con.close()
        return {"status": "NOT_MARKED", "fragment_id": fragment_id, "results": []}
    q = np.frombuffer(row[0], dtype=np.float32)
    rows = con.execute(
        "SELECT fragment_id, source_id, keyframe, embedding "
        "FROM fragment_visual_marks WHERE fragment_id != ?", (fragment_id,)).fetchall()
    con.close()
    if not rows:
        return {"status": "SUCCESS", "fragment_id": fragment_id, "results": []}
    mat = np.stack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
    sims = mat @ q
    order = np.argsort(-sims)[:top_k]
    results = [{"fragment_id": rows[i][0], "source_id": rows[i][1],
                "keyframe": rows[i][2], "similarity": float(sims[i])}
               for i in order]
    return {"status": "SUCCESS", "fragment_id": fragment_id, "results": results}


def status() -> dict:
    con = _connect()
    total = con.execute("SELECT COUNT(*) FROM fragment_visual_marks").fetchone()[0]
    by = dict(con.execute(
        "SELECT marked_by, COUNT(*) FROM fragment_visual_marks GROUP BY marked_by").fetchall())
    con.close()
    return {"marks": total, "by": by, "model": MODEL_NAME, "dim": DIM}


def backfill(marked_by: str = "LAB41_BACKFILL") -> dict:
    """fragment_index 중 keyframe 실존 조각 전체 백필 (기존 표식은 갱신)."""
    con = _connect()
    rows = con.execute(
        "SELECT fragment_id, source_id, keyframe FROM fragment_index "
        "WHERE keyframe IS NOT NULL").fetchall()
    con.close()
    pairs = []
    for fid, sid, kf in rows:
        path = os.path.join(BACKEND_DIR, "storage", kf.lstrip("/"))
        pairs.append((fid, sid, path))
    print(f"[VISUAL-MARK] backfill 대상 {len(pairs)} (keyframe 경로 보유)", flush=True)
    return mark_pairs(pairs, marked_by)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--similar", default=None)
    args = ap.parse_args()
    if args.backfill:
        print(json.dumps(backfill(), ensure_ascii=False))
    if args.status:
        print(json.dumps(status(), ensure_ascii=False))
    if args.similar:
        print(json.dumps(similar(args.similar), ensure_ascii=False))
