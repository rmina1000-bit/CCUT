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
                    print(f"Resized image from {width}x{height} to {img.size[0]}x{img.size[1]}")
                else:
                    print(f"Image size {width}x{height} is within limits.")
            except Exception as e:
                print(f"Pillow failed to process image: {e}. Using original.")
        else:
            print("Pillow not found, using original image.")

        b64_str = base64.b64encode(data).decode('utf-8')
        return {
            "b64": b64_str,
            "original_size": original_size,
            "current_size": len(data),
            "width": width,
            "height": height
        }, "OK"
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
        if hasattr(e, 'reason') and "timed out" in str(e.reason).lower():
            return None, "MODEL_CALL_TIMEOUT", elapsed
        if "timed out" in str(e).lower():
            return None, "MODEL_CALL_TIMEOUT", elapsed
        return None, "OLLAMA_NOT_RUNNING", elapsed
    except Exception as e:
        elapsed = int((time.time() - start_time) * 1000)
        return None, "MODEL_CALL_FAILED", elapsed

def extract_content(raw, mode):
    content = ""
    thinking = ""
    
    msg = raw.get("message", {})
    
    if mode.startswith("chat"):
        content = msg.get("content", "")
        thinking = msg.get("thinking", "")
        if not content: content = raw.get("response", "")
        if not thinking: thinking = raw.get("thinking", "")
    else: # generate
        content = raw.get("response", "")
        thinking = raw.get("thinking", "")
        if not content: content = msg.get("content", "")
        if not thinking: thinking = msg.get("thinking", "")
        
    return content.strip(), thinking.strip()

def analyze_visual_signal(text):
    keywords = ["person", "bowl", "kimchi", "restaurant", "eating", "table", "side dishes", "spoon", "elderly", "food"]
    found = [k for k in keywords if k in text.lower()]
    return len(found) > 0, found

def run_smoke_ladder(args):
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'ccut_backend', 'storage', 'thumbnails'),
        os.path.join(os.path.dirname(__file__), '..', 'storage', 'thumbnails')
    ]
    
    target_image = None
    for p in possible_paths:
        if os.path.exists(p):
            pref = os.path.join(p, "VF100_SRC_4B7DFECE.jpg")
            if os.path.exists(pref):
                target_image = pref
                break
            all_thumbs = [f for f in os.listdir(p) if f.endswith(('.jpg', '.png'))]
            if all_thumbs:
                target_image = os.path.join(p, all_thumbs[0])
                break
    
    if not target_image:
        print("HOLD: No images found.")
        return

    img_info, status = get_image_data(target_image, args.resize_max)
    if status != "OK":
        print(f"HOLD: Image processing failed: {status}")
        return

    print(f"Selected Image: {os.path.basename(target_image)}")
    print(f"Base64 Length: {len(img_info['b64'])}")

    output_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'qwen_vl_smoke_ladder')
    os.makedirs(output_dir, exist_ok=True)

    results = []
    base_url = "http://127.0.0.1:11434"
    
    # Modes to test
    # Mode format: (display_name, api_endpoint, prompt, use_no_think_logic)
    test_modes = [
        ("chat", "/api/chat", "이미지를 보고, 보이는 내용을 한국어 한 문장으로만 답하세요. 빈 답변을 하지 마세요.", False),
        ("generate", "/api/generate", "이미지를 보고, 보이는 내용을 한국어 한 문장으로만 답하세요. 빈 답변을 하지 마세요.", False),
        ("chat_no_think", "/api/chat", "/no_think\n이미지를 한국어 한 문장으로 설명하세요.", True),
        ("generate_no_think", "/api/generate", "/no_think\n이미지를 한국어 한 문장으로 설명하세요.", True)
    ]

    for mode_id, endpoint, prompt, is_no_think in test_modes:
        print(f"\nTesting Mode: {mode_id}...")
        
        if endpoint == "/api/chat":
            payload = {
                "model": "qwen3-vl:4b",
                "messages": [{"role": "user", "content": prompt, "images": [img_info['b64']]}],
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": args.num_predict},
                "keep_alive": "10m"
            }
        else:
            payload = {
                "model": "qwen3-vl:4b",
                "prompt": prompt,
                "images": [img_info['b64']],
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": args.num_predict},
                "keep_alive": "10m"
            }
            
        resp, status, elapsed = call_ollama(f"{base_url}{endpoint}", payload, args.timeout_sec)
        
        if resp:
            filename = f"smoke_ladder_raw_{mode_id}.json"
            with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
                json.dump(resp, f, indent=2, ensure_ascii=False)
            
            content, thinking = extract_content(resp, mode_id)
            done_reason = resp.get("done_reason", "unknown")
            
            final_status = "OK_FINAL_CONTENT" if content else "EMPTY_FINAL_CONTENT"
            if not content and thinking:
                final_status = "THINKING_ONLY_LENGTH" if done_reason == "length" else "THINKING_ONLY_STOP"
            
            has_signal, signals = analyze_visual_signal(thinking if thinking else content)
            
            res = {
                "mode": mode_id,
                "status": final_status,
                "elapsed_ms": elapsed,
                "content": content,
                "thinking": thinking,
                "done_reason": done_reason,
                "eval_count": resp.get("eval_count"),
                "prompt_eval_count": resp.get("prompt_eval_count"),
                "diagnostic_visual_seen": has_signal,
                "visual_signal_keywords_found": signals,
                "production_usable": final_status == "OK_FINAL_CONTENT"
            }
        else:
            res = {"mode": mode_id, "status": status, "elapsed_ms": elapsed, "content": "", "production_usable": False}
        
        print(f"Status: {res['status']} | Elapsed: {elapsed}ms | Seen: {res.get('diagnostic_visual_seen', False)}")
        print(f"Response Preview: {res.get('content', '')[:100]}")
        results.append(res)

    # Final Judgement
    is_pass = any(r.get("production_usable") for r in results)
    judgement = "PASS" if is_pass else "FAIL"
    if judgement == "FAIL" and any(r.get("diagnostic_visual_seen") for r in results):
        judgement = "PARTIAL"

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judgement": judgement,
        "image": os.path.basename(target_image),
        "num_predict": args.num_predict,
        "results": results,
        "has_pillow": HAS_PILLOW
    }
    with open(os.path.join(output_dir, 'smoke_ladder_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nFinal Response Unlock Probe complete. Judgement: {judgement}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--resize-max", type=int, default=512)
    parser.add_argument("--num-predict", type=int, default=256)
    args = parser.parse_args()
    run_smoke_ladder(args)
