import json
from typing import Any, List

from .contracts import TextReadiness, TextReadinessState


def decode_subtitle_segments(raw_segments: Any) -> List[dict]:
    value = raw_segments
    for _ in range(3):
        if not isinstance(value, str):
            break
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("subtitle segments must decode to a list")
    return [item for item in value if isinstance(item, dict)]


def assess_text_readiness(
    source_id: str,
    raw_segments: Any,
    *,
    persisted: bool,
    error: str = "",
) -> TextReadiness:
    if error:
        return TextReadiness(
            source_id=source_id,
            state=TextReadinessState.FAILED,
            reason=error,
        )
    if not persisted:
        return TextReadiness(
            source_id=source_id,
            state=TextReadinessState.PENDING,
            reason="subtitle_not_persisted",
        )
    try:
        segments = decode_subtitle_segments(raw_segments)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return TextReadiness(
            source_id=source_id,
            state=TextReadinessState.FAILED,
            reason=f"invalid_subtitle_segments:{exc}",
        )

    text_count = sum(1 for segment in segments if str(segment.get("text") or "").strip())
    state = (
        TextReadinessState.READY
        if text_count > 0
        else TextReadinessState.INSUFFICIENT_TEXT
    )
    return TextReadiness(
        source_id=source_id,
        state=state,
        segment_count=len(segments),
        text_segment_count=text_count,
        reason=None if text_count > 0 else "no_text_segments",
    )


def load_text_readiness(source_id: str) -> TextReadiness:
    try:
        from archive.db_models import SubtitleTable
        from database import SessionLocal

        with SessionLocal() as db:
            row = db.query(SubtitleTable).filter_by(source_id=source_id).first()
            if row is None:
                return assess_text_readiness(source_id, None, persisted=False)
            return assess_text_readiness(
                source_id,
                row.segments,
                persisted=str(row.status or "").upper() == "COMPLETE",
            )
    except Exception as exc:
        return assess_text_readiness(
            source_id,
            None,
            persisted=False,
            error=f"subtitle_readiness_load_failed:{exc}",
        )
