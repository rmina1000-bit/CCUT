"""
fragment_generator.py
---------------------
Main public API for AI-free, deterministic fragment generation.

Pipeline:
    video_path
      → scene_detector  : HSV histogram boundaries
      → audio_detector  : RMS energy boundaries
      → boundary_merge  : deduplicated, min-length-enforced segments
      → FragmentIndex   : list[dict] with id / start / end / editStack
"""

from typing import List, Dict, Any

from .scene_detector import detect_scenes
from .audio_detector import detect_audio_changes
from .boundary_merge import merge_boundaries

MIN_FRAGMENT_LENGTH: float = 2.0
SCENE_THRESHOLD: float = 0.4
AUDIO_ENERGY_THRESHOLD: float = 1.8


def generate_fragments(video_path: str) -> List[Dict[str, Any]]:
    """
    Generate a deterministic FragmentIndex from a video file.

    Returns
    -------
    List of fragment dicts::

        [
            {"id": "frag_0", "start": 0.0, "end": 3.2, "editStack": []},
            {"id": "frag_1", "start": 3.2, "end": 7.8, "editStack": []},
            ...
        ]

    Guarantees
    ----------
    * No overlaps between fragments.
    * First fragment starts at 0.0.
    * Last fragment ends at total_duration.
    * Identical output for identical input (deterministic).
    * No AI models; no random values.
    """
    scenes, total_duration = detect_scenes(video_path)
    audio = detect_audio_changes(video_path)
    segments = merge_boundaries(scenes, audio, total_duration)

    return [
        {
            "id": f"frag_{i}",
            "start": start,
            "end": end,
            "editStack": [],
        }
        for i, (start, end) in enumerate(segments)
    ]
