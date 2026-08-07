"""
[DESK-1 2026-08-08] 엔진 접수대 — 젬마가 통역사로 서는 자리.

국장이 정한 젬마의 일:
  "내 말을 듣고, 내가 말한 그곳이 내가 지시한 것을 할 수 있는 곳인지 확인하고,
   그곳에 있는 엔진에게 내 지시를 엔진이 알아듣는 말로 번역해서 지시를 하고,
   엔진이 작업 데이터를 주면 그걸 내가 알아듣는 말로 말해주지."

그래서 젬마는 손이 아니다. 손은 엔진이 갖고 있다. 젬마는 셋만 한다.
  ① 확인   이 요청을 받아 줄 엔진이 있는가 (없으면 없다고 말한다)
  ② 번역   사람 말 → 엔진이 알아듣는 인자
  ③ 통역   엔진이 준 데이터 → 사람 말

여기 적힌 능력은 전부 코드에서 실측한 것이다. 자막·색보정·소리크기처럼
엔진에 없는 것은 목록에 없다 — 없으면 젬마가 없다고 말할 수 있다.
엔진에 능력이 늘면 이 목록도 같이 는다. 안 늘리면 젬마가 거짓말을 하게 된다.

실측 근거(2026-08-08): 젬마는 추상적 행동 이름 고르기는 6/6 실패했지만
사람 말 → 구체적 엔진 능력 매핑은 9/10 맞혔다. 이 자리가 젬마에게 맞는 일이다.
"""
import json
import re

# ── 접수 가능한 엔진 능력 (코드 실측) ──────────────────────────────────
#   id      : 젬마가 고르는 이름
#   engine  : 실제 코드 경로(사람이 추적할 수 있게)
#   needs   : 젬마가 채워야 할 인자
#   scope   : 조각 하나(fragment) / 원고 전체(story) / 조회(read)
CAPABILITIES = [
    {
        "id": "trim_boundary",
        "say": "조각의 앞이나 뒤 경계를 다듬는다 (말이 없는 구간을 덜어낸다)",
        "engine": "POST /edit-state (command_type=TRIM)",
        "needs": {"fragment": "대상 조각", "side": "start 또는 end"},
        "scope": "fragment",
    },
    {
        "id": "exclude_range",
        "say": "조각 안의 특정 구간만 빼낸다",
        "engine": "POST /edit-state (command_type=EXCLUDE_RANGE)",
        "needs": {"fragment": "대상 조각"},
        "scope": "fragment",
    },
    {
        "id": "remove_fragment",
        "say": "조각 하나를 통째로 뺀다 — 사용자가 조각 이름(A60 같은 것)으로 가리킬 때",
        "engine": "POST /edit-state (command_type=REMOVE)",
        "needs": {"fragment": "대상 조각 이름"},
        "scope": "fragment",
    },
    {
        "id": "restore_fragment",
        "say": "뺐거나 다듬은 것을 이전 값으로 되돌린다",
        "engine": "POST /edit-state (command_type=RESTORE)",
        "needs": {"fragment": "대상 조각"},
        "scope": "fragment",
    },
    {
        "id": "remove_ordinal",
        "say": "원고에서 몇 번째 조각을 뺀다 — 사용자가 순번(3번째 같은 것)으로 가리킬 때",
        "engine": "POST /revision/proposals (op=remove_ordinal)",
        "needs": {"index": "몇 번째인지 숫자 (1~40, 마지막이면 -1)"},
        "scope": "story",
    },
    {
        "id": "set_count",
        "say": "원고의 조각 개수를 맞춘다",
        "engine": "POST /revision/proposals (op=set_count)",
        "needs": {"count": "원하는 조각 수 (1~40)"},
        "scope": "story",
    },
    {
        "id": "remove_theme",
        "say": "어떤 주제·소재가 나오는 조각들을 원고에서 뺀다",
        "engine": "POST /revision/proposals (op=remove_theme)",
        "needs": {"theme": "뺄 소재 낱말 (20자 이내)"},
        "scope": "story",
    },
    {
        "id": "reorder_story",
        "say": "원고에서 조각의 순서를 바꾼다",
        "engine": "POST /projects/{id}/state (ui_state.storyFragments 순서)",
        "needs": {"from_index": "옮길 조각의 현재 자리", "to_index": "옮겨 갈 자리"},
        "scope": "story",
    },
    {
        "id": "find_fragments",
        "say": "말이나 장면으로 조각을 찾아본다",
        "engine": "engine.fragment_search.search",
        "needs": {"query": "찾을 말"},
        "scope": "read",
    },
    {
        "id": "read_sound_roles",
        "say": "조각마다 소리가 대사인지 배경인지 조용한지 살펴본다",
        "engine": "GET /sound-role/{program_id}",
        "needs": {},
        "scope": "read",
    },
    {
        "id": "set_sound_role",
        "say": "어떤 조각의 소리 성격을 대사·배경·조용함 중 하나로 고쳐 준다",
        "engine": "POST /sound-role/{program_id}",
        "needs": {"fragment": "대상 조각",
                  "role": "dialogue / background / silence 중 하나"},
        "scope": "fragment",
    },
]

