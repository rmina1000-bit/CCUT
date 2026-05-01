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
        return segments

    def get_rms_energy(self, start: float, duration: float) -> float:
        """[STEP 2] 구간의 오디오 에너지(RMS) 계산"""
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", self.video_path,
            "-af", "volumedetect", "-f", "null", "NUL"
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            _, stderr = proc.communicate(timeout=10)
            match = re.search(r"mean_volume:\s*([\-\d.]+) dB", stderr)
            if match:
                db = float(match.group(1))
                # dB to linear (approximate)
                return round(pow(10, db/20), 4)
        except Exception as e:
            print(f"[SignalProcessor] RMS calculation failed: {e}")
        return 0.0

    def _detect_silence(self) -> list[float]:
        # Quick FFmpeg run for silence detection
        cmd = [
            "ffmpeg", "-y", "-i", self.video_path,
            "-af", "asetpts=PTS-STARTPTS,silencedetect=n=-30dB:d=0.3",
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

