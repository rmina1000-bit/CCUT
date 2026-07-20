"""[RUBRIC-1] EditRubric — 다조건 채점표.

설계 원리: 큐원은 이미 명령을 이해한다. 그 이해를 단일 theme 문자열로 압축해
hub.plan_edit에 넘기면 keep/exclude 중 하나가 소실된다(실측: hub.py의
extract_intent/plan_edit — keep과 exclude가 동시에 있어도 `theme = keep or exclude`
단일계라 exclude가 완전히 버려짐). EditRubric은 keep/exclude를 대등한 1급 리스트로
보존해 실행에 넘기고, 실행 후 같은 채점표로 결과를 검증(required 위반 탐지)한다.

순수 데이터/헬퍼 모듈이다 — 다른 CCUT 모듈(hub/proposal_engine/main 등)을 import하지
않는다. 부작용 없음, 순환의존 없음. CCUT_RUBRIC_ENABLED 게이트 판단도 여기서 하지
않는다(호출측 책임) — 이 파일 자체는 gate 존재를 모른다.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

_NEGATIVE_MARKERS = ("빼", "제외", "말고", "없이", "없는", "없게", "없도록", "줄여", "줄이", "덜", "보다")


def _term_key(term: str) -> str:
    return " ".join(str(term or "").lower().split())


@dataclass
class RubricTerm:
    term: str
    weight: float = 1.0
    required: bool = True


@dataclass
class EditRubric:
    keep: list = field(default_factory=list)       # list[RubricTerm]
    exclude: list = field(default_factory=list)     # list[RubricTerm] — keep과 대등한 1급 필드
    count: Optional[int] = None
    style: list = field(default_factory=list)       # list[str]
    raw_goal: str = ""                               # 압축 전 원문 보존(큐원 입력 그대로)

    def to_dict(self) -> dict:
        return {
            "keep": [asdict(t) for t in self.keep],
            "exclude": [asdict(t) for t in self.exclude],
            "count": self.count,
            "style": list(self.style),
            "raw_goal": self.raw_goal,
        }

    def required_keep_terms(self):
        return [t.term for t in self.keep if t.required]

    def required_exclude_terms(self):
        return [t.term for t in self.exclude if t.required]

    def is_compound(self) -> bool:
        """keep과 exclude가 동시에 필요한 복합조건인가 — 이게 True인데 실행층이
        단일 theme만 본다면 정확히 그 지점에서 손실이 난다."""
        return bool(self.required_keep_terms()) and bool(self.required_exclude_terms())

    def sanitize_polarity_overlap(self, raw_goal: str = "") -> "EditRubric":
        """모델이 같은 term을 keep/exclude 양쪽에 넣은 경우 한쪽을 제거한다.
        부정 표현이 없으면 keep 의도가 우선이고, 부정 표현이 있으면 exclude 의도가 우선이다."""
        has_negative = any(m in (raw_goal or "") for m in _NEGATIVE_MARKERS)
        if not has_negative:
            self.exclude = []
            return self
        keep_keys = {_term_key(t.term) for t in self.keep if t.term}
        exclude_keys = {_term_key(t.term) for t in self.exclude if t.term}
        overlap = {k for k in keep_keys & exclude_keys if k}
        if not overlap:
            return self
        self.keep = [t for t in self.keep if _term_key(t.term) not in overlap]
        return self

    @classmethod
    def from_intent(cls, intent: dict, raw_goal: str = "") -> "EditRubric":
        """hub.extract_intent()가 이미 산출한 intent dict에서 손실 없이 구성.
        intent에 keep_terms/exclude_terms(C1 복합 파서 결과)가 있으면 그걸 우선 쓰고,
        없으면 단일 keep/exclude 문자열을 1항짜리 리스트로 승격한다(정보 손실 0)."""
        intent = intent or {}
        keep_terms = intent.get("keep_terms") or ([intent["keep"]] if intent.get("keep") else [])
        exclude_terms = intent.get("exclude_terms") or ([intent["exclude"]] if intent.get("exclude") else [])
        return cls(
            keep=[RubricTerm(term=t, weight=1.0, required=True) for t in keep_terms if t],
            exclude=[RubricTerm(term=t, weight=1.0, required=True) for t in exclude_terms if t],
            count=intent.get("count"),
            style=[],
            raw_goal=raw_goal or "",
        ).sanitize_polarity_overlap(raw_goal or "")

    @classmethod
    def from_qwen_json(cls, data: dict, raw_goal: str = "") -> "EditRubric":
        """converse.py 구조화 출력(JSON schema 구속) 파싱용. 스키마 밖 필드는 무시,
        타입 안 맞으면 조용히 빈 값 — 이 함수는 신뢰 경계(모델 출력)를 다루므로
        예외를 던지지 않는다(호출측이 항상 유효한 EditRubric을 받게)."""
        def _terms(items):
            out = []
            if not isinstance(items, list):
                return out
            for it in items:
                if isinstance(it, str) and it.strip():
                    out.append(RubricTerm(term=it.strip(), weight=1.0, required=True))
                elif isinstance(it, dict) and it.get("term"):
                    w = it.get("weight", 1.0)
                    out.append(RubricTerm(
                        term=str(it["term"]).strip(),
                        weight=float(w) if isinstance(w, (int, float)) else 1.0,
                        required=bool(it.get("required", True)),
                    ))
            return out

        data = data or {}
        count = data.get("count")
        count = int(count) if isinstance(count, (int, float)) and 1 <= int(count) <= 40 else None
        style = data.get("style") if isinstance(data.get("style"), list) else []
        return cls(
            keep=_terms(data.get("keep")),
            exclude=_terms(data.get("exclude")),
            count=count,
            style=[str(s) for s in style if s],
            raw_goal=raw_goal or str(data.get("raw_goal") or ""),
        ).sanitize_polarity_overlap(raw_goal or str(data.get("raw_goal") or ""))
