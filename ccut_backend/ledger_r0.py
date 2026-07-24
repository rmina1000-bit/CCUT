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
from fastapi.responses import JSONResponse

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


def _load_ui(raw):
    if not raw:
        return {}
    try:
        ui = json.loads(raw)
        while isinstance(ui, str):
            ui = json.loads(ui)
        return ui if isinstance(ui, dict) else {}
    except Exception:
        return {}


def _program_source_ids(con, program_id: str):
    rows = con.execute(
        "SELECT source_id FROM project_sources WHERE program_id=? ORDER BY rowid", (program_id,)
    ).fetchall()
    return [r["source_id"] for r in rows if r["source_id"]]


def _all_program_fids(con, program_id: str):
    source_ids = _program_source_ids(con, program_id)
    if not source_ids:
        return []
    q = ",".join("?" for _ in source_ids)
    rows = con.execute(
        f'SELECT fragment_id, source_id, start FROM semantic_fragments '
        f'WHERE source_id IN ({q}) ORDER BY source_id, start',
        source_ids,
    ).fetchall()
    return [r["fragment_id"] for r in rows if r["fragment_id"]]


def _recommendation_rows(con, fids):
    if not fids:
        return {}
    q = ",".join("?" for _ in fids)
    rows = con.execute(
        f"SELECT fragment_id, motion_score, hook_score, transcript, role "
        f"FROM fragment_index WHERE fragment_id IN ({q})",
        fids,
    ).fetchall()
    by_fid = {}
    raw_scores = []
    for r in rows:
        motion = float(r["motion_score"] or 0)
        hook = float(r["hook_score"] or 0)
        has_text = bool((r["transcript"] or "").strip())
        role = (r["role"] or "").lower()
        role_bonus = 1.0 if role in {"opening", "closing", "hook", "climax"} else 0.5 if role else 0.0
        raw = motion + hook + (0.12 if has_text else 0.0) + (0.18 * role_bonus)
        raw_scores.append(raw)
        by_fid[r["fragment_id"]] = {
            "signal_name": "motion_hook_text",
            "motion_score": motion,
            "hook_score": hook,
            "has_text": has_text,
            "role": role or None,
            "raw": raw,
        }
    lo = min(raw_scores) if raw_scores else 0.0
    hi = max(raw_scores) if raw_scores else 0.0
    for v in by_fid.values():
        score = 0.5 if hi <= lo else (v["raw"] - lo) / (hi - lo)
        v["score"] = round(max(0.0, min(1.0, score)), 3)
        v["brightness_tier"] = "high" if score >= 0.67 else "mid" if score >= 0.34 else "low"
        v.pop("raw", None)
    return by_fid


def _ordered_stringout_fids(ui, mode, selected_fids, all_fids):
    paper = ((ui.get("paperCutOrder") or {}).get(mode) or []) if isinstance(ui, dict) else []
    base = paper if paper else all_fids
    seen = set()
    ordered = []
    all_set = set(all_fids)
    for fid in base:
        if fid in all_set and fid not in seen:
            seen.add(fid)
            ordered.append(fid)
    for fid in all_fids:
        if fid not in seen:
            seen.add(fid)
            ordered.append(fid)
    for fid in selected_fids:
        if fid not in seen:
            seen.add(fid)
            ordered.append(fid)
    return ordered


def _parse_segments(raw):
    """subtitles.segments 이중 인코딩 해소 (PHASE A 실측: 전 64건 json.loads 2회)."""
    v = json.loads(raw)
    while isinstance(v, str):
        v = json.loads(v)
    return v if isinstance(v, list) else []


