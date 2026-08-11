"""[GEMMA4 2026-08-11] 네이티브 도구 호출 경로 — C축 `tools` 의 알맹이.

## 왜 만들었나

CCUT 은 지금 도구를 고르는 일을 ★손으로 만든 층★으로 한다:
engine_desk._ask_tool 이 도구 목록을 프롬프트 글로 적어 주고, `format:"json"`
으로 JSON 을 강제하고, 그 JSON 을 다시 파싱한다. 말(say)은 ★또 한 번의 호출★이다.
그 층이 내는 값이 format tax 다 — 그리고 지어낸 슬롯이 T09 사슬의 첫 단추다:

    _ask_tool 이 없는 슬롯(fragment:"7")을 지어냄
      → FRAGMENT-GROUND(engine_desk.decide)가 "사용자가 말 안 한 것"이라며 지움
      → can_reach(trim_boundary) 실패 → main.py:5963 _r = None
      → ★결이 정확히 되물은 문장까지 통째로 버려진다★

맨몸 젬마4(`gemma4:e4b-it-qat`)는 ★표준 채팅 템플릿의 네이티브 도구 호출★로
9케이스 중 8을 맞췄다. 지어내지 않으면 위 사슬은 애초에 안 생긴다.
그래서 이 파일은 손으로 만든 층을 ★지우지 않고★ 옆에 길을 하나 낸다.
어느 쪽이 나은지는 `desk_none` 숫자가 말한다.

## 두 벌을 만들지 않는다

도구 스키마는 `engine_desk.CAPABILITIES` 에서 ★자동 생성★한다. 손으로 다시
적지 않는다 — 두 벌이 되면 다음 사람이 두 벌을 읽고, 언젠가 한 벌만 고친다
(이 저장소가 반복해서 겪은 부채다: 액션 이름 두 벌 · fid 저장처 13곳).
능력이 늘면 스키마도 저절로 는다. `census()` 가 그 사실을 매번 대조한다.

## 도구를 안 부른 것도 답이다

`tool_calls` 가 비었으면 ★그게 정답인 경우가 있다.★ 맨몸 실측에서
"좀 더 짧게" · "2배속으로 해줘" 는 도구 없이 되묻거나 정직하게 거절한 것이
정답이었다. 여기서 억지로 도구를 만들지 않는다 — cap=None 과 결의 말 그대로다.

## 말(say)은 어디서 오나 — ★기존 말하는 머리 그대로다.★ (실측이 시킨 모양)

처음엔 같은 호출의 `message.content` 를 쓰려 했다. 그러면 호출이 하나로 줄어
지연이 절반이 되고, HANDS-1 이 머리를 둘로 가른 뒤 생긴 병(도구 머리는
"없는 일"이라 골랐는데 말하는 머리는 "2배속으로 설정하겠습니다")도 사라진다.
만들어서 CCUT 경로로 재 봤다. ★안 됐다.★

  격리 실측 (젬마4 · 어려운 4케이스 × 씨앗 3 = 12):
    맨몸 머리 87자                       도구 12/12
    CCUT 목소리 머리 1,600자 그대로       도구  0/12
    ├ 미루는 예시("제가 CCUT한테 …해 볼게요") 제거   2/12
    ├ 정체성을 "도구를 부르면 그 손이 움직인다"로 재서술 2/12
    └ [이곳이 하려는 일] 문단 제거                  1/12
  CCUT 경로 9케이스: 도구 0건 → (지도 넓힌 뒤) 4건. 격리 6~7건에 못 미친다.

결이 틀린 게 아니다. 그 머리는 "편집하는 손은 CCUT이 갖고 있다 / 너는 시키는
쪽이다 / 대신 해주는 쪽이다"를 일곱 가지로 가르친다. 그래서 결은 배운 대로
"CCUT한테 시킬게요"라고 ★말했다.★ 정확히 맞는 행동이었다.
프롬프트로 세 번 되돌리려다 세 번 다 실패했고(같은 방법 3회 금지),
층을 바꿨다 — ★말하는 머리는 손대지 않고 도구 머리만 갈아 끼운다.★
그러면 두 조합의 차이가 오직 '손으로 만든 도구 층 vs 네이티브 도구 층'이 된다.
한 번의 호출로 합치는 것은 이 머리를 어떻게 할지 국장이 정한 뒤의 일이다.
"""
import json

