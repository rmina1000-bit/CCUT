"""[NIGHT-2] 밤 실험용 계측·축 스위치 — 기본값은 ★현행 그대로★다.

이 파일은 CCUT 의 동작을 바꾸지 않는다. 환경변수를 하나도 안 주면
- enabled() False  → 기록 0건 (rec 는 즉시 return)
- shadow()  False  → guard() 는 항상 True = 검문이 지금처럼 강등한다
- axis_*()  기본값 → 프롬프트 조립이 지금과 한 글자도 다르지 않다

왜 한 파일인가: 축 스위치가 코드 여기저기에 os.getenv 로 흩어지면 다음 사람이
'지금 무엇이 켜져 있나'를 셀 수 없다. 켜고 끄는 자리는 하나다.

환경변수
  CCUT_NIGHT2_PROBE=1     기록 켜기(동작 무변경). 이게 0 이면 아래 전부 잠든다.
  CCUT_NIGHT2_SHADOW=1    E축 그림자 — 검문이 판정만 기록하고 강등은 안 한다.
                          ★PROBE=1 일 때만 산다(기록 없는 그림자는 편향만 남긴다).
  CCUT_NIGHT2_NO_RENDER=1 밤중 렌더 차단(desk_hands._do_confirm_export).
  CCUT_N2_AXIS_A=on|off|full     세계(world_lines) 주입
  CCUT_N2_AXIS_B=on|off          직전 대화(ctx) 주입
  CCUT_N2_AXIS_C=json|xml|free|tools   결에게 시키는 ★응답 형식★ (format tax)
                          tools = [GEMMA4] 형식을 안 시킨다. ollama /api/chat 의
                          네이티브 도구 호출로 받는다(말+도구 한 번에).
  CCUT_NIGHT2_MODEL=...   [GEMMA4] 결의 목소리 모델 교체 (미설정=hub.VOICE_MODEL)
  CCUT_NIGHT2_THINK=0|1   [GEMMA4] /api/chat 의 think (미설정=키 자체를 안 보냄)
  CCUT_NIGHT2_NUM_CTX=n   [GEMMA4] num_ctx 강제 (미설정=hub._ctx_for 현행)
  CCUT_N2_AXIS_D=full|short|off  도구 설명(_capability_lines)
  CCUT_N2_AXIS_H=on|off          수첩(mirror_ledger) 주입
  CCUT_N2_AXIS_V=keep|hands|bare [GEMMA4] 결의 목소리 정체성 (keep=현행)
  CCUT_NIGHT2_NO_FALLBACK=1      desk 가 답을 못 냈을 때 뒷사다리로 안 넘긴다
  CCUT_LLM_SEED / CCUT_LLM_TEMPERATURE / CCUT_LLM_TOP_P / CCUT_LLM_TOP_K
                          (hub._n2_options 에서 읽는다 — 미설정이면 키를 안 넣는다)
"""
import json
import os
import threading
import time

_LOCK = threading.Lock()
_BUF = []
_MAX = 8000          # 드레인 안 해도 메모리가 안 새게. 넘치면 앞을 버린다.
_DROPPED = 0
_REACH = {}          # "이 코드가 실제로 불렸나" — 도달 증명용 카운터

_TRUE = ("1", "true", "True", "TRUE", "on", "ON", "yes")


def _flag(name):
    return (os.getenv(name) or "").strip() in _TRUE


def enabled():
    """기록 스위치. 동작은 안 바꾼다 — 켜도 CCUT 은 똑같이 돈다."""
    return _flag("CCUT_NIGHT2_PROBE")


def shadow():
    """E축 그림자 모드. 기록이 꺼져 있으면 그림자도 안 선다."""
    return enabled() and _flag("CCUT_NIGHT2_SHADOW")


def _short(v, n=400):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


def rec(kind, **fields):
    """append-only 기록. 기록이 꺼져 있으면 아무 일도 안 한다."""
    global _DROPPED
    if not enabled():
        return
    row = {"t": round(time.time(), 3), "kind": kind}
    row.update(fields)
    with _LOCK:
        if len(_BUF) >= _MAX:
            _BUF.pop(0)
            _DROPPED += 1
        _BUF.append(row)


def reach(name):
    """이 자리가 실제로 불렸다 — '정의는 있는데 호출처 0건'을 잡는 계수기."""
    with _LOCK:
        _REACH[name] = _REACH.get(name, 0) + 1
    rec("reach", where=name)


def reach_counts():
    with _LOCK:
        return dict(_REACH)


