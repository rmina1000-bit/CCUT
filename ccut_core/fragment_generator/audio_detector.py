"""
audio_detector.py
-----------------
RMS-energy-based audio boundary detector.

Algorithm:
  1. Extract mono 22050 Hz WAV via ffmpeg subprocess (no AI).
  2. Slice into 20 ms windows; compute RMS per window.
  3. Energy ratio between adjacent windows > AUDIO_ENERGY_THRESHOLD → boundary.
  4. Silence ≥ 0.5 s (RMS < SILENCE_FLOOR) followed by sound → boundary.
  5. Enforce MIN_INTERVAL between boundaries.

Deterministic: subprocess output is deterministic for fixed input.
"""

import os
import subprocess
import tempfile
import wave
from typing import List

import numpy as np

MIN_INTERVAL: float = 0.8
AUDIO_ENERGY_THRESHOLD: float = 1.8
SILENCE_DURATION: float = 0.5
WINDOW_MS: int = 20
SAMPLE_RATE: int = 22050
SILENCE_FLOOR: float = 0.005   # normalised RMS below this = silence


def _extract_wav(video_path: str, wav_path: str) -> bool:
    """Use ffmpeg to extract a mono 22050 Hz WAV. Returns True on success."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-f", "wav",
        wav_path,
        "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0 and os.path.getsize(wav_path) > 44


def _rms_windows(wav_path: str) -> List[tuple]:
    """
    Returns list of (timestamp_seconds, rms_value) for every 20 ms window.
    """
    windows = []
    with wave.open(wav_path, "rb") as wf:
        framerate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()

        window_frames = max(1, int(framerate * WINDOW_MS / 1000))
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
        scale = float(2 ** (8 * sampwidth - 1))

        frame_pos = 0
        while frame_pos < n_frames:
            raw = wf.readframes(window_frames)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype=dtype).astype(np.float32) / scale
            rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
            t = round(frame_pos / framerate, 3)
            windows.append((t, rms))
            frame_pos += window_frames

    return windows


def detect_audio_changes(video_path: str) -> List[float]:
    """
    Returns list of boundary timestamps (seconds).
    Returns [] if no audio track or ffmpeg unavailable.
    """
    tmp_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)

    try:
        if not _extract_wav(video_path, wav_path):
            return []

        windows = _rms_windows(wav_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    if not windows:
        return []

    boundaries: List[float] = []
    last_t: float = 0.0
    silence_start = None
    prev_rms: float = windows[0][1]

    def _add(t: float) -> None:
        nonlocal last_t
        if (t - last_t) >= MIN_INTERVAL:
            boundaries.append(t)
            last_t = t

    for t, rms in windows:
        in_silence = rms < SILENCE_FLOOR

        # ── Silence tracking ───────────────────────────────────────────────
        if in_silence:
            if silence_start is None:
                silence_start = t
        else:
            if silence_start is not None:
                gap = t - silence_start
                if gap >= SILENCE_DURATION:
                    _add(t)          # boundary at end of silence region
                silence_start = None

            # ── Energy-change detection ─────────────────────────────────────
            if prev_rms > 1e-8:
                ratio = rms / prev_rms
            else:
                ratio = rms / 1e-8

            if ratio > AUDIO_ENERGY_THRESHOLD or ratio < (1.0 / AUDIO_ENERGY_THRESHOLD):
                _add(t)

        if not in_silence:
            prev_rms = rms

    return sorted(set(boundaries))
