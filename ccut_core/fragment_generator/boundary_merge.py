"""
boundary_merge.py
-----------------
Merges scene and audio boundaries into non-overlapping (start, end) tuples.

Rules (in priority order):
  1. Scene boundaries are always kept.
  2. Audio boundaries are inserted between scene boundaries.
  3. Any segment shorter than MIN_FRAGMENT_LENGTH is merged into the
     preceding segment (never creates a zero-length fragment).
  4. Coverage: [0.0 … total_duration], no gaps, no overlaps.
"""

from typing import List, Tuple

MIN_FRAGMENT_LENGTH: float = 2.0


def merge_boundaries(
    scene_list: List[float],
    audio_list: List[float],
    total_duration: float = 0.0,
) -> List[Tuple[float, float]]:
    """
    Parameters
    ----------
    scene_list      : boundary timestamps from scene_detector (must include 0.0)
    audio_list      : boundary timestamps from audio_detector
    total_duration  : video length in seconds; used to cap the last fragment

    Returns
    -------
    List of (start, end) tuples in ascending order, no overlaps, no gaps.
    """
    # ── 1. Build master point list ─────────────────────────────────────────
    scene_set = set(scene_list)
    all_points: List[float] = sorted(
        set([0.0] + list(scene_list) + list(audio_list))
    )

    # ── 2. Append total_duration as final sentinel ─────────────────────────
    if total_duration > 0.0:
        end = round(total_duration, 3)
        if not all_points or all_points[-1] < end - 0.001:
            all_points.append(end)

    if len(all_points) < 2:
        # Degenerate: single point or empty — return one fragment if possible
        if total_duration > 0.0:
            return [(0.0, round(total_duration, 3))]
        return []

    # ── 3. Build raw segments ──────────────────────────────────────────────
    raw: List[Tuple[float, float]] = []
    for i in range(len(all_points) - 1):
        s = round(all_points[i], 3)
        e = round(all_points[i + 1], 3)
        if e > s:
            raw.append((s, e))

    # ── 4. Merge segments shorter than MIN_FRAGMENT_LENGTH ─────────────────
    #
    # Strategy: iterate forward; if a segment is too short AND it is not
    # anchored by a scene boundary on both sides, absorb it into the previous
    # fragment.  Scene boundaries that ARE on both sides are never discarded
    # (the fragment simply stays short, which is acceptable for hard cuts).
    #
    merged: List[Tuple[float, float]] = []

    for seg in raw:
        s, e = seg
        length = round(e - s, 3)

        if merged and length < MIN_FRAGMENT_LENGTH:
            # Both endpoints of this short segment are scene boundaries?
            both_scene = s in scene_set and e in scene_set
            if not both_scene:
                # Absorb into previous
                prev_s, _ = merged[-1]
                merged[-1] = (prev_s, e)
                continue

        merged.append((s, e))

    return merged
