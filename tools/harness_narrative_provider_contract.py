import os
import sys
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccut_backend.ai.boundary.narrative_provider_contract import (
    NarrativeLLMStatus, 
    StoryIntentPatch, 
    NarrativeLLMResult,
    validate_narrative_contract
)

def call_ollama_narrative(
    model: str,
    prompt: str,
    timeout: int = 45,
    base_url: str = "http://127.0.0.1:11434"
) -> NarrativeLLMResult:
    url = f"{base_url}/api/generate"
    
    # CASE 10 configuration: think:false + format:schema
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
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": schema,
        "keep_alive": "10m",
        "options": {
            "temperature": 0,
            "num_predict": 256
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
            latency = int((time.time() - start_time) * 1000)
            
            raw_res = resp_data.get("response", "")
            thinking = resp_data.get("thinking", "")
            
            if validate_narrative_contract(raw_res):
                data = json.loads(raw_res)
                return NarrativeLLMResult(
                    status=NarrativeLLMStatus.OK,
                    patch=StoryIntentPatch.from_dict(data),
                    latency_ms=latency,
                    raw_response=raw_res,
                    thinking=thinking
                )
            elif validate_narrative_contract(thinking):
                return NarrativeLLMResult(
                    status=NarrativeLLMStatus.THINKING_JSON_ONLY,
                    latency_ms=latency,
                    raw_response=raw_res,
                    thinking=thinking
                )
            else:
                return NarrativeLLMResult(
                    status=NarrativeLLMStatus.JSON_PARSE_FAILED,
                    latency_ms=latency,
                    raw_response=raw_res,
                    thinking=thinking
                )
                
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_TIMEOUT, error_message=str(e))
        return NarrativeLLMResult(status=NarrativeLLMStatus.OLLAMA_NOT_RUNNING, error_message=str(e))
    except Exception as e:
        return NarrativeLLMResult(status=NarrativeLLMStatus.MODEL_CALL_FAILED, error_message=str(e))

def run_harness():
    model = "qwen3:4b"
    inputs = [
        "더 빠르게, 사람 중심으로 편집해줘",
        "모든 영상에서 한 조각씩은 반드시 써줘",
        "감성적으로, 가족기록처럼 보이게 해줘"
    ]
    
    system_prompt = """You are a narrative editor. Return a JSON patch for narrative intent based on user message.
Format: {"patch_type": "story_intent_patch", "tone": "...", "target_length": "...", "must_keep": [], "avoid": [], "reason": "..."}"""

    results = []
    print(f"--- Narrative Provider Contract Harness (Model: {model}) ---")
    
    for i, user_msg in enumerate(inputs):
        print(f"Testing Input {i+1}: '{user_msg}'...")
        prompt = f"{system_prompt}\nUser message: '{user_msg}'"
        
        res = call_ollama_narrative(model, prompt)
        
        entry = {
            "input_text": user_msg,
            "status": res.status,
            "latency_ms": res.latency_ms,
            "model": model,
            "response_json_ok": res.status == NarrativeLLMStatus.OK,
            "contract_valid": bool(res.patch),
            "patch": vars(res.patch) if res.patch else None,
            "error_message": res.error_message
        }
        results.append(entry)
        print(f"  -> Status: {res.status}, Latency: {res.latency_ms}ms")

    # Save artifacts
    output_dir = "artifacts/narrative_provider_contract"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/harness_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "total": len(inputs),
        "ok_count": sum(1 for r in results if r["status"] == NarrativeLLMStatus.OK),
        "avg_latency_ms": sum(r["latency_ms"] for r in results) // len(inputs) if results else 0
    }
    
    with open(f"{output_dir}/harness_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
        
    print(f"\nResults saved to {output_dir}/")

if __name__ == "__main__":
    run_harness()
