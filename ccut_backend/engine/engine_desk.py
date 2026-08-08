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
import concurrent.futures as _cf
import json
import re

from engine.house_talk import AI_NAME, AI_CALL  # noqa: F401

# ── 접수 가능한 엔진 능력 (코드 실측) ──────────────────────────────────
#   id      : 젬마가 고르는 이름
#   engine  : 실제 코드 경로(사람이 추적할 수 있게)
#   needs   : 젬마가 채워야 할 인자
#   scope   : 조각 하나(fragment) / 원고 전체(story) / 조회(read)
CAPABILITIES = [
    {
        "id": "trim_boundary",
        "ways": ['앞이 늘어져', '뒤가 길어', '말 없는 데 잘라줘', '여기 좀 다듬어줘'],
        "say": "조각의 앞이나 뒤 경계를 다듬는다 (말이 없는 구간을 덜어낸다)",
        "engine": "POST /edit-state (command_type=TRIM)",
        "needs": {"fragment": "대상 조각", "side": "start 또는 end"},
        "scope": "fragment",
    },
    {
        "id": "exclude_range",
        "ways": ['중간에 이 부분만 빼줘', '가운데 이 말만 지워줘'],
        "say": "조각 안의 특정 구간만 빼낸다",
        "engine": "POST /edit-state (command_type=EXCLUDE_RANGE)",
        "needs": {"fragment": "대상 조각"},
        "scope": "fragment",
    },
    {
        "id": "remove_scene",
        "ways": ['이 장면은 굳이 넣을 필요 없을 것 같아', '3번 장면 빼줘',
                 '거긴 없어도 될 것 같아', '그 장면 빼자'],
        "say": "장면 하나를 원고에서 뺀다 — 사용자가 장면을 가리킬 때. "
               "'이 장면'처럼 가리키면 바로 앞에서 이야기하던 장면이다",
        "engine": "engine.desk_hands (REMOVE, 비파괴)",
        "needs": {"scene_no": "몇 번 장면"},
        "scope": "story",
    },
    {
        "id": "remove_fragment",
        "ways": ['A60 빼줘', '이 조각 지워줘'],
        "say": "조각 하나를 통째로 뺀다 — 사용자가 조각 이름(A60 같은 것)으로 가리킬 때",
        "engine": "POST /edit-state (command_type=REMOVE)",
        "needs": {"fragment": "대상 조각 이름"},
        "scope": "fragment",
    },
    {
        "id": "restore_fragment",
        "ways": ['아까 거 되돌려줘', '원래대로 해줘', '취소해줘'],
        "say": "뺐거나 다듬은 것을 이전 값으로 되돌린다",
        "engine": "POST /edit-state (command_type=RESTORE)",
        "needs": {"fragment": "대상 조각"},
        "scope": "fragment",
    },
    {
        "id": "remove_ordinal",
        "ways": ['3번째 빼줘', '다섯 번째 조각 지워줘', '마지막 거 빼줘'],
        "say": "원고에서 몇 번째 조각을 뺀다 — 사용자가 순번(3번째 같은 것)으로 가리킬 때",
        "engine": "POST /revision/proposals (op=remove_ordinal)",
        "needs": {"index": "몇 번째인지 숫자 (1~40, 마지막이면 -1)"},
        "scope": "story",
    },
    {
        "id": "set_count",
        "ways": ['10개로 맞춰줘', '조각 수를 줄여줘', '스무 개만 남겨줘'],
        "say": "원고의 조각 개수를 맞춘다",
        "engine": "POST /revision/proposals (op=set_count)",
        "needs": {"count": "원하는 조각 수 (1~40)"},
        "scope": "story",
    },
    {
        "id": "keep_theme",
        "ways": ['먹는 장면만 남겨줘', '바다 나오는 것만 편집해줘',
                 '낚시하는 데만 쓰자', '요리하는 것만 있는 조각들로 만들어줘',
                 '다른 장면은 모두 빼줘'],
        "say": "어떤 소재가 나오는 조각만 남기고 나머지를 원고에서 뺀다 "
               "('~만', '~만 남기고 다 빼줘' 처럼 남길 것을 말할 때)",
        "engine": "engine.desk_hands (REMOVE, 비파괴)",
        "needs": {"theme": "남길 소재 낱말 (20자 이내)"},
        "scope": "story",
    },
    {
        "id": "remove_theme",
        "ways": ['바다 나오는 건 다 빼줘', '실내 장면 빼줘', '물놀이는 줄여줘'],
        "say": "어떤 주제·소재가 나오는 조각들을 원고에서 뺀다",
        "engine": "POST /revision/proposals (op=remove_theme)",
        "needs": {"theme": "뺄 소재 낱말 (20자 이내)"},
        "scope": "story",
    },
    {
        "id": "reorder_story",
        "ways": ['순서 바꿔줘', '이걸 앞으로 보내줘', '뒤로 옮겨줘'],
        "say": "원고에서 조각의 순서를 바꾼다",
        "engine": "POST /projects/{id}/state (ui_state.storyFragments 순서)",
        "needs": {"from_index": "옮길 조각의 현재 자리", "to_index": "옮겨 갈 자리"},
        "scope": "story",
    },
    {
        "id": "find_fragments",
        "ways": ['고양이 나온 장면 있어?', '바다 몇 개야?', '그 장면 찾아줘', '뭐가 찍혔어?'],
        "say": "말이나 장면으로 조각을 찾아본다",
        "engine": "engine.fragment_search.search",
        "needs": {"query": "찾을 말"},
        "scope": "read",
    },
    {
        "id": "look_scene",
        "ways": ['6번이 뭐야?', '그 장면 자세히 알려줘', '거기 무슨 얘기 나와?',
                 '어떤 장면인지 볼래', '내용 좀 보여줘'],
        "say": "장면 하나를 자세히 펴 본다 — 그 안의 대사와 보이는 것을 읽는다",
        "engine": "engine.ledger_groups (해당 묶음 상세)",
        "needs": {"scene_no": "몇 번 장면"},
        "scope": "read",
    },
    {
        "id": "fix_scene_label",
        "ways": ['이건 산이 아니라 바다야', '2번 장면 이름이 틀렸어', '장면 이름 고쳐줘', '이 장면은 잠수 장면이야', '그거 이름 바꿔줘'],
        "say": "장면 이름을 사용자가 말한 이름으로 고친다. 사용자가 어떤 장면이 "
               "무엇이라고 말하면(부정이 없어도) 그것은 이름을 고쳐 달라는 뜻이다 "
               "(예: '14번은 산이 아니라 바닷가 바위야', '7번은 낚시 장면이야')",
        "engine": "project_timeline kind=scene_label_fix (append-only)",
        "needs": {"scene_no": "장면 번호", "label": "사용자가 말한 올바른 이름"},
        "scope": "story",
    },
    {
        "id": "read_receipt",
        "ways": ['뺐나?', '방금 뭐 했어?', '했어?', '지금 몇 조각이야?',
                 '아까 그거 됐나?'],
        "say": "방금 무엇을 했는지, 지금 원고가 몇 조각인지 확인한다",
        "engine": "engine.desk_hands.recent_receipts (원장)",
        "needs": {},
        "scope": "read",
    },
    {
        "id": "read_sound_roles",
        "ways": ['소리가 어떻게 돼 있어?', '대사인지 배경인지 봐줘'],
        "say": "조각마다 소리가 대사인지 배경인지 조용한지 살펴본다",
        "engine": "GET /sound-role/{program_id}",
        "needs": {},
        "scope": "read",
    },
    {
        "id": "set_sound_role",
        "ways": ['이건 배경음으로 해줘', '여기는 대사로 표시해줘'],
        "say": "어떤 조각의 소리 성격을 대사·배경·조용함 중 하나로 고쳐 준다",
        "engine": "POST /sound-role/{program_id}",
        "needs": {"fragment": "대상 조각",
                  "role": "dialogue / background / silence 중 하나"},
        "scope": "fragment",
    },
]

