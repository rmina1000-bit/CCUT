"""[FRAGMENT-SEARCH 단계3] 조각 자연어 검색.

"영국에서 비오는날 찍었던 중년 아저씨" -> 관련 조각 목록.

하이브리드 검색:
  1. 시맨틱: 쿼리 임베딩 vs fragment_index.embedding cosine (의미 매칭, cross-lingual)
  2. 키워드: FTS5 fragment_fts (정확한 단어 매칭)
  3. 융합: semantic 점수 + keyword 보너스 + curated/edit_value 가중

속도: 임베딩 1회(~80ms) + numpy 행렬곱(812개 <1ms) + FTS5(<1ms).
"""
import os
import sqlite3
import numpy as np

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")


def _fts_match_ids(con, query: str, limit: int = 50) -> dict:
    """FTS5 키워드 매칭 -> {fragment_id: bm25_rank}. 실패 시 빈 dict."""
    out = {}
    try:
        cur = con.cursor()
        # FTS5 쿼리 안전화: 특수문자 제거, OR 결합
        terms = [t for t in query.replace('"', " ").split() if len(t) >= 2]
        if not terms:
            return out
        fts_q = " OR ".join(terms)
        cur.execute("""
            SELECT fragment_id, bm25(fragment_fts) AS rank
            FROM fragment_fts WHERE fragment_fts MATCH ?
            ORDER BY rank LIMIT ?
        """, (fts_q, limit))
        for fid, rank in cur.fetchall():
            out[fid] = rank
    except Exception:
        pass
    return out


def search(query: str, top_k: int = 10, only_curated: bool = False,
           source_id: str = None, role: str = None, prefer_curated: bool = True):
    """조각 검색. 결과: [{fragment_id, score, visual_desc, ...}, ...] 점수 내림차순."""
    from engine import embedding_model as em

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 후보 로드 (필터 적용)
    where = ["embedding IS NOT NULL"]
    params = []
    if only_curated:
        where.append("is_curated = 1")
    if source_id:
        where.append("source_id = ?")
        params.append(source_id)
    if role:
        where.append("role = ?")
        params.append(role)
    sql = f"""SELECT fragment_id, source_id, start, "end", duration, role, hook_score,
                     motion_score, visual_desc, transcript, search_text, embedding,
                     is_curated, edit_value, keyframe, desc_source
              FROM fragment_index WHERE {' AND '.join(where)}"""
    cur.execute(sql, params)
    rows = cur.fetchall()
    if not rows:
        con.close()
        return {"query": query, "count": 0, "results": []}

    # 시맨틱 점수
    q_vec = em.encode_one(query)
    mat = np.stack([em.from_bytes(r[11]) for r in rows])  # (N, 384)
    sims = mat @ q_vec  # 정규화 벡터 -> 내적=cosine

    # 키워드 보너스
    fts = _fts_match_ids(con, query, limit=50)
    con.close()

    results = []
    for i, r in enumerate(rows):
        fid = r[0]
        sem = float(sims[i])
        kw_bonus = 0.15 if fid in fts else 0.0
        curated_bonus = 0.05 if (prefer_curated and r[12]) else 0.0
        score = sem + kw_bonus + curated_bonus
        results.append({
            "fragment_id": fid, "source_id": r[1],
            "start": r[2], "end": r[3], "duration": r[4],
            "role": r[5], "hook_score": r[6], "motion_score": r[7],
            "visual_desc": r[8], "transcript": r[9],
            "is_curated": bool(r[12]), "keyframe": r[14],
            "desc_source": r[15],
            "score": round(score, 4), "semantic": round(sem, 4),
            "keyword_hit": fid in fts,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"query": query, "count": len(results), "results": results[:top_k]}


def index_status():
    """인덱스 현황 (read-only)."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*), SUM(is_curated), SUM(CASE WHEN desc_source='qwen_vl' THEN 1 ELSE 0 END) FROM fragment_index")
    total, curated, vl = cur.fetchone()
    con.close()
    return {"total": total or 0, "curated": curated or 0, "vl_described": vl or 0}
