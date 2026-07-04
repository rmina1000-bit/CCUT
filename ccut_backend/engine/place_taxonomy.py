# -*- coding: utf-8 -*-
"""[PLACE-TAXONOMY P1] 장소 어휘 — VL 묘사(영문)·한국어 명령을 place_code로.

원칙:
- 장소 라벨은 '파생 데이터' — 인물(person_faces, 사용자 축복)과 달리 keyframe 묘사에서
  기계적으로 재생성 가능. 저장물은 캐시이며 재인덱스 때마다 다시 파생된다(스테일 불가능).
- 영문 키워드는 단어 경계 매칭 (실측 오탐: 'ward' ⊂ 'wardrobe').
- 판단 불가 = unknown (fail-silent, 조용한 성공 처리 금지).
"""
import re

# place_code -> (한국어 라벨, [영문 키워드(단어경계)], [한국어 키워드(부분일치)])
TAXONOMY = {
    "hospital": ("병원", ["hospital", "clinic", "ward", "patient", "nurse", "iv pole",
                          "medical equipment", "medical"], ["병원", "병실", "링거", "입원"]),
    "home": ("집", ["bedroom", "living room", "kitchen", "sofa", "couch", "pillow",
                    "blanket", "wardrobe", "bed"], ["침실", "거실", "부엌", "안방"]),
    "school": ("학교", ["classroom", "school"], ["교실", "학교"]),
    "playground": ("운동장", ["playground", "schoolyard", "field"], ["운동장", "놀이터"]),
    "gym": ("체육관", ["gym", "gymnasium"], ["체육관"]),
    "beach": ("바다", ["beach", "sand", "wave", "waves", "ocean", "sea", "shore"],
              ["바다", "해변", "모래", "바닷가", "해안"]),
    "river": ("강", ["river", "stream", "creek"], ["강가", "계곡"]),
    "lake": ("호수", ["lake"], ["호수"]),
    "mountain": ("산", ["mountain", "hiking", "trail"], ["등산"]),
    "street": ("길거리", ["street", "road", "alley", "sidewalk", "crosswalk"],
               ["길거리", "도로", "골목"]),
    "subway": ("지하철", ["subway", "train", "platform", "carriage"], ["지하철", "열차", "전철"]),
    "office": ("사무실", ["office", "meeting room"], ["사무실", "회사", "회의실"]),
    "shopping": ("매장", ["mall", "store", "shop", "market"], ["쇼핑몰", "매장", "상점", "시장"]),
    "rink": ("빙상장", ["ice rink", "skating"], ["빙상장", "스케이트장"]),
    "indoor": ("실내", ["ceiling", "hallway", "corridor", "indoor", "room", "door", "wall"],
               ["실내"]),
    "outdoor": ("실외", ["outdoor", "park", "grass", "tree", "sky", "exterior"],
                ["실외", "야외", "공원"]),
}
_GENERIC = ("indoor", "outdoor")  # 구체 장소가 있으면 밀려나는 범용 코드

_EN_RE = {code: re.compile(r"\b(" + "|".join(re.escape(k) for k in en) + r")\b")
          for code, (_lbl, en, _ko) in TAXONOMY.items() if en}


def derive_places(text):
    """묘사/텍스트 → [(place_code, label, evidence)] (구체 우선, 범용은 구체 없을 때만).
    입력이 비면 [] (unknown 처리는 호출부)."""
    t = (text or "").lower()
    if not t.strip():
        return []
    hits = []
    for code, (label, _en, ko) in TAXONOMY.items():
        ev = []
        m = _EN_RE.get(code)
        if m:
            ev += sorted(set(g if isinstance(g, str) else g[0] for g in m.findall(t)))
        ev += [k for k in ko if k in t]
        if ev:
            hits.append((code, label, ",".join(dict.fromkeys(ev))))
    specific = [h for h in hits if h[0] not in _GENERIC]
    return specific if specific else hits[:1]


def resolve_place_query(text):
    """명령문에서 장소 조건 감지 → {"code","label","matched"} | None.
    한국어 키워드 부분일치 — 단, 1글자 키워드는 오탐이라 제외
    (실측: '편집'⊂'집', '강아지'⊂'강'). 명령용이라 범용(실내/실외)도 허용."""
    t = (text or "")
    for code, (label, _en, ko) in TAXONOMY.items():
        for k in [label] + ko:
            if k and len(k) >= 2 and k in t:
                return {"code": code, "label": label, "matched": k}
    return None
