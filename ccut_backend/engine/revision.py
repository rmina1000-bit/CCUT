"""[REVISION / P3-REV] 두 번째 문장 — 기존 제안에 대한 수정 명령.

설계 원칙 (판단은 hub 한 곳, 실행은 결정론):
  - 수정 명령 감지는 결정론 어휘 우선 (빼줘/제외/추가/N개로/바꿔).
  - 조각 판단이 필요한 수정(테마 조건)은 hub.plan_edit 재사용 — 새 판단자를 만들지 않는다.
  - 시퀀스 조작(제거/개수 조정/순서 유지)은 전부 결정론.
  - honest-empty: 수정 결과가 빈 시퀀스면 그대로 빈 시퀀스 (조작 폴백 금지).

게이트: CCUT_REVISION=1 일 때만 detect/apply가 활성. 기본 OFF — 기존 경로 무변.

로그 체인: [P3-REV] detect / [P4-REV] apply — 기존 [P3b]/[P4] 체인과 같은 문법.
"""
import os
import re


def revision_enabled():
    # [#57 QWEN-R1 본체] 기본 ON 격상 — CCUT_REVISION=0 으로 가역 (구: 기본 OFF)
    return os.getenv("CCUT_REVISION", "1") not in ("0", "false", "False")


# ---------------------------------------------------------------- P3-REV 감지
# 수정 명령 = "기존 결과"를 전제로 하는 지시. 신규 편집 지시와 구분한다.
_REV_REMOVE = ("빼줘", "빼 줘", "빼라", "제외해", "제외 해", "삭제해", "지워", "없애")
_REV_COUNT = re.compile(r"(\d+)\s*개로")
_REV_ORDINAL = re.compile(r"(첫|첫\s*번째|두\s*번째|세\s*번째|네\s*번째|다섯\s*번째|마지막)\s*(조각|장면|컷|클립)")
_ORDINAL_MAP = {"첫": 0, "첫번째": 0, "두번째": 1, "세번째": 2, "네번째": 3, "다섯번째": 4, "마지막": -1}
_REV_MARKERS = ("에서", "지금", "이거", "여기서", "방금", "현재")
# [#57] 명시 타겟("B안에서") — 수정 명령이 어느 안을 겨누는지 결정론 파싱.
# 앞이 영숫자면 불인정("DB안정성"의 'B안' 오탐 차단)
_REV_TARGET = re.compile(r"(?<![A-Za-z0-9])([AaBb])\s*안")
# [#57] 큐원 이해 폴백 소집 조건 — 수정 동사/서수 힌트가 있을 때만 (일상 대화 납치 방지)
_REV_HINT = re.compile(r"빼|제외|삭제|지워|없애|줄여|번째|마지막|맨\s*(앞|뒤)|개로")
_REV_OPS = ("remove_ordinal", "set_count", "remove_theme")


def detect_target_mode(t):
    """'B안에서' → 'B'. 없으면 None."""
    m = _REV_TARGET.search(t or "")
    return m.group(1).upper() if m else None


def validate_revision(rev):
    """[#57 결재선] op는 출처(결정론/큐원/프론트 전달) 불문 집행 전 전수 검증.
    화이트리스트 op + 값 범위를 통과한 정규형만 반환, 아니면 None (조용한 관용 금지)."""
    if not isinstance(rev, dict) or rev.get("op") not in _REV_OPS:
        return None
    out = {"op": rev["op"]}
    if rev["op"] == "remove_ordinal":
        try:
            idx = int(rev.get("index"))
        except (TypeError, ValueError):
            return None
        if not (-1 <= idx <= 39):
            return None
        out["index"] = idx
    elif rev["op"] == "set_count":
        try:
            n = int(rev.get("count"))
        except (TypeError, ValueError):
            return None
        if not (1 <= n <= 40):
            return None
        out["count"] = n
    else:  # remove_theme
        theme = str(rev.get("theme") or "").strip()
        if not theme or len(theme) > 20:
            return None
        out["theme"] = theme
    if rev.get("target_mode") in ("A", "B"):
        out["target_mode"] = rev["target_mode"]
    if rev.get("via"):
        out["via"] = rev["via"]
    return out


def llm_detect_revision(instruction):
    """[#57 이중핵] 결정론이 못 읽은 수정 명령을 큐원이 '이해'만 한다 — 출력은 op JSON.
    집행 여부는 validate_revision(규칙)이 결정. 실패/비정형이면 None (폴백 조작 금지)."""
    from engine import hub as _hub
    prompt = (
        "사용자가 '현재 편집안'을 고치는 명령에서 수정 연산 하나만 JSON으로 뽑아라. "
        "조각 판단·선택·창작은 하지 마라.\n"
        "op 종류:\n"
        "- remove_ordinal: n번째/마지막 조각 제거. index는 0부터 (첫번째=0, 두번째=1, 마지막=-1)\n"
        "- set_count: 조각 개수 지정\n"
        "- remove_theme: 내용 조건 제거 (theme=조건 명사)\n"
        "해당 없으면 op는 \"none\".\n"
        "예시:\n"
        '  "두번째꺼 없애줄래" -> {"op":"remove_ordinal","index":1}\n'
        '  "맨 뒤에 거 빼" -> {"op":"remove_ordinal","index":-1}\n'
        '  "B안에서 세 번째 빼줘" -> {"op":"remove_ordinal","index":2,"target_mode":"B"}\n'
        '  "다섯 개로 정리해줘" -> {"op":"set_count","count":5}\n'
        '  "밤에 찍은 건 다 지워" -> {"op":"remove_theme","theme":"밤"}\n'
        '  "더 멋지게 해줘" -> {"op":"none"}\n'
        'JSON만: {"op":"...","index":정수,"count":정수,"theme":"...","target_mode":"A|B|null"}\n'
        f"명령: {instruction}\n")
    try:
        out = _hub._ollama_json(prompt, timeout=30)
    except Exception as e:
        print(f"[P3-REV] llm 이해 실패 ({e}) -> None")
        return None
    out["via"] = "qwen"
    rev = validate_revision(out)
    print(f"[P3-REV] detect(llm) raw={ {k: out.get(k) for k in ('op', 'index', 'count', 'theme', 'target_mode')} } "
          f"-> {'집행형 ' + str(rev) if rev else '기각(None)'} <- {instruction!r}")
    return rev


