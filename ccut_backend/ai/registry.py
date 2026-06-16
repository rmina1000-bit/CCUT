"""AI Registry · 활성 Adapter 관리.

config.yaml 의 active 필드를 읽어 해당 Adapter를 로드한다.
교체 시 config.yaml 수정 + Registry.reload() 호출.
"""

import os
from typing import Optional
from .interface import ASRProvider, VLProvider


_ADAPTER_CLASS_MAP = {
    "WhisperAdapter": "ccut_backend.ai.adapters.whisper_adapter.WhisperAdapter",
    "WhisperVulkanAdapter": "ccut_backend.ai.adapters.whisper_vulkan_adapter.WhisperVulkanAdapter",
}


def _load_adapter_class(class_name: str):
    """Adapter 클래스 이름을 실제 클래스 객체로 변환."""
    if class_name == "WhisperAdapter":
        from .adapters.whisper_adapter import WhisperAdapter
        return WhisperAdapter
    if class_name == "Qwen3ASRAdapter":
        from .adapters.qwen3_asr_adapter import Qwen3ASRAdapter
        return Qwen3ASRAdapter
    if class_name == "WhisperVulkanAdapter":
        from .adapters.whisper_vulkan_adapter import WhisperVulkanAdapter
        return WhisperVulkanAdapter
    raise ValueError(f"Unknown adapter class: {class_name}")


def _load_yaml_simple(path: str) -> dict:
    """PyYAML 없이 간단한 YAML 파싱 (기본 구조만 지원)."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass

    result = {"active": {"asr": "whisper"}, "providers": {
        "whisper": {"adapter": "WhisperAdapter", "config": {"model_size": "tiny"}}
    }}
    return result


class AIRegistry:
    _instance = None

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config_path = config_path
        self.config = _load_yaml_simple(config_path)
        self._asr: Optional[ASRProvider] = None
        self._vl: Optional[VLProvider] = None

    def get_asr(self) -> ASRProvider:
        if self._asr is None:
            active_key = self.config.get("active", {}).get("asr", "whisper")
            provider_cfg = self.config.get("providers", {}).get(active_key, {})
            adapter_cls_name = provider_cfg.get("adapter", "WhisperAdapter")
            adapter_cls = _load_adapter_class(adapter_cls_name)
            self._asr = adapter_cls(provider_cfg.get("config", {}))
        return self._asr

    def get_vl(self) -> Optional[VLProvider]:
        return self._vl

    def reload(self):
        self._asr = None
        self._vl = None
        self.config = _load_yaml_simple(self.config_path)


def get_registry() -> AIRegistry:
    if AIRegistry._instance is None:
        AIRegistry._instance = AIRegistry()
    return AIRegistry._instance
