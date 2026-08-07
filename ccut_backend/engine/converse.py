# -*- coding: utf-8 -*-
"""[CONVERSE / QWEN-R2 STAGE C] 살아있는 큐원 — 한 왕복 계약.

루프: 사용자 발화 → 이력+상태 주입 → 큐원 판단 {action, params, say}
      → 규칙 검증·집행 → 결과 재주입 → 큐원 say(스트림) → 저장.

이중핵 경계(고정):
  큐원 = 뜻 읽기·도구 선택·인자 제안·발화. 직접 상태수정 금지.
  규칙 = 인자 검증(화이트리스트·범위)·상태변경·DB기록·결과반환.
      자연어 이해를 어휘 게이트로 하드코딩하지 않는다 (F-4 오타 사건의 구조 원인).

출력 계약(③): 큐원은 첫 줄에 JSON 한 줄 {"action","params"}, 둘째 줄부터 say.
  say만 스트림(F2 재사용). format:json은 추출·판사 경로에만 유지 — 이 모듈의
  판단 호출은 format 미지정 스트림이다.

저장(①·F5): 이력의 단일 진실 = project_timeline (append-only).
  message/generation은 프론트 diff-sync가 쓰고, active_intent·chat_pref·
  chat_summary는 이 모듈(규칙 층)이 쓴다. 스키마 변경 없음.
"""
import json
import datetime
import os
import re
import sqlite3
from zoneinfo import ZoneInfo

from engine import hub
from engine import revision as _rev
from engine import timeline_store

_ACTIONS = ("run_proposal", "revise", "retrigger", "clear_intent", "answer", "clarify")


def _now_kst():
    return datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def _rubric_enabled():
    # [RUBRIC-1] 기본 OFF — 켜지기 전까진 build_decide_prompt/validate_decision의
    # rubric 관련 코드가 실행되지 않는다(기존 프롬프트·params 100% 무변).
    return os.getenv("CCUT_RUBRIC_ENABLED") in ("1", "true", "True")


# [RUBRIC-1] gate ON일 때만 프롬프트에 덧붙는 블록. 오작동 방지 few-shot 2건 포함
# ("먹방 빼줘"류 단일exclude에서 keep을 헛지어내지 않게, "실내만" 단일keep에서
# exclude를 헛지어내지 않게). run_proposal params에 "rubric" 키를 덧붙이는
# 구조화 출력 요청일 뿐 — action 판단 자체는 안 건드림.
_RUBRIC_PROMPT_BLOCK = (
    "\n[RUBRIC — run_proposal일 때만] params에 rubric도 함께 채워라. 압축하지 말고 "
    "남길 조건과 뺄 조건을 각각 리스트로 대등하게 적어라(하나만 있으면 다른 쪽은 빈 리스트):\n"
    'rubric: {"keep":[{"term":"명사","required":true}],'
    '"exclude":[{"term":"명사","required":true}],"count":정수|null,"style":[]}\n'
    "count는 사용자가 개수/분량을 직접 말한 경우만 넣고, 현재 화면 조각 수나 기본값을 복사하지 마라.\n"
    "예시:\n"
    "사용자: 먹방 빼줘\n"
    '{"action":"run_proposal","params":{"instruction":"먹방 빼고 나머지",'
    '"rubric":{"keep":[],"exclude":[{"term":"먹방","required":true}],"count":null,"style":[]}}}\n'
    "사용자: 사람 없는 풍경만\n"
    '{"action":"run_proposal","params":{"instruction":"사람 없는 풍경만",'
    '"rubric":{"keep":[{"term":"풍경","required":true}],'
    '"exclude":[{"term":"사람","required":true}],"count":null,"style":[]}}}\n'
)
# [⑥] 대화 샘플링 프로파일 (국장 지시서 고정값). 추출·판사는 temp0 결정론 유지.
_CHAT_TOP_P = 0.8
_CHAT_TOP_K = 20
_CHAT_TEMP = 0.7
# [②] 요약 롤링 문턱 — 마지막 요약 이후 message가 이 수를 넘으면 옛 구간을 요약한다.
_SUMMARY_EVERY = 40
_RECENT_TURNS = 12

_BAD_RE = re.compile(r"[一-鿿]")
_IDENT_RE = re.compile(r"qwen|큐원|퀜|通义|阿里|알리바바", re.IGNORECASE)
_NUM_KO = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6,
           "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}


def _mentioned_count(t):
    m = re.search(r"(\d+)\s*(?:개|컷|조각|장면)", t or "")
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 40 else None
    for k, v in _NUM_KO.items():
        if re.search(k + r"\s*(?:개|컷|조각|장면)", t or ""):
            return v
    return None


def _rubric_direct_vocab():
    terms = set(getattr(hub, "_THEME_VOCAB", ()))
    terms.update(getattr(hub, "_RUBRIC_TEXT_ALIASES", {}).keys())
    terms.update(getattr(hub, "_RUBRIC_ABSTRACT_KEEP_ALIASES", {}).keys())
    terms.add("물")
    return sorted((t for t in terms if t), key=len, reverse=True)


def rubric_direct_decision(user_text):
    """Gate ON에서만 짧은 조각 조건을 Qwen 자유판단 전에 구조화한다.

    예: "딸기", "박수", "사람 없는 풍경만"은 편집 조건이지 잡담이 아니다.
    같은 hub compound parser와 EditRubric 스키마를 쓰므로 실행층 진실은 하나다.
    """
    if not _rubric_enabled():
        return None
    text = str(user_text or "").strip()
    if not text or len(text) > 60 or "?" in text or "？" in text:
        return None
    intent = hub.parse_compound_intent(text, vocab=_rubric_direct_vocab())
    keep_terms = intent.get("keep_terms") or []
    exclude_terms = intent.get("exclude_terms") or []
    if not keep_terms and not exclude_terms:
        return None

    count = _mentioned_count(text) or intent.get("count")
    intent = dict(intent)
    intent["count"] = count
    from engine import edit_rubric as _edit_rubric
    rubric = _edit_rubric.EditRubric.from_intent(intent, raw_goal=text).to_dict()
    params = {"instruction": text, "rubric": rubric}
    if isinstance(count, int):
        params["count"] = count
    return {
        "action": "run_proposal",
        "params": params,
        "say": "네, 그 조건으로 골라볼게요.",
        "matched": {
            "kind": "rubric_direct",
            "keep_terms": keep_terms,
            "exclude_terms": exclude_terms,
        },
    }


