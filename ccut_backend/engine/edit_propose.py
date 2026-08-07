"""
[PROPOSE-1A 2026-08-07] 대화 → 경계 편집 제안.

structural_chat_edit_conflict — "아? 편집 정말 어렵다"류가 되묻기 템플릿으로
죽던 자리(main.py _chat_only_speed_bypass)에서 호출된다.
문은 분류 전체에 열려 있다 — 특정 문장 하드코딩 없음.

역할 분담(이중핵):
  서버 = 근거·숫자·페이로드 전부 계산. ms급 실데이터는 subtitles.segments
         단어 타이밍뿐이다(이중 JSON 인코딩 — ledger_r0._parse_segments 재사용).
  큐원 = 문장만. 큐원 텍스트에서 숫자를 파싱하지 않는다 — 카드 표시값은
         서버 계산값 직결. 숫자 검문(_numbers_ok)이 제공하지 않은 숫자를
         잡으면 서버 문장으로 강등한다.

저장: 없음(신규 테이블 0). 제안은 route 응답 payload 로만 존재한다.
적용: 기존 POST /edit-state (command_type=TRIM, origin=NATURAL_LANGUAGE).
되돌리기: 프론트가 적용 직전 값을 GET /edit-state/{program_id} 로 확보한 뒤
         RESTORE 로 재저장(전진 복귀). vault_events 가 before/after 를 감사 기록.

좌표 병기: fragment_id + source_id + anchor_start/end_ms 를 제안에 싣고,
읽는 코드는 적용 경로(payload 의 parent_fragment_id·anchor) 자체다.
timeline_item_id 발급식은 ledger_r0(315행) 및 프론트 timelineItemIdFor 와
반드시 동일해야 한다 — 다르면 같은 조각에 두 번째 행이 생긴다(NA/B 분열 전례).
"""
import json
import os
import re
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

# 판정 문턱 — 실측 근거: SF_042F66 시작 경계의 말 공백 0.66s 를 사용자가 실제로
# 1.8s 트림했다(fragment_edit_state ES_27B980E605B7). 0.5s 이상이면 제안할 가치,
# 0.3s 미만 변화는 소음, 다듬은 뒤에도 1s 는 남아야 조각이 산다.
MIN_GAP_MS = 500      # 경계 말 공백이 이보다 짧으면 제안하지 않는다
PAD_MS = 120          # 첫/끝 발화에 두는 여유 (단어 경계 절단 방지)
MIN_DELTA_MS = 300    # 현재 trim 과의 차이가 이보다 작으면 무의미
MIN_KEEP_MS = 1000    # 다듬은 뒤 남는 길이 하한


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


# [PROPOSE-1A R1 2026-08-07] 문의 폭 — 막연한 어려움만 제안으로 받는다.
#   실측(화면): "숏츠 영상으로 만들어줄수 있나?" 가 편집충돌로 잡혀 엉뚱한
#   무음 다듬기 제안이 나갔다(동문서답). 구체 요청은 이 문이 아니라 사다리
#   (route_edit_intent understand)가 주인이다 — 그쪽으로 흘려보낸다.
_DIFFICULTY_RE = re.compile(
    r"어렵|어려워|어려운|모르겠|힘들|힘드|헷갈|막막|막혔|막혀|복잡|어떡|어쩌")


def is_vague_difficulty(text):
    """막연한 어려움 호소인가 — True 면 제안 문, False 면 사다리 계속."""
    return bool(_DIFFICULTY_RE.search(text or ""))


def _no_candidate_reply(reason):
    """근거가 없으면 억지로 만들지 않는다 — 정직한 무제안. 대화는 죽지 않는다."""
    return {
        "status": "OK",
        "action": "answer_only",
        "normalized_instruction": None,
        "reply": ("말씀 들었어요. 지금 자료에서는 바로 손볼 만한 경계를 찾지 못했어요. "
                  "어디가 어렵게 느껴지는지 편하게 말씀해 주세요."),
        "confidence": 0.85,
        "matched": {"kind": "propose_none", "gate": "structural_chat",
                    "reason": reason},
        "via": "propose_gate",
    }


def _words_by_source(con, source_id, cache):
    """subtitles.segments → [(start_s, end_s), ...] 절대 초. 소스당 1회 로드."""
    if source_id in cache:
        return cache[source_id]
    import ledger_r0
    words = []
    row = con.execute("SELECT segments FROM subtitles WHERE source_id=?",
                      (source_id,)).fetchone()
    if row and row["segments"]:
        try:
            for sg in ledger_r0._parse_segments(row["segments"]):
                for w in (sg.get("words") or []):
                    if isinstance(w, dict) and w.get("start") is not None \
                            and w.get("end") is not None:
                        words.append((float(w["start"]), float(w["end"])))
        except Exception as e:
            print(f"[PROPOSE-1A][WARN] segments 해석 실패 ({source_id}): {e}")
    words.sort()
    cache[source_id] = words
    return words