# 엔진에 없는 일 — 젬마가 "된다"고 말하지 않게 명시한다(실측: 자막 요청이
# A/B 재제안 절차로 흘렀다). 능력이 생기면 위 목록으로 옮기고 여기서 지운다.
NOT_HERE = [
    "자막 넣기·자막 수정",
    "색 보정·색감·색온도 바꾸기",
    "밝기·대비 조절",
    "소리 크기 조절·잡음 제거 (소리의 성격을 적어 두는 것은 되지만 소리 자체는 못 바꾼다)",
    "화면 효과·전환 효과 넣기",
    "속도 조절(빠르게·느리게)",
    "음악 넣기",
]


def _capability_lines(labels_hint=""):
    lines = []
    for c in CAPABILITIES:
        need = ", ".join(f"{k}({v})" for k, v in c["needs"].items()) or "없음"
        lines.append(f"- {c['id']}: {c['say']} / 필요한 값: {need}")
    return "\n".join(lines)


def _not_here_lines():
    return "\n".join(f"- {x}" for x in NOT_HERE)


def find(cap_id):
    for c in CAPABILITIES:
        if c["id"] == cap_id:
            return c
    return None


def receive(user_text, world_lines="", recent_messages=None):
    """① 확인 + ② 번역. 젬마가 접수대에서 하는 일.

    반환 {cap, args, say, reason} 또는 None(젬마 미응답).
      cap  : 능력 id 또는 None(= 여기서 할 수 없는 일)
      args : 엔진에 넘길 값들(젬마가 채운 것 — 서버가 다시 검증한다)
      say  : 사용자에게 할 말
    """
    from engine import hub
    from engine.intent_router import _sanitize_talk

    ctx = ""
    for m in (recent_messages or [])[-5:]:
        who = "사용자" if (m.get("sender") == "user") else "나"
        txt = str(m.get("text") or "")[:90]
        if txt:
            ctx += f"{who}: {txt}\n"

    prompt = (
        "너는 CCUT 편집실의 통역사다. 사용자의 말을 듣고, 그 일을 해 줄 엔진이 "
        "여기 있는지 확인해서, 있으면 엔진이 알아듣는 말로 옮긴다.\n"
        "너는 직접 편집하지 않는다. 엔진이 한다.\n\n"
        f"[이 편집실의 엔진이 할 수 있는 일]\n{_capability_lines()}\n\n"
        f"[이 편집실에 없는 일 — 사용자가 부탁해도 못 한다]\n{_not_here_lines()}\n\n"
        + (f"[지금 이 이야기]\n{world_lines}\n\n" if world_lines else "")
        + (f"[최근 대화]\n{ctx}\n" if ctx else "")
        + f"[사용자의 말]\n{user_text}\n\n"
        "판단:\n"
        "★먼저 이것이 묻는 말인지 시키는 말인지 가른다. "
        "'있어?·뭐야?·몇 개야?·어떻게 돼?'처럼 묻는 말은 편집 지시가 아니다 — "
        "찾아보는 것(find_fragments)이거나 그냥 대화다. 묻는 말을 빼거나 고치는 "
        "일로 읽으면 사용자의 이야기가 망가진다.\n"
        "- 편집을 부탁한 것이고 위 목록에 그 일이 있으면 → capability 에 그 id\n"
        "- 편집을 부탁했는데 목록에 없으면 → capability: null, reason: \"없는 일\"\n"
        "- 편집 부탁이 아니라 그냥 대화면 → capability: null, reason: \"대화\"\n"
        "- 무엇을 말하는지 알 수 없으면 → capability: null, reason: \"모르겠음\"\n\n"
        "say 는 사용자에게 할 말이다. 없는 일이면 못 한다고 솔직히 말하고 "
        "대신 무엇을 할 수 있는지 알려준다. 숫자를 지어내지 마라.\n"
        "★say 에는 위 목록의 영어 이름(set_count 같은 것)을 쓰지 마라 — "
        "그건 나와 엔진 사이의 말이고 사용자는 모른다. 사람 말로만 적어라.\n"
        'JSON만 출력: {"capability":"id 또는 null","args":{},"reason":"...",'
        '"say":"사용자에게 할 말"}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.4,
                               model=hub.VOICE_MODEL)
    except Exception as e:
        print(f"[DESK][WARN] 접수 실패: {e}")
        return None

    cap = out.get("capability")
    cap = None if cap in (None, "", "null", "none") else str(cap).strip()
    if cap and not find(cap):
        print(f"[DESK][WARN] 목록에 없는 능력 {cap!r} → 없는 일로 읽는다")
        cap = None
    args = out.get("args") if isinstance(out.get("args"), dict) else {}
    say = _sanitize_talk(str(out.get("say") or "").strip()) or ""
    # 내부 이름이 사용자에게 새면 지운다 — 엔진과 나 사이의 말이다(실측 누출).
    leaked = [c["id"] for c in CAPABILITIES if c["id"] in say]
    if leaked:
        print(f"[DESK][NAME-GUARD] 내부 이름 누출 {leaked} → 사람 말로 정리")
        for cid in leaked:
            human = find(cid)["say"].split(" — ")[0]
            say = say.replace(cid, human)
        say = re.sub(r"\s{2,}", " ", say).strip()
    reason = str(out.get("reason") or "").strip()
    return {"cap": cap, "args": args, "say": say, "reason": reason}


