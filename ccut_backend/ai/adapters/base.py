"""Adapter 공통 베이스."""

import time
from typing import Optional
from ..schemas import HealthStatus


class BaseAdapter:
    model_id: str = "base"
    adapter_version: str = "0.0"

    def __init__(self, config: dict):
        self.config = config or {}
        self._loaded = False
        self._load_error: Optional[str] = None

    def _stamp(self, result):
        if hasattr(result, "model_id"):
            result.model_id = self.model_id
        if hasattr(result, "adapter_version"):
            result.adapter_version = self.adapter_version
        return result

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=self._loaded and self._load_error is None,
            model_id=self.model_id,
            version=self.adapter_version,
            loaded=self._loaded,
            error=self._load_error,
        )