def find_candidates(program_id):
    """승인 원고의 각 조각에서 경계 말 공백을 재서 다듬기 후보를 만든다.

    공백은 '현재 trim 창' 기준이다 — 이미 사용자가 다듬은 자리는 다시 제안하지
    않는다(delta 문턱이 거른다). 반환은 gap 큰 순."""
    from story_gate import service as _story
    from edit_contract import service as _edit
    from edit_contract.time_units import to_ms
    import ledger_r0

    live = _story.live_approval(program_id)
    if not live:
        return []
    try:
        fids = json.loads(live.get("fragment_ids") or "[]")
    except Exception:
        fids = []
    if not fids:
        return []

    states = {}
    try:
        for s in _edit.list_edit_states(program_id):
            states[s["timeline_item_id"]] = s
    except Exception as e:
        print(f"[PROPOSE-1A][WARN] edit_state 목록 실패: {e}")

    con = _connect()
    try:
        marks = ",".join("?" * len(fids))
        rows = con.execute(
            f'SELECT fragment_id, source_id, start, "end" FROM semantic_fragments '
            f"WHERE fragment_id IN ({marks})", fids).fetchall()
        by_fid = {r["fragment_id"]: r for r in rows}

        seg_cache = {}
        cands = []
        for order, fid in enumerate(fids, 1):
            r = by_fid.get(fid)
            if not r:
                continue
            sid = r["source_id"]
            a_s, a_e = to_ms(float(r["start"] or 0)), to_ms(float(r["end"] or 0))
            item_id = f"ITEM_{ledger_r0._hash6(program_id)}_{fid}_0"
            st = states.get(item_id)
            if st and st.get("removed"):
                continue
            cur_s = int(st["trim_start_ms"]) if st else a_s
            cur_e = int(st["trim_end_ms"]) if st else a_e

            words = [(ws, we) for (ws, we) in _words_by_source(con, sid, seg_cache)
                     if we * 1000 > cur_s and ws * 1000 < cur_e]
            if not words:
                continue
            first_ms = to_ms(words[0][0])
            last_ms = to_ms(max(we for _, we in words))

            base = {
                "program_id": program_id,
                "timeline_item_id": item_id,
                "fragment_id": fid,
                "source_id": sid,
                "anchor_start_ms": a_s,
                "anchor_end_ms": a_e,
                "order": order,
                "current": {
                    "trim_start_ms": cur_s,
                    "trim_end_ms": cur_e,
                    "revision": (int(st["revision"]) if st else None),
                    "exists": bool(st),
                },
            }
            # 앞 경계: trim 시작 ~ 첫 발화
            lead_gap = first_ms - cur_s
            if lead_gap >= MIN_GAP_MS:
                prop_s = max(a_s, first_ms - PAD_MS)
                delta = prop_s - cur_s
                if delta >= MIN_DELTA_MS and (cur_e - prop_s) >= MIN_KEEP_MS:
                    cands.append({**base,
                                  "side": "start", "gap_ms": lead_gap,
                                  "delta_ms": delta,
                                  "boundary_word_ms": first_ms,
                                  "proposed": {"trim_start_ms": prop_s,
                                               "trim_end_ms": cur_e}})
            # 뒤 경계: 마지막 발화 ~ trim 끝
            tail_gap = cur_e - last_ms
            if tail_gap >= MIN_GAP_MS:
                prop_e = min(a_e, last_ms + PAD_MS)
                delta = cur_e - prop_e
                if delta >= MIN_DELTA_MS and (prop_e - cur_s) >= MIN_KEEP_MS:
                    cands.append({**base,
                                  "side": "end", "gap_ms": tail_gap,
                                  "delta_ms": delta,
                                  "boundary_word_ms": last_ms,
                                  "proposed": {"trim_start_ms": cur_s,
                                               "trim_end_ms": prop_e}})
        cands.sort(key=lambda c: -c["gap_ms"])
        return cands
    finally:
        con.close()


def _numbers_ok(say, allowed_texts):
    """큐원 문장의 숫자 검문 — 제공한 표시값에 없는 숫자가 섞이면 False.

    절대 금지 '실데이터에 없는 숫자'의 집행자. 모델에게 부탁만 하지 않는다."""
    nums = re.findall(r"\d+(?:\.\d+)?", say or "")
    allowed = set()
    for t in allowed_texts:
        allowed.update(re.findall(r"\d+(?:\.\d+)?", t or ""))
    bad = [n for n in nums if n not in allowed]
    if bad:
        print(f"[PROPOSE-1A][NUM-GUARD] 미제공 숫자 검출 → 서버 문장 강등: {bad}")
        return False
    return True


