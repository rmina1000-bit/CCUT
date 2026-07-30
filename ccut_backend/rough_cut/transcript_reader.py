import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from edit_contract.time_units import to_ms

from .contracts import TranscriptExclusion, TranscriptReadResult, TranscriptSpan
from .readiness import decode_subtitle_segments


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "ccut_app.db"
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_SINGLE_TOKEN_REPEAT_LIMIT = 10
_PHRASE_REPEAT_LIMIT = 4
_PHRASE_MIN_COVERED_TOKENS = 12
_PHRASE_MIN_COVERAGE = 0.65
_LOW_UNIQUE_MIN_TOKENS = 20
_LOW_UNIQUE_RATIO = 0.20


class TranscriptReaderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepetitionFinding:
    unit: str
    repeat_count: int
    coverage: float


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.casefold())


def detect_repetition_hallucination(text: str) -> Optional[RepetitionFinding]:
    tokens = _tokens(text)
    token_count = len(tokens)
    if token_count < _SINGLE_TOKEN_REPEAT_LIMIT:
        return None

    best: Optional[Tuple[int, float, int, int, Sequence[str]]] = None
    max_width = min(12, token_count // _PHRASE_REPEAT_LIMIT)
    for width in range(1, max_width + 1):
        for start in range(0, token_count - width + 1):
            unit = tokens[start:start + width]
            repeat_count = 1
            cursor = start + width
            while (
                cursor + width <= token_count
                and tokens[cursor:cursor + width] == unit
            ):
                repeat_count += 1
                cursor += width

            covered = width * repeat_count
            coverage = covered / token_count
            if width == 1:
                qualifies = (
                    repeat_count >= _SINGLE_TOKEN_REPEAT_LIMIT
                    and coverage >= _PHRASE_MIN_COVERAGE
                )
            else:
                qualifies = (
                    repeat_count >= _PHRASE_REPEAT_LIMIT
                    and covered >= _PHRASE_MIN_COVERED_TOKENS
                    and coverage >= _PHRASE_MIN_COVERAGE
                )
            if not qualifies:
                continue

            # 같은 반복 범위를 설명하면 가장 짧은 원형 단위를 근거로 남긴다.
            candidate = (covered, coverage, -width, repeat_count, unit)
            if best is None or candidate[:4] > best[:4]:
                best = candidate

    if best is not None:
        _, coverage, _, repeat_count, unit = best
        return RepetitionFinding(
            unit=" ".join(unit),
            repeat_count=repeat_count,
            coverage=round(coverage, 4),
        )

    unique_ratio = len(set(tokens)) / token_count
    if token_count > _LOW_UNIQUE_MIN_TOKENS and unique_ratio < _LOW_UNIQUE_RATIO:
        return RepetitionFinding(
            unit="low_unique_token_ratio",
            repeat_count=token_count - len(set(tokens)),
            coverage=round(1.0 - unique_ratio, 4),
        )
    return None


def _span_id(source_id: str, start_ms: int, end_ms: int) -> str:
    raw = f"{source_id}|{start_ms}|{end_ms}"
    return "TSPAN_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()


def _segment_confidence(segment: dict) -> Optional[float]:
    direct = segment.get("confidence")
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return max(0.0, min(1.0, float(direct)))
    probabilities = [
        float(word["probability"])
        for word in (segment.get("words") or [])
        if (
            isinstance(word, dict)
            and isinstance(word.get("probability"), (int, float))
            and not isinstance(word.get("probability"), bool)
        )
    ]
    if not probabilities:
        return None
    return max(0.0, min(1.0, sum(probabilities) / len(probabilities)))


def _read_source_segments(
    source_id: str,
    source_order: int,
    raw_segments,
) -> Tuple[List[TranscriptSpan], List[TranscriptExclusion]]:
    spans: List[TranscriptSpan] = []
    exclusions: List[TranscriptExclusion] = []
    for segment_order, segment in enumerate(decode_subtitle_segments(raw_segments)):
        text = " ".join(str(segment.get("text") or "").split())
        try:
            start_ms = to_ms(float(segment.get("start")))
            end_ms = to_ms(float(segment.get("end")))
        except (TypeError, ValueError):
            start_ms = end_ms = None

        reason = None
        finding = None
        if not text:
            reason = "empty_text"
        elif start_ms is None or end_ms is None or end_ms <= start_ms:
            reason = "invalid_time"
        else:
            finding = detect_repetition_hallucination(text)
            if finding is not None:
                reason = "repetition_loop"

        if reason is not None:
            exclusions.append(
                TranscriptExclusion(
                    source_id=source_id,
                    segment_order=segment_order,
                    reason=reason,
                    text=text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    repeat_unit=finding.unit if finding else None,
                    repeat_count=finding.repeat_count if finding else None,
                    repeat_coverage=finding.coverage if finding else None,
                )
            )
            continue

        spans.append(
            TranscriptSpan(
                span_id=_span_id(source_id, start_ms, end_ms),
                source_id=source_id,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                source_order=source_order,
                segment_order=segment_order,
                confidence=_segment_confidence(segment),
            )
        )
    return spans, exclusions


def read_project_transcript(
    project_id: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> TranscriptReadResult:
    if not project_id.strip():
        raise TranscriptReaderError("project_id_required")

    path = Path(db_path).resolve()
    if not path.is_file():
        raise TranscriptReaderError(f"database_not_found:{path}")

    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        source_rows = connection.execute(
            "SELECT source_id FROM project_sources WHERE program_id=? "
            "ORDER BY CASE WHEN display_order IS NULL THEN 1 ELSE 0 END, "
            "display_order, id",
            (project_id,),
        ).fetchall()
        source_ids = tuple(dict.fromkeys(row[0] for row in source_rows if row[0]))
        if not source_ids:
            raise TranscriptReaderError(f"project_sources_not_found:{project_id}")

        spans: List[TranscriptSpan] = []
        exclusions: List[TranscriptExclusion] = []
        missing_source_ids: List[str] = []
        for source_order, source_id in enumerate(source_ids):
            row = connection.execute(
                "SELECT segments, status FROM subtitles WHERE source_id=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (source_id,),
            ).fetchone()
            if row is None or str(row[1] or "").upper() != "COMPLETE":
                missing_source_ids.append(source_id)
                continue
            try:
                source_spans, source_exclusions = _read_source_segments(
                    source_id,
                    source_order,
                    row[0],
                )
            except (TypeError, ValueError) as exc:
                raise TranscriptReaderError(
                    f"invalid_subtitle_segments:{source_id}:{exc}"
                ) from exc
            spans.extend(source_spans)
            exclusions.extend(source_exclusions)

        return TranscriptReadResult(
            project_id=project_id,
            source_ids=source_ids,
            spans=tuple(spans),
            exclusions=tuple(exclusions),
            missing_source_ids=tuple(missing_source_ids),
        )
    except sqlite3.Error as exc:
        raise TranscriptReaderError(f"transcript_read_failed:{exc}") from exc
    finally:
        connection.close()