def _asr_overlap(segments, start_sec, end_sec):
    """조각 시간창과 겹치는 세그먼트 원문 + 환각 신호 + 단어별 타임스탬프.
    [SCRIPT-2] words = 문장 안 한 단어만 빼기(EXCLUDE_RANGE)의 재료 — 조각 창으로 클램프."""
    hits = [s for s in segments
            if isinstance(s, dict) and s.get("end", 0) > start_sec and s.get("start", 0) < end_sec]
    if not hits:
        return None, [], []
    text = " ".join((s.get("text") or "").strip() for s in hits).strip()
    warnings = []
    if text and not _HANGUL.search(text):
        warnings.append("non_korean")  # 비한국어 — 환각 의심 (크메르 반복 등)
    probs = [w.get("probability") for s in hits for w in (s.get("words") or [])
             if isinstance(w, dict) and isinstance(w.get("probability"), (int, float))]
    if probs and sum(probs) / len(probs) < 0.3:
        warnings.append("low_probability")  # 저확률 구간
    words = []
    for s in hits:
        for w in (s.get("words") or []):
            if not isinstance(w, dict):
                continue
            wt = (w.get("word") or "").strip()
            ws, we = w.get("start"), w.get("end")
            if not wt or not isinstance(ws, (int, float)) or not isinstance(we, (int, float)):
                continue
            if we <= start_sec or ws >= end_sec:
                continue  # 조각 창 밖
            words.append({
                "w": wt,
                "s_ms": _to_ms(max(ws, start_sec)),
                "e_ms": _to_ms(min(we, end_sec)),
                "p": round(w.get("probability", 1.0), 3) if isinstance(w.get("probability"), (int, float)) else None,
            })
    return text or None, warnings, words


