import subprocess
import re
import os
import time
from pathlib import Path
from engine.blackbox import blackbox

class SignalProcessor:
    """
    CCUT 1.0.5 - FFmpeg based signal preprocessing engine.
    Optimized for non-blocking I/O and deadlock prevention.
    """

    def __init__(self, video_path: str):
        self.video_path = str(video_path)
        # Ensure the file exists
        if not os.path.exists(self.video_path):
            print(f"[SignalProcessor] WARNING: Video path {self.video_path} does not exist.")

    def build_dynamic_segments(self, video_duration: float, status_obj=None) -> list[dict]:
        """
        [STEP 1] Dynamic segment partitioning (10~30s) with 0.5s overlap.
        [STEP 10-I.3] Fast Path for shorts (<= 60s):
        - 60초 이하 영상은 1~3개 대형 조각으로 제한하여 파티션 폭주 방지.
        """
        is_fast_path = video_duration <= 60.0
        print(f"[SignalProcessor] Starting {'FAST PATH' if is_fast_path else 'DYNAMIC'} partitioning for {video_duration}s video...")
        
        # 1. 침묵 및 장면 전환 탐지
        if status_obj: status_obj.update({"msg": "Analyzing audio/visual signals...", "progress": 15})
        silence_pts = self._detect_silence()
        scene_pts = self._detect_scenes(limit_sec=video_duration)
        
        # 모든 탐지 지점 통합
        triggers = sorted(list(set([t for t in silence_pts + scene_pts if 0.5 < t < video_duration - 0.5])))

        segments = []
        current_start = 0.0
        overlap = 0.5
        
        while current_start < video_duration:
            # Fast Path 시 더 긴 구간(30s)을 지향
            ideal_end = current_start + (30.0 if is_fast_path else 20.0)
            
            # Fast Path 시 최소 15s 보장, 일반 10s 보장
            min_window = 15.0 if is_fast_path else 10.0
            max_window = 45.0 if is_fast_path else 30.0
            legal_triggers = [t for t in triggers if current_start + min_window <= t <= current_start + max_window]
            
            if legal_triggers:
                # 이상적인 종료 지점(20s)에 가장 가까운 지점 선택
                best_end = min(legal_triggers, key=lambda t: abs(t - ideal_end))
            else:
                # 기간 내 지점이 없으면 강제 분할 (Fast Path 시 45s까지 허용)
                best_end = min(current_start + max_window, video_duration)
            
            # 마지막 잔여 구간 처리: 남은 구간이 너무 짧으면 합침 (최대 35s 허용)
            remaining = video_duration - best_end
            if 0 < remaining < 8.0:
                best_end = video_duration
            
            duration = round(best_end - current_start, 2)
            if duration > 0.1:
                segments.append({
                    "index": len(segments),
                    "start": round(current_start, 2),
                    "end": round(best_end, 2),
                    "duration": duration
                })
            
            if best_end >= video_duration:
                break
                
            # 다음 구간은 0.5s 오버랩 적용
            current_start = best_end - overlap

        print(f"[SignalProcessor] Created {len(segments)} dynamic segments (10-30s).")
        return segments, triggers

    def get_rms_energy(self, start: float, duration: float):
        """[STEP 2] 구간의 오디오 에너지(RMS) 계산. 실패하면 None.

        [LAB-51] 반환 계약 변경: 실패 시 0.0 이 아니라 **None**.
          구판은 예외를 삼키고 0.0 을 돌려줘 '측정 실패'와 '무음'을 같은 값으로 뭉갰다.
          그래서 main.py 의 "RMS 측정 실패 → pending 처리(static 오판 금지)" 방어가
          영영 도달하지 못했다 — except 가 발동할 예외가 없었으니까.
          실측 사고(2026-07-30 SRC_3111FA4F, 28분): timeout 10s 초과 → 0.0 →
          static 오판(임계 0.02) → ASR 강제 스킵 → 자막 0·SF 0.
          같은 파일을 넉넉한 timeout 으로 재면 -16.0 dB = 0.1585 로, 임계의 8배다.
          모르는 것을 0으로 위장하지 않는다.

        timeout: 길이에 비례시킨다. 실측 28분(1685s) 전체 스캔에 22.7s 가 걸렸다
          (≈ 재생시간의 1.35%). 여유를 4배쯤 두고 하한 30s —
          max(30, duration × 0.05) 이면 28분 영상에 84s 로 실측의 3.7배 여유다.
        """
        timeout_sec = max(30.0, float(duration or 0.0) * 0.05)
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", self.video_path,
            "-af", "volumedetect", "-f", "null", "NUL"
        ]
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            _, stderr = proc.communicate(timeout=timeout_sec)
            match = re.search(r"mean_volume:\s*([\-\d.]+) dB", stderr)
            if match:
                db = float(match.group(1))
                # dB to linear (approximate)
                return round(pow(10, db/20), 4)
            print(f"[SignalProcessor] RMS: mean_volume 미검출 — 측정 불가(None) {self.video_path}")
            return None
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            print(f"[SignalProcessor] RMS timeout {timeout_sec:.0f}s 초과 — 측정 불가(None), "
                  f"duration={duration}s")
            return None
        except Exception as e:
            print(f"[SignalProcessor] RMS calculation failed — 측정 불가(None): {e}")
            return None

    def _detect_silence(self) -> list[float]:
        # Quick FFmpeg run for silence detection
        cmd = [
            "ffmpeg", "-y", "-i", self.video_path,
            "-af", "asetpts=PTS-STARTPTS,silencedetect=n=-30dB:d=0.8",
            "-f", "null", "NUL"
        ]
        pts = []
        try:
            # logs go to stderr
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            _, stderr = proc.communicate(timeout=15)
            pts = [float(t) for t in re.findall(r"silence_end:\s*([\d.]+)", stderr)]
        except Exception as e:
            print(f"[SignalProcessor] Silence detect skipped: {e}")
        return pts

    def _detect_scenes(self, limit_sec: int = 30) -> list[float]:
        # Fast scene detection using scdet filter
        cmd = [
            "ffmpeg", "-y", "-t", str(limit_sec), "-i", self.video_path,
            "-vf", "setpts=PTS-STARTPTS,select=gt(scene,0.4),showinfo",
            "-f", "null", "NUL"
        ]
        pts = []
        try:
            # Windows?먯꽌??NUL ?μ튂媛 ?덉쟾?? stdout? 臾댁떆?섍퀬 stderr(濡쒓렇)留??띾뱷.
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            _, stderr = proc.communicate(timeout=30)
            pts = [float(t) for t in re.findall(r"pts_time:([\d.]+)", stderr)]
        except Exception as e:
            print(f"[SignalProcessor] Scene detect skipped: {e}")
        return pts


