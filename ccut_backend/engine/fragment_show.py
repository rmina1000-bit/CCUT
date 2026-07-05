# -*- coding: utf-8 -*-
"""[SHOW] 조회/열람 검색 — "OO 나오는 영상 있나/보여줘"의 실행기.

편집이 아니라 '보여주기'다. 결과는 사용자 말 명칭의 자체완결 카드:
  title = 원본 제목(확장자 제거) · time = m:ss–m:ss · thumbnail/video URL 동봉
내부 ID(fid/SRC)는 카드 표면에 노출하지 않는다(payload에만 보관 — 클릭 재생용).
인물 조건은 person_faces(사용자 축복 링크), 자유문은 기존 fragment_search(하이브리드).
"""
import os
import re
import sqlite3
from urllib.parse import quote as _q

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.dirname(BACKEND_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")
THUMBS_DIR = os.path.join(ROOT, "storage", "thumbnails")
PROXIES_DIR = os.path.join(BACKEND_DIR, "storage", "proxies")


def _fmt_time(sec):
    sec = max(0, int(round(sec or 0)))
    return f"{sec // 60}:{sec % 60:02d}"


def display_name(title, start, end):
    """[단일 진실원] 사용자용 조각 주이름 — 규칙 1개: '원본제목(확장자제거) · m:ss–m:ss'.
    카드/조각맵/PBE hydration이 모두 이 함수 하나만 호출한다(이름을 두 번 만들지 않는다).
    title은 확장자 유무 무관 raw로 받아 여기서 벗긴다."""
    base = os.path.splitext(title or "")[0] or (title or "")
    return f"{base} · {_fmt_time(start)}–{_fmt_time(end)}"


def _video_url(file_path, sid):
    name = os.path.basename(file_path or "") or f"{sid}.mp4"
    play = f"play_{os.path.splitext(name)[0]}.mp4"
    if os.path.exists(os.path.join(PROXIES_DIR, play)):
        return f"/static/proxies/{_q(play, safe='')}"
    return f"/static/uploads/{_q(name, safe='')}"


def _card(con, fid, sid, start, end, src_meta, score=None):
    raw_title, fpath = src_meta.get(sid, (sid, None))
    title = os.path.splitext(raw_title or sid)[0]  # 하위호환 title(확장자 제거)
    thumb = f"/static/thumbnails/{fid}.jpg" if os.path.exists(
        os.path.join(THUMBS_DIR, f"{fid}.jpg")) else None
    return {
        "fragment_id": fid, "source_id": sid,
        # display_name = 단일 진실원. title/time은 하위호환 위해 유지.
        "display_name": display_name(raw_title or sid, start, end),
        "title": title, "time": f"{_fmt_time(start)}–{_fmt_time(end)}",
        "start": start, "end": end,
        "thumbnail_url": thumb, "video_url": _video_url(fpath, sid),
        "score": round(score, 3) if score is not None else None,
    }


def search_show(text, person, project_source_ids, limit=12):
    """조회 실행. person(resolve 결과 dict)이 있으면 인물 링크 기준,
    없으면 자유문 하이브리드 검색. 프로젝트 조각 우선 정렬.
    반환 {results, in_project, in_archive, person} | None(결과 0 아님, 판단 불가)."""
    con = sqlite3.connect("file:" + DB_PATH.replace("\\", "/") + "?mode=ro", uri=True)
    try:
        src_meta = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT source_id, title, file_path FROM sources")}
        proj = set(project_source_ids or [])
        rows = []  # (fid, sid, start, end, score)

        if person:
            pids = [r[0] for r in con.execute(
                "SELECT person_id FROM persons WHERE status='named' AND name=?",
                (person["canonical"],))]
            if pids:
                ph = ",".join("?" * len(pids))
                rows = [(r[0], r[1], r[2], r[3], None) for r in con.execute(
                    f"SELECT sf.fragment_id, sf.source_id, sf.start, sf.end "
                    f"FROM person_faces pf JOIN semantic_fragments sf "
                    f"ON sf.fragment_id = pf.fragment_id "
                    f"WHERE pf.person_id IN ({ph}) ORDER BY sf.source_id, sf.start", pids)]
        else:
            # 자유문 — 기존 하이브리드 검색기 재사용 (조회 동사 꼬리 제거)
            q = re.sub(r"(이|가)?\s*(있는|나오는|나온)?\s*(영상|장면|조각|컷)?\s*"
                       r"(이|을|를)?\s*(있나|있냐|있어\?|있는지|보여줘|보여 줘|찾아줘|"
                       r"찾아 줘|찾아봐|불러와|검색해줘|검색해)?[?.! ]*$", "", text).strip()
            if len(q) < 2:
                return None
            from engine import fragment_search
            try:
                found = fragment_search.search(q, top_k=limit * 2)
            except Exception:
                return None
            for it in (found or []):
                fid = it.get("fragment_id")
                sf = con.execute(
                    "SELECT source_id, start, end FROM semantic_fragments "
                    "WHERE fragment_id=?", (fid,)).fetchone()
                if sf:
                    rows.append((fid, sf[0], sf[1], sf[2], it.get("score")))

        if not rows:
            return {"results": [], "in_project": 0, "in_archive": 0,
                    "person": (person or {}).get("canonical")}
        # 프로젝트 조각 우선, limit 컷
        rows.sort(key=lambda r: (r[1] not in proj, r[1], r[2]))
        rows = rows[:limit]
        cards = [_card(con, *r[:4], src_meta, score=r[4]) for r in rows]
        n_proj = sum(1 for r in rows if r[1] in proj)
        return {"results": cards, "in_project": n_proj,
                "in_archive": len(rows) - n_proj,
                "person": (person or {}).get("canonical")}
    finally:
        con.close()