def persist_decision(program_id, action, params):
    if not program_id:
        return
    try:
        import time as _t
        ts = _t.time() * 1000
        entries = []
        if action == "run_proposal" and params.get("instruction"):
            entries.append({"kind": "active_intent", "client_id": f"ai_int_{int(ts)}",
                            "ts": ts, "payload": {"instruction": params["instruction"]}})
        if action == "clear_intent":
            entries.append({"kind": "active_intent", "client_id": f"ai_int_{int(ts)}",
                            "ts": ts, "payload": {"instruction": ""}})
        if action == "run_proposal" and (params.get("count") or params.get("target_length")):
            entries.append({"kind": "chat_pref", "client_id": f"ai_pref_{int(ts)}",
                            "ts": ts, "payload": {"count": params.get("count"),
                                                  "target_length": params.get("target_length")}})
        if entries:
            timeline_store.append_entries(program_id, entries)
    except Exception as e:
        print(f"[CONVERSE][WARN] 기록 실패 ({e})")


# ---------------------------------------------------------------- ①② 주입 재료

# [STAGE-VOICE 분리 2026-08-02] 화면 안내는 대화가 아니다 — 큐원 기억에서 뺀다.
#   STAGE-VOICE(Index.tsx:3249~3272)는 "지금은 분석 중입니다" 같은 단계 안내를 화면에
#   한 줄 띄우고, 그것이 storyPlan.messages 를 타고 원장에 message 로 append 된다.
#   실측(2026-08-02, Freesia): load_history(n=12) 가 큐원에게 넘기는 최근 12턴 중
#   4턴이 이 안내였고, 프로젝트를 한 번 열 때마다 2턴씩 더 밀려 들어왔다.
#   국장이 한 말이 뒤로 밀리고 시스템이 자기에게 한 말이 앞을 차지한다.
#   ★고치는 곳은 화면도 저장도 아니라 '읽는 쪽'이다.
#     - 화면 렌더 경로 무접촉 — 안내는 그대로 뜬다.
#     - 기존 511행 무접촉 — append-only 원장은 지우지 않는다.
#     - 범용 message 조회가 잘못 먹던 것을 조회에서 뺀다.
#   ★문구로 판정하지 않는다. 문구는 바뀌고 번역되고 사용자가 따라 칠 수도 있다.
#     client_id 접두로 판정한다 — client_id 는 payload["id"] 와 같은 값이고
#     (Index.tsx:1773 `const cid = String(m?.id ?? ...)`), 생성부가 그 접두를 박는다
#     (Index.tsx:3258 `id: \`ai_stage_${storyStage.key}_${Date.now()}\``).
_STAGE_NOTICE_PREFIX = "ai_stage_"


def _is_stage_notice(client_id):
    """화면 단계 안내인가 — 구조적 표지(client_id 접두)로만 판정한다."""
    return str(client_id or "").startswith(_STAGE_NOTICE_PREFIX)


def load_history(program_id, n=_RECENT_TURNS):
    """최근 n개 message + 최신 chat_summary. project_timeline이 단일 진실.
    ★단계 안내(ai_stage_*)는 화면용이므로 여기서 제외한다 — 대화가 아니다."""
    con = sqlite3.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                          uri=True, timeout=10)
    try:
        rows = list(con.execute(
            "SELECT kind, payload, client_id FROM project_timeline WHERE program_id=? "
            "AND kind IN ('message','chat_summary') ORDER BY entry_id DESC LIMIT 300",
            (program_id,)))
    except sqlite3.OperationalError:
        rows = []
    finally:
        con.close()
    summary = None
    summary_covers = 0
    msgs = []
    total_msgs = 0
    for kind, payload, client_id in rows:  # 최신 → 과거
        try:
            p = json.loads(payload) if payload else {}
        except Exception:
            continue
        if kind == "chat_summary" and summary is None:
            summary = str(p.get("summary") or "")[:600]
            # [MEMORY-SPINE 2026-08-02] 마지막 요약이 어디까지 덮었는지 — 다음 요약 시점 판정용.
            try:
                summary_covers = int(p.get("covers") or 0)
            except Exception:
                summary_covers = 0
        elif kind == "message":
            if _is_stage_notice(client_id):
                continue        # 화면 안내 — 대화 기억에도 요약 문턱에도 넣지 않는다
            total_msgs += 1
            if len(msgs) < n:
                txt = str(p.get("text") or "").strip()
                if txt:
                    msgs.append({"sender": p.get("sender") or "?", "text": txt[:200]})
    msgs.reverse()
    return {"summary": summary, "summary_covers": summary_covers,
            "messages": msgs, "total_messages": total_msgs}


