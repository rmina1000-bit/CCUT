import difflib
import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .contracts import (
    ChunkSelectionDraft,
    QwenChunkAdapterResult,
    QwenStoryAdapterResult,
    QwenStoryAdapterStatus,
    RoughCutAct,
    RoughCutStoryDraft,
    RoughCutStoryPhase,
    TranscriptSpan,
)


PROMPT_VERSION = "rough_cut_story_v1"
CHUNK_PROMPT_VERSION = "rough_cut_chunk_v1"
TWO_PASS_PROMPT_VERSION = "rough_cut_story_2pass_v1"
_FUZZY_HIGH_THRESHOLD = 0.90
_FUZZY_LOW_THRESHOLD = 0.65
_FUZZY_MARGIN_THRESHOLD = 0.20


@dataclass(frozen=True)
class QuoteRequest:
    act: RoughCutStoryPhase
    quote: str
    position: str


@dataclass(frozen=True)
class QuoteMapping:
    request: QuoteRequest
    status: str
    span_id: Optional[str]
    reason: str
    best_score: float
    second_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "act": self.request.act.value,
            "quote": self.request.quote,
            "position": self.request.position,
            "status": self.status,
            "span_id": self.span_id,
            "reason": self.reason,
            "best_score": self.best_score,
            "second_score": self.second_score,
            "margin": round(self.best_score - self.second_score, 4),
            "recommended_length": 12 <= len(self.request.quote) <= 25,
        }


