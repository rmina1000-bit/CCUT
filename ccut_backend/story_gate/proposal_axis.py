# -*- coding: utf-8 -*-
"""[PROPOSAL-AXIS-01] 제안 축 — proposal = f(승인 스냅샷, 기법팩).

실측으로 확정된 위반 (Merope, 승인 id=51):
    승인 11조각 / 제안 A 9조각(교집합 2) / 제안 B 15조각(교집합 7) / A∩B = 2
    → 승인 시퀀스가 제안 생성에 전혀 들어가지 않았다. engine/ 전체에 승인 참조 0건.

이 모듈의 계약:
    조각·순서는 **승인 스냅파샷이 유일 출처**다 (story_approval.fragment_ids, live 행).
      선정(HRS)·재정렬(arrange/hook_first) 결과는 채택하지 않는다 — 덮어쓴다.
    A/B가 갈리는 축은 **기법팩 하나**뿐이다 (technique_id).
      현재 기법은 as_is 하나이므로 결과적으로 A == B가 된다. 그게 정상이고 정직하다.

불가침:
    INV-1  A.조각집합 == B.조각집합 == 승인 조각집합
    INV-2  A.순서     == B.순서     == 승인 순서
    INV-3  기법은 조각을 추가·삭제·재정렬하지 못한다 (경계·전환·호흡·리듬만).
"""
import json
import os
import hashlib
import random
import sqlite3

from .models import TABLE
from .service import _connect

# 현행 기법. 승인 시퀀스를 그대로 쓴다 — 경계도 손대지 않는다.
TECHNIQUE_AS_IS = "as_is"

# [PUNCH-1 P4] 첫 갈림 기법. 조각 경계를 건드리지 않는 **화면 변환**이므로 INV-3을 통과한다
#   (경계를 움직이는 기법은 재생/export가 9/13에서 갈리는 구조 결함에 걸린다 — C-AUDIT-1 L2).
TECHNIQUE_PUNCH_IN = "punch_in"
TECHNIQUE_WORD_BOUNDARY_SNAP = "word_boundary_snap"


def _flag_on(name):
    return os.getenv(name, "").strip().upper() in ("1", "ON", "TRUE", "YES")


def _word_snap_enabled():
    return _flag_on("CCUT_TECHNIQUE_WORD_SNAP")


def technique_for_mode(mode):
    """mode → technique. 순수 상수 사상 — DB를 타지 않으므로 미리보기·export가 같은 답을 얻는다."""
    m = str(mode or "").upper()
    if m == "A":
        return TECHNIQUE_PUNCH_IN
    if m == "B" and _word_snap_enabled():
        return TECHNIQUE_WORD_BOUNDARY_SNAP
    return TECHNIQUE_AS_IS

# [RULE-1 R4] 규칙 값은 코드 상수·주석이 아니라 config JSON 하나에 둔다.
#   구판(PUNCH-1 R1)은 검증용 1.60~2.20을 코드 상수로 박고 품질용 값을 주석에 보존했다.
#   주석은 규칙이 아니다 — 아무도 읽지 않고 아무것도 집행하지 않는다.
#   지금 유일한 출처: config/editing_techniques.json 의 punch_in.engine_effect.
#   국장은 그 파일 한 곳만 고치면 재생·미리보기·export 세 경로가 같이 움직인다.
_TECH_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "editing_techniques.json")

# motion → zoom 사상의 정의역. PUNCH-1 P3 실측(승인55 13조각 min 0.033263 / max 0.236912).
PUNCH_MOTION_LO, PUNCH_MOTION_HI = 0.03, 0.24

_PUNCH_CACHE = {}
_CFG_CACHE = None
_PACK_CACHE = {}


def _technique_node(technique_id):
    try:
        with open(_TECH_CONFIG_PATH, encoding="utf-8") as f:
            techs = json.load(f).get("techniques", [])
        return next((t for t in techs if t.get("technique_id") == technique_id), None)
    except Exception as e:
        print(f"[TECHNIQUE][CONFIG] 로드 실패 technique={technique_id}: {e}")
        return None


def _load_technique_catalog(config_path=None, extra_techniques=None):
    """기법 후보 목록은 JSON 자료에서만 읽는다. 테스트 후보는 extra_techniques로만 넣는다."""
    path = config_path or _TECH_CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    techniques = list(data.get("techniques") or [])
    if extra_techniques:
        techniques.extend(list(extra_techniques))
    return {
        "version": data.get("version"),
        "source": path,
        "techniques": techniques,
    }


def _as_json(raw):
    for _ in range(2):
        if not isinstance(raw, str):
            break
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    return raw


def _material_state_for_program(program_id):
    """현재 프로젝트가 팩 후보를 쓸 재료를 갖고 있는지 읽기 전용으로 센다."""
    state = {
        "word_timestamps": {"present": False, "count": 0},
        "speech_presence": {"present": False, "count": 0},
        "audio_beat": {"present": False, "count": 0},
        "duration": {"present": True, "count": 0},
        "transcript": {"present": False, "count": 0},
    }
    con = _connect()
    try:
        source_rows = con.execute(
            "SELECT source_id FROM project_sources WHERE program_id=? ORDER BY display_order, id",
            (program_id,),
        ).fetchall()
        source_ids = [r["source_id"] for r in source_rows if r["source_id"]]
        if not source_ids and program_id:
            source_ids = [program_id]

        for source_id in source_ids:
            for r in con.execute("SELECT segments FROM subtitles WHERE source_id=?", (source_id,)):
                segs = _as_json(r["segments"])
                if not isinstance(segs, list):
                    continue
                for seg in segs:
                    if not isinstance(seg, dict):
                        continue
                    words = seg.get("words") or []
                    for w in words:
                        if isinstance(w, dict) and w.get("start") is not None and w.get("end") is not None:
                            state["word_timestamps"]["count"] += 1
                    text = seg.get("text")
                    if isinstance(text, str) and text.strip():
                        state["transcript"]["count"] += 1

            for r in con.execute(
                "SELECT metadata_json FROM evidence_board WHERE source_id=?",
                (source_id,),
            ):
                meta = _as_json(r["metadata_json"]) or {}
                beats = meta.get("audio_beat") or []
                if isinstance(beats, list):
                    state["audio_beat"]["count"] += len(beats)

            for r in con.execute(
                "SELECT structural_json FROM semantic_fragments WHERE source_id=?",
                (source_id,),
            ):
                structural = _as_json(r["structural_json"]) or {}
                vad = (((structural.get("sensor_evidence") or {}).get("silero_vad") or {}).get("values") or {})
                if isinstance(vad.get("speech_ratio"), (int, float)):
                    state["speech_presence"]["count"] += 1
                if isinstance(structural.get("duration"), (int, float)):
                    state["duration"]["count"] += 1
    except sqlite3.OperationalError as e:
        state["error"] = str(e)
    finally:
        con.close()
    for item in state.values():
        if isinstance(item, dict):
            item["present"] = item.get("count", 0) > 0 or item.get("present") is True
    return state


def _gate_for_technique(technique_id):
    env_name = "CCUT_TECHNIQUE_" + str(technique_id or "").upper().replace("-", "_")
    generic = os.getenv(env_name)
    if generic is not None:
        return {"env": env_name, "on": _flag_on(env_name)}
    # 기존 운영 게이트 이름 호환. 게이트를 켜지는 않고 읽기만 한다.
    legacy_names = {
        "word_boundary_snap": "CCUT_TECHNIQUE_WORD_SNAP",
    }
    legacy = legacy_names.get(str(technique_id or ""))
    if legacy:
        return {"env": legacy, "on": _flag_on(legacy)}
    return None


