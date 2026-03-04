from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RenderSegment:
    segment_id: str
    start: float
    end: float


@dataclass(frozen=True)
class RenderRequest:
    version: int
    segments: Tuple[RenderSegment, ...]
    artifact_hash: str
