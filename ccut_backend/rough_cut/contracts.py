from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


class TextReadinessState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    INSUFFICIENT_TEXT = "insufficient_text"
    FAILED = "failed"


class RoughCutStoryPhase(str, Enum):
    GI = "gi"
    SEUNG = "seung"
    JEON = "jeon"
    GYEOL = "gyeol"


class QwenStoryAdapterStatus(str, Enum):
    OK = "ok"
    CONTRACT_INVALID = "contract_invalid"
    MODEL_CALL_FAILED = "model_call_failed"


@dataclass(frozen=True)
class TranscriptSpan:
    span_id: str
    source_id: str
    start_ms: int
    end_ms: int
    text: str
    source_order: int = 0
    segment_order: int = 0
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.span_id.strip():
            raise ValueError("span_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("TranscriptSpan requires 0 <= start_ms < end_ms")
        if not self.text.strip():
            raise ValueError("TranscriptSpan text is required")
        if self.source_order < 0 or self.segment_order < 0:
            raise ValueError("TranscriptSpan order values must be non-negative")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("TranscriptSpan confidence must be between 0 and 1")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoughCutAct:
    phase: RoughCutStoryPhase
    summary: str
    span_ids: Tuple[str, ...]

    @classmethod
    def from_model_output(cls, value: Any) -> "RoughCutAct":
        if not isinstance(value, Mapping):
            raise ValueError("each act must be an object")

        try:
            phase = RoughCutStoryPhase(value.get("phase"))
        except (TypeError, ValueError) as exc:
            raise ValueError("act phase must be gi, seung, jeon, or gyeol") from exc

        summary = value.get("summary")
        if not isinstance(summary, str):
            raise ValueError("act summary must be a string")

        span_ids = _string_tuple(value.get("span_ids"), "act span_ids")
        return cls(phase=phase, summary=summary, span_ids=span_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "summary": self.summary,
            "span_ids": list(self.span_ids),
        }


@dataclass(frozen=True)
class RoughCutStoryDraft:
    project_id: str
    premise: str
    acts: Tuple[RoughCutAct, ...]
    ordered_span_ids: Tuple[str, ...]

    @classmethod
    def from_model_output(
        cls,
        project_id: str,
        value: Any,
    ) -> "RoughCutStoryDraft":
        if not project_id.strip():
            raise ValueError("project_id is required")
        if not isinstance(value, Mapping):
            raise ValueError("story draft must be an object")

        premise = value.get("premise")
        if not isinstance(premise, str):
            raise ValueError("premise must be a string")

        raw_acts = value.get("acts")
        if not isinstance(raw_acts, Sequence) or isinstance(raw_acts, (str, bytes)):
            raise ValueError("acts must be an array")
        acts = tuple(RoughCutAct.from_model_output(item) for item in raw_acts)
        expected_phases = tuple(RoughCutStoryPhase)
        if tuple(act.phase for act in acts) != expected_phases:
            raise ValueError("acts must contain gi, seung, jeon, gyeol in order")

        ordered_span_ids = _string_tuple(
            value.get("ordered_span_ids"),
            "ordered_span_ids",
        )
        return cls(
            project_id=project_id,
            premise=premise,
            acts=acts,
            ordered_span_ids=ordered_span_ids,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "premise": self.premise,
            "acts": [act.to_dict() for act in self.acts],
            "ordered_span_ids": list(self.ordered_span_ids),
        }


@dataclass(frozen=True)
class ChunkSelectionDraft:
    summary: str
    selected_span_ids: Tuple[str, ...]

    @classmethod
    def from_model_output(cls, value: Any) -> "ChunkSelectionDraft":
        if not isinstance(value, Mapping):
            raise ValueError("chunk selection must be an object")
        summary = value.get("summary")
        if not isinstance(summary, str):
            raise ValueError("chunk summary must be a string")
        return cls(
            summary=summary,
            selected_span_ids=_string_tuple(
                value.get("selected_span_ids"),
                "selected_span_ids",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "selected_span_ids": list(self.selected_span_ids),
        }


@dataclass(frozen=True)
class QwenChunkAdapterResult:
    status: QwenStoryAdapterStatus
    project_id: str
    model: str
    prompt_version: str
    chunk_index: int
    chunk_count: int
    input_span_count: int
    latency_ms: int
    selection: Optional[ChunkSelectionDraft] = None
    raw_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is QwenStoryAdapterStatus.OK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "project_id": self.project_id,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "chunk_index": self.chunk_index,
            "chunk_count": self.chunk_count,
            "input_span_count": self.input_span_count,
            "latency_ms": self.latency_ms,
            "selection": self.selection.to_dict() if self.selection else None,
            "raw_output": self.raw_output,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class QwenStoryAdapterResult:
    status: QwenStoryAdapterStatus
    project_id: str
    model: str
    prompt_version: str
    input_span_count: int
    latency_ms: int
    draft: Optional[RoughCutStoryDraft] = None
    raw_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is QwenStoryAdapterStatus.OK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "project_id": self.project_id,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "input_span_count": self.input_span_count,
            "latency_ms": self.latency_ms,
            "draft": self.draft.to_dict() if self.draft else None,
            "raw_output": self.raw_output,
            "error_message": self.error_message,
        }


def _string_tuple(value: Any, field_name: str) -> Tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")
    return tuple(value)


@dataclass(frozen=True)
class TranscriptExclusion:
    source_id: str
    segment_order: int
    reason: str
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    repeat_unit: Optional[str] = None
    repeat_count: Optional[int] = None
    repeat_coverage: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptReadResult:
    project_id: str
    source_ids: Tuple[str, ...]
    spans: Tuple[TranscriptSpan, ...]
    exclusions: Tuple[TranscriptExclusion, ...]
    missing_source_ids: Tuple[str, ...] = ()

    @property
    def total_segment_count(self) -> int:
        return len(self.spans) + len(self.exclusions)

    @property
    def filtered_count(self) -> int:
        return len(self.exclusions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "source_ids": list(self.source_ids),
            "spans": [span.to_dict() for span in self.spans],
            "exclusions": [item.to_dict() for item in self.exclusions],
            "missing_source_ids": list(self.missing_source_ids),
            "total_segment_count": self.total_segment_count,
            "filtered_count": self.filtered_count,
        }


@dataclass(frozen=True)
class TextReadiness:
    source_id: str
    state: TextReadinessState
    segment_count: int = 0
    text_segment_count: int = 0
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if self.segment_count < 0 or self.text_segment_count < 0:
            raise ValueError("segment counts must be non-negative")
        if self.text_segment_count > self.segment_count:
            raise ValueError("text_segment_count cannot exceed segment_count")

    @property
    def ready(self) -> bool:
        return self.state is TextReadinessState.READY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "state": self.state.value,
            "ready": self.ready,
            "segment_count": self.segment_count,
            "text_segment_count": self.text_segment_count,
            "reason": self.reason,
        }
