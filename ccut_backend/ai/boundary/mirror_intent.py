# -*- coding: utf-8 -*-
# [MIRROR-CONNECT] 미러 엔진 v1 — 잡담(user_message) -> {content_type, mentioned_events, mirror_story}
# 자기완결(hub import 결합 0). qwen2.5:7b-instruct. 결정론 우선 + qwen 되비춤 + 근거게이트 + 템플릿 fallback.
# 어떤 실패에도 예외 안 냄 — 최악이면 {} 반환. (호출부는 try/except로 한 번 더 감쌈)
import json, re, urllib.request

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b-instruct"

EVENT_KW = {
    "도착/시작":   ["도착","시작","출발","처음","오프닝","나섰","집 나"],
    "먹방/식사":   ["먹방","먹","밥","국밥","식당","카페","음식","식사","맛집","맛있"],
    "이동/구경":   ["이동","구경","걷","시장","거리","관광","돌아다","산책"],
    "야경/마무리": ["야경","밤","마무리","마지막","불빛","노을","저녁","끝"],
    "바다/해안":   ["바다","해안","해안가","해변","백사장","파도"],
    "물놀이":      ["물놀이","수영","물장난","계곡","워터파크"],
    "여행":        ["여행","가족여행","나들이","소풍","관광"],
    "방/실내":     ["방","실내"],
    "갯벌/조간대": ["갯벌","조간대"],
    "동굴":        ["동굴"],
    "아이/어린이": ["아이들","아이","어린이"],
}
CONTENT_HINT = {
    "travel": ["여행","가족여행","나들이","소풍","관광","시장","거리","바다","해안"],
    "food":   ["먹방","맛집","음식","국밥"],
    "vlog":   ["브이로그","하루","일상","다녀","갔","했음"],
}
REQUEST_TYPE_KW = {
    "story_composition": ["스토리 구성","스토리를 구성","이야기 구성","스토리로","서사","흐름"],
}

COMPOUND_GUARD_KW = ["방학", "방문", "방금", "방송", "주방", "난방", "가방", "해방"]

def _find_ranges(text, keyword):
    ranges = []
    start = 0
    while keyword:
        idx = text.find(keyword, start)
        if idx < 0:
            break
        end = idx + len(keyword)
        ranges.append((idx, end))
        start = idx + 1
    return ranges

def _overlaps(a_start, a_end, ranges):
    return any(a_start < b_end and b_start < a_end for b_start, b_end in ranges)

def detect_events(text):
    found = []
    consumed = []
    for guard in COMPOUND_GUARD_KW:
        consumed.extend(_find_ranges(text, guard))

    candidates = []
    for ev, kws in EVENT_KW.items():
        for k in kws:
            for start, end in _find_ranges(text, k):
                candidates.append((-(end - start), start, end, ev))

    first_pos = {}
    for _, start, end, ev in sorted(candidates):
        if _overlaps(start, end, consumed):
            continue
        consumed.append((start, end))
        first_pos[ev] = min(start, first_pos.get(ev, start))

    found = sorted((pos, ev) for ev, pos in first_pos.items())
    return [ev for _, ev in found]

def detect_content_type(text):
    best, bestn = "vlog", 0
    for ct, kws in CONTENT_HINT.items():
        n = sum(1 for k in kws if k in text)
        if n > bestn:
            best, bestn = ct, n
    return best

def detect_request_type(text):
    for request_type, kws in REQUEST_TYPE_KW.items():
        if any(k in text for k in kws):
            return request_type
    return None

def is_grounded(story, text, events):
    if not story:
        return False
    hay = text + " " + " ".join(events)
    toks = re.findall(r"[가-힣]{2,}", story)
    if not toks:
        return True
    hit = sum(1 for t in toks if t in hay or t[:2] in hay)
    return (hit / len(toks)) >= 0.3   # 관대(v1): 30% 미만 지지면 지어냄으로 보고 템플릿

def template_mirror(events):
    if not events:
        return "말씀만으론 하루 흐름이 잘 안 잡혀요. 어디서 시작해 뭘 하셨는지 한 줄만 더 주시겠어요?"
    order = " → ".join(events)
    return f"이런 하루 맞으실까요? {order} 순서로 흘러가는 하루로 보입니다. 아니면 어디를 고칠지 말씀만 주세요."

def _ollama_json(prompt, timeout=60):
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "stream": False, "format": "json",
        "keep_alive": "10m", "options": {"temperature": 0, "num_predict": 512},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return json.loads(data.get("response", "{}") or "{}")

def _qwen_mirror(text, events):
    ev = ", ".join(events) if events else "(뚜렷한 사건 없음)"
    prompt = (
        "너는 영상 편집 상담자다. 사용자가 자기 하루를 무성의하게 던진 잡담을 보고 "
        "'이런 하루 맞죠?'라고 되비추는 따뜻한 초벌 서사를 한국어 2~3문장으로 쓴다.\n"
        "규칙:\n"
        "1. 사용자가 실제 말한 것과 아래 감지된 사건만 쓴다. 없는 사실 지어내기 금지.\n"
        "2. 확실치 않은 건 '~인 듯', '맞으실까요?'처럼 추측임을 드러낸다.\n"
        "3. 질문 나열 금지. 되비추는 완성된 척 초벌 한 덩어리. 한국어만.\n"
        f"사용자 잡담: {text}\n"
        f"감지된 사건(순서): {ev}\n"
        '출력 JSON: {"mirror_story": "..."}'
    )
    out = _ollama_json(prompt)
    return (out.get("mirror_story") or "").strip() or None

def extract(user_message):
    try:
        text = (user_message or "").strip()
        if not text:
            return {}
        events = detect_events(text)
        ctype = detect_content_type(text)
        request_type = detect_request_type(text)
        story = None
        try:
            story = _qwen_mirror(text, events)
            if story and not is_grounded(story, text, events):
                story = None   # 지어냄 -> 버리고 템플릿
        except Exception:
            story = None
        if not story:
            story = template_mirror(events)
        return {
            "content_type": ctype,
            "mentioned_events": [{"event": e} for e in events],
            "request_type": request_type,
            "mirror_story": story,
            "source": "mirror_v1",
        }
    except Exception:
        return {}

if __name__ == "__main__":
    demo = "오늘 종일 시장 돌아다님. 국밥집 그거 맛있었음. 야경 마지막에 괜찮았고"
    print("detect_events:", detect_events(demo))
    print("content_type :", detect_content_type(demo))
    print("template     :", template_mirror(detect_events(demo)))
