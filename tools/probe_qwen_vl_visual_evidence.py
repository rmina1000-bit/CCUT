import os
import sys
import json
import argparse
import time

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ccut_backend'))

from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker

def run_probe(max_images: int):
    worker = QwenVLVisualWorker()
    
    # Target directory for thumbnails
    thumb_dir = os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'thumbnails')
    if not os.path.exists(thumb_dir):
        print(f"HOLD: Thumbnail directory not found at {thumb_dir}")
        return

    # Select candidates
    all_thumbs = [f for f in os.listdir(thumb_dir) if f.endswith(('.jpg', '.png'))]
    if not all_thumbs:
        print("HOLD: No sample images found in thumbnails directory.")
        return

    candidates = all_thumbs[:max_images]
    print(f"Found {len(all_thumbs)} thumbnails, selecting {len(candidates)} for analysis.")

    results = []
    summary_counts = {
        "total": 0,
        "ok": 0,
        "failed": 0,
        "total_latency_ms": 0
    }

    print(f"{'Image':<30} | {'Status':<15} | {'Latency':<7}")
    print("-" * 60)

    for thumb_name in candidates:
        image_path = os.path.join(thumb_dir, thumb_name)
        res = worker.analyze_image(image_path)
        
        status = res.get("status", "UNKNOWN")
        latency = res.get("latency_ms", 0)
        
        print(f"{thumb_name[:30]:<30} | {status:<15} | {latency}ms")
        
        results.append({
            "image_name": thumb_name,
            "result": res
        })
        
        summary_counts["total"] += 1
        if status == "OK":
            summary_counts["ok"] += 1
            summary_counts["total_latency_ms"] += latency
        else:
            summary_counts["failed"] += 1

    # Save artifacts
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_visual_evidence')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'visual_evidence_result.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    avg_latency = summary_counts["total_latency_ms"] / summary_counts["ok"] if summary_counts["ok"] > 0 else 0
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": summary_counts,
        "average_latency_ms": avg_latency,
        "model": worker.model
    }
    
    with open(os.path.join(output_dir, 'visual_evidence_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nProbe complete. Results saved to artifacts/qwen_vl_visual_evidence/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-images", type=int, default=5)
    args = parser.parse_args()
    
    run_probe(args.max_images)