def _technique_candidate(item, material_state):
    authority = item.get("authority") or {}
    verdict = authority.get("verdict")
    category = item.get("category")
    effect = item.get("engine_effect") or {}
    required = item.get("requires_materials")
    if required is None:
        required = item.get("required_signals") or []
    required = list(required or [])
    blockers = []
    for material in required:
        mat = material_state.get(material)
        if not mat or not mat.get("present"):
            blockers.append({"kind": "material_missing", "id": material})
    gate = _gate_for_technique(item.get("technique_id"))
    if gate and not gate["on"]:
        blockers.append({"kind": "gate_off", "id": gate["env"]})

    condition = " ".join(str(v) for v in (authority.get("basis") or []))
    condition += " " + str(authority.get("condition") or "")
    description = str(item.get("description") or "")
    boundary_only = (
        "조각 가장자리" in condition
        or "경계" in description
        or "컷 지점" in description
        or "snap_threshold_ms" in effect
    )
    usable_verdict = verdict in ("AI_ALLOWED", "AI_ALLOWED_CONDITIONAL") and boundary_only
    if not usable_verdict:
        blockers.append({"kind": "authority", "id": verdict or "UNKNOWN"})

    effect_keys = set(effect.keys())
    trimish = category in ("cutting", "pacing") or bool(
        effect_keys & {"snap_threshold_ms", "min_duration_sec", "max_pause_sec",
                       "compression_ratio", "cut_at_punctuation"}
    )
    return {
        "id": item.get("technique_id"),
        "category": category,
        "display_name": item.get("display_name"),
        "engine_effect": effect,
        "requires_materials": required,
        "gate": gate,
        "usable_now": usable_verdict and not blockers,
        "blockers": blockers,
        "trimish": trimish,
    }


def build_technique_pack(program_id=None, material_state=None, config_path=None,
                         extra_techniques=None, seed=None):
    """A/B가 쓸 수 있는 기법 후보를 자료에서 읽어 팩으로 만든다.

    조각 선택·순서는 건드리지 않는다. 여기서는 후보와 성향만 정한다.
    """
    catalog = _load_technique_catalog(config_path=config_path, extra_techniques=extra_techniques)
    materials = material_state or _material_state_for_program(program_id)
    candidates = [
        _technique_candidate(item, materials)
        for item in catalog["techniques"]
        if item.get("technique_id")
    ]
    usable_boundary = [c for c in candidates if c["usable_now"] and c["trimish"]]
    blocked = [c for c in candidates if not c["usable_now"]]
    seed_src = seed or f"{program_id or ''}:{catalog.get('version') or ''}:{len(candidates)}"
    rng = random.Random(int(hashlib.sha256(seed_src.encode("utf-8")).hexdigest()[:12], 16))
    shuffled = list(usable_boundary)
    rng.shuffle(shuffled)

    def _ids(items):
        return [c["id"] for c in items if c.get("id")]

    def _effects(items):
        return {c["id"]: c["engine_effect"] for c in items if c.get("id")}

    tight = shuffled[:3]
    relaxed = list(reversed(shuffled))[:3]
    pack = {
        "source": catalog["source"],
        "version": catalog["version"],
        "materials": materials,
        "candidate_count": len(candidates),
        "usable_now": _ids(usable_boundary),
        "blocked": [
            {"id": c["id"], "blockers": c["blockers"]}
            for c in blocked
        ],
        "variants": {
            "A": {
                "label_key": "coreOnly",
                "boundary_profile": "tight",
                "techniques": _ids(tight),
                "technique_effects": _effects(tight),
                "parameters": {
                    "edge_padding_ms": 80,
                    "max_trim_each_edge_ms": 4500,
                    "preserve_words": True,
                },
            },
            "B": {
                "label_key": "breathingRoom",
                "boundary_profile": "relaxed",
                "techniques": _ids(relaxed),
                "technique_effects": _effects(relaxed),
                "parameters": {
                    "edge_padding_ms": 1800,
                    "max_trim_each_edge_ms": 0,
                    "preserve_words": True,
                },
            },
        },
    }
    return pack


def technique_pack_for_project(program_id, reload=False):
    key = program_id or "__none__"
    if key not in _PACK_CACHE or reload:
        _PACK_CACHE[key] = build_technique_pack(program_id)
    return _PACK_CACHE[key]


def attach_technique_pack(proposals, program_id, reload=False):
    pack = technique_pack_for_project(program_id, reload=reload)
    print(
        f"[TECHNIQUE-PACK] program={program_id} source={pack['source']} "
        f"candidates={pack['candidate_count']} usable={pack['usable_now']} "
        f"A={pack['variants']['A']['techniques']} B={pack['variants']['B']['techniques']}",
        flush=True,
    )
    for proposal in proposals or []:
        mode = str(proposal.get("mode") or "").upper()
        variant = pack["variants"].get(mode)
        if not variant:
            continue
        proposal["technique_pack"] = variant
        reason = proposal.setdefault("proposal_reason", {})
        reason["technique_pack"] = {
            "source": pack["source"],
            "usable_now": pack["usable_now"],
            "variant": variant,
        }
    return proposals, pack


def punch_config(reload=False):
    """punch_in 규칙 값 — config JSON이 유일한 출처. 없으면 지어내지 않고 None을 돌려준다."""
    global _CFG_CACHE
    if _CFG_CACHE is not None and not reload:
        return _CFG_CACHE
    try:
        node = _technique_node(TECHNIQUE_PUNCH_IN)
        eff = (node or {}).get("engine_effect") or {}
        if not eff or "zoom_min" not in eff or "zoom_max" not in eff or "ramp_sec" not in eff:
            print(f"[PUNCH][CONFIG] punch_in.engine_effect 없음/불완전 — 기법 적용 불가")
            _CFG_CACHE = None
_PACK_CACHE = {}
            return None
        # hard_bounds = 기법이 **요청**하는 값(engine_effect)과 분리된 상한.
        #   같은 출처에서 읽으면 규칙이 절대 실패할 수 없어 집행이 아니라 장식이 된다.
        _CFG_CACHE = {"zoom_min": float(eff["zoom_min"]), "zoom_max": float(eff["zoom_max"]),
                      "ramp_sec": float(eff["ramp_sec"]),
                      "hard_bounds": (node or {}).get("hard_bounds") or None}
    except Exception as e:
        print(f"[PUNCH][CONFIG] 로드 실패 — 기법 적용 불가: {e}")
        _CFG_CACHE = None
_PACK_CACHE = {}
    return _CFG_CACHE


def reset_punch_caches():
    """config·spec 캐시 무효화 (값 조절 후 재판정용)."""
    global _CFG_CACHE
    _CFG_CACHE = None
_PACK_CACHE = {}
    _PUNCH_CACHE.clear()


