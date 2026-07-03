"""[QUALITY / edit_value_v2 후보] 로그 전용 품질 신호 — 판단 비관여.

배경: TVSum 50 실측에서 기존 edit_value는 사람 중요도와 무상관(FAIL).
     → 대체 신호를 '제품 판단에 넣기 전에' 로그로만 흘려 상관을 먼저 측정한다.

원칙:
  - 이 모듈은 어떤 선택/정렬에도 관여하지 않는다. print만 한다.
  - CCUT_QUALITY_LOG=1 일 때만 동작 (기본 OFF).
  - 신호는 전부 센서층 사실에서 유도 (모션/음성/장면 어휘 다양성/길이 적정).

측정 계획: golden runner가 [QUALITY_V2] 라인을 수집 → 사람 평가(블라인드)와
Spearman 상관 → 유의하면 그때 proposal 정렬 후보로 승격 (별도 게이트).
"""
import os
import math


def quality_log_enabled():
    return os.getenv("CCUT_QUALITY_LOG") in ("1", "true", "True")


def _safe(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def edit_value_v2_signals(fragment):
    """조각 1개 → 신호 dict. 점수 합산은 하지 않는다(가중치는 측정 후 결정)."""
    s = fragment.get("structural") or {}
    sem = fragment.get("semantic") or {}
    intel = fragment.get("intelligence") or {}

    dur = _safe(s.get("duration") or fragment.get("duration"))
    motion = _safe(s.get("motion_score") or s.get("motion"))
    # 음성 밀도: ASR 텍스트 길이 / 길이 (말이 있는 조각의 프록시)
    text = str(sem.get("text") or sem.get("description") or intel.get("description") or "")
    speech_density = (len(text) / dur) if dur > 0 else 0.0
    # 장면 어휘 다양성: scene/visual 묘사의 고유 단어 수 (단조 장면 프록시)
    scene = str(sem.get("scene") or intel.get("visual_desc") or "")
    scene_vocab = len(set(w for w in scene.lower().split() if len(w) > 2))
    # 길이 적정: 3~15s 를 정점으로 하는 종형 (너무 짧거나 긴 컷 페널티 프록시)
    length_fit = math.exp(-((dur - 9.0) ** 2) / (2 * 6.0 ** 2)) if dur > 0 else 0.0

    return {
        "fid": fragment.get("fragment_id"),
        "dur": round(dur, 2),
        "motion": round(motion, 4),
        "speech_density": round(speech_density, 3),
        "scene_vocab": scene_vocab,
        "length_fit": round(length_fit, 3),
        "edit_value_v1": _safe(s.get("edit_value"), 0.5),  # 대조군 (무상관 판정된 기존값)
    }


def log_pool_quality(fragments, tag="pool"):
    """조각 pool 전체의 신호를 로그로 방출. 반환값 없음(비관여)."""
    if not quality_log_enabled():
        return
    for f in fragments or []:
        try:
            sig = edit_value_v2_signals(f)
            print(f"[QUALITY_V2] tag={tag} " +
                  " ".join(f"{k}={v}" for k, v in sig.items()))
        except Exception as e:
            print(f"[QUALITY_V2][WARN] {f.get('fragment_id')} 신호 실패 ({e})")
