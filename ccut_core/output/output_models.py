from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class OutputSegment:
    segment_id: str
    start: float
    end: float
    label: str


@dataclass(frozen=True)
class EngineOutput:
    version: int
    segments: tuple