# ── [RULE-1 R3] 하드룰 검사 함수 등록 ────────────────────────────────────────
def _check_technique_path_uniform(ctx):
    """RULE_TECHNIQUE_PATH_UNIFORM — 기법이 세 경로에서 같은 spec을 참조하는가.

    코드 정적 검사가 아니라 **런타임 동일성 비교**로 한다: 같은 조각에 대해
    미리보기(1280x720)·export(1920x1080)가 만드는 필터에서 (절대 펀치시각, 배율)을
    되뽑고, 재생 경로가 쓰는 punch_spec과 셋을 대조한다. 하나라도 다르면 VIOLATION.
    PUNCH-1에서 렌더 경로에만 기법이 걸리고 재생이 누락된 사고를 이 규칙이 잡는다.
    """
    from engine.story_template_resolver import VERDICT_PASS, VERDICT_VIOLATION, VERDICT_UNKNOWN
    fid = ctx.get("fragment_id")
    s, e = ctx.get("clip_start"), ctx.get("clip_end")
    if not fid or s is None or e is None:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "3 paths equal",
                "detail": "검사 입력(fragment_id/clip 경계) 없음"}
    spec = punch_spec(fid)
    if not spec:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "3 paths equal",
                "detail": "punch_spec 없음 — 근거 부족 조각"}

    def _derive(w, h):
        f = _punch_filter_raw(fid, float(s), float(e), w, h)
        if not f:
            return None
        try:
            t_rel = float(f.split("it,")[1].split(")")[0])
            zoom = float(f.split("min(")[1].split(",")[0])
            return (round(float(s) + t_rel, 3), zoom)
        except Exception:
            return None

    play = (spec["at"], spec["zoom"])            # 재생 경로(/punch → CenterPanel)
    prev = _derive(1280, 720)                    # 미리보기 경로
    exp = _derive(1920, 1080)                    # export 경로
    same = (play == prev == exp)
    return {"verdict": VERDICT_PASS if same else VERDICT_VIOLATION,
            "measured": {"playback": play, "preview": prev, "export": exp},
            "threshold": "playback == preview == export",
            "detail": "세 경로 동일" if same else "경로별 spec 불일치 — 기법 적용 차단"}


def _check_punch_zoom_bound(ctx):
    """RULE_PUNCH_ZOOM_BOUND — 배율·램프가 config 상하한 안인가."""
    from engine.story_template_resolver import VERDICT_PASS, VERDICT_VIOLATION, VERDICT_UNKNOWN
    cfg = punch_config()
    if not cfg:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": None,
                "detail": "config 없음 — 임계값을 모른다(0으로 위장하지 않음)"}
    hb = cfg.get("hard_bounds")
    if not hb:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": None,
                "detail": "hard_bounds 없음 — 상한을 모른다(임의 통과시키지 않음)"}
    spec = punch_spec(ctx.get("fragment_id")) if ctx.get("fragment_id") else None
    if not spec:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": hb,
                "detail": "punch_spec 없음"}
    z, r = spec["zoom"], cfg["ramp_sec"]
    lo, hi = float(hb["zoom_min_allowed"]), float(hb["zoom_max_allowed"])
    rmin = float(hb["ramp_min_sec"])
    ok = (lo <= z <= hi) and (r >= rmin)
    return {"verdict": VERDICT_PASS if ok else VERDICT_VIOLATION,
            "measured": {"zoom": z, "ramp_sec": r},
            "threshold": {"zoom": [lo, hi], "ramp_min_sec": rmin},
            "detail": "상하한 내" if ok else "상하한 초과 — 기법 적용 차단(Veto)"}


# ── [BOUNDARY-1 B4] 경계 규칙 3종 ───────────────────────────────────────────
def _hash6(s):
    """프론트 timelineItemIdFor 의 djb2 — 선호 item id 계산에 쓴다(같은 식이라야 같은 행을 고른다)."""
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return format(h, "x").rjust(6, "0")[-6:]


def boundary_spans(program_id, fragment_id):
    """재생·export 경계를 각자의 실제 코드 경로에서 뽑는다. 새 경로를 만들지 않는다.

    playback : edit_contract.service.list_edit_states (compile_spans) + 프론트 선택식
    export   : ledger_r0.get_render_edl (compile_spans)
    preview  : [BOUNDARY-1 B3] 이후 EDL 에 묶여 있으므로 export 와 같은 값이다.
               (구판은 proposal.sequence anchor 좌표였고 그게 갈림의 원인이었다)
    """
    import asyncio
    out = {"playback": None, "export": None, "preview": None}
    try:
        from edit_contract.service import list_edit_states
        states = list_edit_states(program_id)
        cands = [s for s in states if s.get("parent_fragment_id") == fragment_id]
        if cands:
            want = "ITEM_%s_%s_0" % (_hash6(program_id), fragment_id)
            st = next((c for c in cands if c["timeline_item_id"] == want), cands[0])
            out["playback"] = [[round(a / 1000.0, 3), round(b / 1000.0, 3)] for a, b in st["spans"]]
        else:
            con = _connect()
            try:
                r = con.execute('SELECT start,"end" FROM semantic_fragments WHERE fragment_id=?',
                                (fragment_id,)).fetchone()
            finally:
                con.close()
            if r:
                out["playback"] = [[round(float(r["start"]), 3), round(float(r["end"]), 3)]]
    except Exception as e:
        print(f"[BOUNDARY][WARN] playback spans 취득 실패: {e}")
    try:
        from ledger_r0 import get_render_edl
        edl = asyncio.new_event_loop().run_until_complete(get_render_edl(program_id))
        got = [[c["start_sec"], c["end_sec"]] for c in (edl.get("clips") or [])
               if c["fragment_id"] == fragment_id]
        out["export"] = got or None
    except Exception as e:
        print(f"[BOUNDARY][WARN] export spans 취득 실패: {e}")
    out["preview"] = out["export"]      # B3 이후 같은 출처 — 다르면 그건 배선이 풀린 것
    return out


def _fragment_words(fragment_id):
    """조각 구간에 속한 단어 [(start, end)]. 없으면 None (모른다 — 빈 리스트와 구별한다)."""
    con = _connect()
    try:
        r = con.execute('SELECT source_id, start, "end" FROM semantic_fragments WHERE fragment_id=?',
                        (fragment_id,)).fetchone()
        if r is None:
            return None
        s, e = float(r["start"] or 0), float(r["end"] or 0)
        sub = con.execute("SELECT segments FROM subtitles WHERE source_id=?", (r["source_id"],)).fetchone()
        if not sub or not sub["segments"]:
            return None
        segs = json.loads(sub["segments"])
        if isinstance(segs, str):
            segs = json.loads(segs)
        ws = [(float(w["start"]), float(w["end"])) for sg in segs for w in (sg.get("words") or [])
              if w.get("start") is not None and w.get("end") is not None
              and float(w["end"]) > s and float(w["start"]) < e]
        return ws or None
    except Exception:
        return None
    finally:
        con.close()


