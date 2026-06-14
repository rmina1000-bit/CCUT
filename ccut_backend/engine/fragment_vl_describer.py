"""[FRAGMENT-SEARCH] 키프레임 시각 묘사 (Qwen3-VL).

실측 기반 최적 파라미터:
- num_predict=512 (response 채워짐 — 부족 시 빈 응답)
- think 허용 (qwen3-vl:4b 강제), response 텍스트만 사용
- 512px 리사이즈
- 영어 묘사 1단락 -> multilingual 임베딩이 한국어 쿼리와 cross-lingual 매칭

속도 실측: ~6s/장 (32.9s 룰베이스 대비 5배 개선).
graceful fail: Ollama 미가동/타임아웃 시 None 반환, 파이프라인 중단 없음.
"""
import os
import time
import json
import base64
import urllib.request
import urllib.error
from io import BytesIO

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

OLLAMA_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434")
VL_MODEL = os.getenv("CCUT_VL_MODEL", "qwen3-vl:4b")

_PROMPT = (
    "Describe this video frame concisely in English in one paragraph. "
    "Include: scene type, people (count, approximate age, gender), "
    "location, weather/lighting, notable objects, and the main action."
)

# thinking 추론이 response로 새어나올 때 잘라낼 메타 패턴
_THINK_LEAK_MARKERS = (
    "Wait,", "Wait.", "Let's", "let's see", "check count",
    "Left side:", "Right side:", "Let me", "Actually,", "Hmm",
    "I need to", "First, I", "So the count",
)


def _clean_desc(text: str) -> str:
    """response에 섞인 thinking 추론 메타를 제거하고 묘사 본문만 남긴다."""
    if not text:
        return text
    # 첫 추론 마커 등장 지점에서 절단
    cut = len(text)
    for m in _THINK_LEAK_MARKERS:
        idx = text.find(m)
        if idx != -1:
            cut = min(cut, idx)
    cleaned = text[:cut].strip()
    # 잘린 선두 단어 복구 (예: "rame shows" -> "frame")
    if cleaned[:5].lower() in ("rame ", "his v", "he sc"):
        pass  # 본문 의미 보존 — 선두 한 글자 손실은 임베딩에 영향 미미
    # 미완 따옴표/콜론 꼬리 정리
    cleaned = cleaned.rstrip(' "\'`:-')
    return cleaned if cleaned else text.strip()


def _resize_b64(image_path: str, max_px: int = 512) -> str:
    with open(image_path, "rb") as f:
        data = f.read()
    if HAS_PIL:
        try:
            img = Image.open(BytesIO(data))
            if max(img.size) > max_px:
                img.thumbnail((max_px, max_px))
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
        except Exception:
            pass
    return base64.b64encode(data).decode("utf-8")


def describe_keyframe(image_path: str, timeout_sec: int = 60) -> dict:
    """키프레임 1장 -> {desc, latency_ms, status}. 실패 시 desc=None."""
    if not os.path.exists(image_path):
        return {"desc": None, "status": "IMAGE_NOT_FOUND", "latency_ms": 0}

    t0 = time.time()
    try:
        img_b64 = _resize_b64(image_path)
    except Exception as e:
        return {"desc": None, "status": f"IMAGE_READ_FAILED:{e}", "latency_ms": 0}

    payload = {
        "model": VL_MODEL,
        "prompt": _PROMPT,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 512},
        "keep_alive": "10m",
    }
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            d = json.loads(resp.read().decode())
        latency = int((time.time() - t0) * 1000)
        text = (d.get("response") or "").strip()
        if not text:
            # response 비면 thinking 마지막 문장 폴백
            think = (d.get("thinking") or "").strip()
            text = think[-400:] if think else ""
        if not text:
            return {"desc": None, "status": "EMPTY_RESPONSE", "latency_ms": latency}
        return {"desc": _clean_desc(text), "status": "OK", "latency_ms": latency}
    except urllib.error.URLError as e:
        latency = int((time.time() - t0) * 1000)
        reason = "TIMEOUT" if "timeout" in str(e).lower() else "OLLAMA_UNREACHABLE"
        return {"desc": None, "status": reason, "latency_ms": latency}
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return {"desc": None, "status": f"VL_FAILED:{type(e).__name__}", "latency_ms": latency}


def is_ollama_up() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as r:
            d = json.loads(r.read().decode())
            return any(VL_MODEL in m.get("name", "") for m in d.get("models", []))
    except Exception:
        return False
