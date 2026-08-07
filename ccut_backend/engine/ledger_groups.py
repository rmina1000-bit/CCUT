"""
[STRUCT-A① 2026-08-08] 원고의 중간층 L1 — 장면 묶음.

개념서 §3: "카드 수백 개를 나열하지 않는다. 워드 문서를 읽듯이."
개념서 §7: "전체는 가볍게 보고, 필요한 곳만 깊게 본다."

하루치 촬영이 오면 조각이 1,000개를 넘는다(실측 추정: 5시간 → 1,441개).
카드로도, 낱개 원고로도 사람이 마주할 수 없다. 그래서 원고에 층을 만든다.

  L0  전체 한 문단          roughCut.premise (이미 있음)
  L1  장면 묶음 10~30개     ← 이 파일이 만든다
  L2  항목(대사·지문·좌표)   /ledger (이미 있음)

★새 분석기·새 모델·새 저장소를 만들지 않는다. 이미 있는 값만 읽어 묶는 계산이다.
  읽는 것: semantic_fragments(시간) · fragment_index(qwen_vl 태그·장소)
           fragments.intelligence(무음비) · subtitles(대사, 선택)

★관찰 항목(국장 지시): 전사 없이(시간·VL·무음만으로) 묶음이 서는가.
  서면 ASR 을 뒤로 미룰 수 있다 — 하루치 전처리 2시간의 벽이 낮아진다.
  그래서 이 파일은 use_transcript 를 껐다 켰다 하며 같은 묶음을 만들 수 있게 짰다.
"""
import json
import os
import re
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

# 묶음 경계 판정 문턱 — 전부 결정론. 모델을 부르지 않는다.
#
# ★[실측 2026-08-08] 태그 문자열 일치(Jaccard)는 쓰지 않는다.
#   같은 바닷가 장면인데 qwen_vl 이 매번 다른 낱말을 뽑는다:
#     "rocky shore, water, coastal town, woman"  ↔  "concrete, ocean, person, rocks"
#   인접 조각 Jaccard 중앙값 0.154 — 의미는 같은데 유사도가 바닥이라 135조각이
#   113묶음으로 거의 안 묶였다. 낱말이 아니라 뜻을 봐야 한다.
#
# ★그래서 fragment_index.embedding 을 쓴다 — 이미 계산돼 있다(135/135, 새 계산 0).
#   인접 임베딩 유사도 중앙 0.853. 문턱별 실측:
#     0.60 → 4묶음(33.8조각)  0.65 → 12묶음(11.2)  0.70 → 16묶음(8.4)  0.75 → 28묶음(4.8)
#   개념서가 원하는 "읽을 수 있는 크기"는 10~30묶음이므로 0.68 을 기본으로 둔다.
EMB_CUT = 0.68        # 인접 조각 임베딩 유사도가 이보다 낮으면 장면이 바뀐 것
TAG_CUT = 0.05        # 임베딩이 없을 때만 쓰는 최후 폴백(태그 Jaccard)
GAP_MS = 8000         # 조각 사이가 이보다 벌어지면(촬영 중단 등) 끊는다
MAX_ITEMS = 40        # 한 묶음이 이보다 커지면 나눈다 (읽을 수 있는 크기 유지)
MAX_SPAN_MS = 600000  # 10분. 시간으로도 너무 길면 나눈다

_PLACE_RE = re.compile(r"\(장소:([^)]+)\)")
_PAREN_RE = re.compile(r"\([^)]*\)")


def _connect():
    con = sqlite3.connect(f"file:{DB_PATH.replace(os.sep, '/')}?mode=ro", uri=True,
                          timeout=20)
    con.row_factory = sqlite3.Row
    return con


def _tags(visual_desc):
    """qwen_vl 묘사 → 태그 집합. 장소·인물 라벨은 따로 뽑고 본문만 태그로."""
    if not visual_desc:
        return set()
    core = _PAREN_RE.sub("", visual_desc)
    return {t.strip().lower() for t in core.split(",") if t.strip()}


