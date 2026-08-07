"""
[BREATH-1 2026-08-08] 젬마의 호흡.

국장: "ccut을 ccut답게 할 수 있는 젬마의 호흡이야. 호흡... 숨쉬기"

지금까지 젬마는 숨을 못 쉬었다.
  들이쉬면 — 오염된 기억이 새 말을 덮고, 화면에서 벌어진 일은 안 보이고,
             지금 편집이 어떤 상태인지 몰랐다.
  내쉬려면 — 정규식이 먼저 답을 정해 버렸다.

이 파일이 하는 일은 셋뿐이다.
  들숨(inhale)  현재 세계를 짧은 사실로 젬마에게 보인다. 사용자 원문은 원문 그대로.
  날숨(exhale)  젬마가 다음 숨을 고른다 — TALK / LOOK / TRY / PROPOSE / ASK.
  되돌아오는 숨 서버가 그 선택을 실데이터로 채워 다시 들이쉬게 한다(최대 2호흡).

원칙
  · 숫자는 전부 서버가 잰다. 젬마는 의미를 판단하고 말한다.
  · 사용자 승인 전에는 아무것도 바뀌지 않는다(TRY 는 계산일 뿐 쓰기 0).
  · 사전을 만들지 않는다 — 어떤 문장이 오든 같은 호흡이 돈다.
  · 새 저장소를 만들지 않는다 — 재료는 이미 전부 있었다.
"""
import json
import os
import re

from engine import edit_propose as _ep

# [게이트 — 기본 OFF] 2026-08-08 실측 결과 아직 제품에 세울 수 없다. 아래 [남은 벽] 참조.
#   켜려면 CCUT_GEMMA_BREATH=1. 코드는 다음 차수의 재료로 남긴다.
ENABLED = os.getenv("CCUT_GEMMA_BREATH", "0") in ("1", "true", "True", "on", "ON")

# ── [남은 벽 — 젬마 4B 실측, 2026-08-08] ──────────────────────────────────
# 세 구조를 차례로 세워 보고 전부 같은 벽에 부딪혔다.
#
#  ① 행동 이름 고르기(TALK/LOOK/TRY/PROPOSE/ASK)
#     → 6문장 중 6번 TALK. LOOK 을 한 번도 안 골랐다. 이름 선택 자체를 못 한다.
#  ② 살펴본 결과를 처음부터 보여주기
#     → 인사·감사에도 제안을 얹었다(5/5). 눈앞의 것이 앵커가 된다.
#  ③ 예/아니오 한 판단(need_edit) + 살펴본 뒤 둘째 숨
#     → 판정은 붙었으나 말이 따라오지 않았다. 살펴본 결과를 보고도
#       "어떤 부분을 늘리고 싶으신가요?"(오해)처럼 되물었고,
#       SAY-GUARD 가 4/4 발동해 서버 문장이 젬마 말을 대체했다.
#       그 순간 이것은 '젬마의 호흡'이 아니라 서버 방송의 재발이다.
#
# 즉 젬마 4B 는 **대화는 잘하지만, 구조화된 사실을 읽고 그것을 근거로 판단해
# 자기 말로 옮기는 일**을 아직 못 한다. 프롬프트를 더 조여 봐야 사전과 서버
# 문장만 늘어난다 — 국장이 경계한 바로 그 방향이다.
#
# 다음에 시도할 것(권고 순서)
#   1. 젬마에게 판단을 시키지 말고, 서버가 후보를 고르고 젬마는 그 한 후보를
#      사람 말로 옮기기만 한다(PROPOSE-1A/_phrase 방식 — 이미 성공한 형태).
#   2. 그래도 부족하면 CCUT 실제 궤적(원문·관찰·행동·결과·반응)을 모아 후학습.
#   3. 행동 선택권은 그 뒤에 다시 시도한다.
# ──────────────────────────────────────────────────────────────────────

# 젬마가 고를 수 있는 숨. 사용자 화면에는 없는 이름이다(내부 계약).
BREATHS = ("TALK", "LOOK", "TRY", "PROPOSE", "ASK")

_ORDINAL_RE = re.compile(r"(\d{1,2})\s*번")


def _fmt_sec(ms):
    return f"{(ms or 0) / 1000:.0f}초"


