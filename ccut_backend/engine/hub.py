"""[거점 / HUB] qwen2.5 단독 판단 모듈.

센서/AVR거점/순차루프 구조의 '거점'. 센서(VL=프레임 raw / Whisper=자막 / 룰=motion·audio)가
책상에 올린 '조각(semantic_fragments)별 데이터'를 받아, 판단은 거점(qwen2)이 단독으로 한다.

원칙:
- 모든 편집은 조각화 후. 거점은 항상 semantic_fragments(SF) 단위를 받는다.
- 거점이 판단·명령. 센서는 데이터만(이 모듈은 센서 출력을 그대로 받아 씀).
- AVR: 책상(32k)이 커도 조각을 순차 배치로 처리(=한 사이클 처리량 제어, 노이즈 국소화).
- 신뢰성: format:json 강제(생짜 호출 JSON 깨짐 방지). 조각은 짧은 번호로 지칭(긴 SF id 멍글 방지).

격리: 이 파일은 백엔드 어디서도 호출되지 않는다. CLI로 라이브 DB read-only 테스트만.
  파이프라인 배선은 다음 단계(P3). 지금은 '거점이 실제로 되는가'를 부품으로 증명.

CLI:
  cd D:\\CCUT1.0.4\\ccut_backend
  python -m engine.hub SRC_8BDF7096 물놀이 --en "water play, beach, swimming"
  python -m engine.hub SRC_5327870D 실내 --en "indoor room, bedroom"
"""
import os
import json
import hashlib
import sqlite3
import urllib.request

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

OLLAMA_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434")
HUB_MODEL = os.getenv("CCUT_HUB_MODEL", os.getenv("CCUT_CMD_MODEL", "qwen2.5:7b-instruct"))
_SINGLE_CONFIRM_PROMPT_VERSION = "judge_lean_v1"
_SINGLE_CONFIRM_CACHE = {}
_PLAN_CACHE = {}  # [R2-A 후속] plan_edit 결과 캐시 (A/B 이중 호출 중복 제거, CCUT_SINGLE_CACHE 가역)


# ---------- 센서 데이터 수집 (read-only) ----------

def load_bundles(con, source_id, desc_max=240, tr_max=120):
    """조각(SF) + VL 시각데이터 + 자막을 조각별 번들로. 라이브 DB SELECT만."""
    cur = con.cursor()
    cur.execute(
        """
        SELECT sf.fragment_id, sf.start, sf.end, fi.visual_desc, fi.transcript
        FROM semantic_fragments sf
        LEFT JOIN fragment_index fi ON fi.fragment_id = sf.fragment_id
        WHERE sf.source_id = ?
        ORDER BY sf.start
        """,
        (source_id,),
    )
    bundles = []
    for fid, s, e, desc, tr in cur.fetchall():
        bundles.append({
            "fid": fid,
            "start": round(s or 0.0, 1),
            "end": round(e or 0.0, 1),
            "scene": (desc or "")[:desc_max].replace("\n", " ").strip(),
            "speech": (tr or "")[:tr_max].replace("\n", " ").strip(),
        })
    return bundles


# ---------- 거점 호출 (format:json 강제) ----------