# [MEMORY-SPINE 2026-08-02] 살아있는 채팅 경로(/intent/route-edit*)를 위한 기억 어댑터.
#   왜 필요했나: 요약(load_history)과 적용 중 기준(state_snapshot)은 이미 있었지만
#   둘 다 decide_stream 안에서만 쓰였고, 그 함수를 부르는 /chat/converse/stream 을
#   프론트가 한 번도 호출하지 않는다(videoService.ts 는 /intent/route-edit* 만 부른다).
#   ★새 기억 시스템을 만들지 않는다. 이미 있는 세 kind 를 한 쿼리로 읽어
#     라이브 경로의 facts 블록에 실어주는 어댑터 하나가 전부다.
#   ★state_snapshot 을 그대로 쓰지 않는 이유: 그 함수는 조각 수·소스별 집계까지 도는데
#     이 경로는 TTFT 를 계측 중이라([F2-TTFT]) 필요 없는 쿼리를 얹지 않는다.
def load_memory_facts(program_id):
    """지난 요약 · 적용 중 기준 · 분량 선호를 프롬프트 한 덩이로. 쿼리 1개."""
    if not program_id:
        return ""
    summary = intent = None
    pref = {}
    try:
        con = sqlite3.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                              uri=True, timeout=10)
    except Exception:
        return ""
    try:
        for kind, payload in con.execute(
                "SELECT kind, payload FROM project_timeline WHERE program_id=? "
                "AND kind IN ('chat_summary','active_intent','chat_pref') "
                "ORDER BY entry_id DESC LIMIT 30", (program_id,)):
            try:
                p = json.loads(payload) if payload else {}
            except Exception:
                continue
            if kind == "chat_summary" and summary is None:
                summary = str(p.get("summary") or "")[:600]
            elif kind == "active_intent" and intent is None:
                # 빈 문자열은 'clear_intent'가 남긴 해제 기록이다 — 기준 없음으로 확정한다.
                intent = str(p.get("instruction") or "")[:120]
            elif kind == "chat_pref" and not pref:
                pref = {"count": p.get("count"), "target_length": p.get("target_length")}
    except sqlite3.OperationalError:
        pass
    finally:
        con.close()
    out = ""
    if summary:
        out += f"[지난 요약] {summary}\n"
    if intent:
        out += f"[적용 중 기준] {intent}\n"
    if pref.get("count") or pref.get("target_length"):
        bits = []
        if pref.get("count"):
            bits.append(f"조각 {pref['count']}개")
        if pref.get("target_length"):
            bits.append(f"목표 {pref['target_length']}초")
        out += f"[분량 선호] {' · '.join(bits)}\n"
    return out


def _clean_fragment_labels(fragment_labels):
    # [관문C 2026-07-20 stash이식] 프론트 라벨맵 위생검사 —
    #   대문자 1~2자+숫자(G1) 형태만, 값 있는 것만. Qwen이 볼 계기판 재료.
    clean = {}
    for label, fid in (fragment_labels or {}).items():
        lab = str(label or "").upper().strip()
        val = str(fid or "").strip()
        if re.fullmatch(r"[A-Z]{1,2}\d{1,3}", lab) and val:
            clean[lab] = val
    return clean


def _mirror_summary_fact(project_id):
    project_id = str(project_id or "").strip()
    if not project_id:
        return ""
    try:
        from mirror_ledger import format_summary_fact_line, summarize_project
        line = format_summary_fact_line(summarize_project(project_id))
    except Exception:
        return ""
    return line


def state_snapshot(program_id, current_view=None, fragment_labels=None):
    """상태 스냅샷 — 조각풀·직전 의도·분량 설정. 전부 read-only.
    [R2-2 D+E] '지금 안'의 조각 수·구성은 DB 직전 생성분이 아니라 프론트가 보낸
    current_view(현재 화면 조각맵의 라이브 SF 목록)를 진실로 삼는다 — 소환·편집으로
    화면이 DB 최신과 어긋난 상태에서도 큐원이 실제 화면을 본다. DB proposals는
    A/B 존재·소스 폴백 용도로만 남긴다."""
    snap = {"proposals": {}, "pool": 0, "source_count": 0,
            "now": _now_kst(), "active_intent": None,
            "target_length": None, "count_pref": None, "current": None,
            "fragment_labels": _clean_fragment_labels(fragment_labels),
            "mirror_summary": _mirror_summary_fact(program_id)}
    cv = current_view or {}
    if isinstance(cv, dict) and cv.get("count") is not None:
        snap["current"] = {
            "mode": cv.get("mode"),
            "count": int(cv.get("count") or 0),
            "duration": round(float(cv.get("duration") or 0), 1),
            "source": "live",
        }
    con = sqlite3.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                          uri=True, timeout=10)
    try:
        rows = list(con.execute(
            "SELECT mode, proposal_id, duration, "
            "(SELECT COUNT(*) FROM json_each(sequence)), created_at FROM proposals "
            "WHERE program_id=? ORDER BY created_at DESC", (program_id,)))
        for mode, pid, dur, n, _ca in rows:
            if mode in ("A", "B") and mode not in snap["proposals"]:
                snap["proposals"][mode] = {"proposal_id": pid,
                                           "count": n or 0,
                                           "duration": round(dur or 0, 1)}
        # [D+E] current_view 미제공 시(구 프론트/폴백)만 DB 최신을 '지금 안'으로 폴백
        if snap["current"] is None and snap["proposals"]:
            _m = "B" if "B" in snap["proposals"] else "A"
            _p = snap["proposals"][_m]
            snap["current"] = {"mode": _m, "count": _p["count"],
                               "duration": _p["duration"], "source": "db"}
        snap["pool"] = con.execute(
            "SELECT COUNT(*) FROM semantic_fragments WHERE source_id IN "
            "(SELECT source_id FROM project_sources WHERE program_id=?)",
            (program_id,)).fetchone()[0]
        snap["source_count"] = con.execute(
            "SELECT COUNT(*) FROM project_sources WHERE program_id=?",
            (program_id,)).fetchone()[0]
        # [S-4] 소스별 조각 수 — "조각 몇개?" 메타질문에 숫자로 즉답할 재료
        snap["per_source"] = [
            (sid, n) for sid, n in con.execute(
                "SELECT source_id, COUNT(*) FROM semantic_fragments WHERE source_id IN "
                "(SELECT source_id FROM project_sources WHERE program_id=?) "
                "GROUP BY source_id ORDER BY source_id", (program_id,))]
        for kind, payload in con.execute(
                "SELECT kind, payload FROM project_timeline WHERE program_id=? "
                "AND kind IN ('active_intent','chat_pref') ORDER BY entry_id DESC LIMIT 20",
                (program_id,)):
            try:
                p = json.loads(payload) if payload else {}
            except Exception:
                continue
            if kind == "active_intent" and snap["active_intent"] is None:
                snap["active_intent"] = str(p.get("instruction") or "")[:120] or None
            elif kind == "chat_pref":
                if snap["target_length"] is None and p.get("target_length"):
                    snap["target_length"] = p.get("target_length")
                if snap["count_pref"] is None and p.get("count"):
                    snap["count_pref"] = p.get("count")
    except sqlite3.OperationalError as e:
        print(f"[CONVERSE][WARN] snapshot 실패 ({e}) — 빈 스냅샷으로 진행")
    finally:
        con.close()
    return snap