from engine.engine_desk import CAPABILITIES, NOT_HERE

# 이 편집실에 손이 없는 일 — 능력이 아니라서 CAPABILITIES 에 없다.
#   C=json 경로는 `not_here` 를 ★고를 수 있는 항목★으로 준다(_ask_tool 의
#   "not_here: … — 이 편집실에 손이 없는 일이다"). 네이티브에서도 같은 출구를
#   준다. 안 주면 "2배속" 같은 말이 갈 곳이 없어 그냥 잡담으로 떨어지고,
#   main.py 가 wish 로 적어 두는 자리(§8 "불가능하다는 말로 대화를 끝내지
#   않는다")에 도달하지 못한다 — 축 비교가 배관 때문에 오염된다.
#   ★목록 자체는 NOT_HERE 하나에서 온다. 여기서도 두 벌을 안 만든다.
NOT_HERE_TOOL = "not_here"

# 인자 이름 → JSON 타입. 없는 이름은 문자열이다(needs 는 대부분 사람 말이라
#   문자열이 맞다: '2초' · '1분 30초' · '절반' · '가운데').
#   ★능력이 늘어도 이 표를 안 고쳐도 된다 — 모르는 키는 string 으로 나간다.
_ARG_TYPE = {
    "index": "integer",        # remove_ordinal — 몇 번째 (마지막이면 -1)
    "count": "integer",        # set_count
    "scene_no": "integer",     # remove_scene · look_scene · fix_scene_label
    "from_index": "integer",   # reorder_story
    "to_index": "integer",
}
_INT_KEYS = {k for k, v in _ARG_TYPE.items() if v == "integer"}


def _desc_for(cap):
    """도구 설명 — `_capability_lines` 와 ★같은 재료★(say + ways)를 쓴다.

    D축(도구 설명량)이 여기서도 살아야 한다. 안 그러면 C=tools 조합만
    D축이 통하지 않아 두 축을 같이 못 읽는다.
    """
    from engine import night2_probe as _n2
    d = _n2.axis_d()
    if d == "off":
        return ""
    say = cap["say"].split(" (예:")[0].strip()
    if d == "short":
        return say
    w = cap.get("ways") or []
    when = ("  ← " + " / ".join(f'"{x}"' for x in w[:2]) + " 같은 말") if w else ""
    return f"{say}{when}"


def _params_for(cap):
    props = {}
    for k, desc in (cap.get("needs") or {}).items():
        props[k] = {"type": _ARG_TYPE.get(k, "string"),
                    "description": str(desc)}
    # ★required 를 비운다.★ 채우라고 강제하면 젬마는 ★지어낸다★ —
    #   그것이 정확히 T09 사슬의 첫 단추다(fragment:"7" 을 지어내고,
    #   FRAGMENT-GROUND 가 지우고, can_reach 가 실패하고, 결의 말까지 버려진다).
    #   못 들었으면 비운 채로 오는 것이 맞다. 빈 슬롯은 손(desk_hands)과
    #   되묻기가 받는다 — 그쪽은 이미 그렇게 만들어져 있다.
    return {"type": "object", "properties": props, "required": []}


def tool_schemas():
    """★CAPABILITIES 에서 자동 생성★ — 손으로 적은 도구 목록은 이 파일에 없다."""
    tools = []
    for c in CAPABILITIES:
        tools.append({"type": "function",
                      "function": {"name": c["id"],
                                   "description": _desc_for(c),
                                   "parameters": _params_for(c)}})
    tools.append({"type": "function", "function": {
        "name": NOT_HERE_TOOL,
        "description": ("이 편집실에 손이 없어서 해줄 수 없는 일: "
                        + ", ".join(NOT_HERE)),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }})
    return tools