def world(program_id, fragment_labels=None):
    """지금 세계 — 짧게. 매 턴 이만큼만 보인다(전 DB 를 펼치지 않는다)."""
    try:
        fids = _ep._approved_fids(program_id)
    except Exception:
        fids = []
    if not fids:
        return None
    total = _ep._story_total_ms(program_id)
    drafts = _ep._recent_drafts(program_id)
    label_of = {}
    for disp, fid in (fragment_labels or {}).items():
        label_of[str(fid)] = str(disp)
    recent = []
    for item, d in list(drafts.items())[:3]:
        det = d.get("detail") or {}
        b = (det.get("before") or {}).get("trim_ms") or []
        a = (det.get("after") or {}).get("trim_ms") or []
        if len(b) == 2 and len(a) == 2:
            moved = (a[0] - b[0]) + (b[1] - a[1])
            fid = d.get("fragment_id") or ""
            recent.append(f"{label_of.get(fid, fid)} {moved / 1000:.1f}초 다듬음")
    return {
        "fragment_count": len(fids),
        "total_ms": total,
        "total_text": _fmt_sec(total),
        "recent_edits": recent,
        "fids": fids,
        "labels": label_of,
    }


def _world_lines(w):
    lines = [f"- 승인된 이야기: 조각 {w['fragment_count']}개, 전체 {w['total_text']}"]
    if w["recent_edits"]:
        lines.append("- 최근 내가 다듬은 것: " + ", ".join(w["recent_edits"]))
    else:
        lines.append("- 아직 다듬은 곳 없음")
    return "\n".join(lines)


def _labels_for(w, cands):
    """후보에 사람이 부르는 이름을 붙인다(라벨 없으면 승인 순번)."""
    out = []
    for c in cands:
        fid = c["fragment_id"]
        label = w["labels"].get(fid)
        if not label:
            try:
                label = f"{w['fids'].index(fid) + 1}번"
            except ValueError:
                label = fid
        out.append((label, c))
    return out


def look_block(program_id, w, target_text=""):
    """LOOK — 지금 편집을 살펴본 결과. 읽기만 한다(쓰기 0)."""
    cands = _ep.find_candidates(program_id)
    # 사용자가 특정 조각을 가리켰으면 그것부터
    m = _ORDINAL_RE.search(target_text or "")
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(w["fids"]):
            want = w["fids"][idx]
            cands = [c for c in cands if c["fragment_id"] == want] or cands
    pairs = _labels_for(w, cands)[:4]
    if not pairs:
        return "살펴본 결과: 지금 경계에서 덜어낼 만한 말 없는 구간을 찾지 못했다.", []
    lines = ["살펴본 결과 — 말이 없는 구간(서버 실측):"]
    for label, c in pairs:
        side = "앞" if c["side"] == "start" else "뒤"
        lines.append(f"- {label} {side}쪽 {c['gap_ms'] / 1000:.1f}초 비어 있음 "
                     f"(다듬으면 {c['delta_ms'] / 1000:.1f}초 줄어듦)")
    return "\n".join(lines), pairs


def try_block(program_id, w, pairs, pick_label=None):
    """TRY — 적용하면 어떻게 되는지 계산만 한다. DB 쓰기 0."""
    if not pairs:
        return None, None
    chosen = None
    if pick_label:
        for label, c in pairs:
            if str(pick_label).strip() and str(pick_label).strip() in label:
                chosen = (label, c)
                break
    if not chosen:
        chosen = pairs[0]
    label, c = chosen
    after_total = w["total_ms"] - c["delta_ms"]
    side = "앞" if c["side"] == "start" else "뒤"
    text = (f"계산만 해봤다(아직 아무것도 바꾸지 않았다): {label} {side}쪽을 "
            f"{c['delta_ms'] / 1000:.1f}초 다듬으면 전체가 {w['total_text']} → "
            f"{_fmt_sec(after_total)}가 될 것이다.\n"
            f"※ 이것은 예상값이다. 실제로 바뀌려면 사용자가 승인해야 한다. "
            f"'다듬었다'처럼 이미 한 것처럼 말하면 거짓말이 된다.")
    return text, {"label": label, "cand": c, "after_total_ms": after_total}


# 하지 않은 일을 했다고 말하는 것을 막는다 — 실데이터에 없는 사실을 말하지 않는 것과
# 같은 규칙이다. 걸리면 서버 문장으로 강등한다(말을 죽이는 게 아니라 사실로 되돌린다).
_DONE_RE = re.compile(
    r"다듬었|줄였|줄어들었|적용했|반영했|바꿨|잘라냈|했습니다만|완료했|정리했")


