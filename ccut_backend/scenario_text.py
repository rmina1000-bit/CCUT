# -*- coding: utf-8 -*-
"""[SCRIPT-1] 지문 결정론 템플릿 — 장면 태그(qwen_vl)를 사람의 문장으로 번역.

헌장 v1.1: 지문은 태그 노출이 아니라 원고 본문이다.
  "subway car, blue floor, child (장소:지하철)" → "(지하철 안. 아이가 보인다.)"
결정론 우선(이 모듈), 로컬 LLM 다듬기는 후속 (MASTER CONCEPT §12 분업).
실측 어휘(307 조각) 기반 사전 — 미매칭은 조용히 생략하지 않고 객체 나열로 폴백.
"""
import re

# 장소 라벨(이미 한국어) → 배경 문장
_PLACE = {
    "집": "집 안", "바다": "바닷가", "지하철": "지하철 안", "운동장": "운동장",
    "길거리": "길거리", "학교": "학교", "사무실": "사무실", "빙상장": "빙상장",
    "병원": "병원", "강": "강가", "산": "산", "공원": "공원", "카페": "카페",
    "식당": "식당", "방": "방 안", "놀이터": "놀이터", "차": "차 안", "실내": "실내", "실외": "야외",
}

# 주체 태그(영어) — 우선순위 순
_SUBJECT = [
    ("baby", "아기"), ("child", "아이"), ("kid", "아이"), ("girl", "여자아이"),
    ("boy", "남자아이"), ("crowd", "사람들"), ("people", "사람들"),
    ("person", "한 사람"), ("man", "남자"), ("woman", "여자"),
    ("dog", "강아지"), ("cat", "고양이"),
]

# 행동 태그(영어) → 서술어
_ACTION = {
    "walking": "걷는다", "running": "달린다", "jumping": "뛴다", "sitting": "앉아 있다",
    "standing": "서 있다", "people sitting": "앉아 있다", "people standing": "서 있다",
    "waving": "손을 흔든다", "splashing": "물장구친다", "speaking": "이야기한다",
    "talking": "이야기한다", "playing": "논다", "smiling": "웃는다", "eating": "먹는다",
    "looking": "바라본다", "dancing": "춤춘다", "clapping": "박수친다",
    "jumping rope": "줄넘기한다", "lying": "누워 있다", "hugging": "안는다",
}

# 객체 태그(영어) → 명사 (사람/행동 없을 때 배경 묘사 폴백)
_OBJECT = {
    "building": "건물", "room": "방", "trees": "나무", "tree": "나무", "wall": "벽",
    "water": "물", "bed": "침대", "window": "창문", "ocean": "바다", "waves": "파도",
    "beach": "바닷가", "sand": "모래", "umbrella": "우산", "subway car": "지하철",
    "microphone": "마이크", "screen": "화면", "sky": "하늘", "books": "책", "book": "책",
    "table": "탁자", "pillow": "베개", "curtain": "커튼", "door": "문", "fence": "울타리",
    "shoes": "신발", "metal pole": "기둥", "backpack": "가방", "amusement park": "놀이공원",
    "signboard": "간판", "sign": "표지판", "light": "조명", "speaker": "스피커",
    "closet": "옷장", "wardrobe": "옷장", "blanket": "이불", "cake": "케이크",
    "car": "자동차", "flower": "꽃", "flowers": "꽃", "grass": "잔디", "mountain": "산",
}


def _has_jong(ch):
    """한글 종성(받침) 유무."""
    o = ord(ch)
    return 0xAC00 <= o <= 0xD7A3 and (o - 0xAC00) % 28 != 0


def _josa(word, with_jong, without_jong):
    return with_jong if (word and _has_jong(word[-1])) else without_jong


def place_of(visual_desc):
    """씬 헤딩용 장소 (S#n. 장소) — 장소 라벨이 있을 때만. 없으면 None (추정 금지)."""
    if not visual_desc:
        return None
    m = re.search(r"\(장소:([^)]+)\)", visual_desc)
    if not m:
        return None
    p = m.group(1).strip()
    return _PLACE.get(p, p)


def stage_direction(visual_desc):
    """visual_desc → 한국어 지문 문장('(...)') 또는 None."""
    if not visual_desc:
        return None
    place_labels = re.findall(r"\(장소:([^)]+)\)", visual_desc)
    person_labels = re.findall(r"\(인물:([^)]+)\)", visual_desc)
    core = re.sub(r"\([^)]*\)", "", visual_desc)
    tags = [t.strip().lower() for t in core.split(",") if t.strip()]
    tagset = set(tags)
    tagwords = set(w for t in tags for w in t.split())  # 복합 태그 단어 분해("people sitting"→people)

    place_clause = None
    if place_labels:
        p = place_labels[0].strip()
        place_clause = _PLACE.get(p, p) + "."

    # 주체(단어 단위 탐지) + 행동(복합 태그 포함)
    subj = next((ko for en, ko in _SUBJECT if en in tagwords), None)
    act = next((ko for en, ko in _ACTION.items() if en in tagset), None)

    def _objs(n=2):
        out = []
        for t in tags:
            if t in _OBJECT and _OBJECT[t] not in out:
                out.append(_OBJECT[t])
            if len(out) == n:
                break
        return out

    actor_clause = None
    if person_labels and not subj:
        name = person_labels[0].strip()
        actor_clause = (f"{name}{_josa(name, '이', '가')} {act}." if act
                        else f"{name}의 모습.")
    elif subj and act:
        actor_clause = f"{subj}{_josa(subj, '이', '가')} {act}."
    elif subj:
        actor_clause = f"{subj}{_josa(subj, '이', '가')} 보인다."
    else:
        objs = _objs(2)
        if len(objs) == 2:
            actor_clause = f"{objs[0]}{_josa(objs[0], '과', '와')} {objs[1]}{_josa(objs[1], '이', '가')} 보인다."
        elif objs:
            actor_clause = f"{objs[0]}{_josa(objs[0], '이', '가')} 보인다."

    parts = [c for c in (place_clause, actor_clause) if c]
    if not parts:
        return None
    return "(" + " ".join(parts) + ")"