def census():
    """스키마가 CAPABILITIES 와 어긋나지 않는가 — 개수·이름 대조.

    자동 생성이라 어긋날 리 없다… 는 말이 이 저장소에서 여러 번 틀렸다.
    세어서 보여 주는 함수가 있어야 다음 사람이 확인할 수 있다.
    """
    names = [t["function"]["name"] for t in tool_schemas()]
    cap_ids = [c["id"] for c in CAPABILITIES]
    return {
        "capabilities": len(cap_ids),
        "tools": len(names),
        "extra_tools": sorted(set(names) - set(cap_ids)),      # not_here 하나여야
        "missing": sorted(set(cap_ids) - set(names)),          # 비어야 한다
        "same_order": names[:len(cap_ids)] == cap_ids,
        "arg_counts": {c["id"]: len(c.get("needs") or {}) for c in CAPABILITIES},
        "ok": (not set(cap_ids) - set(names)
               and sorted(set(names) - set(cap_ids)) == [NOT_HERE_TOOL]),
    }


def _coerce(name, args):
    """'3' 을 3 으로. 모델이 정수 칸에 문자열을 넣는 일은 흔하다."""
    out = {}
    for k, v in (args or {}).items():
        if k in _INT_KEYS and isinstance(v, str):
            s = v.strip()
            try:
                v = int(s)
            except ValueError:
                pass                       # 못 바꾸면 그대로 보낸다 — 지우지 않는다
        out[k] = v
    return out


def tool_head(ctx="", world_lines=""):
    """도구 머리 — engine_desk._ask_tool 의 ★알맹이만★ 남긴 것.

    _ask_tool 에서 가져온 것(지우면 실측으로 확인된 사고가 되살아난다):
      · [여기 있는 사람]  — GHOST-16. 이 세 줄이 없어서 "ccut은 빼고 너와
        둘이서만 대화하자"가 remove_scene{16} 이 됐다.
      · [방금 나눈 이야기]·[지금 영상] — 가리키는 말을 풀 재료.
      · 가리키는 말 안내 / 지어내지 말라는 안내.
    가져오지 않은 것(스키마가 대신 진다):
      · 능력 목록 산문(_capability_lines)  · 답 모양 지시(JSON)
      · talk/not_here 항목 — talk 는 '도구를 안 부르는 것'이 곧 그 뜻이고,
        not_here 는 스키마에 도구로 들어가 있다.
    ★짧게 두는 것이 성능이다(격리 실측: 87자 12/12 · 1,600자 0/12).
    """
    return (
        "영상 편집실이다. 사용자가 한 말을 실제로 해주려면 어떤 도구가 필요한가.\n"
        "필요하면 도구를 부르고, 인사·감사·잡담·감상처럼 아무 도구도 필요 없는\n"
        "말이면 부르지 않는다.\n\n"
        "[여기 있는 사람]\n"
        "'너'는 결이고, 'CCUT'은 같은 편집실에서 같이 일하는 동료다.\n"
        "둘 다 사람이지 영상에 찍힌 것이 아니다.\n"
        + (f"[방금 나눈 이야기]\n{ctx}\n" if ctx else "")
        + (f"[지금 영상]\n{world_lines}\n" if world_lines else "")
        + "\n가리키는 말('이 장면', '그거', '아까 그것')은 방금 나눈 이야기에서\n"
          "무엇을 가리키는지 찾아 번호나 이름을 채워라.\n"
          "못 들은 값은 지어내지 말고 비워 둬라.\n")


