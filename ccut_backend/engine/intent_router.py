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


def _llm_smalltalk(input_text, recent_messages=None):
    """[SMALLTALK] 질문/잡담에 사람다운 답 — '나는 편집기라서'류 거절 금지 (국장:
    거절은 사용자를 바보 취급하는 것). 실패 시 None → 호출부가 따뜻한 고정 문구."""
    ctx = ""
    for m in (recent_messages or [])[-4:]:
        who = "사용자" if (m.get("sender") == "user") else "CCUT"
        txt = str(m.get("text") or "")[:80]
        if txt:
            ctx += f"{who}: {txt}\n"
    prompt = (
        "너는 CCUT — 영상 편집을 돕는 다정한 동료다. 사용자의 질문/잡담에 짧고 따뜻한 "
        "존댓말 한국어 1~2문장으로 '실제로' 대답한다. 절대 '저는 편집기라서'류의 거절을 "
        "하지 않는다. 자연스러우면 끝에 편집 도움을 가볍게 제안해도 된다.\n"
        'JSON만 출력: {"reply":"..."}\n'
        + (f"최근 대화:\n{ctx}" if ctx else "")
        + f"사용자: {input_text}\n")
    try:
        out = hub._ollama_json(prompt, timeout=20)
        reply = str(out.get("reply") or "").strip()
        return reply or None
    except Exception as e:
        print(f"[INTENT-ROUTER] smalltalk 실패 ({e})")
        return None


def route_edit_intent(source_ids=None, input_text="", recent_messages=None,
                      selected_proposal_id=None, allow_llm=True, person_vocab=None,
                      archive_lookup=None, search_lookup=None):
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

    # ── 0.7 맨몸 재편집 [BARE-REDO] — "편집을 다시해줘"처럼 새 조건이 없는 재요청은
    #    옛 지시를 무단 재사용하지 않고 되묻는다 (국장 지적 2026-07-05: LLM 폴백이
    #    직전 '물놀이' 지시를 그대로 다시 실행해버린 사건). 조건이 붙어 있으면
    #    ("은한이만 다시") 아래 사다리가 정상 처리.
    if len(t) <= 15 and _re.match(
            r"^(편집|제안|영상)?\s*(을|를)?\s*(다시|재)\s*(편집)?\s*"
            r"(해\s*줘|해줘|해\s*봐|해봐|부탁해?|만들어\s*줘|만들어줘|하자|할래)?[.!~?\s]*$", t):
        _prev = None
        for m in reversed(recent_messages or []):
            txt = str(m.get("text") or "").strip()
            if m.get("sender") == "user" and txt and len(txt) > 3 \
                    and not _re.match(r"^(편집|제안|영상)?\s*(을|를)?\s*(다시|재)", txt):
                _prev = txt[:40]
                break
        reply = (f"다시 하기 전에 기준을 여쭤볼게요 — 이전처럼 \"{_prev}\" 그대로 갈까요, "
                 "아니면 다른 방향으로 바꿀까요?" if _prev
                 else "어떤 방향으로 다시 할까요? 예: '사람 중심으로', '더 짧게', '실내만'.")
        return _resp("ask_clarification", reply, confidence=0.9, via="deterministic",
                     matched={"kind": "bare_redo", "prev": _prev})

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

    # ── 5. 질문/잡담 — 거절하지 않고 대화한다 (국장: 거절 = "난 바보예요") ──
    #    단, 편집 동사가 있으면("생일잔치만 편집해줄래?") 질문 꼴이어도 편집으로 —
    #    아래 5.5 OPEN-EDIT가 처리하게 통과시킨다.
    q_re, vague_re = _regexes()
    if q_re.search(t) and not _re.search(r"편집|나오게|남게|남겨|골라|만들|빼|줄여|늘려|위주|중심|모아|추려", t):
        if allow_llm:
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
            llm = _llm_route(t, recent_messages)
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
        llm = _llm_route(t, recent_messages)
        if llm:
            return llm
    return _resp("ask_clarification",
                 "말씀을 편집 조건으로 정확히 못 알아들었어요. '누가 나오는 장면만', "
                 "'어떤 장소만', '몇 개로' 같은 형태로 다시 말씀해 주시겠어요?",
                 confidence=0.5)
