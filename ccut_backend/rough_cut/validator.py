import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Sequence, Tuple

from .contracts import ChunkSelectionDraft, RoughCutStoryDraft, TranscriptSpan


class RoughCutRejectionCode(str, Enum):
    UNKNOWN_ID = "unknown_id"
    DUPLICATE_ID = "duplicate_id"
    EMPTY_TEXT = "empty_text"
    NOT_SHORTENED = "not_shortened"
    UNGROUNDED_TEXT = "ungrounded_text"
    WEAK_TURN = "weak_turn"


@dataclass(frozen=True)
class RoughCutValidationIssue:
    code: RoughCutRejectionCode
    detail: str

    def to_dict(self) -> dict:
        return {"code": self.code.value, "detail": self.detail}


@dataclass(frozen=True)
class RoughCutValidationResult:
    issues: Tuple[RoughCutValidationIssue, ...]

    @property
    def accepted(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> Tuple[str, ...]:
        return tuple(issue.code.value for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "issues": [issue.to_dict() for issue in self.issues],
        }


_GROUND_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
_GROUNDING_MIN_RATIO = 0.30
_WEAK_TURN_DOMINANT_RATIO = 0.70


def validate_chunk_selection(
    selection: ChunkSelectionDraft,
    available_spans: Sequence[TranscriptSpan],
) -> RoughCutValidationResult:
    span_by_id = {span.span_id: span for span in available_spans}
    selected_ids = selection.selected_span_ids
    issues: List[RoughCutValidationIssue] = []

    _append_unknown_issue(issues, selected_ids, span_by_id)
    _append_duplicate_issue(issues, selected_ids)
    selected_spans = [
        span_by_id[span_id]
        for span_id in selected_ids
        if span_id in span_by_id
    ]
    if (
        not selection.summary.strip()
        or not selected_spans
        or any(not span.text.strip() for span in selected_spans)
    ):
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.EMPTY_TEXT,
                "chunk summary and selected transcript text must be nonempty",
            )
        )
    evidence = " ".join(span.text for span in selected_spans)
    if selection.summary.strip() and not _is_grounded(selection.summary, evidence):
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.UNGROUNDED_TEXT,
                "chunk summary has less than 30% lexical support",
            )
        )
    return RoughCutValidationResult(tuple(_unique_issues(issues)))


def validate_story_draft(
    draft: RoughCutStoryDraft,
    allowed_spans: Sequence[TranscriptSpan],
    *,
    total_transcript_span_count: int,
) -> RoughCutValidationResult:
    span_by_id = {span.span_id: span for span in allowed_spans}
    ordered_ids = draft.ordered_span_ids
    act_ids = tuple(span_id for act in draft.acts for span_id in act.span_ids)
    referenced_ids = ordered_ids + act_ids
    issues: List[RoughCutValidationIssue] = []

    _append_unknown_issue(issues, referenced_ids, span_by_id)
    _append_duplicate_issue(issues, ordered_ids)
    _append_duplicate_issue(issues, act_ids)

    selected_spans = [
        span_by_id[span_id]
        for span_id in ordered_ids
        if span_id in span_by_id
    ]
    empty_story_text = (
        not draft.premise.strip()
        or any(not act.summary.strip() for act in draft.acts)
        or not selected_spans
        or any(not span.text.strip() for span in selected_spans)
    )
    if empty_story_text:
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.EMPTY_TEXT,
                "premise, act summaries, and selected transcript text must be nonempty",
            )
        )

    selected_count = len(
        {span_id for span_id in ordered_ids if span_id in span_by_id}
    )
    if selected_count >= total_transcript_span_count:
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.NOT_SHORTENED,
                f"selected={selected_count}, transcript={total_transcript_span_count}",
            )
        )

    selected_evidence = " ".join(span.text for span in selected_spans)
    if draft.premise.strip() and not _is_grounded(draft.premise, selected_evidence):
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.UNGROUNDED_TEXT,
                "premise has less than 30% lexical support",
            )
        )
    for act in draft.acts:
        evidence = " ".join(
            span_by_id[span_id].text
            for span_id in act.span_ids
            if span_id in span_by_id
        )
        if act.summary.strip() and not _is_grounded(act.summary, evidence):
            issues.append(
                RoughCutValidationIssue(
                    RoughCutRejectionCode.UNGROUNDED_TEXT,
                    f"{act.phase.value} summary has less than 30% lexical support",
                )
            )

    act_counts = [len(act.span_ids) for act in draft.acts]
    total_act_ids = sum(act_counts)
    act_set_matches_order = set(act_ids) == set(ordered_ids)
    dominant_ratio = (
        max(act_counts) / total_act_ids
        if total_act_ids
        else 1.0
    )
    if (
        any(count == 0 for count in act_counts)
        or dominant_ratio > _WEAK_TURN_DOMINANT_RATIO
        or not act_set_matches_order
    ):
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.WEAK_TURN,
                "act_counts="
                f"{'/'.join(str(count) for count in act_counts)}, "
                f"dominant_ratio={dominant_ratio:.4f}, "
                f"act_set_matches_order={act_set_matches_order}",
            )
        )

    return RoughCutValidationResult(tuple(_unique_issues(issues)))


def _append_unknown_issue(
    issues: List[RoughCutValidationIssue],
    span_ids: Iterable[str],
    span_by_id: Dict[str, TranscriptSpan],
) -> None:
    unknown = sorted({span_id for span_id in span_ids if span_id not in span_by_id})
    if unknown:
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.UNKNOWN_ID,
                "unknown=" + ",".join(unknown),
            )
        )


def _append_duplicate_issue(
    issues: List[RoughCutValidationIssue],
    span_ids: Sequence[str],
) -> None:
    seen = set()
    duplicates = []
    for span_id in span_ids:
        if span_id in seen and span_id not in duplicates:
            duplicates.append(span_id)
        seen.add(span_id)
    if duplicates:
        issues.append(
            RoughCutValidationIssue(
                RoughCutRejectionCode.DUPLICATE_ID,
                "duplicates=" + ",".join(duplicates),
            )
        )


def _is_grounded(statement: str, evidence: str) -> bool:
    tokens = _GROUND_TOKEN_RE.findall(statement.casefold())
    if not tokens:
        return True
    haystack = evidence.casefold()
    hit_count = sum(
        1
        for token in tokens
        if token in haystack or token[:2] in haystack
    )
    return (hit_count / len(tokens)) >= _GROUNDING_MIN_RATIO


def _unique_issues(
    issues: Sequence[RoughCutValidationIssue],
) -> List[RoughCutValidationIssue]:
    unique: List[RoughCutValidationIssue] = []
    seen = set()
    for issue in issues:
        key = (issue.code, issue.detail)
        if key not in seen:
            unique.append(issue)
            seen.add(key)
    return unique

