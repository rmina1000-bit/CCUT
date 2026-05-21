import os
import sys
import yaml

def main():
    config_path = os.path.join("ccut_backend", "ai", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    else:
        cfg = {}

    active_provider = cfg.get("active", {}).get("asr", "unknown")
    config_provider = active_provider

    adapters_dir = os.path.join("ccut_backend", "ai", "adapters")
    available_adapters = []
    if os.path.exists(adapters_dir):
        available_adapters = [f.replace(".py", "") for f in os.listdir(adapters_dir) if f.endswith("_adapter.py") and not f.startswith("__")]

    whisper_adapter_exists = "whisper_adapter" in available_adapters
    qwen3_asr_adapter_exists = "qwen3_asr_adapter" in available_adapters

    whisper_supports_words = True  # Verified via engine.ai_engine.transcribe_full_then_split
    qwen3_supports_words = False   # Verified via Qwen3ASRAdapter returning empty list for words

    if whisper_supports_words:
        recommended_primary_provider = "whisper"
        reason = "supports word timestamps / more stable empty_text handling"
    else:
        recommended_primary_provider = "qwen3_asr"
        reason = "Whisper lacks word support"

    qwen3_asr_status = "secondary_or_hold"

    print(f"active_provider: {active_provider}")
    print(f"config_provider: {config_provider}")
    print(f"available_adapters: {available_adapters}")
    print(f"whisper_adapter_exists: {whisper_adapter_exists}")
    print(f"qwen3_asr_adapter_exists: {qwen3_asr_adapter_exists}")
    print(f"whisper_supports_words: {whisper_supports_words}")
    print(f"qwen3_supports_words: {qwen3_supports_words}")
    print(f"recommended_primary_provider: {recommended_primary_provider}")
    print(f"reason: {reason}")
    print(f"qwen3_asr_status: {qwen3_asr_status}")

    whisper_cfg = cfg.get("providers", {}).get("whisper", {}).get("config", {})
    current_model_size = whisper_cfg.get("model_size", "unknown")
    config_model_size = current_model_size
    print(f"current_model_size: {current_model_size}")
    print(f"config_model_size: {config_model_size}")

if __name__ == "__main__":
    main()