def detect_revision_full(instruction, has_committed_proposal, allow_llm=True):
    """[#57] 결정론 우선 → (힌트 있을 때만) 큐원 이해 폴백. 타겟 모드는 항상 결정론 부착."""
    t = (instruction or "").strip()
    rev = detect_revision(t, has_committed_proposal)
    if rev:
        rev["via"] = "deterministic"
    elif (allow_llm and has_committed_proposal and revision_enabled()
          and _REV_HINT.search(t)):
        rev = llm_detect_revision(t)
    if rev:
        tm = detect_target_mode(t)
        if tm:
            rev["target_mode"] = tm
    return rev


def detect_revision(instruction, has_committed_proposal):
    """수정 명령이면 {op, ...} 반환, 아니면 None (→ 기존 신규 제안 경로).

    지원 op:
      remove_ordinal: n번째/마지막 조각 제거
      remove_theme:   "밤 장면 빼줘" — hub 판단으로 테마 조각 제거
      set_count:      "5개로 줄여줘"
    """
    if not revision_enabled() or not has_committed_proposal:
        return None
    t = (instruction or "").strip()
    if not t:
        return None

    m = _REV_ORDINAL.search(t)
    if m and any(k in t for k in _REV_REMOVE):
        key = re.sub(r"\s+", "", m.group(1))
        idx = _ORDINAL_MAP.get(key)
        if idx is not None:
            out = {"op": "remove_ordinal", "index": idx}
            print(f"[P3-REV] detect {out} <- {t!r}")
            return out

    m = _REV_COUNT.search(t)
    if m:
        out = {"op": "set_count", "count": max(1, min(int(m.group(1)), 40))}
        print(f"[P3-REV] detect {out} <- {t!r}")
        return out

    if any(k in t for k in _REV_REMOVE):
        # [#57 결재선 교정] 테마 제거는 '알려진 어휘'(결정론)일 때만 규칙이 확정.
        # 구판은 여기서 extract_intent(LLM)를 몰래 타 "두번째꺼"를 테마로 날조했다
        # (E1 실측: 서수 제거 명령이 remove_theme '두번째꺼'로 오집행). 새 표현의
        # '이해'는 llm_detect_revision(큐원) 한 곳으로 — det가 None이면 그리로 간다.
        from engine import hub as _hub
        det = _hub._deterministic_intent(t)
        theme = det.get("exclude") or det.get("keep")
        if theme:
            out = {"op": "remove_theme", "theme": theme}
            print(f"[P3-REV] detect {out} <- {t!r}")
            return out

    return None


# ---------------------------------------------------------------- P4-REV 적용
def apply_revision(rev, sequence, source_ids=None):
    """확정 시퀀스에 수정 적용 → (새 시퀀스, reason).
    순서는 항상 보존. honest-empty 허용."""
    seq = list(sequence or [])
    before = len(seq)

    if rev["op"] == "remove_ordinal":
        idx = rev["index"]
        if seq and -len(seq) <= idx < len(seq):
            removed = seq.pop(idx)
            reason = f"remove_ordinal idx={idx} fid={removed.get('fragment_id')}"
        else:
            reason = f"remove_ordinal idx={idx} out_of_range (no-op)"

    elif rev["op"] == "set_count":
        n = rev["count"]
        seq = seq[:n]
        reason = f"set_count {before}->{len(seq)}"

    elif rev["op"] == "remove_theme":
        # 테마 해당 여부는 hub 판단 재사용: keep 계산 후 '테마에 해당하는' 것을 뺀다.
        from engine import hub as _hub
        fids = [f.get("fragment_id") for f in seq]
        sids = list(source_ids or {f.get("source_id") for f in seq if f.get("source_id")})
        plan = _hub.plan_edit(sids, f'{rev["theme"]}만')
        theme_fids = {k.get("fid") for k in (plan.get("keep") or []) if k.get("fid")}
        seq = [f for f in seq if f.get("fragment_id") not in theme_fids]
        reason = f'remove_theme "{rev["theme"]}" hit={before - len(seq)}/{before}'

    else:
        reason = f"unknown op {rev['op']} (no-op)"

    print(f"[P4-REV] apply {reason} seq={before}->{len(seq)}")
    return seq, reason
