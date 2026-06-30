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
import sqlite3
import urllib.request

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

OLLAMA_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434")
HUB_MODEL = os.getenv("CCUT_HUB_MODEL", os.getenv("CCUT_CMD_MODEL", "qwen2.5:7b-instruct"))


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
    "풍경", "음식", "요리", "사람", "인물", "아이", "어린이", "밤", "야경", "거리",
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


def _build_judge_lean(theme, chunk):
    """[속도] 판정 전용 lean 프롬프트 — 출력은 {n,t}만(why/recheck 제거 = 생성 토큰↓)."""
    lines = [f'{i}. {b["scene"] or "(없음)"}' for i, b in enumerate(chunk, 1)]
    return (
        f"각 조각이 테마 '{theme}'에 해당하면 t=true, 아니면 t=false. "
        "장면 태그에 분명한 근거가 없으면 false(추측 금지). "
        "실내 체육관(indoor gymnasium)은 실내; school·concrete·schoolyard 등 야외는 실내 아님.\n"
        '오직 JSON: {"items":[{"n":번호,"t":true}]}\n'
        "조각:\n" + "\n".join(lines)
    )


def _judge_batch(theme_ko, bundles, theme_en=None, batch=8):
    """[속도] 조각 묶음을 배치 판단. lean 출력({n,t})로 생성 토큰 최소화.
    출력키는 plan_edit이 쓰는 fid/time/scene/is_theme 유지."""
    results = []
    for i in range(0, len(bundles), batch):
        chunk = bundles[i:i + batch]
        prompt = _build_judge_lean(theme_ko, chunk)
        try:
            out = _ollama_json(prompt)
            items = out.get("items") or []
        except Exception as e:
            print(f"[HUB-JUDGE] batch {i // batch} 실패 ({e})")
            items = []
        by_n = {int(it["n"]): it for it in items if isinstance(it, dict) and "n" in it}
        for j, b in enumerate(chunk, 1):
            it = by_n.get(j, {})
            results.append({
                "fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
                "scene": b["scene"],
                "is_theme": bool(it.get("t")),
                "confidence": None, "recheck": False, "reason": None,
            })
    return results


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
        print(f"[HUB-PLAN] intent={intent}")

    theme = intent["keep"] or intent["exclude"]
    is_exclude = intent["exclude"] is not None and intent["keep"] is None

    # 내용조건 없음 → 판단 생략, 전체 유지 (count만 결정론)
    if not theme:
        con = sqlite3.connect(DB_PATH)
        bundles = []
        for sid in source_ids:
            bundles.extend(load_bundles(con, sid))
        con.close()
        keep = [{"fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
                 "scene": b["scene"], "why": "내용조건 없음(전체)"} for b in bundles]
        return {"keep": keep, "count": intent["count"], "intent": intent,
                "reason": f"no content filter, keep all {len(keep)}"}

    # 내용조건 있음 → 전체 조각을 '큰 배치'로 한 번에 판단(속도: 소스별 루프 제거)
    con = sqlite3.connect(DB_PATH)
    bundles = []
    for sid in source_ids:
        bundles.extend(load_bundles(con, sid))
    con.close()
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
        kept = [j for j in judged if j["is_theme"]]
        tag = f"keep '{theme}'"
    keep = [{"fid": j["fid"], "time": j["time"], "scene": j["scene"],
             "why": j.get("reason")} for j in kept]
    return {"keep": keep, "count": intent["count"], "intent": intent,
            "reason": f"{tag}: {len(keep)}/{len(judged)}"}


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