def _snap_block(snap):
    per = snap.get("per_source") or []
    # [S-4] 원본 수와 조각 수를 분리 명시 — "영상 4개"를 조각 수로 오답하던 사건 차단
    source_count = snap.get("source_count", len(per))
    pool_line = (f"원본 영상 {source_count}개 · 조각(장면) 총 {snap['pool']}개"
                 + (f" (소스별 {', '.join(str(n) for _s, n in per)}개)" if per else ""))
    # [D+E] '지금 안'은 라이브 current(화면 조각맵)를 진실로. 없으면 제안 없음.
    cur = snap.get("current")
    if cur:
        m = cur.get("mode") or "현재"
        now_line = f"지금 화면 안({m}안) {cur['count']}조각 {cur['duration']}초"
    else:
        now_line = "제안 아직 없음(전체 조각에서 고를 차례)"
    gauge_line = (
        f"계기판: source_count={source_count}(원본 영상 수), "
        f"semantic_fragment_count={snap['pool']}(분석 조각/장면 수), "
        f"edited_visible_count={(cur or {}).get('count') if cur else '없음'}(현재 화면 편집·표시 조각 수), "
        f"now={snap.get('now')}(KST 로컬 시계)"
    )
    labels = snap.get("fragment_labels") or {}
    if labels:
        _lab_keys = ", ".join(sorted(labels.keys()))
        gauge_line = gauge_line + f", fragment_labels=[{_lab_keys}](조각맵 타일 라벨—이 목록의 라벨만 유효)"
    lines = [pool_line, now_line, gauge_line]
    if snap.get("mirror_summary"):
        lines.append(snap["mirror_summary"])
    if snap.get("active_intent"):
        lines.append(f"적용 중 기준: {snap['active_intent']}")
    if snap.get("target_length"):
        lines.append(f"목표 길이 설정: {snap['target_length']}초")
    if snap.get("count_pref"):
        lines.append(f"조각 수 설정: {snap['count_pref']}개")
    return " / ".join(lines)


# ---------------------------------------------------------------- ③④⑦ 판단 프롬프트

