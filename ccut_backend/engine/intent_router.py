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
_CONTEXT_COMMAND_RE = _re_mod.compile(
    r"다시\s*해\s*줘|아까\s*그거|방금\s*말한\s*거|그거\s*말고|취소|되돌려|undo",
    _re_mod.IGNORECASE)
_OPEN_EDIT_RE = _re_mod.compile(
    r"편집|나오게|남게|남겨|골라|만들|위주|중심|모아|추려|빼|줄여|늘려|장면만|컷만|부분만")
_OPEN_EDIT_META_RE = _re_mod.compile(
    r"잘\s*모르|모르겠|생소|궁금|어떻게|뭐지|무엇|뭔지|왜|배웠|얘기는\s*나중|나중에\s*하고|"
    r"좋은\s*건지|좋은건지|어울리는\s*건지|어울리는건지|사용해야\s*하는\s*건지|"
    r"사용하는지|[?？]")
_OPEN_EDIT_REQUEST_RE = _re_mod.compile(
    r"해\s*줘|해줘|해\s*줄래|해줄래|해\s*주세요|해주세요|해\s*봐|해봐|"
    r"만들어\s*줘|만들어줘|골라\s*줘|골라줘|모아\s*줘|모아줘|추려\s*줘|추려줘|"
    r"남겨\s*줘|남겨줘|빼\s*줘|빼줘|줄여\s*줘|줄여줘")

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


def _history_prefix_pattern():
    return os.getenv(
        "CCUT_RECENT_MESSAGE_PREFIX_RE",
        r"^\s*(?:(?:CCUT|AI|Assistant|User|사용자|어시스턴트)\s*[:：]\s*)+",
    )


def _clean_recent_text(text):
    """Strip speaker prefixes from stored chat history before prompt injection."""
    raw = str(text or "")
    try:
        return _re_mod.sub(_history_prefix_pattern(), "", raw).strip()
    except _re_mod.error:
        return _re_mod.sub(
            r"^\s*(?:(?:CCUT|AI|Assistant|User|사용자|어시스턴트)\s*[:：]\s*)+",
            "",
            raw,
        ).strip()


def _last_user_edit_instruction(recent_messages):
    """Return the last user edit instruction exactly as typed, if one is present."""
    for m in reversed(recent_messages or []):
        if m.get("sender") != "user":
            continue
        txt = str(m.get("text") or "").strip()
        if not txt:
            continue
        if _EDIT_MARK_RE.search(txt) or _re_mod.search(
                r"위주|중심|나오는|나온|장면|영상|조각|클립|컷|모아|골라|추려|만들|남겨|빼|줄여|늘려",
                txt):
            return txt
    return None


def _bare_redo_clarification(prev_instruction=None):
    if prev_instruction:
        return f"방금 말씀하신 '{prev_instruction}' 기준으로 다시 할까요? 맞으면 '응'이라고 답해 주세요."
    return "무엇을 다시 할까요? 다시 적용할 기준을 한 번만 말씀해 주세요."


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


# [MIRROR-FIX-1] facts 블록(:177-188)이 수첩이 있을 때만 덧붙이는 읽기 지시문.
#   자유대화 프롬프트에서 수첩 줄을 들어낼 때 이 지시문도 함께 들어내야
#   "없는 블록을 읽어라"가 남지 않는다. ★블록 원문은 수정 금지라 여기서 참조만 한다.
_MIRROR_READ_CLAUSE = " [수첩 요약]은 mirror_ledger의 pass/correction 집계값으로만 읽어라.\n"


def _mirror_summary_fact(project_id):
    project_id = str(project_id or "").strip()
    if not project_id:
        return ""
    try:
        from mirror_ledger import format_summary_fact_line, summarize_project
        line = format_summary_fact_line(summarize_project(project_id))
    except Exception:
        return ""
    return (line + "\n") if line else ""


# [CHAT-EYES 2026-08-02] 자유 대화용 조각 근거 블록 — ★상한을 두고 발췌만 싣는다.
#   왜 이 방식인가(갈래 ㄱ):
#     갈래 ㄴ(_qwen_tools 안내에 조각·시각 테이블 추가)은 목표에 못 닿는다.
#     _qwen_tool_show 는 `if _show_subject:` 안에서만 불린다(:783). 자유 대화는
#     거기까지 가지 않으므로 안내 테이블을 아무리 늘려도 chat 분기에는 0건이다.
#   ★전문 금지: 조각당 scene 60자 · 전사 60자 발췌. 건수 상한 _EVID_MAX.
#   ★없으면 없다고 말할 수 있게 실패를 표지로 남긴다(8/2 실측: 표지 없으면 7B 3/3 날조).
#   ★검색은 기존 fragment_search(임베딩 + FTS bm25 보너스)를 그대로 쓴다. 새 검색 안 만든다.
#     실측(Merope, 2026-08-02): "바닷가"·"바닷가 장면"·"바다" 모두 정답 6조각을 상위 6/6 으로
#     집었다. visual_desc 가 영어("beach, sand, ocean")라 한국어 LIKE 로는 0건인데
#     다국어 임베딩이 건넌다 — 그래서 키워드가 아니라 이 검색을 쓴다.
_EVID_MAX = 8            # 프롬프트에 싣는 조각 최대 건수
_EVID_POOL = 3000        # 검색 후보 상한 — 사실상 전수(현재 fragment_index 936).
                         # 프로젝트 필터를 뒤에 걸므로 여기서 자르면 개수가 왜곡된다.
# [FRAG-TRUTH 2026-08-02] 문턱을 세 방에서 다시 쟀다 (Merope · Freesia · Adhara × 질문 5종).
#   ★있는 것 top   바닷속잠수 0.589 / 0.642 / 0.589   바닷가 0.598 / 0.526 / 0.598
#   ★없는 것 top   식당       0.322 / 0.340 / 0.333   파인애플 0.170 / 0.252 / 0.231
#   두 무리가 0.34 ↔ 0.53 으로 크게 벌어진다. 그 사이 어디에도 표본이 없다.
#   그래서 ★한 숫자로 있다/없다를 가르지 않고 대역을 둔다:
#     top >= _EVID_SURE      있다        (그 아래 _EVID_CUT 까지를 목록으로)
#     top <  _EVID_ZERO      없다
#     그 사이               ★확실하지 않다 — 억지로 고르지 않는다
#   ★계수 문턱 0.48 근거 — 표본에 곡선을 맞춘 게 아니라 ★알려진 정답을 자르지 않는 하한이다.
#     Merope "바닷가"의 정답 5조각(`_P00N` 병합 후)은 장면 설명에 beach 가 명시돼 있고
#     점수가 0.49 ~ 0.61 이다. 컷을 0.50 으로 두면 그중 SF_89D736(0.49,
#     "beach, sand, water, girl")이 잘려 4개가 되고, 국장이 조각맵에서 센 5개와 어긋난다.
#     0.48 은 그 정답을 살리는 가장 높은 자리다.
#     ★그래도 검색의 오탐·누락은 남는다 — 그래서 아래 UNCERTAIN 대역을 함께 둔다.
_EVID_CUT = 0.48         # 목록·계수에 넣는 최소 점수
_EVID_ZERO = 0.45        # 최고점이 이 아래면 '없다'
_EVID_SURE = 0.53        # 최고점이 이 위면 '있다'


# [FRAG-TRUTH 2026-08-02] CCUT 규약: `_P00N` 형제는 한 조각이다.
#   규칙 출처 — proposal_engine.py:694 ProposalEngine._semantic_group_key
#     """SF_CD37EA_SRC_616AEFBA_P001 -> SF_CD37EA_SRC_616AEFBA
#        마지막 _P001, _P002 같은 part suffix를 제거해 같은 semantic group으로 묶는다."""
#   그 메서드는 무거운 엔진 클래스에 붙어 있어 여기서 import 하지 않고 ★같은 정규식을 쓴다.
#   (semantic_engine.py:1075 "_P00N 형제는 같은 base 를 유지한다" 와 같은 규약)
#   ★왜 여기서 병합하나: 안 하면 큐원이 세는 수와 국장이 조각맵에서 세는 수가 갈린다.
#     실측(Merope "바닷가"): DB 행 6 · 병합 5 · ★국장이 화면에서 센 수 5.
#     개수를 모델에게 세게 하지 않는다 — ★서버가 병합해서 목록 자체를 정답으로 만든다.
def _sf_group(fid):
    return _re_mod.sub(r"_P\d+$", "", str(fid or ""))


