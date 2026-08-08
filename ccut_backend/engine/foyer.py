"""[FOYER-1 2026-08-08] 현관 — 프로젝트를 열기 전에도 결이가 받는다.

국장 지시:
  "CCUT을 켜면 처음 만나는 화면에 입력창은 있는데 뒤에 아무도 없다.
   사용자가 처음 만나는 자리에서 말이 안 통하면, 안에서 아무리 잘 통해도
   이 물건의 첫인상은 '말 안 듣는 물건'이다."

안에서 검증된 구조를 그대로 쓴다 — 말과 도구를 갈라 병렬로 묻고(engine_desk),
고른 것을 실제로 하고, 한 일을 사실로 돌려준다.
새로 만드는 것은 '현관에서 할 수 있는 일' 목록 하나뿐이다.

현관의 결이가 알아야 할 것은 많지 않다: 프로젝트 목록 · 각각의 최근 상태 ·
자기 소개. 그 안쪽 편집은 이미 있는 회로가 이어받는다.
"""
import concurrent.futures as _cf
import re

from engine.house_talk import AI_NAME, AI_CALL

# ── 현관에서 할 수 있는 일 ────────────────────────────────────────────
FOYER_CAPS = [
    {
        "id": "open_project",
        "ways": ['어제 낚시 영상 어디 있지?', 'Marigold 열어줘', '그거 이어서 하자',
                 '아까 하던 거 보여줘'],
        "say": "프로젝트를 연다. 여는 순간 화면이 바뀌니, 어느 것인지 말하고 "
               "사용자가 그러자고 하면 그때 confirmed 를 true 로 준다",
        "needs": {"name": "프로젝트 이름", "confirmed": "사용자가 열라고 했으면 true"},
    },
    {
        "id": "new_project",
        "ways": ['새로 시작할래', '새 프로젝트 만들어줘', '처음부터 할래'],
        "say": "새 프로젝트를 만들 자리를 연다 — 만든 뒤에는 영상을 넣어야 한다",
        "needs": {"confirmed": "사용자가 만들자고 했으면 true"},
    },
    {
        "id": "recall_project",
        "ways": ['Marigold에서 뭐 하다 말았지?', '어디까지 했었지?', '그거 어떻게 됐더라'],
        "say": "프로젝트 하나가 지금 어떤 상태인지 살펴본다 (화면은 안 바뀐다)",
        "needs": {"name": "프로젝트 이름"},
    },
]


def _caps_lines():
    out = []
    for c in FOYER_CAPS:
        keys = ", ".join(c["needs"].keys())
        w = (c.get("ways") or [""])[0]
        out.append(f"  {c['id']}({keys}): {c['say']}" + (f'  ← "{w}" 같은 말' if w else ""))
    return "\n".join(out)


def projects():
    """프로젝트 목록과 각각의 지금 상태 — 현관 결이의 세계."""
    from engine.edit_propose import _connect
    con = _connect()
    try:
        rows = con.execute(
            "SELECT p.program_id, p.name, p.last_updated_at, "
            "  (SELECT COUNT(*) FROM project_sources s "
            "   WHERE s.program_id = p.program_id) AS n_src "
            "FROM programs p WHERE p.deleted_at IS NULL "
            "ORDER BY p.last_updated_at DESC").fetchall()
    except Exception as e:
        print(f"[FOYER][WARN] 목록 조회 실패: {e}")
        return []
    finally:
        con.close()
    out = []
    for r in rows:
        if not (r["n_src"] or 0):
            continue          # 영상이 없는 껍데기는 목록에 없다(기존 /projects 와 같은 기준)
        out.append({"program_id": r["program_id"], "name": r["name"] or "이름 없음",
                    "updated": str(r["last_updated_at"] or "")[:16],
                    "sources": r["n_src"]})
    return out


def state_of(program_id):
    """그 프로젝트에서 어디까지 했나 — 원고 조각 수와 마지막으로 한 일."""
    try:
        from engine import desk_hands as _h
        live, _ = _h._live_fids(program_id)
        rs = _h.recent_receipts(program_id, 1)
        return {"fragments": len(live),
                "last": (rs[0].get("what") if rs else "")}
    except Exception as e:
        print(f"[FOYER][WARN] 상태 조회 실패: {e}")
        return {"fragments": 0, "last": ""}