def build_decide_prompt(user_text, hist, snap):
    ctx = ""
    for m in hist["messages"]:
        who = "사용자" if m["sender"] == "user" else "CCUT"
        ctx += f"{who}: {m['text']}\n"
    return (
        "너는 CCUT — 로컬 영상 편집실의 총괄 편집자다. 사용자의 말을 읽고 "
        "(1) 무엇을 할지 도구 하나를 고르고 (2) 사용자에게 할 말을 만든다.\n"
        "[도구]\n"
        "- run_proposal: 새 기준으로 조각을 골라 편집안 생성. params: "
        '{"instruction":"무엇을 고를지 기준(빈 문자열이면 직전 기준 유지)",'
        '"count":조각수(정수,선택),"target_length":초(정수,선택),'
        '"count_scope":"both|A|B(분량을 A·B 둘 다=both(기본), 한쪽만이면 A 또는 B)",'
        '"candidate_labels":["G1","G3"](선택 — 계기판 fragment_labels에 있는 라벨만. '
        '"G1만"/"G2랑 G4만"처럼 라벨을 콕 집으면 그 라벨만 남긴다)}\n'
        "- revise: 지금 안에서 국소 수정만. params: "
        '{"op":"remove_ordinal|set_count|remove_theme","index":0부터(첫번째=0,마지막=-1),'
        '"count":정수,"theme":"명사","target_mode":"A|B"}\n'
        '- retrigger: 직전 기준 그대로 재실행. params: {}\n'
        '- clear_intent: 기준을 없애고 전체에서 다시. params: {}\n'
        '- answer: 편집 실행 없이 대답만(상태 질문·잡담·설명). params: {}\n'
        '- clarify: 뜻을 정말 알 수 없을 때만 되묻기. params: {}\n'
        "[규칙 — 어기면 실격]\n"
        "1. 출력 첫 줄: JSON 딱 한 줄 {\"action\":\"...\",\"params\":{...}} — 다른 글자 금지.\n"
        "2. 둘째 줄부터 사용자에게 할 말. 반드시 한국어 존댓말. 짧은 말에는 1문장, "
        "복잡한 요청에도 2~3문장까지 (설교·장황 금지). 인사·감사·짧은 반응에는 "
        "한 문장으로만 답하고 편집 이야기를 먼저 꺼내지 마라.\n"
        "3. 사용자의 문장을 그대로 되풀이하지 마라 — 네가 이해한 바를 네 말로.\n"
        "4. 상태 질문(왜/몇 개/뭐가)에는 [상태]의 계기판 숫자로만 답하라 (action=answer). "
        "'오늘/날짜/시간/몇 일'은 now=KST 로컬 시계만 읽어 답하라. "
        "'영상 몇 개/원본 몇 개'는 source_count=원본 영상 수만 답하고 조각 수를 섞지 마라. "
        "'조각 몇 개/장면 몇 개/분석 조각'은 semantic_fragment_count와 edited_visible_count를 구분해 답하라. "
        "'지금 안/현재 화면/편집된 조각'은 edited_visible_count만 답하라.\n"
        # [QWEN-01 2-3 2026-08-02] "절대 되묻지 마라" 삭제.
        #   근거: Qwen 공식 문서가 "사용자에게 묻는 대신 인자를 지어낸다"고 경고한다.
        #   지어내는 성향인데 되묻기까지 막으면 지어내기 외에 길이 없다.
        #   실측(같은 날 STEP 1-3): 조회가 실패했는데 되묻지도 재시도하지도 않고
        #   조각 id·전사를 통째로 날조했다. 되묻기를 여는 대신 예산을 둔다 — 한 번에 하나.
        #   ★ 위임은 여전히 위임이다. 위임에는 네가 정한다 — 그 규율은 남긴다.
        "5. 위임(니가 알아서/적당히/맡길게)이면 [상태]를 보고 네가 기준·개수를 정해 "
        "run_proposal 하고, 말로는 네 계획을 밝혀라. 위임에는 되묻지 말고 네가 정하라.\n"
        "5-1. 위임이 아닌데 뜻을 정말 알 수 없으면 지어내지 말고 clarify 로 되물어라. "
        "단 한 번에 한 가지만 묻는다. 이미 한 번 되물었으면 그다음은 네가 정해서 진행하라.\n"
        "6. 분량 요구(여러 개로/길게/짧게/N분/N개)는 count·target_length 숫자로 옮겨 담아라.\n"
        "7. 오타가 있어도 뜻으로 읽어라.\n"
        # [QWEN-01 2-2 2026-08-02] "모델명·제조사 언급 금지" 프롬프트에서 삭제 → 서버 후처리로.
        #   이 검출은 이미 서버에 있다(converse.py:72 _IDENT_RE, :522 위생 판정,
        #   intent_router.py:372 정체 노출 차단, :479 스트림 중단). 프롬프트와 이중이었다.
        #   ★ 중국어 금지는 남긴다 — 서버는 검출만 하고 재생성이 필요한 보완관계이고,
        #     같은 날 실측에서 실제 누출을 봤다("오늘은 좋은 날씨에 기분이很不错…").
        "8. 중국어·영어 문장 금지. [상태] 밖 수치를 지어내지 마라.\n"
        "9. 행동은 아직 실행 전이다 — '바뀌었습니다/완료했습니다'처럼 결과가 이미 나온 듯 "
        "말하지 마라. 결과 보고는 집행이 끝난 뒤 따로 온다.\n"
        "10. 감정·잡담·인사·안부에는 [상태]의 조각 수·길이 숫자를 나열하지 마라 — "
        "먼저 사람으로서 공감하고, 편집 얘기는 사용자가 원할 때만. 조각 수 질문일 때만 숫자를 답한다.\n"
        "[예시 — 숫자는 예시일 뿐, 답은 항상 [상태]의 실제 값으로]\n"
        "사용자: G1만\n"
        '{"action":"run_proposal","params":{"instruction":"","candidate_labels":["G1"],"count":1}}\n'
        "G1 조각만 남겨서 다시 구성해볼게요.\n"
        "사용자: G2랑 G4만\n"
        '{"action":"run_proposal","params":{"instruction":"","candidate_labels":["G2","G4"]}}\n'
        "G2, G4만 골라서 구성해볼게요.\n"
        "사용자: 지금 조각이 몇개야?\n"
        '{"action":"answer","params":{}}\n'
        "전체 조각은 26개예요(원본 영상 7개를 장면 단위로 나눈 수). 지금 안에는 그중 "
        "3개를 골라 두었습니다.\n"
        "사용자: 영상 몇 개야?\n"
        '{"action":"answer","params":{}}\n'
        "원본 영상은 7개입니다.\n"
        "사용자: 조각 몇 개야?\n"
        '{"action":"answer","params":{}}\n'
        "분석 조각은 26개이고, 지금 화면 안에는 3조각이 있습니다.\n"
        "사용자: 조각은 왜 3개만이야?\n"
        '{"action":"answer","params":{}}\n'
        "지금 기준에 확실히 맞는 조각만 남겨서 3개가 됐어요. 기준을 넓히거나 개수를 "
        "정해 주시면 다시 골라볼게요.\n"
        "사용자: 전체 보고 니가 스토리 잡아줘. 적당하게\n"
        '{"action":"run_proposal","params":{"instruction":"인물 중심으로 흐름이 이어지는 장면","count":8}}\n'
        "전체 조각을 보고 인물 중심으로 8개쯤 이어지는 흐름을 잡아볼게요. 방향이 "
        "다르면 한마디만 주세요.\n"
        "사용자: 여러 개로 길게 해줘\n"
        '{"action":"run_proposal","params":{"instruction":"","count":10,"target_length":120}}\n'
        "지금 기준은 그대로 두고 조각을 10개, 길이는 2분 정도로 늘려볼게요.\n"
        "사용자: B안만 8개로 해줘, A는 그대로\n"
        '{"action":"run_proposal","params":{"instruction":"","count":8,"count_scope":"B"}}\n'
        "B안만 8개로 맞추고 A안은 그대로 둘게요.\n"
        "사용자: 두번쨰 조각 뺴줘\n"
        '{"action":"revise","params":{"op":"remove_ordinal","index":1}}\n'
        "두 번째 조각을 빼겠습니다.\n"
        "사용자: 오늘 날씨 어때?\n"
        '{"action":"answer","params":{}}\n'
        "실시간 날씨는 제가 알 수가 없어요. 그래도 오늘 촬영은 잘 되셨나요?\n"
        "사용자: 요즘 좀 안 편하네\n"
        '{"action":"answer","params":{}}\n'
        "그러셨군요, 무리하지 마세요. 편집은 천천히 하셔도 돼요 — 쉬고 싶으실 땐 그냥 말씀만 주세요.\n"
        # [D+E] 이력을 먼저, [상태]를 질문 바로 앞에 — 최근 대화의 옛 숫자보다 [상태]가
        # 이긴다(recency). 조각 수·구성 질문은 반드시 [상태] '지금 화면 안'으로만 답한다.
        + (f"[지난 요약] {hist['summary']}\n" if hist.get("summary") else "")
        + (f"[최근 대화]\n{ctx}" if ctx else "")
        + f"[상태 — 지금 이 순간의 진실. 최근 대화에 다른 숫자가 있어도 이 값으로만 답하라]\n{_snap_block(snap)}\n"
        + (_RUBRIC_PROMPT_BLOCK if _rubric_enabled() else "")
        + f"사용자: {user_text}\n")


