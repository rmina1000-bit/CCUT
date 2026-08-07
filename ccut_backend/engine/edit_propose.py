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
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5,
                               model=hub.VOICE_MODEL)
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


# ════════════════════════════════════════════════════════════════════
# [LIVING-DRAFT-1 2026-08-08] 말하면 해보고, 해본 것을 함께 고친다.
#
# PROPOSE-1A(제안→[해봐])의 다음 형태: 제안만 하지 않고 초안을 실제로
# 적용해 보여준다. 전부 비파괴 오버레이(fragment_edit_state) 위 —
# 원본 영상·승인 원고(story_approval)는 무접촉이고, 모든 쓰기는
# vault_events 에 before/after 로 남아 언제든 전진 복귀된다.
#
# 큰 의도(막연한 어려움·늘어짐 호소) → 서버가 재고 젬마가 말한다.
# 확정된 작은 행동(되돌리기·이대로) → 젬마 없이 결정론으로 집행한다.
# ════════════════════════════════════════════════════════════════════

# 초안 유발: 어려움 호소(기존) + 늘어짐 계열. 일부러 좁게 잡는다 —
# "답답해"·"길다" 같은 일상어는 안 받는다(동문서답 전례). 사전이 아니라 문의 폭이다.
_FRESH_DRAFT_RE = re.compile(
    r"어렵|모르겠|힘들|힘드|헷갈|막막|막혔|막혀|복잡|어떡|어쩌|늘어지|늘어져|지루|밋밋|루즈")
# 되돌림·보존 어휘 — 대상 조각 토큰 바로 뒤(10자 안)에 붙을 때만 그 조각에 적용
_KEEP_RE = re.compile(r"그대로|되돌려|원래대로|취소")
_ORDINAL_RE = re.compile(r"(\d{1,2})\s*번")
_LABEL_TOKEN_RE = re.compile(r"[A-Za-z]{1,2}\d{1,3}")


def _approved_fids(program_id):
    from story_gate import service as _story
    live = _story.live_approval(program_id)
    if not live:
        return []
    try:
        return json.loads(live.get("fragment_ids") or "[]")
    except Exception:
        return []


def _story_total_ms(program_id):
    """승인 원고의 현재 총 길이(ms) — edit state spans 반영, removed=0."""
    from edit_contract import service as _edit
    from edit_contract.time_units import to_ms
    import ledger_r0
    fids = _approved_fids(program_id)
    if not fids:
        return 0
    states = {}
    try:
        for s in _edit.list_edit_states(program_id):
            states[s["timeline_item_id"]] = s
    except Exception:
        pass
    con = _connect()
    try:
        marks = ",".join("?" * len(fids))
        rows = con.execute(
            f'SELECT fragment_id, start, "end" FROM semantic_fragments '
            f"WHERE fragment_id IN ({marks})", fids).fetchall()
        by_fid = {r["fragment_id"]: r for r in rows}
    finally:
        con.close()
    h6 = ledger_r0._hash6(program_id)
    total = 0
    for fid in fids:
        st = states.get(f"ITEM_{h6}_{fid}_0")
        if st:
            if st.get("removed"):
                continue
            total += sum(int(e) - int(s) for s, e in (st.get("spans") or []))
        else:
            r = by_fid.get(fid)
            if r:
                total += to_ms(float(r["end"] or 0)) - to_ms(float(r["start"] or 0))
    return total