def pre_profile_source(
    audio_energies: list,
    scene_changes: list,
    duration_sec: float,
) -> dict:
    """[단계1-A] ASR 이전 사전 판정.
    mean_energy < 0.02 AND scene_rate < 0.05 -> static 확정.
    그 외 pending. 입력이 비면 static 오판 금지 -> pending.
    """
    if not audio_energies:
        return {
            "profile": "pending",
            "asr_skipped": False,
            "mean_audio_energy": None,
            "scene_rate": round(len(scene_changes) / max(duration_sec, 1.0), 4),
            "note": "no_energy_input",
        }

    mean_energy = sum(audio_energies) / len(audio_energies)
    scene_rate = len(scene_changes) / max(duration_sec, 1.0)

    if mean_energy < 0.02 and scene_rate < 0.05:
        return {
            "profile": "static",
            "asr_skipped": True,
            "asr_yield": 0.0,
            "mean_audio_energy": round(mean_energy, 4),
            "scene_rate": round(scene_rate, 4),
            "confidence": 0.3,
        }

    return {
        "profile": "pending",
        "asr_skipped": False,
        "mean_audio_energy": round(mean_energy, 4),
        "scene_rate": round(scene_rate, 4),
    }


def profile_source(
    source_id: str,
    all_words: list,
    scene_changes: list,
    audio_energies: list,
    duration_sec: float,
    pre: dict = None,
) -> dict:
    """[단계1-B] ASR 이후 최종 판정 + logs/source_profile 저장."""
    import json, os
    from datetime import datetime

    mean_energy = (sum(audio_energies) / len(audio_energies)) if audio_energies else 0.0
    scene_rate = len(scene_changes) / max(duration_sec, 1.0)
    asr_yield = len(all_words) / max(duration_sec, 1.0)

    if pre and pre.get("profile") == "static":
        final_profile = "static"
        confidence = 0.3
        asr_skipped = bool(pre.get("asr_skipped"))
    else:
        asr_skipped = False
        if asr_yield >= 0.5:
            final_profile = "speech_led"
            confidence = round(min(0.5 + asr_yield * 0.3, 1.0), 4)
        elif scene_rate >= 0.05:
            final_profile = "visual_led"
            confidence = round(min(0.5 + scene_rate * 2.0, 1.0), 4)
        else:
            final_profile = "static"
            confidence = 0.3

    result = {
        "source_id": source_id,
        "profile": final_profile,
        "asr_skipped": asr_skipped,
        "asr_yield": round(asr_yield, 4),
        "mean_audio_energy": round(mean_energy, 4),
        "scene_rate": round(scene_rate, 4),
        "confidence": round(confidence, 4),
        "pre_profile": pre,
        "timestamp": datetime.now().isoformat(),
    }

    log_dir = "logs/source_profile"
    log_path = f"{log_dir}/{source_id}.json"
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[profile_source] {source_id} -> {final_profile} "
              f"(conf={confidence:.2f}) asr_skipped={asr_skipped}")
    except Exception as e:
        print(f"[profile_source] 저장 실패 (무시): {e}")

    return result