def drain():
    """모아 둔 기록을 넘기고 비운다(하네스가 턴마다 가져간다)."""
    global _DROPPED
    with _LOCK:
        out, _BUF[:] = list(_BUF), []
        dropped, _DROPPED = _DROPPED, 0
        reached = dict(_REACH)
    return {"enabled": enabled(), "shadow": shadow(), "rows": out,
            "dropped": dropped, "reach": reached, "axes": axes()}


# ── E축: 검문 ────────────────────────────────────────────────────────
def guard(name, **detail):
    """검문이 발동했다. ★반환 True = 원래대로 강등한다.★

    기본(그림자 OFF)에서는 무조건 True 라 현행과 완전히 같다.
    그림자 ON 이면 판정만 남기고 False — "안 막았으면 무엇이 됐을지"가
    남아야 (1)참진술 살해 (2)막은 실제 오류 (3)놓친 오류를 사후에 가른다.
    """
    s = shadow()
    if enabled():
        rec("guard", guard=name, demoted=(not s),
            detail={k: _short(v) for k, v in detail.items()})
    return not s


# ── 축 스위치 ────────────────────────────────────────────────────────
def _axis(letter, default, allowed):
    v = (os.getenv(f"CCUT_N2_AXIS_{letter}") or "").strip().lower()
    if not v:
        return default
    if v not in allowed:
        print(f"[NIGHT-2][WARN] CCUT_N2_AXIS_{letter}={v!r} 는 모르는 값 "
              f"(허용 {allowed}) → 기본 {default!r} 로 간다", flush=True)
        return default
    return v


def axis_a():
    """세계 주입. on=현행(scenes 는 비운 채 world_lines) / off=주입 없음 /
    full=장면 지도까지 통째로(실측 2,960자)."""
    return _axis("A", "on", ("on", "off", "full"))


def axis_b():
    """직전 대화(ctx) 주입. 결 자신의 답이 도는 고리는 여기에만 있다.

    on(기본)=현행(사용자+결 8턴) / off=주입 없음 / user=★사용자 말만★.

    ★[NIGHT-2 2026-08-10] user 를 세 번째 값으로 둔 이유:
      engine_desk.decide 의 주석이 "결의 말이 결의 입력으로 되도는 고리는
      B 에만 있다"고 적어 놓았는데, on/off 둘로는 그 고리를 못 가른다 —
      off 는 고리와 ★기억★을 함께 없앤다. user 는 기억은 남기고 고리만 끊는다.
      정정 과제(T16~T18)가 이 값에서 어떻게 되는지가 이 축의 알맹이다.
      (지시서의 B(3)·162조합 셈도 이 값이 있어야 맞는다 — 코드에는 2개뿐이었다.)
    """
    return _axis("B", "on", ("on", "off", "user"))


def axis_c():
    """[NIGHT-2] C축 — 결에게 시키는 응답 형식. json(현행) / xml / free / tools.

    ★hub.py:164 의 전역 "format":"json" 에는 걸지 않는다 — 그 자리를 풀면
      판사·추출·요약 등 사용자에게 안 보이는 계산까지 통째로 오염된다.
      _ollama_json 에 fmt= 인자를 더해 ★결이 말하는 두 자리만★ 바꾼다
      (engine_desk._ask_tool 의 도구 물음 · decide 의 say 물음).

    ★[GEMMA4 2026-08-11] 네 번째 값 tools 를 더했다. 앞 셋은 "형식을 어떻게
      시킬까"의 변주라 전부 ★형식 세금★을 낸다. tools 는 세금을 내는 대신
      자리를 옮긴다 — /api/generate + 손으로 짠 JSON 지시 대신
      /api/chat + 표준 채팅 템플릿의 네이티브 도구 호출(engine.gemma4_tools).
      ★바뀌는 것은 도구 머리(engine_desk._ask_tool) 하나뿐이다.★

      원래는 말+도구를 ★한 번의 호출★로 받으려 했다(그러면 지연이 절반이다).
      만들어서 재 봤고, 안 됐다 — 격리 실측(젬마4 · 4케이스 × 씨앗 3):
        머리 87자(맨몸)         도구 12/12
        CCUT 목소리 머리 1,600자  도구 ★0/12★  ("CCUT한테 시킬게요" 라고 말만 한다)
        미루는 예시 한 줄 제거     2/12 · 정체성 재서술    2/12 · 사명 문단 제거 1/12
      결이 틀린 게 아니다. 그 머리는 "너는 손이 없다"를 일곱 가지로 가르친다.
      배운 대로 답한 것이다. 프롬프트로 세 번 되돌리려다 실패했고(같은 방법
      3회 금지), 층을 바꿨다 — 말하는 머리는 그대로 두고 도구 머리만 짧게.
      HANDS-1 이 gemma3 에서 머리를 둘로 가른 근거가 젬마4에서도 그대로였다.
    """
    return _axis("C", "json", ("json", "xml", "free", "tools"))