def _place(visual_desc):
    if not visual_desc:
        return None
    m = _PLACE_RE.search(visual_desc)
    return m.group(1).strip() if m else None


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_units(con, source_id):
    """조각 하나 = 단위 하나. 시간·VL·무음·대사를 붙여 온다."""
    rows = con.execute(
        'SELECT fragment_id, start, "end" FROM semantic_fragments '
        "WHERE source_id=? ORDER BY start", (source_id,)).fetchall()
    if not rows:
        return []
    vis = {}
    emb = {}
    for r in con.execute(
            "SELECT fragment_id, visual_desc, embedding FROM fragment_index "
            "WHERE source_id=?", (source_id,)):
        vis[r["fragment_id"]] = r["visual_desc"]
        if r["embedding"]:
            try:
                from engine import embedding_model as _em
                emb[r["fragment_id"]] = _em.from_bytes(r["embedding"])
            except Exception:
                pass
    # 무음비는 VF(30초 창) 단위라 시간으로 겹치는 것을 가져온다
    vf = []
    for r in con.execute(
            "SELECT start_time, end_time, intelligence FROM fragments WHERE source_id=?",
            (source_id,)):
        try:
            intel = json.loads(r["intelligence"] or "{}")
        except Exception:
            intel = {}
        vf.append((float(r["start_time"] or 0), float(r["end_time"] or 0),
                   intel.get("silence_ratio")))
    units = []
    for r in rows:
        s, e = float(r["start"] or 0), float(r["end"] or 0)
        sil = None
        for a, b, v in vf:
            if b > s and a < e and v is not None:
                sil = float(v)
                break
        vd = vis.get(r["fragment_id"])
        units.append({
            "fragment_id": r["fragment_id"], "source_id": source_id,
            "start_ms": int(s * 1000 + 0.5), "end_ms": int(e * 1000 + 0.5),
            "tags": _tags(vd), "place": _place(vd), "silence": sil,
            "visual_desc": vd, "emb": emb.get(r["fragment_id"]),
        })
    return units


def _attach_dialogue(con, source_id, units):
    """대사 붙이기 — 전사가 있을 때만. 없으면 units 그대로(관찰 항목의 B 조건)."""
    import ledger_r0
    row = con.execute("SELECT segments FROM subtitles WHERE source_id=?",
                      (source_id,)).fetchone()
    if not row or not row["segments"]:
        return False
    try:
        segs = ledger_r0._parse_segments(row["segments"])
    except Exception:
        return False
    for u in units:
        s, e = u["start_ms"] / 1000.0, u["end_ms"] / 1000.0
        txt = " ".join((sg.get("text") or "").strip() for sg in segs
                       if sg.get("end", 0) > s and sg.get("start", 0) < e).strip()
        u["dialogue"] = txt
    return True


def _boundary(prev, cur, use_transcript, emb_cut=None):
    """여기서 장면이 바뀌는가 — 이유를 함께 돌려준다(사람이 검증할 수 있게).

    전부 전사 없이 판정한다(시간·VL·무음). 관찰 항목의 근거가 여기다."""
    if prev["place"] and cur["place"] and prev["place"] != cur["place"]:
        return "place"                       # 장소가 바뀌었다 (VL 라벨)
    gap = cur["start_ms"] - prev["end_ms"]
    if gap >= GAP_MS:
        return "gap"                         # 촬영이 끊겼다 (시간)
    pe, ce = prev.get("emb"), cur.get("emb")
    if pe is not None and ce is not None:
        import numpy as _np
        if float(_np.dot(pe, ce)) < (EMB_CUT if emb_cut is None else emb_cut):
            return "visual"                  # 보이는 것의 뜻이 달라졌다 (VL 임베딩)
    elif prev["tags"] and cur["tags"] and _jaccard(prev["tags"], cur["tags"]) < TAG_CUT:
        return "visual_tag"                  # 임베딩이 없을 때의 폴백
    if (prev.get("silence") is not None and cur.get("silence") is not None
            and abs(prev["silence"] - cur["silence"]) > 0.5):
        return "silence"                     # 소리 상태가 급변했다 (무음)
    return None


