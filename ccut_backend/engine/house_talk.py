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


# ★[GHOST-16 2026-08-09] 이미 건넨 소식 — 같은 말을 두 번 귀에 넣지 않는다.
#   실측(Daffodil, 국장 화면 22:07~22:11): 45분 창 안에 문구가 완전히 같은
#   AB_FILTER 소식이 여러 행(entry 532·533·544·545·546…) 쌓여 있었고,
#   recent() 는 거를 것이 없어 매 턴 같은 소식을 그대로 다시 건넸다.
#   결의 답 "CCUT이 화면에서 내려 뒀기 때문입니다" 는 이 payload 문자열 그대로다.
#   ★사건을 고르는 표가 아니다(그건 이 파일이 금지한 것이다). 한 번 건넨 것을
#     또 건네지 않는 배관 수리다 — 무엇을 말할지는 여전히 전부 결이 정한다.
#   프로세스 안에만 둔다(새 kind·새 테이블·쓰기 0). 재기동하면 다시 한 번은 건넨다.
_HANDED = {}


def recent(program_id, limit=3, fresh_ms=FRESH_MS, mark=True):
    """방금 집에서 있었던 일 — 최근 것 몇 개. 거르지 않는다.

    거르는 것은 '무엇을 말할지'가 아니라 '이미 건넨 것'뿐이다.
    """
    from engine import timeline_store as _ts
    try:
        rows = _ts.fetch(program_id, limit=200) or []
    except Exception:
        return []
    now = time.time() * 1000
    handed = _HANDED.setdefault(str(program_id), set())
    out, keys, twins = [], [], []
    seen_what = set()
    skipped = 0
    for r in rows:
        if r.get("kind") != EVENT_KIND:
            continue
        if fresh_ms and (now - float(r.get("ts") or 0)) > fresh_ms:
            continue
        p = r.get("payload") or {}
        if not (isinstance(p, dict) and p.get("what")):
            continue
        what = p["what"]
        cid = str(r.get("client_id") or r.get("entry_id") or what)
        # ① 이 한 번의 전달 안에서 같은 문구가 여러 행으로 쌓인 것 → 한 번만
        #    (실측 532·533 은 문구가 완전히 같은 두 행이었다)
        if what in seen_what:
            skipped += 1
            twins.append(cid)       # 같은 말이니 이 행도 '건넨 것'으로 친다
            continue                #   (안 그러면 다음 턴에 쌍둥이 행이 대신 들어간다)
        # ② 이미 결의 귀에 들어간 행 → 다시 넣지 않는다. 표식은 행(client_id)
        #    이라, 나중에 진짜로 다시 일어난 일은 새 행이므로 그때 또 건넨다.
        if cid in handed:
            skipped += 1
            continue
        seen_what.add(what)
        out.append(what)
        keys.append(cid)
    out, keys = out[-limit:][::-1], keys[-limit:][::-1]
    if mark:
        handed.update(keys)
        handed.update(twins)
    # ★도달 증명용 한 줄 — "방어를 만들면 발동한 사례를 하나 확보한다"(CLAUDE.md).
    #   등록만 하고 호출처 0건이던 사고를 반복하지 않으려고 소리를 낸다.
    if skipped:
        print(f"[HOUSE][이미 건넸다] {skipped}건은 다시 안 넣는다 "
              f"(건넨 것 {len(handed)}건)")
    return out


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
