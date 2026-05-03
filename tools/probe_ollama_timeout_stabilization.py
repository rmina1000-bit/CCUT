import os
import sys
import json
import urllib.request
import urllib.error
import time
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

def run_stabilization_probe():
    model = "qwen3:0.6b"
    prompt = """Return a JSON patch for narrative intent. 
User message: '더 빠르게 해줘'
Format: {"patch_type": "story_intent_patch", "tone": "fast", "target_length": "short", "must_keep": [], "avoid": [], "reason": "short test"}"""
    
    cases = [
        {"id": "CASE 1", "timeout": 10, "num_predict": 64, "keep_alive": "5m"},
        {"id": "CASE 2", "timeout": 20, "num_predict": 64, "keep_alive": "5m"},
        {"id": "CASE 3", "timeout": 30, "num_predict": 128, "keep_alive": "5m"},
        {"id": "CASE 4", "timeout": 30, "num_predict": 128, "keep_alive": "5m"},
    ]
    
    results = []
    print(f"--- Ollama Timeout Stabilization Probe (Model: {model}) ---")
    
    for case in cases:
        print(f"Running {case['id']} (timeout={case['timeout']}s, num_predict={case['num_predict']})...")
        res = call_ollama_stabilization(
            model=model,
            prompt=prompt,
            timeout=case['timeout'],
            num_predict=case['num_predict'],
            keep_alive=case['keep_alive']
        )
        
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
    artifact_dir = "artifacts/ollama_timeout_stabilization"
    os.makedirs(artifact_dir, exist_ok=True)
    
    with open(f"{artifact_dir}/ollama_timeout_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    summary = {
        "model": model,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "success_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.OK),
        "timeout_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.MODEL_CALL_TIMEOUT)
    }
    
    with open(f"{artifact_dir}/ollama_timeout_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    
    print(f"\nResults saved to {artifact_dir}/")

if __name__ == "__main__":
    run_stabilization_probe()