# ---------------------------------------------------------------- 규칙: 검증

def validate_decision(d, snap):
    """큐원 제안 {action, params}를 규칙이 전수 검증 — 통과 못 하면 clarify 강등."""
    action = str((d or {}).get("action") or "").strip()
    params = (d or {}).get("params") or {}
    if not isinstance(params, dict):
        params = {}
    if action not in _ACTIONS:
        return "clarify", {}, f"unknown action {action!r}"
    out = {}
    if action == "run_proposal":
        instr = str(params.get("instruction") or "").strip()
        if len(instr) > 120 or "?" in instr:
            return "clarify", {}, "instruction 오염(질문꼴/과장)"
        out["instruction"] = instr  # 빈 문자열 = 직전 기준 승계
        # [관문C 2026-07-20 stash이식] 라벨 교정("G1만") 실행 —
        #   Qwen candidate_labels를 계기판 fragment_labels로 검증해 조각ID로 변환.
        #   목록에 없는 라벨(G99)이 하나라도 있으면 clarify (조용한 오답·날조 금지).
        label_map = snap.get("fragment_labels") or {}
        labels = params.get("candidate_labels")
        if isinstance(labels, list) and labels:
            picked, unknown = [], []
            for label in labels[:40]:
                lab = str(label or "").upper().strip()
                fid = label_map.get(lab)
                if fid:
                    picked.append(fid)
                else:
                    unknown.append(lab)
            if unknown or not picked:
                return "clarify", {}, f"unknown candidate labels {unknown!r}"
            out["candidate_fragment_ids"] = list(dict.fromkeys(picked))
        c = params.get("count")
        if isinstance(c, (int, float)) and 1 <= int(c) <= 40:
            out["count"] = int(c)
        t = params.get("target_length")
        if isinstance(t, (int, float)) and 10 <= float(t) <= 600:
            out["target_length"] = int(t)
        # [R2-3 다] 분량 적용 범위 — 기본 both(A·B 대칭). 사용자가 한쪽만 지정 시 A|B.
        sc = str(params.get("count_scope") or "both").lower()
        if sc in ("a", "b"):
            out["count_scope"] = sc.upper()
        # [RUBRIC-1] gate ON일 때만 — 큐원이 함께 낸 rubric을 캡처해 params에 얹는다.
        # 이 값은 프론트 user_intent를 거쳐 hub.plan_edit(rubric=...)까지 전달된다.
        # 실행층은 명시 rubric이 있으면 그것을 진실 원천으로 삼고 instruction 재파싱
        # rubric은 만들지 않는다.
        if _rubric_enabled() and isinstance(params.get("rubric"), dict):
            from engine import edit_rubric as _edit_rubric
            _rubric = _edit_rubric.EditRubric.from_qwen_json(
                params["rubric"], raw_goal=instr
            )
            _mentioned = _mentioned_count(instr)
            if _rubric.count is not None:
                _rubric.count = _mentioned
            out["rubric"] = _rubric.to_dict()
    elif action == "revise":
        rev = _rev.validate_revision({**params, "via": "qwen"})
        if not rev:
            return "clarify", {}, f"revise 인자 기각 {params!r}"
        out = rev
    return action, out, None


# ---------------------------------------------------------------- ③ 판단+발화 스트림

def _candidate_evidence(fragment_ids):
    """[관문D 2026-07-20] 결정된 candidate 조각의 판단 근거(scene·speech·context)를
    결정론적으로 조회해 응답에 노출. 모델 무관 — hub._sensor_evidence(DB 번들)만 사용.
    번들 없으면 그 조각은 근거 없음(빈 리스트) — 지어내기 0."""
    out = {}
    fids = [str(f) for f in (fragment_ids or []) if f]
    if not fids:
        return out
    try:
        con = sqlite3.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                              uri=True)
    except Exception as e:
        print(f"[CONVERSE][WARN] candidate_evidence DB 열기 실패 ({e})")
        return {fid: [] for fid in fids}
    try:
        qs = ",".join("?" * len(fids))
        by_src = {}
        for fid, sid in con.execute(
                f"SELECT fragment_id, source_id FROM semantic_fragments "
                f"WHERE fragment_id IN ({qs})", fids):
            by_src.setdefault(sid, []).append(fid)
        ctx = hub._load_context_for_sources(con, list(by_src.keys())) if by_src else {}
        for sid, sfids in by_src.items():
            bundles = hub.load_bundles(con, sid)
            hub._apply_context_to_bundles(bundles, ctx)
            bmap = {b.get("fid"): b for b in bundles}
            for fid in sfids:
                b = bmap.get(fid)
                out[fid] = hub._sensor_evidence(b) if b else []
    except Exception as e:
        print(f"[CONVERSE][WARN] candidate_evidence 실패 ({e})")
    finally:
        con.close()
    for fid in fids:
        out.setdefault(fid, [])
    return out