def _world_lines(projs, detail_for=None):
    if not projs:
        return "아직 만든 프로젝트가 없다."
    lines = []
    for p in projs:
        line = f"- {p['name']} (영상 {p['sources']}개, 마지막 {p['updated']})"
        if detail_for and p["program_id"] == detail_for:
            st = state_of(p["program_id"])
            line += f" — 지금 편집본 {st['fragments']}조각"
            if st["last"]:
                line += f", 마지막으로 한 일: {st['last']}"
        lines.append(line)
    return "\n".join(lines)


def find_project(projs, name):
    """이름으로 찾는다 — 사람은 정확히 안 적는다('마리골드', 'marigold ')."""
    key = re.sub(r"\s+", "", str(name or "")).lower()
    if not key:
        return None
    for p in projs:
        if re.sub(r"\s+", "", p["name"]).lower() == key:
            return p
    for p in projs:                       # 부분 일치도 받는다
        n = re.sub(r"\s+", "", p["name"]).lower()
        if key in n or n in key:
            return p
    return None


def _ask_tool(user_text, ctx, world):
    """도구만 고른다 — engine_desk 와 같은 형태(격리 10/10 이 나온 그것)."""
    from engine import hub
    prompt = (
        "CCUT 현관에서 쓸 수 있는 것들이다. 사용자가 한 말에 가장 맞는 것을 "
        "하나 고르고, 필요한 값을 채워라.\n\n"
        "  talk: 인사·잡담·자기소개라 아무것도 할 필요 없다\n"
        + _caps_lines() + "\n"
        + (f"[지금 있는 프로젝트]\n{world}\n" if world else "")
        + (f"[방금 나눈 이야기]\n{ctx}\n" if ctx else "")
        + f"\n[사용자가 한 말]\n{user_text}\n\n"
        '{"capability": 위에서 고른 이름, "args": {필요한 값}}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.2,
                               model=hub.VOICE_MODEL)
        return out if isinstance(out, dict) else {}
    except Exception as e:
        print(f"[FOYER][WARN] 도구 선택 실패: {e}")
        return {}


def decide(user_text, recent_messages=None, detail_for=None):
    """현관의 결이 — 말과 도구를 갈라 동시에 묻는다(안에서 쓰는 그 구조)."""
    from engine import hub
    from engine.intent_router import _sanitize_talk

    projs = projects()
    world = _world_lines(projs, detail_for)
    ctx = ""
    for m in (recent_messages or [])[-8:]:
        who = "사용자" if (m.get("sender") == "user") else "나"
        txt = str(m.get("text") or "")[:160]
        if txt:
            ctx += f"{who}: {txt}\n"

    prompt = (
        f"너는 '{AI_NAME}'이다. 사람들은 너를 {AI_CALL}라고 부른다.\n"
        "여기는 CCUT 편집실의 현관이고, 너는 CCUT이 아니다 — CCUT에서 일하는\n"
        "동료다. 편집하는 손은 CCUT이 갖고 있다. CCUT 이야기를 할 때는 남\n"
        "이야기하듯 한다 — \"CCUT이 …했어요\", \"제가 CCUT한테 …해 볼게요\".\n\n"
        "[이곳이 하려는 일]\n"
        "혼자 영상을 만드는 사람이 하루 종일 찍어 온 것을 들고 온다. 그 사람은\n"
        "편집을 배운 적이 없고 지쳐 있다. 여기 현관에서는 어느 작업을 이어서\n"
        "할지 고르거나, 새로 시작한다. 안으로 들어가면 함께 편집한다.\n\n"
        f"[지금 있는 프로젝트]\n{world}\n\n"
        f"[네가 할 수 있는 것]\n{_caps_lines()}\n\n"
        + (f"[지금까지 나눈 이야기]\n{ctx}\n" if ctx else "")
        + f"[사용자]\n{user_text}\n\n"
        "편하게 답해라.\n"
        '답 모양: {"say": 사용자에게 할 말}'
    )
    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as ex:
            f_say = ex.submit(hub._ollama_json, prompt, timeout=30,
                              temperature=0.4, model=hub.VOICE_MODEL)
            f_cap = ex.submit(_ask_tool, user_text, ctx, world)
            out = f_say.result() or {}
            picked = f_cap.result() or {}
    except Exception as e:
        print(f"[FOYER][WARN] 판단 실패: {e}")
        return None

    cap = picked.get("capability")
    cap = None if cap in (None, "", "null", "none", "None", "talk") else str(cap).strip()
    if cap and cap not in {c["id"] for c in FOYER_CAPS}:
        print(f"[FOYER][WARN] 없는 것 {cap!r} → 대화로")
        cap = None
    args = picked.get("args") if isinstance(picked.get("args"), dict) else {}
    say = _sanitize_talk(str(out.get("say") or "").strip()) or ""
    if any(c["id"] in say for c in FOYER_CAPS):
        keep = [s for s in re.split(r"(?<=[.!?])\s+", say)
                if not any(c["id"] in s for c in FOYER_CAPS)]
        say = " ".join(keep).strip()
    return {"cap": cap, "args": args, "say": re.sub(r"\s{2,}", " ", say).strip(),
            "projects": projs}