def _has_user_edit_state(program_id, fragment_id):
    """사용자가 직접 만진 경계가 있으면 semantic 경계 보정 대상이 아니다(INV-6).

    [LAB-45] 이름 정정: 구명 _has_edit_overlay 는 edit_overlay 를 읽는다고 읽혔으나
    실제 조회 대상은 처음부터 fragment_edit_state 였다. 이름이 거짓말을 해서
    'INV-6 보호가 폐기된 표를 본다'는 오진을 유발했다(LAB-45 실측으로 기각 —
    18/18 보호 정상). 이름을 실제와 맞춘다.
    """
    con = _connect()
    try:
        try:
            row = con.execute(
                "SELECT 1 FROM fragment_edit_state WHERE program_id=? "
                "AND parent_fragment_id=? LIMIT 1",
                (program_id, fragment_id),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None
    finally:
        con.close()


def _word_snap_threshold_ms():
    node = _technique_node(TECHNIQUE_WORD_BOUNDARY_SNAP)
    value = ((node or {}).get("engine_effect") or {}).get("snap_threshold_ms")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nearest_word_mark(edge_sec, words):
    marks = sorted({float(v) for w in (words or []) for v in w})
    if not marks:
        return None, None
    mark = min(marks, key=lambda item: abs(float(edge_sec) - item))
    return mark, abs(float(edge_sec) - mark) * 1000.0


def _snap_sequence_item(program_id, item, tol_ms):
    """proposal sequence item 하나를 단어 경계로 미세 보정한다.

    큰 이동은 하지 않는다. 200ms 밖이면 VIOLATION으로 남기고 값을 보존한다.
    """
    from engine.story_template_resolver import (
        VERDICT_PASS, VERDICT_VIOLATION, VERDICT_UNKNOWN, VERDICT_NA,
    )
    fid = item.get("fragment_id")
    if not fid:
        return dict(item), {"verdict": VERDICT_UNKNOWN, "detail": "fragment_id 없음"}
    if _has_user_edit_state(program_id, fid):
        return dict(item), {
            "verdict": VERDICT_NA,
            "fragment_id": fid,
            "detail": "fragment_edit_state 오버레이 존재 — 사용자 경계 보호",
        }
    words = _fragment_words(fid)
    if words is None:
        return dict(item), {
            "verdict": VERDICT_UNKNOWN,
            "fragment_id": fid,
            "detail": "word 타임스탬프 없음",
        }
    out = dict(item)
    changes = []
    violations = []
    for key in ("start", "end"):
        if out.get(key) is None:
            continue
        mark, dev_ms = _nearest_word_mark(float(out[key]), words)
        if mark is None or dev_ms is None:
            return dict(item), {
                "verdict": VERDICT_UNKNOWN,
                "fragment_id": fid,
                "detail": "단어 경계 없음",
            }
        if dev_ms > tol_ms:
            violations.append({"edge": key, "deviation_ms": round(dev_ms, 1)})
            continue
        before = float(out[key])
        out[key] = round(mark, 3)
        if abs(before - float(out[key])) > 0.0005:
            changes.append({
                "edge": key,
                "from": round(before, 3),
                "to": out[key],
                "deviation_ms": round(dev_ms, 1),
            })
    if float(out.get("end") or 0) <= float(out.get("start") or 0):
        return dict(item), {
            "verdict": VERDICT_UNKNOWN,
            "fragment_id": fid,
            "detail": "스냅 후 end <= start — 보정 보류",
        }
    if violations:
        return dict(item), {
            "verdict": VERDICT_VIOLATION,
            "fragment_id": fid,
            "measured": {"violations": violations},
            "detail": "허용오차 밖 — 큰 경계 이동 보류",
        }
    duration = round(float(out["end"]) - float(out["start"]), 3)
    out["duration"] = duration
    out["duration_sec"] = duration
    return out, {
        "verdict": VERDICT_PASS,
        "fragment_id": fid,
        "measured": {"changes": changes, "changed": bool(changes)},
        "detail": "단어 경계 스냅 적용" if changes else "이미 허용오차 내",
    }


def apply_word_boundary_snap(proposals, program_id):
    """B안 제안에 word_boundary_snap을 적용한다. 조각 집합·순서는 바꾸지 않는다."""
    if not _word_snap_enabled():
        return proposals, {"enabled": False, "applied": 0, "results": []}
    tol_ms = _word_snap_threshold_ms()
    if tol_ms is None:
        return proposals, {
            "enabled": True,
            "applied": 0,
            "results": [{"verdict": "UNKNOWN", "detail": "snap_threshold_ms 없음"}],
        }
    report = {"enabled": True, "threshold_ms": tol_ms, "applied": 0, "results": []}
    for proposal in (proposals or []):
        if proposal.get("technique_id") != TECHNIQUE_WORD_BOUNDARY_SNAP:
            continue
        snapped = []
        for item in (proposal.get("sequence") or []):
            new_item, result = _snap_sequence_item(program_id, item, tol_ms)
            snapped.append(new_item)
            result["mode"] = proposal.get("mode")
            report["results"].append(result)
        proposal["sequence"] = snapped
        proposal["duration"] = round(sum(
            float(s.get("duration_sec") or s.get("duration") or 0) for s in snapped
        ), 2)
        proposal.setdefault("proposal_reason", {})["applied_technique"] = TECHNIQUE_WORD_BOUNDARY_SNAP
        report["applied"] += 1
    return proposals, report


def _check_boundary_path_uniform(ctx):
    """RULE_BOUNDARY_PATH_UNIFORM — 재생·미리보기·export 가 같은 경계를 읽는가."""
    from engine.story_template_resolver import (VERDICT_PASS, VERDICT_VIOLATION,
                                                VERDICT_UNKNOWN, VERDICT_NA)
    fid, prog = ctx.get("fragment_id"), ctx.get("program_id")
    if not fid or not prog:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "3 paths equal",
                "detail": "program_id/fragment_id 없음"}
    sp = boundary_spans(prog, fid)
    if sp["playback"] is None or sp["export"] is None:
        return {"verdict": VERDICT_UNKNOWN, "measured": sp, "threshold": "3 paths equal",
                "detail": "경로 중 하나를 측정하지 못함"}
    same = (sp["playback"] == sp["export"] == sp["preview"])
    return {"verdict": VERDICT_PASS if same else VERDICT_VIOLATION, "measured": sp,
            "threshold": "playback == preview == export",
            "detail": "세 경로 동일" if same else "경계 불일치 — 산출물이 재생과 달라진다"}


def _check_no_mid_word_cut(ctx):
    """RULE_NO_MID_WORD_CUT — span 경계가 단어 **내부**를 자르는가.

    [INV-6] 사용자가 명시적으로 자른 자리를 되돌리지 않는다. 이 규칙은 경고만 한다.
    """
    from engine.story_template_resolver import VERDICT_PASS, VERDICT_VIOLATION, VERDICT_UNKNOWN
    fid, prog = ctx.get("fragment_id"), ctx.get("program_id")
    words = _fragment_words(fid) if fid else None
    if words is None:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "no cut inside a word",
                "detail": "word 타임스탬프 없음 — 검사 불가(모른다)"}
    sp = boundary_spans(prog, fid) if prog else None
    spans = (sp or {}).get("export")
    if not spans:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": "no cut inside a word",
                "detail": "spans 측정 실패"}
    hits = []
    for a, b in spans:
        for ws, we in words:
            if ws < a < we:
                hits.append({"edge": "start", "t": a, "word": [round(ws, 3), round(we, 3)]})
            if ws < b < we:
                hits.append({"edge": "end", "t": b, "word": [round(ws, 3), round(we, 3)]})
    return {"verdict": VERDICT_PASS if not hits else VERDICT_VIOLATION,
            "measured": {"spans": spans, "mid_word_cuts": hits[:4], "n": len(hits)},
            "threshold": "no cut inside a word",
            "detail": "단어 내부 절단 없음" if not hits
                      else "단어 내부 절단 — 경고만(사용자 결정 우선, INV-6)"}


def _check_word_boundary_snap(ctx):
    """RULE_WORD_BOUNDARY_SNAP — span 경계가 가장 가까운 단어 경계에서 얼마나 떨어졌나.

    허용오차 출처: config/editing_techniques.json 의 word_boundary_snap.engine_effect
    .snap_threshold_ms (실재 자산 200ms). 문서 BROADCAST_EDITING_ACTIVATION_PLAN 에는
    스냅 허용오차 값이 없다 — 없는 것을 있다고 적지 않는다.
    """
    from engine.story_template_resolver import VERDICT_PASS, VERDICT_VIOLATION, VERDICT_UNKNOWN
    tol_ms = None
    try:
        node = _technique_node(TECHNIQUE_WORD_BOUNDARY_SNAP)
        tol_ms = ((node or {}).get("engine_effect") or {}).get("snap_threshold_ms")
    except Exception:
        pass
    if tol_ms is None:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": None,
                "detail": "snap_threshold_ms 없음 — 허용오차를 모른다"}
    fid, prog = ctx.get("fragment_id"), ctx.get("program_id")
    if prog and fid and _has_user_edit_state(prog, fid):
        from engine.story_template_resolver import VERDICT_NA
        return {"verdict": VERDICT_NA, "measured": {"fragment_id": fid},
                "threshold": {"snap_threshold_ms": tol_ms},
                "detail": "fragment_edit_state 오버레이 존재 — 사용자 경계 보호(INV-6)"}
    words = _fragment_words(fid) if fid else None
    if words is None:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": {"snap_threshold_ms": tol_ms},
                "detail": "word 타임스탬프 없음 — 검사 불가(모른다)"}
    sp = boundary_spans(prog, fid) if prog else None
    spans = (sp or {}).get("export")
    if not spans:
        return {"verdict": VERDICT_UNKNOWN, "measured": None, "threshold": {"snap_threshold_ms": tol_ms},
                "detail": "spans 측정 실패"}
    edges = [t for a, b in spans for t in (a, b)]
    marks = sorted({v for w in words for v in w})
    devs = [round(min(abs(t - m) for m in marks) * 1000.0, 1) for t in edges] if marks else []
    worst = max(devs) if devs else None
    ok = worst is not None and worst <= float(tol_ms)
    return {"verdict": VERDICT_PASS if ok else VERDICT_VIOLATION,
            "measured": {"deviations_ms": devs, "worst_ms": worst},
            "threshold": {"snap_threshold_ms": tol_ms},
            "detail": "허용오차 내" if ok else "허용오차 초과 — 경고만(사용자 결정 우선, INV-6)"}