# 엔진에 구조적으로 없는 일 — 영상·소리의 성질 자체를 바꾸는 것.
#   CCUT 은 '어디를 남기고 어디를 뺄지'를 다루는 편집실이라 이 계열은 손이 없다.
#   ★이 목록은 '아직 안 만든 것'이 아니라 '이 편집실이 하는 일이 아닌 것'이다.
NOT_HERE = [
    "자막 넣기·자막 수정",
    "색 보정·색감·색온도 바꾸기",
    "밝기·대비 조절",
    "소리 크기 조절·잡음 제거 (소리의 성격을 적어 두는 것은 되지만 소리 자체는 못 바꾼다)",
    "화면 효과·전환 효과 넣기",
    "속도 조절(빠르게·느리게, 2배속 같은 것)",
    "음악 넣기",
    # [NIGHT-1 2026-08-09 천 명의 밤] 결이 몰라서 "설정하겠습니다"라고 답한
    #   자리들 — 목록에 없던 게 아니라 안 보였다(아래 참조).
    "해상도·화질 바꾸기(1080p·4K 같은 것)",
    "프레임레이트 바꾸기(60fps 같은 것)",
]

# [2026-08-08 국장 지적 "이래서 틀에 가두면 안 된다"]
#   실화면: "14번 산은 산이 아니고 바닷가 바위야" → "제가 정확히 못 알아들었어요"
#   목록에 없다는 이유로 대화가 끝났다. 그런데 그건 못 할 일이 아니라
#   ★아무도 안 만들었을 뿐인 일이었다. 둘을 같은 '없는 일'로 묶은 것이 잘못이다.
#
#   개념서 §8: "불가능하다는 말로 대화를 끝내지 않는다."
#   그래서 목록 밖 요청을 벽이 아니라 문으로 만든다 —
#   할 수 있는 척하지 않되, 그 요구를 적어 두고 국장이 볼 수 있게 남긴다.
#   적힌 것이 쌓이면 그것이 다음에 만들 목록이 된다(틀이 사용자를 따라간다).
WISH_SAY = ("그건 아직 제가 못 해요. 다만 적어 뒀으니 만들 수 있는지 보겠습니다. "
            "지금 할 수 있는 일로 도와드릴까요?")


