import os
import sys
import json
import time

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccut_backend.ai.boundary.narrative_provider_adapter import NarrativeProviderAdapter
from ccut_backend.ai.boundary.narrative_provider_contract import NarrativeLLMStatus

def run_dryrun():
    adapter = NarrativeProviderAdapter(model="qwen3:4b")
    
    test_inputs = [
        "더 빠르게, 사람 중심으로 편집해줘",
        "모든 영상에서 한 조각씩은 반드시 써줘",
        "감성적으로, 가족기록처럼 보이게 해줘",
        "너무 길면 안 되고 쇼츠처럼 빠르게 해줘",
        "말이 없는 장면은 줄이고 표정이 잘 보이는 장면을 살려줘"
    ]

    print(f"--- Narrative Provider Adapter Dry Run (Model: {adapter.model}) ---")
    
    results = []
    for i, msg in enumerate(test_inputs):
        print(f"[{i+1}/{len(test_inputs)}] Processing: '{msg}'...")
        res = adapter.get_story_intent_patch(msg)
        
        entry = {
            "input": msg,
            "status": res.status,
            "latency_ms": res.latency_ms,
            "patch": vars(res.patch) if res.patch else None,
            "response_json_ok": res.status == NarrativeLLMStatus.OK,
            "contract_valid": bool(res.patch),
            "error": res.error_message
        }
        results.append(entry)
        print(f"    -> Status: {res.status}, Latency: {res.latency_ms}ms")

    # Save artifacts
    output_dir = "artifacts/narrative_provider_adapter_dryrun"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/dryrun_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": adapter.model,
        "total": len(test_inputs),
        "success_rate": sum(1 for r in results if r["status"] == NarrativeLLMStatus.OK) / len(test_inputs),
        "avg_latency_ms": sum(r["latency_ms"] for r in results) // len(test_inputs) if results else 0
    }
    
    with open(f"{output_dir}/dryrun_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
        
    print(f"\nDry Run results saved to {output_dir}/")

if __name__ == "__main__":
    run_dryrun()