def decide_stream(program_id, user_text, write=True, current_view=None, fragment_labels=None):
    """생성기: ('meta', {...}) → ('token', str)* → ('done', {...}).
    첫 줄 JSON 헤더는 규칙이 파싱·검증, 둘째 줄부터 say를 그대로 흘린다.
    위생 위반(중문·정체 노출) 감지 시 중단 → 고정 문구 강등.
    current_view: 프론트가 보낸 현재 화면 조각맵 라이브 요약(D+E)."""
    hist = load_history(program_id)
    snap = state_snapshot(program_id, current_view=current_view,
                          fragment_labels=fragment_labels)
    prompt = build_decide_prompt(user_text, hist, snap)
    header = None
    action = params = None
    buf = ""
    say = ""
    aborted = False
    try:
        for chunk in hub._ollama_stream(prompt, timeout=60, temperature=_CHAT_TEMP,
                                        top_p=_CHAT_TOP_P, top_k=_CHAT_TOP_K,
                                        num_predict=400):
            if header is None:
                buf += chunk
                if "\n" in buf:
                    line, rest = buf.split("\n", 1)
                    m = re.search(r"\{.*\}", line)
                    try:
                        header = json.loads(m.group(0)) if m else {}
                    except Exception:
                        header = {}
                    action, params, why = validate_decision(header, snap)
                    if why:
                        print(f"[CONVERSE] 검증 강등: {why}")
                    yield ("meta", {"action": action, "params": params, "via": "qwen"})
                    if rest:
                        say += rest
                        yield ("token", rest)
                continue
            say += chunk
            if _BAD_RE.search(say) or _IDENT_RE.search(say):
                print("[CONVERSE] 위생 위반 -> 중단·고정문구 강등")
                aborted = True
                break
            yield ("token", chunk)
            # [F6 리듬 — 규칙 집행] 아주 짧은 입력(인사·감탄)에는 첫 문장에서 발화를
            # 끊는다. 길이 기반 규칙 — 자연어 이해 하드코딩 아님. 모델이 규칙 2를
            # 어기고 편집 설교로 이어가는 실측(D6) 보정.
            if (len(user_text.strip()) <= 8 and action == "answer"
                    and len(say) >= 6 and re.search(r"[.!?~]\s*$", say)):
                print("[CONVERSE] F6 리듬 절단 — 짧은 입력, 첫 문장에서 마침")
                break
    except Exception as e:
        print(f"[CONVERSE] decide 스트림 실패 ({e})")
    if header is None:
        # 헤더 없이 끝남(전부 say였거나 실패) — answer로 정직 강등
        m = re.search(r"\{.*\}", buf)
        try:
            header = json.loads(m.group(0)) if m else {}
        except Exception:
            header = {}
        if header:
            action, params, _why = validate_decision(header, snap)
            # [관문D 2026-07-20] 결정된 candidate 조각의 판단 근거를 응답에 얇게 노출.
            if params.get("candidate_fragment_ids"):
                params["candidate_evidence"] = _candidate_evidence(
                    params.get("candidate_fragment_ids"))
            say = ""
        else:
            action, params = "answer", {}
            say = buf.strip()
            if say and not (_BAD_RE.search(say) or _IDENT_RE.search(say)):
                yield ("token", say)
        yield ("meta", {"action": action, "params": params, "via": "qwen"})
    say = say.strip()
    if aborted or not say:
        say = _fallback_say(action)
    # ── 규칙 층의 기록 (F5) ──
    if write:
        try:
            import time as _t
            ts = _t.time() * 1000
            entries = []
            if action == "run_proposal" and params.get("instruction"):
                entries.append({"kind": "active_intent", "client_id": f"ai_int_{int(ts)}",
                                "ts": ts, "payload": {"instruction": params["instruction"]}})
            if action == "clear_intent":
                entries.append({"kind": "active_intent", "client_id": f"ai_int_{int(ts)}",
                                "ts": ts, "payload": {"instruction": ""}})
            if action == "run_proposal" and (params.get("count") or params.get("target_length")):
                entries.append({"kind": "chat_pref", "client_id": f"ai_pref_{int(ts)}",
                                "ts": ts, "payload": {"count": params.get("count"),
                                                      "target_length": params.get("target_length")}})
            if entries:
                timeline_store.append_entries(program_id, entries)
        except Exception as e:
            print(f"[CONVERSE][WARN] 기록 실패 ({e})")
        try:
            maybe_roll_summary(program_id, hist)
        except Exception as e:
            print(f"[CONVERSE][WARN] 요약 롤링 실패 ({e})")
    yield ("done", {"action": action, "params": params, "say": say})


def _fallback_say(action):
    return {"run_proposal": "네, 그 기준으로 골라볼게요.",
            "revise": "네, 지금 안에서 그 부분만 손보겠습니다.",
            "retrigger": "직전 기준으로 다시 골라볼게요.",
            "clear_intent": "기준 없이 전체에서 다시 고를게요.",
            "clarify": "어떤 기준으로 고칠지 조금만 더 말씀해 주세요.",
            }.get(action, "네, 듣고 있어요. 편하게 말씀해 주세요.")


def ack_say_stream(user_text, det_reply, kind):
    """[④ 발화권] det 사다리 확정 행동의 접수 발화를 모델이 짧게 생성 (결정은 이미 규칙).
    실패·위생 위반 시 det_reply(사실 기반 고지) 강등."""
    prompt = (
        "너는 CCUT — 영상 편집 동료다. 방금 사용자의 지시를 접수해 아래 행동을 시작한다.\n"
        f"행동 요약: {det_reply}\n"
        f"사용자 말: {user_text}\n"
        "존댓말 한국어 한 문장으로 자연스럽게 접수 답만 하라. 사용자의 문장을 그대로 "
        "되풀이하지 말고, 행동 요약의 사실만 담아라. 다른 말·JSON 금지.\n")
    acc = ""
    try:
        for chunk in hub._ollama_stream(prompt, timeout=20, temperature=_CHAT_TEMP,
                                        top_p=_CHAT_TOP_P, top_k=_CHAT_TOP_K,
                                        num_predict=80):
            acc += chunk
            if _BAD_RE.search(acc) or _IDENT_RE.search(acc):
                yield ("abort", None)
                return
            yield ("token", chunk)
    except Exception as e:
        print(f"[CONVERSE] ack 스트림 실패 ({e})")
        yield ("abort", None)
        return
    yield ("done", acc.strip())