def _capability_lines(labels_hint=""):
    # [2026-08-08 국장 지시 "도구 사용설명"] 도구마다 '무엇을 하는지 · 어떤 말에
    #   쓰는지 · 무슨 값이 필요한지'를 한 줄로. 이건 답변 예시가 아니라 사용설명이다.
    #   (답변 예시를 넣었더니 젬마가 그 내용을 따라 했고, 빼면 도구를 안 잡았다.
    #    설명은 남기고 예시는 두지 않는 자리가 여기다.)
    lines = []
    for c in CAPABILITIES:
        say = c["say"].split(" — ")[0].split(" (예:")[0].strip()
        keys = ", ".join(c["needs"].keys())
        w = c.get("ways") or []
        when = f"  ← \"{w[0]}\" 같은 말" if w else ""
        lines.append(f"  {c['id']}({keys}): {say}{when}")
    return "\n".join(lines)


def _not_here_lines():
    return "\n".join(f"- {x}" for x in NOT_HERE)


def find(cap_id):
    for c in CAPABILITIES:
        if c["id"] == cap_id:
            return c
    return None


def _cap_vectors():
    """능력 설명을 벡터로 — 서버가 고르기 위한 재료. 프로세스당 1회."""
    global _CAP_VECS
    try:
        return _CAP_VECS
    except NameError:
        pass
    from engine import embedding_model as em
    vecs = []
    for c in CAPABILITIES:
        # 설명 한 줄만으로는 사람 말과 안 붙는다(실측: '장면 이름 고쳐줘' 0.355).
        # 사람이 할 법한 말 여러 각도를 함께 재고 그 중 가장 가까운 것을 쓴다.
        texts = [c["say"]] + list(c.get("ways") or [])
        vecs.append((c["id"], [em.encode_one(t) for t in texts]))
    globals()["_CAP_VECS"] = vecs
    return vecs


def match(want_text, floor=0.45):
    """사용자가 원하는 것(한 문장) → 능력 하나. 고르는 일은 서버가 한다.

    [2026-08-08 국장 지적 "왜 자유롭게 하지 않고 구속과 속박으로"]
      그동안 젬마에게 능력 12종·인자·규칙 2,500자를 주고 "JSON 으로 골라라"를
      시켰다. 그건 젬마가 못하는 일이다(행동 이름 고르기 6/6 실패, 실측).
      실제 사고: '2바다는 바다지만, 바다속 잠수장면이야' →
                 {group_no:14, label:'바닷가 바위'} (직전 대화를 되풀이)
      ★젬마는 이해만 한다. 고르는 일은 서버가 벡터로 한다 — 규칙이 아니라 계산이다.
      임베딩은 이미 있는 것을 쓴다(새 모델 0)."""
    if not (want_text or "").strip():
        return None, 0.0
    from engine import embedding_model as em
    import numpy as np
    q = em.encode_one(want_text)
    best, score = None, -1.0
    for cid, vs in _cap_vectors():
        s = max(float(np.dot(q, v)) for v in vs)
        if s > score:
            best, score = cid, s
    return (best if score >= floor else None), round(score, 3)


