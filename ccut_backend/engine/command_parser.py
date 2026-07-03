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
    '  "focus_en": focus의 짧은 영어 장면 표현(예 "water play at the beach, swimming"), focus 없으면 null\n'
    '  "focus_mode": focus가 있을 때만. "only"=그 내용만 남김(배타: "~만","오직","~빼고 전부"),\n'
    '               "boost"=그 내용을 중심/위주로 강조하되 다른 것도 포함. 기본 "boost". focus 없으면 null\n'
    '  "avoid": 빼야 할 내용 테마, 없으면 null\n'
    '  "avoid_en": avoid의 짧은 영어 장면 표현(예 "indoor room, bedroom, interior"), avoid 없으면 null\n'
    "(영어 표현은 영상 장면 묘사가 영어라 매칭 정확도를 높이기 위함. 장면이 보일 법한 영어 명사구로.)\n"
    "예시:\n"
    '  "조각을 4개만 편집해줘" -> {"count":4,"focus":null,"focus_en":null,"focus_mode":null,"avoid":null,"avoid_en":null}\n'
    '  "한 다섯개 정도로 짧게" -> {"count":5,"focus":null,"focus_en":null,"focus_mode":null,"avoid":null,"avoid_en":null}\n'
    '  "물놀이 중심으로 편집해줘" -> {"count":null,"focus":"물놀이","focus_en":"water play at the beach, swimming, ocean","focus_mode":"boost","avoid":null,"avoid_en":null}\n'
    '  "물놀이만 보여줘" -> {"count":null,"focus":"물놀이","focus_en":"water play at the beach, swimming, ocean","focus_mode":"only","avoid":null,"avoid_en":null}\n'
    '  "오직 물놀이 장면만" -> {"count":null,"focus":"물놀이","focus_en":"water play, beach, swimming","focus_mode":"only","avoid":null,"avoid_en":null}\n'
    '  "실내는 빼고" -> {"count":null,"focus":null,"focus_en":null,"focus_mode":null,"avoid":"실내","avoid_en":"indoor room, bedroom, interior scene"}\n'
    '  "실내영상은 빼줘" -> {"count":null,"focus":null,"focus_en":null,"focus_mode":null,"avoid":"실내","avoid_en":"indoor room, bedroom, interior scene"}\n'
    '  "사람 위주로 다섯개만" -> {"count":5,"focus":"사람","focus_en":"people, person, close-up of a person","focus_mode":"boost","avoid":null,"avoid_en":null}\n'
    '  "더 빠르게" -> {"count":null,"focus":null,"focus_en":null,"focus_mode":null,"avoid":null,"avoid_en":null}\n'
)


def parse(instruction: str) -> dict:
    """편집 지시 → {count:int|None, focus:str|None, avoid:str|None}."""
    out = {"count": None, "focus": None, "focus_en": None, "focus_mode": None,
           "avoid": None, "avoid_en": None}
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
        def _clean(v):
            if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none"):
                return v.strip()
            return None

        f = _clean(parsed.get("focus"))
        if f:
            out["focus"] = f
            out["focus_en"] = _clean(parsed.get("focus_en"))
            # focus가 있을 때만 mode 의미. 기본 boost(비파괴), "only"만 배타 필터.
            fm = parsed.get("focus_mode")
            out["focus_mode"] = "only" if (isinstance(fm, str) and fm.strip().lower() == "only") else "boost"
        a = _clean(parsed.get("avoid"))
        if a:
            out["avoid"] = a
            out["avoid_en"] = _clean(parsed.get("avoid_en"))
        print(f"[QWEN_ROUTE] route=command_parser model={CMD_MODEL}")
        print(f"[INTENT-ROUTER cmd] model={CMD_MODEL} {instruction!r} -> {out}")
    except Exception as e:
        print(f"[INTENT-ROUTER cmd] parse skip ({e})")
    return out
