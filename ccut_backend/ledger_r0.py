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

from scenario_text import place_of as _place
from scenario_text import stage_direction as _stage

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

        # [SCRIPT-2] 승인된 편집(Edit State) 반영 — REMOVE된 사용본은 대본에서 뺀다.
        removed_items = {}
        state_rev = {}
        try:
            for r in con.execute(
                "SELECT timeline_item_id, removed, revision FROM fragment_edit_state WHERE program_id=?",
                (program_id,)):
                removed_items[r["timeline_item_id"]] = bool(r["removed"])
                state_rev[r["timeline_item_id"]] = r["revision"]
        except sqlite3.OperationalError:
            pass  # Cutover 전 운영 DB — 테이블 부재면 편집 없음

        srcs = {r["source_id"]: r for r in con.execute("SELECT source_id, title, file_path FROM sources")}
        subs_cache = {}

        # [SCRIPT-1] visual_desc를 좌표로 찾기 위한 소스별 색인 (D8: fid 재발급으로
        # ui_state의 fid가 fragment_index와 안 맞음 → PBE 감사의 좌표 재매칭 교훈 적용).
        fi_by_source = {}
        for r in con.execute(
            'SELECT source_id, start, "end", visual_desc, desc_source FROM fragment_index '
            'WHERE visual_desc IS NOT NULL AND visual_desc<>""'):
            fi_by_source.setdefault(r["source_id"], []).append(
                (_to_ms(r["start"]), _to_ms(r["end"]), r["visual_desc"], r["desc_source"]))

        def visual_for(fid, sid, s_ms, e_ms, tol=120):
            row = con.execute(
                "SELECT visual_desc, desc_source FROM fragment_index WHERE fragment_id=?", (fid,)).fetchone()
            if row and row["visual_desc"]:
                return row["visual_desc"], row["desc_source"]
            best, bestd = None, tol + 1
            for a, b, vd, ds in fi_by_source.get(sid, []):
                d = abs(a - s_ms) + abs(b - e_ms)
                if d < bestd:
                    best, bestd = (vd, ds), d
            return best if best else (None, None)

        def segments_for(sid):
            if sid not in subs_cache:
                row = con.execute("SELECT segments FROM subtitles WHERE source_id=?", (sid,)).fetchone()
                subs_cache[sid] = _parse_segments(row["segments"]) if row else None  # None = 자막 자체 없음
            return subs_cache[sid]

        from engine import fragment_show as _fs  # 실파일 URL resolver 재사용 (L2)

        items = []
        running_ms = 0
        occ_seen = {}
        excluded_count = 0
        excluded_items = []
        for fid in fids:
            occ = occ_seen.get(fid, 0)
            occ_seen[fid] = occ + 1
            item_id = f"ITEM_{_hash6(program_id)}_{mode}_{fid}_{occ}"
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
                              "timeline_item_id": item_id})
                continue
            sid = sf["source_id"]
            s_ms, e_ms = _to_ms(sf["start"]), _to_ms(sf["end"])
            if removed_items.get(item_id):
                # [SCRIPT-2] 제외된 장면 — 대본 밖이지만 되돌릴 길은 항상 열어둔다
                excluded_count += 1
                excluded_items.append({
                    "timeline_item_id": item_id, "fragment_id": fid, "source_id": sid,
                    "anchor_start_ms": s_ms, "anchor_end_ms": e_ms,
                    "revision": state_rev.get(item_id),
                })
                continue
            src = srcs.get(sid)
            segs = segments_for(sid)
            if segs is None:
                text, warns, no_sub = None, [], True
            else:
                text, warns = _asr_overlap(segs, sf["start"], sf["end"])
                no_sub = False
            scene, scene_src = visual_for(fid, sid, s_ms, e_ms)
            # [SCRIPT-1] 지문 = 장면 태그를 사람 문장으로 번역 (결정론 템플릿)
            stage = _stage(scene)
            # [SCRIPT-1] 대본 = 대사(정체) + 지문(이탤릭). 환각 자막 구간은 대사 대신 지문으로
            # 대체 표기하고 원문은 상세 보기에 보존 (정직 원칙).
            is_hallucination = "non_korean" in warns
            dialogue = None if is_hallucination else text
            original_text = text if is_hallucination else None
            dur = e_ms - s_ms
            if dur > 0:
                running_ms += dur
            items.append({
                "fragment_id": fid,
                "timeline_item_id": item_id,
                "revision": state_rev.get(item_id),  # 낙관적 잠금용 (없으면 신규)
                "ledger_span_id": _ledger_span_id(sid, s_ms, e_ms),
                "source_id": sid,
                "source_title": (src["title"] if src else sid),
                "anchor_start_ms": s_ms,
                "anchor_end_ms": e_ms,
                "dialogue": dialogue,               # 대사 (정체) — None이면 지문만
                "stage_direction": stage,           # 지문 (이탤릭) — 장면 번역
                "place": _place(scene),             # 씬 헤딩용 장소 (S#n) — 라벨 있을 때만
                "original_text": original_text,     # 환각 원문 (상세 보기 보존)
                "no_subtitle_source": no_sub,       # 소스 자체에 자막 없음 (11개 소스 케이스)
                "warnings": warns,                  # non_korean / low_probability
                "scene_note_source": scene_src,  # 'transcript'=대사 파생 태그
                "coord_source": coord_source,       # db | ui_state_snapshot (D8 폴백 정직 표기)
                "video_url": _fs._video_url(src["file_path"] if src else None, sid),
            })
        return {"ok": True, "program_id": program_id, "program_name": prow["name"],
                "mode": mode, "sequence_count": len(fids), "items": items,
                "running_ms": running_ms,  # [SCRIPT-5] 상단 러닝타임(현재)
                "excluded_count": excluded_count,  # [SCRIPT-2] 제외된 장면 수
                "excluded_items": excluded_items}  # 복원용 최소 정보
    finally:
        con.close()