def refine_boundaries_to_words(
    fragments: list,
    all_words: list,
    max_shift_sec: float = 2.0,
    min_gap_sec: float = 0.15,
    min_fragment_sec: float = 1.0,
) -> list:
    """[단계2] 인접 조각 사이 경계를 가장 가까운 발화 휴지로 스냅.
    조각 생성/삭제 없음. 제안 목록만 반환 (적용은 호출측 책임).
    """
    proposals = []
    if not all_words or len(fragments) < 2:
        return proposals

    gaps = []
    for i in range(len(all_words) - 1):
        try:
            prev_end = float(all_words[i].get("end", 0))
            next_start = float(all_words[i + 1].get("start", 0))
        except (TypeError, ValueError):
            continue
        gap = next_start - prev_end
        if gap >= min_gap_sec:
            gaps.append({"mid": (prev_end + next_start) / 2.0, "len": gap})

    if not gaps:
        return proposals

    frs = sorted(fragments, key=lambda f: float(f.get("start_time", 0)))

    for i in range(len(frs) - 1):
        left, right = frs[i], frs[i + 1]
        boundary = float(left.get("end_time", 0))
        best = None
        for g in gaps:
            dist = abs(g["mid"] - boundary)
            if dist <= max_shift_sec and (
                best is None or dist < abs(best["mid"] - boundary)
            ):
                best = g
        entry = {
            "left_id": left.get("fragment_id"),
            "right_id": right.get("fragment_id"),
            "old_boundary": round(boundary, 3),
            "new_boundary": round(boundary, 3),
            "shift": 0.0,
            "gap_len": 0.0,
            "snapped": False,
        }
        if best is not None:
            nb = best["mid"]
            left_len = nb - float(left.get("start_time", 0))
            right_len = float(right.get("end_time", 0)) - nb
            if left_len >= min_fragment_sec and right_len >= min_fragment_sec:
                entry.update({
                    "new_boundary": round(nb, 3),
                    "shift": round(nb - boundary, 3),
                    "gap_len": round(best["len"], 3),
                    "snapped": True,
                })
        proposals.append(entry)

    return proposals


def detect_scenes_rescan(video_path: str, duration_sec: float,
                         threshold: float = 0.22) -> list:
    """[단계3.6] 경계 기근 소스용 저임계 장면 재스캔.
    기존 _detect_scenes(0.4)가 후보 0개일 때만 호출되는 보강 경로.
    반환: 장면 전환 타임스탬프(float) 목록.
    """
    import subprocess, re
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"setpts=PTS-STARTPTS,select=gt(scene,{threshold}),showinfo",
        "-f", "null", "NUL",
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        _, stderr = proc.communicate(timeout=max(60, int(duration_sec)))
        pts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", stderr)]
        return [p for p in pts if 0.0 < p < duration_sec]
    except Exception as e:
        print(f"[RESCAN] 저임계 장면 재스캔 실패 (무시): {e}")
        return []


