"""[FRAGMENT-SEARCH 단계4] 채팅 자연어 -> 검색 의도/쿼리 추출.

"영국에서 비오는날 찍었던 중년 아저씨를 찾아서 관련된 영상조각들 불러와줘"
  -> {is_search: True, query: "영국에서 비오는날 찍었던 중년 아저씨"}

설계:
- 룰베이스 우선 (즉각 응답, qwen 불필요). 한국어 검색 동사/조사 정제.
- qwen 폴백: 룰베이스가 모호할 때만 (옵션, CCUT_CHAT_LLM=1).
"""
import re

# 검색 의도 트리거 (이게 있으면 "조각을 찾아달라"는 요청)
_SEARCH_TRIGGERS = (
    "찾아", "찾아줘", "찾아서", "불러와", "불러줘", "불러", "검색",
    "보여줘", "보여", "가져와", "가져와줘", "가져", "끌어와", "꺼내",
    "있어?", "있나", "어디", "관련 영상", "관련된 영상", "영상조각",
    "조각 찾", "장면 찾", "자료 찾", "찾을", "search", "find",
)

# 검색어에서 제거할 꼬리 동사구/명령구 (긴 것부터)
_TAIL_PHRASES = (
    "관련된 영상조각들 불러와줘", "관련된 영상조각 불러와줘",
    "관련된 영상조각들을 불러와줘", "관련 영상조각들 불러와줘",
    "관련된 조각들 불러와줘", "관련 조각 불러와줘",
    "영상조각들 불러와줘", "영상 조각 불러와줘", "조각들 불러와줘",
    "찾아서 불러와줘", "찾아서 보여줘", "찾아서 가져와줘",
    "을 찾아줘", "를 찾아줘", "을 불러와줘", "를 불러와줘",
    "찾아줘", "찾아서", "불러와줘", "불러줘", "보여줘", "가져와줘",
    "검색해줘", "검색해", "꺼내줘", "끌어와줘",
    "관련된 영상", "관련 영상", "영상조각", "조각", "장면", "자료",
    "클립 있어", "클립있어", "클립", "있어", "있나", "있는지",
    "찾아", "불러와", "가져와", "보여", "검색",
)

# 검색어에서 떼낼 조사/접속 꼬리
_PARTICLES = ("을", "를", "이", "가", "은", "는", "와", "과", "도", "의")


def _strip_query(message: str) -> str:
    q = message.strip()
    # 꼬리 명령구 반복 제거
    changed = True
    while changed:
        changed = False
        for ph in _TAIL_PHRASES:
            if q.endswith(ph):
                q = q[: -len(ph)].strip()
                changed = True
        # 꼬리 조사 제거
        for p in _PARTICLES:
            if q.endswith(p) and len(q) > 1:
                q = q[:-1].strip()
                changed = True
    return q.strip(" ,.!?…")


def detect(message: str) -> dict:
    """채팅 메시지 -> {is_search, query, confidence}."""
    if not message or not message.strip():
        return {"is_search": False, "query": "", "confidence": 0.0}

    msg = message.strip()
    low = msg.lower()
    hit = any(t in msg or t in low for t in _SEARCH_TRIGGERS)
    if not hit:
        return {"is_search": False, "query": "", "confidence": 0.0}

    query = _strip_query(msg)
    # 정제 후 너무 짧으면(트리거 단어만 있던 경우) 검색어 부재
    if len(query) < 2:
        return {"is_search": False, "query": "", "confidence": 0.3}

    return {"is_search": True, "query": query, "confidence": 0.85}


def detect_with_llm(message: str) -> dict:
    """qwen 폴백: 룰베이스가 검색어를 못 뽑을 때만. (옵션)"""
    base = detect(message)
    if base["is_search"]:
        return base
    # LLM 보강은 추후 — 현재는 룰베이스 결과 그대로
    return base