def _evid_snip(s, n=60):
    # ★이 모듈은 모듈 레벨에 `re` 가 없다(함수 안 지역 import 관행). _re_mod 를 쓴다.
    t = _re_mod.sub(r"\s+", " ", str(s or "")).strip()
    # ★전사 꼬리에 붙은 조각 id(VF1_SRC_… )를 뗀다. 그대로 두면 큐원이 그 id 를
    #   답에 옮겨 적어 "실재하지 않는 id" 처럼 보인다(B-2 오판 유발).
    t = _re_mod.sub(r"\b[A-Z]{1,3}\d*_SRC_[0-9A-Za-z_]+", "", t).strip()
    return t[:n]


# [FRAG-TRUTH 2026-08-02] 조각을 묻는 말인가 — 잡담과 가른다.
#   ★왜 필요: 상태=없음을 그대로 "없습니다"로 답하면 "오늘 하루 어땠어?" 에도 없다고 한다.
#     조각 소재(조각·장면·영상…)를 묻고 존재/개수를 묻는 말일 때만 서버가 단정한다.
_FRAG_NOUN = r"조각|장면|영상|클립|컷|사진|화면|소스|원본"
_FRAG_ASK = r"있|없|몇|개수|얼마나|알려|찾|보여|나오"


def _is_fragment_question(t):
    t = str(t or "")
    return bool(_re_mod.search(_FRAG_NOUN, t) and _re_mod.search(_FRAG_ASK, t))


# [FRAG-TRUTH 2026-08-03] 임베딩이 놓친 것을 ★전사 낱말로 건진다.
#   국장 화면이 증명한 실패: "식당에서 식사하는 영상 있나?" 에 "못 찾았어요"라고 답했는데
#   SRC_3111FA4F 에 식사 장면이 ★실제로 있었다 —
#     SF_6C6CF9 "…손가락에 분명히 먹을 거 들어있을 건데? 아침에 식사도 하신다고…"
#     SF_6D6452 "한 번 잘라서 맛을 볼까요? … 맛이 있을까?"
#   임베딩 top 은 0.34 였다. 장면 설명(visual_desc)이 영어라 '식사'가 시각 쪽에 없고,
#   전사 쪽 신호는 FTS 보너스 0.15 뿐인데 그 FTS 는 질문 ★문장 전체로 매칭을 시도해
#   한국어 조사("식사도")를 못 넘는다.
#   ★그래서 의미검색 하나에 맡기지 않는다. 질문의 내용어로 전사·장면을 직접 훑는다.
#     낱말이 실제로 전사에 있으면 그것은 점수가 아니라 ★사실이다 — 무조건 건진다.
#   ★기능어를 막지 않으면 "있어" 가 전사의 "있어" 에 걸려 없는 것을 있다고 한다
#     (실측: "혹시 파인애플 본 적 있어?" -> Freesia 에서 4건 오탐).
_TOK_STOP = {"영상", "조각", "장면", "클립", "사진", "화면", "소스", "원본", "프로젝트",
             "지금", "여기", "그거", "이거", "저거", "어떤", "무슨", "누가", "언제",
             "혹시", "정말", "진짜", "그냥", "좀더", "다시", "모두", "전부", "얼마",
             # 존재·요청·의문 기능어 — 전사에 흔해서 아무거나 걸린다
             "있나", "있어", "있는", "있을", "있다", "없나", "없어", "없는", "없다",
             "알려", "보여", "찾아", "말해", "어때", "어떻", "그런", "이런", "저런",
             "하는", "하고", "해줘", "주세", "인지", "인가", "될까", "몇개", "개수",
             "본적", "적이", "적있", "한번", "번쯤", "정도", "대해", "관련", "포함"}


def _content_tokens(q):
    """질문에서 내용어 후보. 한국어 조사를 못 떼므로 ★접두 부분문자열을 함께 본다."""
    out = []
    for w in _re_mod.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", str(q or "")):
        if w in _TOK_STOP:
            continue
        # "식당에서" -> 식당에서·식당에·식당 / "식사하는" -> 식사하는·식사하·식사
        for n in range(len(w), 1, -1):
            p = w[:n]
            if len(p) >= 2 and p not in _TOK_STOP:
                out.append(p)
    # 긴 것부터, 중복 제거
    seen, uniq = set(), []
    for t in sorted(set(out), key=len, reverse=True):
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq[:24]


def _transcript_hits(tokens, sids, limit=60):
    """전사·장면에 그 낱말이 실제로 든 조각. 점수가 아니라 사실이다."""
    if not tokens or not sids:
        return {}
    import sqlite3 as _sq
    found = {}
    try:
        con = _sq.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                          uri=True, timeout=10)
    except Exception:
        return {}
    try:
        ph = ",".join("?" * len(sids))
        for t in tokens:
            if len(found) >= limit:
                break
            rows = con.execute(
                f"""SELECT sf.fragment_id, sf.source_id, sf.start, sf."end",
                           fi.visual_desc, fi.transcript
                    FROM semantic_fragments sf
                    JOIN fragment_index fi ON fi.fragment_id = sf.fragment_id
                    WHERE sf.source_id IN ({ph})
                      AND (fi.transcript LIKE ? OR fi.visual_desc LIKE ?)
                    LIMIT ?""",
                list(sids) + [f"%{t}%", f"%{t}%", limit]).fetchall()
            for fid, sid, s, e, vd, tr in rows:
                if fid not in found:
                    found[fid] = {"fragment_id": fid, "source_id": sid,
                                  "start": s, "end": e, "visual_desc": vd,
                                  "transcript": tr, "score": 1.0, "_kw": t}
    except Exception as ex:
        print(f"[FRAG-TRUTH][WARN] 전사 낱말 조회 실패 ({ex})")
    finally:
        con.close()
    return found


# [COUNT-TRUTH 2026-08-03] 근거 주입·상태 즉답을 한 쌍으로 묶는다.
#   같은 두 줄이 네 곳(chat 분기 · speed bypass · 대화신호 그물 · 질문 그물)에 필요해서
#   ★한 곳에 두고 부른다 — 네 곳이 서로 다르게 굴면 그것이 다음 '네 수 갈림'이 된다.
def _evidence_facts(t, source_ids=None):
    try:
        return _fragment_evidence(t, source_ids)[2] or ""
    except Exception as e:
        print(f"[COUNT-TRUTH][WARN] 근거 주입 실패 ({e})")
        return ""


def _zero_or_uncertain_reply(t, source_ids=None):
    """조각을 묻는 말이고 없음/애매함이면 ★서버가 낼 고정 문구. 아니면 None."""
    try:
        if not _is_fragment_question(t):
            return None
        state, _total, _blk = _fragment_evidence(t, source_ids)
        if state == "ZERO":
            return "그런 조각은 이 프로젝트에서 못 찾았어요."
        if state == "UNCERTAIN":
            return ("확실하지 않습니다. 비슷해 보이는 조각은 있는데 찾으시는 것과 "
                    "맞는지 자신이 없어요. 어떤 장면인지 한 가지만 더 알려주시겠어요?")
    except Exception as e:
        print(f"[COUNT-TRUTH][WARN] 상태 판정 실패 ({e})")
    return None


