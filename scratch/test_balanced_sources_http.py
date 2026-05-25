import json
import requests

def run_test(coverage_value=None, instruction_value=None):
    payload = {
        "project_id": "test_project_123",
        "source_ids": ["SRC_616AEFBA", "SRC_AA6C87D2", "SRC_B1A26714"],
        "target_length": 60.0,
        "user_intent": {
            "coverage": coverage_value,
            "instruction_text": instruction_value,
            "tone": "energetic",
            "target_length": 60.0
        }
    }
    print(f"\n--- Running HTTP Test (coverage={coverage_value}, instruction={instruction_value}) ---")
    try:
        response = requests.post("http://127.0.0.1:8000/proposals/project", json=payload, timeout=90)
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            return None
        return response.json()
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

# 1. Base (No balanced sources requested)
res_base = run_test(coverage_value="default", instruction_value="일반 편집")
if res_base:
    proposals = res_base.get("proposals", [])
    for p in proposals:
        mode = p.get("mode")
        seq = p.get("sequence", [])
        dist = p.get("source_distribution", {})
        print(f"[{mode} Mode Base] Sequence length: {len(seq)}, Duration: {p.get('duration')}s")
        print(f"[{mode} Mode Base] Source distribution: {json.dumps(dist)}")

# 2. Balanced (coverage == 'balanced_sources')
res_balanced = run_test(coverage_value="balanced_sources", instruction_value="아무거나")
if res_balanced:
    proposals = res_balanced.get("proposals", [])
    for p in proposals:
        mode = p.get("mode")
        seq = p.get("sequence", [])
        dist = p.get("source_distribution", {})
        print(f"[{mode} Mode Balanced] Sequence length: {len(seq)}, Duration: {p.get('duration')}s")
        print(f"[{mode} Mode Balanced] Source distribution: {json.dumps(dist)}")

# 3. Fallback (keyword match in instruction_text)
res_fallback = run_test(coverage_value="default", instruction_value="여러 영상 골고루 섞어서 다시 제안해줘")
if res_fallback:
    proposals = res_fallback.get("proposals", [])
    for p in proposals:
        mode = p.get("mode")
        seq = p.get("sequence", [])
        dist = p.get("source_distribution", {})
        print(f"[{mode} Mode Fallback] Sequence length: {len(seq)}, Duration: {p.get('duration')}s")
        print(f"[{mode} Mode Fallback] Source distribution: {json.dumps(dist)}")