def extract_motion_curve(video_path: str, duration_sec: float,
                         fps_sample: float = 2.0) -> list:
    """[M-1] 프레임 간 변화량(scene score)을 연속 곡선으로 추출.
    임계 비교 없음 — 곡선 자체를 반환.
    반환: [{"t": float, "score": float}, ...] (t 오름차순)
    실패 시 빈 리스트 (호출측이 폴백 판단).
    """
    import subprocess, re, tempfile, os
    out = []
    tmp = None
    try:
        # [M-1.1] Windows: 절대경로의 드라이브 콜론(C:)이
        # ffmpeg 필터 옵션 파서와 충돌 — CWD에 생성 후
        # 필터에는 파일명(상대)만 전달한다.
        fd, tmp = tempfile.mkstemp(suffix=".txt", dir=os.getcwd())
        os.close(fd)
        tmp_name = os.path.basename(tmp)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"fps={fps_sample},select='gte(scene,0)',"
                   f"metadata=print:file={tmp_name}",
            "-f", "null", "NUL",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.communicate(timeout=max(120, int(duration_sec * 2)))
        with open(tmp, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        pairs = re.findall(
            r"pts_time:([\d.]+).*?lavfi\.scene_score=([\d.]+)",
            txt, re.S,
        )
        for t, s in pairs:
            tv = float(t)
            if 0.0 <= tv <= duration_sec:
                out.append({"t": tv, "score": float(s)})
    except Exception as e:
        print(f"[MOTION_CURVE] 추출 실패 (무시): {e}")
        return []
    finally:
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass
    return sorted(out, key=lambda x: x["t"])


def motion_scores_for_spans(video_path: str, duration_sec: float, spans: list,
                            fps_sample: float = 2.0, curve: list = None) -> list:
    """[SIGNAL-WAKE-1] 구간별 모션 점수 = extract_motion_curve 샘플의 구간 평균.

    생산함수(extract_motion_curve)·저장컬럼(evidence_board.motion_score)·
    소비처(proposal_engine:211)는 이미 있었고 배선만 끊겨 있었다(256/256 전부 0).
    새 모델·새 테이블 없이 기존 곡선을 구간으로 접기만 한다.

    spans: [(start_sec, end_sec), ...]
    반환: [float | None, ...] — 구간에 샘플이 없으면 None ("모른다"를 0으로 위장하지 않는다)
    """
    c = curve if curve is not None else extract_motion_curve(video_path, duration_sec, fps_sample)
    out = []
    for s, e in spans:
        vals = [p["score"] for p in c if s <= p["t"] < e]
        out.append(round(sum(vals) / len(vals), 6) if vals else None)
    return out


def beat_times(video_path: str, duration_sec: float = None) -> list:
    """[SIGNAL-WAKE-1] 오디오 비트 시각(초). 기존 설치 자산(librosa)만 사용 — 새 모델 없음.

    실패·무음·librosa 부재면 빈 리스트를 그대로 반환한다(없는 걸 있다고 하지 않는다).
    """
    import subprocess, tempfile, os
    tmp = None
    try:
        import librosa
    except Exception as e:
        print(f"[BEAT] librosa 없음 — 건너뜀: {e}")
        return []
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
               "-vn", "-ac", "1", "-ar", "22050", tmp]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=max(120, int((duration_sec or 60) * 2)))
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            return []
        y, sr = librosa.load(tmp, sr=22050, mono=True)
        if y is None or len(y) == 0:
            return []
        _tempo, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        return [round(float(t), 3) for t in librosa.frames_to_time(frames, sr=sr)]
    except Exception as e:
        print(f"[BEAT] 추출 실패 (무시): {e}")
        return []
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def find_motion_inflections(curve: list, min_gap_sec: float = 3.0,
                            smooth_window: int = 4,
                            k_smooth: float = 1.0,
                            k_raw: float = 0.5) -> list:
    """[M-1] 모션 곡선에서 변곡점(국소 최대) 검출.
    D1: 평활 피크 ±2샘플 창에서 raw 최대점 시각 채택.
    D2: 그 raw 최대 < raw_mean + k_raw*raw_std 이면 기각.
    반환: [{"t": float, "score": float,
            "reason": "motion_inflection"}, ...]
    """
    n = len(curve)
    if n < smooth_window + 2:
        return []

    raw = [c["score"] for c in curve]
    ts = [c["t"] for c in curve]

    raw_mean = sum(raw) / n
    raw_var = sum((x - raw_mean) ** 2 for x in raw) / n
    raw_std = raw_var ** 0.5
    raw_floor = raw_mean + k_raw * raw_std

    # 이동평균 (트레일링이지만 D1 보정으로 시각 지연 해소)
    sm = []
    for i in range(n):
        lo = max(0, i - smooth_window + 1)
        win = raw[lo:i + 1]
        sm.append(sum(win) / len(win))

    sm_mean = sum(sm) / n
    sm_var = sum((x - sm_mean) ** 2 for x in sm) / n
    sm_std = sm_var ** 0.5
    sm_thresh = sm_mean + k_smooth * sm_std

    candidates = []
    for i in range(1, n - 1):
        if sm[i] < sm_thresh:
            continue
        if not (sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]):
            continue
        # D1: ±2샘플 창에서 raw 최대점
        lo, hi = max(0, i - 2), min(n - 1, i + 2)
        j = max(range(lo, hi + 1), key=lambda k: raw[k])
        # D2: raw 동반 조건
        if raw[j] < raw_floor:
            continue
        candidates.append({"t": ts[j], "score": round(raw[j], 6),
                           "reason": "motion_inflection"})

    # min_gap 중복 제거 (점수 높은 것 우선 유지)
    candidates.sort(key=lambda c: -c["score"])
    kept = []
    for c in candidates:
        if all(abs(c["t"] - k["t"]) >= min_gap_sec for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c["t"])


