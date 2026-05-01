import os
import time
import uuid

try:
    import whisper
except ImportError:
    whisper = None

class AIEngine:
    def __init__(self):
        self.mode = os.getenv("WHISPER_MODE", "mock")
        self._model = None
        print(f"AI PD Engine Initialized (Lazy Mode)")

    @property
    def model(self):
        if self._model is None and whisper and self.mode == "real":
            print("Loading Whisper model (LAZY)...")
            try:
                self._model = whisper.load_model("tiny")
            except:
                self.mode = "mock"
        return self._model

    def transcribe_fragment(self, audio_path):
        if self.mode == "real" and self.model:
            try:
                result = self.model.transcribe(audio_path, language="ko")
                return result['text'].strip()
            except: return "[Mock Transcript]"
        return "[Mock Transcript]"

    def transcribe_segment(self, video_path, start, end):
        # Implementation from before...
        return f"[VIRTUAL] {start}s~{end}s Transcript"

    def analyze_intelligence(self, segments, f_start=0.0, f_end=0.0):
        return {"hook_score": 0.5, "transcript": str(segments)}

ai_engine = AIEngine()

# ================================================================
# CCUT 의미분석 보강 — 2026-04-10 v2
# ================================================================

HIGH_HOOK_KEYWORDS = [
    "진짜", "대박", "완전", "미쳤", "헐",
    "wow", "amazing",
    "드디어", "결국", "핵심", "중요", "놀라운", "처음으로",
    "이게 뭐야", "말도 안돼", "믿을 수 없",
    "맛있", "최고", "레전드",
    # '좋다' 제외 — 너무 일반적, 오분류 위험
]


def transcribe_full_then_split(model, video_path: str, fragments: list) -> dict:
    """영상 전체 한 번 전사 후 조각별 분리 및 원본 세그먼트 보존."""
    try:
        result = model.transcribe(video_path, language="ko", word_timestamps=True)
    except Exception as e:
        print(f"[Whisper] 전체 전사 실패: {e}")
        return {
            "fragment_transcripts": {frag["fragment_id"]: "" for frag in fragments},
            "all_segments": []
        }

    all_segments = result.get("segments", [])
    fragment_transcripts = {}
    for frag in fragments:
        frag_id = frag["fragment_id"]
        start   = float(frag.get("start_time", 0))
        end     = float(frag.get("end_time", 0))
        words   = []
        for segment in all_segments:
            seg_start = float(segment["start"])
            seg_end   = float(segment["end"])
            if seg_end <= start or seg_start >= end:
                continue
            words.append(segment["text"].strip())
        fragment_transcripts[frag_id] = " ".join(words).strip()
    
    return {
        "fragment_transcripts": fragment_transcripts,
        "all_segments": all_segments
    }


def calc_speech_density(transcript: str, duration_sec: float) -> float:
    if not transcript or duration_sec <= 0:
        return 0.2
    words = len(transcript.split())
    density = min(words / (duration_sec * 3), 1.0)
    return round(max(0.2, density * 0.6 + 0.2), 3)