def _ask_gemma(user_text, recent_messages, world_text, extra_block=None,
               breath_no=1):
    """젬마에게 세계를 보이고 다음 숨을 묻는다. 말투는 젬마 것이다."""
    from engine import hub
    from engine.ccut_manual import CCUT_MANUAL

    ctx = ""
    for m in (recent_messages or [])[-6:]:
        who = "사용자" if (m.get("sender") == "user") else "나"
        txt = str(m.get("text") or "")[:100]
        if txt:
            ctx += f"{who}: {txt}\n"

    parts = [
        CCUT_MANUAL.strip(),
        "",
        "[지금 이 이야기]",
        world_text,
    ]
    if extra_block:
        parts += ["", "[방금 내가 살펴본 것 — 서버 실측]", extra_block,
                  "",
                  "이제 이것을 바탕으로 사용자에게 답한다.",
                  "권할 만하면 권하고(need_edit: true), 정말 애매하면 묻는다"
                  "(need_edit: false). 위 숫자만 쓴다."]
    parts += [
        "",
        "[최근 대화]",
        ctx.strip() or "(없음)",
        "",
        f"[사용자가 방금 한 말]\n{user_text}",
        "",
        "[먼저 한 가지만 판단한다]",
        "사용자가 지금 영상을 손보고 싶어 하는가?",
        "  손보고 싶어 한다 → need_edit: true",
        "  그냥 이야기하는 중이다(인사·잡담·고맙다는 말·지금이 좋다는 말) "
        "→ need_edit: false",
        "",
        "need_edit 이 true 면 내가 지금 편집을 살펴보고 다시 물어보겠다 — "
        "그때 답하면 되니 지금은 짧게 대답하라.",
        "false 면 그냥 사람으로서 대답한다. 편집 얘기를 꺼내지 마라.",
        "숫자는 위에 적힌 것만 쓴다. 네가 계산하지 않는다.",
        "손댈 필요가 없으면 없다고 말해도 된다.",
        "아직 실제로 바꾼 것은 없다 — 사용자가 승인해야 바뀐다. "
        "이미 다듬었다고 말하지 마라.",
        'JSON만 출력: {"need_edit":true|false,"say":"사용자에게 할 말",'
        '"target":"사용자가 특정 조각을 가리켰으면 그 이름, 없으면 빈 문자열"}',
    ]
    prompt = "\n".join(parts)
    try:
        out = hub._ollama_json(prompt, timeout=30, temperature=0.6,
                              model=hub.VOICE_MODEL)
    except Exception as e:
        print(f"[BREATH][WARN] 젬마 미응답({breath_no}호흡): {e}")
        return None
    # 젬마 4B 실측: 행동 이름(TALK/LOOK/TRY/PROPOSE/ASK) 고르기는 6/6 실패했다.
    #   말은 잘하는데 이름은 못 고른다 — 그래서 예/아니오 하나만 묻는다.
    need = out.get("need_edit")
    if isinstance(need, str):
        need = need.strip().lower() in ("true", "yes", "y", "1", "네", "예")
    breath = "LOOK" if need else "TALK"
    if breath_no >= 2:
        # 살펴본 뒤에는 권할지 물을지만 남는다 — 권할 거리가 있으면 서버가 올린다.
        breath = "PROPOSE" if need else "ASK"
    from engine.intent_router import _sanitize_talk
    say = _sanitize_talk(str(out.get("say") or "").strip()) or ""
    return {"breath": breath, "say": say,
            "target": str(out.get("target") or "").strip()}