def _truthy(v):
    return v in (True, "true", "True", "yes", "네", 1, "1")


def answer(user_text, recent_messages=None):
    """현관 한 턴. 화면을 바꿔야 하면 open/new 를 함께 돌려준다."""
    r = decide(user_text, recent_messages)
    if not r:
        return None
    projs, cap, args = r["projects"], r["cap"], r["args"]
    say = r["say"]

    if cap == "recall_project":
        p = find_project(projs, args.get("name"))
        if p:
            # 그 프로젝트만 자세히 보고 다시 말한다 — 안에서 쓰는 look 과 같은 결.
            r2 = decide(user_text, recent_messages, detail_for=p["program_id"])
            if r2 and r2["say"]:
                return {"reply": r2["say"], "kind": "foyer_recall"}
        return {"reply": say or "어느 작업을 말씀하시는 걸까요?",
                "kind": "foyer_recall"}

    if cap == "open_project":
        p = find_project(projs, args.get("name"))
        if not p:
            names = ", ".join(x["name"] for x in projs[:6]) or "아직 없어요"
            return {"reply": say or f"어느 걸 열까요? 지금은 {names} 이 있어요.",
                    "kind": "foyer_ask"}
        # ★결이가 방금 이 프로젝트를 짚어 물었고 지금 또 열자고 하면, 그게 확인이다.
        #   실측: "응 열어줘" 에 결이가 confirmed 를 안 채워 계속 되물었다.
        #   인자를 못 채운 것이지 뜻이 없는 게 아니다 — 뜻은 대화에 있다.
        _asked = any(p["name"] in str(m.get("text") or "")
                     for m in (recent_messages or [])[-4:]
                     if m.get("sender") != "user")
        if _truthy(args.get("confirmed")) or _asked:
            print(f"[FOYER] 연다: {p['name']}")
            return {"reply": say or f"{p['name']} 열게요.",
                    "kind": "foyer_open", "open_project_id": p["program_id"],
                    "open_project_name": p["name"]}
        st = state_of(p["program_id"])
        return {"reply": say or (f"{p['name']}에 있어요. 편집본 "
                                 f"{st['fragments']}조각까지 하셨네요. 열어드릴까요?"),
                "kind": "foyer_ask", "suggest_project_id": p["program_id"]}

    if cap == "new_project":
        if _truthy(args.get("confirmed")):
            print("[FOYER] 새 프로젝트")
            return {"reply": say or "새로 만들게요. 영상을 넣어 주세요.",
                    "kind": "foyer_new", "new_project": True}
        return {"reply": say or "새로 시작할까요?", "kind": "foyer_ask"}

    return {"reply": say, "kind": "foyer_talk"}