def result_say_stream(program_id, facts):
    """[결과 재주입] 집행 결과 사실을 주입해 완료 보고 발화를 스트림.
    숫자는 주입값 그대로 — 규칙이 준 사실 밖 수치 생성 금지."""
    hist = load_history(program_id, n=6)
    ctx = ""
    for m in hist["messages"][-4:]:
        who = "사용자" if m["sender"] == "user" else "CCUT"
        ctx += f"{who}: {m['text']}\n"
    prompt = (
        "너는 CCUT — 영상 편집 동료다. 방금 편집 실행이 끝났고 아래가 결과 사실이다.\n"
        f"[결과] {facts}\n"
        "존댓말 한국어 1~2문장으로 결과를 보고하라. 숫자는 [결과]의 값 그대로만 쓰고, "
        "지어내지 마라. 다음에 할 수 있는 일을 반 문장으로 덧붙여도 좋다. JSON 금지.\n"
        + (f"[최근 대화]\n{ctx}" if ctx else ""))
    acc = ""
    try:
        for chunk in hub._ollama_stream(prompt, timeout=30, temperature=_CHAT_TEMP,
                                        top_p=_CHAT_TOP_P, top_k=_CHAT_TOP_K,
                                        num_predict=160):
            acc += chunk
            if _BAD_RE.search(acc) or _IDENT_RE.search(acc):
                yield ("abort", None)
                return
            yield ("token", chunk)
    except Exception as e:
        print(f"[CONVERSE] result 스트림 실패 ({e})")
        yield ("abort", None)
        return
    yield ("done", acc.strip())


# ---------------------------------------------------------------- ② 요약 롤링

def maybe_roll_summary(program_id, hist):
    """마지막 요약 이후 message가 문턱을 넘으면 옛 구간을 요약해 append (F5 실물).
    요약은 '추출' 계열 — format:json 유지 (③ 예외 규정)."""
    if hist["total_messages"] < _SUMMARY_EVERY:
        return
    # [MEMORY-SPINE 2026-08-02] 요약이 매 턴 돌던 것을 막는다.
    #   구판: `if summary and total < _SUMMARY_EVERY*2: return` — total 이 80 을 넘는
    #   순간부터 두 조건 다 통과해 ★대화 한 턴마다 ollama 요약이 돌았다.
    #   실측(Freesia): covers 73 -> 75 -> 77 로 세 턴 연속 새 요약이 쌓였고,
    #   매번 새로 요약되니 같은 사실이 실렸다 빠졌다 했다
    #   (#5927 '은빛해오라기' 포함 -> #5933 누락). 기억이 흔들리는 원인이다.
    #   ★문턱의 뜻은 "마지막 요약 이후 _SUMMARY_EVERY 만큼 더 쌓였을 때"다.
    #     covers(그 요약이 덮은 줄 수)를 기준선으로 그 뜻대로 판정한다.
    #     covers 가 없는 옛 요약(0)은 구판과 같게 _SUMMARY_EVERY*2 로 동작한다.
    _covers = int(hist.get("summary_covers") or 0)
    if hist.get("summary"):
        _floor = (_covers + _SUMMARY_EVERY) if _covers else (_SUMMARY_EVERY * 2)
        if hist["total_messages"] < _floor:
            return
    con = sqlite3.connect("file:" + hub.DB_PATH.replace("\\", "/") + "?mode=ro",
                          uri=True, timeout=10)
    try:
        rows = list(con.execute(
            "SELECT payload, client_id FROM project_timeline WHERE program_id=? "
            "AND kind='message' ORDER BY entry_id DESC LIMIT 120", (program_id,)))
    finally:
        con.close()
    lines = []
    for payload, client_id in reversed(rows):
        # [STAGE-VOICE 분리] 요약도 대화만 요약한다 — 안내를 요약하면
        #   "지금은 분석 중입니다"가 사용자의 기준으로 굳는다.
        if _is_stage_notice(client_id):
            continue
        try:
            p = json.loads(payload)
            t = str(p.get("text") or "").strip()
            if t:
                lines.append(f"{'U' if p.get('sender') == 'user' else 'C'}: {t[:100]}")
        except Exception:
            continue
    if not lines:
        return
    # [LIVING-DRAFT-1] 요약도 젬마로 — 채팅 턴 꼬리에서 큐원을 부르면 다음 턴이
    #   모델 스왑(~10초 실측)을 문다. 루프 안은 젬마 하나로 통일한다.
    out = hub._ollama_json(
        "다음 편집실 대화 기록을 5문장 이내 한국어로 요약하라. 사용자가 준 기준·결정·"
        "선호를 우선 보존한다.\n" + "\n".join(lines[-100:]) +
        '\nJSON만: {"summary":"..."}', timeout=45, model=hub.VOICE_MODEL)
    s = str(out.get("summary") or "").strip()
    if s:
        import time as _t
        ts = _t.time() * 1000
        timeline_store.append_entries(program_id, [{
            "kind": "chat_summary", "client_id": f"ai_sum_{int(ts)}",
            "ts": ts, "payload": {"summary": s[:600], "covers": len(lines)}}])
        print(f"[CONVERSE] 요약 롤링 저장 ({len(lines)}줄 -> {len(s)}자)")