def _fragment_evidence(input_text, source_ids=None):
    """(state, total, block) — state 는 HAVE / ZERO / UNCERTAIN / SKIP.
    ★판정은 여기서 끝난다. 모델에게 '세어라'·'없으면 없다고 해라'를 시키지 않는다.
    앞 차수(9db84b86)에서 그 방식으로 두 번 실패했다 — 한쪽을 고치면 반대쪽이 죽었다."""
    q = str(input_text or "").strip()
    if not q:
        return ("SKIP", 0, "")
    sids = {str(s) for s in (source_ids or []) if s}
    if not sids:
        return ("SKIP", 0, "")
    try:
        from engine import fragment_search as _fs
        # ★후보를 넉넉히 받아 ★프로젝트로 먼저 좁힌 뒤 문턱으로 자른다.
        #   구판은 전역 top 120 을 받아 프로젝트 필터를 나중에 걸었다 — 그러면 개수가
        #   '다른 프로젝트가 상위를 얼마나 차지했나'에 좌우된다(실측: 같은 질문·같은 방에서
        #   pool 120 이면 5건, pool 400 이면 13건). 개수를 답할 거면 그 우연을 없애야 한다.
        res = _fs.search(q, top_k=_EVID_POOL)
        mine = [r for r in (res.get("results") or []) if str(r.get("source_id")) in sids]
        top = max((float(r.get("score") or 0) for r in mine), default=0.0)
        hits = [r for r in mine if float(r.get("score") or 0) >= _EVID_CUT]
        # ★전사에 그 낱말이 실제로 든 조각은 점수와 무관하게 건진다.
        #   의미검색이 놓쳐도 낱말이 거기 있으면 그건 사실이다(국장 화면이 증명한 실패).
        kw = _transcript_hits(_content_tokens(q), sorted(sids))
        if kw:
            have = {str(r.get("fragment_id")) for r in hits}
            hits = hits + [v for k, v in kw.items() if k not in have]
            top = max(top, 1.0)          # 낱말 일치는 확실하다 -> UNCERTAIN 으로 새지 않는다
        # [COUNT-TRUTH 2026-08-03] ★_P00N 병합을 걷어낸다 — 단위가 틀렸다.
        #   국장 답: "원본맵에서 조각단위를 일일이 셌다" -> 그 단위가 유일한 정답 기준이다.
        #   원본맵이 무엇을 그리는지 코드로 확정했다:
        #     OriginalPanorama.tsx:167  {fragments.map((f,i) => ...)}   타일 1개 = 배열 원소 1개
        #     <- Index.tsx:3666  sourceEntries[...].fragments
        #     <- GET /proposals/project/{id}/sources  (videoService.ts:291)
        #     <- main.py:2878  bams.get_semantic_fragments(sid)
        #     <- archive/manager.py:565  filter_by(source_id).order_by(start).all()
        #   ★병합 코드도 필터도 0. 즉 원본맵 타일 = semantic_fragments ★행 하나.
        #   실측 재현: SRC_3111FA4F 의 물속 구간 131.0~354.0s 가 연속 한 덩어리이고
        #   그 안의 semantic_fragments 행이 정확히 ★17개 — 국장이 세신 수와 일치한다.
        #   (같은 집합을 _P00N 병합하면 5그룹이라 17 이 재현되지 않는다)
        #   ★그래서 병합하지 않는다. 어제 내가 넣은 병합이 원본맵과 단위를 어긋나게 했다.
        #     Merope "바닷가" 5 가 병합값과 맞았던 것은 ★조각맵(다른 화면) 관찰이었다 —
        #     두 화면을 같은 기준으로 착각한 것이 내 잘못이다.
        seen_fid = set()
        rows = []
        for r in hits:
            fid = str(r.get("fragment_id"))
            if fid in seen_fid:
                continue
            seen_fid.add(fid)
            rows.append(r)
    except Exception as e:
        print(f"[CHAT-EYES][WARN] 조각 조회 실패 ({e})")
        return ("UNCERTAIN", 0,
                "[조각 근거] 조회에 실패했다. 조각 내용을 아는 척하지 말고 "
                "지금은 확인할 수 없다고 말하라.\n")
    # ★판정을 모델에게 맡기지 않는다 — 서버가 세고 서버가 상태를 정한다.
    #   앞 차수(9db84b86)는 "세어서 답하라"/"없으면 없다고 하라"를 지시문으로 시켰고,
    #   한쪽을 고치면 반대쪽이 죽었다("없습니다" 오답 -> 지시 수정 -> '없다'가 사라짐).
    #   문턱 하나로 양방향을 잡으려 한 것이 잘못이었다. 이제 세 상태로 나눈다.
    total = len(rows)
    if total == 0 or top < _EVID_ZERO:
        return ("ZERO", 0,
                "[조각 근거] 상태=없음. 이 프로젝트에서 질문에 맞는 조각을 찾지 못했다(0개). "
                "\"없습니다\"라고 답하라. 조각 id 나 내용을 지어내지 마라.\n")
    if top < _EVID_SURE:
        return ("UNCERTAIN", total,
                f"[조각 근거] 상태=확실하지 않음(최고 근접도 {top:.2f}). "
                f"비슷해 보이는 조각이 {total}개 있으나 질문과 맞는지 확신할 수 없다. "
                "\"확실하지 않습니다\"라고 말하고, 무엇을 찾는지 한 가지만 되물어라. "
                "★있다/없다로 단정하지 마라. 개수도 단정하지 마라.\n")
    rows = sorted(rows, key=lambda r: -float(r.get("score") or 0))
    shown = rows[:_EVID_MAX]
    more = total - len(shown)
    # ★1회차 실패 기록: 처음엔 "가까운 순서일 뿐 조건에 맞는다는 뜻이 아니다 …
    #   맞는 것이 없으면 '없습니다'" 로 썼다. 근거 6건을 주고도 답이 "없습니다." 였다.
    #   7B 는 부정 프레이밍을 먼저 집는다. 그래서 (1) 문턱으로 걸러 목록 자체를 믿을 수
    #   있게 만들고 (2) 지시를 '세어서 답하라'로 돌린다. '없다'는 마지막 예외로 내린다.
    # [COUNT-TRUTH 2026-08-03] ★개수를 단정하지 않는다 — 셀 수 없다는 것이 실측 결과다.
    #   국장이 원본맵에서 눈으로 센 17개(SRC_3111FA4F 131.0~354.0s 연속 구간)를
    #   정답으로 놓고 점수 분포를 쟀다:
    #       17 구간 안  0.320 ~ 0.642
    #       구간 밖 최고 0.625            ← ★두 분포가 완전히 겹친다
    #       컷 0.48 -> 정답 11/17 · 오검출 24    컷 0.54 -> 정답 6/17 · 오검출 9
    #   어떤 문턱으로도 17 이 나오지 않는다. 문턱을 옮기면 놓치거나 섞이거나 둘 중 하나다.
    #   ★이유: visual_desc 는 "wetsuit, goggles, diving suit" 를 물가에서도 똑같이 적는다.
    #     물속인지 물가인지는 그 텍스트에 신호가 없다 — 국장은 ★썸네일을 보고 가른 것이다.
    #   그래서 개수 질문에는 수를 말하지 않고 ★못 센다고 말하고 화면 계수를 청한다.
    #   (CCUT 원칙: 불가능하다는 말로 대화를 끝내지 않는다 — 다음 할 일을 제안한다)
    if _re_mod.search(r"몇\s*(개|것|장면|조각)|개수|얼마나", str(input_text or "")):
        return ("COUNT_UNSURE", total,
                f"[조각 근거] 상태=개수 확신 못함. 비슷한 조각 {total}개를 찾았지만 "
                "이 수가 정확하다고 말하면 안 된다 — 장면 설명만으로는 물속과 물가를, "
                "실내와 실외를 가르지 못한다(실측 확인).\n"
                "★이렇게 답하라: 정확한 개수는 자신이 없다고 먼저 밝히고, "
                f"비슷해 보이는 것이 {total}개쯤 있다고 말한 뒤, "
                "화면(원본맵)에서 직접 세어 알려주시면 그 수를 그대로 쓰겠다고 청하라.\n"
                "★숫자를 단정하지 마라. 목록에 없는 조각을 지어내지 마라.\n")
    # ★개수는 이미 서버가 셌다(total). 큐원은 세지 않고 그 수를 말하기만 한다.
    #   목록은 근거로 보여줄 뿐이고, 상한에 잘려도 개수는 잘리지 않는다
    #   (구판은 상한 8 에 잘린 목록을 세게 해서 "8개"라 답할 수 있었다).
    out = [f"[조각 근거] 상태=있음. 개수={total}개. "
           f"개수를 물으면 반드시 {total}개라고 답하라 — 아래 목록을 다시 세지 마라. "
           + (f"아래는 그중 가까운 {len(shown)}개만 보인 것이다. " if more > 0 else "")
           + "목록에 없는 조각 id·내용은 지어내지 마라. "
           "조각 id 는 SF_ 로 시작하는 것만 쓴다. "
           "이전 질문에 나온 낱말은 이 답에 섞지 마라. "
           "장면 설명은 영어일 수 있다(beach=바닷가, ocean=바다, underwater=바닷속) — 뜻으로 읽어라."]
    for r in shown:
        out.append("  - {fid} {s:.0f}~{e:.0f}s (근접 {sc:.2f}) | 장면: {vd} | 말: {tr}".format(
            fid=r.get("fragment_id"), s=float(r.get("start") or 0), e=float(r.get("end") or 0),
            sc=float(r.get("score") or 0),
            vd=_evid_snip(r.get("visual_desc")) or "-",
            tr=_evid_snip(r.get("transcript")) or "-"))
    return ("HAVE", total, "\n".join(out) + "\n")


