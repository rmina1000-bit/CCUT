import os
import sys
import json
import urllib.request
import urllib.error
import time
import argparse
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class StabilizationResult:
    OK = "OK"
    OLLAMA_NOT_RUNNING = "OLLAMA_NOT_RUNNING"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_CALL_TIMEOUT = "MODEL_CALL_TIMEOUT"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
    CONTRACT_INVALID = "CONTRACT_INVALID"

def call_ollama_stabilization(
    model: str, 
    prompt: str, 
    timeout: int, 
    num_predict: int, 
    keep_alive: str = "5m", 
    base_url: str = "http://127.0.0.1:11434"
) -> Dict[str, Any]:
    url = f"{base_url}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": keep_alive,
        "options": {
            "num_predict": num_predict
        }
    }
    
    start_time = time.time()
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode(), 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_data = json.loads(response.read().decode())
            latency = (time.time() - start_time) * 1000
            return {
                "status": StabilizationResult.OK,
                "latency_ms": int(latency),
                "response": resp_data.get("response"),
                "raw": resp_data
            }
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError) or "timed out" in str(e).lower():
            return {"status": StabilizationResult.MODEL_CALL_TIMEOUT, "error": str(e)}
        return {"status": StabilizationResult.OLLAMA_NOT_RUNNING, "error": str(e)}
    except Exception as e:
        if "timed out" in str(e).lower():
            return {"status": StabilizationResult.MODEL_CALL_TIMEOUT, "error": str(e)}
        return {"status": StabilizationResult.MODEL_CALL_FAILED, "error": str(e)}

def validate_json_contract(response_text: str) -> str:
    if not response_text:
        return StabilizationResult.JSON_PARSE_FAILED
    try:
        data = json.loads(response_text)
        required_keys = ["patch_type", "tone", "target_length", "must_keep", "avoid", "reason"]
        if all(k in data for k in required_keys):
            return StabilizationResult.OK
        return StabilizationResult.CONTRACT_INVALID
    except:
        return StabilizationResult.JSON_PARSE_FAILED

def check_ollama_model_exists(model: str, base_url: str = "http://127.0.0.1:11434") -> bool:
    """Check if the model exists in Ollama by calling /api/tags."""
    url = f"{base_url}/api/tags"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            # Some models might have :latest tag implicitly
            if model in models:
                return True
            if ":" not in model and f"{model}:latest" in models:
                return True
            return False
    except:
        return False

def run_stabilization_probe():
    parser = argparse.ArgumentParser(description="Ollama Stabilization Probe")
    parser.add_argument("--model", type=str, default="qwen3:0.6b", help="Model name to probe")
    parser.add_argument("--output-dir", type=str, default="artifacts/ollama_timeout_stabilization", help="Directory to save results")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:11434", help="Ollama API base URL")
    args = parser.parse_args()

    model = args.model
    output_dir = args.output_dir
    base_url = args.base_url
    
    print(f"--- Ollama Timeout Stabilization Probe (Model: {model}) ---")

    # [STEP 10-I.5.28-E9-R2-R10-E] Pre-check: Does the model exist?
    if not check_ollama_model_exists(model, base_url):
        # Try a quick test call to see if it's OLLAMA_NOT_RUNNING or just MODEL_NOT_FOUND
        try:
            urllib.request.urlopen(base_url, timeout=2)
            print(f"ERROR: Model '{model}' not found in Ollama tags.")
            print(f"Please run 'ollama pull {model}' first.")
            # We still proceed to create a "not found" result artifact if possible
        except:
            print("ERROR: Ollama server is not running or unreachable.")
            return

    prompt = """Return a JSON patch for narrative intent. 
User message: '더 빠르게 해줘'
Format: {"patch_type": "story_intent_patch", "tone": "fast", "target_length": "short", "must_keep": [], "avoid": [], "reason": "short test"}"""
    
    # Adjust timeouts based on model weight (heuristics)
    if "4b" in model.lower():
        cases = [
            {"id": "CASE 1", "timeout": 20, "num_predict": 64, "keep_alive": "5m"},
            {"id": "CASE 2", "timeout": 30, "num_predict": 64, "keep_alive": "5m"},
            {"id": "CASE 3", "timeout": 45, "num_predict": 128, "keep_alive": "5m"},
            {"id": "CASE 4", "timeout": 60, "num_predict": 128, "keep_alive": "10m"},
        ]
    else:
        cases = [
            {"id": "CASE 1", "timeout": 10, "num_predict": 64, "keep_alive": "5m"},
            {"id": "CASE 2", "timeout": 20, "num_predict": 64, "keep_alive": "5m"},
            {"id": "CASE 3", "timeout": 30, "num_predict": 128, "keep_alive": "5m"},
            {"id": "CASE 4", "timeout": 30, "num_predict": 128, "keep_alive": "5m"},
        ]
    
    results = []
    
    for case in cases:
        print(f"Running {case['id']} (timeout={case['timeout']}s, num_predict={case['num_predict']})...")
        res = call_ollama_stabilization(
            model=model,
            prompt=prompt,
            timeout=case['timeout'],
            num_predict=case['num_predict'],
            keep_alive=case['keep_alive'],
            base_url=base_url
        )
        
        # If model is not found, Ollama returns 404 which might trigger MODEL_CALL_FAILED
        # or we might have caught it in the pre-check.
        
        case_result = {
            "case_id": case['id'],
            "params": case,
            "result": res
        }
        
        if res["status"] == StabilizationResult.OK:
            contract_status = validate_json_contract(res["response"])
            case_result["contract_validation"] = contract_status
            print(f"  -> Latency: {res['latency_ms']}ms, Contract: {contract_status}")
        else:
            print(f"  -> Failed: {res['status']}")
            
        results.append(case_result)

    # Save results
    os.makedirs(output_dir, exist_ok=True)
    
    model_safe_name = model.replace(":", "_")
    with open(f"{output_dir}/{model_safe_name}_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    summary = {
        "model": model,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "success_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.OK),
        "timeout_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.MODEL_CALL_TIMEOUT),
        "model_not_found": any("not found" in str(r["result"].get("error", "")).lower() for r in results)
    }
    
    with open(f"{output_dir}/{model_safe_name}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    
    print(f"\nResults saved to {output_dir}/")

if __name__ == "__main__":
    run_stabilization_probe()