def look(user_text, scene_lines, recent_messages=None):
    """[STRUCT-A② 2026-08-08] 조회로 판정된 뒤에만 장면 지도를 펴고 답한다.

    ★왜 접수 때 같이 주지 않는가(실측):
      L1(2,228자)을 접수 프롬프트에 얹었더니 접수대가 무너졌다 —
        '자막을 넣어줘'(없는 일) → remove_fragment 로 읽음
        '고양이 나온 장면 있어?' → "조각 3번과 17번에서 나타납니다"(지어냄)
      같은 질문을 짧은 world 로 물으면 각각 None(정답)·find_fragments 로 맞혔다.
      눈앞의 목록이 앵커가 되어 조각 조작 쪽으로 기운다. 젬마 4B 에서 어제
      호흡 회로가 겪은 것과 같은 병이다.
    ★그래서 층을 나눈다: 판단할 때는 눈이 짧고, 답할 때 눈을 뜬다."""
    from engine import hub
    from engine.intent_router import _sanitize_talk

    prompt = (
        "너는 CCUT 편집실의 통역사다. 사용자가 영상에 대해 물었다.\n"
        "아래는 이 영상을 장면 단위로 훑은 지도다. **여기 적힌 것만** 사실이다.\n"
        "적혀 있지 않은 것은 '없다' 또는 '확인되지 않는다'고 말한다. "
        "조각 번호를 지어내지 마라.\n\n"
        f"[장면 지도]\n{scene_lines}\n\n"
        f"[사용자의 물음]\n{user_text}\n\n"
        "한국어 1~3문장으로 답한다. 장면 번호와 시간은 위에 적힌 것만 쓴다.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.4,
                               model=hub.VOICE_MODEL)
        say = _sanitize_talk(str(out.get("say") or "").strip()) or None
    except Exception as e:
        print(f"[DESK][WARN] 조회 답변 실패: {e}")
        return None
    if not say:
        return None
    # [TIME-GUARD] 답에 적힌 시각이 지도에 있는 것인가 — 사용자는 이 시간으로
    #   실제 영상을 찾아간다. 실측에서 '1분51초'를 '2분51초'로 옮겨 적은 예가 나왔다.
    #   지도에 없는 시각이 섞이면 그 시각만 지우지 않고 문장을 통째로 버린다
    #   (반쪽 사실이 더 위험하다). 숫자를 못 믿으면 시간 없이 다시 답하게 한다.
    said = set(re.findall(r"\d+분\d+초", say))
    known = set(re.findall(r"\d+분\d+초", scene_lines or ""))
    bad = said - known
    if bad:
        print(f"[DESK][TIME-GUARD] 지도에 없는 시각 {sorted(bad)} → 시간 빼고 다시")
        try:
            out2 = hub._ollama_json(
                prompt + "\n주의: 시각(N분NN초)을 적지 마라. 장면 내용만 말하라.",
                timeout=25, temperature=0.3, model=hub.VOICE_MODEL)
            say2 = _sanitize_talk(str(out2.get("say") or "").strip())
            if say2 and not (set(re.findall(r"\d+분\d+초", say2)) - known):
                return say2
        except Exception:
            pass
        return re.sub(r"\s*\d+분\d+초\s*[~-]?\s*", " ", say).strip() or None
    return say


def explain(result_data, user_text, cap_id=None):
    """③ 통역. 엔진이 준 작업 데이터를 사용자 말로 옮긴다.

    result_data 는 서버가 만든 사실 문장 목록이다(숫자는 여기서 이미 확정).
    젬마는 이것을 사람 말로 바꾸기만 한다 — 숫자를 새로 만들지 않는다."""
    from engine import hub
    from engine.intent_router import _sanitize_talk

    facts = "\n".join(f"- {x}" for x in (result_data or []))
    if not facts:
        return None
    cap = find(cap_id) if cap_id else None
    prompt = (
        "너는 CCUT 편집실의 통역사다. 엔진이 일을 하고 작업 데이터를 돌려줬다.\n"
        "이것을 사용자가 알아들을 한국어 1~2문장으로 옮겨라.\n\n"
        f"[사용자가 부탁했던 말]\n{user_text}\n\n"
        + (f"[엔진이 한 일]\n{cap['say']}\n\n" if cap else "")
        + f"[엔진이 돌려준 작업 데이터]\n{facts}\n\n"
        "위 데이터에 있는 숫자만 쓴다. 없는 것을 지어내지 마라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=25, temperature=0.5,
                               model=hub.VOICE_MODEL)
        return _sanitize_talk(str(out.get("say") or "").strip()) or None
    except Exception as e:
        print(f"[DESK][WARN] 통역 실패: {e}")
        return None
