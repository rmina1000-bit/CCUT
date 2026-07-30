from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .contracts import (
    ChunkSelectionDraft,
    QwenStoryAdapterStatus,
    RoughCutAct,
    RoughCutStoryDraft,
    RoughCutStoryPhase,
    TranscriptSpan,
)
from .qwen_story_adapter import QwenStoryAdapter
from .validator import (
    RoughCutValidationIssue,
    condense_story_draft,
    validate_chunk_selection,
    validate_story_draft,
)


class RoughCutBuildStatus(str, Enum):
    OK = "ok"
    INSUFFICIENT_TEXT = "insufficient_text"
    CHUNK_EXHAUSTED = "chunk_exhausted"
    ARRANGEMENT_EXHAUSTED = "arrangement_exhausted"


@dataclass(frozen=True)
class RoughCutAttempt:
    stage: str
    unit_index: int
    attempt: int
    adapter_status: str
    rejection_codes: Tuple[str, ...]
    latency_ms: int
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "unit_index": self.unit_index,
            "attempt": self.attempt,
            "adapter_status": self.adapter_status,
            "rejection_codes": list(self.rejection_codes),
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class RoughCutBuildResult:
    status: RoughCutBuildStatus
    project_id: str
    input_span_count: int
    chunk_count: int
    model_call_count: int
    attempts: Tuple[RoughCutAttempt, ...]
    draft: Optional[RoughCutStoryDraft] = None
    failure_issues: Tuple[RoughCutValidationIssue, ...] = ()
    error_message: Optional[str] = None
    generation_evidence: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.status is RoughCutBuildStatus.OK

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "project_id": self.project_id,
            "input_span_count": self.input_span_count,
            "chunk_count": self.chunk_count,
            "model_call_count": self.model_call_count,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "draft": self.draft.to_dict() if self.draft else None,
            "failure_issues": [
                issue.to_dict() for issue in self.failure_issues
            ],
            "error_message": self.error_message,
            "generation_evidence": self.generation_evidence,
        }


def chunk_transcript_spans(
    spans: Sequence[TranscriptSpan],
    *,
    max_spans: int = 48,
    max_text_chars: int = 12000,
) -> Tuple[Tuple[TranscriptSpan, ...], ...]:
    if max_spans < 1 or max_text_chars < 1:
        raise ValueError("chunk limits must be positive")

    chunks: List[Tuple[TranscriptSpan, ...]] = []
    current: List[TranscriptSpan] = []
    current_chars = 0
    for span in spans:
        span_chars = len(span.text)
        would_overflow = current and (
            len(current) >= max_spans
            or current_chars + span_chars > max_text_chars
        )
        if would_overflow:
            chunks.append(tuple(current))
            current = []
            current_chars = 0
        current.append(span)
        current_chars += span_chars
    if current:
        chunks.append(tuple(current))
    return tuple(chunks)


