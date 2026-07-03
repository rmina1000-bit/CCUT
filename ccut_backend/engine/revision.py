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
    return os.getenv("CCUT_REVISION") in ("1", "true", "True")


# ---------------------------------------------------------------- P3-REV 감지
# 수정 명령 = "기존 결과"를 전제로 하는 지시. 신규 편집 지시와 구분한다.
_REV_REMOVE = ("빼줘", "빼 줘", "빼라", "제외해", "제외 해", "삭제해", "지워", "없애")
_REV_COUNT = re.compile(r"(\d+)\s*개로")
_REV_ORDINAL = re.compile(r"(첫|첫\s*번째|두\s*번째|세\s*번째|네\s*번째|다섯\s*번째|마지막)\s*(조각|장면|컷|클립)")
_ORDINAL_MAP = {"첫": 0, "첫번째": 0, "두번째": 1, "세번째": 2, "네번째": 3, "다섯번째": 4, "마지막": -1}
_REV_MARKERS = ("에서", "지금", "이거", "여기서", "방금", "현재")


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
        # 테마 제거 — 테마 추출은 hub extract_intent 재사용 (판단자 1곳 원칙)
        from engine import hub as _hub
        intent = _hub.extract_intent(t)
        theme = intent.get("exclude") or intent.get("keep")
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
