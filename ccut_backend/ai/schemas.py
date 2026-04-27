"""AI 입출력 표준 스키마 (계약 · 불변)."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranscriptSegment:
    start_sec: float
    end_sec: float
    text: str
    language: Optional[str] = None


@dataclass
class TranscriptResult:
    segments: list
    full_text: str
    language_detected: str
    model_id: str = ""
    adapter_version: str = ""
    raw: Optional[dict] = None


@dataclass
class HealthStatus:
    ok: bool
    model_id: str
    version: str
    loaded: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
