"""AI Provider 계약 (Layer 1 · 절대 불변)."""

from abc import ABC, abstractmethod
from typing import Optional
from .schemas import TranscriptResult, HealthStatus


class ASRProvider(ABC):
    """음성 → 텍스트 전사 Provider 계약."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptResult:
        """오디오 파일을 전사한 결과를 TranscriptResult 형식으로 반환."""
        raise NotImplementedError

    @abstractmethod
    def transcribe_fragments(self, video_path: str, fragments: list) -> dict:
        """비디오와 fragment 목록을 받아 fragment_id → transcript 딕셔너리 반환.

        기존 engine.ai_engine.transcribe_full_then_split 와 동일 시그니처.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> HealthStatus:
        raise NotImplementedError


class VLProvider(ABC):
    """비전-언어 Provider 계약 (PHASE B에서 사용)."""

    @abstractmethod
    def analyze_fragment(self, frame_paths, transcript=None):
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> HealthStatus:
        raise NotImplementedError
