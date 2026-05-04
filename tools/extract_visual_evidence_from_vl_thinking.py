import json
import os
import re
import time

def extract_evidence(thinking_text):
    """
    [STEP 10-J-R1.3] Rule-based Visual Evidence Extractor
    Extracts structured evidence from Qwen-VL's 'thinking' trace.
    """
    # Default schema structure
    evidence = {
        "visual_summary": "",
        "scene_type": "unknown",
        "main_subjects": [],
        "visible_people_count": 0,
        "face_visibility": "unknown",
        "human_presence_score": 0.0,
        "emotion": "neutral",
        "action_level": "none",
        "camera_quality": "good",
        "edit_value": 0.5,
        "must_keep_candidates": [],
        "avoid_candidates": [],
        "cognitive_role_hint": "context",
        "reason": "Rule-based extraction from thinking trace text",
        "source_channel": "thinking",
        "production_usable": False,
        "diagnostic_visual_seen": True
    }

    # Normalize text for keyword matching
    text = thinking_text.lower()
    
    # 1. Scene Type Detection
    if any(k in text for k in ["restaurant", "dining place", "casual dining", "eatery"]):
        evidence["scene_type"] = "restaurant"
    elif any(k in text for k in ["food", "eating", "bowl", "kimchi", "dishes", "meal"]):
        evidence["scene_type"] = "food"
    elif any(k in text for k in ["landscape", "mountain", "sea", "outside"]):
        evidence["scene_type"] = "landscape"
    elif any(k in text for k in ["travel", "airport", "suitcase", "tourist"]):
        evidence["scene_type"] = "travel"
    
    # 2. Subject Detection
    subjects = []
    if any(k in text for k in ["person", "elderly", "man", "woman", "human"]): 
        subjects.append("person")
    if "kimchi" in text: subjects.append("kimchi")
    if "bowl" in text: subjects.append("bowl")
    if "table" in text: subjects.append("table")
    if any(k in text for k in ["spoon", "chopsticks", "utensil"]): 
        subjects.append("utensils")
    if "side dish" in text: subjects.append("side dishes")
    evidence["main_subjects"] = list(set(subjects))

    # 3. Human Presence
    if "person" in subjects:
        evidence["visible_people_count"] = 1
        evidence["human_presence_score"] = 0.85
        if "elderly" in text:
             evidence["main_subjects"].append("elderly person")
    
    # 4. Action Level
    if any(k in text for k in ["eating", "using a spoon", "sitting"]):
        evidence["action_level"] = "medium"
        evidence["cognitive_role_hint"] = "context"
    
    # 5. Visual Summary (English to Korean Heuristics)
    if "elderly person" in text and "eating" in text and "restaurant" in text:
        evidence["visual_summary"] = "식당에서 한 어르신이 식사를 하고 있는 장면"
    elif "kimchi" in text and "table" in text:
        evidence["visual_summary"] = "테이블 위에 김치와 여러 반찬이 놓여 있는 식사 장면"
    else:
        # Fallback to a truncated snippet if no high-confidence heuristic matches
        evidence["visual_summary"] = "이미지 시각적 분석: " + thinking_text.replace("<think>", "").strip()[:60] + "..."

    # 6. Quality & Value
    if evidence["scene_type"] != "unknown":
        evidence["edit_value"] = 0.75
    
    # 7. Emotion
    if "warm" in text or "casual" in text:
        evidence["emotion"] = "warm"
    
    return evidence

def run_extraction():
    # Attempt to locate source JSON
    source_path = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_smoke_ladder', 'smoke_ladder_summary.json')
    if not os.path.exists(source_path):
        print(f"Error: Source file not found at {source_path}")
        return

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
    except Exception as e:
        print(f"Error reading summary: {e}")
        return

    # Select the first available thinking text (preferring generate_no_think if it exists)
    thinking_text = ""
    target_modes = ["generate_no_think", "chat_no_think", "generate", "chat"]
    
    results_map = {r["mode"]: r for r in summary_data.get("results", [])}
    for mode in target_modes:
        if mode in results_map and results_map[mode].get("thinking"):
            thinking_text = results_map[mode]["thinking"]
            print(f"Selected thinking source from mode: {mode}")
            break
            
    if not thinking_text:
        print("Status: NO_THINKING_TEXT. Aborting extraction.")
        return

    # Extract
    evidence = extract_evidence(thinking_text)
    
    # Save Artifacts
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_thinking_evidence')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'thinking_evidence_result.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
        
    summary_out = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "OK_DIAGNOSTIC_EVIDENCE",
        "image": summary_data.get("image"),
        "source_channel": "thinking",
        "num_predict": summary_data.get("num_predict"),
        "extracted_fields": list(evidence.keys())
    }
    
    with open(os.path.join(output_dir, 'thinking_evidence_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary_out, f, indent=2, ensure_ascii=False)

    print(f"\nExtraction complete. Visual Summary: {evidence['visual_summary']}")
    print(f"Results saved to artifacts/qwen_vl_thinking_evidence/")

if __name__ == "__main__":
    run_extraction()
