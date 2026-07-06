"""[아카이브 채팅 MVP] 자연어 조회 전용 라우터.
결정론 파싱(인물/장소/장면) -> DB 검색 -> 애매할 때만 hub._ollama_json 폴백.
proposal_engine/route-edit/기존 채팅 컴포넌트와는 완전히 분리된 read-only 조회 경로다.

[RED-1 수정] person_faces.fragment_id는 SF_ 네이밍 — fragments 테이블(VF_ 네이밍)과는
조인이 0건이다. fragment_vault 우선, 없으면 semantic_fragments로 fragment 정보를 복원한다.
[RED-2 수정] 결과 단위를 source card가 아니라 fragment card로 반환한다.
"""
import json
import os
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import quote as _url_quote

from fastapi import APIRouter
from pydantic import BaseModel

from engine import hub

router = APIRouter()

_BACKEND_DIR = Path(__file__).resolve().parent
_DB_PATH = str(_BACKEND_DIR / "ccut_app.db")
_THUMBS_DIR = _BACKEND_DIR.parent / "storage" / "thumbnails"

# 결정론 ①: 한국어 장면 키워드 -> fragment_vault.scene_type 값 (DB 실측 확인된 값만)
_SCENE_KEYWORDS = {
    "실내": "indoor", "실외": "outdoor", "야외": "outdoor",
    "학교": "school", "병원": "hospital", "해변": "beach", "바다": "beach",
    "지하철": "subway", "놀이터": "playground", "집": "home", "가정": "home",
    "거리": "street", "길거리": "street", "링크": "rink", "스케이트장": "rink",
}

# 요청 동사/조사 제거 — 남는 문자열을 키워드 검색어로 사용
_REQUEST_VERB_RE = re.compile(
    r"(보여\s*줘|보여\s*주세요|찾아\s*줘|찾아\s*주세요|알려\s*줘|알려\s*주세요|"
    r"모아\s*줘|정리해\s*줘|있어\s*\??|있나요\s*\??|있는지|해줘|줘)\s*$"
)