# ★C축은 세 곳을 같이 바꿔야 뜻이 산다: (1) payload 의 format (2) 프롬프트의
#   답 모양 지시 (3) 응답 해석. (2)가 여기 있다 — json 값은 ★현행 문자열 그대로★라
#   기본에서 프롬프트가 한 글자도 안 달라진다.
_FMT_SAY = {
    "json": '답 모양: {"say": 사용자에게 할 말}',
    "xml": "답 모양: <answer><say>사용자에게 할 말</say></answer>",
    "free": "형식 없이, 사용자에게 할 말만 그대로 적어라.",
}
# ★[GEMMA4 2026-08-11] tools 는 ★말하는 머리를 안 건드린다★ — json 과 같은 값이다.
#   갈아 끼우는 것은 도구 머리 하나뿐이라, 두 조합의 차이가 오직 그 층이 된다.
#   (실측이 시킨 모양이다: 말+도구를 한 번에 받는 형태도 만들어 재 봤는데,
#    CCUT 의 1,600자 목소리 머리에서는 젬마4가 도구를 ★0/12★ 불렀다.
#    같은 모델이 87자 머리에서는 12/12 였다. 아래 axis_c 주석 참조.)
_FMT_SAY["tools"] = _FMT_SAY["json"]
_FMT_TOOL = {
    "json": '{"capability": 위에서 고른 이름, "args": {필요한 값}}',
    "xml": ("<tool><capability>위에서 고른 이름</capability>"
            "<args><이름>값</이름></args></tool>"),
    "free": ("첫 줄에 `capability: 고른 이름` 을 적고, 다음 줄부터 필요한 값을 "
             "`이름: 값` 으로 한 줄씩 적어라."),
    "tools": "",                                              # [GEMMA4] 위와 같음
}


def fmt_say_line():
    return _FMT_SAY[axis_c()]


def fmt_tool_line():
    return _FMT_TOOL[axis_c()]


def no_fallback():
    """desk 가 답을 못 냈을 때 뒷사다리(gemma_breath→draft_gate→intent_router)로
    안 넘긴다. 기본 OFF = 현행 그대로.

    ★왜 끊나(정찰로 전제가 바뀐 자리 — 2026-08-10 실측):
      지시서는 "폴백이 깨어나면 HUB_MODEL(qwen2.5)이 뜬다"였는데,
      grep 해 보니 이 경로의 LLM 호출은 ★전부 hub.VOICE_MODEL(gemma3:4b)★이다
      (intent_router._llm_understand:608 · _llm_smalltalk:1028 ·
       stream_smalltalk:1049 · gemma_breath:322 · edit_propose:260,472).
      qwen2.5 를 부르는 converse.decide_stream 은 /chat/converse/stream 전용이라
      /intent/route-edit/stream 에서는 닿지 않는다.
      → 축출 위험은 없다. 그래도 끊는 이유는 ★측정★이다: 다른 회로가 대신
        답하면 그 조합의 숫자가 'desk 가 낸 답'이 아니게 되어 축을 못 가른다.
    """
    return _flag("CCUT_NIGHT2_NO_FALLBACK")


def desk_none(where, **detail):
    """desk 가 None 으로 떨어졌다 = ★format tax 의 크기★. 실패가 아니라 측정값이다."""
    reach("desk_none/" + str(where))
    rec("desk_none", where=where, detail={k: _short(v) for k, v in detail.items()})


def axis_d():
    """도구 설명. full=현행(1,889자) / short=id+인자만(476자) / off=0자."""
    return _axis("D", "full", ("full", "short", "off"))


def axis_h():
    """수첩(mirror_ledger) 주입."""
    return _axis("H", "on", ("on", "off"))


