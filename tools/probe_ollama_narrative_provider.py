import os
import sys
import json
import time

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccut_backend.ai.boundary.ollama_provider_probe import (
    check_ollama_server,
    list_ollama_models,
    call_ollama_generate_if_available,
    OllamaProbeResult
)

def run_probe():
    base_url = "http://127.0.0.1:11434"
    summary = {
        "ollama_running": False,
        "models_found": [],
        "selected_model": None,
        "probe_status": OllamaProbeResult.OLLAMA_NOT_RUNNING,
        "story_intent_patch_candidate": None,
        "latency_ms": 0,
        "error": None,
        "note": "Initial state"
    }
    
    print("--- Ollama Narrative Provider Probe ---")
    
    # 1. Server Check
    if not check_ollama_server(base_url):
        summary["note"] = "Ollama server is not running on http://127.0.0.1:11434"
        print(json.dumps(summary, indent=4))
        return
    
    summary["ollama_running"] = True
    
    # 2. Model List
    models = list_ollama_models(base_url)
    summary["models_found"] = models
    
    if not models:
        summary["probe_status"] = OllamaProbeResult.NO_MODEL_AVAILABLE
        summary["note"] = "Server is running but no models are installed. Please run 'ollama pull qwen3-instruct' or similar."
        print(json.dumps(summary, indent=4))
        return
    
    # 3. Model Selection (Pick first one for probe)
    # Prefer qwen or mistral if available
    selected = next((m for m in models if "qwen" in m or "mistral" in m), models[0])
    summary["selected_model"] = selected
    
    # 4. Limited Call (only if requested, but for probe we try 1 input)
    test_input = "더 빠르게 해줘"
    print(f"Testing model '{selected}' with input: '{test_input}'...")
    
    start_time = time.time()
    response = call_ollama_generate_if_available(selected, test_input, base_url)
    summary["latency_ms"] = int((time.time() - start_time) * 1000)
    
    if "error" in response:
        summary["probe_status"] = OllamaProbeResult.MODEL_CALL_FAILED
        summary["error"] = response["error"]
    else:
        summary["probe_status"] = OllamaProbeResult.PROBE_PASS
        summary["story_intent_patch_candidate"] = response.get("response")
        
    print(json.dumps(summary, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    run_probe()