def _register_rules():
    try:
        from engine.story_template_resolver import register_rule_check
        register_rule_check("RULE_TECHNIQUE_PATH_UNIFORM", _check_technique_path_uniform)
        register_rule_check("RULE_PUNCH_ZOOM_BOUND", _check_punch_zoom_bound)
        # [BOUNDARY-1 B4] 경계 3종. WORD_BOUNDARY_SNAP은 AI semantic 경계 한정으로 집행 가능.
        register_rule_check("RULE_BOUNDARY_PATH_UNIFORM", _check_boundary_path_uniform)
        register_rule_check("RULE_NO_MID_WORD_CUT", _check_no_mid_word_cut)
        register_rule_check("RULE_WORD_BOUNDARY_SNAP", _check_word_boundary_snap)
    except Exception as e:
        print(f"[RULE][REGISTER] 등록 실패: {e}")


# [BOUNDARY-1 B4 · INV-6] 사용자 오버레이는 집행 대상이 아니다.
#   WORD_BOUNDARY_SNAP은 semantic_fragments AI 경계에만 적용된다.
# [LAB-43 ⓐ 국장 판정 2026-07-30] RULE_WORD_BOUNDARY_SNAP 을 veto 에서 뺀다.
#   근거: _check_word_boundary_snap 의 판정문이 스스로 "경고만(사용자 결정 우선,
#   INV-6)"이라 적으면서 veto 목록에 있어, 검사 함수와 등록부가 어긋나 있었다.
#   지금까지는 ctx 에 program_id 가 없어 늘 UNKNOWN 이라 모순이 드러나지 않았고,
#   LAB-43 이 program_id 를 이어 붙이자 승인 4조각 중 2건의 punch_in 이 차단됐다
#   (worst_ms 230·1200 > 임계 200). 경고는 경고로 집행한다 — WARN(run_boundary_checks)
#   으로 위반은 계속 기록되고, 기법 적용을 막지는 않는다.
VETO_RULE_IDS = ("RULE_PUNCH_ZOOM_BOUND", "RULE_TECHNIQUE_PATH_UNIFORM")


def punch_spec(fragment_id):
    """[PUNCH-1] 조각의 펀치인 지점·배율. 저장하지 않는 계산 결과(파생) — 좌표를 굽지 않는다.

    지점 = 첫 말 시작(subtitles word timestamps). 말이 없으면 구간 내 첫 beat.
    배율 = fragment_index.motion_score 선형 사상. motion이 NULL이면 배율 근거가 없으므로
           펀치인을 생략한다 — 모르는 값을 지어내지 않는다(INV-4).
    반환: {"at": 절대 소스 초, "zoom": float, "basis": str} 또는 None
    """
    if fragment_id in _PUNCH_CACHE:
        return _PUNCH_CACHE[fragment_id]
    spec = None
    con = _connect()
    try:
        row = con.execute(
            'SELECT source_id, start, "end", semantic_json FROM semantic_fragments '
            'WHERE fragment_id=?', (fragment_id,)).fetchone()
        if row is None:
            _PUNCH_CACHE[fragment_id] = None
            return None
        src, s, e = row["source_id"], float(row["start"] or 0), float(row["end"] or 0)

        mrow = con.execute("SELECT motion_score FROM fragment_index WHERE fragment_id=?",
                           (fragment_id,)).fetchone()
        motion = None if (mrow is None or mrow["motion_score"] is None) else float(mrow["motion_score"])
        if motion is None:
            _PUNCH_CACHE[fragment_id] = None
            return None

        at, basis = None, None
        sub = con.execute("SELECT segments FROM subtitles WHERE source_id=?", (src,)).fetchone()
        if sub and sub["segments"]:
            try:
                segs = json.loads(sub["segments"])
                if isinstance(segs, str):        # 이중 인코딩 (실측 확인됨)
                    segs = json.loads(segs)
                starts = [float(w["start"]) for sg in segs for w in (sg.get("words") or [])
                          if w.get("start") is not None and s <= float(w["start"]) < e]
                if starts:
                    at, basis = min(starts), "word_first"
            except Exception:
                pass
        if at is None:
            try:
                refs = (json.loads(row["semantic_json"] or "{}") or {}).get("evidence_refs") or []
            except Exception:
                refs = []
            beats = []
            if refs:
                ph = ",".join("?" for _ in refs)
                for r in con.execute(
                        "SELECT metadata_json FROM evidence_board WHERE fragment_id IN (%s)" % ph, refs):
                    try:
                        beats += (json.loads(r["metadata_json"] or "{}") or {}).get("audio_beat") or []
                    except Exception:
                        pass
            inb = sorted(t for t in beats if s <= float(t) < e)
            if inb:
                at, basis = float(inb[0]), "beat_first"
        if at is None:
            _PUNCH_CACHE[fragment_id] = None
            return None

        cfg = punch_config()
        if not cfg:                       # 규칙 값을 모르면 기법을 적용하지 않는다 (지어내지 않음)
            _PUNCH_CACHE[fragment_id] = None
            return None
        t = max(0.0, min(1.0, (motion - PUNCH_MOTION_LO) / (PUNCH_MOTION_HI - PUNCH_MOTION_LO)))
        zoom = round(cfg["zoom_min"] + (cfg["zoom_max"] - cfg["zoom_min"]) * t, 4)
        spec = {"at": round(at, 3), "zoom": zoom, "basis": basis, "motion": motion}
    except sqlite3.OperationalError:
        spec = None
    finally:
        con.close()
    _PUNCH_CACHE[fragment_id] = spec
    return spec


def _punch_filter_raw(fragment_id, clip_start, clip_end, out_w, out_h, fps=30):
    """규칙 검사 **전**의 순수 필터 산출. 검사 함수가 세 경로를 비교할 때 쓴다(재귀 방지)."""
    spec = punch_spec(fragment_id)
    cfg = punch_config()
    if not spec or not cfg:
        return None
    at, ramp = spec["at"], cfg["ramp_sec"]
    if not (clip_start <= at < clip_end - ramp):
        return None
    t_rel = round(at - clip_start, 3)      # -ss 입력이라 클립 타임스탬프는 0부터 시작
    z = spec["zoom"]
    return (
        "zoompan=z='if(lt(it,{t}),1,min({z},1+({z}-1)*(it-{t})/{r}))'"
        ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={f}"
    ).format(t=t_rel, z=z, r=ramp, w=out_w, h=out_h, f=fps)


