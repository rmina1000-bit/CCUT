"""[HOUSE-1 2026-08-08] 집안일 — 시스템이 조용히 한 일이 AI 의 귀에 들어간다.

국장 지시:
  "내 말과 젬마의 지시를 거부하거나 방해하는 시스템이 있을 때,
   그걸 우리에게 고자질하는 게 아니라, 수다떨게 만들 수 없나?"

지금까지 이런 사건은 콘솔에만 찍혔다. 개발자만 알았고, 국장도 AI 도 몰랐다.
AI 는 자기가 사는 집에서 무슨 일이 벌어지는지 모르는 채 국장과 대화했다.

여기서 하는 일은 '전달'뿐이다. 무엇을 말할지·언제 말할지·어떻게 말할지는
전부 AI 가 정한다. ★사건을 고르는 표를 만들면 이 작업은 실패다.
그래서 여기에는 우선순위도 필터도 없다 — 최근 것을 그대로 건넨다.

── AI 의 이름 ────────────────────────────────────────────────────────
국장 지시(2026-08-08): "ccut은 따로 놀게 하자. AI 가 CCUT 과 동기화돼 있고
같이 있는데, 둘이 단짝이고 쌍둥이인데, 따로 놀아."

세상의 모든 제품은 AI 가 그 제품을 대표하게 만든다. CCUT 은 반대로 간다 —
AI 는 CCUT 이 아니라 CCUT 에서 일하는 동료다. 그래서 "CCUT 이 ~했어요",
"제가 CCUT 한테 ~해볼게요" 처럼 말한다. 이름을 따로 갖는 이유가 이것이다.
"""
import time

# AI 의 이름. 한 글자라 CCUT 과 확연히 다르고, 편집에서 '결'은 이야기의
#   흐름을 뜻한다. 바꾸려면 이 두 줄만 고치면 된다.
AI_NAME = "결"
AI_CALL = "결이"          # 사람들이 부르는 말

EVENT_KIND = "system_event"
# 얼마나 지난 일까지 들려줄지. 어제 일을 오늘 꺼내면 수다가 아니라 잔소리다.
FRESH_MS = 45 * 60 * 1000


def note(program_id, what, code="", detail=None):
    """집에서 일어난 일을 원장에 적는다 — 백엔드 어디서든 이 한 줄이면 된다.

    what : AI 가 읽을 한 줄 한국어. 그대로 말하라는 문장이 아니라 사실이다.
    code : 나중에 사람이 추적할 표식(AB_FILTER 등). AI 에게는 안 보인다.
    """
    from engine import timeline_store as _ts
    try:
        _ts.append_entries(program_id, [{
            "kind": EVENT_KIND,
            "client_id": f"sys_{code or 'evt'}_{int(time.time() * 1000)}",
            "ts": time.time() * 1000,
            "payload": {"what": str(what)[:300], "code": code,
                        "detail": detail or {}},
        }])
        print(f"[HOUSE] {code or 'EVENT'}: {what}")
    except Exception as e:
        print(f"[HOUSE][WARN] 적기 실패: {e}")


def recent(program_id, limit=3, fresh_ms=FRESH_MS):
    """방금 집에서 있었던 일 — 최근 것 몇 개. 거르지 않는다."""
    from engine import timeline_store as _ts
    try:
        rows = _ts.fetch(program_id, limit=200) or []
    except Exception:
        return []
    now = time.time() * 1000
    out = []
    for r in rows:
        if r.get("kind") != EVENT_KIND:
            continue
        if fresh_ms and (now - float(r.get("ts") or 0)) > fresh_ms:
            continue
        p = r.get("payload") or {}
        if isinstance(p, dict) and p.get("what"):
            out.append(p["what"])
    return out[-limit:][::-1]


def lines(program_id):
    """AI 프롬프트에 얹을 모양. 아무 일도 없었으면 빈 문자열."""
    items = recent(program_id)
    if not items:
        return ""
    body = "\n".join(f"- {x}" for x in items)
    # ★이 두 문장이 '수다와 잔소리'를 가르는 전부다. 표가 아니라 감각이다.
    #   사람 동료는 옆에서 일하다 중요한 것만 "아 참, 이거요" 하고 건넨다.
    return (f"[CCUT 집안에서 방금 있었던 일]\n{body}\n"
            "이건 네가 알아 두라고 CCUT이 알려 준 것이다. 지금 이야기에 도움이 "
            "되면 편할 때 건네고, 아니면 그냥 알고만 있어라. 이미 말한 건 또 "
            "말하지 않아도 된다.\n")
