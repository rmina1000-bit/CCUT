import sys
import os
import json
import time

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ccut_backend'))

from ai.boundary.narrative_provider_adapter import NarrativeProviderAdapter

def run_probe():
    adapter = NarrativeProviderAdapter()
    
    test_inputs = [
        "안녕",
        "너 누구야?",
        "대화가 좀 이상한데?",
        "앞부분이 좀 늘어져",
        "애가 웃는 장면 살리고 싶어",
        "이 영상은 기록용이야",
        "모든 영상에서 하나씩은 꼭 넣어줘",
        "아니 그건 아니고 좀 더 감성적으로",
        "이대로 해",
        "그냥 알아서 잘 해봐"
    ]
    
    results = []
    print(f"{'Input':<30} | {'Intent':<20} | {'Patch?':<6} | {'Latency':<7}")
    print("-" * 75)
    
    for text in test_inputs:
        start_time = time.time()
        res = adapter.get_free_conversation(text)
        latency = int((time.time() - start_time) * 1000)
        
        intent = res.get("intent_type", "N/A")
        needs_patch = res.get("needs_story_patch", False)
        
        print(f"{text:<30} | {intent:<20} | {str(needs_patch):<6} | {latency}ms")
        
        results.append({
            "input": text,
            "response": res,
            "latency_ms": latency
        })
        
    # Save results to artifact directory if possible, or just print
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'free_conversation_probe')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'probe_results.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print(f"\nResults saved to artifacts/free_conversation_probe/probe_results.json")

if __name__ == "__main__":
    run_probe()
