import os
import sys
import json
from dataclasses import asdict

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ccut_backend.ai.boundary.mock_narrative_llm import build_mock_narrative_response

def simulate():
    test_inputs = [
        "더 빠르게 해줘",
        "사람 표정이 잘 보이게 해줘",
        "웃긴 장면 위주로 해줘",
        "너무 길지 않게 짧게",
        "여러 영상 골고루 섞어줘"
    ]
    
    print("--- Narrative LLM Mock Simulation ---")
    
    for msg in test_inputs:
        print(f"\nUser Input: {msg}")
        result = build_mock_narrative_response(msg)
        
        # Convert dataclass to dict for JSON output
        result_dict = asdict(result)
        print(json.dumps(result_dict, indent=2, ensure_ascii=False))
        
        # Verification
        assert result.schema_valid is True
        assert result.provider == "mock_narrative_llm"
        print("Status: PASS (schema_valid=True, provider=mock_narrative_llm)")

if __name__ == "__main__":
    simulate()
