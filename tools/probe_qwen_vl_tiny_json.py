import os
import sys
import json
import base64
import time
import argparse
import urllib.request
import urllib.error
from io import BytesIO

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

def get_image_data(image_path, resize_max=512):
    if not os.path.exists(image_path):
        return None, "IMAGE_NOT_FOUND"

    try:
        with open(image_path, "rb") as f:
            data = f.read()
            original_size = len(data)
            
        width, height = 0, 0
        if HAS_PILLOW:
            try:
                img = Image.open(BytesIO(data))
                width, height = img.size
                if max(width, height) > resize_max:
                    img.thumbnail((resize_max, resize_max))
                    buf = BytesIO()
                    img.save(buf, format="JPEG")
                    data = buf.getvalue()
            except Exception as e:
                print(f"Pillow failed: {e}")
        
        b64_str = base64.b64encode(data).decode('utf-8')
        return {"b64": b64_str, "original_size": original_size, "current_size": len(data)}, "OK"
    except Exception as e:
        return None, str(e)

def call_ollama(url, payload, timeout):
    start_time = time.time()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_data = json.loads(response.read().decode())
            elapsed = int((time.time() - start_time) * 1000)
            return resp_data, "OK", elapsed
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start_time) * 1000)
        return None, str(e), elapsed
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        return None, str(e), elapsed

def run_tiny_json_probe(args):
    # 1. Select Image (same as smoke ladder)
    thumb_dir = os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'thumbnails')
    target_image = os.path.join(thumb_dir, "VF100_SRC_4B7DFECE.jpg")
    if not os.path.exists(target_image):
         all_thumbs = [f for f in os.listdir(thumb_dir) if f.endswith(('.jpg', '.png'))]
         if all_thumbs: target_image = os.path.join(thumb_dir, all_thumbs[0])
         else:
             print("No images found.")
             return

    img_info, status = get_image_data(target_image, args.resize_max)
    if status != "OK":
        print(f"Image error: {status}")
        return

    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_tiny_json')
    os.makedirs(output_dir, exist_ok=True)

    base_url = "http://127.0.0.1:11434"
    tiny_schema = {
        "type": "object",
        "properties": {
            "visual_summary": {"type": "string"},
            "scene_type": {"type": "string"},
            "has_person": {"type": "boolean"}
        },
        "required": ["visual_summary", "scene_type", "has_person"]
    }

    results = []
    # We test num_predict 128 and 256 as requested
    predict_configs = [128, 256] if args.num_predict == 256 else [args.num_predict]

    for npred in predict_configs:
        print(f"\nTesting Tiny JSON with num_predict={npred}...")
        
        payload = {
            "model": "qwen3-vl:4b",
            "prompt": "/no_think\n이미지를 보고 JSON만 출력하세요.",
            "images": [img_info['b64']],
            "stream": False,
            "format": tiny_schema,
            "options": {
                "temperature": 0,
                "num_predict": npred
            },
            "keep_alive": "10m"
        }
        
        resp, status, elapsed = call_ollama(f"{base_url}/api/generate", payload, args.timeout_sec)
        
        if resp:
            raw_filename = f"tiny_json_raw_np{npred}.json"
            with open(os.path.join(output_dir, raw_filename), 'w', encoding='utf-8') as f:
                json.dump(resp, f, indent=2, ensure_ascii=False)
            
            content = resp.get("response", "").strip()
            thinking = resp.get("thinking", "").strip()
            
            parsed = None
            try:
                if content:
                    parsed = json.loads(content)
            except:
                pass
                
            res = {
                "num_predict": npred,
                "status": "OK" if parsed else ("THINKING_ONLY" if thinking else "EMPTY"),
                "elapsed_ms": elapsed,
                "content": content,
                "thinking": thinking,
                "parsed": parsed,
                "done_reason": resp.get("done_reason")
            }
        else:
            res = {"num_predict": npred, "status": "CALL_FAILED", "error": status, "elapsed_ms": elapsed}
        
        print(f"Status: {res['status']} | Elapsed: {elapsed}ms | Parsed: {parsed is not None}")
        results.append(res)

    is_pass = any(r.get("parsed") for r in results)
    judgement = "PASS" if is_pass else "FAIL"
    if judgement == "FAIL" and any(r.get("thinking") for r in results):
        judgement = "PARTIAL"

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judgement": judgement,
        "image": os.path.basename(target_image),
        "results": results
    }
    with open(os.path.join(output_dir, 'tiny_json_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nTiny JSON Probe complete. Judgement: {judgement}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--resize-max", type=int, default=512)
    parser.add_argument("--num-predict", type=int, default=256)
    args = parser.parse_args()
    run_tiny_json_probe(args)