class RoughCutStoryBuilder:
    def __init__(
        self,
        adapter: Optional[QwenStoryAdapter] = None,
        *,
        max_attempts: int = 3,
        max_spans_per_chunk: int = 48,
        max_text_chars_per_chunk: int = 12000,
    ) -> None:
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self.adapter = adapter or QwenStoryAdapter()
        self.max_attempts = max_attempts
        self.max_spans_per_chunk = max_spans_per_chunk
        self.max_text_chars_per_chunk = max_text_chars_per_chunk

    def build(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
    ) -> RoughCutBuildResult:
        return self._build(
            project_id,
            spans,
            use_two_pass=False,
            recommendation_span_ids=(),
        )

    def build_two_pass(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
        *,
        recommendation_span_ids: Sequence[str] = (),
    ) -> RoughCutBuildResult:
        return self._build(
            project_id,
            spans,
            use_two_pass=True,
            recommendation_span_ids=recommendation_span_ids,
        )

    def _build(
        self,
        project_id: str,
        spans: Sequence[TranscriptSpan],
        *,
        use_two_pass: bool,
        recommendation_span_ids: Sequence[str],
    ) -> RoughCutBuildResult:
        if len(spans) < 5:
            return RoughCutBuildResult(
                status=RoughCutBuildStatus.INSUFFICIENT_TEXT,
                project_id=project_id,
                input_span_count=len(spans),
                chunk_count=0,
                model_call_count=0,
                attempts=(),
                error_message="at least five transcript spans are required",
            )

        chunks = chunk_transcript_spans(
            spans,
            max_spans=self.max_spans_per_chunk,
            max_text_chars=self.max_text_chars_per_chunk,
        )
        attempts: List[RoughCutAttempt] = []
        candidate_spans: List[TranscriptSpan] = list(spans) if use_two_pass else []
        span_by_id = {span.span_id: span for span in spans}

        if not use_two_pass:
            for chunk_index, chunk in enumerate(chunks):
                selection, issues, error_message = self._extract_valid_chunk(
                    project_id,
                    chunk,
                    chunk_index,
                    len(chunks),
                    attempts,
                )
                if selection is None:
                    return RoughCutBuildResult(
                        status=RoughCutBuildStatus.CHUNK_EXHAUSTED,
                        project_id=project_id,
                        input_span_count=len(spans),
                        chunk_count=len(chunks),
                        model_call_count=len(attempts),
                        attempts=tuple(attempts),
                        failure_issues=issues,
                        error_message=error_message,
                    )
                candidate_spans.extend(
                    span_by_id[span_id]
                    for span_id in selection.selected_span_ids
                )

        draft, issues, error_message, generation_evidence = self._arrange_valid_story(
            project_id,
            candidate_spans,
            len(spans),
            attempts,
            use_two_pass=use_two_pass,
        )
        if draft is None:
            fallback = (
                _recommendation_fallback_draft(
                    project_id,
                    candidate_spans,
                    recommendation_span_ids,
                )
                if use_two_pass
                else None
            )
            if fallback is not None:
                fallback_evidence = dict(generation_evidence or {})
                fallback_evidence["fallback"] = {
                    "kind": "existing_recommendation",
                    "reason": "qwen_arrangement_failed",
                    "selected_span_count": len(fallback.ordered_span_ids),
                }
                return RoughCutBuildResult(
                    status=RoughCutBuildStatus.OK,
                    project_id=project_id,
                    input_span_count=len(spans),
                    chunk_count=len(chunks),
                    model_call_count=_actual_model_call_count(
                        attempts,
                        fallback_evidence,
                    ),
                    attempts=tuple(attempts),
                    draft=fallback,
                    generation_evidence=fallback_evidence,
                )
            return RoughCutBuildResult(
                status=(
                    RoughCutBuildStatus.INSUFFICIENT_TEXT
                    if use_two_pass
                    else RoughCutBuildStatus.ARRANGEMENT_EXHAUSTED
                ),
                project_id=project_id,
                input_span_count=len(spans),
                chunk_count=len(chunks),
                model_call_count=_actual_model_call_count(
                    attempts,
                    generation_evidence,
                ),
                attempts=tuple(attempts),
                failure_issues=issues,
                error_message=(
                    f"{error_message or 'qwen_arrangement_failed'};"
                    "recommendation_fallback_unavailable"
                    if use_two_pass
                    else error_message
                ),
                generation_evidence=generation_evidence,
            )
        return RoughCutBuildResult(
            status=RoughCutBuildStatus.OK,
            project_id=project_id,
            input_span_count=len(spans),
            chunk_count=len(chunks),
            model_call_count=_actual_model_call_count(
                attempts,
                generation_evidence,
            ),
            attempts=tuple(attempts),
            draft=draft,
            generation_evidence=generation_evidence,
        )

    def _extract_valid_chunk(
        self,
        project_id: str,
        chunk: Sequence[TranscriptSpan],
        chunk_index: int,
        chunk_count: int,
        attempts: List[RoughCutAttempt],
    ) -> Tuple[
        Optional[ChunkSelectionDraft],
        Tuple[RoughCutValidationIssue, ...],
        Optional[str],
    ]:
        feedback: Tuple[str, ...] = ()
        previous_failure = None
        repeated_failure_count = 0
        last_issues: Tuple[RoughCutValidationIssue, ...] = ()
        last_error = None

        for attempt_number in range(1, self.max_attempts + 1):
            result = self.adapter.extract_chunk(
                project_id,
                chunk,
                chunk_index,
                chunk_count,
                feedback,
            )
            if result.status is QwenStoryAdapterStatus.OK:
                last_error = None
                validation = validate_chunk_selection(result.selection, chunk)
                last_issues = validation.issues
                fingerprint = ("validation",) + validation.codes
                attempts.append(
                    RoughCutAttempt(
                        stage="chunk",
                        unit_index=chunk_index,
                        attempt=attempt_number,
                        adapter_status=result.status.value,
                        rejection_codes=validation.codes,
                        latency_ms=result.latency_ms,
                    )
                )
                if validation.accepted:
                    return result.selection, (), None
                feedback = tuple(
                    f"{issue.code.value}: {issue.detail}"
                    for issue in validation.issues
                )
            else:
                last_issues = ()
                last_error = result.error_message
                fingerprint = (
                    "adapter",
                    result.status.value,
                    result.error_message or "",
                )
                attempts.append(
                    RoughCutAttempt(
                        stage="chunk",
                        unit_index=chunk_index,
                        attempt=attempt_number,
                        adapter_status=result.status.value,
                        rejection_codes=(),
                        latency_ms=result.latency_ms,
                        error_message=result.error_message,
                    )
                )
                feedback = (
                    f"{result.status.value}: {result.error_message or 'unknown error'}",
                )

            repeated_failure_count = (
                repeated_failure_count + 1
                if fingerprint == previous_failure
                else 1
            )
            previous_failure = fingerprint
            if repeated_failure_count >= 2:
                break

        return None, last_issues, last_error

    def _arrange_valid_story(
        self,
        project_id: str,
        candidate_spans: Sequence[TranscriptSpan],
        total_span_count: int,
        attempts: List[RoughCutAttempt],
        *,
        use_two_pass: bool = False,
    ) -> Tuple[
        Optional[RoughCutStoryDraft],
        Tuple[RoughCutValidationIssue, ...],
        Optional[str],
        Optional[Dict[str, Any]],
    ]:
        feedback: Tuple[str, ...] = ()
        previous_failure = None
        repeated_failure_count = 0
        last_issues: Tuple[RoughCutValidationIssue, ...] = ()
        last_error = None
        last_evidence = None
        attempt_limit = 1 if use_two_pass else self.max_attempts

        for attempt_number in range(1, attempt_limit + 1):
            result = (
                self.adapter.generate_two_pass(project_id, candidate_spans)
                if use_two_pass
                else self.adapter.generate(project_id, candidate_spans, feedback)
            )
            last_evidence = result.raw_output
            if result.status is QwenStoryAdapterStatus.OK:
                last_error = None
                validation = validate_story_draft(
                    result.draft,
                    candidate_spans,
                    total_transcript_span_count=total_span_count,
                )
                last_issues = validation.issues
                if (
                    use_two_pass
                    and "not_shortened" in validation.codes
                ):
                    condensed, condense_evidence = condense_story_draft(
                        result.draft,
                        candidate_spans,
                        total_transcript_span_count=total_span_count,
                    )
                    last_evidence = dict(last_evidence or {})
                    last_evidence["server_condense"] = condense_evidence
                    validation = validate_story_draft(
                        condensed,
                        candidate_spans,
                        total_transcript_span_count=total_span_count,
                    )
                    result = result.__class__(
                        status=result.status,
                        project_id=result.project_id,
                        model=result.model,
                        prompt_version=result.prompt_version,
                        input_span_count=result.input_span_count,
                        latency_ms=result.latency_ms,
                        draft=condensed,
                        raw_output=last_evidence,
                        error_message=result.error_message,
                    )
                    last_issues = validation.issues
                fingerprint = ("validation",) + validation.codes
                attempts.append(
                    RoughCutAttempt(
                        stage="arrangement",
                        unit_index=0,
                        attempt=attempt_number,
                        adapter_status=result.status.value,
                        rejection_codes=validation.codes,
                        latency_ms=result.latency_ms,
                    )
                )
                if validation.accepted:
                    return result.draft, (), None, last_evidence
                feedback = tuple(
                    f"{issue.code.value}: {issue.detail}"
                    for issue in validation.issues
                )
            else:
                last_issues = ()
                last_error = result.error_message
                fingerprint = (
                    "adapter",
                    result.status.value,
                    result.error_message or "",
                )
                attempts.append(
                    RoughCutAttempt(
                        stage="arrangement",
                        unit_index=0,
                        attempt=attempt_number,
                        adapter_status=result.status.value,
                        rejection_codes=(),
                        latency_ms=result.latency_ms,
                        error_message=result.error_message,
                    )
                )
                feedback = (
                    f"{result.status.value}: {result.error_message or 'unknown error'}",
                )

            repeated_failure_count = (
                repeated_failure_count + 1
                if fingerprint == previous_failure
                else 1
            )
            previous_failure = fingerprint
            if repeated_failure_count >= 2:
                break

        return None, last_issues, last_error, last_evidence