def _ask_tool(user_text, ctx="", world_lines=""):
    """도구만 고른다 — 말은 안 만든다. 격리 실측 10/10 이 나온 형태.

    말과 함께 물으면 도구 칸이 빈다. 그래서 이 물음에는 도구밖에 없다.
    """
    from engine import hub
    # ★'없음'도 고를 수 있는 항목으로 준다. null 로 비우라고만 하면 젬마는
    #   늘 무언가를 골랐다(실측: '고마워' → remove_scene, '자막 넣어줄 수 있나' →
    #   fix_scene_label). 젬마는 비우는 것보다 고르는 것을 잘한다 — 그러면
    #   고를 것을 주는 게 맞다.
    prompt = (
        "영상 편집실에서 쓸 수 있는 도구다. 사용자가 한 말에 가장 맞는 것을 "
        "하나 고르고, 필요한 값을 채워라.\n\n"
        "  talk: 인사·감사·잡담·감상이라 아무 도구도 필요 없다\n"
        # [NIGHT-1 2026-08-09] 전에는 [:5]로 잘라 보여줬다 — 그래서 목록에
        #   있던 "속도 조절"·"음악 넣기"가 안 보였고, 결이 몰라서 "2배속으로
        #   설정하겠습니다" 처럼 못 하는 일을 하겠다고 답했다. 다 보여준다.
        f"  not_here: {', '.join(NOT_HERE)} — 이 편집실에 손이 없는 일이다\n"
        + _capability_lines() + "\n"
        # 세계를 빼 보았다(미끼 가설). 오히려 '뺐나?' 가 깨져서 되돌렸다 —
        #   지금 몇 조각인지를 모르면 확인 요청을 확인으로 못 읽는다. 실측 3회로
        #   이 지점은 프롬프트로 안 잡힌다는 것이 드러났고, 남은 사고는 실행 문
        #   앞 검문으로 막는다(main.py LABEL-GROUND).
        + (f"[방금 나눈 이야기]\n{ctx}\n" if ctx else "")
        + (f"[지금 영상]\n{world_lines}\n" if world_lines else "")
        + f"\n[사용자가 한 말]\n{user_text}\n\n"
        "말한 것을 실제로 해주려면 어떤 도구가 필요한가. 가리키는 말('이 장면', "
        "'그거', '아까 그것')은 방금 나눈 이야기에서 무엇을 가리키는지 찾아 "
        "번호나 이름을 채워라.\n"
        '{"capability": 위에서 고른 이름, "args": {필요한 값}}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.2,
                               model=hub.VOICE_MODEL)
        return out if isinstance(out, dict) else {}
    except Exception as e:
        print(f"[DESK][WARN] 도구 선택 실패: {e}")
        return {}