class QwenStoryAdapter:
    def __init__(self, timeout_seconds: int = 90) -> None:
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
        feedback: Sequence[str] = (),
    ) -> QwenStoryAdapterResult:
        from engine import hub

        started_at = time.perf_counter()
        try:
            raw_output = hub._ollama_json(
                self._build_prompt(project_id, spans, feedback),
                timeout=self.timeout_seconds,
                temperature=0,
            )
        except Exception as exc:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.MODEL_CALL_FAILED,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                error_message=str(exc),
            )

        try:
            draft = RoughCutStoryDraft.from_model_output(project_id, raw_output)
        except ValueError as exc:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.CONTRACT_INVALID,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output=raw_output if isinstance(raw_output, dict) else None,
                error_message=str(exc),
            )

        return QwenStoryAdapterResult(
            status=QwenStoryAdapterStatus.OK,
            project_id=project_id,
            model=hub.HUB_MODEL,
            prompt_version=PROMPT_VERSION,
            input_span_count=len(spans),
            latency_ms=_elapsed_ms(started_at),
            draft=draft,
            raw_output=raw_output,
        )

    def generate_two_pass(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
    ) -> QwenStoryAdapterResult:
        from engine import hub

        started_at = time.perf_counter()
        try:
            pass1_prose = "".join(
                hub._ollama_stream(
                    self._build_pass1_prompt(spans),
                    timeout=self.timeout_seconds,
                    temperature=0.3,
                    num_predict=768,
                )
            ).strip()
        except Exception as exc:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.MODEL_CALL_FAILED,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=TWO_PASS_PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output={"model_call_count": 1},
                error_message=f"pass1_failed:{exc}",
            )
        if not pass1_prose:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.CONTRACT_INVALID,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=TWO_PASS_PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output={"model_call_count": 1},
                error_message="pass1_empty",
            )

        pass2_attempts = []
        best_attempt = None
        retry_feedback: Sequence[str] = ()
        for attempt_number in (1, 2):
            try:
                pass2_raw = hub._ollama_json(
                    self._build_pass2_prompt(
                        pass1_prose,
                        spans,
                        retry_feedback,
                    ),
                    timeout=self.timeout_seconds,
                    temperature=0,
                )
                requests = _parse_quote_requests(pass2_raw)
                mappings = map_quotes_to_spans(requests, spans)
                mappings = _reject_duplicate_mappings(mappings)
                attempt = {
                    "attempt": attempt_number,
                    "raw_output": pass2_raw,
                    "mappings": mappings,
                    "error": None,
                }
            except Exception as exc:
                attempt = {
                    "attempt": attempt_number,
                    "raw_output": None,
                    "mappings": (),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            pass2_attempts.append(_pass2_attempt_evidence(attempt))
            if best_attempt is None or _attempt_rank(attempt) > _attempt_rank(best_attempt):
                best_attempt = attempt

            unknown = [
                mapping
                for mapping in attempt["mappings"]
                if mapping.status == "unknown"
            ]
            mapped_phases = {
                mapping.request.act
                for mapping in attempt["mappings"]
                if mapping.span_id is not None
            }
            if (
                attempt["mappings"]
                and not unknown
                and mapped_phases == set(RoughCutStoryPhase)
            ):
                best_attempt = attempt
                break
            retry_feedback = _pass2_retry_feedback(attempt)

        if best_attempt is None or not best_attempt["mappings"]:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.CONTRACT_INVALID,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=TWO_PASS_PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output={
                    "model_call_count": 1 + len(pass2_attempts),
                    "pass1_prose": pass1_prose,
                    "pass2_attempts": pass2_attempts,
                },
                error_message="pass2_quotes_exhausted",
            )

        draft = _draft_from_mappings(
            project_id,
            best_attempt["mappings"],
            spans,
        )
        if draft is None:
            return QwenStoryAdapterResult(
                status=QwenStoryAdapterStatus.CONTRACT_INVALID,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=TWO_PASS_PROMPT_VERSION,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output={
                    "model_call_count": 1 + len(pass2_attempts),
                    "pass1_prose": pass1_prose,
                    "pass2_attempts": pass2_attempts,
                    "mapping": _mapping_evidence(best_attempt["mappings"]),
                },
                error_message="pass2_missing_story_act",
            )

        return QwenStoryAdapterResult(
            status=QwenStoryAdapterStatus.OK,
            project_id=project_id,
            model=hub.HUB_MODEL,
            prompt_version=TWO_PASS_PROMPT_VERSION,
            input_span_count=len(spans),
            latency_ms=_elapsed_ms(started_at),
            draft=draft,
            raw_output={
                "model_call_count": 1 + len(pass2_attempts),
                "pass1_prose": pass1_prose,
                "pass2_attempts": pass2_attempts,
                "pass2_quotes": [
                    mapping.request.quote
                    for mapping in best_attempt["mappings"]
                ],
                "mapping": _mapping_evidence(best_attempt["mappings"]),
            },
        )

    def extract_chunk(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
        chunk_index: int,
        chunk_count: int,
        feedback: Sequence[str] = (),
    ) -> QwenChunkAdapterResult:
        from engine import hub

        started_at = time.perf_counter()
        try:
            raw_output = hub._ollama_json(
                self._build_chunk_prompt(
                    project_id,
                    spans,
                    chunk_index,
                    chunk_count,
                    feedback,
                ),
                timeout=self.timeout_seconds,
                temperature=0,
            )
        except Exception as exc:
            return QwenChunkAdapterResult(
                status=QwenStoryAdapterStatus.MODEL_CALL_FAILED,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=CHUNK_PROMPT_VERSION,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                error_message=str(exc),
            )

        try:
            selection = ChunkSelectionDraft.from_model_output(raw_output)
        except ValueError as exc:
            return QwenChunkAdapterResult(
                status=QwenStoryAdapterStatus.CONTRACT_INVALID,
                project_id=project_id,
                model=hub.HUB_MODEL,
                prompt_version=CHUNK_PROMPT_VERSION,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                input_span_count=len(spans),
                latency_ms=_elapsed_ms(started_at),
                raw_output=raw_output if isinstance(raw_output, dict) else None,
                error_message=str(exc),
            )

        return QwenChunkAdapterResult(
            status=QwenStoryAdapterStatus.OK,
            project_id=project_id,
            model=hub.HUB_MODEL,
            prompt_version=CHUNK_PROMPT_VERSION,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            input_span_count=len(spans),
            latency_ms=_elapsed_ms(started_at),
            selection=selection,
            raw_output=raw_output,
        )

    @staticmethod
    def _build_prompt(
        project_id: str,
        spans: Sequence[TranscriptSpan],
        feedback: Sequence[str] = (),
    ) -> str:
        transcript = [
            {
                "span_id": span.span_id,
                "source_id": span.source_id,
                "start_ms": span.start_ms,
                "end_ms": span.end_ms,
                "text": span.text,
            }
            for span in spans
        ]
        payload = json.dumps(
            {"project_id": project_id, "transcript_spans": transcript},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        feedback_text = _feedback_text(feedback)
        return (
            "역할: 긴 영상 전사에서 핵심 이야기를 추리는 스토리 편집자.\n"
            "입력에는 텍스트가 있는 전사 조각만 있다. 입력에 없는 사실을 만들지 말고, "
            "핵심 조각을 골라 기승전결 순서로 구성하라.\n"
            "네 막은 모두 최소 1개 조각을 가져야 하며 한 막에 대부분을 몰지 마라. "
            "같은 ID를 반복하지 마라. premise와 summary는 선택한 전사의 실제 표현에 "
            "근거하고 전사에 없는 사건이나 문장을 만들지 마라.\n"
            "JSON 객체 하나만 반환하라. 키와 구조는 다음과 정확히 같아야 한다.\n"
            '{"premise":"한 문장 핵심","acts":['
            '{"phase":"gi","summary":"요약","span_ids":["ID"]},'
            '{"phase":"seung","summary":"요약","span_ids":["ID"]},'
            '{"phase":"jeon","summary":"요약","span_ids":["ID"]},'
            '{"phase":"gyeol","summary":"요약","span_ids":["ID"]}'
            '],"ordered_span_ids":["ID"]}\n'
            "phase 값과 순서는 gi, seung, jeon, gyeol로 고정한다. "
            "span_ids와 ordered_span_ids에는 입력의 span_id 문자열을 사용한다.\n"
            f"{feedback_text}"
            f"INPUT_JSON={payload}"
        )

    @staticmethod
    def _build_pass1_prompt(spans: Sequence[TranscriptSpan]) -> str:
        transcript = "\n".join(span.text for span in spans)
        return (
            "아래는 한 영상의 전사입니다.\n"
            "이 영상으로 어떤 이야기를 만들 수 있는지 한국어로 설명해 주세요.\n"
            "무슨 일이 있었고, 무엇이 달라졌고, 어떻게 마무리되는지 짚어 주세요.\n\n"
            f"{transcript}"
        )

    @staticmethod
    def _build_pass2_prompt(
        pass1_prose: str,
        spans: Sequence[TranscriptSpan],
        feedback: Sequence[str] = (),
    ) -> str:
        transcript = [
            {
                "position": _span_position(index, len(spans)),
                "text": span.text,
            }
            for index, span in enumerate(spans)
        ]
        payload = json.dumps(
            {
                "story_prose": pass1_prose,
                "transcript": transcript,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        feedback_text = _feedback_text(feedback)
        return (
            "이야기 산문을 따라 원본 전사에서 짧은 인용구를 골라 순서대로 배열하라.\n"
            "quote는 원문에서 그대로 12~25자를 발췌하고 position은 앞/중간/뒤로 적어라.\n"
            "기승전결이 모두 있도록 아래의 평평한 JSON 객체 하나만 반환하라.\n"
            '{"items":[{"act":"gi","quote":"원문 인용구","position":"앞"},'
            '{"act":"seung","quote":"원문 인용구","position":"중간"},'
            '{"act":"jeon","quote":"원문 인용구","position":"중간"},'
            '{"act":"gyeol","quote":"원문 인용구","position":"뒤"}]}\n'
            f"{feedback_text}"
            f"INPUT_JSON={payload}"
        )

    @staticmethod
    def _build_chunk_prompt(
        project_id: str,
        spans: Sequence[TranscriptSpan],
        chunk_index: int,
        chunk_count: int,
        feedback: Sequence[str] = (),
    ) -> str:
        selection_limit = max(1, math.floor(len(spans) * 0.4))
        if len(spans) >= 5:
            selection_limit = min(len(spans) - 1, max(4, selection_limit))
        transcript = [
            {
                "span_id": span.span_id,
                "source_id": span.source_id,
                "start_ms": span.start_ms,
                "end_ms": span.end_ms,
                "text": span.text,
            }
            for span in spans
        ]
        payload = json.dumps(
            {
                "project_id": project_id,
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "selection_limit": selection_limit,
                "transcript_spans": transcript,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        feedback_text = _feedback_text(feedback)
        return (
            "역할: 긴 영상 전사에서 핵심 이야기를 추리는 스토리 편집자.\n"
            "이것은 전체 전사의 한 구간이다. 텍스트에 실제로 있는 핵심만 고르고 "
            f"selected_span_ids는 최대 {selection_limit}개로 제한하라. "
            "ID를 만들거나 반복하지 마라. summary는 선택한 전사의 실제 단어를 써서 "
            "한 문장으로 작성하고 없는 사건을 만들지 마라.\n"
            "JSON 객체 하나만 반환하라. 구조는 다음과 정확히 같아야 한다.\n"
            '{"summary":"선택한 전사에 근거한 한 문장",'
            '"selected_span_ids":["ID"]}\n'
            f"{feedback_text}"
            f"INPUT_JSON={payload}"
        )


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _feedback_text(feedback: Sequence[str]) -> str:
    cleaned = [str(item).strip() for item in feedback if str(item).strip()]
    if not cleaned:
        return ""
    return (
        "이전 출력은 서버 검증에서 거부됐다. 아래 항목만 고쳐 다시 작성하라.\n"
        + "\n".join(f"- {item}" for item in cleaned)
        + "\n"
    )


def _parse_quote_requests(value: Any) -> Tuple[QuoteRequest, ...]:
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("pass2 items must be an array")
    requests = []
    for item in value["items"]:
        if not isinstance(item, dict):
            raise ValueError("pass2 item must be an object")
        try:
            act = RoughCutStoryPhase(item.get("act"))
        except (TypeError, ValueError) as exc:
            raise ValueError("pass2 act must be gi, seung, jeon, or gyeol") from exc
        quote = str(item.get("quote") or "").strip()
        position = str(item.get("position") or "").strip()
        if not quote:
            raise ValueError("pass2 quote must be nonempty")
        requests.append(QuoteRequest(act=act, quote=quote, position=position))
    if not requests:
        raise ValueError("pass2 returned no quotes")
    return tuple(requests)


def map_quotes_to_spans(
    requests: Sequence[QuoteRequest],
    spans: Sequence[TranscriptSpan],
) -> Tuple[QuoteMapping, ...]:
    return tuple(_map_quote(request, spans) for request in requests)


def _map_quote(
    request: QuoteRequest,
    spans: Sequence[TranscriptSpan],
) -> QuoteMapping:
    preferred = set(_preferred_span_indices(request.position, len(spans)))
    raw_exact = [
        index for index, span in enumerate(spans)
        if request.quote in span.text
    ]
    raw_exact = _prefer_position_matches(raw_exact, preferred)
    if len(raw_exact) == 1:
        return QuoteMapping(
            request=request,
            status="auto",
            span_id=spans[raw_exact[0]].span_id,
            reason="exact_match",
            best_score=1.0,
            second_score=0.0,
        )
    if len(raw_exact) > 1:
        return QuoteMapping(
            request=request,
            status="unknown",
            span_id=None,
            reason="ambiguous_exact_match",
            best_score=1.0,
            second_score=1.0,
        )

    quote_norm = _normalize_quote(request.quote)
    normalized_exact = [
        index for index, span in enumerate(spans)
        if quote_norm and quote_norm in _normalize_quote(span.text)
    ]
    normalized_exact = _prefer_position_matches(normalized_exact, preferred)
    if len(normalized_exact) == 1:
        return QuoteMapping(
            request=request,
            status="auto",
            span_id=spans[normalized_exact[0]].span_id,
            reason="normalized_match",
            best_score=1.0,
            second_score=0.0,
        )
    if len(normalized_exact) > 1:
        return QuoteMapping(
            request=request,
            status="unknown",
            span_id=None,
            reason="ambiguous_normalized_match",
            best_score=1.0,
            second_score=1.0,
        )

    ranked = []
    for index, span in enumerate(spans):
        score = _partial_similarity(quote_norm, _normalize_quote(span.text))
        if index in preferred:
            score = min(1.0, score + 0.02)
        ranked.append((score, index))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_index = ranked[0] if ranked else (0.0, -1)
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    if (
        best_index >= 0
        and best_score >= _FUZZY_HIGH_THRESHOLD
        and margin >= _FUZZY_MARGIN_THRESHOLD
    ):
        return QuoteMapping(
            request=request,
            status="candidate",
            span_id=spans[best_index].span_id,
            reason="high_similarity",
            best_score=round(best_score, 4),
            second_score=round(second_score, 4),
        )
    if best_score >= _FUZZY_LOW_THRESHOLD:
        reason = (
            "ambiguous_similarity"
            if margin < _FUZZY_MARGIN_THRESHOLD
            else "below_high_threshold"
        )
    else:
        reason = "low_similarity"
    return QuoteMapping(
        request=request,
        status="unknown",
        span_id=None,
        reason=reason,
        best_score=round(best_score, 4),
        second_score=round(second_score, 4),
    )


def _reject_duplicate_mappings(
    mappings: Sequence[QuoteMapping],
) -> Tuple[QuoteMapping, ...]:
    seen = set()
    result = []
    for mapping in mappings:
        if mapping.span_id is None or mapping.span_id not in seen:
            result.append(mapping)
            if mapping.span_id is not None:
                seen.add(mapping.span_id)
            continue
        result.append(
            QuoteMapping(
                request=mapping.request,
                status="unknown",
                span_id=None,
                reason="duplicate_mapping",
                best_score=mapping.best_score,
                second_score=mapping.second_score,
            )
        )
    return tuple(result)


def _draft_from_mappings(
    project_id: str,
    mappings: Sequence[QuoteMapping],
    spans: Sequence[TranscriptSpan],
) -> Optional[RoughCutStoryDraft]:
    span_by_id = {span.span_id: span for span in spans}
    by_act = {phase: [] for phase in RoughCutStoryPhase}
    ordered_ids = []
    for mapping in mappings:
        if mapping.span_id is None:
            continue
        by_act[mapping.request.act].append(mapping.span_id)
        ordered_ids.append(mapping.span_id)
    if any(not by_act[phase] for phase in RoughCutStoryPhase):
        return None
    acts = tuple(
        RoughCutAct(
            phase=phase,
            summary=span_by_id[by_act[phase][0]].text,
            span_ids=tuple(by_act[phase]),
        )
        for phase in RoughCutStoryPhase
    )
    return RoughCutStoryDraft(
        project_id=project_id,
        premise=span_by_id[ordered_ids[0]].text,
        acts=acts,
        ordered_span_ids=tuple(ordered_ids),
    )


def _mapping_evidence(mappings: Sequence[QuoteMapping]) -> Dict[str, Any]:
    counts = {"auto": 0, "candidate": 0, "unknown": 0}
    for mapping in mappings:
        counts[mapping.status] += 1
    return {
        **counts,
        "thresholds": {
            "high": _FUZZY_HIGH_THRESHOLD,
            "low": _FUZZY_LOW_THRESHOLD,
            "margin": _FUZZY_MARGIN_THRESHOLD,
        },
        "items": [mapping.to_dict() for mapping in mappings],
    }


def _pass2_attempt_evidence(attempt: Dict[str, Any]) -> Dict[str, Any]:
    mappings = attempt["mappings"]
    return {
        "attempt": attempt["attempt"],
        "error": attempt["error"],
        "quote_count": len(mappings),
        "mapping": _mapping_evidence(mappings),
        "raw_output": attempt["raw_output"],
    }


def _attempt_rank(attempt: Dict[str, Any]) -> Tuple[int, int, int]:
    mappings = attempt["mappings"]
    mapped_count = sum(mapping.span_id is not None for mapping in mappings)
    unknown_count = sum(mapping.status == "unknown" for mapping in mappings)
    phase_count = len({
        mapping.request.act
        for mapping in mappings
        if mapping.span_id is not None
    })
    return phase_count, mapped_count, -unknown_count


def _pass2_retry_feedback(attempt: Dict[str, Any]) -> Tuple[str, ...]:
    if attempt["error"]:
        return (
            "인용구를 읽을 수 없었다. items 배열과 네 act를 정확히 반환할 것",
        )
    unknown = [
        mapping.request.quote
        for mapping in attempt["mappings"]
        if mapping.status == "unknown"
    ]
    missing = [
        phase.value
        for phase in RoughCutStoryPhase
        if not any(
            mapping.request.act is phase and mapping.span_id is not None
            for mapping in attempt["mappings"]
        )
    ]
    feedback = []
    if unknown:
        feedback.append(
            "원문에서 찾지 못한 인용구를 원문 그대로 다시 고를 것: "
            + " | ".join(unknown)
        )
    if missing:
        feedback.append("비어 있는 act를 채울 것: " + ",".join(missing))
    return tuple(feedback)


def _normalize_quote(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(re.findall(r"[0-9a-z가-힣]+", normalized))


def _partial_similarity(short_text: str, long_text: str) -> float:
    if not short_text or not long_text:
        return 0.0
    if short_text in long_text or long_text in short_text:
        return min(len(short_text), len(long_text)) / max(
            len(short_text),
            len(long_text),
        )
    if len(short_text) > len(long_text):
        short_text, long_text = long_text, short_text
    window_size = len(short_text)
    return max(
        difflib.SequenceMatcher(
            None,
            short_text,
            long_text[index:index + window_size],
        ).ratio()
        for index in range(max(1, len(long_text) - window_size + 1))
    )


def _span_position(index: int, span_count: int) -> str:
    if span_count <= 0 or index < span_count / 3:
        return "앞"
    if index < span_count * 2 / 3:
        return "중간"
    return "뒤"


def _preferred_span_indices(position: str, span_count: int) -> Tuple[int, ...]:
    normalized = position.casefold()
    if "앞" in normalized or "front" in normalized:
        label = "앞"
    elif "중" in normalized or "middle" in normalized:
        label = "중간"
    elif "뒤" in normalized or "back" in normalized or "end" in normalized:
        label = "뒤"
    else:
        match = re.search(r"(\d+)", normalized)
        if not match:
            return ()
        chunk_number = max(1, int(match.group(1)))
        label = ("앞", "중간", "뒤")[min(2, chunk_number - 1)]
    return tuple(
        index
        for index in range(span_count)
        if _span_position(index, span_count) == label
    )


def _prefer_position_matches(
    matches: Sequence[int],
    preferred: set,
) -> List[int]:
    preferred_matches = [index for index in matches if index in preferred]
    return preferred_matches or list(matches)