def _display_texts(cand, fragment_labels):
    """카드·문장에 쓸 표시값 — 전부 서버가 만든다."""
    label = None
    for disp, fid in (fragment_labels or {}).items():
        if fid == cand["fragment_id"]:
            label = str(disp)
            break
    if not label:
        label = f"{cand['order']}번째 조각"
    return {
        "label": label,
        "direction": "앞" if cand["side"] == "start" else "뒤",
        "gap_text": f"{cand['gap_ms'] / 1000:.1f}초",
        "amount_text": f"{cand['delta_ms'] / 1000:.1f}초",
        "order": cand["order"],
    }


def _fallback_sentence(disp):
    return (f"{disp['label']} {disp['direction']}쪽에 말이 없는 구간이 "
            f"{disp['gap_text']} 있어요. {disp['amount_text']} 다듬을 수 있는데, 해볼까요?")


def _phrase(user_text, disp):
    """큐원에게 문장만 부탁한다.

    강등 조건 셋(전부 서버가 집행): 위생 불량(_sanitize_talk) / 미제공 숫자
    (_numbers_ok) / 라벨 원문 훼손(제안이 가리키는 조각 지칭이 깨지면 거짓 제안 —
    실측: '3번째 조각' 을 'thirds 조각' 으로 바꾼 사례를 이 검문이 잡는다)."""
    from engine import hub
    from engine.intent_router import _sanitize_talk
    prompt = (
        "너는 CCUT — 영상 편집을 돕는 다정한 동료다.\n"
        f"사용자가 이렇게 말했다: \"{(user_text or '')[:120]}\"\n"
        "서버가 자료를 재서 편집 하나를 찾아뒀다. 아래 사실을 그대로 전하는 "
        "따뜻한 존댓말 1~2문장을 만들어라.\n"
        f"- 사실: {disp['label']} {disp['direction']}쪽에 말이 없는 구간이 "
        f"{disp['gap_text']} 있고, 다듬으면 {disp['amount_text']} 짧아진다\n"
        f"규칙: '{disp['label']}' 표기를 글자 그대로 포함하라. 숫자는 위에 적힌 "
        "것만 그대로 쓰고 새로 계산하지 마라. 호칭은 쓰지 마라. 결과가 좋아진다고 "
        "단정하지 마라. 해볼지 물어보는 말로 끝내라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5)
        say = _sanitize_talk(str(out.get("say") or "").strip())
        if say and disp["label"] not in say:
            print(f"[PROPOSE-1A][LABEL-GUARD] 라벨 훼손 → 서버 문장 강등: {say[:60]!r}")
            say = None
        if say and _numbers_ok(say, [disp["label"], disp["gap_text"],
                                     disp["amount_text"]]):
            return say, "qwen"
    except Exception as e:
        print(f"[PROPOSE-1A][WARN] 큐원 문장 실패 — 서버 문장 강등: {e}")
    return _fallback_sentence(disp), "server"


def propose_from_conflict(user_text, project_id, source_ids=None,
                          fragment_labels=None):
    """편집 충돌 분류에서 불린다. 항상 dict 를 돌려준다(제안 또는 정직한 무제안)."""
    if not project_id:
        return _no_candidate_reply("no_project")
    try:
        cands = find_candidates(project_id)
    except Exception as e:
        print(f"[PROPOSE-1A][WARN] 후보 계산 실패: {e}")
        cands = []
    if not cands:
        return _no_candidate_reply("no_boundary_gap")

    c = cands[0]
    disp = _display_texts(c, fragment_labels)
    say, say_source = _phrase(user_text, disp)
    return {
        "status": "OK",
        "action": "propose_edit",
        "normalized_instruction": None,
        "reply": say,
        "confidence": 0.9,
        "matched": {"kind": "boundary_trim_proposal", "gate": "structural_chat",
                    "say_source": say_source},
        "via": "propose_gate",
        "proposal": {
            "proposal_kind": "TRIM",
            "program_id": c["program_id"],
            "timeline_item_id": c["timeline_item_id"],
            "fragment_id": c["fragment_id"],
            "source_id": c["source_id"],
            "anchor_start_ms": c["anchor_start_ms"],
            "anchor_end_ms": c["anchor_end_ms"],
            "current": c["current"],
            "proposed": c["proposed"],
            "evidence": {
                "side": c["side"],
                "gap_ms": c["gap_ms"],
                "delta_ms": c["delta_ms"],
                "boundary_word_ms": c["boundary_word_ms"],
                "basis": "subtitles.segments word timing",
            },
            "display": disp,
        },
    }
