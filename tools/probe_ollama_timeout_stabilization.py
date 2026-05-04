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
    THINKING_JSON_ONLY = "THINKING_JSON_ONLY"

def call_ollama_stabilization(
    model: str, 
    prompt: str, 
    timeout: int, 
    num_predict: int, 
    keep_alive: str = "5m", 
    format: Any = None,
    think: bool = None,
    temperature: float = None,
    base_url: str = "http://127.0.0.1:11434"
) -> Dict[str, Any]:
    url = f"{base_url}/api/generate"
    
    options = {
        "num_predict": num_predict
    }
    if temperature is not None:
        options["temperature"] = temperature

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": options
    }
    if format:
        payload["format"] = format
    if think is not None:
        payload["think"] = think
    
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
                "response": resp_data.get("response", ""),
                "thinking": resp_data.get("thinking", ""),
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

def validate_json_contract(response_text: str) -> bool:
    if not response_text:
        return False
    # Handle potential extra characters around JSON if format was not strictly json
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
        
    try:
        data = json.loads(text)
        required_keys = ["patch_type", "tone", "target_length", "must_keep", "avoid", "reason"]
        return all(k in data for k in required_keys)
    except:
        return False

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
    parser.add_argument("--r1-json-repair", action="store_true", help="Run R1 repair CASEs")
    parser.add_argument("--r2-think-false", action="store_true", help="Run R2 repair CASEs (think:false)")
    args = parser.parse_args()

    model = args.model
    output_dir = args.output_dir
    base_url = args.base_url
    
    print(f"--- Ollama Timeout Stabilization Probe (Model: {model}) ---")

    if not check_ollama_model_exists(model, base_url):
        try:
            urllib.request.urlopen(base_url, timeout=2)
            print(f"ERROR: Model '{model}' not found.")
            return
        except:
            print("ERROR: Ollama server not running.")
            return

    default_prompt = """Return a JSON patch for narrative intent. 
User message: '더 빠르게 해줘'
Format: {"patch_type": "story_intent_patch", "tone": "fast", "target_length": "short", "must_keep": [], "avoid": [], "reason": "short test"}"""
    
    cases = []
    if args.r2_think_false:
        schema = {
            "type": "object",
            "properties": {
                "patch_type": { "type": "string" },
                "tone": { "type": "string" },
                "target_length": { "type": "string" },
                "must_keep": { "type": "array", "items": { "type": "string" } },
                "avoid": { "type": "array", "items": { "type": "string" } },
                "reason": { "type": "string" }
            },
            "required": ["patch_type", "tone", "target_length", "must_keep", "avoid", "reason"]
        }
        cases = [
            {"id": "CASE 8", "timeout": 45, "num_predict": 128, "keep_alive": "10m", 
             "think": False, "format": "json", "temperature": 0},
            {"id": "CASE 9", "timeout": 60, "num_predict": 256, "keep_alive": "10m", 
             "think": False, "format": "json", "temperature": 0},
            {"id": "CASE 10", "timeout": 60, "num_predict": 256, "keep_alive": "10m", 
             "think": False, "format": schema, "temperature": 0},
        ]
    elif args.r1_json_repair:
        cases = [
            {"id": "CASE 5", "timeout": 45, "num_predict": 128, "keep_alive": "10m", 
             "prompt": default_prompt + "\nDo not think. Return only final JSON."},
            {"id": "CASE 6", "timeout": 45, "num_predict": 128, "keep_alive": "10m", 
             "prompt": "/no_think\n" + default_prompt},
            {"id": "CASE 7", "timeout": 45, "num_predict": 128, "keep_alive": "10m", 
             "prompt": default_prompt, "format": "json"},
        ]
    else:
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
        print(f"Running {case['id']}...")
        res = call_ollama_stabilization(
            model=model,
            prompt=case.get("prompt", default_prompt),
            timeout=case['timeout'],
            num_predict=case['num_predict'],
            keep_alive=case['keep_alive'],
            format=case.get("format"),
            think=case.get("think"),
            temperature=case.get("temperature"),
            base_url=base_url
        )
        
        diag = {
            "response_empty": not res.get("response"),
            "thinking_present": bool(res.get("thinking")),
            "response_json_ok": validate_json_contract(res.get("response")),
            "thinking_json_ok": validate_json_contract(res.get("thinking")),
        }
        
        status = res["status"]
        if status == StabilizationResult.OK:
            if diag["response_json_ok"]:
                status = StabilizationResult.OK
            elif diag["thinking_json_ok"]:
                status = StabilizationResult.THINKING_JSON_ONLY
            else:
                status = StabilizationResult.JSON_PARSE_FAILED

        case_result = {
            "case_id": case['id'],
            "params": case,
            "result": {**res, "status": status},
            "diagnostics": diag
        }
        print(f"  -> Status: {status}, Latency: {res.get('latency_ms', 0)}ms")
        results.append(case_result)

    os.makedirs(output_dir, exist_ok=True)
    if args.r2_think_false:
        suffix = "_r2"
    elif args.r1_json_repair:
        suffix = "_r1"
    else:
        suffix = ""
    
    model_safe = model.replace(":", "_")
    
    with open(f"{output_dir}/{model_safe}{suffix}_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    summary = {
        "model": model,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "success_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.OK),
        "thinking_only_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.THINKING_JSON_ONLY),
        "failure_count": sum(1 for r in results if r["result"]["status"] == StabilizationResult.JSON_PARSE_FAILED)
    }
    
    with open(f"{output_dir}/{model_safe}{suffix}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
    
    print(f"\nResults saved to {output_dir}/")

if __name__ == "__main__":
    run_stabilization_probe()
