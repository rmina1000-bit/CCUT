# -*- coding: utf-8 -*-
"""[LEDGER-1] Text Ledger R0 — 스토리 원고 read API (MASTER CONCEPT ①원고의 첫 구현).

- 읽기 전용. DB 원문은 한 글자도 바꾸지 않는다 (이중 인코딩은 여기 읽기 계층에서만 해소).
- 스토리 원고 = committedProposalId 우선(없으면 selected) 제안의 sequence 순서 (v1.1 패치 4).
- 항목 = timeline_item_id(사용본) + ledger_span_id(증거 링크, LSPAN_해시) 병기 (v1.1 패치 3).
- 정직 표기: [자막 없음]/[장면설명 없음]을 숨기지 않는다. 환각 의심은 제거가 아니라 경고 플래그.
- 재생 URL은 기존 실파일 resolver(fragment_show._video_url) 재사용 — ".mp4" 문자열 조립 금지 (패치 7 L2).
- DEBT: 원본 원장(영상별 촬영순 전사) 보기는 R0.5로 이월 — 스토리 원고 우선 (패치 4 허용).
- DEBT: B0 시대 timeline_item_id의 proposal 자리는 mode 문자(A/B) 사용 — 영속 없음(표시 전용).
"""
import hashlib
import json
import os
import re
import sqlite3

from fastapi import APIRouter

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

router = APIRouter()

_HANGUL = re.compile(r"[가-힣]")


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _hash6(s: str) -> str:
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return format(h, "x").rjust(6, "0")[-6:]


def _to_ms(seconds: float) -> int:
    import math
    return math.floor(seconds * 1000 + 0.5)


def _ledger_span_id(source_id: str, start_ms: int, end_ms: int) -> str:
    return "LSPAN_" + hashlib.sha1(f"{source_id}|{start_ms}|{end_ms}".encode()).hexdigest()[:12]


def _parse_segments(raw):
    """subtitles.segments 이중 인코딩 해소 (PHASE A 실측: 전 64건 json.loads 2회)."""
    v = json.loads(raw)
    while isinstance(v, str):
        v = json.loads(v)
    return v if isinstance(v, list) else []


def _asr_overlap(segments, start_sec, end_sec):
    """조각 시간창과 겹치는 세그먼트 원문 + 환각 신호 (제거 금지 — 경고만)."""
    hits = [s for s in segments
            if isinstance(s, dict) and s.get("end", 0) > start_sec and s.get("start", 0) < end_sec]
    if not hits:
        return None, []
    text = " ".join((s.get("text") or "").strip() for s in hits).strip()
    warnings = []
    if text and not _HANGUL.search(text):
        warnings.append("non_korean")  # 비한국어 — 환각 의심 (크메르 반복 등)
    probs = [w.get("probability") for s in hits for w in (s.get("words") or [])
             if isinstance(w, dict) and isinstance(w.get("probability"), (int, float))]
    if probs and sum(probs) / len(probs) < 0.3:
        warnings.append("low_probability")  # 저확률 구간
    return text or None, warnings