def decide(user_text, world_lines="", recent_messages=None, project_id=""):
    """[2026-08-08 국장 지시 "모든 조정권을 젬마에게"]

    젬마가 듣고 · 분석하고 · 시스템을 확인하고 · 그 중에서 고르고 · 지시한다.
    실행만 안 한다.

    ★서버는 고르지 않는다. 서버는 국장 말을 알아듣지 못한다(임베딩 유사도일 뿐).
      앞 차수에서 서버가 고르게 했더니 '바다 나오는 장면 제거'를 fix_scene_label
      로 골랐다 — 뜻을 모르니 그렇게 된다.
    ★프롬프트에서 판단 규칙을 걷어냈다. 초기 실측에서 젬마는 능력 매핑을 9/10
      맞혔는데, 그 위에 규칙(없는일/아직/묻는말/시키는말/대화/모르겠음 …)을
      2,500자 쌓으면서 4/11까지 떨어졌다. 규칙이 젬마를 묶었다.
      남기는 것은 '무엇을 할 수 있는지'와 '무엇은 여기 없는지' 둘뿐이다.
    서버가 하는 일: 고른 것이 실재하는 능력인지, 값이 범위 안인지 확인(실행 전 안전)."""
    from engine import hub
    from engine.intent_router import _sanitize_talk

    # [2026-08-08] 직전 대화를 돌려준다 — 매 턴 처음 만난 사람이 되지 않게.
    #   한때 이것을 뺐다(판단 오염 3/8 vs 7/8). 그때는 프롬프트가 2,500자였고
    #   규칙표에 눌려 젬마가 직전 것을 되풀이했다. 안내서만 남은 지금 다시 넣고
    #   실측한다 — 나빠지면 그때 다시 판단한다.
    ctx = ""
    for m in (recent_messages or [])[-8:]:
        who = "사용자" if (m.get("sender") == "user") else "나"
        txt = str(m.get("text") or "")[:160]
        if txt:
            ctx += f"{who}: {txt}\n"
    # [2026-08-08 국장 지시 "젬마를 풀어준다"]
    #   안내서에는 세 가지만 적는다 — 이곳이 사용자에게 해주려는 일 / 사용자가
    #   어떤 상태인지 / 네 손에 있는 도구. 제약·금지·판단 분기표는 한 줄도 없다.
    #   무엇을 할지, 어떻게 말할지는 전부 젬마가 정한다.
    # [HOUSE-1 2026-08-08 국장 지시] CCUT 과 ★따로 논다★.
    #   세상의 모든 제품은 AI 가 그 제품을 대표하게 만든다. CCUT 은 반대다.
    #   결이는 CCUT 이 아니라 CCUT 에서 일하는 동료다. 단짝이지만 다른 사람이다.
    #   (직전까지 이 자리에 "너도 CCUT 이라고 부른다"가 있었다 — 정반대였다.)
    from engine import house_talk as _ht
    prompt = (
        f"너는 '{_ht.AI_NAME}'이다. 사람들은 너를 {_ht.AI_CALL}라고 부른다.\n"
        "여기는 CCUT 편집실이고, 너는 CCUT이 아니다 — CCUT에서 일하는 동료다.\n"
        "편집하는 손은 CCUT이 갖고 있다. 너는 사람의 말을 듣고 CCUT에게 시키고,\n"
        "CCUT이 한 일을 사람에게 전한다. 둘은 단짝이고 늘 붙어 있지만 한 사람은\n"
        "아니다. 그래서 CCUT 이야기를 할 때는 남 이야기하듯 한다 —\n"
        "\"CCUT이 …했어요\", \"제가 CCUT한테 …해 볼게요\", \"CCUT이 …라고 하네요\".\n\n"
        "[이곳이 하려는 일]\n"
        "혼자 영상을 만드는 사람이 하루 종일 찍어 온 것을 들고 온다.\n"
        "그 사람은 편집을 배운 적이 없고, 배우고 싶어하지도 않는다. 지쳐 있고,\n"
        "빨리 결과를 보고 싶어한다. 버튼을 찾아다니는 대신 너에게 말한다 —\n"
        "\"여기가 늘어져\", \"이 부분 어색해\", \"물속 장면만 쓰자\" 처럼.\n"
        "편집 기술은 CCUT이 갖고 있다. 너는 그 사람과 이야기하고, 무엇을 원하는지\n"
        "알아내고, 대신 해주는 쪽이다. 결과를 함께 보며 고쳐 나간다.\n\n"
        "[지금 이 사람의 영상]\n"
        + (world_lines + "\n" if world_lines else "(아직 없다)\n")
        + "\n[네 손에 있는 도구]\n"
        + _capability_lines() + "\n"
        + f"화면이나 소리의 성질 자체({', '.join(NOT_HERE)})는 이 편집실에\n"
          "손이 없어서 네가 대신 해줄 수 없다.\n"
        # [NIGHT-1 2026-08-09 천 명의 밤·국장 지시 "결을 소중히, 교육으로"]
        #   실측: "본사가 어디야?" 에 없는 주소를 지어냈고, "투자 받았어?" 에
        #   없는 사실을 단정했다. 모르면 지어내는 버릇을 막는 규칙을 세우는
        #   대신, 몰라도 괜찮다는 것을 알려준다 — 편하게 모른다고 해도 된다.
        + "CCUT이 회사로서 어떤지(사장이 누군지, 투자를 받았는지, 본사가\n"
          "어딘지 같은 것)는 너도 몰라도 된다. 아는 척하지 않고 모른다고\n"
          "편하게 말해도 괜찮다.\n\n"
        # 집에서 방금 있었던 일 — 알려만 준다. 말할지는 결이가 정한다.
        + _ht.lines(project_id)
        + (f"[지금까지 나눈 이야기]\n{ctx}\n" if ctx else "")
        + f"[사용자]\n{user_text}\n\n"
        # 예시에 '내용'을 넣지 않는다 — 넣었더니 젬마가 그 내용을 따라 했다
        #   ('고마워'에 "6번 집 조각을 빼드릴게요", 답에 JSON 조각 유출. 실측).
        #   형식만 알려주고 무엇을 말할지는 젬마가 정한다.
        "편하게 답해라.\n"
        '답 모양: {"say": 사용자에게 할 말}'
    )
    # ★[HANDS-1 2026-08-08] 말과 도구를 갈라 ★동시에★ 묻는다.
    #   실측: 하나의 JSON 에 say + capability + args 를 함께 담게 했더니
    #   대화가 자연스러워질수록 도구 칸이 비었다(36발화 중 15건 just_talk,
    #   '뺐나?' 조차 도구 없이 되물음). 젬마 4B 에게 한 번에 두 일은 무겁다.
    #   격리에서 도구만 물었을 때는 10/10 이었다 — 그 형태를 그대로 쓴다.
    #   순차로 두 번 부르면 11.8초가 됐다(실측). 그래서 병렬이다.
    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as ex:
            f_say = ex.submit(hub._ollama_json, prompt, timeout=30,
                              temperature=0.4, model=hub.VOICE_MODEL)
            f_cap = ex.submit(_ask_tool, user_text, ctx, world_lines)
            out = f_say.result() or {}
            picked = f_cap.result() or {}
    except Exception as e:
        print(f"[DESK][WARN] 판단 실패: {e}")
        return None
    out["capability"] = picked.get("capability")
    out["args"] = picked.get("args")

    cap = out.get("capability")
    cap = None if cap in (None, "", "null", "none", "None") else str(cap).strip()
    if cap == "talk":
        cap, out["reason"] = None, "대화"
    elif cap == "not_here":
        cap, out["reason"] = None, "없는 일"
    if cap and not find(cap):
        print(f"[DESK][WARN] 없는 능력 {cap!r} → 적어만 둔다")
        cap = None
        out["reason"] = "아직"
    args = out.get("args") if isinstance(out.get("args"), dict) else {}
    # 남긴 검문은 둘뿐이다 — 사용자가 말하지 않은 조각을 집는 것(실측 사고)과
    # 내부 id 가 화면에 새는 것. 나머지 규칙은 프롬프트에서 걷어냈다.
    _f = str(args.get("fragment") or "").strip()
    if _f and _f.upper() not in (user_text or "").upper():
        args = {k: v for k, v in args.items() if k != "fragment"}
    say = _sanitize_talk(str(out.get("say") or "").strip()) or ""
    # 내부 id 가 섞인 문장은 그 문장만 통째로 버린다. 낱말만 지우면
    #   '3번째 조각을 빼드릴게요. 사용하겠습니다.' 같은 잔재가 남는다(실측).
    if any(c["id"] in say for c in CAPABILITIES):
        keep = [s for s in re.split(r"(?<=[.!?])\s+", say)
                if not any(c["id"] in s for c in CAPABILITIES)]
        say = " ".join(keep).strip()
    return {"cap": cap, "args": args, "say": re.sub(r"\s{2,}", " ", say).strip(),
            "reason": str(out.get("reason") or "").strip()}


