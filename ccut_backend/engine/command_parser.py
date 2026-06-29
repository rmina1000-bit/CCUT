"""[INTENT-ROUTER] 자연어 편집지시 → 구조화 명령 (qwen 파서, 학습 X / 프롬프트 O).

regex/키워드 하드코딩을 대체한다. 사용자가 어떻게 말하든 Ollama의 qwen이
{count, focus, avoid} JSON으로 번역한다. Ollama format=json으로 JSON 강제.

graceful: Ollama 미가동/타임아웃/파싱실패 시 전부 null 반환 → 기존 동작으로 무해 폴백.
모델 교체는 CCUT_CMD_MODEL 한 줄(=머리 갈아끼우기). 손발(executor)은 불변.
"""
import os
import json
import urllib.request

OLLAMA_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434")
CMD_MODEL = os.getenv("CCUT_CMD_MODEL", "qwen2.5:7b-instruct")

_PROMPT = (
    "너는 영상 편집기의 명령 파서다. 한국어 편집 지시를 받아 JSON만 출력한다.\n"
    "키:\n"
    '  "count": 사용자가 명시한 조각(클립) 개수(정수), 없으면 null\n'
    '  "focus": 강조할 내용 테마(예 "물놀이","사람","풍경"), 없으면 null\n'
    '  "avoid": 빼야 할 내용 테마, 없으면 null\n'
    "예시:\n"
    '  "조각을 4개만 편집해줘" -> {"count":4,"focus":null,"avoid":null}\n'
    '  "네 개만 써줘" -> {"count":4,"focus":null,"avoid":null}\n'
    '  "한 다섯개 정도로 짧게" -> {"count":5,"focus":null,"avoid":null}\n'
    '  "물놀이 중심으로 편집해줘" -> {"count":null,"focus":"물놀이","avoid":null}\n'
    '  "물놀이 위주로 보여줘" -> {"count":null,"focus":"물놀이","avoid":null}\n'
    '  "물놀이 장면은 빼줘" -> {"count":null,"focus":null,"avoid":"물놀이"}\n'
    '  "사람 위주로 다섯개만" -> {"count":5,"focus":"사람","avoid":null}\n'
    '  "더 빠르게" -> {"count":null,"focus":null,"avoid":null}\n'
)


def parse(instruction: str) -> dict:
    """편집 지시 → {count:int|None, focus:str|None, avoid:str|None}."""
    out = {"count": None, "focus": None, "avoid": None}
    if not instruction or not instruction.strip():
        return out
    try:
        body = json.dumps({
            "model": CMD_MODEL,
            "prompt": _PROMPT + "\n지시: " + instruction.strip() + "\nJSON:",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL + "/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parsed = json.loads(data.get("response", "{}") or "{}")

        c = parsed.get("count")
        if isinstance(c, bool):
            c = None
        if isinstance(c, (int, float)) and 1 <= int(c) <= 40:
            out["count"] = int(c)
        f = parsed.get("focus")
        if isinstance(f, str) and f.strip() and f.strip().lower() not in ("null", "none"):
            out["focus"] = f.strip()
        a = parsed.get("avoid")
        if isinstance(a, str) and a.strip() and a.strip().lower() not in ("null", "none"):
            out["avoid"] = a.strip()
        print(f"[INTENT-ROUTER cmd] model={CMD_MODEL} {instruction!r} -> {out}")
    except Exception as e:
        print(f"[INTENT-ROUTER cmd] parse skip ({e})")
    return out
