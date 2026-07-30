import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .contracts import (
    ChunkSelectionDraft,
    RoughCutAct,
    RoughCutStoryDraft,
    TranscriptSpan,
)


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


def condense_story_draft(
    draft: RoughCutStoryDraft,
    allowed_spans: Sequence[TranscriptSpan],
    *,
    total_transcript_span_count: int,
    target_count: int = 0,
) -> Tuple[RoughCutStoryDraft, Dict[str, Any]]:
    span_by_id = {span.span_id: span for span in allowed_spans}
    available_count = len({
        span_id
        for act in draft.acts
        for span_id in act.span_ids
        if span_id in span_by_id
    })
    if target_count <= 0:
        target_count = max(4, round(total_transcript_span_count * 0.4))
    target_count = min(
        max(4, target_count),
        max(4, total_transcript_span_count - 1),
        available_count,
    )

    act_ids = [
        [span_id for span_id in act.span_ids if span_id in span_by_id]
        for act in draft.acts
    ]
    if any(not ids for ids in act_ids) or target_count < len(act_ids):
        return draft, {
            "applied": False,
            "reason": "cannot_preserve_all_acts",
            "target_count": target_count,
        }

    quotas = [1] * len(act_ids)
    remaining = target_count - len(act_ids)
    while remaining > 0:
        progressed = False
        for index, ids in enumerate(act_ids):
            if quotas[index] >= len(ids):
                continue
            quotas[index] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break

    selected_by_act = [
        _evenly_spaced_ids(ids, quota)
        for ids, quota in zip(act_ids, quotas)
    ]
    _preserve_source_representatives(
        selected_by_act,
        act_ids,
        span_by_id,
        target_count,
    )
    condensed_acts = tuple(
        RoughCutAct(
            phase=act.phase,
            summary=span_by_id[selected_ids[0]].text,
            span_ids=tuple(selected_ids),
        )
        for act, selected_ids in zip(draft.acts, selected_by_act)
    )
    ordered_ids = tuple(
        span_id
        for selected_ids in selected_by_act
        for span_id in selected_ids
    )
    condensed = RoughCutStoryDraft(
        project_id=draft.project_id,
        premise=span_by_id[ordered_ids[0]].text,
        acts=condensed_acts,
        ordered_span_ids=ordered_ids,
    )
    before_sources = {
        span_by_id[span_id].source_id
        for ids in act_ids
        for span_id in ids
    }
    after_sources = {
        span_by_id[span_id].source_id
        for span_id in ordered_ids
    }
    return condensed, {
        "applied": True,
        "reason": "server_target_condense",
        "before_count": available_count,
        "target_count": target_count,
        "after_count": len(ordered_ids),
        "act_quotas": quotas,
        "source_count_before": len(before_sources),
        "source_count_after": len(after_sources),
    }


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


def _evenly_spaced_ids(span_ids: Sequence[str], count: int) -> List[str]:
    if count >= len(span_ids):
        return list(span_ids)
    if count <= 1:
        return [span_ids[len(span_ids) // 2]]
    indices = [
        round(index * (len(span_ids) - 1) / (count - 1))
        for index in range(count)
    ]
    return [span_ids[index] for index in indices]


def _preserve_source_representatives(
    selected_by_act: List[List[str]],
    act_ids: Sequence[Sequence[str]],
    span_by_id: Dict[str, TranscriptSpan],
    target_count: int,
) -> None:
    all_sources = []
    for ids in act_ids:
        for span_id in ids:
            source_id = span_by_id[span_id].source_id
            if source_id not in all_sources:
                all_sources.append(source_id)
    required_sources = set(all_sources[:target_count])

    def selected_sources() -> set:
        return {
            span_by_id[span_id].source_id
            for ids in selected_by_act
            for span_id in ids
        }

    for source_id in required_sources - selected_sources():
        replacement = None
        for act_index, ids in enumerate(act_ids):
            for span_id in ids:
                if span_by_id[span_id].source_id == source_id:
                    replacement = (act_index, span_id)
                    break
            if replacement:
                break
        if replacement is None:
            continue
        act_index, span_id = replacement
        selected = selected_by_act[act_index]
        replace_index = next(
            (
                index
                for index, selected_id in enumerate(selected)
                if sum(
                    span_by_id[item].source_id
                    == span_by_id[selected_id].source_id
                    for group in selected_by_act
                    for item in group
                ) > 1
            ),
            None,
        )
        if replace_index is not None:
            selected[replace_index] = span_id
            selected.sort(key=lambda item: span_by_id[item].start_ms)