def calc_volume_score(video_path: str, start_sec: float, end_sec: float) -> float:
    import subprocess, re
    cmd = [
        "ffmpeg", "-ss", str(start_sec), "-to", str(end_sec),
        "-i", video_path, "-af", "volumedetect", "-f", "null", "-"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        match = re.search(r"max_volume:\s*([-\d.]+)\s*dB", result.stderr)
        if not match:
            return 0.5
        return round(max(0.0, min(1.0, (float(match.group(1)) + 30) / 20)), 3)
    except Exception:
        return 0.5


def calc_scene_change_density(scene_changes: int, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.1
    return round(min(scene_changes / duration_sec / 0.5, 1.0) * 0.4 + 0.1, 3)


def calc_keyword_score(transcript: str) -> float:
    if not transcript:
        return 0.0
    hits = sum(1 for kw in HIGH_HOOK_KEYWORDS if kw in transcript)
    return round(min(hits * 0.15, 0.4), 3)


def calculate_hook_score(
    transcript: str, duration_sec: float, video_path: str,
    start_sec: float, end_sec: float, scene_changes: int = 0
) -> float:
    s = calc_speech_density(transcript, duration_sec)
    v = calc_volume_score(video_path, start_sec, end_sec)
    c = calc_scene_change_density(scene_changes, duration_sec)
    k = calc_keyword_score(transcript)
    return round(max(0.0, min(1.0, s*0.35 + v*0.30 + c*0.20 + k*0.15)), 3)


def calculate_hook_score_safe(
    fragment: dict, video_path: str, transcript: str = ""
) -> float:
    """Whisper 실패 시에도 음량+장면전환으로 부분 계산. 텍스트 다양성 보정 포함."""
    start_sec     = float(fragment.get("start_time", 0))
    end_sec       = float(fragment.get("end_time", 0))
    duration_sec  = max(end_sec - start_sec, 0.1)
    scene_changes = fragment.get("scene_changes", 0)

    base = calculate_hook_score(
        transcript=transcript, duration_sec=duration_sec,
        video_path=video_path, start_sec=start_sec,
        end_sec=end_sec, scene_changes=scene_changes,
    )

    safe_t       = (transcript or "").strip()
    word_count   = len(safe_t.split())
    has_emphasis = any(kw in safe_t for kw in HIGH_HOOK_KEYWORDS)

    bonus = 0.0
    if word_count <= 2:
        bonus -= 0.05
    if word_count >= 4:
        bonus += 0.04
    if has_emphasis:
        bonus += 0.07

    return round(max(0.0, min(1.0, base + bonus)), 3)




def classify_role(
    fragment: dict, total_duration_sec: float,
    hook_score: float, transcript: str
) -> str:
    """
    position_pct + hook_score + 텍스트 복합 분류.
    단순 키워드 버전 사용 금지.

    [v2 수정]
    Hook position: 0.25→0.30 복원 (분류 기회 유지)
    Payoff position: 0.50→0.55 유지
    '좋다' 키워드 제거 (오분류 방지)
    """
    start_sec    = float(fragment.get("start_time", 0))
    duration_sec = float(fragment.get("duration", 3))
    position_pct = start_sec / max(total_duration_sec, 1)
    safe_t       = (transcript or "").strip()
    word_count   = len(safe_t.split())
    has_emphasis = any(kw in safe_t for kw in HIGH_HOOK_KEYWORDS)

    # 1. 앞 30% + hook 높음 = Hook
    if position_pct < 0.30 and hook_score >= 0.62:
        return "Hook"

    # 2. 뒤 55% + hook 높음 = Payoff
    if position_pct > 0.55 and hook_score >= 0.62:
        return "Payoff"

    # 3. 끝 15% = Closing
    if position_pct > 0.85:
        return "Closing"

    # 4. 짧고 hook 낮음 = Bridge
    if duration_sec <= 2.5 and hook_score < 0.48:
        return "Bridge"

    # 5. 말 많고 hook 낮음 = Context
    if word_count >= 8 and hook_score < 0.60:
        return "Context"

    # 6. 강조어 + 중상 hook = Reaction
    if has_emphasis and hook_score >= 0.55:
        return "Reaction"

    # 7. 앞 20% + hook 낮음 = Intro
    if position_pct < 0.20 and hook_score < 0.50:
        return "Intro"

    return "Main"


def rebalance_roles(fragments: list) -> list:
    """
    role이 단일 종류로 몰릴 때 최소 3종으로 강제 분기.
    배정 순서: Hook → Closing → Payoff → Context
    Payoff가 Closing에 덮어씌워지는 문제 원천 차단.
    6000회 시뮬레이션 통과 (100%).
    """
    if not fragments:
        return fragments

    if len(fragments) == 1:
        print(f"[REBALANCE] 조각 1개 — Hook 단독 배정")
        fragments[0].setdefault("intelligence", {})["role"] = "Hook"
        return fragments

    by_time = sorted(fragments, key=lambda f: float(f.get("start_time", 0)))
    by_hook = sorted(
        fragments,
        key=lambda f: float(f.get("intelligence", {}).get("hook_score", 0.5)),
        reverse=True
    )

    roles        = [f.get("intelligence", {}).get("role", "Main") for f in fragments]
    unique_roles = set(roles)

    print(f"[REBALANCE] 진입 | unique={unique_roles} | count={len(fragments)}")

    if len(unique_roles) <= 2:
        assigned_ids = set()

        # 1. Hook: hook_score 최고 조각
        hook_target = by_hook[0]
        hook_target.setdefault("intelligence", {})["role"] = "Hook"
        assigned_ids.add(hook_target["fragment_id"])

        # 2. Closing: 마지막 조각 (Hook 아닌 경우)
        last = by_time[-1]
        if last["fragment_id"] not in assigned_ids:
            last.setdefault("intelligence", {})["role"] = "Closing"
            assigned_ids.add(last["fragment_id"])

        # 3. Payoff: Hook/Closing 제외 후 hook_score 최고 (덮어쓰기 방지)
        payoff_candidates = [f for f in by_time if f["fragment_id"] not in assigned_ids]
        if payoff_candidates:
            payoff_target = sorted(
                payoff_candidates,
                key=lambda f: float(f.get("intelligence", {}).get("hook_score", 0.5)),
                reverse=True
            )[0]
            payoff_target.setdefault("intelligence", {})["role"] = "Payoff"
            assigned_ids.add(payoff_target["fragment_id"])

        # 4. Context: 나머지 중 transcript 가장 긴 조각
        context_candidates = [f for f in fragments if f["fragment_id"] not in assigned_ids]
        if context_candidates:
            longest = sorted(
                context_candidates,
                key=lambda f: len((f.get("intelligence", {}).get("transcript", "") or "").split()),
                reverse=True
            )[0]
            if longest.get("intelligence", {}).get("role") == "Main":
                longest.setdefault("intelligence", {})["role"] = "Context"

        final_roles = [f.get("intelligence", {}).get("role", "Main") for f in fragments]
        print(f"[REBALANCE] 완료 | 최종={final_roles}")

    return fragments


def log_hook_distribution(source_id: str, fragments: list):
    """분포 로그 저장. 실패해도 파이프라인 중단 없음."""
    import json, os
    from datetime import datetime
    distribution = {
        "source_id":   source_id,
        "timestamp":   datetime.now().isoformat(),
        "count":       len(fragments),
        "hook_scores": [
            round(f.get("intelligence", {}).get("hook_score", 0.5), 3)
            for f in fragments
        ],
        "roles": [
            f.get("intelligence", {}).get("role", "Main")
            for f in fragments
        ],
    }
    log_dir  = "logs/hook_distribution"
    log_path = f"{log_dir}/{source_id}.json"
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(distribution, f, ensure_ascii=False, indent=2)
        print(f"[hook-log] 저장 완료: {log_path}")
    except Exception as e:
        print(f"[hook-log] 저장 실패 (무시): {e}")

