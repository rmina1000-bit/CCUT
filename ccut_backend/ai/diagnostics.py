"""[FIX-RUNTIME-1a] GPU ASR 런타임 환경진단 — read 전용 수집 레이어.

부작용 0 원칙: 파일 생성/이동/전사/네트워크 호출/모델(VRAM) 로드 없음.
config read + 경로 존재체크 + 디스크 용량 조회만 수행한다.
경로는 WhisperVulkanAdapter 가 __file__ 기준으로 해석한 값을 그대로 재사용하여
외부경로(D:/CCUT_EXTERNAL_DATA) 하드코딩을 만들지 않는다.
"""
import os
import shutil
import importlib.util

_AI_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_AI_DIR, "config.yaml")

# storage_free_gb 가 이 값 미만이면 warning
_STORAGE_WARN_GB = 5.0


def _load_config() -> dict:
    try:
        import yaml
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _serialize_health(hc) -> dict:
    """HealthStatus(pydantic/dataclass) → dict (스키마 결합 회피)."""
    for attr in ("model_dump", "dict"):
        fn = getattr(hc, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return {
        "ok": getattr(hc, "ok", None),
        "loaded": getattr(hc, "loaded", None),
        "error": getattr(hc, "error", None),
        "model_id": getattr(hc, "model_id", None),
    }


def collect_diagnostics() -> dict:
    """현재 GPU ASR 런타임 환경 진단 결과를 dict 로 반환 (read 전용)."""
    cfg = _load_config()
    current_asr_provider = cfg.get("active", {}).get("asr", "whisper")

    wv_cfg = cfg.get("providers", {}).get("whisper_vulkan", {}).get("config", {})

    # 어댑터 인스턴스화 = 경로 해석만(__file__ 기준). __init__ 은 전사/로드 없음.
    from .adapters.whisper_vulkan_adapter import WhisperVulkanAdapter
    adapter = WhisperVulkanAdapter(wv_cfg)

    cli_path = adapter.cli_path
    model_path = adapter.model_path
    fallback_model_path = adapter.fallback_model_path
    runtime_dir = os.path.dirname(cli_path)

    cli_path_exists = os.path.exists(cli_path)
    model_path_exists = os.path.exists(model_path)
    fallback_model_path_exists = os.path.exists(fallback_model_path)
    ffmpeg_available = shutil.which("ffmpeg") is not None
    runtime_dir_exists = os.path.isdir(runtime_dir)

    try:
        free_bytes = shutil.disk_usage(runtime_dir if runtime_dir_exists else _AI_DIR).free
        storage_free_gb = round(free_bytes / (1024 ** 3), 1)
    except Exception:
        storage_free_gb = None

    # CPU fallback(openai-whisper) 가용 여부 — 모델 로드 없이 import 가능성만 확인
    cpu_fallback_available = importlib.util.find_spec("whisper") is not None

    # 어댑터 가용성 판정 (존재체크 기반, 모델/VRAM 로드 없음)
    try:
        adapter._ensure_loaded()  # os.path.exists 만 수행
    except Exception:
        pass  # _load_error 가 채워짐
    whisper_vulkan_health = _serialize_health(adapter.health_check())

    # status 종합
    if (not ffmpeg_available) or (not cli_path_exists and not cpu_fallback_available):
        status = "fail"
    elif (not model_path_exists and fallback_model_path_exists) or (
        storage_free_gb is not None and storage_free_gb < _STORAGE_WARN_GB
    ):
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "current_asr_provider": current_asr_provider,
        "whisper_vulkan_health": whisper_vulkan_health,
        "cli_path_exists": cli_path_exists,
        "model_path_exists": model_path_exists,
        "fallback_model_path_exists": fallback_model_path_exists,
        "ffmpeg_available": ffmpeg_available,
        "runtime_dir_exists": runtime_dir_exists,
        "storage_free_gb": storage_free_gb,
        # 참고(외부경로 아님 검증용) — 진단 9필드 외 부가정보
        "cpu_fallback_available": cpu_fallback_available,
        "cli_path": cli_path,
        "model_path": model_path,
        "fallback_model_path": fallback_model_path,
    }