def _actual_model_call_count(
    attempts: Sequence[RoughCutAttempt],
    generation_evidence: Optional[Dict[str, Any]],
) -> int:
    chunk_calls = sum(attempt.stage == "chunk" for attempt in attempts)
    if (
        not generation_evidence
        or "model_call_count" not in generation_evidence
    ):
        return len(attempts)
    return chunk_calls + int(generation_evidence.get("model_call_count") or 1)


def _recommendation_fallback_draft(
    project_id: str,
    candidate_spans: Sequence[TranscriptSpan],
    recommendation_span_ids: Sequence[str],
) -> Optional[RoughCutStoryDraft]:
    span_by_id = {span.span_id: span for span in candidate_spans}
    selected = []
    seen = set()
    for span_id in recommendation_span_ids:
        if span_id in span_by_id and span_id not in seen:
            selected.append(span_id)
            seen.add(span_id)
    if len(selected) < 4:
        return None

    groups = [selected[index::4] for index in range(4)]
    if any(not group for group in groups):
        return None
    acts = tuple(
        RoughCutAct(
            phase=phase,
            summary=span_by_id[group[0]].text,
            span_ids=tuple(group),
        )
        for phase, group in zip(RoughCutStoryPhase, groups)
    )
    return RoughCutStoryDraft(
        project_id=project_id,
        premise=span_by_id[selected[0]].text,
        acts=acts,
        ordered_span_ids=tuple(selected),
    )