def _parse_calls(msg):
    """message.tool_calls → (cap, args, extra). ask_tool_native 와 ★같은 규칙★."""
    calls = msg.get("tool_calls") or []
    cap, args, extra = None, {}, []
    for i, c in enumerate(calls):
        fn = c.get("function") or {}
        name = fn.get("name")
        a = fn.get("arguments")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except Exception:
                a = {"_raw": a}
        a = _coerce(name, a if isinstance(a, dict) else {})
        if i == 0:
            cap, args = name, a
        else:
            extra.append({"tool": name, "args": a})
        from engine import night2_probe as _n2
        _n2.reach("gemma4_tools/tool_call/" + str(name))
    return cap, args, extra, len(calls)


def ask_both_native(system_head, user_text, timeout=90, temperature=0.4):
    """★[GEMMA4 2026-08-11] 말+도구를 ★한 번의 호출★로.

    왜 지금 다시 하는가: 두 물음은 hub._OLLAMA_LOCK 에 직렬화되므로 벽시계가
    두 호출의 ★합★이다(실측: 두 번째 호출의 lock_wait 이 첫 번째의 gen 과
    소수점까지 같다). 합치면 지연이 절반이다.
    전에 실패한 이유는 배관이 아니라 ★머리★였다 — CCUT 목소리 머리 1,600자에서
    젬마4가 도구를 0/12 불렀다(맨몸 87자 머리는 12/12). 그래서 V=hands 머리를
    먼저 만들고, 그 위에서만 이 길을 연다.

    ★안 되면 None 을 돌려준다.★ 호출처(engine_desk.decide)는 그걸 받으면
      2회 경로로 되돌아간다. 억지로 만들지 않는다.

    반환 {say, capability, args, n_calls, extra_calls, _fmt_hit:"tools_both"}.
    """
    from engine import hub
    from engine import night2_probe as _n2
    tools = tool_schemas()
    msgs = [{"role": "system", "content": system_head},
            {"role": "user", "content": user_text}]
    print(f"[GEMMA4][BOTH] 한 호출 · 머리 {len(system_head)}자 · 도구 {len(tools)}개",
          flush=True)
    try:
        data = hub._ollama_chat_native(
            msgs, tools=tools, temperature=temperature, timeout=timeout,
            think=_n2.think(), purpose="tools_both")
    except Exception as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f"[GEMMA4][BOTH][WARN] 한 호출 실패: {type(e).__name__}: {e} {body}",
              flush=True)
        _n2.desk_none("gemma4_both", err=f"{type(e).__name__}: {e}", body=body)
        return None
    msg = data.get("message") or {}
    say = str(msg.get("content") or "").strip()
    cap, args, extra, n = _parse_calls(msg)
    _n2.reach("gemma4_both/call")
    if n:
        _n2.reach("gemma4_both/said_and_called" if say else "gemma4_both/called_only")
    else:
        _n2.reach("gemma4_both/said_only")
    print(f"[GEMMA4][BOTH] cap={cap!r} args={json.dumps(args, ensure_ascii=False)} "
          f"calls={n} say={len(say)}자" + (f" ★버린 호출 {extra}" if extra else ""),
          flush=True)
    _n2.rec("gemma4_both", cap=cap, args=args, n_calls=n, extra=extra,
            say_chars=len(say), say=say[:400],
            thinking=str(msg.get("thinking") or "")[:300])
    return {"say": say, "capability": cap, "args": args, "n_calls": n,
            "extra_calls": extra, "_fmt_hit": "tools_both"}