def axis_v():
    """★[GEMMA4 2026-08-11] V축 — 결의 ★목소리 정체성★. keep(현행) / hands / bare.

    왜 축이 되었나(격리 실측 · 젬마4 · 어려운 4케이스 × 씨앗 3 = 12):
        맨몸 머리 87자                              도구 12/12
        CCUT 목소리 머리 1,600자                    도구  0/12
        ├ "제가 CCUT한테 …해 볼게요" 예시 제거        2/12
        ├ 정체성을 "도구를 부르면 그 손이 움직인다"    2/12
        └ [이곳이 하려는 일] 문단 제거                1/12
      조각 하나씩 빼서는 1~2 밖에 안 돌아온다 — ★1,600자 전체가 누적으로 누른다.★
      결이 틀린 게 아니다. 그 머리가 "너는 손이 없다"를 일곱 가지로 가르치고,
      결은 배운 대로 답했다.

    ★그런데 그 화법은 국장이 ★의도로 설계한 것★이다(HOUSE-1 단짝 화법).
      그래서 지우지 않는다 — 축으로 만들어 ★잰다.★ 기본값 keep = 현행 그대로라
      아무것도 안 주면 프롬프트가 한 글자도 안 달라진다.

    V 가 건드리는 곳은 ★정체성·사명 산문 블록 하나뿐이다.★
      세계(A)·직전 대화(B)·도구 설명(D)·집안 소식·답 모양은 세 값 모두 같다.
      안 그러면 V 가 다른 축과 섞여 무엇이 숫자를 움직였는지 못 가른다.
    """
    return _axis("V", "keep", ("keep", "hands", "bare"))


# ── [GEMMA4 2026-08-11] 모델 축 ────────────────────────────────────────
#   젬마4는 VOICE_MODEL 이 아니다. 그리고 gemma3:4b 와 ★공존이 안 된다★
#   (8GiB VRAM — 젬마4 로드 시 gemma3 축출, 실측). 그래서 모델을 갈아끼우는
#   자리가 필요하다. 셋 다 ★미설정이면 키 자체가 안 붙는다★ = 현행 그대로.
def model():
    """결의 목소리 모델. 미설정=None → 호출처가 hub.VOICE_MODEL 을 쓴다."""
    return (os.getenv("CCUT_NIGHT2_MODEL") or "").strip() or None


def think():
    """/api/chat 의 think. None=키를 안 보낸다 / True / False.

    젬마4는 thinking 기본 ON 이고 끄면 5.7배 빠르다(실측). 그런데 기본값을
    False 로 박으면 그 순간 '현행'이 아니게 된다 — 안 준 것과 끈 것은 다르다.
    """
    v = (os.getenv("CCUT_NIGHT2_THINK") or "").strip().lower()
    if not v:
        return None
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    print(f"[GEMMA4][WARN] CCUT_NIGHT2_THINK={v!r} 는 모르는 값 → 안 보낸다",
          flush=True)
    return None


def num_ctx():
    """num_ctx 강제. 미설정=None → hub._ctx_for 현행 그대로.

    ★조합마다 맞춰야 하는 이유: 젬마4 첫 로드가 ctx 4096 으로 떴다.
      gemma3:4b 는 16384 다(hub.VOICE_NUM_CTX). 안 맞추면 비교가 무효다.
      그리고 hub._ctx_for 는 '모델이 VOICE_MODEL 이냐'로 갈라서, 모델을
      갈아끼우면 ★조용히 8192★ 로 떨어진다. 그 조용함을 막는 자리다.
    """
    v = (os.getenv("CCUT_NIGHT2_NUM_CTX") or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        print(f"[GEMMA4][WARN] CCUT_NIGHT2_NUM_CTX={v!r} 가 정수가 아니다 → 무시",
              flush=True)
        return None


def axes():
    return {"A": axis_a(), "B": axis_b(), "C": axis_c(), "D": axis_d(),
            "H": axis_h(), "V": axis_v(),                     # [GEMMA4] V축
            "shadow": shadow(), "no_render": _flag("CCUT_NIGHT2_NO_RENDER"),
            "no_fallback": no_fallback(),
            "seed": os.getenv("CCUT_LLM_SEED"),
            "temperature": os.getenv("CCUT_LLM_TEMPERATURE"),
            # ★[GEMMA4] 샘플링도 조합끼리 같아야 비교가 산다. 여기서 ★보여만★
            #   준다(읽어서 payload 에 넣는 자리는 hub._n2_options 하나다).
            "top_p": os.getenv("CCUT_LLM_TOP_P"),
            "top_k": os.getenv("CCUT_LLM_TOP_K"),
            # [GEMMA4] 모델 축 — 미설정이면 셋 다 None 이라 is_default() 가 산다.
            "model": model(), "think": think(), "num_ctx": num_ctx()}


def default_axes():
    """기본값 표 — '현행 그대로'가 무엇인지 코드가 스스로 말하게 한다."""
    return {"A": "on", "B": "on", "C": "json", "D": "full", "H": "on",
            "V": "keep",                                      # [GEMMA4] V축
            "shadow": False, "no_render": False, "no_fallback": False,
            "seed": None, "temperature": None,
            "top_p": None, "top_k": None,                     # [GEMMA4]
            "model": None, "think": None, "num_ctx": None}   # [GEMMA4]


def is_default():
    return axes() == default_axes()
