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

from engine import hub

_ACTIONS = ("run_proposal", "revise_current", "ask_clarification", "answer_only")

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


def _llm_route(input_text, recent_messages=None):
    """Qwen2.5 라우팅 — 결정론이 못 잡은 말만 온다. 실패 시 None(호출부가 되묻기)."""
    ctx = ""
    for m in (recent_messages or [])[-4:]:
        who = "사용자" if (m.get("sender") == "user") else "편집기"
        txt = str(m.get("text") or "")[:80]
        if txt:
            ctx += f"{who}: {txt}\n"
    prompt = (
        "너는 영상 편집기의 접수 담당(종업원)이다. 사용자의 말을 아래 4가지 중 하나로 분류한다.\n"
        "- run_proposal: 편집 조건이 담긴 실행 지시 (예: '물놀이 장면 위주로', '앞부분 위주로 짧게')\n"
        "- revise_current: 현재 안에 대한 국소 수정 (예: '마지막 조각 빼줘', '두 번째만 바꿔')\n"
        "- ask_clarification: 편집 의도는 있는데 조건이 모호 (예: '느낌있게 해줘')\n"
        "- answer_only: 편집 지시가 아닌 질문/잡담\n"
        "run_proposal이면 normalized_instruction에 실행 가능한 형태의 한국어 지시문을 만들어라.\n"
        "reply는 공손한 한국어 한 문장(존댓말, 종업원 말투)으로.\n"
        "JSON만 출력: {\"action\":\"...\",\"normalized_instruction\":\"...\",\"reply\":\"...\",\"confidence\":0.0~1.0}\n"
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n"
    )
    try:
        out = hub._ollama_json(prompt, timeout=30)
        action = str(out.get("action") or "").strip()
        if action not in _ACTIONS:
            return None
        return _resp(
            action,
            str(out.get("reply") or "").strip() or "네, 말씀 확인했습니다.",
            normalized=(str(out.get("normalized_instruction") or "").strip() or None),
            confidence=out.get("confidence") or 0.6,
            via="qwen",
        )
    except Exception as e:
        print(f"[INTENT-ROUTER] llm route 실패 ({e})")
        return None


def route_edit_intent(source_ids=None, input_text="", recent_messages=None,
                      selected_proposal_id=None, allow_llm=True, person_vocab=None):
    t = (input_text or "").strip()
    if not t:
        return _resp("ask_clarification", "말씀을 조금만 더 입력해 주세요.", confidence=1.0)

    # ── 1. 인물 이름/애칭 (저장은 풀네임, 부를 땐 애칭 — 애칭이면 풀네임으로 정규화) ──
    person = hub.resolve_person_name(t, vocab=person_vocab)
    if person:
        canonical, matched = person["canonical"], person["matched"]
        normalized = t.replace(matched, canonical) if matched != canonical else t
        is_excl = any(k in t for k in hub._EXCLUDE_MARK) or "아닌" in t
        if matched != canonical:
            reply = (f"아, {matched} — {canonical} 말씀이시죠. "
                     + (f"{canonical} 나오는 장면은 빼고 다시 골라볼게요." if is_excl
                        else f"그 사람이 나오는 장면만 다시 골라볼게요."))
        else:
            reply = (f"네, {canonical} 나오는 장면은 빼고 다시 골라볼게요." if is_excl
                     else f"네, {canonical} 나오는 장면만 다시 골라볼게요.")
        return _resp("run_proposal", reply, normalized=normalized,
                     confidence=person.get("confidence", 0.95),
                     matched={"kind": "person_alias" if matched != canonical else "person",
                              "input": matched, "canonical": canonical,
                              "person_id": person.get("person_id")})

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
    if re.search(r"이대로|진행|확정|좋아|오케이|ok", t, re.IGNORECASE):
        return _resp("run_proposal", "네, 지금 방향 그대로 진행하겠습니다.",
                     normalized=t, confidence=0.85, matched={"kind": "confirm"})

    # ── 4. 현재 안 국소 수정 (CCUT_REVISION 게이트) ──
    if selected_proposal_id and os.getenv("CCUT_REVISION", "0") in ("1", "true", "True"):
        try:
            from engine import revision as _rev
            if _rev.detect_revision(t, True):
                return _resp("revise_current", "네, 지금 안에서 그 부분만 손보겠습니다.",
                             normalized=t, confidence=0.85, matched={"kind": "revision"})
        except Exception:
            pass

    # ── 5. 질문/모호 ──
    q_re, vague_re = _regexes()
    if q_re.search(t):
        return _resp("answer_only",
                     "저는 편집 지시를 실행하는 편집기예요. '정은한 나오는 장면만', "
                     "'실내만', '5개로 줄여줘'처럼 조건을 말씀해주시면 바로 움직일게요.",
                     confidence=0.8)
    if vague_re.search(t):
        if allow_llm:
            llm = _llm_route(t, recent_messages)
            if llm:
                return llm
        return _resp("ask_clarification",
                     "어떤 기준으로 고를지 조금만 더 구체적으로 말씀해 주세요 — "
                     "예: '정은한 나오는 장면만', '실내만', '더 빠르게'.",
                     confidence=0.7)

    # ── 6. 결정론이 전부 놓친 말 → Qwen 종업원 ──
    if allow_llm:
        llm = _llm_route(t, recent_messages)
        if llm:
            return llm
    return _resp("ask_clarification",
                 "말씀을 편집 조건으로 정확히 못 알아들었어요. '누가 나오는 장면만', "
                 "'어떤 장소만', '몇 개로' 같은 형태로 다시 말씀해 주시겠어요?",
                 confidence=0.5)