def say_for(cap_id, args, user_text):
    """젬마가 say 를 비웠을 때 대신 할 말 — 사람 말로.

    [2026-08-08] 예전엔 능력 설명문을 그대로 썼다. 그래서 국장 화면에
    '조각 안의 특정 구간만 빼낸다, 해볼까요?' 같은 내부 문장이 나갔다.
    설명문은 나와 엔진 사이의 말이지 사용자에게 할 말이 아니다."""
    from engine import hub
    from engine.intent_router import _sanitize_talk
    cap = find(cap_id)
    if not cap:
        return None
    what = cap["say"].split(" — ")[0].split("(")[0].strip()
    need = [k for k in (cap.get("needs") or {}) if not args.get(k)]
    prompt = (
        "너는 CCUT 편집실의 동료다. 사용자에게 할 말 한 문장만 만든다.\n"
        f"사용자가 한 말: \"{(user_text or '')[:100]}\"\n"
        f"내가 하려는 일: {what}\n"
        + (f"아직 모르는 것: {', '.join(need)}\n" if need else "")
        + "모르는 것이 있으면 그것만 자연스럽게 묻고, 없으면 해도 될지 묻는다.\n"
        "영어 낱말이나 내부 용어를 쓰지 마라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5,
                               model=hub.VOICE_MODEL)
        s = _sanitize_talk(str(out.get("say") or "").strip())
        if s:
            return s
    except Exception as e:
        print(f"[DESK][WARN] 확인 문장 실패: {e}")
    return f"{what}, 해볼까요?"


