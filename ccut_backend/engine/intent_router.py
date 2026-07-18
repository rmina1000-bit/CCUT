# -*- coding: utf-8 -*-
"""[INTENT-ROUTER] 채팅 '종업원' — 프론트 메뉴판 정규식을 대체하는 백엔드 해석기.

구조 (2026-07-05, 국장 승인 계획):
  사용자 말 → 프론트는 거의 그대로 전달 → 여기서 해석
  1) 결정론 사다리: 인물 이름/애칭(resolve) → 장면/개수/제외 어휘 → 수정명령 →
     질문/모호 감지
  2) 그래도 애매하면 Qwen2.5 라우팅 (format:json)
  3) 실행 가능하면 run_proposal + normalized_instruction(애칭→풀네임 정규화),
     애매하면 ask_clarification(되묻기), 설명 질문은 answer_only

응답 계약:
  {status, action, normalized_instruction, reply, confidence, matched}
  action ∈ run_proposal | revise_current | ask_clarification | answer_only

원칙: 메뉴판이 아니라 종업원 — "이 말이 메뉴에 있나"가 아니라 "이 말씀인가요"를
판단한다. 판단 불가 시 정직하게 되묻는다(조용한 오답 금지).
"""
import json
import os
import re as _re_mod

from engine import hub

_ACTIONS = ("run_proposal", "revise_current", "ask_clarification", "answer_only")

# ── [CHAT-GATE 국장지시 2026-07-06] "무슨 말을 해도 다 편집으로 끌고가" 수리 ──
# 편집 표지가 전혀 없는 일상 대화는 인물/테마 사다리보다 먼저 대화로 보낸다.
# 편집 표지: 이게 하나라도 있으면 게이트를 지나쳐 기존 편집 사다리로 (편집 보호 우선)
_EDIT_MARK_RE = _re_mod.compile(
    r"편집|나오게|남게|남겨|골라|만들|위주|중심|모아|추려|빼|제외|줄여|늘려|"
    r"장면|컷|조각|부분만|\d+\s*개|짧게|길게|빠르게|느리게|템포|속도|"
    r"이대로|진행|확정|제안|내보내|렌더|썸네일|자막|프로젝트|"
    r"넣어|넣고|바꾸|바꿔|교체|삭제|추가|순서|"
    r"(게|하게)\s*(해\s*줘|해줘|해\s*봐|해봐)")
# 대화 신호: 물음/웃음/인사/감정/서술 종결어미 — 하나는 있어야 대화로 판단.
# 종결어미에 어/아/요 포함: 축약 과거형("탔어!","갔어","했어요")이 대화의 주력 형태.
_CHAT_SIGNAL_RE = _re_mod.compile(
    r"[?？]"
    r"|[ㅋㅎ]{2,}|ㅠ|ㅜ"
    r"|안녕|고마워|고맙|감사|반가|수고|잘자|잘 자|주무|굿모닝|굿나잇"
    r"|피곤|힘들|심심|외롭|기분|행복|슬프|슬퍼|우울|배고|졸리|졸려|스트레스"
    r"|짜증|화나|신나|즐겁|즐거|사랑|보고싶|설레|걱정|불안|아프|맛있|재밌|재미있|귀엽|귀여"
    r"|예뻐|이뻐|기뻐|바빠|나빠|고파|추워|더워|무서워|웃겨|어려워|쉬워|미워"
    r"|(었|았|였)(어|다|네|지|죠|는데)"
    r"|(다|야|네|지|죠|잖아|거든|는데|대|래|어|아|요|구나|군|자|음|함)[.!~\s]*$")
# 짧은 승인어는 게이트 제외 — 제안 확정("좋아", "이대로") 흐름 보호
_AFFIRM_SHORT_RE = _re_mod.compile(
    r"^(응+|어+|네|예|그래|좋아요?|좋지|좋네|오케이|ok|콜)[.!~\s]*$", _re_mod.IGNORECASE)

# 받침 유무에 따라 형태가 갈리는 조사 (받침없음형, 받침있음형)
_PARTICLE_PAIRS = [("가", "이"), ("는", "은"), ("를", "을"), ("와", "과"),
                   ("야", "아"), ("랑", "이랑"), ("로", "으로")]


def _has_batchim(word):
    ch = (word or "")[-1:]
    if not ch or not ("가" <= ch <= "힣"):
        return False
    return (ord(ch) - 0xAC00) % 28 != 0