@router.get("/ledger/{program_id}")
async def get_ledger(program_id: str):
    con = _connect()
    try:
        prow = con.execute(
            "SELECT program_id, name, ui_state FROM programs WHERE program_id=?", (program_id,)
        ).fetchone()
        if prow is None:
            return {"ok": False, "error": "program_not_found", "program_id": program_id}
        mode, fids = None, []
        snapshot_coords = {}
        if prow["ui_state"]:
            try:
                ui = json.loads(prow["ui_state"])
                while isinstance(ui, str):
                    ui = json.loads(ui)
                mode = ui.get("committedProposalId") or ui.get("selectedProposalId")
                fids = (ui.get("proposalsKeyFragments") or {}).get(mode) or []
                # [D8 대응] fid 재발급으로 DB에서 좌표를 잃은 조각의 폴백 —
                # ui_state 스냅샷(proposalsCustomFragments)의 좌표 (PHASE A: 좌표가 진실)
                for cf in (ui.get("proposalsCustomFragments") or {}).get(mode) or []:
                    if isinstance(cf, dict) and cf.get("fragment_id") is not None:
                        st = cf.get("start_time", cf.get("start_sec"))
                        en = cf.get("end_time", cf.get("end_sec"))
                        sid_cf = cf.get("source_id")
                        if isinstance(st, (int, float)) and isinstance(en, (int, float)) and en > st:
                            snapshot_coords[str(cf["fragment_id"])] = (sid_cf, float(st), float(en))
            except Exception:
                pass

        srcs = {r["source_id"]: r for r in con.execute("SELECT source_id, title, file_path FROM sources")}
        subs_cache = {}

        def segments_for(sid):
            if sid not in subs_cache:
                row = con.execute("SELECT segments FROM subtitles WHERE source_id=?", (sid,)).fetchone()
                subs_cache[sid] = _parse_segments(row["segments"]) if row else None  # None = 자막 자체 없음
            return subs_cache[sid]

        from engine import fragment_show as _fs  # 실파일 URL resolver 재사용 (L2)

        items = []
        occ_seen = {}
        for fid in fids:
            occ = occ_seen.get(fid, 0)
            occ_seen[fid] = occ + 1
            sf = con.execute(
                'SELECT source_id, start, "end" FROM semantic_fragments WHERE fragment_id=?', (fid,)
            ).fetchone()
            if sf is None:
                sf = con.execute(
                    'SELECT source_id, start, "end" FROM fragment_index WHERE fragment_id=?', (fid,)
                ).fetchone()
            coord_source = "db"
            if sf is None and fid in snapshot_coords:
                sid_cf, st_cf, en_cf = snapshot_coords[fid]
                if not sid_cf and "_SRC_" in fid:
                    sid_cf = "SRC_" + fid.split("_SRC_")[-1].split("_")[0]
                sf = {"source_id": sid_cf, "start": st_cf, "end": en_cf}
                coord_source = "ui_state_snapshot"
            if sf is None:
                items.append({"fragment_id": fid, "missing": {"coords": True},
                              "timeline_item_id": f"ITEM_{_hash6(program_id)}_{mode}_{fid}_{occ}"})
                continue
            sid = sf["source_id"]
            s_ms, e_ms = _to_ms(sf["start"]), _to_ms(sf["end"])
            src = srcs.get(sid)
            segs = segments_for(sid)
            if segs is None:
                text, warns, no_sub = None, [], True
            else:
                text, warns = _asr_overlap(segs, sf["start"], sf["end"])
                no_sub = False
            fi = con.execute(
                "SELECT visual_desc, desc_source FROM fragment_index WHERE fragment_id=?", (fid,)
            ).fetchone()
            scene = fi["visual_desc"] if fi and fi["visual_desc"] else None
            items.append({
                "fragment_id": fid,
                "timeline_item_id": f"ITEM_{_hash6(program_id)}_{mode}_{fid}_{occ}",
                "ledger_span_id": _ledger_span_id(sid, s_ms, e_ms),
                "source_id": sid,
                "source_title": (src["title"] if src else sid),
                "anchor_start_ms": s_ms,
                "anchor_end_ms": e_ms,
                "text": text,                       # None = [자막 없음]/[겹침 없음] — 프론트 정직 표기
                "no_subtitle_source": no_sub,       # 소스 자체에 자막 없음 (11개 소스 케이스)
                "warnings": warns,                  # non_korean / low_probability — 제거 아님
                "scene_note": scene,
                "scene_note_source": (fi["desc_source"] if fi else None),  # 'transcript'=대사 파생 태그
                "coord_source": coord_source,  # db | ui_state_snapshot (D8 폴백 정직 표기)
                "video_url": _fs._video_url(src["file_path"] if src else None, sid),
            })
        return {"ok": True, "program_id": program_id, "program_name": prow["name"],
                "mode": mode, "sequence_count": len(fids), "items": items}
    finally:
        con.close()