def _connect():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_schema(con=None):
    owns = con is None
    con = con or _connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS archive_result_sets (
            id TEXT PRIMARY KEY,
            query_text TEXT,
            result_type TEXT,
            result_ids TEXT,
            created_at TEXT
        )"""
    )
    con.commit()
    if owns:
        con.close()


class ChatQuery(BaseModel):
    query: str


def _strip_request_verbs(text: str) -> str:
    return _REQUEST_VERB_RE.sub("", text.strip()).strip()


def _match_person(con, query: str):
    rows = con.execute(
        "SELECT person_id, name, aliases FROM persons WHERE name IS NOT NULL AND name != ''"
    ).fetchall()
    for r in rows:
        name = (r["name"] or "").strip()
        if name and name in query:
            return r["person_id"], name
        for alias in (r["aliases"] or "").split(","):
            alias = alias.strip()
            if alias and alias in query:
                return r["person_id"], name
    return None, None


def _match_place(con, query: str):
    rows = con.execute(
        "SELECT DISTINCT place_label FROM fragment_places WHERE status='active'"
    ).fetchall()
    for r in rows:
        label = (r["place_label"] or "").strip()
        if label and label in query:
            return label
    return None


def _match_scene(query: str):
    for kw, scene_type in _SCENE_KEYWORDS.items():
        if kw in query:
            return scene_type
    return None


# ── ② DB 검색 — 전부 fragment_id 단위로 반환 (source 단위 집계 금지, RED-2) ──

def _search_person(con, person_id, person_name):
    rows = con.execute(
        "SELECT fragment_id, score FROM person_faces WHERE person_id=?", (person_id,)
    ).fetchall()
    return [(r["fragment_id"], {"matched": "person", "person_name": person_name, "score": r["score"]})
            for r in rows]


def _search_place(con, place_label):
    rows = con.execute(
        "SELECT fragment_id, evidence_json FROM fragment_places WHERE place_label=? AND status='active'",
        (place_label,),
    ).fetchall()
    out = []
    for r in rows:
        try:
            ev = json.loads(r["evidence_json"]) if r["evidence_json"] else {}
        except Exception:
            ev = {}
        ev["matched"] = "place"
        ev["place_label"] = place_label
        out.append((r["fragment_id"], ev))
    return out


def _search_scene(con, scene_type):
    rows = con.execute(
        "SELECT fragment_id FROM fragment_vault WHERE scene_type=?", (scene_type,)
    ).fetchall()
    return [(r["fragment_id"], {"matched": "scene", "scene_type": scene_type}) for r in rows]


def _search_keyword(con, keyword):
    if not keyword:
        return []
    like = f"%{keyword}%"
    rows = con.execute(
        "SELECT fragment_id, search_text, visual_desc, transcript FROM fragment_vault "
        "WHERE search_text LIKE ? OR visual_desc LIKE ? OR transcript LIKE ?",
        (like, like, like),
    ).fetchall()
    out = []
    for r in rows:
        if r["search_text"] and keyword in r["search_text"]:
            field, snippet = "search_text", r["search_text"]
        elif r["visual_desc"] and keyword in r["visual_desc"]:
            field, snippet = "visual_desc", r["visual_desc"]
        else:
            field, snippet = "transcript", r["transcript"] or ""
        out.append((r["fragment_id"], {"matched": "keyword", "field": field, "snippet": snippet[:120]}))
    return out


def _run_deterministic_search(con, query: str):
    """① 결정론 파싱 + ② DB 검색. 매칭 실패 시 (None, []) 반환 — LLM 폴백 신호."""
    person_id, person_name = _match_person(con, query)
    if person_id:
        return "person", _search_person(con, person_id, person_name)

    place_label = _match_place(con, query)
    if place_label:
        return "place", _search_place(con, place_label)

    scene_type = _match_scene(query)
    if scene_type:
        return "scene", _search_scene(con, scene_type)

    keyword = _strip_request_verbs(query)
    if keyword:
        matches = _search_keyword(con, keyword)
        if matches:
            return "keyword", matches

    return None, []


def _llm_fallback_search(con, query: str):
    """③ 애매할 때만 — hub._ollama_json으로 person/place/scene/keyword 추출 후 재검색."""
    prompt = (
        "너는 영상 아카이브 검색 거점이다. 사용자의 자연어 조회 문장에서 검색 대상을 뽑는다.\n"
        f'문장: "{query}"\n'
        '다음 JSON 형식으로만 답하라: {"kind": "person|place|scene|keyword", "value": "추출한 문자열"}\n'
        "kind는 인물 이름이면 person, 장소면 place, 실내/실외 등 장면 유형이면 scene, "
        "그 외는 keyword로 분류한다. value는 검색에 바로 쓸 짧은 단어/구다."
    )
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0)
    except Exception as e:
        print(f"[ARCHIVE-CHAT] LLM 폴백 실패 (non-blocking): {e}")
        return "unmatched", []

    kind = str(out.get("kind") or "").strip()
    value = str(out.get("value") or "").strip()
    if not value:
        return "unmatched", []

    if kind == "person":
        person_id, person_name = _match_person(con, value)
        if person_id:
            return "person", _search_person(con, person_id, person_name)
        return "unmatched", []
    if kind == "place":
        place_label = _match_place(con, value)
        if place_label:
            return "place", _search_place(con, place_label)
        return "unmatched", []
    if kind == "scene":
        scene_type = _SCENE_KEYWORDS.get(value) or (value if value in _SCENE_KEYWORDS.values() else None)
        if scene_type:
            return "scene", _search_scene(con, scene_type)
        return "unmatched", []

    matches = _search_keyword(con, value)
    return ("keyword", matches) if matches else ("unmatched", [])


def _source_video_url(con, source_id):
    row = con.execute("SELECT file_path FROM sources WHERE source_id=?", (source_id,)).fetchone()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
        return f"/static/uploads/{_url_quote(os.path.basename(row['file_path']), safe='')}"
    return None


def _thumbnail_url(fragment_id):
    if fragment_id and (_THUMBS_DIR / f"{fragment_id}.jpg").exists():
        return f"/static/thumbnails/{fragment_id}.jpg"
    return None


def _fragment_card(con, fragment_id, evidence):
    row = con.execute(
        "SELECT fragment_id, source_id, display_name, start, end, people, places "
        "FROM fragment_vault WHERE fragment_id=?", (fragment_id,)
    ).fetchone()
    if row:
        source_id, display_name = row["source_id"], row["display_name"]
        start, end = row["start"], row["end"]
        people, places = row["people"], row["places"]
    else:
        # [RED-1] fragment_vault에 없으면 semantic_fragments로 source_id 복원
        row2 = con.execute(
            "SELECT fragment_id, source_id, start, end FROM semantic_fragments WHERE fragment_id=?",
            (fragment_id,)
        ).fetchone()
        if not row2:
            return None
        source_id = row2["source_id"]
        display_name, people, places = None, None, None
        start, end = row2["start"], row2["end"]

    return {
        "fragment_id": fragment_id,
        "source_id": source_id,
        "display_name": display_name,
        "thumbnail_url": _thumbnail_url(fragment_id),
        "video_url": _source_video_url(con, source_id),
        "start": start,
        "end": end,
        "people": people,
        "places": places,
        "evidence": evidence,
    }


def _save_result_set(con, query_text, result_type, matches):
    result_set_id = uuid.uuid4().hex
    payload = [{"fragment_id": fid, "evidence": ev} for fid, ev in matches]
    con.execute(
        "INSERT INTO archive_result_sets (id, query_text, result_type, result_ids, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (result_set_id, query_text, result_type, json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
    return result_set_id


@router.post("/archive/chat")
async def archive_chat(body: ChatQuery):
    query = (body.query or "").strip()
    con = _connect()
    try:
        ensure_schema(con)
        if not query:
            return {"result_set_id": None, "result_type": "unmatched", "results": []}

        result_type, matches = _run_deterministic_search(con, query)
        if result_type is None:
            result_type, matches = _llm_fallback_search(con, query)

        result_set_id = _save_result_set(con, query, result_type, matches)
        cards = [c for fid, ev in matches if (c := _fragment_card(con, fid, ev))]
        return {"result_set_id": result_set_id, "result_type": result_type, "results": cards}
    finally:
        con.close()


@router.get("/archive/chat/results/{result_set_id}")
async def archive_chat_results(result_set_id: str):
    con = _connect()
    try:
        ensure_schema(con)
        row = con.execute(
            "SELECT id, query_text, result_type, result_ids, created_at "
            "FROM archive_result_sets WHERE id=?",
            (result_set_id,),
        ).fetchone()
        if not row:
            return {"status": "ERROR", "message": "result set not found"}
        payload = json.loads(row["result_ids"] or "[]")
        cards = [c for item in payload
                 if (c := _fragment_card(con, item["fragment_id"], item.get("evidence")))]
        return {
            "result_set_id": row["id"],
            "query_text": row["query_text"],
            "result_type": row["result_type"],
            "created_at": row["created_at"],
            "results": cards,
        }
    finally:
        con.close()
