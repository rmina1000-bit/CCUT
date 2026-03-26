"""
scene_detector.py
-----------------
HSV-histogram-based scene cut detector.

Algorithm:
  1. Sample one frame per second (1 fps).
  2. Convert to HSV; compute 2-D histogram (H × S, 50 × 60 bins).
  3. Compare consecutive histograms with Bhattacharyya distance.
  4. If distance > SCENE_THRESHOLD and gap ≥ MIN_INTERVAL → boundary.

Deterministic: no random state, identical results on repeated runs.
"""

import logging
import time

import cv2
import numpy as np
from typing import List, Tuple

logger = logging.getLogger(__name__)

MIN_INTERVAL: float = 2.0
SCENE_THRESHOLD: float = 0.4

_H_BINS = 50
_S_BINS = 60


def _frame_histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv], [0, 1], None,
        [_H_BINS, _S_BINS],
        [0, 180, 0, 256],
    )
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def detect_scenes(video_path: str) -> Tuple[List[float], float]:
    """
    Returns:
        (boundaries, total_duration)
        boundaries: list of timestamps [0.0, t1, t2, …] in seconds
        total_duration: video length in seconds
    """
    t0 = time.time()
    logger.info(f"[SCENE] 씬 감지 시작: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_duration = round(n_frames / fps, 3)

    logger.info(f"[SCENE] 영상 정보: {n_frames}프레임, {fps}fps, {total_duration:.1f}초")

    step = max(1, int(round(fps)))   # frames per 1-second sample

    boundaries: List[float] = [0.0]
    last_t = 0.0
    prev_hist = None
    idx = 0
    processed = 0

    while idx < n_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(idx))
        ret, frame = cap.read()
        if not ret:
            break

        t = round(idx / fps, 3)
        hist = _frame_histogram(frame)

        if prev_hist is not None:
            dist = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
            if dist > SCENE_THRESHOLD and (t - last_t) >= MIN_INTERVAL:
                boundaries.append(t)
                last_t = t
                logger.info(f"[SCENE] 경계 감지: {t:.1f}s (dist={dist:.3f})")

        prev_hist = hist
        idx += step
        processed += 1

        if processed % 300 == 0:
            logger.info(f"[SCENE] {processed} 샘플 처리 중 ({t:.1f}s / {total_duration:.1f}s, {time.time()-t0:.1f}s 경과)")

    cap.release()
    logger.info(f"[SCENE] 씬 감지 완료: {len(boundaries)}개 경계, {time.time()-t0:.2f}s")
    return sorted(set(boundaries)), total_duration