def _llm_understand(input_text, recent_messages=None, source_ids=None,
                    person_vocab=None, defer_chat=False, project_id=None):
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
        txt = _clean_recent_text(m.get("text"))[:160]
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
    mirror_line = _mirror_summary_fact(project_id)
    fact_rule = "위 [지금]/[작업 상황] 수치는 실측값이다 — 날짜·조각·원본 질문은 이 값으로만 답하라.\n"
    if mirror_line:
        fact_rule = (
            "위 [지금]/[작업 상황] 수치는 실측값이다 — 날짜·조각·원본 질문은 이 값으로만 답하라. "
            "[수첩 요약]은 mirror_ledger의 pass/correction 집계값으로만 읽어라.\n"
        )
    # [MEMORY-SPINE 2026-08-02] 12턴(여기선 8턴) 밖의 기억을 이 자리에서 잇는다.
    #   recent_messages 는 프론트가 보낸 최근 몇 마디뿐이라, 그 앞의 대화와 국장이 정한
    #   기준은 이 블록으로 들어오지 않으면 큐원에게 존재하지 않는다.
    #   ★새로 만드는 값이 아니다 — 원장에 이미 쌓이는 chat_summary·active_intent·
    #     chat_pref 를 읽어 붙일 뿐이다(converse.load_memory_facts, 쿼리 1개).
    #   ★없으면 빈 문자열이라 프롬프트 모양이 종전과 같다(첫 대화·빈 프로젝트 무영향).
    memory_line = ""
    try:
        from engine.converse import load_memory_facts
        memory_line = load_memory_facts(project_id)
    except Exception as _e:
        print(f"[MEMORY-SPINE][WARN] 기억 주입 실패 ({_e})")
    facts = (f"[지금] {now.year}년 {now.month}월 {now.day}일 {weekday}요일 "
             f"{now.strftime('%H:%M')}\n" + work_line + memory_line + mirror_line + fact_rule)
    # [MIRROR-FIX-1 R4(2)] 자유대화 프롬프트에서는 수첩을 뺀다.
    #   판정 근거(R2-4 실측): 프롬프트 어디에도 큐원이 수첩으로 무엇을 하라는 지시가 없다.
    #     유일한 언급이 "…집계값으로만 읽어라"(읽는 법)뿐이라 대화에서 이 값으로
    #     달라질 행동이 없다. 남으면 편집 쪽으로 끄는 앵커로만 작동한다.
    #   ★뺐을 때 달라지는 것: 잡담 중 "내가 몇 번 되돌렸지?" 같은 질문에 큐원이
    #     수첩으로 답하지 못하고 모른다고 한다. 분류 프롬프트에는 그대로 남으므로
    #     편집 맥락의 판단에는 영향이 없다.
    #   ★facts 블록(:177-188) 문구는 건드리지 않는다 — 조립된 결과에서 수첩 줄만 들어낸다.
    facts_chat = facts
    if mirror_line:
        facts_chat = facts_chat.replace(mirror_line, "")
        if _MIRROR_READ_CLAUSE in facts_chat:
            facts_chat = facts_chat.replace(_MIRROR_READ_CLAUSE, "\n")
        else:
            print("[MIRROR-FIX-1][WARN] 수첩 읽기 지시문을 못 찾음 — "
                  "facts 문구가 바뀌었는지 확인 필요(대화 프롬프트에 지시문만 남음)")
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
        # [QWEN-01 2-2] 정체 금지는 서버 후처리(:372 · :479)로 이관. 중국어 금지는 유지.
        "reply 규칙: 반드시 한국어로만(중국어·영어 문장 금지). "
        "너의 이름은 오직 CCUT이다. 날짜·시간·작업 상황 질문은 위 값으로 정확히 답하고, "
        "날씨·뉴스 등 모르는 실시간 정보는 아는 척하지 않는다.\n"
        'JSON만 출력: {"kind":"chat|edit|confirm|retrigger|reset|unclear","reply":"...",'
        '"instruction":"edit일 때 선별 기준, 아니면 빈 문자열"}\n'
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n")
    try:
        # [LIVING-DRAFT-1] 이해도 젬마로 — 채팅 턴 안에서 큐원·젬마를 오가면
        #   GPU 모델 스왑이 회당 ~10초(실측)라 반복 수정 루프가 죽는다.
        #   지시서 분담: 숫자=서버, 판단과 말=젬마. 큐원은 루프 밖(판사·plan)에만.
        out = hub._ollama_json(prompt, timeout=45, model=hub.VOICE_MODEL)
    except Exception as e:
        print(f"[INTENT-ROUTER] llm understand 실패 ({e})")
        return None
    kind = str(out.get("kind") or "").strip()
    reply = _sanitize_talk(str(out.get("reply") or "").strip())
    # [FRAG-TRUTH 2026-08-02] 묻는 것과 시키는 것을 ★서버 규칙으로 가른다.
    #   실측: "그 바닷가 조각들 id 를 알려줘" 가 run_proposal 로 갔다 —
    #   조각 13개를 다시 고르고 미리보기 렌더까지 약 1분을 태웠다. 물었을 뿐인데.
    #   원인: 분류가 '바닷가'라는 기준어를 보고 edit 로 읽는다. 조회 사다리(:832)의
    #   트리거에는 "몇 개"·"알려줘"가 아예 없어서 그 앞에서 걸러지지도 않는다.
    #   ★모델 분류를 다시 가르치지 않는다(그 방식으로 두 번 실패했다). 뒤에서 덮는다:
    #     조각을 묻는 말인데 편집 동사가 하나도 없으면 편집이 아니다.
    #   ★애매하면 조회 쪽으로 — 편집은 되돌리기가 비싸다(렌더 1~3분).
    if kind == "edit" and _is_fragment_question(input_text) and not _re_mod.search(
            r"편집|골라|만들어|빼|줄여|늘려|남겨|자르|이어|바꿔|다시 골|재제안|추천해", input_text):
        print(f"[FRAG-TRUTH] 조회를 편집으로 읽었다 -> chat 으로 되돌림: {input_text[:40]}")
        kind = "chat"
    if kind == "edit":
        instr = str(out.get("instruction") or "").strip() or input_text
        # [지시문 오염 가드 2026-07-06] LLM이 instruction 칸에 되묻기 문장을 넣는 사고
        # ("...알려주십시오"가 편집 기준으로 실행된 사건) — 질문꼴/과장 지시문은
        # 실행하지 않고 되묻기로 강등한다.
        if _re_mod.search(r"[?？]|주세요|주십시오|알려|말씀해|무엇을|어떤 (부분|장면)을|"
                          r"싶으신지|시겠어요|해볼까요", instr) or len(instr) > 60:
            kind = "unclear"
        # [GROUND-1 2026-08-08 국장 "또 17개야"] 지시문이 사용자 말에 근거가 있는가.
        #   실측 사고: "편집이나 하자."(기준 없는 말)에 모델이 기준을 지어냈다 —
        #   normalized='정은한 나오는 장면'. DB 어디에도 없는 이름이고 국장은 그런
        #   말을 한 적이 없다. 그 지어낸 기준으로 조각 17개 재선별이 3분씩 돌았다.
        #   ★기준은 사용자에게서 와야 한다. 원문에 없는 낱말로만 이뤄진 지시문은
        #     근거가 없는 것이다 — 실행하지 않고 되묻는다(NUM-GUARD 의 낱말 판).
        elif kind == "edit":
            # ★낱말 '일치'가 아니라 '포함'으로 본다 (2026-08-08 실측 사고):
            #   국장 "2바다는 바다지만, 바다속 잠수장면이야." 를 이 방어가 막았다.
            #   지시문 '바다 속 잠수장면' 의 낱말이 원문의 '바다속'·'잠수장면이야'와
            #   조사·띄어쓰기 때문에 集合으로는 안 맞았다. 내가 만든 방어가 사용자를
            #   막은 것이다. 포함으로 보면 '바다'·'잠수장면'이 원문 안에 있어 통과하고,
            #   지어낸 이름('정은한')은 여전히 원문에 없어 막힌다.
            _src = str(input_text or "")
            _iw = [w for w in _re_mod.findall(r"[가-힣]{2,}", instr)]
            if _iw and not any(
                    (w in _src) or any(w[:i] and w[:i] in _src for i in range(len(w), 1, -1))
                    for w in _iw):
                print(f"[GROUND-1] 근거 없는 지시문 — 사용자 말에 없는 낱말로만 "
                      f"이뤄짐: {instr[:40]!r} ← {str(input_text)[:30]!r}")
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
        # [CHAT-EYES 2026-08-02] 자유 대화에서 큐원에게 ★조각을 보여준다.
        #   국장 실화면: 조각맵에 바닷가 조각이 여럿인데 "1개뿐"이라 답하고
        #   직전 질문의 "파인애플"까지 섞였다. 원인은 성격이 아니라 ★눈이 없어서다 —
        #   이 분기는 candidate_fragment_ids 를 채우지 않고, facts 에는 조각 '수'만 있고
        #   조각 '내용'이 0건이다. 못 보는데 물으면 지어낸다.
        #   ★분류 프롬프트(facts)와 되묻기 템플릿은 건드리지 않는다. 대화용 facts_chat 에만
        #     붙이고, kind=="chat" 으로 판정된 뒤에만 조회한다(다른 경로 비용 0 · 회귀 0).
        _state, _total, _evid = _fragment_evidence(input_text, source_ids)
        facts_chat = facts_chat + _evid
        # [FRAG-TRUTH 2026-08-02] ★판정을 코드로 내린다 — 모델에게 맡기지 않는다.
        #   실측 2회 실패: 근거 블록에 "상태=없음 … '없습니다'라고 답하라"를 실었는데
        #   7B 가 "있습니다. 식당에서 식사하는 장면은 2개의 영상에 포함되어 있습니다.
        #   한 편은 내부 조명이 뛰어난 실내 촬영…" 이라고 통째로 지어냈다
        #   (백엔드 로그 path=stream reply_len=90 — 블록은 분명히 붙어 있었다).
        #   지시문으로 두 번 실패했으므로 ★없다/애매하다는 서버가 직접 말한다.
        #   있다일 때만 모델에게 넘긴다(그때는 근거가 있으니 지어낼 이유가 없다).
        #   ★조각을 묻는 말일 때만 단정한다 — 잡담("오늘 하루 어땠어?")까지
        #     "없습니다"로 답하지 않게.
        if _is_fragment_question(input_text):
            if _state == "ZERO":
                return _resp("answer_only",
                             "그런 조각은 이 프로젝트에서 못 찾았어요.",
                             confidence=0.9, via="deterministic",
                             matched={"kind": "frag_zero"})
            if _state == "UNCERTAIN":
                return _resp("answer_only",
                             "확실하지 않습니다. 비슷해 보이는 조각은 있는데 "
                             "찾으시는 것과 맞는지 자신이 없어요. 어떤 장면인지 한 가지만 더 알려주시겠어요?",
                             confidence=0.9, via="deterministic",
                             matched={"kind": "frag_uncertain"})
        # [F2 스트리밍] defer_chat=True면 대화 생성을 하지 않고 표식만 반환 —
        # 스트림 엔드포인트가 stream_smalltalk로 토큰 단위 생성한다. 분류는 이미 완료.
        if defer_chat:
            r = _resp("answer_only", "", confidence=0.85, via="qwen",
                      matched={"kind": "free_chat"})
            r["_stream_chat"] = {"facts": facts_chat}   # [MIRROR-FIX-1] 대화엔 수첩 없음
            return r
        # [대화 품질 2026-07-06] 분류(temp 0)와 대화(temp 0.7)를 분리 — 분류 초안 답 대신
        # 대화 전용 프롬프트(화제 이탈 금지·실시간 정보 아는 척 금지)로 최종 답을 만든다.
        talk = _llm_smalltalk(input_text, recent_messages, facts=facts_chat)
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
    # [VOICE 2026-08-08] 덧붙인 로마자 병기·영어 번역은 떼기만 한다 — 본문은 그대로.
    #   말을 죽이고 고정문구로 바꾸는 것과 다르다(대화가 죽지 않는다).
    reply = re.split(r"\n\s*Translation\s*:", reply)[0]
    reply = re.sub(r"\([A-Z][a-z]+[A-Za-z\s\-!?,.0-9']{15,}\)", "", reply)
    reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
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
        txt = _clean_recent_text(m.get("text"))[:120]
        if txt:
            ctx += f"{who}: {txt}\n"
    tail = ("답변 문장만 출력한다 — JSON·따옴표·머리말 금지.\n" if plain
            else 'JSON만 출력: {"reply":"..."}\n')
    # [VOICE 2026-08-08 국장 지시] 소개서를 준다 — 지금까지 목소리는 CCUT을 한 줄로만
    #   알고 대답해 왔다. 사실(무엇을 할 수 있고 없는지)이지 말투 지시가 아니다.
    try:
        from engine.ccut_manual import manual_block
        manual = manual_block()
    except Exception:
        manual = ""
    return (
        "너는 CCUT — 영상 편집을 돕는 다정한 동료다. 사용자의 말에 따뜻한 존댓말 "
        "한국어 1~3문장으로 '실제로' 대답한다.\n"
        + manual
        + facts +
        "대화 규칙 (어기면 실격):\n"
        "1. 사용자의 마지막 말에 직접 반응한다. 화제를 네 맘대로 바꾸지 않는다 — "
        "카페·취미 추천 같은 뻔한 스몰토크를 먼저 꺼내지 마라.\n"
        "2. 날씨·뉴스·유행 같은 실시간 정보는 너는 모른다 — 아는 척 금지. "
        "사용자가 알려주면 그 말을 믿고 따라가라.\n"
        "3. 고민·감정을 말하면 가볍게 공감하고, 구체적으로 하나만 되물어라.\n"
        "4. '저는 편집기라서'류 거절 금지. 매번 편집 얘기로 돌리지도 마라.\n"
        # [QWEN-01 2-2] "모델명·제조사 언급 금지" 삭제 → 서버 후처리에 맡긴다
        #   (:372 정체 노출 차단, :479 스트림 중단). 중국어 금지는 남긴다(실측 누출 있음).
        #   정체성 확립("너의 이름은 오직 CCUT")은 금지가 아니라 자기규정이라 남긴다.
        # [VOICE 2026-08-08] 젬마용 한 줄 — 직통 방 실측: 젬마는 답 끝에 로마자 발음
        #   병기·영어 번역을 덧붙이는 버릇이 있고, 한 번 붙으면 다음 턴이 그 형식을
        #   물려받는다. 문패로 씨앗을 막는다(첫 턴 0/4 실측).
        "5. 반드시 한국어만(중국어·영어 문장 금지). 로마자 발음 표기, 영어 번역, "
        "괄호 병기, Translation 표기를 덧붙이지 않는다. 답이 끝나면 그대로 끝낸다. "
        "너의 이름은 오직 CCUT이다. 모르는 건 솔직히 모른다고 한다.\n"
        + tail
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n")


def _chat_role_enabled():
    return os.getenv("CCUT_CHAT_ROLE", "0") in ("1", "true", "True", "on", "ON")


# ── [QWEN-02 STEP 2 2026-08-02] 큐원의 손 — 조회 의도에만 배선 ──────────────
#   왜 여기인가(실측): 현행 show_fragments 경로는 임베딩 top-k 라 **무엇을 물어도
#     12건을 뱉는다.** DB 에 0건인 '파인애플'에도 12건을 냈고, 딸기 정답
#     VF1_SRC_009AE91F 는 12건에 없었다. 즉 이 경로는 "없다"고 말하지 못한다.
#     큐원이 전사를 직접 조회하면 없는 것을 없다고 말할 수 있다.
#   ★ 편집 실행 경로(run_proposal)는 건드리지 않는다. 조회 의도에서만 갈린다.
#   ★ 기본 OFF. 게이트를 끄면 이 함수는 즉시 None 이고 기존 경로가 그대로 산다.
def _qwen_tools_enabled():
    return os.getenv("CCUT_QWEN_TOOLS", "0") in ("1", "true", "True", "on", "ON")


# [FRAG-TRUTH 2026-08-02] 큐원이 보는 조각과 사용자가 보는 조각을 같은 것으로 만든다.
#   실측(2026-08-02): 이 프로젝트의 조각 id 는 두 계열이다.
#     VF_*  fragments(377) · evidence_board(377)      — 30초 고정 분할(거친 1차)
#                                                        예: VF1 0~30s · VF2 29.5~61.4s
#     SF_*  semantic_fragments(936) · fragment_index(936)
#           · fragment_vault(1149) · fragment_visual_marks(1765)  — 의미 단위 분할
#                                                        예: 0~13 · 13~29.5 · 29.5~38 …
#   화면(조각맵)은 /fragments/{source_id} -> bams.get_semantic_fragments 라 ★SF 를 쓴다.
#   그런데 이 도구 안내의 첫 줄이 evidence_board(=VF)였다. 그래서 큐원이
#   "조각 ID VF1_SRC_009AE91F 의 전사는…"이라 답했고, 국장이 화면에서 그 id 를 찾을 수 없었다.
#   ★안내를 SF 계열로 바꾼다. 지시문을 설득하는 게 아니라 ★틀린 테이블을 바로잡는 것이다.
_QWEN_TOOL_SYSTEM = (
    "너는 CCUT — 영상 편집을 돕는 동료다. 사용자가 조각을 찾아달라고 하면 "
    "db_query 도구로 DB를 직접 조회해서 답한다. 추측하지 말고 조회해라.\n"
    "★조각 id 는 반드시 SF_ 로 시작하는 것만 쓴다. VF_ 로 시작하는 id 는 사용자 화면에 "
    "없는 옛 주소이므로 답에 절대 쓰지 않는다(evidence_board 는 그 옛 주소라 쓰지 않는다).\n"
    "주요 테이블(이 밖의 테이블도 조회할 수 있다):\n"
    "- fragment_index(fragment_id, source_id, transcript, visual_desc) : "
    "transcript 가 조각의 전사(대사), visual_desc 가 장면 설명(영어일 수 있다)\n"
    "- semantic_fragments(fragment_id, source_id, start, \"end\") : 조각의 시간 좌표\n"
    "- fragment_vault(fragment_id, transcript) : 조각 금고\n"
    "- programs(program_id, title) / sources(source_id, filename)\n"
    "조회가 실패하거나 0건이면 다른 테이블·컬럼으로 다시 조회한다. "
    "조회 결과에 없는 조각 id 나 전사 내용을 절대 지어내지 않는다. "
    "정말 없으면 없다고 말한다.\n"
    "찾은 뒤에는 조회 결과에 실제로 있는 조각 id 와 전사 내용을 한국어로 짧게 알려준다.\n"
)


def _qwen_answer_cards(reply, source_ids=None):
    """[CHAT-ROOT 3-B-1] 큐원이 답에 적은 조각 id 로 카드를 만든다.

    왜 필요했나: qwen_tools 분기가 reply 만 돌려주고 results 를 비워 둬서
      답은 맞는데 화면에 카드가 안 떴다(기존 경로는 :645 에서 채운다).
    ★ 형식은 fragment_show._card 그대로 쓴다 — 새 필드·새 형식을 만들지 않는다.
    ★ 답에 없는 조각을 억지로 채우지 않는다. 못 찾으면 빈 배열이다.
    """
    fids = []
    # _re 는 이 모듈에서 함수 안 지역 import 라 모듈 레벨엔 없다 — _re_mod 를 쓴다.
    for m in _re_mod.finditer(r"\b(?:SF|VF)\w*_SRC_[0-9A-Za-z_]+", reply or ""):
        f = m.group(0).rstrip(".,)）")
        if f not in fids:
            fids.append(f)
    if not fids:
        return []
    _qwen_answer_cards.last_fid_count = len(fids)
    try:
        import sqlite3 as _sq
        from engine.fragment_show import _card, DB_PATH, THUMBS_DIR  # noqa: F401
        con = _sq.connect("file:" + DB_PATH.replace("\\", "/") + "?mode=ro", uri=True)
    except Exception as e:
        print(f"[QWEN-TOOLS][CARD] 카드 생성 실패(답변은 유지): {e}", flush=True)
        return []
    try:
        src_meta = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT source_id, title, file_path FROM sources")}
        ph = ",".join("?" for _ in fids)
        rows = []
        # 조각은 두 저장처에 흩어져 있다 — semantic_fragments(분절)와
        # evidence_board(원본 증거 구간). 큐원이 어느 쪽 id 를 답하든 카드가 되게 한다.
        for tbl in ("semantic_fragments", "evidence_board"):
            try:
                for r in con.execute(
                        f'SELECT fragment_id, source_id, start, "end" FROM {tbl} '
                        f'WHERE fragment_id IN ({ph})', fids):
                    if not any(x[0] == r[0] for x in rows):
                        rows.append(tuple(r))
            except Exception:
                continue
        proj = set(source_ids or [])
        if proj:
            rows = [r for r in rows if r[1] in proj]
        cards = [_card(con, r[0], r[1], r[2], r[3], src_meta) for r in rows]
    except Exception as e:
        print(f"[QWEN-TOOLS][CARD] 조회 실패(답변은 유지): {e}", flush=True)
        cards = []
    finally:
        con.close()
    print(f"[QWEN-TOOLS][CARD] 답변에서 fid {len(fids)}건 -> 카드 {len(cards)}건", flush=True)
    return cards


def _qwen_tool_show(user_text, source_ids=None):
    """조회 의도를 큐원이 DB 를 직접 보고 답하게 한다. 실패하면 None (기존 경로 폴백).

    ★ 조용히 실패하지 않는다 — 이 방 원칙: 안 닿는 방어는 영원히 조용하다.
      게이트가 켜졌는데 도구를 한 번도 안 불렀으면 그 사실을 로그로 말한다.
    ★ [CHAT-ROOT 3-B-2] 지금 프로젝트 안에서 찾는다. 조회할 수 있는 테이블에는
      제한을 걸지 않는다 — 프로젝트 조건은 재갈이 아니라 사용자 기대다.
    """
    if not _qwen_tools_enabled():
        return None
    system_text = _QWEN_TOOL_SYSTEM
    if source_ids:
        system_text += (
            "\n[지금 프로젝트의 소스]\n" + ", ".join(str(s) for s in source_ids) + "\n"
            "조각을 찾을 때는 반드시 이 source_id 들로 범위를 좁혀라 "
            "(예: AND source_id IN (...)). 다른 프로젝트 조각은 답에 넣지 않는다. "
            "이 범위 안에 없으면 없다고 말한다.\n")
    else:
        print("[QWEN-TOOLS][NO-SCOPE] source_ids 가 비어 전역 조회가 된다 "
              "(프로젝트 미선택 상태로 추정)", flush=True)
    try:
        from admin import ai_tools
        r = hub._ollama_chat_tools(
            [{"role": "system", "content": system_text},
             {"role": "user", "content": user_text}],
            ai_tools.ollama_tool_defs(["db_query"]), ai_tools.run,
            timeout=120, temperature=0, max_rounds=6)
    except Exception as e:
        print(f"[QWEN-TOOLS] 실패 -> 기존 조회 경로로 폴백: {type(e).__name__}: {e}",
              flush=True)
        return None
    text = (r or {}).get("text") or ""
    if not r or not r.get("tool_calls"):
        # 게이트는 켜졌는데 도구가 안 불렸다. 조용히 넘어가면 영원히 모른다.
        print(f"[QWEN-TOOLS][NO-CALL] 게이트 ON 인데 도구 호출 0건 "
              f"(rounds={(r or {}).get('rounds')}). 기존 조회 경로로 폴백. "
              f"입력={user_text[:40]!r}", flush=True)
        return None
    if not text.strip():
        print("[QWEN-TOOLS][EMPTY] 도구는 돌았는데 답이 비었다 -> 기존 경로 폴백",
              flush=True)
        return None
    print(f"[QWEN-TOOLS] tool_calls={r['tool_calls']} rounds={r['rounds']} "
          f"limit={r['hit_round_limit']}", flush=True)
    _qwen_answer_cards.last_fid_count = 0
    cards = _qwen_answer_cards(text, source_ids)
    # [CHAT-ROOT 3-B-2 실측 2026-08-02] 프롬프트만으로는 범위가 안 지켜진다.
    #   Merope(딸기 소스 없음)에서 3/3 모두 다른 프로젝트의 VF1_SRC_009AE91F 를 답했다 —
    #   7B 는 system 의 "이 source_id 로 좁혀라"를 따르지 않는다(관제실 Claude 와 갈리는 지점).
    #   그래서 말이 아니라 좌표로 막는다: 답에 조각을 적었는데 그중 이 프로젝트 것이
    #   하나도 없으면, 그 답은 범위 밖이므로 채택하지 않는다.
    #   ★ 조회 테이블에는 여전히 제한이 없다. 막는 것은 '남의 프로젝트 조각을 답하는 것'뿐이다.
    if source_ids and getattr(_qwen_answer_cards, "last_fid_count", 0) > 0 and not cards:
        print(f"[QWEN-TOOLS][OUT-OF-SCOPE] 답이 범위 밖 조각을 가리켰다 "
              f"(fid {_qwen_answer_cards.last_fid_count}건, 프로젝트 내 0건) -> 없음으로 답한다",
              flush=True)
        return {"reply": "지금 프로젝트 안에는 그런 조각이 없어요.",
                "trace": r, "results": []}
    return {"reply": text.strip(), "trace": r, "results": cards}


def _estimate_chat_tokens(text):
    return max(1, (len(str(text or "")) + 1) // 2)


def _smalltalk_chat_messages(input_text, recent_messages=None, facts=""):
    budget = int(os.getenv("CCUT_CHAT_ROLE_HISTORY_TOKENS", "2048"))
    try:
        from engine.ccut_manual import manual_block
        manual = manual_block()
    except Exception:
        manual = ""
    system = (
        "너는 CCUT — 영상 편집을 돕는 다정한 동료다. 사용자의 말에 따뜻한 존댓말 "
        "한국어 1~3문장으로 '실제로' 대답한다.\n"
        + manual
        + facts +
        "대화 규칙 (어기면 실격):\n"
        "1. 사용자의 마지막 말에 직접 반응한다. 화제를 네 맘대로 바꾸지 않는다 — "
        "카페·취미 추천 같은 뻔한 스몰토크를 먼저 꺼내지 마라.\n"
        "2. 날씨·뉴스·유행 같은 실시간 정보는 너는 모른다 — 아는 척 금지. "
        "사용자가 알려주면 그 말을 믿고 따라가라.\n"
        "3. 고민·감정을 말하면 가볍게 공감하고, 구체적으로 하나만 되물어라.\n"
        "4. '저는 편집기라서'류 거절 금지. 매번 편집 얘기로 돌리지도 마라.\n"
        # [QWEN-01 2-2] "모델명·제조사 언급 금지" 삭제 → 서버 후처리에 맡긴다
        #   (:372 정체 노출 차단, :479 스트림 중단). 중국어 금지는 남긴다(실측 누출 있음).
        #   정체성 확립("너의 이름은 오직 CCUT")은 금지가 아니라 자기규정이라 남긴다.
        # [VOICE 2026-08-08] 젬마용 한 줄 — 직통 방 실측: 젬마는 답 끝에 로마자 발음
        #   병기·영어 번역을 덧붙이는 버릇이 있고, 한 번 붙으면 다음 턴이 그 형식을
        #   물려받는다. 문패로 씨앗을 막는다(첫 턴 0/4 실측).
        "5. 반드시 한국어만(중국어·영어 문장 금지). 로마자 발음 표기, 영어 번역, "
        "괄호 병기, Translation 표기를 덧붙이지 않는다. 답이 끝나면 그대로 끝낸다. "
        "너의 이름은 오직 CCUT이다. 모르는 건 솔직히 모른다고 한다.\n"
        "답변 문장만 출력한다 — JSON·따옴표·머리말 금지.\n")
    messages = [{"role": "system", "content": system}]
    history = []
    used = 0
    for m in reversed(recent_messages or []):
        txt = _clean_recent_text(m.get("text"))[:120]
        if not txt:
            continue
        cost = _estimate_chat_tokens(txt)
        if history and used + cost > budget:
            break
        used += cost
        role = "user" if (m.get("sender") == "user") else "assistant"
        history.append({"role": role, "content": txt})
    messages.extend(reversed(history))
    messages.append({"role": "user", "content": input_text})
    return messages


def _llm_smalltalk(input_text, recent_messages=None, facts=""):
    """[SMALLTALK/자유대화] 질문/잡담에 사람다운 답 — '나는 편집기라서'류 거절 금지
    (국장: 거절은 사용자를 바보 취급하는 것). 실패 시 None → 호출부가 따뜻한 고정 문구.
    [국장지시 2026-07-06] 편집 얘기가 아니어도 사용자의 화제를 진짜로 따라간다 —
    매 답을 편집 제안으로 되돌리지 않는다. facts=실제 날짜·작업 상황 블록(환각 봉쇄)."""
    prompt = _smalltalk_prompt(input_text, recent_messages, facts=facts)
    try:
        # temperature 0.7 — 대화는 결정성보다 자연스러움 (판사 경로와 분리)
        out = hub._ollama_json(prompt, timeout=30, temperature=0.7,
                               model=hub.VOICE_MODEL)
        return _sanitize_talk(str(out.get("reply") or "").strip())
    except Exception as e:
        print(f"[INTENT-ROUTER] smalltalk 실패 ({e})")
        return None


def stream_smalltalk(input_text, recent_messages=None, facts=""):
    """[F2 스트리밍] 자유대화 토큰 스트림 생성기.
    산출: ('token', 조각) 반복 → ('done', 전체문장) / 위생 위반·실패 시 ('abort', None).
    위생 규칙은 _sanitize_talk와 동일 기준을 누적문에 적용 — 위반 즉시 중단해
    호출부가 CCUT 고정 문구로 강등한다 (조용한 유출 금지)."""
    acc = ""
    try:
        if _chat_role_enabled():
            chunks = hub._ollama_chat_stream(
                _smalltalk_chat_messages(input_text, recent_messages, facts=facts),
                timeout=30, temperature=0.7, model=hub.VOICE_MODEL)
        else:
            prompt = _smalltalk_prompt(input_text, recent_messages, facts=facts, plain=True)
            chunks = hub._ollama_stream(prompt, timeout=30, temperature=0.7,
                                        model=hub.VOICE_MODEL)
        for chunk in chunks:
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
                      defer_chat=False, project_id=None):
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
                                   archive_lookup=archive_lookup,
                                   project_id=project_id)
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

        _redo_ask_idx = None
        for idx in range(len(recent_messages) - 1, -1, -1):
            txt = str(recent_messages[idx].get("text") or "").strip()
            if recent_messages[idx].get("sender") != "user" and "기준으로 다시 할까요" in txt:
                _redo_ask_idx = idx
                break
        _redo_prev_edit = _last_user_edit_instruction(
            recent_messages[:_redo_ask_idx] if _redo_ask_idx is not None else None)
        if _redo_prev_edit:
            return route_edit_intent(source_ids=source_ids, input_text=_redo_prev_edit,
                                     recent_messages=None, allow_llm=allow_llm,
                                     person_vocab=person_vocab,
                                     archive_lookup=archive_lookup,
                                     search_lookup=search_lookup,
                                     fragment_labels=fragment_labels,
                                     project_id=project_id)

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
            r"(편집|제안|생성|골라서|골라|만들어|만들|뽑아|뽑)?\s*(하게|하도록)?\s*"
            r"(해\s*줘|해줘|해\s*봐|해봐|부탁해?|줘|주세요|하자|할래|볼래|보자)?[.!~?\s]*$", t):
        _prev_edit = _last_user_edit_instruction(recent_messages)
        return _resp("ask_clarification",
                     _bare_redo_clarification(_prev_edit),
                     confidence=0.9, via="deterministic",
                     matched={"kind": "bare_redo_clarification"})
    if len(t) <= 24 and _re.match(
            r"^(아까\s*그거|방금\s*말한\s*거|그거)\s*(다시|한\s*번\s*더)?\s*"
            r"(해\s*줘|해줘|해\s*봐|해봐|줘|주세요)?[.!~?\s]*$", t):
        _prev_edit = _last_user_edit_instruction(recent_messages)
        return _resp("ask_clarification",
                     _bare_redo_clarification(_prev_edit),
                     confidence=0.9, via="deterministic",
                     matched={"kind": "bare_redo_clarification"})

    # ── 0.5 조회/열람 [SHOW] — "보여줘/있나/찾아줘"는 편집이 아니라 보여주기다.
    #    편집 동사가 함께 있으면(예: "찾아서 편집해줘") 편집 사다리가 우선.
    #    결과 카드는 자체완결(제목·시간·썸네일·재생 URL) — 흐름에 남고 클릭=재생.
    if (_re.search(r"보여줘|보여 줘|있나\??|있냐|있어\?|있는지|찾아줘|찾아 줘|찾아봐|불러와|검색해|뭐가 있", t)
            and not _re.search(r"편집|골라줘|골라 줘|만들어|빼줘|빼 줘|줄여|늘려|남겨", t)):
        _person0 = hub.resolve_person_name(t, vocab=person_vocab)
        # [SHOW-GUARD 2026-07-26] 조회어만으로는 조회가 아니다 — '무엇을' 찾는지가 있어야 한다.
        #   실사고: "넌 니 안에 어떤 기능이 있는지 알고 있나?"가 '있는지'·'있나' 두 개에 걸려
        #   조각 12개를 토해냈다(det 즉답 48ms, 큐원 미호출). '있나?'는 한국어에서 압도적으로
        #   그냥 의문 어미다("먹었나?", "알고 있나?"). 조회어 + (소재 명사 | 인물)을 함께 요구한다.
        #   ★위 정규식에서 단어를 빼지 않는다 — 기존 조회 발화는 그대로 산다.
        #   ★main.py 의문문 가드(:4828)에 show를 넣는 길은 택하지 않았다: 큐원 분류표에
        #     show 항목이 아예 없어(chat|edit|confirm|retrigger|reset|unclear) 물음표 붙은
        #     정상 조회("정은한 나오는 조각 있나?")까지 잡담으로 죽는다.
        _show_subject = bool(
            _re.search(r"조각|장면|영상|사진|클립|컷|화면|파일|소스|원본|아카이브", t)
            or _person0)
        if not _show_subject:
            print(f"[SHOW-GUARD] 조회어는 있으나 소재(조각·장면·인물)가 없다 "
                  f"-> 조회 아님, 사다리 계속: {t[:40]}")
            found = None
        elif search_lookup is not None:
            found = search_lookup(t, _person0)
        else:
            from engine.fragment_show import search_show
            found = search_show(t, _person0, source_ids)
        # [QWEN-02 STEP 2] 조회 의도 — 게이트 ON 이면 큐원이 DB 를 직접 보고 답한다.
        #   기본 OFF 이므로 이 분기는 평상시 통째로 건너뛴다(회귀 없음).
        #   실패·무응답이면 None 이라 아래 기존 임베딩 경로가 그대로 산다.
        if _show_subject:
            _qt = _qwen_tool_show(t, source_ids)
            if _qt is not None:
                # [FRAG-TRUTH 2026-08-03] ★이 경로에 위생 필터가 없었다.
                #   실측: "그 조각들만 보여 줄 수 있어? 조각맵에 모아줘" 에
                #   "根据提供的信息，这段视频的内容主要涉及一些人在海边进行捕鱼活动…" 가
                #   그대로 사용자 화면으로 나갔다(Freesia·Adhara 두 방). 중국어 누출은
                #   _sanitize_talk 이 이미 막고 있는 사고인데 이 분기만 그 문을 안 지났다.
                #   ★막히면 조각 카드는 그대로 두고 문구만 CCUT 말로 강등한다 —
                #     찾은 결과를 버리지 않는다.
                _say = _sanitize_talk(_qt.get("reply"))
                if not _say:
                    _n = len(_qt.get("results") or [])
                    _say = (f"조각 {_n}개를 찾았어요." if _n
                            else "조건에 맞는 조각을 못 찾았어요.")
                _r = _resp("show_fragments", _say, confidence=0.9,
                           via="qwen_tools")
                # [3-B-1] 기존 조회 경로(:645)와 같은 형태로 카드를 싣는다.
                _r["results"] = _qt.get("results") or []
                return _r
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
    _lmap = {str(k).upper(): v for k, v in (fragment_labels or {}).items()}
    # [관문C 2026-07-21 라이브RED 수리] "G1만"의 bare '만'은 트리거 목록(만으로|만 가지고…) 밖이라
    #   결정론 사다리를 못 잡고 Qwen 단계로 새, 라이브에서 "G1은 몇 번째?"로 되물었다(RED).
    #   해결은 트리거 하드코딩 증식이 아니라 계기판 사실: 히트한 라벨이 실제 fragment_labels에
    #   있을 때만(_real_hits), 그 라벨 뒤 한정조사(만/들만/번만)를 '그 라벨만 유지' 교정으로 해석.
    #   실재 않는 라벨(G99)·포맷토큰(MP4)은 _real_hits에서 빠져 발화 불가 → 기존 진실 불변(C3).
    #   사실 없이 표면형을 나열하지 않으므로 라우터 증식이 아니다(관문B 계기판의 연장).
    _real_hits = [h for h in _label_hits if h.upper() in _lmap]
    _label_only = any(_re.search(_re.escape(h) + r"\s*(?:들|번)?만", t) for h in _real_hits)
    if _label_hits and (
            _re.search(r"만으로|으로만|만 가지고|편집|골라|구성|묶|모아|합쳐|넣|빼|제외|말고|없이", t)
            or _label_only):
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
        if allow_llm and defer_chat and not _EDIT_MARK_RE.search(t) \
                and not _CONTEXT_COMMAND_RE.search(t):
            r = _resp("answer_only", "", confidence=0.85, via="qwen",
                      matched={"kind": "free_chat"})
            # [COUNT-TRUTH 2026-08-03] ★빈 facts 로 내보내지 않는다.
            #   이 자리는 _llm_understand 를 안 거치고 바로 스트림으로 가므로
            #   CHAT-EYES 근거 주입이 닿지 않았다. 근거 없이 답하면 지어낸다
            #   (국장 화면 "바닷속 잠수 11개" 의 출처 후보 — 서버가 준 수가 아니다).
            r["_stream_chat"] = {"facts": _evidence_facts(t, source_ids)}
            _z = _zero_or_uncertain_reply(t, source_ids)
            if _z:
                r.pop("_stream_chat", None); r["reply"] = _z
                r["matched"] = {"kind": "frag_state", "gate": "chat_signal"}
            return r
        if allow_llm:
            und = _llm_understand(t, recent_messages, source_ids, person_vocab,
                                  defer_chat=defer_chat, project_id=project_id)
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
    # [FRAG-TRUTH 2026-08-03] ★어휘가 있다고 편집은 아니다 — 묻는 말이면 묻는 말이다.
    #   실측: "그 바닷가 조각들 id 를 알려줘" 가 여기서 theme='바닷가' 로 잡혀
    #   run_proposal 로 갔다. 조각 13개를 다시 고르고 미리보기 렌더까지 약 1분.
    #   물었을 뿐인데 편집이 돈다 — 되돌리기가 비싼 쪽으로 잘못 기운다.
    #   ★조각을 묻는 말인데 편집 동사가 하나도 없으면 이 분기를 타지 않는다.
    #     그러면 아래 사다리를 지나 큐원 이해(_llm_understand)로 가고,
    #     거기서 조각 근거를 받아 답한다. 편집 발화("골라줘·빼줘·편집해줘")는 그대로 여기서 산다.
    if (det.get("theme_found") or det.get("count")) and _is_fragment_question(t) \
            and not _re.search(r"편집|골라|만들어|빼|줄여|늘려|남겨|자르|이어|바꿔|다시 골|재제안|추천해", t):
        print(f"[FRAG-TRUTH] det 어휘가 잡혔지만 묻는 말이다 -> 편집 아님: {t[:40]}")
        det = {}
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
                # [COUNT-TRUTH 2026-08-03] 질문 그물도 같다 — 빈 facts 금지.
                r["_stream_chat"] = {"facts": _evidence_facts(t, source_ids)}
                _z = _zero_or_uncertain_reply(t, source_ids)
                if _z:
                    r.pop("_stream_chat", None); r["reply"] = _z
                    r["matched"] = {"kind": "frag_state", "gate": "question_net"}
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
                                  defer_chat=defer_chat, project_id=project_id)
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
    if _OPEN_EDIT_RE.search(t):
        _core = _re.sub(
            r"(의)?\s*(장면|부분|컷|것|영상|조각)?\s*(만|들만|을|를|이|가|으로|로)?\s*"
            r"(나오게|남게|보이게)?\s*(위주로|중심으로)?\s*(다시)?\s*(편집|모아|골라|추려|만들어|남겨)?\s*"
            r"(해\s*줘|해줘|해\s*줄래|해줄래|해\s*주세요|해주세요|해\s*봐|해봐|줘|주세요|부탁해?)?[.!?~\s]*$", "", t).strip()
        if len(_core) >= 2:
            if _OPEN_EDIT_META_RE.search(t) and not _OPEN_EDIT_REQUEST_RE.search(t):
                return _resp("ask_clarification",
                             "지금 말씀은 편집 지시라기보다 고민이나 질문으로 들려요. "
                             "이 내용을 기준으로 편집안을 다시 만들고 싶으시면 "
                             "'이 기준으로 편집해줘'처럼 말씀해 주세요.",
                             normalized=t, confidence=0.82, via="deterministic",
                             matched={"kind": "open_theme_confirm", "core": _core})
            return _resp("run_proposal",
                         f"네, \"{_core}\" 기준으로 골라볼게요. 맞는 조각이 없으면 솔직히 말씀드릴게요.",
                         normalized=t, confidence=0.75, via="deterministic",
                         matched={"kind": "open_theme", "core": _core})

    # ── 6. 결정론이 전부 놓친 말 → Qwen 종업원 ──
    if allow_llm:
        llm = _llm_understand(t, recent_messages, source_ids, person_vocab,
                              defer_chat=defer_chat, project_id=project_id)
        if llm:
            return llm
    # [국장지시 2026-07-06] 못 알아들어도 편집 조건을 강요하지 않는다 — 대화도 정상 경로
    return _resp("ask_clarification",
                 "제가 정확히 못 알아들었어요. 편하게 다시 말씀해 주세요 — "
                 "그냥 이야기하셔도 좋고, 편집은 '누가 나오는 장면만'처럼 "
                 "말씀하시면 바로 움직여요.",
                 confidence=0.5)
