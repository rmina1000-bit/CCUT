import json
import time
import urllib.request
import urllib.error
import base64
import os
import re
from io import BytesIO
from typing import Dict, Any, List, Optional

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

class QwenVLVisualWorker:
    """
    [STEP 10-J-R4.1] Qwen3-VL Visual Evidence Worker (Trace-based + Diagnostic)
    Note: Current Ollama qwen3-vl:4b uses qwen3-vl-thinking renderer/parser.
    Visual Evidence is primarily extracted from the 'thinking' trace.
    """
    def __init__(self, model: str = "qwen3-vl:4b", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url
        self.timeout = 150  # Default timeout

    def _extract_from_thinking(self, thinking_text: str) -> Dict[str, Any]:
        """
        Extracts structured evidence from the thinking trace string.
        Attempts JSON parse first, then falls back to rule-based keyword extraction.
        """
        # Try to find JSON block in thinking
        json_match = re.search(r'\{.*\}', thinking_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if "visual_summary" in data or "scene_type" in data:
                    return data
            except:
                pass

        # Fallback: Rule-based extraction (Heuristic)
        text = thinking_text.lower()
        evidence = {
            "visual_summary": "시각적 분석 (thinking trace): " + thinking_text.replace("<think>", "").strip()[:80] + "...",
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
            "reason": "Rule-based fallback from thinking trace"
        }

        if any(k in text for k in ["restaurant", "dining", "eatery"]): evidence["scene_type"] = "restaurant"
        elif any(k in text for k in ["food", "eating", "bowl", "kimchi"]): evidence["scene_type"] = "food"
        
        if any(k in text for k in ["person", "elderly", "man", "woman"]):
            evidence["main_subjects"].append("person")
            evidence["visible_people_count"] = 1
            evidence["human_presence_score"] = 0.8
            if "elderly" in text: evidence["main_subjects"].append("elderly person")
        
        if "kimchi" in text: evidence["main_subjects"].append("kimchi")
        if "bowl" in text: evidence["main_subjects"].append("bowl")
        
        if "eating" in text:
            evidence["action_level"] = "medium"
            evidence["edit_value"] = 0.75
            evidence["visual_summary"] = "식당에서 식사를 하는 장면이 감지됨"

        return evidence

    def analyze_image(self, image_path: str, resize_max: int = 512, timeout_sec: int = 120) -> Dict[str, Any]:
        start_time = time.time()
        diag = {
            "image_path": image_path,
            "image_exists": os.path.exists(image_path),
            "image_size_bytes": 0,
            "original_width": 0,
            "original_height": 0,
            "resized_width": 0,
            "resized_height": 0,
            "resized_size_bytes": 0,
            "base64_length": 0,
            "request_mode": "generate",
            "timeout_sec": timeout_sec,
            "exception_type": None,
            "exception_message": None,
            "elapsed_ms": 0
        }

        if not diag["image_exists"]:
            diag["elapsed_ms"] = int((time.time() - start_time) * 1000)
            return {"status": "IMAGE_NOT_FOUND", "error": "File not found", "diag": diag}

        try:
            diag["image_size_bytes"] = os.path.getsize(image_path)
            with open(image_path, "rb") as f:
                img_data = f.read()
            
            # Resizing
            if HAS_PILLOW:
                try:
                    img = Image.open(BytesIO(img_data))
                    diag["original_width"], diag["original_height"] = img.size
                    if max(img.size) > resize_max:
                        img.thumbnail((resize_max, resize_max))
                        diag["resized_width"], diag["resized_height"] = img.size
                        buf = BytesIO()
                        img.save(buf, format="JPEG")
                        img_data = buf.getvalue()
                        diag["resized_size_bytes"] = len(img_data)
                    else:
                        diag["resized_width"], diag["resized_height"] = img.size
                        diag["resized_size_bytes"] = diag["image_size_bytes"]
                except Exception as e:
                    diag["exception_type"] = "IMAGE_RESIZE_FAILED"
                    diag["exception_message"] = str(e)
                    # Continue with original data if possible or fail
            
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            diag["base64_length"] = len(img_base64)
            
        except Exception as e:
            diag["elapsed_ms"] = int((time.time() - start_time) * 1000)
            diag["exception_type"] = type(e).__name__
            diag["exception_message"] = str(e)
            return {"status": "IMAGE_READ_FAILED", "error": str(e), "diag": diag}

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": "/no_think\nAnalyze this image. Output a summary and key scene attributes in JSON.",
            "images": [img_base64],
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 300
            },
            "keep_alive": "10m"
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                resp_data = json.loads(response.read().decode())
                latency = int((time.time() - start_time) * 1000)
                diag["elapsed_ms"] = latency
                
                content = resp_data.get("response", "").strip()
                thinking = resp_data.get("thinking", "").strip()
                
                source_text = content if content else thinking
                if not source_text:
                    return {"status": "EMPTY_RESPONSE", "latency_ms": latency, "diag": diag}

                evidence = self._extract_from_thinking(source_text)
                
                return {
                    "status": "OK_TRACE_VISUAL" if not content else "OK",
                    "evidence": evidence,
                    "latency_ms": latency,
                    "model": self.model,
                    "source_channel": "thinking_trace" if not content else "response",
                    "evidence_grade": "trace_visual_candidate",
                    "production_usable": False,
                    "diag": diag
                }

        except urllib.error.URLError as e:
            diag["elapsed_ms"] = int((time.time() - start_time) * 1000)
            if "timeout" in str(e).lower():
                return {"status": "MODEL_CALL_TIMEOUT", "error": str(e), "diag": diag}
            return {"status": "OLLAMA_NOT_RUNNING", "error": str(e), "diag": diag}
        except Exception as e:
            diag["elapsed_ms"] = int((time.time() - start_time) * 1000)
            diag["exception_type"] = type(e).__name__
            diag["exception_message"] = str(e)
            return {"status": "MODEL_CALL_FAILED", "error": str(e), "diag": diag}
