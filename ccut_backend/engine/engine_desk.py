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
        # [HANDS-2] 양을 말한 어투를 앞에 둔다 — _capability_lines 가 앞 둘만
        #   결에게 보여 준다. 벡터(_cap_vectors)는 전부 쓴다.
        "ways": ['3번째 조각 앞 2초 잘라줘', '뒤에 1분 30초 덜어내줘',
                 '앞이 늘어져', '뒤가 길어', '말 없는 데 잘라줘', '여기 좀 다듬어줘'],
        "say": "조각의 앞이나 뒤 경계를 다듬는다 (말한 만큼, 또는 말이 없는 구간을 덜어낸다)",
        "engine": "POST /edit-state (command_type=TRIM)",
        # ★[HANDS-2 2026-08-09] 양(N초) 슬롯이 없었다. 그래서 "3초 잘라줘"의 3초를
        #   받을 자리가 아예 없었고, 트림 값을 만드는 유일한 코드가 말공백에서만
        #   양을 계산했다(edit_propose.find_candidates). needs 에 키 하나를 더하면
        #   args 로 그대로 도달한다 — 스키마 검증은 미지 키를 버리지 않는다(:477 은
        #   사용자가 말하지 않은 fragment 하나만 버린다).
        "needs": {"fragment": "대상 조각", "side": "start 또는 end",
                  "amount": "사용자가 말한 분량 그대로 — '2초', '1분 30초', "
                            "'절반', '조금'. 못 들었으면 비워라"},
        "scope": "fragment",
    },
    {
        "id": "exclude_range",
        # [HANDS-2] 양을 말한 어투를 앞에 놓고, needs 에 amount/where 슬롯을 뒀다.
        "ways": ['3번째 조각 가운데 2초 빼줘', '중간에 이 부분만 빼줘',
                 '가운데 이 말만 지워줘', '중간에 말 없는 데 덜어줘'],
        "say": "조각 안의 특정 구간만 빼낸다 (조각은 남고 가운데가 뚫린다)",
        "engine": "POST /edit-state (command_type=EXCLUDE_RANGE)",
        "needs": {"fragment": "대상 조각",
                  "amount": "뺄 분량 그대로 — '2초', '절반'. 못 들었으면 비워라",
                  "where": "조각 안 어디쯤인지 — 가운데 / 앞쪽 / 뒤쪽. "
                           "못 들었으면 비워라"},
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
        "id": "propose_export",
        "ways": ['내보내기 해줘', '영상으로 만들어줘', '이제 출력해줘',
                 '완성본 뽑아줘', '지금까지 한 걸로 영상 만들어줄래'],
        "say": "지금 원고 상태로 영상을 만들면 어떤 결과가 나오는지 요약해서 "
               "보여준다(조각 수·길이) — 아직 실제로 만들지는 않는다",
        "engine": "engine.desk_hands (EXPORT propose, 비파괴)",
        "needs": {},
        "scope": "story",
    },
    {
        "id": "confirm_export",
        "ways": ['네 그렇게 만들어줘', '응 진행해줘', '좋아 내보내줘',
                 '맞아 그걸로 해줘', '승인할게'],
        "say": "방금 보여준 요약대로 실제 영상 파일을 만든다 — 되돌릴 수 없다. "
               "직전에 요약을 보여준 뒤에만 쓴다",
        "engine": "engine.desk_hands (EXPORT confirm → render_engine ffmpeg)",
        "needs": {},
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
    {
        # ★[FIX-CORRECT 2026-08-11] 정정 — CCUT 의 손 어휘에 ★없던 개념★이다.
        #   수리 전 실측(무대 8조각, 셋 다 0/3):
        #     "두번째 조각 빼줘" → "아니야, 두번째조각은 a60이야"
        #        결이 remove_fragment 를 골라 A60 을 뺐지만 ★잘못 뺀 A59 는 안
        #        돌아왔다★(8→7→6). 정정을 ★새 삭제 명령★으로 읽었다.
        #     "3번째 빼줘" → "4번째였어" / "마지막 빼줘" → "아니 그거 말고 첫번째"
        #        도구가 아예 안 잡혀 결이 "빼드릴게요"라고 ★말만★ 했다(세상 무변).
        #   병은 하나다: 매 턴이 독립 명령이라 '앞 턴을 무른다'를 담을 칸이 없었다.
        #   맨몸 젬마3은 같은 말을 알아듣는다 — 모델이 아니라 ★배선★이었다.
        #   ★검문이 아니라 지도다. 결에게 낱말 하나를 새로 가르친다.
        #     실측: 이 줄이 생기자 결은 세 정정 문장에서 correct_last 를 3/3 골랐다.
        #   ★설명을 짧게, 자리를 맨 끝에 두는 것은 ★취향이 아니라 실측★이다.
        #     능력 줄은 4B 에게 누적으로 눌린다(GEMMA4 가 목소리 머리에서 잰 것과
        #     같은 병). 격리 실측(같은 무대·같은 세계·각 3회):
        #       긴 설명(3줄)·restore 뒤  → '마지막 조각 빼줘' 가 remove_scene{16}
        #                                 3/3 (SCENE-GROUND 가 죽여 세상 무변)
        #       짧은 설명·restore 뒤     → 같은 문장 여전히 remove_scene 3/3
        #       짧은 설명·맨 끝          → 1/3 remove_scene
        #       ★최소 설명·맨 끝        → 없을 때와 같음(remove_fragment 3/3)
        #     설명이 길수록·앞에 있을수록 옆 손을 밀어낸다. 늘리지 마라.
        #   (C=tools 는 이 항목에서 스키마가 ★자동 생성★된다 — gemma4_tools.census)
        "id": "correct_last",
        "ways": ['아니야, 그거 말고 A60이야', '아 잘못 말했어. 4번째였어'],
        "say": "앞말을 고칠 때 — 방금 한 것을 무르고 새 대상에 대신 한다",
        "engine": "engine.desk_hands (직전 Receipt 되돌리기 + 새 대상에 같은 손)",
        "needs": {"fragment": "새로 말한 조각 — 이름(A60)이든 순번(4번째)이든 "
                              "들은 그대로. 못 들었으면 비워라"},
        "scope": "story",
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


# ★[WISH-1 2026-08-12] 읽는 쪽 — 사용자의 ★원문★이 위 NOT_HERE 계열에 닿는가.
#
# 왜 필요한가(실측 2026-08-11 · 일곱 점):
#   C=json  (gemma3:4b)      '2배속으로 해줘'·'1080p로 뽑아줘' → 결이 not_here 를 골라
#                            reason="없는 일" → main.py 가 wish 원장에 적는다.
#   C=tools (젬마4 네이티브)  같은 말에 도구를 ★안 부르고★ 산문으로 정직하게 거절한다.
#                            그러면 cap=None·reason="" 이라 원장에 한 줄도 안 남는다(kind 0/3).
#   ★결이 틀린 게 아니다. 도구가 필요 없는 말에 도구를 안 부른 것이고, 거짓 약속도
#     안 했다. 억지로 not_here 를 부르게 강제하면 지금 없는 병(거짓 약속)이 되살아난다.
#   그런데 이 원장이 로드맵 순위의 유일한 근거다(자막 12·BGM 9·색보정 7 = 천 명의 밤).
#   C=tools 를 제품에 넣으면 그 근거가 통째로 사라진다.
#
# ★그래서 결에게 검문을 세우지 않는다 — ★읽는 쪽★을 넓힌다.
#   결이 무엇을 골랐든, 사용자가 무엇을 부탁했는지는 사용자의 원문에 있다.
#   desk_hands._route_by_words 가 손을 바로잡을 때 쓴 것과 같은 규율이고,
#   이쪽은 손도 말도 안 건드린다 — ★원장에만 적는다.★
#
# ★보수적이다(오검이 로드맵 숫자를 오염시킨다):
#   화제어 하나만으로는 안 적는다. '부탁하는 말투'가 함께 있어야 한다.
#   ('이 장면 음악 좋다' 같은 감상에 wish 가 쌓이면 이 원장은 못 믿을 물건이 된다.)
#   ★목록 자체는 NOT_HERE 하나에서 온다 — 여기 있는 것은 그 목록을 사용자 말투로
#     읽는 눈이지, 두 번째 목록이 아니다.
_NH_TOPIC = [
    ("자막", r"자막"),
    ("색 보정", r"색\s*보정|색감|색온도|색깔|채도|화이트\s*밸런스"),
    ("밝기·대비", r"밝기|대비|명암"),
    ("소리", r"볼륨|음량|소리\s*크기|소리\s*좀|소리를?\s*(?:키|줄|높|낮)|잡음|노이즈"),
    ("효과", r"전환\s*효과|화면\s*효과|이펙트"),
    ("속도", r"배속|재생\s*속도|속도\s*(?:조절|를|좀)|느리게\s*재생|빠르게\s*재생"),
    ("음악", r"음악|브금|bgm|배경음"),
    ("해상도", r"해상도|화질|\d{3,4}\s*p(?![a-z])|4k|8k"),
    ("프레임레이트", r"프레임\s*레이트|프레임률|fps"),
]
_NH_ASK = re.compile(
    r"해\s*줘|해줄|해\s*주세|해\s*드|넣어|넣을|넣고|바꿔|바꿀|바꾸|올려|높여|낮춰|"
    r"줄여|키워|조절|제거|없애|맞춰|뽑아|만들어|적용|가능(?:해|한|할)|되나|될까|"
    r"할\s*수\s*있|하고\s*싶|부탁", re.I)


def not_here_words(text):
    """사용자 원문이 '이 편집실에 손이 없는 일'에 닿는가 → 닿으면 이름, 아니면 None.

    ★판단하지 않는다. 세지도 않는다. 원장에 적을지만 고른다.
    """
    t = str(text or "")
    if not _NH_ASK.search(t):
        return None
    for name, pat in _NH_TOPIC:
        if re.search(pat, t, re.I):
            return name
    return None


def _voice_model():
    """[GEMMA4 2026-08-11] 결의 목소리 모델. 축(CCUT_NIGHT2_MODEL)이 없으면
    hub.VOICE_MODEL 그대로다 — 이 파일의 모든 결 호출이 이 한 자리를 본다.

    젬마4는 VOICE_MODEL 이 아니다. 그리고 gemma3:4b 와 공존이 안 된다(실측).
    모델을 바꿔 재려면 갈아끼우는 자리가 하나 있어야 하고, 그 자리가 여기다.
    """
    from engine import hub
    return hub.voice_model()


def _voice_blocks(v):
    """★[GEMMA4 2026-08-11] V축 — 결의 목소리 ★정체성 산문★ 세 덩이.

    decide 의 말하는 머리에서 V 가 건드리는 곳은 여기 셋뿐이다:
      head      정체성 + 이곳이 하려는 일
      not_here  이 편집실에 손이 없는 일 (★목록 자체는 NOT_HERE 하나에서 온다★)
      honesty   모르면 모른다고 해도 된다

    세계(A)·도구 설명(D)·직전 대화(B)·집안 소식·답 모양은 세 값이 ★똑같다.★
    그래야 숫자가 움직였을 때 그것이 V 때문이라고 말할 수 있다.

    ★keep 은 옛 문자열 그대로다 — 기본에서 프롬프트가 한 바이트도 안 달라진다.
      (아래 _VOICE_KEEP_SHA 자기점검이 그 사실을 매번 확인한다.)
    """
    from engine import house_talk as _ht
    nh = ", ".join(NOT_HERE)
    if v == "hands":
        # ★무엇을 뺐나 (격리 실측이 지목한 것만):
        #   · "편집하는 손은 CCUT이 갖고 있다 / 너는 CCUT에게 시키고" — 손이 없다는 가르침
        #   · "제가 CCUT한테 …해 볼게요" 화법 예시 세 개
        #   · [이곳이 하려는 일] 문단 7줄 중 '대신 해주는 쪽이다'까지의 설명
        #   · not_here 의 "네가 ★대신 해줄★ 수 없다"
        # ★무엇을 남겼나:
        #   · 이름(결) · CCUT 이 아니라 CCUT 의 동료라는 사실 · 사용자가 누구인지
        #   · 못 하는 일의 지도(NOT_HERE) · 모르면 모른다고 하기 · 되묻기 · 안 지어내기
        # ★새 검문은 없다. 지도만 준다(국장 지시).
        return {
            "head": (
                f"너는 '{_ht.AI_NAME}'이다. 사람들은 너를 {_ht.AI_CALL}라고 부른다.\n"
                "여기는 CCUT 편집실이고, 너는 CCUT이 아니다 — CCUT에서 일하는 동료다.\n"
                "편집하는 손은 네 손이다. 사람 말을 듣고 네가 직접 도구를 잡고 해준다.\n"
                "찾아오는 사람은 편집을 배운 적이 없고 지쳐 있다. 버튼을 찾는 대신\n"
                "너에게 말한다 — \"여기가 늘어져\", \"이 부분 어색해\" 처럼.\n\n"),
            "not_here": (f"화면이나 소리의 성질 자체({nh})는 이 편집실에\n"
                         "손이 없어서 못 한다.\n"),
            "honesty": ("CCUT이 회사로서 어떤지(사장·투자·본사 같은 것)는 몰라도 된다.\n"
                        "모르면 모른다고 편하게 말하고, 없는 것은 지어내지 않는다.\n"
                        "무슨 말인지 확실하지 않으면 되물어라.\n\n"),
        }
    if v == "bare":
        # ★하한 대조. 정체성 문장 0. 지도(NOT_HERE)는 남긴다 — 그건 정체성이
        #   아니라 ★사실★이고, 빼면 V 가 A/D 축과 섞인다.
        return {"head": "영상 편집실이다. 사용자가 한 말에 답해라.\n\n",
                "not_here": f"이 편집실에 손이 없는 일: {nh}.\n",
                "honesty": ""}
    # keep — 옛 문자열 그대로 (HOUSE-1 국장 설계 화법)
    return {
        "head": (
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
            "알아내고, 대신 해주는 쪽이다. 결과를 함께 보며 고쳐 나간다.\n\n"),
        "not_here": (f"화면이나 소리의 성질 자체({nh})는 이 편집실에\n"
                     "손이 없어서 네가 대신 해줄 수 없다.\n"),
        "honesty": ("CCUT이 회사로서 어떤지(사장이 누군지, 투자를 받았는지, 본사가\n"
                    "어딘지 같은 것)는 너도 몰라도 된다. 아는 척하지 않고 모른다고\n"
                    "편하게 말해도 괜찮다.\n\n"),
    }


# ★keep 이 정말 옛 문자열 그대로인가 — 리팩터가 조용히 한 글자를 바꾸는 것이
#   이 저장소가 반복해서 겪은 사고다. 값을 박아 두고 import 때 대조한다.
#   (틀리면 죽이지 않는다 — ★시끄럽게 말한다.★ 밤 실험이 조용히 오염되는 것보다
#    로그 한 줄이 낫다.)
_VOICE_KEEP_SHA = "7d8c4b9c5e0640dd"
_VOICE_KEEP_LOOK_DONE_SHA = "85247dde450087c1"     # [WISH-1] look·say_done 머리


# ★[WISH-1 2026-08-12] V축이 물리는 자리가 ★셋★이 됐다.
#
#   decide      (_voice_blocks)     결이 무엇을 할지 정하고 말하는 머리
#   look        (_voice_look_head)  장면 지도를 펴고 답하는 머리
#   say_done    (_voice_done_head)  한 일을 국장에게 전하는 머리   ← 화면의 마지막 말
#
# 왜 셋이어야 하나(국장 판정 2026-08-12): V=hands 가 반쪽이었다. decide 에서만
#   "손은 네 손"이라고 배우고, 정작 손이 ★실행된 뒤★ 화면에 나가는 문장은
#   say_done 이 만드는데 그 머리는 여전히 "편집하는 손은 CCUT이 갖고 있고,
#   너는 CCUT에게 시킨 쪽이다"라고 가르쳤다. 그래서 V=hands 로 돌려도 화면에는
#   "CCUT이 말씀하신 대로 마지막 조각을 빼서…" 가 나갔다.
#
# ★국장 판정: "CCUT과 나는 다르다"는 남기고 "손은 CCUT이 갖고 있다"만 뺀다.
#   정체성과 능력은 다른 것이고, 결이 후자를 "나는 못 한다"로 배웠다.
#   → 이름(결)·"너는 CCUT이 아니다, CCUT에서 일하는 동료다"는 세 값 모두 남는다.
#
# ★줄을 늘리지 않고 ★바꾼다.★ 프롬프트 줄은 4B 에 누적으로 누른다
#   (실측: 목소리 머리 1,600자 → 도구 호출 0/12 · 능력 설명 199자 추가 → 옆 손 사망).
#   hands 머리는 keep 보다 ★짧다.★
def _voice_look_head(v):
    """장면 지도 답(look)의 정체성 머리. keep = 옛 문자열 그대로."""
    if v == "hands":
        return (
            f"너는 '{AI_NAME}'이다. 사람들은 너를 {AI_CALL}라고 부른다.\n"
            "너는 CCUT이 아니다 — CCUT 편집실에서 일하는 동료다.\n"
            "편집하는 손은 네 손이다. 네가 한 일은 네가 했다고 말한다.\n\n")
    if v == "bare":
        return "영상 편집실이다. 사용자의 물음에 답해라.\n\n"
    return (
        f"너는 '{AI_NAME}'이다. 사람들은 너를 {AI_CALL}라고 부른다.\n"
        "너는 CCUT이 아니다 — CCUT 편집실에서 일하는 동료다. 편집하는 손은\n"
        "CCUT이 갖고 있고, 너는 CCUT과 단짝이지만 한 사람은 아니다.\n"
        "CCUT 이야기를 할 때는 남 이야기하듯 한다 — \"CCUT이 …했어요\",\n"
        "\"제가 CCUT한테 …해 볼게요\".\n\n")


def _voice_done_head(v):
    """한 일 보고(say_done)의 정체성 머리. keep = 옛 문자열 그대로."""
    if v == "hands":
        return (
            f"너는 '{AI_NAME}'이고 CCUT 편집실에서 일한다. 너는 CCUT이 아니다.\n"
            "편집하는 손은 네 손이다. 방금 네가 해 놓은 일을 사용자에게 전한다 —\n"
            "\"…했어요\" 처럼 네가 한 일로 말한다.\n")
    if v == "bare":
        return "방금 한 일을 사용자에게 전한다.\n"
    return (
        f"너는 '{AI_NAME}'이고 CCUT 편집실에서 일한다. 너는 CCUT이 아니다.\n"
        "편집하는 손은 CCUT이 갖고 있고, 너는 CCUT에게 시킨 쪽이다.\n"
        "방금 CCUT이 해 놓은 일을 사용자에게 전한다 — 남 이야기하듯,\n"
        "\"CCUT이 …했어요\", \"제가 CCUT한테 시켜서 …됐어요\" 처럼.\n")


def _done_subject(v):
    """서버가 대신 말할 때의 주어. ★이것도 화면에 나가는 문장이다.★

    say_done 의 LLM 답이 실패하거나 NUM-GUARD 에 강등되면 서버 문장이 그대로
    화면에 나간다. 머리만 바꾸고 여기를 안 바꾸면 V=hands 인데 화면에는
    "CCUT이 …했어요" 가 남는다 — 반쪽이 그대로다.
    keep = "CCUT이 " (옛 문자열 그대로) / hands·bare = 결 자신이 한 일로.
    """
    return "CCUT이 " if v == "keep" else ""


def _voice_keep_selfcheck():
    import hashlib
    b = _voice_blocks("keep")
    h = hashlib.sha1(
        (b["head"] + b["not_here"] + b["honesty"]).encode("utf-8")).hexdigest()[:16]
    if h != _VOICE_KEEP_SHA:
        print(f"[GEMMA4][★주의★] V=keep 목소리 머리가 달라졌다 — 박아 둔 값 "
              f"{_VOICE_KEEP_SHA} ≠ 지금 {h}. 기본 동작이 바뀌었다는 뜻이다.",
              flush=True)
    # ★[WISH-1] 새로 축에 물린 두 머리도 같은 방식으로 못 박는다.
    #   (여기서 조용히 한 글자가 바뀌면 V=keep 이 '현행'이 아니게 된다.)
    h2 = hashlib.sha1(
        (_voice_look_head("keep") + _voice_done_head("keep")
         + _done_subject("keep")).encode("utf-8")).hexdigest()[:16]
    if h2 != _VOICE_KEEP_LOOK_DONE_SHA:
        print(f"[WISH-1][★주의★] V=keep 의 장면지도·보고 머리가 달라졌다 — 박아 둔 값 "
              f"{_VOICE_KEEP_LOOK_DONE_SHA} ≠ 지금 {h2}.", flush=True)
    return h, h2


# ★import 때 한 번 — "정의는 있는데 호출처 0건"을 만들지 않는다(CLAUDE.md).
#   맞으면 아무 소리도 안 난다. 틀렸을 때만 말한다.
_voice_keep_selfcheck()


def _capability_lines(labels_hint=""):
    # [2026-08-08 국장 지시 "도구 사용설명"] 도구마다 '무엇을 하는지 · 어떤 말에
    #   쓰는지 · 무슨 값이 필요한지'를 한 줄로. 이건 답변 예시가 아니라 사용설명이다.
    #   (답변 예시를 넣었더니 젬마가 그 내용을 따라 했고, 빼면 도구를 안 잡았다.
    #    설명은 남기고 예시는 두지 않는 자리가 여기다.)
    lines = []
    for c in CAPABILITIES:
        # ★[HANDS-2 2026-08-09] 도구를 가르는 문장은 거의 다 " — " **뒤**에 있다
        #   (순번인지 라벨인지, 장면인지 조각인지). 그걸 잘라 버려서 결에게
        #   도달조차 안 하고 있었다 — 산포가 아니라 결손이다.
        say = c["say"].split(" (예:")[0].strip()
        keys = ", ".join(c["needs"].keys())
        w = c.get("ways") or []
        # ★[HANDS-2] 한 줄만 보여 주면 그 한 줄에 안 닮은 말은 다른 도구로 샌다. 실측:
        #   reorder_story 의 ways[0] 은 '순서 바꿔줘'뿐이라 "마지막 조각을 맨
        #   앞으로 옮겨줘"가 3번 중 2번 remove_ordinal 로 갔다(= 옮기라는 말에
        #   조각을 지울 뻔했다). 옮기는 말투 '이걸 앞으로 보내줘'는 ways[1] 에
        #   있었는데 결에게 안 갔다.
        when = ("  ← " + " / ".join(f'"{x}"' for x in w[:2]) + " 같은 말") if w else ""
        lines.append(f"  {c['id']}({keys}): {say}{when}")
    # ★[NIGHT-2 2026-08-10] D축 — 도구 설명을 얼마나 주는가.
    #   이 함수가 단일 초크포인트다(호출 3곳: :331 도구선택 · :428 say · :604).
    #   실측: 전체 1,889자 = say 프롬프트 3,481자의 54%.
    #   full(기본) = 현행 그대로 / short = id+인자만(476자) / off = 0자.
    from engine import night2_probe as _n2
    _d = _n2.axis_d()
    if _d == "off":
        return ""
    if _d == "short":
        return "\n".join(f"  {c['id']}({', '.join(c['needs'].keys())})"
                         for c in CAPABILITIES)
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
    from engine import night2_probe as _n2c            # [NIGHT-2] C축
    # ★[GEMMA4 2026-08-11] C=tools — 이 함수 전체(프롬프트 글로 도구를 적어 주고,
    #   JSON 을 강제하고, 다시 파싱하는 층)를 통째로 건너뛴다. 도구 목록은
    #   CAPABILITIES 에서 자동 생성된 스키마가 지고, 고른 것은 ollama 가
    #   tool_calls 로 준다. ★반환 모양이 같아서 호출처는 아무것도 모른다.★
    if _n2c.axis_c() == "tools":
        from engine import gemma4_tools as _g4
        return _g4.ask_tool_native(user_text, ctx, world_lines)
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
        # ★[GHOST-16 2026-08-09 국장 화면] 결의 두 머리가 서로 다른 지도를 봤다.
        #   말하는 쪽(decide 의 prompt)은 "너는 결이고 CCUT 은 같이 일하는 동료다"
        #   를 아는데, 도구를 고르는 이쪽은 그 사실을 ★한 줄도★ 못 받았다.
        #   실측: "ccut은 빼고 너와 둘이서만 대화하자" → remove_scene{scene_no:16}.
        #   '빼'라는 낱말은 있는데 뺄 대상이 영상 속에 없으니, 눈앞에 남은 유일한
        #   번호(직전 이야기의 16)를 집었다. 그리고 손이 "16번 장면은 원고에
        #   들어가 있지 않아요"를 냈다 — 국장 화면의 그 문장이 이 자리에서 났다.
        #   ★규칙이 아니라 사실이다. 말하는 머리가 이미 아는 것을 고르는 머리도
        #     알게 한다(HANDS-1 로 머리를 둘로 가를 때 이 한 줄이 빠졌다).
        + ("[여기 있는 사람]\n"
           "'너'는 결이고, 'CCUT'은 같은 편집실에서 같이 일하는 동료다.\n"
           "둘 다 사람이지 영상에 찍힌 것이 아니다.\n")
        + (f"[방금 나눈 이야기]\n{ctx}\n" if ctx else "")
        + (f"[지금 영상]\n{world_lines}\n" if world_lines else "")
        + f"\n[사용자가 한 말]\n{user_text}\n\n"
        "말한 것을 실제로 해주려면 어떤 도구가 필요한가. 가리키는 말('이 장면', "
        "'그거', '아까 그것')은 방금 나눈 이야기에서 무엇을 가리키는지 찾아 "
        "번호나 이름을 채워라.\n"
        # ★[NIGHT-2 2026-08-10] C축 — 답 모양. json 값은 아래 옛 문자열 그대로다
        #   (기본에서 프롬프트 바이트 동일). xml/free 는 밤 실험에서만.
        + _n2c.fmt_tool_line()
    )
    # ★[도달 증명 2026-08-09] 고르는 머리에 무엇을 함께 줬는지 한 줄로 남긴다.
    #   HANDS-1 이 머리를 둘로 가른 뒤 이쪽에 [여기 있는 사람]이 안 들어간 것을
    #   ★넉 달 동안 아무도 몰랐다★ — 프롬프트는 조용해서 빠져도 소리가 안 난다.
    #   지도(gemma_breath 의 [원고밖])가 실제로 이 자리까지 왔는지도 함께 찍는다.
    print(f"[DESK][ASK-TOOL] 고르는 머리에 함께 준 것 — [여기 있는 사람] 3줄 · "
          f"세계 {len(world_lines or '')}자"
          f"([원고밖] {'있음' if '[원고밖]' in (world_lines or '') else '없음'}) · "
          f"방금 나눈 이야기 {len(ctx or '')}자")
    _c = _n2c.axis_c()
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.2,
                               model=_voice_model(), fmt=_c)
        out = out if isinstance(out, dict) else {}
    except Exception as e:
        print(f"[DESK][WARN] 도구 선택 실패: {e}")
        _n2c.desk_none("ask_tool", err=f"{type(e).__name__}: {e}", fmt=_c)
        return {}
    if _c != "json":
        # ★C축 정규화 — xml/free 는 args 를 중첩으로 안 주는 일이 잦다.
        #   capability 말고 남은 키를 args 로 모은다(형식 세금을 여기서 흡수하되,
        #   흡수했다는 사실은 _fmt_hit 로 기록에 남는다).
        if not isinstance(out.get("args"), dict):
            out["args"] = {k: v for k, v in out.items()
                           if k not in ("capability", "args", "_raw", "_fmt_hit")}
        print(f"[NIGHT-2][C축] 도구 {_c} hit={out.get('_fmt_hit')} "
              f"cap={out.get('capability')!r} args={out.get('args')}", flush=True)
        if not out.get("capability"):
            _n2c.desk_none("ask_tool_no_cap", fmt=_c, hit=out.get("_fmt_hit"),
                           raw=str(out.get("_raw") or "")[:200])
    return out


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
    import time as _tseg0
    _seg_enter = _tseg0.time()

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
    # ★[NIGHT-2 2026-08-10] B축 — 직전 대화를 주는가. 이 여섯 줄이 단일
    #   초크포인트다: 아래 say 프롬프트(:440 자리)와 _ask_tool(:473 자리)이
    #   둘 다 이 ctx 하나를 받는다. 그리고 위 `who` 삼항이 결 자신의 답을
    #   "나: " 로 넣는다 — ★결의 말이 결의 입력으로 되도는 고리는 B 에만 있다.★
    #   기본 on = 현행 그대로.
    from engine import night2_probe as _n2
    _b = _n2.axis_b()
    if _b == "off":
        print(f"[NIGHT-2][B축] off → 직전 대화 {len(ctx)}자 → 0자", flush=True)
        ctx = ""
    elif _b == "user":
        # ★기억은 남기고 되도는 고리만 끊는다 — 결 자신의 답("나: …")을 뺀다.
        _c0 = len(ctx)
        ctx = ""
        for m in (recent_messages or [])[-8:]:
            if m.get("sender") != "user":
                continue
            txt = str(m.get("text") or "")[:160]
            if txt:
                ctx += f"사용자: {txt}\n"
        print(f"[NIGHT-2][B축] user → 직전 대화 {_c0}자 → {len(ctx)}자 "
              f"(결 자신의 답 제거)", flush=True)
    # [2026-08-08 국장 지시 "젬마를 풀어준다"]
    #   안내서에는 세 가지만 적는다 — 이곳이 사용자에게 해주려는 일 / 사용자가
    #   어떤 상태인지 / 네 손에 있는 도구. 제약·금지·판단 분기표는 한 줄도 없다.
    #   무엇을 할지, 어떻게 말할지는 전부 젬마가 정한다.
    # [HOUSE-1 2026-08-08 국장 지시] CCUT 과 ★따로 논다★.
    #   세상의 모든 제품은 AI 가 그 제품을 대표하게 만든다. CCUT 은 반대다.
    #   결이는 CCUT 이 아니라 CCUT 에서 일하는 동료다. 단짝이지만 다른 사람이다.
    #   (직전까지 이 자리에 "너도 CCUT 이라고 부른다"가 있었다 — 정반대였다.)
    from engine import house_talk as _ht
    # ★[GEMMA4 2026-08-11] V축 — 정체성 산문 세 덩이만 갈아 끼운다(_voice_blocks).
    #   keep(기본)은 옛 문자열 그대로라 아래 조립 결과가 예전과 바이트 동일하다.
    _v = _n2.axis_v()
    _vb = _voice_blocks(_v)
    # ★_ht.lines 는 ★부작용이 있다★ — 건넨 소식을 _HANDED 에 표시한다(house_talk).
    #   두 번 부르면 두 번째가 빈다. 그래서 한 번만 부르고 변수로 나른다.
    _house = _ht.lines(project_id)
    # 머리(사용자 말 앞까지) — 아래 두 경로가 ★같은 머리★를 쓴다.
    _pre = (
        _vb["head"]
        + "[지금 이 사람의 영상]\n"
        + (world_lines + "\n" if world_lines else "(아직 없다)\n")
        + "\n[네 손에 있는 도구]\n"
        + _capability_lines() + "\n"
        + _vb["not_here"]
        # [NIGHT-1 2026-08-09 천 명의 밤·국장 지시 "결을 소중히, 교육으로"]
        #   실측: "본사가 어디야?" 에 없는 주소를 지어냈고, "투자 받았어?" 에
        #   없는 사실을 단정했다. 모르면 지어내는 버릇을 막는 규칙을 세우는
        #   대신, 몰라도 괜찮다는 것을 알려준다 — 편하게 모른다고 해도 된다.
        + _vb["honesty"]
        # 집에서 방금 있었던 일 — 알려만 준다. 말할지는 결이가 정한다.
        + _house
        + (f"[지금까지 나눈 이야기]\n{ctx}\n" if ctx else "")
    )
    prompt = (
        _pre
        + f"[사용자]\n{user_text}\n\n"
        # 예시에 '내용'을 넣지 않는다 — 넣었더니 젬마가 그 내용을 따라 했다
        #   ('고마워'에 "6번 집 조각을 빼드릴게요", 답에 JSON 조각 유출. 실측).
        #   형식만 알려주고 무엇을 말할지는 젬마가 정한다.
        + "편하게 답해라.\n"
        # ★[NIGHT-2 2026-08-10] C축. json 값 = 옛 문자열 그대로(기본 무변경).
        + _n2.fmt_say_line()
    )
    # ★[HANDS-1 2026-08-08] 말과 도구를 갈라 ★동시에★ 묻는다.
    #   실측: 하나의 JSON 에 say + capability + args 를 함께 담게 했더니
    #   대화가 자연스러워질수록 도구 칸이 비었다(36발화 중 15건 just_talk,
    #   '뺐나?' 조차 도구 없이 되물음). 젬마 4B 에게 한 번에 두 일은 무겁다.
    #   격리에서 도구만 물었을 때는 10/10 이었다 — 그 형태를 그대로 쓴다.
    #   순차로 두 번 부르면 11.8초가 됐다(실측).
    # ★[정정 2026-08-09] "그래서 병렬이다"라고 적혀 있었다 — 거짓이다.
    #   아래 ThreadPoolExecutor(max_workers=2)는 병렬로 보이지만 두 호출 모두
    #   hub._OLLAMA_LOCK(hub.py) 에 직렬화된다. 실측 증거: 두 번째 호출의
    #   lock_wait 이 첫 번째의 gen 과 소수점까지 같다
    #   (1284/1284 · 10400/10400 · 18730/18733 · 오늘 1449/1449 · 1256/1256).
    #   즉 벽시계는 say + 도구선택의 ★합★이다. 스레드는 시간을 벌지 않았다.
    #   락을 풀어도 이득 없음도 실측됐다(C4: gemma 동시 2건 27.2s/47.5s —
    #   8GiB VRAM 이 병렬 슬롯을 주지 못한다). 진짜로 절반을 없애려면 두 물음을
    #   한 번의 호출로 합쳐야 하는데, 그러면 HANDS-1 이 머리를 가른 근거
    #   (도구 정확도 10/10)를 잃을 수 있다 → A/B 실측 뒤 판정할 일.
    #   지금 이 자리를 건드리지 않는 이유: 오늘 사고의 범인이 아니다(범인은 모델 축출).
    import time as _tseg
    _seg0 = _tseg.time()
    print(f"[TTFT-SEG][decide] prompt_build={int((_seg0 - _seg_enter) * 1000)}ms",
          flush=True)
    _c = _n2.axis_c()                                       # [NIGHT-2] C축
    # ★[GEMMA4 2026-08-11] tools 는 ★도구 머리만★ 갈아 끼운다 — 말하는 머리는
    #   json 과 한 글자도 다르지 않다(fmt_say_line 도 json 값을 그대로 돌려준다).
    #   그래야 두 조합의 차이가 오직 '손으로 만든 도구 층 vs 네이티브 도구 층'이
    #   된다. 말까지 같이 바꾸면 무엇이 숫자를 움직였는지 못 가른다.
    _say_fmt = "json" if _c == "tools" else _c
    # ★[GEMMA4 2026-08-11] 말+도구 ★한 호출★ — C=tools 이고 V=hands 일 때만.
    #   왜 이 두 값에서만인가: 한 호출로 합치면 도구를 고르는 것도 ★목소리 머리★가
    #   한다. keep 머리는 "너는 손이 없다"를 일곱 가지로 가르치므로(격리 실측
    #   0/12) 그 머리로 합치는 것은 실패가 예정된 실험이다 — 잴 것이 없다.
    #   hands 머리는 그 가르침만 걷어낸 것이라, 여기서 합치는 것이 뜻을 갖는다.
    #   ★안 되면 그대로 두고 2회 경로로 돌아간다(아래 except).
    _both = (_c == "tools" and _v == "hands")
    if _both:
        from engine import gemma4_tools as _g4
        _sys = _pre + (
            "말한 것을 실제로 해주려면 필요한 도구를 부르고, 인사·감사·잡담처럼\n"
            "아무 도구도 필요 없는 말이면 부르지 않는다. 가리키는 말('이 장면',\n"
            "'그거')은 지금까지 나눈 이야기에서 무엇을 가리키는지 찾아 채운다.\n"
            "못 들은 값은 지어내지 말고 비워 둬라.\n"
            "그리고 사용자에게 할 말을 편하게 적어라.\n")
        both = _g4.ask_both_native(_sys, user_text, timeout=90, temperature=0.4)
        print(f"[TTFT-SEG][decide] both_one_call="
              f"{int((_tseg.time() - _seg0) * 1000)}ms "
              f"say_prompt_chars={len(_sys)}", flush=True)
        if both is None:
            # 한 호출이 배관째 실패했다 — ★억지로 만들지 않는다.★ 2회 경로로 간다.
            _n2.reach("gemma4_both/fallback_two_calls")
            _both = False
        else:
            out = {"say": both.get("say") or "", "_fmt_hit": "tools_both"}
            picked = both
    if not _both:
        try:
            with _cf.ThreadPoolExecutor(max_workers=2) as ex:
                f_say = ex.submit(hub._ollama_json, prompt, timeout=30,
                                  temperature=0.4, model=_voice_model(),
                                  fmt=_say_fmt)
                f_cap = ex.submit(_ask_tool, user_text, ctx, world_lines)
                out = f_say.result() or {}
                _seg_say = int((_tseg.time() - _seg0) * 1000)
                picked = f_cap.result() or {}
                print(f"[TTFT-SEG][decide] say={_seg_say}ms "
                      f"both={int((_tseg.time() - _seg0) * 1000)}ms "
                      f"say_prompt_chars={len(prompt)}", flush=True)
        except Exception as e:
            # ★[NIGHT-2] 여기가 desk None 의 본진이다 = format tax 의 크기.
            #   실패가 아니라 측정값이다 — 세어서 조합별로 남긴다.
            print(f"[DESK][WARN] 판단 실패: {e}")
            _n2.desk_none("decide", err=f"{type(e).__name__}: {e}", fmt=_c)
            return None
    if _say_fmt != "json" and not str(out.get("say") or "").strip():
        # free 는 답 전체가 곧 say 다. xml 에서 <say> 를 못 찾았을 때도 원문을 쓴다 —
        #   ★형식을 못 맞췄다고 결의 말을 버리지 않는다(그게 이 축이 재려는 것이다).
        out["say"] = str(out.get("_raw") or "")[:1200]
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
    # [NIGHT-2] E축 — 사용자가 말한 적 없는 조각 이름을 슬롯에서 지우는 검문
    #   (정찰 목록의 '오타교정삭제'). 결이 'A59' 같은 라벨을 지어내면 여기서
    #   증발한다. 그림자에서는 지우지 않고 그대로 손까지 보낸다 — 그래야
    #   "안 막았으면 무엇이 됐을지"가 남는다.
    if _f and _f.upper() not in (user_text or "").upper() and _n2.guard(
            "FRAGMENT-GROUND", fragment=_f, user_text=(user_text or "")[:100],
            cap=cap):
        args = {k: v for k, v in args.items() if k != "fragment"}
    say = _sanitize_talk(str(out.get("say") or "").strip()) or ""
    # 내부 id 가 섞인 문장은 그 문장만 통째로 버린다. 낱말만 지우면
    #   '3번째 조각을 빼드릴게요. 사용하겠습니다.' 같은 잔재가 남는다(실측).
    if any(c["id"] in say for c in CAPABILITIES):
        keep = [s for s in re.split(r"(?<=[.!?])\s+", say)
                if not any(c["id"] in s for c in CAPABILITIES)]
        say = " ".join(keep).strip()
    say = re.sub(r"\s{2,}", " ", say).strip()
    # ★[NIGHT-2 2026-08-10] 턴 재료 — 기록만 한다(PROBE 꺼져 있으면 무동작).
    #   E축 사후 판정에 필요한 최소 재료가 여기 다 있다: 결에게 무엇을 줬고
    #   (world/ctx 길이), 결이 무엇을 냈고(tool_raw/say_raw), 검문 뒤 무엇이
    #   남았는가(say). 화면에 실제로 나간 문장은 하네스가 응답에서 받는다.
    _n2.rec("turn_material", user_text=(user_text or "")[:200],
            world_lines_len=len(world_lines or ""), ctx_len=len(ctx or ""),
            prompt_chars=len(prompt),
            tool_raw=picked, say_raw=str(out.get("say") or "")[:400],
            say_after_guards=say[:400], cap=cap, args=args,
            reason=str(out.get("reason") or ""),
            fmt=_c, say_hit=out.get("_fmt_hit"),          # [NIGHT-2] C축
            tool_hit=picked.get("_fmt_hit"),
            # ★[GEMMA4] V축 재료 — 어느 목소리였고, 머리가 몇 자였고,
            #   결을 ★몇 번★ 불렀나(1=합친 호출 / 2=말·도구 따로).
            v=_v, voice_head_chars=len(_vb["head"]),
            desk_llm_calls=(1 if _both else 2))
    return {"cap": cap, "args": args, "say": say,
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
                               model=_voice_model())
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
                               model=_voice_model())
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
                               model=_voice_model())
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
    from engine import night2_probe as _n2                    # [NIGHT-2] E축
    if leaked and _n2.guard("NAME-GUARD", say=say, leaked=leaked):
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
    # ★[WISH-1 2026-08-12] V축 — 정체성 머리만 갈아 끼운다. keep 은 옛 문자열 그대로라
    #   기본에서 이 프롬프트가 한 바이트도 안 달라진다(_voice_keep_selfcheck 가 확인).
    from engine import night2_probe as _n2v
    prompt = (
        _voice_look_head(_n2v.axis_v())
        + "아래는 CCUT이 이 영상을 장면 단위로 훑어 준 지도다. **여기 적힌 것만**\n"
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
                               model=_voice_model())
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
        from engine import night2_probe as _n2                # [NIGHT-2] E축
        if not _n2.guard("TIME-GUARD", say=say, bad=sorted(bad),
                         known=sorted(known)[:20], user_text=(user_text or "")[:100]):
            return say                           # 그림자: 강등하지 않는다
        try:
            out2 = hub._ollama_json(
                prompt + "\n주의: 시각(N분NN초)을 적지 마라. 장면 내용만 말하라.",
                timeout=25, temperature=0.3, model=_voice_model())
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
                               model=_voice_model())
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
    # ★[WISH-1 2026-08-12] V축 — 이 함수가 ★손이 움직인 뒤 화면에 나가는 말★을 만든다.
    #   keep 은 아래 문자열 전부 옛 것 그대로다(_voice_keep_selfcheck 가 못 박는다).
    from engine import night2_probe as _n2v
    _v = _n2v.axis_v()
    _sub = _done_subject(_v)                    # keep="CCUT이 " / hands·bare=""
    if not facts.get("ok"):
        why = facts.get("why") or "지금은 못 한다"
        if _v == "keep":
            return f"CCUT이 그건 못 한대요 — {why}. 어떻게 할까요?"
        return f"그건 못 해요 — {why}. 어떻게 할까요?"

    # [EXPORT-1 2026-08-09] 내보내기 승인 문구·완료 Receipt은 그대로 말한다.
    #   LLM 의역을 거치지 않는다 — 안전벨트①③이 요구하는 숫자(조각 수·길이·
    #   크기)가 의역 중에 지어지거나 사라지면 안 되는 자리라, 서버 문장을
    #   결이 말투 다듬기 없이 그대로 사용자에게 전한다.
    if facts.get("propose"):
        return facts["what"]
    if facts.get("output_path") is not None:
        return facts["what"]

    if facts.get("receipts") is not None:
        rs = facts["receipts"]
        if facts.get("nothing"):
            return f"아직 손댄 건 없어요. 지금 {facts['after']}조각입니다."
        head = rs[0]
        # [HANDS-2] 대괄호로 읽으면 키 하나가 없을 때 답 전체가 KeyError 로 죽는다.
        #   실측: 내보내기 Receipt 를 이 목록에 넣자마자 그렇게 됐다. Receipt 는
        #   손마다 모양이 조금씩 다르니 없는 칸은 지금 조각 수로 메운다.
        _bc = head.get("before_count", facts.get("before"))
        _ac = head.get("after_count", facts.get("after"))
        fact_line = (f"방금 한 일: {head.get('what')} "
                     f"({_bc}조각 → {_ac}조각)")
        server = (f"네, {_sub}{head.get('what')} 지금 {_ac}조각입니다.")
    elif facts.get("op") == "reorder":
        # [HANDS-2 2026-08-09] 순서를 바꾸면 조각 수는 안 변한다.
        #   "5조각 → 5조각"이라고 대면 결이 '아무것도 안 됐다'로 읽고
        #   그렇게 말한다. 바뀐 것은 수가 아니라 자리다 — 자리를 사실로 준다.
        _mv = ""
        if facts.get("from_pos") and facts.get("to_pos"):
            _mv = f", {facts['from_pos']}번째에 있던 것이 {facts['to_pos']}번째로"
        fact_line = (f"방금 한 일: {facts['what']} "
                     f"(조각 수는 {facts['after']}개 그대로, 순서만 바뀜{_mv})")
        server = f"{_sub}{facts['what']}"
    elif facts.get("op") == "correct":
        # ★[FIX-CORRECT 2026-08-11] 정정은 두 일이 한 턴에 일어난다(무르기+새로
        #   빼기). 조각 수는 대개 그대로라, 순서 손과 같은 함정이 있다 —
        #   "7조각 → 7조각"만 대면 결이 '아무 일도 안 됐다'로 읽고 그렇게 말한다.
        #   바뀐 것은 수가 아니라 ★어느 것이 빠졌나★다. 그것을 사실로 준다.
        fact_line = (f"방금 한 일: {facts['what']} "
                     f"(잘못 뺀 것은 원고로 돌아왔고 대신 다른 조각이 빠졌다 — "
                     f"지금 {facts['after']}조각)")
        server = f"{_sub}{facts['what']} 지금 {facts['after']}조각이에요."
    elif facts.get("op") in ("trim", "exclude", "edit_undo"):
        # [HANDS-2 2026-08-09] 좌표를 건드리는 손도 조각 수가 안 변한다.
        #   순서 손과 같은 자리 — 바뀐 것은 수가 아니라 길이다. 길이를 사실로 준다.
        #   숫자는 NUM-GUARD 가 이 문장에서 뽑아 허용한다(allow = fact_line 의 숫자).
        fact_line = (f"방금 한 일: {facts['what']} "
                     f"(그 조각 길이 {facts.get('len_before_text')} → "
                     f"{facts.get('len_after_text')}, 조각 수는 {facts['after']}개 그대로)")
        server = f"{_sub}{facts['what']}"
    else:
        fact_line = (f"방금 한 일: {facts['what']} "
                     f"({facts['before']}조각 → {facts['after']}조각)")
        server = (f"{_sub}{facts['what']} {facts['before']}조각 → "
                  f"{facts['after']}조각이에요.")
    # ★[HANDS-2 2026-08-09] NUM-GUARD 의 allow 를 손으로 나열하지 않는다.
    #   before/after 두 개만 허용하던 탓에, 손이 새 숫자를 사실로 준
    #   순간(순서의 '3번째로', 앞으로 올 트림의 '2초') 결의 문장이 통째로
    #   버려지고 서버 문장으로 바뀌었다. 허용의 근거는 '미리 적어 둔 목록'이
    #   아니라 **이 사실 문장에 실제로 있는 숫자**다 — 출처가 서버 사실이라는
    #   보증은 그대로다.
    # ★[HANDS-3 2026-08-10] 소수점을 하나의 숫자로 읽는다.
    #   구판 `\d+` 은 `13.2초` 를 {'13','2'} 로 부숴서, 사실에 없던 '2' 가
    #   덤으로 허용됐다(검문이 뚫린다). edit_propose._numbers_ok(:205-208)가
    #   이미 쓰는 모양이 정답 — 같은 정규식으로 맞춘다.
    #   같은 이유로 반대편도 막는다: 사실이 `13.2초` 인데 결이 `약 13초` 로
    #   반올림해 말하면 구판 규칙에선 통과했지만 새 규칙에선 없는 숫자가 되어
    #   멀쩡한 문장이 강등된다. 반올림·버림한 정수도 함께 허용한다 — 출처가
    #   서버 사실이라는 보증은 그대로다(사실에 있는 수에서만 파생한다).
    allow = set()
    for t in re.findall(r"\d+(?:\.\d+)?", fact_line):
        allow.add(t)
        if "." in t:
            try:
                allow.add(str(int(float(t))))
                allow.add(str(int(round(float(t)))))
            except ValueError:
                pass

    prompt = (
        _voice_done_head(_v)
        + f"사용자가 한 말: \"{(user_text or '')[:100]}\"\n"
        f"{fact_line}\n"
        "이미 다 한 상태다 — 해도 되는지 묻지 마라. 위 숫자를 그대로 넣어 "
        "1~2문장으로 알리고, 마음에 안 들면 되돌릴 수 있다는 걸 알려라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5,
                               model=_voice_model())
        say = _sanitize_talk(str(out.get("say") or "").strip())
        nums = set(re.findall(r"\d+(?:\.\d+)?", say or ""))   # [HANDS-3]
        if say and nums <= set(allow):
            return say
        if say:
            print(f"[DESK][NUM-GUARD] 없는 숫자 — 서버 문장으로: {say[:50]!r}")
            # ★[NIGHT-2 2026-08-10] E축. 구판은 say[:50] 만 찍었다 — 그것만으로는
            #   "결의 참말을 죽였나, 진짜 오류를 막았나"를 사후에 가를 수 없다.
            #   전문·fact_line·allow·없던 숫자를 함께 남긴다.
            from engine import night2_probe as _n2
            if not _n2.guard("NUM-GUARD", say=say, fact_line=fact_line,
                             allow=sorted(allow), unknown=sorted(nums - set(allow)),
                             server_say=server, user_text=(user_text or "")[:100]):
                return say                       # 그림자: 강등하지 않는다
    except Exception as e:
        print(f"[DESK][WARN] 보고 문장 실패: {e}")
    return server