@router.get("/ledger/{program_id}")
async def get_ledger(program_id: str):
    con = _connect()
    try:
        prow = con.execute(
            "SELECT program_id, name, ui_state FROM programs WHERE program_id=?", (program_id,)
        ).fetchone()
        if prow is None:
            return {"ok": False, "error": "program_not_found", "program_id": program_id}
        # [STORY-GATE P3] 원고 순서를 만드는 규칙은 하나뿐 — story_gate.service.resolve_sequence.
        # ui_state 우선, 분석 직후처럼 ui_state가 아직 NULL이면 proposals 폴백(B 우선).
        from story_gate.service import resolve_sequence as _resolve_seq
        mode, selected_fids, _seq_src = _resolve_seq(con, program_id)
        ui = _load_ui(prow["ui_state"])
        all_fids = _all_program_fids(con, program_id)
        fids = _ordered_stringout_fids(ui, mode, selected_fids, all_fids)
        selected_set = set(selected_fids)
        play_order_by_fid = {fid: i for i, fid in enumerate(selected_fids)}
        recommendation_by_fid = _recommendation_rows(con, fids)
        snapshot_coords = {}
        if ui:
            try:
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
        trim_by_item = {}
        excluded_by_item = {}  # [SCRIPT-2] timeline_item_id -> [[s_ms,e_ms], ...]
        state_seen = {}
        try:
            for r in con.execute(
                "SELECT timeline_item_id, removed, revision, trim_start_ms, trim_end_ms, excluded_ranges_json "
                "FROM fragment_edit_state WHERE program_id=?", (program_id,)):
                state_seen[r["timeline_item_id"]] = True
                removed_items[r["timeline_item_id"]] = bool(r["removed"])
                state_rev[r["timeline_item_id"]] = r["revision"]
                trim_by_item[r["timeline_item_id"]] = (r["trim_start_ms"], r["trim_end_ms"])
                try:
                    rngs = json.loads(r["excluded_ranges_json"] or "[]")
                    if rngs:
                        excluded_by_item[r["timeline_item_id"]] = rngs
                except Exception:
                    pass
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
            selected = fid in selected_set and not removed_items.get(item_id)
            if removed_items.get(item_id):
                # [SCRIPT-2] 제외된 장면 — 대본 밖이지만 되돌릴 길은 항상 열어둔다
                excluded_count += 1
                excluded_items.append({
                    "timeline_item_id": item_id, "fragment_id": fid, "source_id": sid,
                    "anchor_start_ms": s_ms, "anchor_end_ms": e_ms,
                    "revision": state_rev.get(item_id),
                })
            src = srcs.get(sid)
            segs = segments_for(sid)
            if segs is None:
                text, warns, words, no_sub = None, [], [], True
            else:
                text, warns, words = _asr_overlap(segs, sf["start"], sf["end"])
                no_sub = False
            # [SCRIPT-2] 이미 저장된 EXCLUDE_RANGE로 제외된 단어에 취소선 플래그
            item_trim_start, item_trim_end = trim_by_item.get(item_id, (s_ms, e_ms))
            item_excl = excluded_by_item.get(item_id) or []
            for w in words:
                outside_trim = w["s_ms"] < item_trim_start or w["e_ms"] > item_trim_end
                w["excluded"] = outside_trim or any(er[0] < w["e_ms"] and er[1] > w["s_ms"] for er in item_excl)
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
                "selected": selected,
                "play_order": play_order_by_fid.get(fid, 100000 + len(items)),
                "revision": state_rev.get(item_id),  # 낙관적 잠금용 (없으면 신규)
                "ledger_span_id": _ledger_span_id(sid, s_ms, e_ms),
                "source_id": sid,
                "source_title": (src["title"] if src else sid),
                "anchor_start_ms": s_ms,
                "anchor_end_ms": e_ms,
                "trim_start_ms": item_trim_start,
                "trim_end_ms": item_trim_end,
                "removed": removed_items.get(item_id, False),
                "dialogue": dialogue,               # 대사 (정체) — None이면 지문만
                "words": (words if dialogue else []),  # [SCRIPT-2] 단어별 타임스탬프 (문장 안 편집)
                "excluded_ranges": item_excl,       # [SCRIPT-2] 현재 제외 구간 (병합용)
                "stage_direction": stage,           # 지문 (이탤릭) — 장면 번역
                "place": _place(scene),             # 씬 헤딩용 장소 (S#n) — 라벨 있을 때만
                "original_text": original_text,     # 환각 원문 (상세 보기 보존)
                "no_subtitle_source": no_sub,       # 소스 자체에 자막 없음 (11개 소스 케이스)
                "warnings": warns,                  # non_korean / low_probability
                "recommendation": recommendation_by_fid.get(fid),
                "scene_note_source": scene_src,  # 'transcript'=대사 파생 태그
                "coord_source": coord_source,       # db | ui_state_snapshot (D8 폴백 정직 표기)
                "video_url": _fs._video_url(src["file_path"] if src else None, sid),
            })
        out = {"ok": True, "program_id": program_id, "program_name": prow["name"],
               "mode": mode, "sequence_count": len(selected_fids), "stringout_count": len(fids),
               "selected_count": sum(1 for it in items if it.get("selected")),
               "unselected_count": sum(1 for it in items if not it.get("selected") and not it.get("missing")),
               "items": items,
               "running_ms": running_ms,  # [SCRIPT-5] 상단 러닝타임(현재)
               "excluded_count": excluded_count,  # [SCRIPT-2] 제외된 장면 수
               "excluded_items": excluded_items}  # 복원용 최소 정보
        # [STORY-GATE P2] 게이트 ON일 때만 승인 상태를 함께 싣는다.
        # OFF면 응답이 이전과 바이트 동일 (I-4) — 기존 프론트 경로 무영향.
        try:
            from story_gate import gate as _sg
            if _sg.is_enabled():
                from story_gate import service as _ss
                out["story"] = _ss.story_state(program_id)
        except Exception as _e:  # 승인 계층 실패가 원고 읽기를 막지 않는다 (정직 표기)
            out["story_error"] = str(_e)
        return out
    finally:
        con.close()