def _recent_drafts(program_id, limit=5):
    """최근 초안들(vault_events, origin=NATURAL_LANGUAGE) — item별 최신 1건."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT event_id, fragment_id, detail FROM vault_events "
            "WHERE event_kind='edit_command' AND program_id=? "
            "ORDER BY event_id DESC LIMIT 40", (program_id,)).fetchall()
    finally:
        con.close()
    out = {}
    for r in rows:
        try:
            d = json.loads(r["detail"] or "{}")
        except Exception:
            continue
        if d.get("origin") != "NATURAL_LANGUAGE":
            continue
        item = d.get("timeline_item_id")
        if item and item not in out:
            out[item] = {"event_id": r["event_id"], "fragment_id": r["fragment_id"],
                         "detail": d}
        if len(out) >= limit:
            break
    return out


def _parse_targets(text, fragment_labels, fids):
    """본문에서 대상 조각을 뽑는다: 'N번'(승인 순번) / 라벨(A60 등).
    반환 [(fragment_id, keep여부, order또는None, 표시라벨), ...] — 등장 순."""
    targets = []
    seen = set()
    label_map = {str(k): v for k, v in (fragment_labels or {}).items()}
    for m in list(_ORDINAL_RE.finditer(text)) + list(_LABEL_TOKEN_RE.finditer(text)):
        tok = m.group(0)
        if m.re is _ORDINAL_RE:
            order = int(m.group(1))
            if not (1 <= order <= len(fids)):
                continue
            fid = fids[order - 1]
            disp = f"{order}번"
        else:
            fid = label_map.get(tok) or label_map.get(tok.upper())
            if not fid or fid not in fids:
                continue
            disp = tok.upper()
        if fid in seen:
            continue
        seen.add(fid)
        tail = text[m.end():m.end() + 10]
        keep = bool(_KEEP_RE.search(tail))
        targets.append((fid, keep, disp))
    return targets


def _apply_state(program_id, fid, source_id, anchor, trim, command, before_state=None):
    """서버측 upsert — 프론트 [해봐] 핸들러와 동일 절차(현재 revision 재조회)."""
    from edit_contract import service as _edit
    import ledger_r0
    item_id = f"ITEM_{ledger_r0._hash6(program_id)}_{fid}_0"
    row = None
    try:
        for s in _edit.list_edit_states(program_id):
            if s["timeline_item_id"] == item_id:
                row = s
                break
    except Exception:
        pass
    before = ({"trim_start_ms": row["trim_start_ms"], "trim_end_ms": row["trim_end_ms"],
               "excluded_ranges": row.get("excluded_ranges") or [],
               "removed": bool(row.get("removed"))}
              if row else
              {"trim_start_ms": anchor[0], "trim_end_ms": anchor[1],
               "excluded_ranges": [], "removed": False})
    payload = {
        "program_id": program_id, "timeline_item_id": item_id, "source_id": source_id,
        "anchor_start_ms": anchor[0], "anchor_end_ms": anchor[1],
        "trim_start_ms": trim[0], "trim_end_ms": trim[1],
        "excluded_ranges": (before_state or before)["excluded_ranges"],
        "removed": bool((before_state or {}).get("removed", False)),
        "parent_fragment_id": fid, "occurrence": 0,
        "command_type": command, "origin": "NATURAL_LANGUAGE",
    }
    if row:
        payload["revision"] = row["revision"]
    res = _edit.upsert_edit_state(payload)
    return res, before, item_id


def _phrase_draft(user_text, disp):
    """초안 보고 문장 — 젬마가 말하고 서버가 검문한다(라벨·숫자·위생)."""
    from engine import hub
    from engine.intent_router import _sanitize_talk
    prompt = (
        "너는 CCUT — 영상 편집실의 동료다. 사용자가 이렇게 말했다: "
        f"\"{(user_text or '')[:120]}\"\n"
        "서버가 초안을 실제로 만들어 화면에 적용해 뒀다. 아래 사실을 그대로 전하는 "
        "따뜻한 존댓말 1~2문장을 만들어라.\n"
        f"- 한 일: {disp['label']} {disp['direction']}쪽 말 없는 구간을 다듬어 "
        f"{disp['amount_text']} 줄였다\n"
        f"- 전체 길이: {disp['story_before_text']} → {disp['story_after_text']}\n"
        f"규칙: '{disp['label']}' 표기를 글자 그대로 포함하라. 숫자는 위에 적힌 것만 "
        "그대로 써라. 이미 적용된 상태다 — 해도 되는지 묻지 말고, 보고 마음에 안 들면 "
        "고칠 수 있다는 투로 끝내라.\n"
        'JSON만 출력: {"say":"..."}'
    )
    try:
        out = hub._ollama_json(prompt, timeout=20, temperature=0.5,
                               model=hub.VOICE_MODEL)
        say = _sanitize_talk(str(out.get("say") or "").strip())
        if say and disp["label"] not in say:
            print(f"[LIVING-DRAFT][LABEL-GUARD] 강등: {say[:60]!r}")
            say = None
        if say and _numbers_ok(say, [disp["label"], disp["amount_text"],
                                     disp["story_before_text"],
                                     disp["story_after_text"]]):
            return say, "gemma"
    except Exception as e:
        print(f"[LIVING-DRAFT][WARN] 문장 실패 — 서버 문장 강등: {e}")
    return (f"{disp['label']} {disp['direction']}쪽 말 없는 구간을 "
            f"{disp['amount_text']} 다듬어 봤어요. 전체 {disp['story_before_text']} → "
            f"{disp['story_after_text']}예요. 마음에 안 들면 되돌릴 수 있어요."), "server"


def _sec_text(ms):
    return f"{ms / 1000:.0f}초"


def draft_gate(user_text, project_id, source_ids=None, fragment_labels=None):
    """초안 문 — 발동 안 하면 None(사다리 계속). 발동하면 실제로 적용하고 보고한다."""
    t = (user_text or "").strip()
    if not t or not project_id:
        return None
    fresh = bool(_FRESH_DRAFT_RE.search(t))
    fids = _approved_fids(project_id)
    if not fids:
        return None
    targets = _parse_targets(t, fragment_labels, fids)
    if not fresh and not targets:
        return None
    drafts_ctx = _recent_drafts(project_id)
    # 표적 지목만 있고(어려움 호소 없음) 초안 문맥도 없으면 이 문이 아니다 —
    # "11번 보여줘" 같은 조회를 가로채지 않는다.
    if not fresh and targets and not drafts_ctx:
        return None

    import ledger_r0
    h6 = ledger_r0._hash6(project_id)
    story_before = _story_total_ms(project_id)
    reverted = []
    # ① 되돌림(확정된 작은 행동 — 결정론, 젬마 무경유)
    for fid, keep, disp in targets:
        if not keep:
            continue
        item_id = f"ITEM_{h6}_{fid}_0"
        ctx = drafts_ctx.get(item_id)
        if not ctx:
            continue  # 초안이 없던 조각의 '그대로'는 이미 그대로다
        b = (ctx["detail"].get("before") or {})
        trim = b.get("trim_ms") or []
        if len(trim) != 2:
            continue
        anchor = None
        con = _connect()
        try:
            r = con.execute('SELECT source_id, start, "end" FROM semantic_fragments '
                            "WHERE fragment_id=?", (fid,)).fetchone()
        finally:
            con.close()
        if not r:
            continue
        from edit_contract.time_units import to_ms
        anchor = (to_ms(float(r["start"] or 0)), to_ms(float(r["end"] or 0)))
        _apply_state(project_id, fid, r["source_id"], anchor,
                     (int(trim[0]), int(trim[1])), "RESTORE",
                     before_state={"excluded_ranges": b.get("excluded_ranges_ms") or [],
                                   "removed": bool(b.get("removed"))})
        reverted.append(disp)

    # ② 새 초안 — 표적이 지목됐으면 그 조각에서, 아니면 전체 최적 후보
    draft_targets = [fid for fid, keep, _ in targets if not keep]
    cands = find_candidates(project_id)
    if draft_targets:
        cands = [c for c in cands if c["fragment_id"] in draft_targets]
    cand = cands[0] if cands else None

    if not cand:
        parts = []
        if reverted:
            parts.append(f"{'·'.join(reverted)}을 원래대로 되돌렸어요.")
        if draft_targets or fresh:
            parts.append("지금 자료에서는 더 다듬을 만한 경계를 찾지 못했어요.")
        if not parts:
            return None
        return {
            "status": "OK", "action": "answer_only", "normalized_instruction": None,
            "reply": " ".join(parts), "confidence": 0.88,
            "matched": {"kind": "draft_none" if not reverted else "draft_reverted",
                        "gate": "living_draft", "reverted": reverted},
            "via": "draft_gate",
        }

    # 초안 실제 적용 (비파괴 오버레이 — 원본·승인원고 무접촉)
    res, before, item_id = _apply_state(
        project_id, cand["fragment_id"], cand["source_id"],
        (cand["anchor_start_ms"], cand["anchor_end_ms"]),
        (cand["proposed"]["trim_start_ms"], cand["proposed"]["trim_end_ms"]), "TRIM")
    story_after = _story_total_ms(project_id)

    disp = _display_texts(cand, fragment_labels)
    disp["story_before_text"] = _sec_text(story_before)
    disp["story_after_text"] = _sec_text(story_after)
    say, say_source = _phrase_draft(t, disp)
    if reverted:
        say = f"{'·'.join(reverted)}은 원래대로 되돌렸어요. " + say
    return {
        "status": "OK", "action": "draft_applied", "normalized_instruction": None,
        "reply": say, "confidence": 0.9,
        "matched": {"kind": "living_draft", "gate": "living_draft",
                    "say_source": say_source, "reverted": reverted},
        "via": "draft_gate",
        "draft": {
            "program_id": project_id, "timeline_item_id": item_id,
            "fragment_id": cand["fragment_id"], "source_id": cand["source_id"],
            "anchor_start_ms": cand["anchor_start_ms"],
            "anchor_end_ms": cand["anchor_end_ms"],
            "before": before,
            "after": {"trim_start_ms": cand["proposed"]["trim_start_ms"],
                      "trim_end_ms": cand["proposed"]["trim_end_ms"]},
            "revision": res.get("revision"),
            "side": cand["side"], "gap_ms": cand["gap_ms"],
            "delta_ms": cand["delta_ms"],
            "story": {"before_ms": story_before, "after_ms": story_after},
            "display": disp,
        },
    }


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
