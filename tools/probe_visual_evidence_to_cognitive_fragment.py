import json
import os
import time

def generate_fragment(evidence, filename):
    """
    [STEP 10-J-R3] Visual Evidence to Cognitive Fragment Mapper
    Converts extracted visual metadata into a CCUT Cognitive Fragment candidate.
    """
    fragment_id = os.path.splitext(filename)[0]
    
    # Semantic tags: Merge subjects, scene type, and action level
    tags = list(set(evidence.get("main_subjects", []) + [evidence.get("scene_type")] + [evidence.get("action_level")]))
    tags = [t for t in tags if t and t != "unknown" and t != "none"]

    fragment = {
        "fragment_id": fragment_id,
        "cognitive_summary": evidence.get("visual_summary", ""),
        "semantic_tags": tags,
        "edit_role": evidence.get("cognitive_role_hint", "context"),
        "edit_value": evidence.get("edit_value", 0.0),
        "human_presence_score": evidence.get("human_presence_score", 0.0),
        "visual_scene_type": evidence.get("scene_type", "unknown"),
        "must_keep_reason": "Clear human activity and relevant scene objects detected visually." if evidence.get("human_presence_score", 0) > 0.7 else "",
        "avoid_reason": "Low visual quality or irrelevant subject." if evidence.get("camera_quality") in ["blurry", "dark"] else "",
        "evidence_refs": {
            "visual_evidence": "artifacts/qwen_vl_thinking_evidence/thinking_evidence_result.json",
            "source_channel": evidence.get("source_channel", "thinking")
        },
        "evidence_grade": "diagnostic_visual",
        "production_usable": False
    }
    return fragment

def main():
    # Source paths
    evidence_path = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_thinking_evidence', 'thinking_evidence_result.json')
    summary_path = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_thinking_evidence', 'thinking_evidence_summary.json')
    
    if not os.path.exists(evidence_path):
        print(f"Status: NO_VISUAL_EVIDENCE. Aborting.")
        return

    try:
        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence = json.load(f)
    except Exception as e:
        print(f"Status: INVALID_VISUAL_EVIDENCE. Error: {e}")
        return
    
    # Identify source image filename
    filename = "VF100_SRC_UNKNOWN.jpg"
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
                filename = summary.get("image", filename)
        except:
            pass

    # Map to Cognitive Fragment
    fragment = generate_fragment(evidence, filename)
    
    # Save Artifacts
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_cognitive_fragment_probe')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'cognitive_fragment_result.json'), 'w', encoding='utf-8') as f:
        json.dump(fragment, f, indent=2, ensure_ascii=False)
        
    summary_out = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "OK_COGNITIVE_FRAGMENT_CANDIDATE",
        "fragment_id": fragment["fragment_id"],
        "edit_role": fragment["edit_role"],
        "edit_value": fragment["edit_value"],
        "evidence_grade": fragment["evidence_grade"]
    }
    
    with open(os.path.join(output_dir, 'cognitive_fragment_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary_out, f, indent=2, ensure_ascii=False)

    print(f"\nCognitive Fragment candidate generated for {fragment['fragment_id']}.")
    print(f"Summary: {fragment['cognitive_summary']}")
    print(f"Results saved to artifacts/qwen_vl_cognitive_fragment_probe/")

if __name__ == "__main__":
    main()