def understand(user_text, world_lines="", recent_messages=None):
    """젬마는 이해만 한다 — 사용자가 원하는 것을 한 문장으로.

    능력 목록도, 판단 규칙도 주지 않는다. 자유롭게 듣고 자유롭게 말한다."""
    from engine import hub
    from engine.intent_router import _sanitize_talk

    ctx = ""
    for m in (recent_messages or [])[-4:]:
        who = "사용자" if (m.get("sender") == "user") else "나"
        txt = str(m.get("text") or "")[:80]
        if txt:
            ctx += f"{who}: {txt}\n"
    prompt = (
        "너는 CCUT 영상 편집실의 동료다. 사용자의 말을 듣고 두 가지만 한다.\n"
        "1) 사용자가 지금 원하는 것을 한 문장으로 적는다(want).\n"
        "   편집 부탁이 아니면 want 는 빈 문자열로 둔다.\n"
        "2) 사용자에게 할 말을 한다(say).\n\n"
        + (f"[지금 이 이야기]\n{world_lines}\n\n" if world_lines else "")
        + (f"[최근 대화]\n{ctx}\n" if ctx else "")
        + f"[사용자의 말]\n{user_text}\n\n"
        "지난 대화가 아니라 ★방금 한 말★을 보고 판단한다.\n"
        'JSON만 출력: {"want":"...","say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=25, temperature=0.4,
                               model=hub.VOICE_MODEL)
    except Exception as e:
        print(f"[DESK][WARN] 이해 실패: {e}")
        return None
    return {
        "want": str(out.get("want") or "").strip(),
        "say": _sanitize_talk(str(out.get("say") or "").strip()) or "",
    }


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
        "★목록에 없는 부탁이라고 해서 '못 한다'로 끝내지 마라. 둘을 가른다:\n"
        "  - 위 [없는 일]에 해당한다 → reason: \"없는 일\" (영상·소리의 성질을 "
        "바꾸는 것은 이 편집실이 하는 일이 아니다)\n"
        "  - 목록에도 없고 [없는 일]도 아니다 → reason: \"아직\" "
        "(만들면 될 수 있는 일이다. 적어 두겠다고 말한다)\n"
        "★먼저 이것이 묻는 말인지 시키는 말인지 가른다. "
        "'있어?·뭐야?·몇 개야?·어떻게 돼?'처럼 묻는 말은 편집 지시가 아니다 — "
        "찾아보는 것(find_fragments)이거나 그냥 대화다. 묻는 말을 빼거나 고치는 "
        "일로 읽으면 사용자의 이야기가 망가진다.\n"
        "- 편집을 부탁한 것이고 위 목록에 그 일이 있으면 → capability 에 그 id\n"
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


def scene_detail(scenes, scene_no, fixes=None):
    """[2026-08-08] 젬마가 장면 하나를 펴 볼 때 받는 것 — 그 묶음의 실제 내용.

    국장 실화면: '6번 집 조각? 이 뭐지? 상세하게 알려줄 수 있나?' 에
    짧은 목록만 있어 되물었다. 도구를 쥐면 안을 볼 수 있어야 한다."""
    from engine import ledger_groups as _lg
    g = next((x for x in (scenes or []) if x["group_no"] == scene_no), None)
    if not g:
        return None
    t0, t1 = g["start_ms"] / 1000.0, g["end_ms"] / 1000.0
    lines = [
        f"{g['group_no']}번 장면 — {_lg.scene_label(g, fixes)}",
        f"{int(t0 // 60)}분{int(t0 % 60):02d}초 ~ {int(t1 // 60)}분{int(t1 % 60):02d}초, "
        f"조각 {g['item_count']}개",
    ]
    if g.get("top_tags"):
        lines.append("보이는 것: " + ", ".join(g["top_tags"]))
    if g.get("dialogue_head"):
        lines.append(f"들리는 말: \"{g['dialogue_head']}\"")
    return "\n".join(lines)