@router.get("/ledger/{program_id}/edl")
async def get_render_edl(program_id: str):
    """[SCRIPT-2d] 대본 편집을 반영한 최종 클립 목록(EDL) — '편집(export)에 넘기는 것'.

    각 사용본의 Edit State를 compile_spans(계약 순수함수)로 Render Span으로 펼쳐
    대본 순서대로 (source_id, start_sec, end_sec) 물리 클립을 만든다.
    REMOVE된 사용본은 빠지고, EXCLUDE_RANGE는 여러 클립으로 쪼개진다.
    이 EDL이 곧 export_engine/render 파이프라인의 입력(physical clip 목록)과 같은 형태다.
    저장하지 않는 계산 결과(Render Span) — Preview/Export만 소비 (MASTER CONCEPT).
    """
    from edit_contract.edit_state import compile_spans

    d = await get_ledger(program_id)
    if not d.get("ok"):
        return d
    con = _connect()
    try:
        state = {}
        try:
            for r in con.execute(
                "SELECT timeline_item_id, trim_start_ms, trim_end_ms, excluded_ranges_json, removed "
                "FROM fragment_edit_state WHERE program_id=?", (program_id,)):
                state[r["timeline_item_id"]] = r
        except sqlite3.OperationalError:
            pass

        clips = []
        order = 0
        total_ms = 0
        for it in sorted(d["items"], key=lambda x: x.get("play_order", 100000)):
            if it.get("missing"):
                continue
            if it.get("selected") is False:
                continue
            a0, a1 = it["anchor_start_ms"], it["anchor_end_ms"]
            st = state.get(it["timeline_item_id"])
            if st:
                canon = {
                    "trim_start_ms": st["trim_start_ms"], "trim_end_ms": st["trim_end_ms"],
                    "excluded_ranges": json.loads(st["excluded_ranges_json"] or "[]"),
                    "removed": bool(st["removed"]),
                }
            else:
                canon = {"trim_start_ms": a0, "trim_end_ms": a1, "excluded_ranges": [], "removed": False}
            for k, (cs, ce) in enumerate(compile_spans(canon)):
                clips.append({
                    "order": order,
                    "source_id": it["source_id"],
                    "start_sec": round(cs / 1000.0, 3),
                    "end_sec": round(ce / 1000.0, 3),
                    "duration_sec": round((ce - cs) / 1000.0, 3),
                    "fragment_id": it["fragment_id"],
                    "clip_of": (f"{it['fragment_id']}#k{k + 1}" if len(compile_spans(canon)) > 1 else it["fragment_id"]),
                    "video_url": it.get("video_url"),
                })
                order += 1
                total_ms += (ce - cs)
        return {"ok": True, "program_id": program_id, "program_name": d.get("program_name"),
                "clip_count": len(clips), "total_ms": total_ms, "clips": clips}
    finally:
        con.close()


@router.post("/ledger/{program_id}/order")
async def save_ledger_order(program_id: str, payload: dict):
    """Papercut order: save full display order plus active proposal order in ui_state."""
    try:
        from story_gate.service import is_edit_locked
        if is_edit_locked(program_id):
            return JSONResponse(status_code=409, content={"ok": False, "error": "story_approved_edit_locked"})
    except Exception:
        pass
    con = _connect()
    try:
        prow = con.execute(
            "SELECT ui_state FROM programs WHERE program_id=?", (program_id,)
        ).fetchone()
        if prow is None:
            return {"ok": False, "error": "program_not_found", "program_id": program_id}
        ui = _load_ui(prow["ui_state"])
        mode = payload.get("mode") or ui.get("committedProposalId") or ui.get("selectedProposalId") or "B"
        full_order = [str(x) for x in (payload.get("order") or []) if x]
        selected_order = [str(x) for x in (payload.get("selected") or []) if x]
        all_fids = set(_all_program_fids(con, program_id))
        if not full_order:
            return {"ok": False, "error": "empty_order"}
        full_order = [fid for fid in full_order if fid in all_fids]
        selected_order = [fid for fid in selected_order if fid in all_fids]
        paper = ui.get("paperCutOrder") if isinstance(ui.get("paperCutOrder"), dict) else {}
        paper[mode] = full_order
        ui["paperCutOrder"] = paper
        pk = ui.get("proposalsKeyFragments") if isinstance(ui.get("proposalsKeyFragments"), dict) else {}
        pk[mode] = selected_order
        ui["proposalsKeyFragments"] = pk
        if not ui.get("selectedProposalId") and not ui.get("committedProposalId"):
            ui["selectedProposalId"] = mode
        con.execute(
            "UPDATE programs SET ui_state=? WHERE program_id=?",
            (json.dumps(ui, ensure_ascii=False), program_id),
        )
        con.commit()
        try:
            from story_gate.service import compute_hash
            sequence_hash = compute_hash(mode, selected_order)
        except Exception:
            sequence_hash = None
        return {
            "ok": True,
            "program_id": program_id,
            "mode": mode,
            "order_count": len(full_order),
            "selected_count": len(selected_order),
            "sequence_hash": sequence_hash,
            "order": full_order,
            "selected": selected_order,
        }
    finally:
        con.close()