def replace_name(text, matched, canonical):
    """이름 치환 + 바로 뒤 조사 교정 — '은한이가'→'정은한이' (단순 replace의
    '정은한가' 문법 붕괴 수리). 치환 지점마다 다음 조사를 canonical 받침에 맞춘다."""
    if matched == canonical or matched not in text:
        return text
    out = []
    i = 0
    L = len(matched)
    batchim = _has_batchim(canonical)
    while True:
        j = text.find(matched, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(canonical)
        k = j + L
        # 뒤따르는 조사 교정 (긴 형태 우선: '이랑' > '랑')
        rest = text[k:]
        fixed = None
        for plain, tail in sorted(_PARTICLE_PAIRS, key=lambda x: -max(len(x[0]), len(x[1]))):
            for form in {plain, tail}:
                if rest.startswith(form):
                    fixed = (tail if batchim else plain)
                    k += len(form)
                    break
            if fixed:
                break
        if fixed:
            out.append(fixed)
        i = k
    return "".join(out)

_QUESTION_RE = None
_VAGUE_RE = None


def _regexes():
    global _QUESTION_RE, _VAGUE_RE
    if _QUESTION_RE is None:
        import re
        _QUESTION_RE = re.compile(r"[?？]$|왜 |뭐야|무슨|어떻게|알아듣|이해해|설명해")
        _VAGUE_RE = re.compile(r"느낌|멋있|예쁘|좋게|세련|힙하게|감각|영화처럼|분위기|감성|그럴듯")
    return _QUESTION_RE, _VAGUE_RE


def _resp(action, reply, normalized=None, confidence=0.9, matched=None, via="deterministic"):
    return {
        "status": "OK",
        "action": action,
        "normalized_instruction": normalized,
        "reply": reply,
        "confidence": round(float(confidence), 2),
        "matched": matched,
        "via": via,
    }


_ORDINAL_KO = {0: "첫 번째", 1: "두 번째", 2: "세 번째", 3: "네 번째",
               4: "다섯 번째", -1: "마지막"}


def _revision_reply(rev):
    """[#57 §5] 수정 op의 정직 예고문 — 무엇을 어디서 어떻게 바꾸는지 실행 전에 말한다."""
    where = f"{rev['target_mode']}안에서" if rev.get("target_mode") else "지금 안에서"
    if rev["op"] == "remove_ordinal":
        pos = _ORDINAL_KO.get(rev["index"], f"{rev['index'] + 1}번째")
        return f"네, {where} {pos} 조각을 빼겠습니다."
    if rev["op"] == "set_count":
        return f"네, {where} 조각 {rev['count']}개로 맞추겠습니다."
    return f"네, {where} '{rev['theme']}' 조각을 빼겠습니다."


def _llm_understand(input_text, recent_messages=None, source_ids=None,
                    person_vocab=None, defer_chat=False):
    """[문맥 종업원 v2 — 국장지시 2026-07-06] 매트릭스가 아니라 문맥으로 판단한다.
    한 번의 호출로 대화/편집/승인/모호를 분류하고, 대화면 그 자리에서 진짜 답을 만든다.
    실제 날짜·작업 상황을 주입해 '오늘 몇일?' 환각(22일 사건)을 봉쇄한다.
    실패 시 None → 호출부가 정직한 고정 문구."""
    import datetime as _dt
    now = _dt.datetime.now()
    weekday = "월화수목금토일"[now.weekday()]
    ctx = ""
    for m in (recent_messages or [])[-8:]:
        who = "사용자" if (m.get("sender") == "user") else "CCUT"
        txt = str(m.get("text") or "")[:160]
        if txt:
            ctx += f"{who}: {txt}\n"
    n_src = len(source_ids or [])
    # [실데이터 주입] 조각/원본 혼동 환각 봉쇄 ("조각 11개가 원본 영상입니다" 사건)
    n_frag = 0
    if source_ids:
        try:
            import sqlite3 as _sq
            _con = _sq.connect(hub.DB_PATH, timeout=10)
            n_frag = _con.execute(
                "SELECT COUNT(*) FROM semantic_fragments WHERE source_id IN (%s)"
                % ",".join("?" * len(source_ids)), list(source_ids)).fetchone()[0]
            _con.close()
        except Exception:
            n_frag = 0
    # 0개여도 항상 명시 — 빈 프로젝트에서 "조각 5개" 환각 방지 (모르면 지어내는 습성 봉쇄)
    work_line = (f"[작업 상황] 이 프로젝트에는 원본 영상 {n_src}개가 올라와 있고, "
                 f"거기서 나눈 조각(장면 단위)이 {n_frag}개다. 원본과 조각은 다른 개념이며, "
                 "이 숫자 외의 작업 수치를 지어내지 마라.\n") if source_ids is not None else ""
    facts = (f"[지금] {now.year}년 {now.month}월 {now.day}일 {weekday}요일 "
             f"{now.strftime('%H:%M')}\n" + work_line
             + "위 [지금]/[작업 상황] 수치는 실측값이다 — 날짜·조각·원본 질문은 이 값으로만 답하라.\n")
    prompt = (
        "너는 CCUT — 영상 편집 스튜디오의 다정한 동료다. 사용자와 자연스럽게 대화하고, "
        "사용자의 말이 편집 지시일 때만 편집 접수로 처리한다.\n"
        + facts
        + "판단 기준:\n"
        "- edit: 영상에서 무엇을 골라/빼/줄여/늘려/만들어 달라는 '기준'이 명확할 때만.\n"
        "- confirm: 직전에 CCUT이 제안한 방향에 대한 승인(그대로 진행해 등).\n"
        "- chat: 그 외 전부 — 일상 이야기·감정·질문·근황. 사람 이름이 나와도 이야기면 chat이다.\n"
        "  예: '은한이가 자전거 탔어!' → chat / '은한이 나오는 장면만 넣어줬으면 좋겠어' → edit\n"
        "- retrigger: 새 기준 없이 '다시/재/새로/한 번 더 + 편집·제안해 달라'는 순수 재실행 명령 "
        "('다시 편집해줘', '재제안'). 기준 단어가 하나라도 있으면 edit이다. "
        "주의: '다르게/바꿔서/딴 걸로' 같은 변화 요구가 붙거나('다시 해줘 근데 이번엔 좀 다르게'), "
        "'처음부터 다시'처럼 해제인지 재실행인지 애매하면 retrigger가 아니라 unclear다.\n"
        "- reset: 기준을 없애고 전체를 다시 보자는 말 ('전부 다시 봐줘', '조건 없이 다 보여줘', '기준 없애줘').\n"
        "- unclear: 편집 의도는 있는데 무엇을 고를지 기준이 없고 재실행도 해제도 아닐 때 "
        "('느낌있게', '처음부터 다시', '다시 해줘 근데 이번엔 좀 다르게').\n"
        "instruction 규칙: edit일 때만 채운다. 반드시 '무엇을 고르는 기준'(예: '정은한 나오는 "
        "장면만', '물놀이 위주로 길게')이어야 한다. 사용자에게 묻는 문장을 넣으면 절대 안 된다. "
        "기준을 모르면 kind를 unclear로 하라.\n"
        "reply 규칙: 반드시 한국어로만(중국어·영어 문장 금지). 모델명·제조사(Qwen 등) 언급 금지 — "
        "너의 이름은 오직 CCUT이다. 날짜·시간·작업 상황 질문은 위 값으로 정확히 답하고, "
        "날씨·뉴스 등 모르는 실시간 정보는 아는 척하지 않는다.\n"
        'JSON만 출력: {"kind":"chat|edit|confirm|retrigger|reset|unclear","reply":"...",'
        '"instruction":"edit일 때 선별 기준, 아니면 빈 문자열"}\n'
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n")
    try:
        out = hub._ollama_json(prompt, timeout=45)
    except Exception as e:
        print(f"[INTENT-ROUTER] llm understand 실패 ({e})")
        return None
    kind = str(out.get("kind") or "").strip()
    reply = _sanitize_talk(str(out.get("reply") or "").strip())
    if kind == "edit":
        instr = str(out.get("instruction") or "").strip() or input_text
        # [지시문 오염 가드 2026-07-06] LLM이 instruction 칸에 되묻기 문장을 넣는 사고
        # ("...알려주십시오"가 편집 기준으로 실행된 사건) — 질문꼴/과장 지시문은
        # 실행하지 않고 되묻기로 강등한다.
        if _re_mod.search(r"[?？]|주세요|주십시오|알려|말씀해|무엇을|어떤 (부분|장면)을|"
                          r"싶으신지|시겠어요|해볼까요", instr) or len(instr) > 60:
            kind = "unclear"
        else:
            # 애칭→풀네임 정규화·filters는 결정론 헬퍼 재사용 (LLM 분류 + 결정론 정규화 분업)
            r_extra = {}
            person = hub.resolve_person_name(instr, vocab=person_vocab)
            if person:
                instr = replace_name(instr, person["matched"], person["canonical"])
                r_extra["filters"] = [{"type": "person", "value": person["canonical"],
                                       "source": "alias" if person["matched"] != person["canonical"] else "name",
                                       "matched": person["matched"]}]
            r = _resp("run_proposal",
                      reply or "네, 말씀하신 기준으로 골라볼게요.",
                      normalized=instr, confidence=0.75, via="qwen",
                      matched={"kind": "llm_edit"})
            r.update(r_extra)
            return r
    if kind == "confirm":
        return _resp("run_proposal",
                     reply or "네, 지금 방향 그대로 진행하겠습니다.",
                     normalized=input_text, confidence=0.7, via="qwen",
                     matched={"kind": "llm_confirm"})
    # [#49 (a) — det·qwen 양 경로 일관] LLM이 재실행/해제로 분류한 경우도 같은 action으로.
    if kind == "retrigger":
        # [경계 가드 — V 판정 "애매하면 clarification, retrigger로 몰지 않는다"]
        # 소형 LLM이 프롬프트 배제 조건을 무시하는 실측(A1·A2) → 결정론 후처리로 강등:
        # 변화 요구(다르게·바꿔·딴)나 '처음부터'가 붙으면 순수 재실행이 아니다.
        if _re_mod.search(r"다르게|다른\s*(방향|느낌|걸|거)|바꿔|바꾸|딴\s*(걸|거)|처음부터", input_text):
            kind = "unclear"
        else:
            return _resp("retrigger", "직전 기준으로 다시 골라볼게요.",
                         confidence=0.7, via="qwen", matched={"kind": "retrigger_llm"})
    if kind == "reset":
        return _resp("intent_clear", "기준 없이 전체에서 다시 고를게요.",
                     confidence=0.7, via="qwen", matched={"kind": "intent_clear_llm"})
    if kind == "unclear":
        # 되묻기는 LLM 문장을 쓰지 않는다 — reply 칸에 예시 지시문을 넣는 사고가
        # 관측됨("물놀이 장면 위주로 길게 편집해주세요"가 CCUT 말로 출력). 고정 템플릿.
        return _resp("ask_clarification",
                     "어떤 기준으로 고를까요? 예: '정은한 나오는 장면만', "
                     "'물놀이 위주로', '실내만', '더 길게/짧게'.",
                     confidence=0.6, via="qwen", matched={"kind": "llm_unclear"})
    if kind == "chat":
        # [F2 스트리밍] defer_chat=True면 대화 생성을 하지 않고 표식만 반환 —
        # 스트림 엔드포인트가 stream_smalltalk로 토큰 단위 생성한다. 분류는 이미 완료.
        if defer_chat:
            r = _resp("answer_only", "", confidence=0.85, via="qwen",
                      matched={"kind": "free_chat"})
            r["_stream_chat"] = {"facts": facts}
            return r
        # [대화 품질 2026-07-06] 분류(temp 0)와 대화(temp 0.7)를 분리 — 분류 초안 답 대신
        # 대화 전용 프롬프트(화제 이탈 금지·실시간 정보 아는 척 금지)로 최종 답을 만든다.
        talk = _llm_smalltalk(input_text, recent_messages, facts=facts)
        return _resp("answer_only",
                     talk or reply or "네, 듣고 있어요. 편하게 이야기해 주세요.",
                     confidence=0.85, via="qwen", matched={"kind": "free_chat"})
    return None


def _sanitize_talk(reply):
    """[SMALLTALK 위생] LLM 답에서 중국어 유출·모델 정체(Qwen) 노출을 차단.
    (국장 실측: '큐원은 뭐지?'에 중문 혼입, '니가 누군지'에 'Qwen이라는 인공지능' 자백)
    걸리면 None → 호출부가 CCUT 인격의 고정 문구로 강등."""
    import re
    if not reply:
        return None
    if re.search(r"[一-鿿]", reply):   # 한자/중문 — 한국어 답변만 허용
        return None
    if re.search(r"qwen|큐원|퀜|通义|阿里|알리바바|인공지능(으로|입니다)", reply, re.IGNORECASE):
        return None                             # 모델 정체 노출 — 너는 오직 CCUT
    return reply


def _smalltalk_prompt(input_text, recent_messages=None, facts="", plain=False):
    """[F2] 자유대화 프롬프트 조립 — 일괄(JSON)과 스트림(plain 텍스트)이 규칙을 공유."""
    ctx = ""
    for m in (recent_messages or [])[-6:]:
        who = "사용자" if (m.get("sender") == "user") else "CCUT"
        txt = str(m.get("text") or "")[:120]
        if txt:
            ctx += f"{who}: {txt}\n"
    tail = ("답변 문장만 출력한다 — JSON·따옴표·머리말 금지.\n" if plain
            else 'JSON만 출력: {"reply":"..."}\n')
    return (
        "너는 CCUT — 영상 편집을 돕는 다정한 동료다. 사용자의 말에 따뜻한 존댓말 "
        "한국어 1~3문장으로 '실제로' 대답한다.\n"
        + facts +
        "대화 규칙 (어기면 실격):\n"
        "1. 사용자의 마지막 말에 직접 반응한다. 화제를 네 맘대로 바꾸지 않는다 — "
        "카페·취미 추천 같은 뻔한 스몰토크를 먼저 꺼내지 마라.\n"
        "2. 날씨·뉴스·유행 같은 실시간 정보는 너는 모른다 — 아는 척 금지. "
        "사용자가 알려주면 그 말을 믿고 따라가라.\n"
        "3. 고민·감정을 말하면 가볍게 공감하고, 구체적으로 하나만 되물어라.\n"
        "4. '저는 편집기라서'류 거절 금지. 매번 편집 얘기로 돌리지도 마라.\n"
        "5. 반드시 한국어만(중국어·영어 문장 금지). 모델명·제조사(Qwen 등) 언급 금지 — "
        "너의 이름은 오직 CCUT이다. 모르는 건 솔직히 모른다고 한다.\n"
        + tail
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n")


def _llm_smalltalk(input_text, recent_messages=None, facts=""):
    """[SMALLTALK/자유대화] 질문/잡담에 사람다운 답 — '나는 편집기라서'류 거절 금지
    (국장: 거절은 사용자를 바보 취급하는 것). 실패 시 None → 호출부가 따뜻한 고정 문구.
    [국장지시 2026-07-06] 편집 얘기가 아니어도 사용자의 화제를 진짜로 따라간다 —
    매 답을 편집 제안으로 되돌리지 않는다. facts=실제 날짜·작업 상황 블록(환각 봉쇄)."""
    prompt = _smalltalk_prompt(input_text, recent_messages, facts=facts)
    try:
        # temperature 0.7 — 대화는 결정성보다 자연스러움 (판사 경로와 분리)
        out = hub._ollama_json(prompt, timeout=30, temperature=0.7)
        return _sanitize_talk(str(out.get("reply") or "").strip())
    except Exception as e:
        print(f"[INTENT-ROUTER] smalltalk 실패 ({e})")
        return None


def stream_smalltalk(input_text, recent_messages=None, facts=""):
    """[F2 스트리밍] 자유대화 토큰 스트림 생성기.
    산출: ('token', 조각) 반복 → ('done', 전체문장) / 위생 위반·실패 시 ('abort', None).
    위생 규칙은 _sanitize_talk와 동일 기준을 누적문에 적용 — 위반 즉시 중단해
    호출부가 CCUT 고정 문구로 강등한다 (조용한 유출 금지)."""
    prompt = _smalltalk_prompt(input_text, recent_messages, facts=facts, plain=True)
    acc = ""
    try:
        for chunk in hub._ollama_stream(prompt, timeout=30, temperature=0.7):
            acc += chunk
            if _re_mod.search(r"[一-鿿]", acc) or \
               _re_mod.search(r"qwen|큐원|퀜|通义|阿里|알리바바", acc, _re_mod.IGNORECASE):
                print("[F2-STREAM] 위생 위반 감지 -> 중단·고정문구 강등")
                yield ("abort", None)
                return
            yield ("token", chunk)
    except Exception as e:
        print(f"[F2-STREAM] 스트림 실패 ({e}) -> 중단·고정문구 강등")
        yield ("abort", None)
        return
    yield ("done", acc.strip())


def route_edit_intent(source_ids=None, input_text="", recent_messages=None,
                      selected_proposal_id=None, allow_llm=True, person_vocab=None,
                      archive_lookup=None, search_lookup=None, fragment_labels=None,
                      defer_chat=False):
    t = (input_text or "").strip()
    if not t:
        return _resp("ask_clarification", "말씀을 조금만 더 입력해 주세요.", confidence=1.0)

    # ── 0. 아카이브 포함 승인 응답 [B안] — 직전 편집기 질문이 ask_include_archive였고
    #      사용자가 짧은 긍정("응, 포함해줘")이면, 그 직전 사용자 지시를 아카이브
    #      수용 모드로 재해석해 실행으로 전환한다.
    import re as _re
    _affirm = (len(t) <= 15
               and (_re.match(r"^(응|어+|네|예|그래|좋아|좋지|오케이|ok)\b", t, _re.IGNORECASE)
                    or t.startswith("포함")))
    if _affirm and recent_messages:
        _ask_seen = False
        _prev_user = None
        for m in reversed(recent_messages):
            txt = str(m.get("text") or "").strip()
            if not _ask_seen:
                if m.get("sender") != "user" and "아카이브까지 포함할까요" in txt:
                    _ask_seen = True
                continue
            if m.get("sender") == "user" and txt:
                _prev_user = txt
                break
        if _ask_seen and _prev_user:
            r0 = route_edit_intent(source_ids=source_ids, input_text=_prev_user,
                                   recent_messages=None, allow_llm=allow_llm,
                                   person_vocab=person_vocab,
                                   archive_lookup=archive_lookup)
            if r0.get("action") == "ask_include_archive":
                fids = r0.get("candidate_fragment_ids") or []
                rr = _resp("run_proposal",
                           f"네, 아카이브 조각까지 포함해서 골라볼게요 ({len(fids)}개).",
                           normalized=r0.get("normalized_instruction"),
                           confidence=0.9, matched=r0.get("matched"))
                rr.update({"filters": r0.get("filters"), "scope": "archive_included",
                           "candidate_fragment_ids": fids,
                           "include_source_ids": r0.get("candidate_sources") or [],
                           "by_program": r0.get("by_program") or {}})
                return rr
            return r0  # 그새 프로젝트에 생겼으면 그 결과 그대로

    # ── 0.65 의도 해제 [INTENT-CLEAR — #49 (a) 4단, 국장 승인 2026-07-17] —
    #    "전부 다시 봐줘"류 = 활성 의도 스택 초기화 + 무필터 복귀 (F4·§1-10: 승계가 감옥이 되면 안 된다).
    #    "처음부터 다시"는 재실행/해제가 애매 — 여기서 잡지 않고 clarification으로 (V 판정).
    if _re.match(
            r"^(조건\s*없이|기준\s*없이)?\s*(전부|전체|다)\s*(다시)?\s*"
            r"(보여\s*줘|봐\s*줘|봐줘|보자|보여주라)[.!~?\s]*$", t) or \
       _re.match(r"^기준\s*(을|를)?\s*(없애|빼|치워|지워)\s*(줘|주세요|라)?[.!~?\s]*$", t):
        return _resp("intent_clear",
                     "기준 없이 전체에서 다시 고를게요.",
                     confidence=0.9, via="deterministic",
                     matched={"kind": "intent_clear"})

    # ── 0.7 재실행 [RETRIGGER — #49 (a) 1·2단, 국장 승인 2026-07-17. 구 BARE-REDO 대체] —
    #    재실행 신호(다시·재·새로·한 번 더)만 있고 필터 명사(인물·장소·행위·길이·분위기)가 0개인
    #    문장은 '명령'이지 '의도'가 아니다 — 주제(open_theme)로 오해해 의도를 덮어쓰지 않는다
    #    (16:06 사건: "스토리 다시 편집하게 해줘" → open_theme 오분류 → keep=26/26 무필터).
    #    처리: 분류만 반환 — 직전 활성 의도의 승계/무의도 무필터+고지는 프론트가 결정(§5 표시 동반).
    #    계보: 구 BARE-REDO(07-05 "무단 재사용 금지→되묻기")를 승계+표시 설계가 대체 —
    #    승계 사실을 지휘부 채팅에 즉시 고지하므로 '무단'이 아니다.
    #    [#59 어미 틈 봉합] 동사군에 연결어미 활용형(만들어·골라서·뽑아) 추가 — 구판은
    #    어간만 수용해 "스토리 다시 만들어 줘"가 매칭 실패 → 5.5 OPEN-EDIT로 누출,
    #    open_theme(core='스토리')로 실행되며 활성 의도를 덮어썼다(16:06 잔여 실측).
    #    긴 형태 우선(만들어→만들) — 정규식 대안은 순서 매칭.
    if len(t) <= 24 and _re.match(
            r"^(그럼\s*)?(스토리|편집|제안|영상)?\s*(을|를)?\s*(다시|재|새로|한\s*번\s*더)\s*"
            r"(편집|제안|골라서|골라|만들어|만들|뽑아|뽑)?\s*(하게|하도록)?\s*"
            r"(해\s*줘|해줘|해\s*봐|해봐|부탁해?|줘|주세요|하자|할래|볼래|보자)?[.!~?\s]*$", t):
        return _resp("retrigger",
                     "직전 기준으로 다시 골라볼게요.",
                     confidence=0.9, via="deterministic",
                     matched={"kind": "retrigger"})

    # ── 0.5 조회/열람 [SHOW] — "보여줘/있나/찾아줘"는 편집이 아니라 보여주기다.
    #    편집 동사가 함께 있으면(예: "찾아서 편집해줘") 편집 사다리가 우선.
    #    결과 카드는 자체완결(제목·시간·썸네일·재생 URL) — 흐름에 남고 클릭=재생.
    if (_re.search(r"보여줘|보여 줘|있나\??|있냐|있어\?|있는지|찾아줘|찾아 줘|찾아봐|불러와|검색해|뭐가 있", t)
            and not _re.search(r"편집|골라줘|골라 줘|만들어|빼줘|빼 줘|줄여|늘려|남겨", t)):
        _person0 = hub.resolve_person_name(t, vocab=person_vocab)
        if search_lookup is not None:
            found = search_lookup(t, _person0)
        else:
            from engine.fragment_show import search_show
            found = search_show(t, _person0, source_ids)
        if found is not None:
            n = len(found.get("results") or [])
            who = found.get("person")
            if n == 0:
                reply = (f"{who} 나오는 조각을 아직 못 찾았어요." if who
                         else "조건에 맞는 조각을 못 찾았어요.")
                return _resp("show_fragments", reply, confidence=0.85, via="deterministic")
            scope = []
            if found.get("in_project"):
                scope.append(f"이 프로젝트 {found['in_project']}개")
            if found.get("in_archive"):
                scope.append(f"아카이브 {found['in_archive']}개")
            head = f"{who} 나오는 조각" if who else "조건에 맞는 조각"
            reply = (f"{head} {n}개를 찾았어요 ({', '.join(scope)}). "
                     "카드를 누르면 바로 볼 수 있어요.")
            r = _resp("show_fragments", reply, confidence=0.9, via="deterministic",
                      matched={"kind": "show", "person": who})
            r["results"] = found["results"]
            return r
        # 판단 불가(검색어 추출 실패 등) → 아래 사다리 계속

    # ── 0.55 [조각 라벨 지정 편집 국장지시 2026-07-06] "K1,K4,K6만으로 편집해줘" —
    #    조각맵 타일 라벨(display_id)로 조각을 지목하는 편집. 프론트가 동봉한
    #    fragment_labels(라벨→조각ID)로 해석해 그 조각들만 후보로 실행한다.
    #    모르는 라벨은 실행하지 않고 정직 보고 (날조 실행 사건 봉쇄: "정은한..." 지어내기).
    _label_hits = _re.findall(r"[A-Za-z]{1,2}\d{1,3}", t)
    if _label_hits and _re.search(r"만으로|으로만|만 가지고|편집|골라|구성|묶|모아|합쳐|넣|빼|제외|말고|없이", t):
        _lmap = {str(k).upper(): v for k, v in (fragment_labels or {}).items()}
        _asked = []
        for _h in _label_hits:  # 순서 보존 + 중복 제거
            _u = _h.upper()
            if _u not in _asked:
                _asked.append(_u)
        if not _lmap:
            return _resp("answer_only",
                         "조각 번호로 지정하는 편집은 조각맵 라벨 연결이 필요한데, 지금 "
                         "화면에서 매핑을 받지 못했어요. 조각맵에서 해당 조각을 직접 "
                         "클릭해 다뤄주시거나, 조건(인물·장면)으로 말씀해 주세요.",
                         confidence=0.9, matched={"kind": "fragment_labels_unavailable"})
        _known = [u for u in _asked if u in _lmap]
        # 미지 라벨 보고는 단일 문자 접두(진짜 타일 형태 "K1")만 — "MP4"/"H264" 같은
        # 파일 포맷 토큰이 "조각맵에 없는 번호"로 오탐되지 않게
        _unknown = [u for u in _asked
                    if u not in _lmap and _re.match(r"^[A-Z]\d{1,3}$", u)]
        if _known:
            _is_excl = bool(_re.search(r"빼|제외|말고|없이", t))
            if _is_excl:
                _excl_ids = {_lmap[u] for u in _known}
                _fids = [v for k, v in _lmap.items() if v not in _excl_ids]
                # 시간순 아님(사전순)이지만 후보군 제약 목적이라 순서 무관 — 판사가 배치
                _desc = f"{', '.join(_known)}를 뺀 나머지 조각 {len(_fids)}개"
                _norm = f"지정 조각({', '.join(_known)})을 제외한 나머지로 구성"
            else:
                _fids = [_lmap[u] for u in _known]
                _desc = f"조각 {', '.join(_known)} ({len(_fids)}개)"
                _norm = f"지정한 조각({', '.join(_known)})만 전부 사용해 구성"
            if not _fids:
                return _resp("ask_clarification",
                             "그렇게 빼면 남는 조각이 없어요. 다른 기준으로 말씀해 주세요.",
                             confidence=0.9, matched={"kind": "fragment_labels_empty"})
            _warn = (f" (참고: {', '.join(_unknown)}은 조각맵에 없어 뺐어요)"
                     if _unknown else "")
            r = _resp("run_proposal",
                      f"네, {_desc}만 가지고 골라볼게요.{_warn}",
                      normalized=_norm, confidence=0.95, via="deterministic",
                      matched={"kind": "fragment_labels", "labels": _known,
                               "unknown": _unknown, "exclude": _is_excl})
            r["candidate_fragment_ids"] = _fids
            return r
        if _unknown:
            _avail = ", ".join(sorted(_lmap.keys())[:12])
            return _resp("ask_clarification",
                         f"{', '.join(_unknown)}은 지금 조각맵에 없는 번호예요. "
                         f"현재 있는 조각: {_avail}{'…' if len(_lmap) > 12 else ''}. "
                         "다시 지정해 주시겠어요?",
                         confidence=0.9,
                         matched={"kind": "fragment_labels_unknown", "unknown": _unknown})

    # ── 0.6 [실행 사칭 금지 국장승인 2026-07-06 B안] 프레임 단위 미세조정·복원 요청은
    #    이 경로에 능력이 없다 — 재제안을 돌리며 "잘랐습니다"라고 사칭하던 사건
    #    (B안 3조각→1조각 2초 파괴) 봉쇄. 실존 기능(정밀편집창·지난 제안 다시 열기)으로
    #    정직하게 안내만 한다. 제안 실행 없음.
    if _re.search(r"프레임", t) and _re.search(r"잘라|자르|빼|다듬|트림|제거", t):
        return _resp("answer_only",
                     "프레임 단위 정밀 조정은 채팅으로는 아직 못 해요 — 제가 자를 수 있는 "
                     "단위가 아니라서, 한 것처럼 말씀드리지 않을게요. 조각을 클릭하면 열리는 "
                     "정밀편집창에서 직접 프레임을 다듬으실 수 있어요. 지금 안은 그대로 둡니다.",
                     confidence=0.95, matched={"kind": "honest_no_frame_trim"})
    if _re.search(r"되돌려|원래대로|복원|원상복구", t) or \
            _re.search(r"(원본|이전|아까|지난)\s*(조각|안|제안|버전).{0,8}(다시|가져와|돌려|살려)", t):
        return _resp("answer_only",
                     "새로 고르지 않고 그대로 되살리는 건 채팅 아래 '지난 제안 다시 열기'에서 "
                     "할 수 있어요 — 원하시는 세대를 누르면 그 안이 그대로 돌아옵니다. "
                     "지금 안은 건드리지 않을게요.",
                     confidence=0.95, matched={"kind": "honest_restore_hint"})

    # ── 0.78 [#57 REVISION 도구층] 명시 타겟 국소 수정 — "B안에서 두 번째 조각 빼줘".
    #    'X안에서'로 기존 안 수정 문맥이 명시되면 인물/어휘 사다리보다 먼저 —
    #    새 제안(전체 재제안)으로 뭉개지 않는다. 이해=큐원 폴백, 집행 op=규칙 검증.
    from engine import revision as _revm
    if _revm.revision_enabled() and _revm.detect_target_mode(t):
        _rev0 = _revm.detect_revision_full(t, True, allow_llm=allow_llm)
        if _rev0:
            r = _resp("revise_current", _revision_reply(_rev0), normalized=t,
                      confidence=0.9, via=_rev0.get("via", "deterministic"),
                      matched={"kind": "revision", "op": _rev0["op"]})
            r["revision"] = _rev0
            return r

    # ── 0.8 정체성 질문 — 결정론 자기소개 최우선 (Qwen 자백 사건 봉쇄).
    #    대화 게이트보다 먼저: 정체성은 LLM으로 새지 않고 고정 문구로 답한다.
    if _re.search(r"(너|네|니)가?\s*누구|누군지|누구야|누구니|정체|이름이 뭐|뭐 ?하는 (ai|애|친구|프로그램)", t):
        return _resp("answer_only",
                     "저는 CCUT이에요 — 올려주신 영상을 조각으로 나눠 이해하고, "
                     "말씀 한마디로 골라 편집해 드리는 편집 동료예요. "
                     "'생일잔치 장면만'처럼 말씀하시면 바로 움직이고, "
                     "궁금한 건 뭐든 물어보셔도 좋아요.",
                     confidence=0.9, matched={"kind": "self_intro"})

    # ── 0.9 [문맥 우선 국장지시 2026-07-06] 대화 신호가 있으면 정규식 사다리를
    #    타지 않는다 — 종업원 LLM이 문맥(최근 대화·실제 날짜·작업 상황)을 보고
    #    "이건 대화 / 이건 편집지시"를 스스로 판단한다.
    #    ("응 지금 너를 만들고 잇는데" → '만들'·'진행' 정규식이 편집으로 납치하던 사건,
    #     "오늘 몇일이지?" → 날짜 모른 채 22일 환각 사건 — 실데이터 주입으로 봉쇄)
    #    짧은 승인어("좋아")는 제외 — 제안 확정 흐름은 기존 사다리가 처리.
    #    LLM 불가(allow_llm=False) 시엔 편집 표지가 있으면 게이트를 건너뛴다 —
    #    "생일잔치만 편집해줄래?"(질문꼴 편집요청)는 결정론 모드에서 편집 우선(L0 골든).
    if _CHAT_SIGNAL_RE.search(t) and not _AFFIRM_SHORT_RE.match(t) \
            and (allow_llm or not _EDIT_MARK_RE.search(t)):
        if allow_llm:
            und = _llm_understand(t, recent_messages, source_ids, person_vocab,
                                  defer_chat=defer_chat)
            if und:
                return und
        # hub 미응답/비활성 — 편집 강요 없이 정직한 수신 확인
        return _resp("answer_only",
                     "네, 듣고 있어요. 편하게 이야기해 주세요 — 편집이 필요해지면 "
                     "'생일잔치 장면만'처럼 말씀하시면 바로 움직일게요.",
                     confidence=0.7, matched={"kind": "free_chat_fallback"})

    # ── 1. 인물/장소 filters 수집 (사람을 만나도 즉시 return 금지 — 복합 조건 유지) ──
    from engine import place_taxonomy as pt
    person = hub.resolve_person_name(t, vocab=person_vocab)
    place = pt.resolve_place_query(t)
    is_excl = any(k in t for k in hub._EXCLUDE_MARK) or "아닌" in t

    if person:
        canonical, matched = person["canonical"], person["matched"]
        normalized = replace_name(t, matched, canonical)
        filters = [{"type": "person", "value": canonical,
                    "source": "alias" if matched != canonical else "name",
                    "matched": matched}]
        alias_prefix = (f"아, {matched} — {canonical} 말씀이시죠. "
                        if matched != canonical else "")

        # ── 1a. 인물+장소 복합 → 아카이브 교집합 검색 (현재 프로젝트 우선) ──
        # 장소-단독은 여기로 오지 않는다: 라벨 커버리지(파생 캐시)로 사전필터하면
        # 기존 전체풀 judge 대비 리콜이 후퇴하므로, 교집합이 목적일 때만 쓴다.
        if place and not is_excl:
            filters.append({"type": "place", "value": place["code"],
                            "label": place["label"], "matched": place["matched"]})
            lookup = archive_lookup
            if lookup is None:
                from engine.archive_query import query as lookup
            found = lookup(filters, project_source_ids=source_ids)
            base = {"normalized": normalized, "matched": filters[0],
                    "confidence": person.get("confidence", 0.95)}
            extra = {"filters": filters, "scope": found.get("scope"),
                     "candidate_fragment_ids": found.get("fids") or [],
                     "candidate_sources": found.get("sources") or [],
                     "by_program": found.get("by_program") or {},
                     "coverage": found.get("coverage")}
            if found.get("scope") == "project":
                r = _resp("run_proposal",
                          f"{alias_prefix}{canonical} + {place['label']} 조건으로 "
                          f"{len(found['fids'])}개 찾았어요. 그 조각들로 다시 골라볼게요.",
                          via="deterministic", **base)
                r.update(extra)
                return r
            if found.get("scope") == "archive":
                progs = ", ".join(f"{k} {v}개" for k, v in
                                  sorted(found["by_program"].items(), key=lambda x: -x[1])[:3])
                r = _resp("ask_include_archive",
                          f"{alias_prefix}지금 프로젝트에는 {canonical}+{place['label']} 조각이 없고, "
                          f"아카이브에 있어요 ({progs}). 아카이브까지 포함할까요?",
                          via="deterministic", **base)
                r.update(extra)
                return r
            # scope none — C/D 분기 (정직 안내, 조용한 성공 처리 금지)
            cov = found.get("coverage") or {}
            if (cov.get("place_labeled") or 0) * 3 < (cov.get("total") or 1):
                msg = (f"{alias_prefix}아직 장소 라벨이 부족해요"
                       f"(라벨 {cov.get('place_labeled', 0)}/{cov.get('total', 0)}조각). "
                       f"대표 프레임 장소 분석을 먼저 돌릴까요?")
            else:
                msg = (f"{alias_prefix}{canonical} 조각은 있지만 "
                       f"'{place['label']}' 장소 라벨이 붙은 조각이 없습니다.")
            r = _resp("ask_clarification", msg, via="deterministic", **base)
            r.update(extra)
            return r

        # ── 1b. 인물 단독 ──
        # [고리① ③ — QWEN-R1] 인물 밖 내용어가 남으면("심장 시술") 인물-단독으로
        # 확정하지 않는다 — 사다리를 계속 타서 OPEN-EDIT/큐원이 전체 문맥을 보존한다.
        # §5: 실제로는 인물만 고르지 않을 것이므로 "인물만 골라볼게요"라고 말하지 않는다.
        _residue = hub._person_shadow_residue(t, [matched])
        if _residue and not is_excl:
            print(f"[INTENT-ROUTER] person+잔여 {_residue!r} -> 인물단독 미확정, "
                  f"정규화({matched}->{canonical})만 승계하고 사다리 계속")
            t = normalized
        else:
            if matched != canonical:
                reply = (alias_prefix
                         + (f"{canonical} 나오는 장면은 빼고 다시 골라볼게요." if is_excl
                            else f"그 사람이 나오는 장면만 다시 골라볼게요."))
            else:
                reply = (f"네, {canonical} 나오는 장면은 빼고 다시 골라볼게요." if is_excl
                         else f"네, {canonical} 나오는 장면만 다시 골라볼게요.")
            r = _resp("run_proposal", reply, normalized=normalized,
                      confidence=person.get("confidence", 0.95),
                      matched={"kind": "person_alias" if matched != canonical else "person",
                               "input": matched, "canonical": canonical,
                               "person_id": person.get("person_id")})
            r["filters"] = filters
            return r

    # ── 2. 장면/개수/제외 어휘 (기존 결정론 그대로 신뢰) ──
    det = hub._deterministic_intent(t)
    if det.get("theme_found") or det.get("count"):
        theme = det.get("keep") or det.get("exclude")
        if det.get("exclude"):
            reply = f"네, '{theme}' 장면은 빼는 방향으로 다시 골라볼게요."
        elif theme:
            reply = f"네, '{theme}' 조건으로 다시 골라볼게요."
        else:
            reply = f"네, 조각 {det['count']}개 기준으로 다시 골라볼게요."
        return _resp("run_proposal", reply, normalized=t, confidence=0.9,
                     matched={"kind": "vocab", "keep": det.get("keep"),
                              "exclude": det.get("exclude"), "count": det.get("count")})

    # ── 3. 템포/확정 표현 ──
    import re
    if re.search(r"빠르게|느리게|짧게|길게|템포|속도|페이스", t):
        return _resp("run_proposal", "네, 흐름 속도를 조정해서 다시 골라볼게요.",
                     normalized=t, confidence=0.85, matched={"kind": "pace"})
    # [앵커링 2026-07-06] 확정은 짧은 순수 승인문만 — "잘 진행되고 있어" 같은
    # 서술문 속 '진행'이 확정으로 오인되던 납치 봉쇄
    if len(t) <= 12 and re.match(
            r"^(이대로|그대로|지금 ?방향)?\s*(진행|확정|좋아|오케이|ok)\s*(해줘|해|하자|요)?[.!~\s]*$",
            t, re.IGNORECASE):
        return _resp("run_proposal", "네, 지금 방향 그대로 진행하겠습니다.",
                     normalized=t, confidence=0.85, matched={"kind": "confirm"})

    # ── 4. 현재 안 국소 수정 [#57 REVISION 도구층 — 게이트 기본 ON 격상] ──
    #    선택된 안이 있으면 서수/개수/테마 수정 명령을 국소 집행으로 — op를 동봉해
    #    프론트가 /revision/proposals 를 부른다 (구판: action만 반환 → 전체 재제안 수렴).
    if selected_proposal_id and _revm.revision_enabled():
        try:
            _rev4 = _revm.detect_revision_full(t, True, allow_llm=allow_llm)
            if _rev4:
                r = _resp("revise_current", _revision_reply(_rev4), normalized=t,
                          confidence=0.85, via=_rev4.get("via", "deterministic"),
                          matched={"kind": "revision", "op": _rev4["op"]})
                r["revision"] = _rev4
                return r
        except Exception as _rev_err:
            print(f"[P3-REV][WARN] ladder4 실패 ({_rev_err}) -> 기존 사다리 계속")

    # ── 5. 질문/잡담 2차 그물 — 게이트(0.9)를 지나쳤지만 의문형인 말.
    #    편집 동사가 있으면("생일잔치만 편집해줄래?") 질문 꼴이어도 편집으로 —
    #    아래 5.5 OPEN-EDIT가 처리하게 통과시킨다. (정체성 질문은 0.8에서 처리 완료)
    q_re, vague_re = _regexes()
    if q_re.search(t) and not _re.search(r"편집|나오게|남게|남겨|골라|만들|빼|줄여|늘려|위주|중심|모아|추려", t):
        if allow_llm:
            # [F2 스트리밍] 질문 그물의 대화 생성도 defer 시 표식만 — 스트림이 생성
            if defer_chat:
                r = _resp("answer_only", "", confidence=0.8, via="qwen",
                          matched={"kind": "smalltalk"})
                r["_stream_chat"] = {"facts": ""}
                return r
            _talk = _llm_smalltalk(t, recent_messages)
            if _talk:
                return _resp("answer_only", _talk, confidence=0.8, via="qwen",
                             matched={"kind": "smalltalk"})
        return _resp("answer_only",
                     "그럼요, 편하게 말씀하세요. 저는 영상 편집을 돕는 CCUT이에요 — "
                     "궁금한 건 뭐든 물어보시고, 편집은 '생일잔치 장면만'처럼 "
                     "말씀하시면 바로 움직일게요.",
                     confidence=0.8)
    if vague_re.search(t):
        if allow_llm:
            llm = _llm_understand(t, recent_messages, source_ids, person_vocab,
                                  defer_chat=defer_chat)
            if llm:
                return llm
        return _resp("ask_clarification",
                     "어떤 기준으로 고를지 조금만 더 구체적으로 말씀해 주세요 — "
                     "예: '정은한 나오는 장면만', '실내만', '더 빠르게'.",
                     confidence=0.7)

    # ── 5.5 [OPEN-EDIT] 편집 동사 + 내용어가 있으면 거절하지 않는다 — 해석은 판사가.
    #    메뉴판(인물/장소/개수/템포)에 없는 말이라도 편집 요청이 명확하면 원문 그대로
    #    hub 판사(조각 서술 기반 LLM 판단)에 넘긴다 (국장 지적 2026-07-05:
    #    "생일잔치 장면만 나오게 해줘"가 되묻기로 거절된 사건 — 정해지지 않은 요구에
    #    해석·인식으로 반응). 조건 미달이면 하류의 정직한 빈 제안이 설명한다.
    if _re.search(r"편집|나오게|남게|남겨|골라|만들|위주|중심|모아|추려|빼|줄여|늘려|장면만|컷만|부분만", t):
        _core = _re.sub(
            r"(의)?\s*(장면|부분|컷|것|영상|조각)?\s*(만|들만|을|를|이|가|으로|로)?\s*"
            r"(나오게|남게|보이게)?\s*(위주로|중심으로)?\s*(다시)?\s*(편집|모아|골라|추려|만들어|남겨)?\s*"
            r"(해\s*줘|해줘|해\s*봐|해봐|줘|주세요|부탁해?)?[.!?~\s]*$", "", t).strip()
        if len(_core) >= 2:
            return _resp("run_proposal",
                         f"네, \"{_core}\" 기준으로 골라볼게요. 맞는 조각이 없으면 솔직히 말씀드릴게요.",
                         normalized=t, confidence=0.75, via="deterministic",
                         matched={"kind": "open_theme", "core": _core})

    # ── 6. 결정론이 전부 놓친 말 → Qwen 종업원 ──
    if allow_llm:
        llm = _llm_understand(t, recent_messages, source_ids, person_vocab,
                              defer_chat=defer_chat)
        if llm:
            return llm
    # [국장지시 2026-07-06] 못 알아들어도 편집 조건을 강요하지 않는다 — 대화도 정상 경로
    return _resp("ask_clarification",
                 "제가 정확히 못 알아들었어요. 편하게 다시 말씀해 주세요 — "
                 "그냥 이야기하셔도 좋고, 편집은 '누가 나오는 장면만'처럼 "
                 "말씀하시면 바로 움직여요.",
                 confidence=0.5)