def look(user_text, scene_lines, recent_messages=None, project_id=""):
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

    # ★이 함수가 화면에 나가는 마지막 말을 만든다. 여기에 정체성과 집안일이
    #   없으면 decide 에 아무리 적어도 사라진다(실측: '넌 누구야?' 에
    #   "저는 CCUT 편집실의 통역사입니다" — 이름도 집안일도 안 나왔다).
    from engine import house_talk as _ht
    prompt = (
        f"너는 '{AI_NAME}'이다. 사람들은 너를 {AI_CALL}라고 부른다.\n"
        "너는 CCUT이 아니다 — CCUT 편집실에서 일하는 동료다. 편집하는 손은\n"
        "CCUT이 갖고 있고, 너는 CCUT과 단짝이지만 한 사람은 아니다.\n"
        "CCUT 이야기를 할 때는 남 이야기하듯 한다 — \"CCUT이 …했어요\",\n"
        "\"제가 CCUT한테 …해 볼게요\".\n\n"
        "아래는 CCUT이 이 영상을 장면 단위로 훑어 준 지도다. **여기 적힌 것만**\n"
        "사실이다. 적혀 있지 않은 것은 '없다' 또는 '확인되지 않는다'고 말한다. "
        "조각 번호를 지어내지 마라.\n\n"
        f"[장면 지도]\n{scene_lines}\n\n"
        + (_ht.lines(project_id) + "\n" if project_id else "")
        + f"[사용자의 물음]\n{user_text}\n\n"
        # 지도는 자료지 화제가 아니다 — '넌 누구야?' 에도 장면 이야기를 붙이던 자리.
        "물음이 영상 내용과 상관없으면 장면 이야기를 굳이 꺼내지 않아도 된다.\n"
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


def say_done(facts, user_text, recent_messages=None):
    """한 일을 젬마가 국장에게 말한다 — 되돌아오는 숨.

    ★서버가 사실을 만들고 젬마가 문장을 만든다. 반대로 하면 젬마가 숫자를
      지어낸다(실측: 뺀 적 없는 조각을 뺐다고 말했다).
      그래서 숫자는 아래 목록에 있는 것만 통과시킨다.
    """
    from engine import hub
    from engine.intent_router import _sanitize_talk
    if not facts.get("ok"):
        why = facts.get("why") or "지금은 못 한다"
        return f"CCUT이 그건 못 한대요 — {why}. 어떻게 할까요?"

    if facts.get("receipts") is not None:
        rs = facts["receipts"]
        if facts.get("nothing"):
            return f"아직 손댄 건 없어요. 지금 {facts['after']}조각입니다."
        head = rs[0]
        fact_line = (f"방금 한 일: {head['what']} "
                     f"({head['before_count']}조각 → {head['after_count']}조각)")
        allow = [str(head["before_count"]), str(head["after_count"])]
        server = (f"네, CCUT이 {head['what']} 지금 {head['after_count']}조각입니다.")
    else:
        fact_line = (f"방금 한 일: {facts['what']} "
                     f"({facts['before']}조각 → {facts['after']}조각)")
        allow = [str(facts["before"]), str(facts["after"])]
        server = (f"CCUT이 {facts['what']} {facts['before']}조각 → "
                  f"{facts['after']}조각이에요.")

    prompt = (
        f"너는 '{AI_NAME}'이고 CCUT 편집실에서 일한다. 너는 CCUT이 아니다.\n"
        "편집하는 손은 CCUT이 갖고 있고, 너는 CCUT에게 시킨 쪽이다.\n"
        "방금 CCUT이 해 놓은 일을 사용자에게 전한다 — 남 이야기하듯,\n"
        "\"CCUT이 …했어요\", \"제가 CCUT한테 시켜서 …됐어요\" 처럼.\n"
        f"사용자가 한 말: \"{(user_text or '')[:100]}\"\n"
        f"{fact_line}\n"
        "이미 다 한 상태다 — 해도 되는지 묻지 마라. 위 숫자를 그대로 넣어 "
        "1~2문장으로 알리고, 마음에 안 들면 되돌릴 수 있다는 걸 알려라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5,
                               model=hub.VOICE_MODEL)
        say = _sanitize_talk(str(out.get("say") or "").strip())
        nums = set(re.findall(r"\d+", say or ""))
        if say and nums <= set(allow):
            return say
        if say:
            print(f"[DESK][NUM-GUARD] 없는 숫자 — 서버 문장으로: {say[:50]!r}")
    except Exception as e:
        print(f"[DESK][WARN] 보고 문장 실패: {e}")
    return server
