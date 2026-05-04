import os
import sys
import json
import argparse
import time

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ccut_backend'))

from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker

def run_batch_probe(args):
    worker = QwenVLVisualWorker()
    
    thumb_dir = os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'thumbnails')
    if not os.path.exists(thumb_dir):
        print(f"Error: Thumbnail directory not found at {thumb_dir}", flush=True)
        return

    all_thumbs = sorted([f for f in os.listdir(thumb_dir) if f.endswith(('.jpg', '.png'))])
    if not all_thumbs:
        print("No images found.", flush=True)
        return

    # Filter candidates
    if args.image_name:
        candidates = [args.image_name] if args.image_name in all_thumbs else []
    else:
        candidates = all_thumbs[:args.max_images]

    print(f"Batch validation: {len(candidates)} images (Trace-based Policy, Resize={args.resize_max})", flush=True)

    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_trace_batch')
    os.makedirs(output_dir, exist_ok=True)
    
    result_path = os.path.join(output_dir, 'trace_batch_result.json')
    existing_results = []
    if os.path.exists(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
        except:
            pass

    existing_map = {r["image_name"]: r for r in existing_results if r["status"] in ["OK", "OK_TRACE_VISUAL"]}

    results = [] if not args.skip_existing else existing_results
    stats = {
        "total": 0,
        "ok_count": 0,
        "ok_trace_visual_count": 0, # Legacy support
        "failed_count": 0,
        "timeout_count": 0,
        "model_call_failed_count": 0,
        "total_elapsed_ms": 0,
        "total_latency_ms": 0, # Legacy support
        "avg_elapsed_ms": 0,
        "max_elapsed_ms": 0,
        "scene_type_distribution": {},
        "human_presence_avg": 0,
        "cognitive_fragment_candidate_count": 0
    }

    print(f"{'Image':<30} | {'Status':<18} | {'Latency':<7} | {'Scene'}", flush=True)
    print("-" * 80, flush=True)

    human_presence_total = 0
    for thumb_name in candidates:
        if args.skip_existing and thumb_name in existing_map:
            # We'll re-calculate stats for skipped items to ensure summary is accurate
            res_item = existing_map[thumb_name]
            actual_latency = res_item.get("latency_ms", 0)
            diag_elapsed = res_item.get("diag", {}).get("elapsed_ms", 0)
            actual_elapsed = actual_latency if actual_latency > 0 else diag_elapsed
            
            stats["total"] += 1
            stats["ok_count"] += 1
            stats["ok_trace_visual_count"] += 1
            stats["total_elapsed_ms"] += actual_elapsed
            stats["total_latency_ms"] += actual_elapsed
            if actual_elapsed > stats["max_elapsed_ms"]: stats["max_elapsed_ms"] = actual_elapsed
            
            scene = res_item.get("scene_type", "unknown")
            stats["scene_type_distribution"][scene] = stats["scene_type_distribution"].get(scene, 0) + 1
            # Note: human_presence_avg needs raw evidence or we fallback to 0 for skipped
            stats["cognitive_fragment_candidate_count"] += 1
            
            print(f"{thumb_name[:30]:<30} | SKIPPED (OK)       | -      | {scene}", flush=True)
            continue

        image_path = os.path.join(thumb_dir, thumb_name)
        size = os.path.getsize(image_path) if os.path.exists(image_path) else 0
        print(f"START {thumb_name} path={image_path} size={size} resize_max={args.resize_max}", flush=True)
        
        res = worker.analyze_image(image_path, resize_max=args.resize_max, timeout_sec=args.timeout_sec)
        
        status = res.get("status", "UNKNOWN")
        latency = res.get("latency_ms", 0)
        evidence = res.get("evidence", {})
        scene = evidence.get("scene_type", "N/A")
        
        print(f"{thumb_name[:30]:<30} | {status:<18} | {latency}ms | {scene}", flush=True)
        
        item = {
            "image_name": thumb_name,
            "status": status,
            "latency_ms": latency,
            "visual_summary": evidence.get("visual_summary"),
            "scene_type": scene,
            "visible_people_count": evidence.get("visible_people_count"),
            "semantic_tags": evidence.get("main_subjects", []),
            "edit_value": evidence.get("edit_value"),
            "cognitive_role_hint": evidence.get("cognitive_role_hint"),
            "evidence_grade": res.get("evidence_grade"),
            "diag": res.get("diag")
        }
        results.append(item)
        
        stats["total"] += 1
        
        # Calculate actual elapsed time even for failures
        diag = res.get("diag", {})
        actual_elapsed = latency if latency > 0 else diag.get("elapsed_ms", 0)
        stats["total_elapsed_ms"] += actual_elapsed
        if actual_elapsed > stats["max_elapsed_ms"]:
            stats["max_elapsed_ms"] = actual_elapsed

        if status in ["OK", "OK_TRACE_VISUAL"]:
            stats["ok_count"] += 1
            stats["ok_trace_visual_count"] += 1
            stats["total_latency_ms"] += actual_elapsed
            stats["scene_type_distribution"][scene] = stats["scene_type_distribution"].get(scene, 0) + 1
            human_presence_total += evidence.get("human_presence_score", 0)
            stats["cognitive_fragment_candidate_count"] += 1
        else:
            stats["failed_count"] += 1
            if diag.get("exception_type") == "TimeoutError" or status == "MODEL_CALL_TIMEOUT":
                stats["timeout_count"] += 1
            if status.startswith("MODEL_CALL_FAILED"):
                stats["model_call_failed_count"] += 1

    if stats["total"] > 0:
        stats["avg_elapsed_ms"] = stats["total_elapsed_ms"] / stats["total"]
        
    if stats["ok_count"] > 0:
        stats["human_presence_avg"] = human_presence_total / stats["ok_count"]

    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    with open(os.path.join(output_dir, 'trace_batch_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nBatch validation complete. Success: {stats['ok_count']}/{stats['total']}", flush=True)
    print(f"Total Elapsed: {stats['total_elapsed_ms']}ms | Avg: {stats['avg_elapsed_ms']:.1f}ms", flush=True)
    print(f"Results saved to artifacts/qwen_vl_trace_batch/", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-images", type=int, default=5)
    parser.add_argument("--image-name", type=str, default=None)
    parser.add_argument("--resize-max", type=int, default=512)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    
    run_batch_probe(args)