def program_id_for_proposal(proposal_id):
    """[LAB-43] proposal → program_id. veto ctx 를 채우는 유일한 경로.

    구판은 punch_rule_results ctx 에 program_id 가 없어 RULE_WORD_BOUNDARY_SNAP 이
    항상 UNKNOWN 을 반환했고, has_veto 는 VIOLATION 만 보므로 차단이 서지 않았다
    (LAB-15 감사가 'veto_unreachable' 로 값 확정). 여기서 값을 만들어 도달시킨다.
    못 찾으면 None — 구동작(UNKNOWN, 차단 없음) 그대로다.
    """
    if not proposal_id:
        return None
    try:
        con = _connect()
        try:
            row = con.execute(
                "SELECT program_id FROM proposals WHERE proposal_id=?",
                (proposal_id,)).fetchone()
        finally:
            con.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def punch_rule_results(fragment_id, clip_start, clip_end, program_id=None):
    """[RULE-1 R3] 기법 적용 판정에 쓰는 규칙만 돌린다(Veto 대상). raw 로그는 check_rules가 남긴다.

    경계 3종은 여기서 돌리지 않는다 — 렌더 루프마다 EDL을 다시 뽑으면 비싸다.
    경계 검사는 boundary_rule_results()로 따로 부른다.
    [LAB-43] program_id 전달 — 없으면 VETO_RULE_IDS 안의 경계 룰이 영원히 UNKNOWN 이었다.
    """
    from engine.story_template_resolver import check_rules
    ctx = {"fragment_id": fragment_id, "clip_start": clip_start,
           "clip_end": clip_end, "technique": TECHNIQUE_PUNCH_IN}
    if program_id:
        ctx["program_id"] = program_id
    return check_rules(ctx, rule_ids=list(VETO_RULE_IDS))


def boundary_rule_results(program_id, fragment_id):
    """[BOUNDARY-1 B4] 경계 규칙 3종 판정. 로그 전용 — 어떤 것도 산출물을 막지 않는다."""
    from engine.story_template_resolver import check_rules
    return check_rules({"program_id": program_id, "fragment_id": fragment_id},
                       rule_ids=["RULE_BOUNDARY_PATH_UNIFORM", "RULE_NO_MID_WORD_CUT",
                                 "RULE_WORD_BOUNDARY_SNAP"])


def run_boundary_checks(program_id, fragment_ids):
    """[LAB-43] 경계 규칙 3종을 실제로 돌린다.

    구판은 boundary_rule_results() 를 정의만 하고 **아무도 부르지 않았다**
    (LAB-43 STEP 0 실측: 호출자 0건). 감사기는 이 셋을 '로그 전용'이라 적었지만
    실상은 한 번도 실행되지 않는 무등작이었다. 승인 직후 여기서 돌려 위반을
    사실로 남긴다 — 값은 바꾸지 않는다(경고 전용, INV-6 사용자 경계 우선).
    """
    summary = {"checked": 0, "violations": [], "unknown": 0, "na": 0, "pass": 0}
    for fid in fragment_ids or []:
        try:
            results = boundary_rule_results(program_id, fid)
        except Exception as e:
            print(f"[BOUNDARY-RULE][WARN] {fid} 검사 실패(비차단): {e}", flush=True)
            continue
        summary["checked"] += 1
        for r in results:
            verdict = r.get("verdict")
            if verdict == "VIOLATION":
                summary["violations"].append({
                    "fragment_id": fid, "rule_id": r.get("rule_id"),
                    "detail": r.get("detail"), "measured": r.get("measured"),
                })
            elif verdict == "UNKNOWN":
                summary["unknown"] += 1
            elif verdict == "NA":
                summary["na"] += 1
            else:
                summary["pass"] += 1
    print(f"[BOUNDARY-RULE] program={program_id} 조각={summary['checked']} "
          f"pass={summary['pass']} 위반={len(summary['violations'])} "
          f"unknown={summary['unknown']} na={summary['na']}", flush=True)
    for v in summary["violations"][:5]:
        print(f"[BOUNDARY-RULE][VIOLATION] {v['rule_id']} {v['fragment_id']}: "
              f"{v['detail']}", flush=True)
    return summary


def punch_filter(technique, fragment_id, clip_start, clip_end, out_w, out_h, fps=30,
                 program_id=None):
    """[PUNCH-1] 미리보기·렌더가 **같이 부르는 단일 함수**. ffmpeg -vf 조각 또는 None.

    좌표(clip_start/clip_end)는 읽기만 하고 바꾸지 않는다 — 경계 불변(INV-3).
    [RULE-1 R3] 규칙 위반(VIOLATION)이면 기법을 적용하지 않는다(Veto).
      UNKNOWN은 차단하지 않는다 — 모르는 것과 위반은 다르다.
    """
    if technique != TECHNIQUE_PUNCH_IN or not fragment_id:
        return None
    f = _punch_filter_raw(fragment_id, clip_start, clip_end, out_w, out_h, fps)
    if not f:
        return None
    try:
        from engine.story_template_resolver import has_veto
        results = punch_rule_results(fragment_id, clip_start, clip_end, program_id)
        if has_veto(results):
            bad = [r["rule_id"] for r in results if r.get("verdict") == "VIOLATION"]
            print(f"[RULE][VETO] punch_in 적용 차단 fragment={fragment_id} 위반규칙={bad}")
            return None
    except Exception as e:
        print(f"[RULE][WARN] 검사 실패 — 기법은 유지하고 사실만 남긴다: {e}")
    return f


_register_rules()


