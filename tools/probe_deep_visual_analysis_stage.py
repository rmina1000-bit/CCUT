import os
import sys
import json
import argparse
import time
import hashlib

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ccut_backend'))

from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker

def get_cache_key(image_path, model, resize_max):
    """Generates a unique cache key based on file content and parameters."""
    try:
        with open(image_path, "rb") as f:
            content = f.read()
            f_hash = hashlib.md5(content).hexdigest()
        return f"{model.replace(':', '_')}_{resize_max}_{f_hash}"
    except:
        return f"unknown_{time.time()}"

def run_deep_stage_probe(args):
    """
    [STEP 10-K] Deep Visual Analysis Stage Probe
    Simulates Stage 5 analysis of candidate fragments with non-blocking logic and caching.
    """
    worker = QwenVLVisualWorker()
    
    thumb_dir = os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'thumbnails')
    cache_dir = os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'cache', 'visual_evidence')
    
    # Ensure directories exist
    os.makedirs(cache_dir, exist_ok=True)

    if not os.path.exists(thumb_dir):
        print(f"Error: Thumbnail directory not found at {thumb_dir}")
        return

    all_thumbs = sorted([f for f in os.listdir(thumb_dir) if f.endswith(('.jpg', '.png'))])
    if not all_thumbs:
        print("No thumbnails found for analysis.")
        return

    # Simulate Candidate Selection (e.g., from A/B Proposals)
    candidates = all_thumbs[:args.max_candidates]
    
    print(f"Deep Visual Analysis Stage: {len(candidates)} candidates selected for refinement.", flush=True)

    results = []
    stats = {
        "stage": "deep_visual_analysis",
        "model": "qwen3-vl:4b",
        "resize_max": args.resize_max,
        "timeout_sec": args.timeout_sec,
        "total_candidates": len(candidates),
        "ok_count": 0,
        "failed_count": 0,
        "cache_hit_count": 0,
        "cache_miss_count": 0,
        "total_elapsed_ms": 0,
        "avg_elapsed_ms": 0,
        "fast_path_blocked": False, # Strategy constraint
        "cognitive_fragment_refined_count": 0
    }

    start_time_total = time.time()

    for thumb_name in candidates:
        image_path = os.path.join(thumb_dir, thumb_name)
        cache_key = get_cache_key(image_path, stats["model"], args.resize_max)
        cache_path = os.path.join(cache_dir, f"{cache_key}.json")
        
        is_cache_hit = False
        
        # 1. Cache Lookup (Mandatory Policy)
        if os.path.exists(cache_path):
            print(f"CACHE HIT: {thumb_name} (Loading saved evidence)", flush=True)
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    res = json.load(f)
                is_cache_hit = True
                stats["cache_hit_count"] += 1
            except:
                print(f"CACHE CORRUPTED: {thumb_name}. Re-analyzing...", flush=True)
                res = worker.analyze_image(image_path, resize_max=args.resize_max, timeout_sec=args.timeout_sec)
                stats["cache_miss_count"] += 1
        else:
            # 2. Worker Call (Cache Miss)
            print(f"CACHE MISS: {thumb_name} (Starting deep inference...)", flush=True)
            res = worker.analyze_image(image_path, resize_max=args.resize_max, timeout_sec=args.timeout_sec)
            stats["cache_miss_count"] += 1
            
            # Save to Cache on success
            if res["status"] in ["OK", "OK_TRACE_VISUAL"]:
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(res, f, indent=2, ensure_ascii=False)
                except:
                    pass

        status = res.get("status")
        latency = res.get("latency_ms", 0)
        diag = res.get("diag", {})
        actual_elapsed = latency if latency > 0 else diag.get("elapsed_ms", 0)
        
        # Don't add latency for cache hits to total inference time stats if needed, 
        # but here we track total stage time.
        stats["total_elapsed_ms"] += actual_elapsed
        
        if status in ["OK", "OK_TRACE_VISUAL"]:
            stats["ok_count"] += 1
            stats["cognitive_fragment_refined_count"] += 1
            evidence = res.get("evidence", {})
            
            # Form Visual Evidence v0 for result
            results.append({
                "fragment_id": os.path.splitext(thumb_name)[0],
                "visual_summary": evidence.get("visual_summary"),
                "scene_type": evidence.get("scene_type"),
                "semantic_tags": evidence.get("main_subjects", []),
                "evidence_grade": res.get("evidence_grade", "trace_visual_candidate"),
                "cache_hit": is_cache_hit,
                "latency_ms": actual_elapsed
            })
        else:
            stats["failed_count"] += 1
            print(f"WARNING: Stage 5 analysis failed for {thumb_name} ({status})", flush=True)

    if stats["total_candidates"] > 0:
        stats["avg_elapsed_ms"] = stats["total_elapsed_ms"] / stats["total_candidates"]

    # Save Artifacts
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'deep_visual_analysis_stage')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'deep_visual_result.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    with open(os.path.join(output_dir, 'deep_visual_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nDeep Analysis Stage Probe Complete.")
    print(f"Success: {stats['ok_count']}/{stats['total_candidates']} | Cache Hits: {stats['cache_hit_count']}")
    print(f"Total Time: {stats['total_elapsed_ms']}ms | Fast Path Blocked: {stats['fast_path_blocked']}")
    print(f"Results saved to artifacts/deep_visual_analysis_stage/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--resize-max", type=int, default=384)
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()
    
    run_deep_stage_probe(args)
