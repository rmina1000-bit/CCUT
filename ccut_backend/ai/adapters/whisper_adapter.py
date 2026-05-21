"""Whisper Adapter · 기존 whisper 호출을 Adapter 뒤로 래핑.

동작 변화 없음. 기존 engine.ai_engine.transcribe_full_then_split 를 그대로 호출.
"""

import time
from typing import Optional
from ..interface import ASRProvider
from ..schemas import TranscriptResult, HealthStatus
from .base import BaseAdapter


class WhisperAdapter(BaseAdapter, ASRProvider):
    model_id = "whisper-tiny"
    adapter_version = "1.0"

    def __init__(self, config: dict):
        super().__init__(config)
        self._model = None
        self._model_size = (config or {}).get("model_size", "tiny")

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            import whisper
            self._model = whisper.load_model(self._model_size)
            self._loaded = True
            self._load_error = None
        except Exception as e:
            self._loaded = False
            self._load_error = str(e)
            raise

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptResult:
        self._ensure_loaded()
        start = time.time()
        raw = self._model.transcribe(audio_path, language=language) if language else self._model.transcribe(audio_path)
        elapsed_ms = int((time.time() - start) * 1000)

        segments = raw.get("segments", []) if isinstance(raw, dict) else []
        result = TranscriptResult(
            segments=segments,
            full_text=raw.get("text", "") if isinstance(raw, dict) else "",
            language_detected=raw.get("language", "unknown") if isinstance(raw, dict) else "unknown",
            raw=raw if isinstance(raw, dict) else None,
        )
        return self._stamp(result)

    def transcribe_fragments(self, video_path: str, fragments: list) -> dict:
        """기존 engine.ai_engine.transcribe_full_then_split 를 호출하여 결과 그대로 반환.

        호출 시점에 engine 모듈을 import (순환 방지).
        """
        try:
            self._ensure_loaded()
            from engine.ai_engine import transcribe_full_then_split
            result = transcribe_full_then_split(self._model, video_path, fragments)
            provider_error = None
        except Exception as e:
            result = {
                "fragment_transcripts": {f["fragment_id"]: "" for f in fragments},
                "all_segments": [],
                "fragment_words": {f["fragment_id"]: [] for f in fragments},
                "words": []
            }
            provider_error = str(e)

        rejected_fragments = {}
        for frag_id, text in result.get("fragment_transcripts", {}).items():
            if not text or not text.strip():
                rejected_fragments[frag_id] = "empty_text"

        result["provider"] = "whisper"
        result["provider_error"] = provider_error
        result["rejected_fragments"] = rejected_fragments

        return result

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=self._loaded and self._load_error is None,
            model_id=self.model_id,
            version=self.adapter_version,
            loaded=self._loaded,
            error=self._load_error,
        )