def live_approval_snapshot(program_id):
    """유효 승인 1건의 (approval_id, fids). 없으면 (None, [])."""
    con = _connect()
    try:
        row = con.execute(
            f"SELECT approval_id, fragment_ids FROM {TABLE} "
            f"WHERE program_id=? AND superseded_by IS NULL "
            f"ORDER BY approval_id DESC LIMIT 1",
            (program_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None, []          # Cutover 전 운영 DB — 승인 없음
    finally:
        con.close()
    if row is None:
        return None, []
    try:
        fids = json.loads(row["fragment_ids"])
    except Exception:
        fids = []
    return row["approval_id"], [str(f) for f in fids if f]


def _fragment_rows(fids):
    """fid → semantic_fragments 행(dict). 승인 조각이 엔진 결과에 없을 때의 보충용.

    [PLAYSTABILITY-FIX-01 2번] video_url을 함께 채운다.
      구판은 좌표·의미만 채워 재생원(video_url)이 빠졌다 — 실측: A 11조각 중 3조각 결손
      (idx 2·4·7). 프론트 playFrag는 video_url이 없고 getVideoUrlForFrag 폴백도 실패하면
      `[PLAYFRAG][BLOCKED]`로 재생을 중단한다. 엔진 경로(proposal_engine:566-572)와 같은
      규칙(프록시 우선 → uploads)을 쓴다 — 재생원 해석이 경로마다 갈리면 안 된다.
    """
    if not fids:
        return {}
    con = _connect()
    try:
        ph = ",".join("?" for _ in fids)
        rows = con.execute(
            f'SELECT sf.fragment_id, sf.source_id, sf.start, sf."end", sf.semantic_json, '
            f'sf.structural_json, sf.continuity_json, sf.confidence, s.file_path '
            f'FROM semantic_fragments sf LEFT JOIN sources s ON s.source_id = sf.source_id '
            f'WHERE sf.fragment_id IN ({ph})',
            list(fids),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    out = {}
    for r in rows:
        def _j(v):
            try:
                return json.loads(v) if v else {}
            except Exception:
                return {}
        out[r["fragment_id"]] = {
            "fragment_id": r["fragment_id"],
            "source_id": r["source_id"],
            "start": r["start"],
            "end": r["end"],
            "duration": (r["end"] or 0) - (r["start"] or 0),
            "duration_sec": (r["end"] or 0) - (r["start"] or 0),
            "semantic": _j(r["semantic_json"]),
            "structural": _j(r["structural_json"]),
            "continuity": _j(r["continuity_json"]),
            "confidence": r["confidence"],
            "video_url": _video_url_for(r["file_path"], r["source_id"]),
            "thumbnail_url": _thumb_url_for(r["fragment_id"]),
        }
    return out


def _video_url_for(file_path, source_id):
    """재생원 URL — 엔진 경로(proposal_engine)·원장 경로(fragment_show)와 같은 규칙."""
    try:
        from engine.fragment_show import _video_url
        return _video_url(file_path, source_id)
    except Exception:
        # 폴백: 규칙만 그대로 재현 (프록시 존재 여부는 판단하지 않는다 — 정직하게 uploads)
        import os
        from urllib.parse import quote
        name = os.path.basename(file_path or "") or f"{source_id}.mp4"
        return f"/static/uploads/{quote(name, safe='')}"


def _thumb_url_for(fragment_id):
    """썸네일 — 있으면 붙이고 없으면 None (없는 걸 있다고 하지 않는다)."""
    try:
        from engine.fragment_show import THUMBS_DIR
        import os
        return (f"/static/thumbnails/{fragment_id}.jpg"
                if os.path.exists(os.path.join(THUMBS_DIR, f"{fragment_id}.jpg")) else None)
    except Exception:
        return None


def _seq_fids(sequence):
    return [str(s.get("fragment_id")) for s in (sequence or []) if isinstance(s, dict) and s.get("fragment_id")]


def _alive_fragment_ids(fids):
    """[SEQ-ANCHOR] 그중 **현행 semantic_fragments 에 실제로 있는** fid 집합."""
    if not fids:
        return set()
    con = _connect()
    try:
        ph = ",".join("?" for _ in fids)
        rows = con.execute(
            f"SELECT fragment_id FROM semantic_fragments WHERE fragment_id IN ({ph})",
            list(fids),
        ).fetchall()
        return {r["fragment_id"] for r in rows}
    except sqlite3.OperationalError:
        return set()
    finally:
        con.close()


def _rematch_by_anchor(missing_fids, by_fid, approval_fids):
    """[SEQ-ANCHOR 2026-08-01] fid 로 못 찾은 조각을 **좌표로 다시 잇는다.**

    왜 필요한가(실측): 승인 원고·제안이 담은 fid 는 재조각화로 분절 경계가 바뀌면 죽는다.
      story_approval 최신 승인 5행 36 fid 중 10건(27.8%) · proposals 42 중 13건(30.9%) 끊김.
      fid 는 sha1(source_id|start_ds|end_ds)[:6] 결정론이라 경계가 바뀔 때만 달라진다.
      그런데 읽기 경로는 :753 `WHERE sf.fragment_id IN (...)` 문자열 일치 하나뿐이었고,
      못 찾은 fid 는 :853 에서 **조용히 시퀀스에서 빠졌다** — 사용자는 9조각을 승인했는데
      A 는 3조각만 남는다. 예외도 경고도 없이 줄어든다.

    좌표는 어디서 오는가: 이미 저장돼 있다. proposals.sequence[] 의 각 dict 가
      source_id + start/end 를 함께 갖고 있고(archive/manager.py:667-680), 승인 시점의
      제안 dict 가 by_fid 에 그대로 들어온다. 새로 만들 게 없다 — 읽지 않았을 뿐이다.

    ★ 재매칭식을 복제하지 않는다. 편집 상태가 쓰는 계약 함수를 그대로 부른다
      (edit_contract/edit_state.py:128 rematch_anchor). 같은 일을 하는 자리가 둘이면
      언젠가 다르게 판정한다.
    ★ 허용오차 3000ms 는 실측값이다(원고 재연결과 같은 값, Index.tsx 와 동일).
      끊긴 원고 300건 드리프트: 중앙값 840ms · 90% 1840ms · 최대 2980ms.
      모든 오차 구간에서 다중 후보 0건 — 양끝을 다 요구해 오매칭이 관측되지 않았다.
    ★ 못 찾으면 UNKNOWN 이다. 가까운 걸 아무거나 붙이지 않는다.

    반환: {옛 fid: 현 세대 조각 dict}
    """
    if not missing_fids:
        return {}
    from edit_contract.edit_state import rematch_anchor
    from edit_contract.time_units import to_ms

    # 옛 좌표: 승인/제안 dict 안에 이미 있는 값만 쓴다. 없으면 지어내지 않는다.
    anchors = {}
    for fid in missing_fids:
        row = by_fid.get(fid) or {}
        sid = str(row.get("source_id") or "")
        s, e = row.get("start"), row.get("end")
        if not sid or s is None or e is None:
            continue
        try:
            anchors[fid] = (sid, to_ms(float(s)), to_ms(float(e)))
        except Exception:
            continue
    if not anchors:
        return {}

    # 후보: 그 소스들의 현행 조각을 시간순으로 (rematch_anchor 계약이 정렬을 요구한다)
    con = _connect()
    try:
        sids = sorted({a[0] for a in anchors.values()})
        ph = ",".join("?" for _ in sids)
        rows = con.execute(
            f'SELECT fragment_id, source_id, start, "end" FROM semantic_fragments '
            f'WHERE source_id IN ({ph}) ORDER BY source_id, start', list(sids),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()

    cand = {}
    for r in rows:
        cand.setdefault(r["source_id"], []).append(
            (r["fragment_id"], to_ms(float(r["start"])), to_ms(float(r["end"]))))

    found = {}
    for fid, (sid, a_s, a_e) in anchors.items():
        lst = cand.get(sid) or []
        idx = rematch_anchor((a_s, a_e), [(c[1], c[2]) for c in lst], SEQ_REMATCH_TOL_MS)
        if idx is None:
            continue
        found[fid] = lst[idx][0]
    if not found:
        return {}
    resolved = _fragment_rows(list(found.values()))
    return {old: resolved[new] for old, new in found.items() if new in resolved}


# 원고 재연결과 같은 값(ccut_frontend/src/pages/Index.tsx STORY_REMATCH_TOL_MS).
# 실측 근거는 _rematch_by_anchor 주석 참조. 임의 조정 금지.
SEQ_REMATCH_TOL_MS = 3000


def rebuild_from_approval(proposals, approval_fids, pool_fragments=None):
    """A/B의 sequence를 **승인 fids 순서 그대로** 재구성한다 (INV-1·INV-2 강제).

    조각 dict는 (1) 엔진 결과 (2) 조각 pool (3) DB 순으로 찾아 채운다 — 좌표·썸네일 등
    기존 필드를 최대한 보존해 렌더·EDL·미리보기 경로의 입력 형태를 바꾸지 않는다.
    반환: (proposals, report) — report는 조각을 못 찾은 fid 목록(정직 표기).
    """
    by_fid = {}
    for p in (proposals or []):
        for s in (p.get("sequence") or []):
            if isinstance(s, dict) and s.get("fragment_id"):
                by_fid.setdefault(str(s["fragment_id"]), s)
    for f in (pool_fragments or []):
        if isinstance(f, dict) and f.get("fragment_id"):
            by_fid.setdefault(str(f["fragment_id"]), f)

    missing = [fid for fid in approval_fids if fid not in by_fid]
    if missing:
        by_fid.update(_fragment_rows(missing))

    # [PLAYSTABILITY-FIX-01 2번] '있다'와 '재생할 수 있다'는 다르다.
    #   조각 pool(all_fragments)에는 fid가 있지만 video_url이 없다 — 그 dict가 그대로 채택되면
    #   프론트 playFrag가 `[PLAYFRAG][BLOCKED]`로 재생을 중단한다(실측: idx 2·4·7 결손).
    #   그래서 fid 부재가 아니라 **재생원 부재**를 기준으로 한 번 더 보충한다.
    playable_gap = [fid for fid in approval_fids
                    if fid in by_fid and not (by_fid[fid] or {}).get("video_url")]
    if playable_gap:
        for fid, row in _fragment_rows(playable_gap).items():
            merged = dict(by_fid[fid])          # 기존 필드(좌표·의미·썸네일) 보존
            for k in ("video_url", "thumbnail_url"):
                if not merged.get(k) and row.get(k):
                    merged[k] = row[k]
            by_fid[fid] = merged
        still = [fid for fid in playable_gap if not (by_fid[fid] or {}).get("video_url")]
        print(f"[PROPOSAL-AXIS] video_url 보충: 대상 {len(playable_gap)}건, 남은 결손 {len(still)}건"
              + (f" {still[:3]}" if still else ""))

    # [SEQ-ANCHOR 2026-08-01] fid 가 현행 조각을 가리키지 못하면 **좌표로 다시 잇는다.**
    #   ① fid 직접 매칭(위) → ② 좌표 재매칭(여기) → ③ 둘 다 실패면 UNKNOWN.
    #
    #   ★ 판정 기준이 'by_fid 에 dict 가 있는가'가 아니라 **'현행 semantic_fragments 에
    #     그 조각이 실제로 있는가'**다. 구판(:853)은 dict 유무만 봤는데, by_fid 는 저장된
    #     제안의 sequence 로도 채워지므로 **죽은 조각의 낡은 dict 가 그대로 통과**했다.
    #     실측(살아있는 프로그램 현행 승인): SA#59 3건 · SA#32 5건이 이 경로로 통과 중이었다 —
    #     화면에는 뜨는데 그 fid 의 조각은 semantic_fragments 에 없다.
    #     'dict 가 있다'와 '조각이 있다'는 다르다. 뒤엣것을 기준으로 삼는다.
    alive_fids = _alive_fragment_ids(approval_fids)
    stale = [fid for fid in approval_fids if fid not in alive_fids]
    rematched = {}
    if stale:
        rematched = _rematch_by_anchor(stale, by_fid, approval_fids)
        by_fid.update(rematched)
    still_missing = [fid for fid in approval_fids if fid not in by_fid]

    unresolved = [fid for fid in approval_fids if fid not in by_fid]

    if rematched or unresolved:
        print(f"[SEQ-ANCHOR] 승인 {len(approval_fids)}조각 — 현행 조각 직행 "
              f"{len(approval_fids) - len(stale)} · 좌표 재연결 {len(rematched)} · "
              f"못 찾음 {len(unresolved)}", flush=True)

    # ③ 조용히 빼지 않는다. 구판은 못 찾은 fid 를 아래 시퀀스 구성에서 그냥 건너뛰어
    #   사용자가 9조각을 승인하고 3조각만 받아도 아무 신호가 없었다(로그 한 줄뿐).
    #   원장에 남겨 화면이 알 수 있게 한다. 신고 실패가 본선을 죽이지 않는다.
    if unresolved:
        try:
            import failure_ledger as _fl_seq
            _fl_seq.record(
                "story", "approval_fids_unresolved",
                phase="rebuild_from_approval",
                detail={
                    "approved": len(approval_fids),
                    "fid_direct": len(approval_fids) - len(stale),
                    "rematched_by_anchor": len(rematched),
                    "unresolved": len(unresolved),
                    "first3": list(unresolved[:3]),
                },
            )
        except Exception as _e_seq:
            print(f"[SEQ-ANCHOR][LEDGER-BROKEN] 신고 실패(본선 계속): {_e_seq}", flush=True)

    for p in (proposals or []):
        p["sequence"] = [dict(by_fid[fid]) for fid in approval_fids if fid in by_fid]
        p["duration"] = round(sum(
            float(s.get("duration_sec") or s.get("duration") or 0) for s in p["sequence"]
        ), 2)
        # [LAB-19] 구판은 여기서 as_is 를 박았고, 호출부(main.py)가 그 뒤에
        # technique_for_mode 로 다시 세팅해 결과적으로 맞았다. 순서가 바뀌면
        # 게이트가 조용히 무력화되는 시한폭탄이라 순서 의존을 끊는다 —
        # 여기서도 같은 상수 사상을 쓴다(호출부와 같은 함수, 같은 답).
        p["technique_id"] = technique_for_mode(p.get("mode"))
    return proposals, {"unresolved_fids": unresolved}


def verify_or_restore(proposals, approval_fids, approval_id, program_id):
    """[2번 검산기] 저장 직전 최후 방어선.

    A·B의 fids와 순서를 승인 스냅샷과 대조한다. 하나라도 어긋나면 **저장하지 않고**
    승인 시퀀스로 되돌린 뒤 raw 로그를 남긴다. 기법이 INV-3을 위반해도 여기서 멈춘다.
    반환: (proposals, violations) — violations가 비어 있으면 통과.
    """
    violations = []
    for p in (proposals or []):
        got = _seq_fids(p.get("sequence"))
        if got == list(approval_fids):
            continue
        got_set, appr_set = set(got), set(approval_fids)
        violations.append({
            "mode": p.get("mode"),
            "proposal_id": p.get("proposal_id"),
            "technique_id": p.get("technique_id"),
            "approval_id": approval_id,
            "expected_n": len(approval_fids),
            "got_n": len(got),
            "added": sorted(got_set - appr_set)[:5],
            "removed": sorted(appr_set - got_set)[:5],
            "order_only": got_set == appr_set,
        })
        # 로그는 ASCII 안전 문자만 쓰고 실패해도 삼킨다. 콘솔 인코딩(cp949 등) 때문에
        # print가 예외를 던지면 상위 try/except가 그걸 잡아 **되돌림이 실행되지 않는다**
        # — 실측: UnicodeEncodeError('cp949') at em-dash. 보호 로직이 로그에 목숨을 걸지 않는다.
        try:
            print(
                f"[PROPOSAL-AXIS][VERIFY][RESTORE] INV violation, restoring approved sequence. "
                f"program={program_id} approval_id={approval_id} mode={p.get('mode')} "
                f"technique={p.get('technique_id')} expected_n={len(approval_fids)} got_n={len(got)} "
                f"order_only={got_set == appr_set} added={sorted(got_set - appr_set)[:3]} "
                f"removed={sorted(appr_set - got_set)[:3]}"
            )
        except Exception:
            pass
    if violations:
        proposals, _ = rebuild_from_approval(proposals, approval_fids)
        for p in (proposals or []):
            after = _seq_fids(p.get("sequence"))
            try:
                print(f"[PROPOSAL-AXIS][VERIFY][RESTORED] mode={p.get('mode')} "
                      f"n={len(after)} matches_approval={after == list(approval_fids)}")
            except Exception:
                pass
    return proposals, violations


def ensure_columns():
    """[1-1] proposals에 story_approval_id / technique_id 보장 (ADD COLUMN만)."""
    con = _connect()
    try:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(proposals)").fetchall()}
        added = []
        if "story_approval_id" not in cols:
            con.execute("ALTER TABLE proposals ADD COLUMN story_approval_id INTEGER")
            added.append("story_approval_id")
        if "technique_id" not in cols:
            con.execute("ALTER TABLE proposals ADD COLUMN technique_id TEXT")
            added.append("technique_id")
        con.commit()
        return added
    finally:
        con.close()