def _ollama_json(prompt: str, timeout: int = 60) -> dict:
    body = json.dumps({
        "model": HUB_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 1024},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return json.loads(data.get("response", "{}") or "{}")


def _build_prompt(theme_ko, theme_en, chunk):
    """조각을 번호(1..N)로 지칭. 거점이 테마 판정 + 불확실 시 재분석 명령."""
    theme = theme_ko + (f" ({theme_en})" if theme_en else "")
    lines = []
    for i, b in enumerate(chunk, 1):
        sc = b["scene"] or "(시각데이터 없음)"
        sp = f" / 말소리: {b['speech']}" if b["speech"] else ""
        lines.append(f'{i}. [{b["start"]}~{b["end"]}s] 장면: {sc}{sp}')
    frags = "\n".join(lines)
    return (
        "너는 영상 편집 거점이다. 센서가 올린 조각별 장면 태그를 보고 직접 판단한다.\n"
        f"판정 테마: '{theme}'.\n"
        "각 조각이 이 테마에 해당하는지 판단하라.\n"
        "엄격 규칙: 장면 태그에 분명한 근거가 있을 때만 is_theme=true. 근거 없으면 false(추측 금지).\n"
        "예: '실내' 판정 시 태그에 indoor/room/실내 등 명시 단서가 있어야 함. "
        "school building·concrete ground·schoolyard 등 야외 구조물은 실내가 아니다.\n"
        "장면이 모호하면 recheck=true. reason(근거)은 반드시 한국어로 짧게.\n"
        "JSON만 출력. 형식:\n"
        '{"items":[{"n":번호,"scene":"한단어 장면라벨","is_theme":true/false,'
        '"confidence":0.0~1.0,"recheck":true/false,"reason":"짧은 근거"}]}\n'
        "조각:\n" + frags + "\n"
    )


def judge_theme(source_id, theme_ko, theme_en=None, batch=8, verbose=True):
    """거점이 한 source의 조각들을 테마로 순차 판정. 결과 리스트 반환."""
    con = sqlite3.connect(DB_PATH)
    bundles = load_bundles(con, source_id)
    con.close()
    if not bundles:
        print(f"[HUB] {source_id}: 조각 없음")
        return []

    results = []
    for i in range(0, len(bundles), batch):
        chunk = bundles[i:i + batch]
        prompt = _build_prompt(theme_ko, theme_en, chunk)
        try:
            out = _ollama_json(prompt)
            items = out.get("items") or []
        except Exception as e:
            print(f"[HUB] batch {i // batch} 호출 실패 ({e})")
            items = []
        by_n = {int(it["n"]): it for it in items if isinstance(it, dict) and "n" in it}
        for j, b in enumerate(chunk, 1):
            it = by_n.get(j, {})
            results.append({
                "fid": b["fid"],
                "time": f'{b["start"]}~{b["end"]}s',
                "scene": it.get("scene"),
                "is_theme": bool(it.get("is_theme")),
                "confidence": it.get("confidence"),
                "recheck": bool(it.get("recheck")),
                "reason": it.get("reason"),
            })
        if verbose:
            print(f"[HUB] 배치 {i // batch + 1}: {len(chunk)}조각 판정 완료")
    return results


# ---------- [P3a] 편집계획: 분해(추출 → judge_theme → 결정론 count) ----------

def _clean_s(v):
    if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none"):
        return v.strip()
    return None


import re

# 알려진 핵심 어휘 = 결정론(손발). 새 표현만 LLM(머리) 폴백.
_THEME_VOCAB = [
    "실내", "실외", "야외", "운동장", "물놀이", "바다", "해변", "수영", "계곡", "강",
    "풍경", "음식", "요리", "사람", "인물", "아이", "어린이", "가족", "밤", "야경", "거리",
    "호텔", "침실", "방", "체육관", "공원", "놀이터",
]
_NUM_KO = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6,
           "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_EXCLUDE_MARK = ("빼", "제외", "말고", "없이")


def _det_count(t):
    """'5개','다섯 개' → 정수. '명'(사람 수)은 제외."""
    m = re.search(r"(\d+)\s*개", t)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 40 else None
    for k, v in _NUM_KO.items():
        if re.search(k + r"\s*개", t):
            return v
    return None


def _deterministic_intent(t):
    """알려진 어휘에 한해 {keep,exclude,count} 확정. 못 잡으면 theme_found=False."""
    count = _det_count(t)
    is_excl = any(k in t for k in _EXCLUDE_MARK)
    theme = next((kw for kw in _THEME_VOCAB if kw in t), None)
    keep = exclude = None
    if theme:
        if is_excl:
            exclude = theme
        else:
            keep = theme
    return {"keep": keep, "exclude": exclude, "count": count,
            "theme_found": theme is not None}


_THEME_ALIASES = {
    "실내": ("실내", "indoor", "interior", "inside", "room", "bedroom", "hallway", "corridor", "closet", "bed", "pillow", "wardrobe", "couch", "sofa", "복도", "走廊", "室内", "방", "침실", "체육관", "subway", "train", "bus", "carriage", "지하철", "기차", "버스"),
    "실외": ("실외", "야외", "외부", "밖", "outdoor", "outside", "exterior", "schoolyard", "playground", "street", "road", "park"),
    "야외": ("실외", "야외", "외부", "밖", "outdoor", "outside", "exterior", "schoolyard", "playground", "street", "road", "park"),
    "운동장": ("운동장", "schoolyard", "playground", "field", "ground"),
    "물놀이": ("물놀이", "water play", "swimming", "beach", "sea", "ocean", "pool", "바다", "해변", "수영"),
    "바다": ("바다", "sea", "ocean", "beach", "shore", "해변"),
    "해변": ("해변", "beach", "shore", "sand", "바다"),
    "수영": ("수영", "swimming", "pool", "water"),
    "계곡": ("계곡", "valley", "stream", "creek"),
    "강": ("강", "river"),
    "풍경": ("풍경", "landscape", "scenery", "view", "background"),
    "음식": ("음식", "food", "meal", "dish"),
    "요리": ("요리", "cooking", "cook", "kitchen"),
    "사람": ("사람", "인물", "person", "people", "child", "kid", "face", "man", "woman", "boy", "girl", "adult", "family", "가족"),
    "인물": ("사람", "인물", "person", "people", "face", "man", "woman", "portrait"),
    "아이": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl", "toddler", "baby"),
    "어린이": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl"),
    "아이들": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl", "toddler", "baby"),
    "가족": ("가족", "family", "사람", "인물", "person", "people", "parent", "mother", "father", "child"),
    "밤": ("밤", "night", "dark"),
    "야경": ("야경", "night view", "nightscape", "night"),
    "거리": ("거리", "street", "road"),
    "호텔": ("호텔", "hotel"),
    "침실": ("침실", "bedroom"),
    "방": ("방", "room"),
    "체육관": ("체육관", "gym", "gymnasium", "indoor gym"),
    "공원": ("공원", "park"),
    "놀이터": ("놀이터", "playground"),
}

_INDOOR_POSITIVE = _THEME_ALIASES["실내"]
_INDOOR_NEGATIVE = (
    "outdoor", "outside", "exterior", "schoolyard", "school yard", "playground",
    "school building", "building exterior", "concrete ground", "field", "park",
    "street", "road", "beach", "sea", "ocean", "shore", "water play", "swimming",
    "야외", "실외", "외부", "운동장", "놀이터", "공원", "거리", "바다", "해변", "물놀이", "수영",
)


def _scene_text(item):
    scene = item.get("scene")
    if scene:
        return str(scene)
    for key in ("visual_desc", "description", "caption", "summary"):
        if item.get(key):
            return str(item.get(key))
    semantic = item.get("semantic") if isinstance(item.get("semantic"), dict) else {}
    intelligence = item.get("intelligence") if isinstance(item.get("intelligence"), dict) else {}
    parts = [
        semantic.get("topic"),
        semantic.get("scene"),
        semantic.get("description"),
        intelligence.get("visual_desc"),
        intelligence.get("caption"),
    ]
    return " ".join(str(p) for p in parts if p)


def _item_fid(item):
    return item.get("fid") or item.get("fragment_id") or item.get("id")


def _item_time(item):
    if item.get("time"):
        return item.get("time")
    start = item.get("start", item.get("start_time", ""))
    end = item.get("end", item.get("end_time", ""))
    return f"{start}~{end}s" if start != "" or end != "" else ""


def _aliases_for_theme(theme):
    aliases = list(_THEME_ALIASES.get(theme, (theme,)))
    if theme and theme not in aliases:
        aliases.append(theme)
    return tuple(str(a).lower() for a in aliases if a)


def _scene_has_any(scene, aliases):
    text = (scene or "").lower()
    return any(a and a in text for a in aliases)


def _scene_alias_hits(scene, aliases):
    text = (scene or "").lower()
    return [a for a in aliases if a and a.lower() in text]


def _self_check_item(theme, is_exclude, item):
    scene = _scene_text(item)
    text = scene.lower()
    aliases = _aliases_for_theme(theme)
    has_theme = _scene_has_any(scene, aliases)

    if theme == "실내":
        has_indoor = _scene_has_any(scene, _INDOOR_POSITIVE)
        has_outdoor = any(sig in text for sig in _INDOOR_NEGATIVE)
        if is_exclude:
            if has_indoor:
                return "MISMATCH", "excluded indoor signal present"
            return "PASS", None
        if has_outdoor and not has_indoor:
            return "MISMATCH", "strong outdoor signal in indoor-only result"
        if has_indoor:
            return "PASS", None
        return "AMBIGUOUS", "no explicit indoor signal"

    if is_exclude:
        if has_theme:
            return "MISMATCH", f"excluded theme '{theme}' appears in scene"
        return "PASS", None

    if has_theme:
        return "PASS", None
    return "AMBIGUOUS", f"theme '{theme}' not explicit in scene"


def self_check_selection(theme, is_exclude, selected, judged=None, judge_mode=None):
    """Pure post-check: no model calls, no selection changes."""
    selected = selected or []
    judged = judged or []
    if judge_mode is None and theme and not is_exclude and not judged:
        judge_mode = "batch+single"
    mismatches, ambiguous, omitted = [], [], []

    for item in selected:
        verdict, reason = _self_check_item(theme, is_exclude, item)
        if verdict == "MISMATCH":
            mismatches.append({
                "fid": _item_fid(item), "time": _item_time(item),
                "scene": _scene_text(item), "reason": reason
            })
        elif verdict == "AMBIGUOUS":
            ambiguous.append({
                "fid": _item_fid(item), "time": _item_time(item),
                "scene": _scene_text(item), "reason": reason
            })

    selected_ids = {_item_fid(item) for item in selected}
    if theme and not is_exclude:
        for item in judged:
            if _item_fid(item) in selected_ids:
                continue
            verdict, _reason = _self_check_item(theme, False, item)
            if verdict == "PASS" and not bool(item.get("is_theme")):
                omitted.append({
                    "fid": _item_fid(item), "time": _item_time(item),
                    "scene": _scene_text(item), "reason": "judge omitted explicit theme candidate"
                })

    total = len(selected)
    mismatch_count = len(mismatches)
    ambiguous_count = len(ambiguous)
    omitted_count = len(omitted)
    ambiguous_ratio = (ambiguous_count / total) if total else 0.0
    if total == 0:
        status = "FAIL"
    elif mismatch_count >= max(2, int(total * 0.4 + 0.999)):
        status = "FAIL"
    elif mismatch_count or omitted_count:
        status = "WARN"
    elif ambiguous_count and ambiguous_ratio > 0.1:
        status = "WARN"
    else:
        status = "PASS"

    if total == 0:
        message = "요청 조건에 맞는 조각을 찾지 못했습니다."
    elif status == "PASS":
        message = "요청 조건과 선택 조각이 대체로 일치합니다."
    elif status == "FAIL":
        message = "조건을 만족하지 못했습니다. 요청과 다른 컷이 다수 포함됐습니다."
    elif theme == "실내":
        message = "실내로 확정 가능한 조각이 부족해서 일부 애매한 컷이 포함됐거나 누락 후보가 있습니다."
    else:
        message = "요청 조건과 일부 어긋나거나 애매한 컷이 포함됐습니다."

    if judge_mode == "batch":
        status = "WARN"
        message = "batch-only judge result used as final selection"

    result = {
        "status": status,
        "theme": theme,
        "mode": "exclude" if is_exclude else "keep",
        "judge_mode": judge_mode,
        "mismatch_count": mismatch_count,
        "ambiguous_count": ambiguous_count,
        "omitted_count": omitted_count,
        "total_count": total,
        "judged_count": len(judged),
        "message": message,
        "mismatches": mismatches[:8],
        "ambiguous": ambiguous[:8],
        "omitted": omitted[:8],
    }
    return result


def extract_intent(instruction):
    """[추출] 명령 → {keep, exclude, count}. 결정론(알려진 어휘) 우선, 새 표현만 LLM 폴백."""
    det = _deterministic_intent(instruction or "")
    if det["theme_found"]:
        print(f"[HUB-EXTRACT] det keep={det['keep']} exclude={det['exclude']} count={det['count']}")
        return {"keep": det["keep"], "exclude": det["exclude"], "count": det["count"]}
    # 어휘 못 잡음 → LLM 폴백(새 표현). count는 결정론값 우선.
    prompt = (
        "사용자 영상편집 명령에서 아래 셋만 뽑아 JSON으로 출력한다. 조각 판단/선택은 하지 마라.\n"
        f"명령: {instruction}\n"
        "키: keep(남길 내용조건 명사구, 없으면 null), "
        "exclude(빼야 할 내용조건, 없으면 null), count(조각 개수 정수, 없으면 null)\n"
        "예시:\n"
        '  "실내만" -> {"keep":"실내","exclude":null,"count":null}\n'
        '  "실내 빼줘" -> {"keep":null,"exclude":"실내","count":null}\n'
        '  "한명만 있는 조각만" -> {"keep":"한 명만 있는 장면","exclude":null,"count":null}\n'
        '  "운동장만" -> {"keep":"운동장","exclude":null,"count":null}\n'
        '  "조각 5개로" -> {"keep":null,"exclude":null,"count":5}\n'
        '  "물놀이 5개" -> {"keep":"물놀이","exclude":null,"count":5}\n'
        '  "더 빠르게" -> {"keep":null,"exclude":null,"count":null}\n'
        "JSON만:"
    )
    try:
        out = _ollama_json(prompt)
    except Exception as e:
        print(f"[HUB-EXTRACT] 실패 ({e})")
        return {"keep": None, "exclude": None, "count": None}
    c = out.get("count")
    if isinstance(c, bool):
        c = None
    llm_count = int(c) if isinstance(c, (int, float)) and 1 <= int(c) <= 40 else None
    # 개수는 결정론('N개')이 LLM보다 신뢰도 높음 → 결정론 우선
    final_count = det["count"] if det["count"] is not None else llm_count
    print(f"[HUB-EXTRACT] llm keep={_clean_s(out.get('keep'))} "
          f"exclude={_clean_s(out.get('exclude'))} count={final_count}")
    return {"keep": _clean_s(out.get("keep")), "exclude": _clean_s(out.get("exclude")),
            "count": final_count}


GOLDEN_CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_cases.json")


def _load_golden_cases():
    """확정 골든 케이스 로드({theme, tags, gold}). 파일 없거나 깨지면 빈 리스트(프롬프트는 기본 규칙만)."""
    try:
        with open(GOLDEN_CASES_PATH, encoding="utf-8") as f:
            cases = json.load(f).get("cases", [])
        return [c for c in cases if isinstance(c, dict) and c.get("tags") and c.get("theme")]
    except Exception:
        return []


def _golden_fewshot_block(theme, max_examples=6):
    """현재 테마의 골든 케이스에서 대표 예시 블록 생성(true/false 균형, 최대 6개).
    해당 테마 골든이 없으면 빈 문자열 — 다른 테마 라벨을 섞어 오도하지 않는다."""
    cases = [c for c in _load_golden_cases() if c.get("theme") == theme]
    if not cases:
        return ""
    pos = [c for c in cases if c.get("gold")][:max_examples // 2]
    neg = [c for c in cases if not c.get("gold")][:max_examples - len(pos)]
    picked = pos + neg
    if not picked:
        return ""
    lines = [f'- "{c["tags"]}" -> t={"true" if c.get("gold") else "false"}' for c in picked]
    return "확정 예시:\n" + "\n".join(lines) + "\n"


def _build_judge_lean(theme, chunk):
    """[속도] 판정 전용 lean 프롬프트 — 출력은 {n,t}만(why/recheck 제거 = 생성 토큰↓).
    경계 판단은 산문 규칙 대신 골든 케이스 few-shot 예시(golden_cases.json)로 전달."""
    lines = [f'{i}. {b["scene"] or "(없음)"}' for i, b in enumerate(chunk, 1)]
    return (
        f"각 조각이 테마 '{theme}'에 해당하면 t=true, 아니면 t=false. "
        "장면 태그에 분명한 근거가 없으면 false(추측 금지).\n"
        + _golden_fewshot_block(theme)
        + '오직 JSON: {"items":[{"n":번호,"t":true}]}\n'
        "조각:\n" + "\n".join(lines)
    )


def _requery_indoor_signal(scene, aliases, fid=None):
    prompt = (
        f"센서 데이터: {scene}\n"
        f"센서가 실내 관련 사물 ({', '.join(aliases)})을 감지했다. "
        "이 장면은 실내인가?\n"
        "반드시 한국어로만 답하라.\n"
        '{"indoor": true/false, "reason": "..."}'
    )
    import time as _t
    _t0 = _t.time()
    out = _ollama_json(prompt)
    elapsed = _t.time() - _t0
    result = bool(out.get("indoor"))
    print(
        f"[P3b REQUERY] frag={fid or 'UNKNOWN'} alias={','.join(aliases)} "
        f"judge=false -> requery={str(result).lower()} time={elapsed:.2f}s"
    )
    return result


def _requery_theme_signal(theme, scene, aliases, fid=None):
    """[PERSON-PALETTE] 실내 재질의 패턴의 일반화: 센서 alias가 있는데 judge=false인
    조각을 테마 문구로 허브에 재질의. 판단 주체는 여전히 hub 1곳."""
    prompt = (
        f"센서 데이터: {scene}\n"
        f"센서가 '{theme}' 관련 단서 ({', '.join(aliases)})를 감지했다. "
        f"이 장면은 '{theme}'에 해당하는가?\n"
        "반드시 한국어로만 답하라.\n"
        '{"match": true/false, "reason": "..."}'
    )
    import time as _t
    _t0 = _t.time()
    out = _ollama_json(prompt)
    elapsed = _t.time() - _t0
    result = bool(out.get("match"))
    print(
        f"[P3b REQUERY] frag={fid or 'UNKNOWN'} theme={theme} alias={','.join(aliases)} "
        f"judge=false -> requery={str(result).lower()} time={elapsed:.2f}s"
    )
    return result


# [PERSON-PALETTE] 인물 계열 테마 — CCUT_PERSON_REQUERY=1일 때만 재질의 승격 (기본 OFF)
_PERSON_THEMES = ("사람", "인물", "아이", "어린이")


def _golden_exact_verdict(theme, scene):
    """[R3] 확정 골든과 센서 텍스트가 정확히 일치하면 그 gold를 결정론으로 반환.
    (SF_566DF6: 동일 장면이 퓨샷에 t=true로 있어도 모델이 false → 확정 라벨은 재판단 금지)
    일치 기준은 정규화 해시(_scene_sensor_hash) — 퍼지 매칭 없음."""
    h = _scene_sensor_hash(scene)
    for c in _load_golden_cases():
        if c.get("theme") == theme and _scene_sensor_hash(c.get("tags")) == h:
            return bool(c.get("gold"))
    return None


def _normalize_judge_theme_decision(theme, scene, raw_value, fid=None):
    """Post-process hub judge output with deterministic scene boundary rules."""
    golden = _golden_exact_verdict(theme, scene)
    if golden is not None:
        if golden != bool(raw_value):
            print(f"[P3b GOLDEN-MATCH] frag={fid or 'UNKNOWN'} theme={theme} "
                  f"judge={str(bool(raw_value)).lower()} -> golden={str(golden).lower()} (확정 라벨 우선)")
        return golden
    decision = bool(raw_value)
    if theme == "실내":
        if decision:
            return True
        aliases = _scene_alias_hits(scene, _INDOOR_POSITIVE)
        if aliases:
            try:
                return _requery_indoor_signal(scene, aliases, fid=fid)
            except Exception as e:
                print(f"[P3b REQUERY][WARN] frag={fid or 'UNKNOWN'} failed ({e}) -> keep judge=false")
                return False
        return False
    if theme in _PERSON_THEMES and os.getenv("CCUT_PERSON_REQUERY") in ("1", "true", "True"):
        if decision:
            return True
        aliases = _scene_alias_hits(scene, _aliases_for_theme(theme))
        if aliases:
            try:
                return _requery_theme_signal(theme, scene, aliases, fid=fid)
            except Exception as e:
                print(f"[P3b REQUERY][WARN] frag={fid or 'UNKNOWN'} failed ({e}) -> keep judge=false")
                return False
        return False
    return decision


def _judge_one_chunk(theme_ko, chunk, chunk_no):
    """청크 1개 판단 → 결과 리스트. 병렬/순차 공용 (내용·프롬프트 동일 = 편향 중립)."""
    prompt = _build_judge_lean(theme_ko, chunk)
    try:
        out = _ollama_json(prompt)
        items = out.get("items") or []
    except Exception as e:
        print(f"[HUB-JUDGE] batch {chunk_no} 실패 ({e})")
        items = []
    by_n = {int(it["n"]): it for it in items if isinstance(it, dict) and "n" in it}
    results = []
    for j, b in enumerate(chunk, 1):
        it = by_n.get(j, {})
        raw_t = bool(it.get("t"))
        normalized_t = _normalize_judge_theme_decision(theme_ko, b["scene"], raw_t, fid=b["fid"])
        results.append({
            "fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
            "scene": b["scene"],
            "is_theme": normalized_t,
            "batch_raw_is_theme": raw_t,
            "requery_applied": bool(normalized_t and not raw_t),
            "confidence": None, "recheck": False, "reason": None,
        })
    return results


def _judge_batch(theme_ko, bundles, theme_en=None, batch=8):
    """[속도] 조각 묶음을 배치 판단. lean 출력({n,t})로 생성 토큰 최소화.
    출력키는 plan_edit이 쓰는 fid/time/scene/is_theme 유지.

    [JUDGE-PAR] CCUT_JUDGE_PARALLEL=N (기본 1=기존 순차 무변): 청크를 N개 동시 요청.
    서버가 OLLAMA_NUM_PARALLEL 슬롯을 열어야 실효 (기본 auto 1|4).
    청크 구성·프롬프트는 순차와 동일 — 위치편향 구조 불변, 결과는 원래 순서로 병합."""
    chunks = [bundles[i:i + batch] for i in range(0, len(bundles), batch)]
    try:
        workers = max(1, min(int(os.getenv("CCUT_JUDGE_PARALLEL", "1")), 8))
    except Exception:
        workers = 1
    if workers <= 1 or len(chunks) <= 1:
        results = []
        for no, chunk in enumerate(chunks):
            results.extend(_judge_one_chunk(theme_ko, chunk, no))
        return results
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        chunk_results = list(ex.map(
            lambda t: _judge_one_chunk(theme_ko, t[1], t[0]), enumerate(chunks)))
    results = []
    for r in chunk_results:
        results.extend(r)
    return results


def _judge_single_confirm(theme_ko, bundle):
    import time as _t
    _t0 = _t.time()
    try:
        out = _ollama_json(_build_judge_lean(theme_ko, [bundle]))
        items = out.get("items") or []
        item = next((it for it in items if isinstance(it, dict) and int(it.get("n", 0) or 0) == 1), None)
        if item is None:
            raise ValueError("missing single judge item")
        result = _normalize_judge_theme_decision(theme_ko, bundle.get("scene"), item.get("t"), fid=bundle.get("fid"))
        return bool(result), _t.time() - _t0, None
    except Exception as e:
        return False, _t.time() - _t0, e


def _single_cache_enabled():
    return os.getenv("CCUT_SINGLE_CACHE") in ("1", "true", "True")


def _scene_sensor_hash(scene):
    normalized = " ".join(str(scene or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _golden_state_sig():
    """[AUDIT-⑽] golden_cases.json 변경 시 캐시 무효화용 서명 (mtime+size).
    골든 추가/수정이 재시작 없이도 판정 캐시에 반영되게 한다."""
    try:
        st = os.stat(GOLDEN_CASES_PATH)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except Exception:
        return "no-golden"


def _single_cache_key(theme_ko, bundle):
    return (
        bundle.get("fid"),
        theme_ko,
        _scene_sensor_hash(bundle.get("scene")),
        HUB_MODEL,
        _SINGLE_CONFIRM_PROMPT_VERSION,
        _golden_state_sig(),
    )


def _confirm_keep_candidates_single(theme_ko, judged, bundles):
    bundle_by_fid = {b.get("fid"): b for b in bundles}
    batch_keep = 0
    confirmed = 0
    single_calls = 0
    cache_hits = 0
    cache_misses = 0
    total_time = 0.0
    use_cache = _single_cache_enabled()

    for item in judged:
        batch_t = bool(item.get("is_theme"))
        item["batch_is_theme"] = batch_t
        item["judge_mode"] = "batch"
        if not batch_t:
            continue

        batch_keep += 1
        if item.get("requery_applied"):
            confirmed += 1
            item["single_is_theme"] = bool(item.get("is_theme"))
            item["single_time_sec"] = 0.0
            item["judge_mode"] = "batch+requery"
            print(
                f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
                "batch=true -> single=t skipped=requery"
            )
            continue

        bundle = bundle_by_fid.get(item.get("fid")) or {
            "fid": item.get("fid"),
            "scene": item.get("scene") or "",
            "start": 0,
            "end": 0,
        }
        cache_key = _single_cache_key(theme_ko, bundle)
        if use_cache and cache_key in _SINGLE_CONFIRM_CACHE:
            cached = _SINGLE_CONFIRM_CACHE[cache_key]
            single_t = bool(cached.get("is_theme"))
            cache_hits += 1
            item["single_is_theme"] = single_t
            item["single_time_sec"] = 0.0
            item["judge_mode"] = "batch+single"
            item["is_theme"] = single_t
            if single_t:
                confirmed += 1
            print(f"[P3b SINGLE-CACHE] frag={item.get('fid')} hit")
            print(
                f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
                f"batch=true -> single={'t' if single_t else 'f'} cached"
            )
            continue

        if use_cache:
            cache_misses += 1
            print(f"[P3b SINGLE-CACHE] frag={item.get('fid')} miss")

        single_t, elapsed, error = _judge_single_confirm(theme_ko, bundle)
        single_calls += 1
        total_time += elapsed
        item["single_is_theme"] = bool(single_t)
        item["single_time_sec"] = round(elapsed, 3)
        item["judge_mode"] = "batch+single"
        item["is_theme"] = bool(single_t)
        if single_t:
            confirmed += 1
        if error is not None:
            item["single_error"] = str(error)
            print(
                f"[P3b SINGLE-CONFIRM][WARN] frag={item.get('fid')} "
                f"batch=true -> single=f failed ({error}) time={elapsed:.2f}s"
            )
        elif use_cache:
            _SINGLE_CONFIRM_CACHE[cache_key] = {"is_theme": bool(single_t)}
        print(
            f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
            f"batch=true -> single={'t' if single_t else 'f'} time={elapsed:.2f}s"
        )

    avg = (total_time / single_calls) if single_calls else 0.0
    if use_cache:
        print(
            f"[P3b JUDGE] mode=batch+single batch_keep={batch_keep} "
            f"confirmed={confirmed} single_calls={single_calls} "
            f"cache_hits={cache_hits} cache_misses={cache_misses} "
            f"single_time_total={total_time:.2f}s "
            f"single_time_avg={avg:.2f}s"
        )
    else:
        print(
            f"[P3b JUDGE] mode=batch+single batch_keep={batch_keep} "
            f"confirmed={confirmed} single_calls={single_calls} "
            f"single_time_total={total_time:.2f}s "
            f"single_time_avg={avg:.2f}s"
        )
    result = {
        "batch_keep": batch_keep,
        "confirmed": confirmed,
        "single_calls": single_calls,
        "single_time_total": total_time,
    }
    if use_cache:
        result["cache_hits"] = cache_hits
        result["cache_misses"] = cache_misses
    return result


def plan_edit(source_ids, instruction_text, batch=8, verbose=True):
    """[P3a] 명령+조각풀 → 편집계획. 분해 파이프라인:
      1) extract_intent: 명령 → {keep,exclude,count} (분류만)
      2) judge_theme(테마): 클립별 keep/exclude (검증된 P1 판단)
      3) count: 모델이 아니라 결정론으로 그대로 전달(하류 P3b가 적용)
    내용조건 없으면 판단 0, 전체 유지.
    반환: {keep:[{fid,time,scene,why}], count:int|None, intent, reason}
    """
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    intent = extract_intent(instruction_text)
    if verbose:
        print(f"[QWEN_ROUTE] route=hub_plan model={HUB_MODEL}")
        print(f"[HUB-PLAN] intent={intent}")

    theme = intent["keep"] or intent["exclude"]
    is_exclude = intent["exclude"] is not None and intent["keep"] is None

    # 조각풀은 두 분기 모두 필요 → 먼저 적재 (plan 캐시 키의 pool hash에도 사용)
    con = sqlite3.connect(DB_PATH)
    bundles = []
    for sid in source_ids:
        bundles.extend(load_bundles(con, sid))
    con.close()

    # 내용조건 없음 → 판단 생략, 전체 유지 (count만 결정론)
    if not theme:
        keep = [{"fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
                 "scene": b["scene"], "why": "내용조건 없음(전체)"} for b in bundles]
        return {"keep": keep, "count": intent["count"], "intent": intent,
                "reason": f"no content filter, keep all {len(keep)}"}

    # [R2-A 후속] 같은 요청 안에서 A안·B안이 plan_edit를 각각 호출 → batch judge 2배.
    # 판(plan) 수준 인메모리 캐시: 명령+소스+조각풀(sensor)+모델이 같으면 재계산 금지.
    # 단일판정 캐시와 동일하게 CCUT_SINGLE_CACHE로 가역, 실패/예외 결과는 저장하지 않음.
    _plan_cache_on = os.getenv("CCUT_SINGLE_CACHE") in ("1", "true", "True")
    _plan_key = None
    if _plan_cache_on:
        _pool_sig = hashlib.sha256(
            "|".join(sorted(f'{b["fid"]}:{_scene_sensor_hash(b.get("scene"))}' for b in bundles)).encode("utf-8")
        ).hexdigest()[:16]
        _plan_key = (tuple(source_ids), theme, is_exclude, intent.get("count"),
                     _pool_sig, HUB_MODEL, _golden_state_sig())
        _hit = _PLAN_CACHE.get(_plan_key)
        if _hit is not None:
            if verbose:
                print(f"[P3b PLAN-CACHE] hit keep={len(_hit.get('keep') or [])} ({_hit.get('reason')})")
            import copy as _copy
            return _copy.deepcopy(_hit)

    # 내용조건 있음 → 전체 조각을 '큰 배치'로 한 번에 판단(속도: 소스별 루프 제거)
    import time as _t
    _jbatch = int(os.getenv("CCUT_HUB_JUDGE_BATCH", "8"))
    _t0 = _t.time()
    judged = _judge_batch(theme, bundles, batch=_jbatch)
    if verbose:
        print(f"[HUB-PLAN] judged {len(judged)}frags batch={_jbatch} "
              f"calls={(len(judged) + _jbatch - 1) // _jbatch} time={_t.time() - _t0:.1f}s")
    if is_exclude:
        kept = [j for j in judged if not j["is_theme"]]
        tag = f"exclude '{theme}'"
    else:
        _confirm_keep_candidates_single(theme, judged, bundles)
        kept = [j for j in judged if j["is_theme"]]
        tag = f"keep '{theme}'"
    keep = [{"fid": j["fid"], "time": j["time"], "scene": j["scene"],
             "why": j.get("reason")} for j in kept]
    self_check = self_check_selection(
        theme, is_exclude, keep, judged=judged,
        judge_mode="batch+single" if not is_exclude else None,
    )
    _plan = {"keep": keep, "count": intent["count"], "intent": intent,
             "reason": f"{tag}: {len(keep)}/{len(judged)}",
             "self_check": self_check}
    if _plan_cache_on and _plan_key is not None:
        import copy as _copy
        if len(_PLAN_CACHE) >= 32:  # [AUDIT-⑽] 무제한 증식 방지 (FIFO)
            _PLAN_CACHE.pop(next(iter(_PLAN_CACHE)))
        _PLAN_CACHE[_plan_key] = _copy.deepcopy(_plan)
    return _plan


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode")

    pj = sub.add_parser("judge")  # P1: 테마 판정
    pj.add_argument("source_id")
    pj.add_argument("theme")
    pj.add_argument("--en", default=None)
    pj.add_argument("--batch", type=int, default=8)

    pp = sub.add_parser("plan")   # P3a: 편집계획
    pp.add_argument("source_ids", nargs="+")
    pp.add_argument("--cmd", required=True)
    pp.add_argument("--batch", type=int, default=16)

    args = ap.parse_args()

    if args.mode == "plan":
        print(f"[HUB-PLAN] model={HUB_MODEL} sources={len(args.source_ids)} cmd={args.cmd!r}")
        r = plan_edit(args.source_ids, args.cmd, batch=args.batch)
        print(f"\ncount={r['count']}  keep={len(r['keep'])}  ({r['reason']})")
        print(f"{'time':<16} {'scene':<46} why")
        print("-" * 100)
        for k in r["keep"]:
            print(f"{k['time']:<16} {str(k['scene'])[:46]:<46} {str(k['why'])[:30]}")
    else:
        # judge (P1 기존)
        print(f"[HUB] model={HUB_MODEL} source={args.source_id} theme={args.theme!r} "
              f"en={args.en!r} batch={args.batch}")
        res = judge_theme(args.source_id, args.theme, args.en, batch=args.batch)
        print(f"\n{'n':>2} {'is':>3} {'conf':>5} {'rechk':>5}  {'time':<14} {'label':<16} 근거")
        print("-" * 90)
        theme_n = 0
        recheck_n = 0
        for i, r in enumerate(res, 1):
            theme_n += 1 if r["is_theme"] else 0
            recheck_n += 1 if r["recheck"] else 0
            conf = r["confidence"]
            conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "  - "
            print(f"{i:>2} {'Y' if r['is_theme'] else '.':>3} {conf_s:>5} "
                  f"{'Y' if r['recheck'] else '.':>5}  {r['time']:<14} "
                  f"{str(r['scene'])[:16]:<16} {str(r['reason'])[:40]}")
        print("-" * 90)
        print(f"총 {len(res)}조각 | 테마판정 {theme_n} | 재분석요청 {recheck_n}")