def breathe(user_text, program_id, recent_messages=None, fragment_labels=None):
    """한 번의 호흡.

    ★들숨에 세계가 다 들어온다 — 조각·길이·최근 편집에 더해 '살펴본 결과'까지.
      사람도 "늘어진다"는 말을 들으면 먼저 본다. 보지도 않고 되묻지 않는다.
      (실측: LOOK 을 따로 두었더니 젬마가 그것을 안 고르고 계속 되물었다 —
       이 트랙이 처음 잡으려던 바로 그 병이 다른 옷을 입고 돌아왔다.)
    날숨은 셋뿐이다 — TALK / PROPOSE / ASK.

    젬마가 못 고르거나 세계가 없으면 None(기존 사다리로 흘려보낸다)."""
    if not ENABLED:
        return None
    if not program_id or not (user_text or "").strip():
        return None
    w = world(program_id, fragment_labels)
    if not w:
        return None

    world_text = _world_lines(w)

    # 첫 숨 — 세계만 보인다. 살펴본 결과는 아직 꺼내지 않는다.
    #   (실측: 처음부터 후보를 보이면 젬마가 인사·감사에도 제안을 얹는다 —
    #    눈앞의 것이 앵커가 된다. 필요할 때만 그 공간을 연다.)
    first = _ask_gemma(user_text, recent_messages, world_text)
    if not first:
        return None

    trail = [first["breath"]]
    say = first["say"]
    result_kind = "talk"
    payload = None
    chosen = None

    if first["breath"] in ("LOOK", "TRY", "PROPOSE"):
        looked, pairs = look_block(program_id, w, first.get("target") or user_text)
        calc = None
        if pairs:
            calc, chosen = try_block(program_id, w, pairs, first.get("target"))
        seen = looked if not calc else f"{looked}\n\n{calc}"
        # 둘째 숨 — 살펴본 것을 들고 판단한다.
        second = _ask_gemma(user_text, recent_messages, world_text,
                            extra_block=seen, breath_no=2)
        if second:
            trail.append(second["breath"])
            say = second["say"] or say
            first = second
        # 이미 살펴보고 계산까지 끝났다 — 또 LOOK 을 고르면 제안 자리로 올린다.
        if first["breath"] in ("LOOK", "TRY") and chosen:
            first = {**first, "breath": "PROPOSE"}
            trail.append("PROPOSE*")
        # ★말과 숨이 어긋나면 말을 믿는다. TALK 을 골라 놓고 실제로 제안을 한 경우
        #   (그 조각 이름과 양을 그대로 말한 경우) 카드를 붙인다 — "해볼까요?"를
        #   듣고도 누를 것이 없던 자리(실측).
        if first["breath"] == "TALK" and chosen:
            label = chosen["label"]
            amount = f"{chosen['cand']['delta_ms'] / 1000:.1f}초"
            if label and label in (say or "") and amount in (say or ""):
                first = {**first, "breath": "PROPOSE"}
                trail.append("PROPOSE†")

    if chosen:
        if True:
            if True:
                if first["breath"] == "PROPOSE":
                    c = chosen["cand"]
                    disp = _ep._display_texts(c, fragment_labels)
                    disp["label"] = chosen["label"]
                    disp["story_before_text"] = w["total_text"]
                    disp["story_after_text"] = _fmt_sec(chosen["after_total_ms"])
                    # 말이 사실과 어긋나면 사실로 되돌린다. 두 경우:
                    #   ① 하지 않은 일을 했다고 말함(_DONE_RE)
                    #   ② 제안 카드가 나가는데 말에는 그 조각도 그 양도 없음 —
                    #      사용자는 "어떤 부분을 원하세요?"를 듣고 카드를 보게 된다(실측).
                    label = chosen["label"]
                    amount = f"{c['delta_ms'] / 1000:.1f}초"
                    off_topic = not (label in (say or "") and amount in (say or ""))
                    if _DONE_RE.search(say or "") or off_topic:
                        why = "완료로 말함" if _DONE_RE.search(say or "") else "사실 없음"
                        print(f"[BREATH][SAY-GUARD] {why} → 서버 문장: {say[:45]!r}")
                        say = (f"{label} "
                               f"{'앞' if c['side'] == 'start' else '뒤'}쪽 말 없는 구간을 "
                               f"{amount} 다듬으면 전체가 "
                               f"{w['total_text']} → {_fmt_sec(chosen['after_total_ms'])}"
                               f"가 돼요. 해볼까요?")
                    result_kind = "propose"
                    payload = {
                        "proposal_kind": "TRIM",
                        "program_id": program_id,
                        "timeline_item_id": None,   # 아래서 채운다
                        "fragment_id": c["fragment_id"],
                        "source_id": c["source_id"],
                        "anchor_start_ms": c["anchor_start_ms"],
                        "anchor_end_ms": c["anchor_end_ms"],
                        "current": c["current"],
                        "proposed": c["proposed"],
                        "evidence": {"side": c["side"], "gap_ms": c["gap_ms"],
                                     "delta_ms": c["delta_ms"],
                                     "basis": "subtitles.segments word timing"},
                        "display": disp,
                        "story": {"before_ms": w["total_ms"],
                                  "after_ms": chosen["after_total_ms"]},
                    }
                    import ledger_r0
                    payload["timeline_item_id"] = (
                        f"ITEM_{ledger_r0._hash6(program_id)}_{c['fragment_id']}_0")
    elif first["breath"] in ("TRY", "PROPOSE"):
        # 계산할 것이 없으면 정직하게. 억지 제안을 만들지 않는다.
        say = say or "지금 자료에서는 손볼 만한 자리를 찾지 못했어요."
        result_kind = "talk"

    if not say:
        return None   # 할 말이 없으면 기존 경로에 맡긴다

    print(f"[BREATH] {'→'.join(trail)} | {user_text[:30]!r} → {result_kind}")

    if result_kind == "propose" and payload:
        return {
            "status": "OK", "action": "propose_edit",
            "normalized_instruction": None, "reply": say, "confidence": 0.9,
            "matched": {"kind": "gemma_breath", "gate": "breath",
                        "trail": trail},
            "via": "breath", "proposal": payload,
        }
    return {
        "status": "OK", "action": "answer_only",
        "normalized_instruction": None, "reply": say, "confidence": 0.88,
        "matched": {"kind": "gemma_breath", "gate": "breath", "trail": trail},
        "via": "breath",
    }
