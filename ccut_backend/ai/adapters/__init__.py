"""AI Adapter 구현체 모음."""

from .base import BaseAdapter
from .whisper_adapter import WhisperAdapter

__all__ = ["BaseAdapter", "WhisperAdapter"]