def group_source(source_id, use_transcript=True, emb_cut=None):
    """한 소스의 조각들을 장면 묶음(L1)으로. 읽기 전용."""
    con = _connect()
    try:
        units = _load_units(con, source_id)
        if not units:
            return []
        has_tx = _attach_dialogue(con, source_id, units) if use_transcript else False
    finally:
        con.close()

    groups = []
    cur = [units[0]]
    for prev, u in zip(units, units[1:]):
        why = _boundary(prev, u, use_transcript, emb_cut)
        too_big = (len(cur) >= MAX_ITEMS
                   or (u["end_ms"] - cur[0]["start_ms"]) >= MAX_SPAN_MS)
        if why or too_big:
            groups.append((cur, why or "size"))
            cur = [u]
        else:
            cur.append(u)
    groups.append((cur, "end"))

    out = []
    for idx, (members, why) in enumerate(groups, 1):
        tags = {}
        for m in members:
            for t in m["tags"]:
                tags[t] = tags.get(t, 0) + 1
        top = [t for t, _ in sorted(tags.items(), key=lambda x: -x[1])[:6]]
        places = [m["place"] for m in members if m["place"]]
        dialog = " ".join((m.get("dialogue") or "") for m in members).strip()
        out.append({
            "group_no": idx,
            "source_id": source_id,
            "start_ms": members[0]["start_ms"],
            "end_ms": members[-1]["end_ms"],
            "item_count": len(members),
            "place": places[0] if places else None,
            "top_tags": top,
            "boundary_reason": why,
            "fragment_ids": [m["fragment_id"] for m in members],
            "dialogue_chars": len(dialog),
            "dialogue_head": dialog[:120] if has_tx else None,
        })
    return out


def group_program(program_id, use_transcript=True, target=(12, 30)):
    """프로젝트의 모든 소스를 묶는다(촬영 순서대로).

    ★길이에 맞춰 스스로 조인다. 28분이든 5시간이든 사람이 읽을 수 있는 수
      (기본 12~30묶음)로 맞춘다 — 고정 문턱이면 하루치가 170묶음이 된다.
      조이는 방법은 문턱 한 개를 낮추는 것뿐이라 결정론이고 되돌릴 수 있다."""
    con = _connect()
    try:
        sids = [r[0] for r in con.execute(
            "SELECT source_id FROM project_sources WHERE program_id=? "
            "ORDER BY display_order", (program_id,))]
    finally:
        con.close()

    lo, hi = target
    cut = EMB_CUT
    out = []
    for _ in range(8):                       # 최대 8번만 조인다(폭주 방지)
        out = []
        for sid in sids:
            out.extend(group_source(sid, use_transcript=use_transcript, emb_cut=cut))
        if len(out) <= hi or cut <= 0.40:
            break
        cut = round(cut - 0.03, 3)           # 너무 잘게 쪼개졌다 → 덜 민감하게
    for i, g in enumerate(out, 1):
        g["group_no"] = i
        g["emb_cut"] = cut
    return out


def label_fixes(program_id):
    """사용자가 고친 장면 이름 — {group_no: label}. 마지막 정정이 이긴다.

    VL 은 센서라 틀린다(국장 실화면: 14번 '산' → 실제는 바닷가 바위).
    사람이 고친 것은 센서보다 위에 있다. append-only 원장이라 역사는 남는다."""
    out = {}
    con = _connect()
    try:
        rows = con.execute(
            "SELECT payload FROM project_timeline WHERE program_id=? "
            "AND kind='scene_label_fix' ORDER BY entry_id", (program_id,)).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    for r in rows:
        try:
            p = json.loads(r["payload"] or "{}")
        except Exception:
            continue
        no, lab = p.get("group_no"), str(p.get("label") or "").strip()
        if isinstance(no, int) and lab:
            out[no] = lab
    return out


def scene_label(g, fixes=None):
    """사람이 읽는 장면 이름. 사용자가 고친 것이 있으면 그것이 먼저."""
    if fixes:
        fixed = fixes.get(g.get("group_no"))
        if fixed:
            return fixed
    if g.get("place"):
        return g["place"]
    tags = g.get("top_tags") or []
    return " · ".join(tags[:2]) if tags else "장면"


def summary_lines(groups, limit=30, fixes=None):
    """젬마와 사람이 함께 읽는 L1 요약 — 짧게. 사용자가 고친 이름을 우선한다."""
    lines = []
    for g in groups[:limit]:
        t0 = g["start_ms"] / 1000.0
        t1 = g["end_ms"] / 1000.0
        head = f"{g['group_no']}. {int(t0 // 60)}분{int(t0 % 60):02d}초~{int(t1 // 60)}분{int(t1 % 60):02d}초"
        _fx = (fixes or {}).get(g["group_no"])
        where = f" · {_fx}(사용자가 고침)" if _fx else (f" · {g['place']}" if g["place"] else "")
        tags = f" · {', '.join(g['top_tags'][:4])}" if g["top_tags"] else ""
        lines.append(f"{head}{where} · 조각 {g['item_count']}개{tags}")
        if g.get("dialogue_head"):
            lines.append(f"   \"{g['dialogue_head'][:70]}\"")
    if len(groups) > limit:
        lines.append(f"… 외 {len(groups) - limit}묶음")
    return "\n".join(lines)