def ask_tool_native(user_text, ctx="", world_lines="", timeout=90,
                    temperature=0.2):
    """[GEMMA4] engine_desk._ask_tool 의 네이티브 판. 반환 모양도 같다.

    반환 {capability, args, _fmt_hit, n_calls} — _ask_tool 이 내던 dict 와
    같은 자리에 꽂힌다(호출처는 한 곳, engine_desk._ask_tool).
    capability=None 은 실패가 아니다: 도구가 필요 없다고 본 것이고,
    되묻기·거절이 정답인 자리에서는 ★그게 맞는 답★이다.
    temperature 0.2 = 옛 도구 물음과 같은 값(_ask_tool:380).
    """
    from engine import hub
    from engine import night2_probe as _n2
    tools = tool_schemas()
    head = tool_head(ctx, world_lines)
    msgs = [{"role": "system", "content": head},
            {"role": "user", "content": user_text}]
    print(f"[GEMMA4][ASK-TOOL] 네이티브 · 머리 {len(head)}자 · 도구 {len(tools)}개 "
          f"· 세계 {len(world_lines or '')}자 · 이야기 {len(ctx or '')}자", flush=True)
    try:
        data = hub._ollama_chat_native(
            msgs, tools=tools, temperature=temperature, timeout=timeout,
            think=_n2.think(), purpose="tools")
    except Exception as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]                 # HTTPError
        except Exception:
            pass
        # ★C축과 모델 축은 ★묶여 있다.★ 실측: gemma3:4b 에 tools 를 주면
        #   ollama 가 400 "does not support tools" 를 낸다. 그러면 모든 턴이
        #   조용히 desk_none 이 되고, 다음 사람은 '네이티브가 형편없다'로 읽는다.
        #   막지 않는다 — ★무엇을 고쳐야 하는지 이름을 대고 시끄럽게 말한다.★
        if "does not support tools" in body:
            print(f"[GEMMA4][★설정 오류★] 이 모델은 네이티브 도구를 못 받는다: "
                  f"{hub.voice_model()} — C=tools 를 쓰려면 CCUT_NIGHT2_MODEL 을 "
                  f"도구를 받는 모델로 주거나 C축을 json 으로 되돌려라. "
                  f"(ollama: {body})", flush=True)
            _n2.reach("gemma4_tools/model_no_tools")
        print(f"[GEMMA4][WARN] 네이티브 도구 호출 실패: {type(e).__name__}: {e} {body}",
              flush=True)
        _n2.desk_none("gemma4_native", err=f"{type(e).__name__}: {e}", body=body)
        # ★{} 로 돌려준다 — _ask_tool 이 실패했을 때 내던 것과 같은 모양이다.
        #   None 을 내면 호출처가 다른 길로 갈라져 두 경로가 달라진다.
        return {}
    msg = data.get("message") or {}
    say = str(msg.get("content") or "").strip()
    calls = msg.get("tool_calls") or []
    cap, args, extra = None, {}, []
    for i, c in enumerate(calls):
        fn = c.get("function") or {}
        name = fn.get("name")
        a = fn.get("arguments")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except Exception:
                a = {"_raw": a}
        a = _coerce(name, a if isinstance(a, dict) else {})
        if i == 0:
            cap, args = name, a
        else:
            # 여러 개를 부르면 ★첫 것만★ 쓴다. 버린 것을 조용히 버리지 않는다 —
            #   기록에 남겨야 "한 턴에 둘을 부르더라"가 나중에 보인다.
            extra.append({"tool": name, "args": a})
        _n2.reach("gemma4_tools/tool_call/" + str(name))
    print(f"[GEMMA4][TOOL] cap={cap!r} args={json.dumps(args, ensure_ascii=False)} "
          f"calls={len(calls)} say={len(say)}자"
          + (f" ★버린 호출 {extra}" if extra else ""), flush=True)
    if not calls:
        # 도구를 안 부른 것 — 되묻기·거절·잡담. 실패가 아니다.
        _n2.rec("gemma4_no_tool", user_text=str(user_text)[:120], say=say[:300])
    _n2.rec("gemma4_native", cap=cap, args=args, n_calls=len(calls),
            extra=extra, say_chars=len(say),
            thinking=str(msg.get("thinking") or "")[:300])
    # say 는 ★안 돌려준다.★ 이 머리는 도구 머리다 — 여기서 나온 말은 사용자에게
    #   갈 말이 아니다(말은 decide 의 목소리 머리가 만든다). 버리지는 않고
    #   위 rec 에 남긴다: "도구 대신 말을 했다"가 나중에 보여야 한다.
    return {"capability": cap, "args": args, "n_calls": len(calls),
            "extra_calls": extra, "tool_head_say": say[:400],
            "_fmt_hit": "tools"}
