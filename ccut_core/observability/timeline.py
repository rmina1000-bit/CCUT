import json
from datetime import datetime, timezone
from pathlib import Path
from .runtime_switch import is_enabled
from .trace_buffer import buffered_append


TRACE_DIR = Path("storage/observability")
TIMELINE_LOG = TRACE_DIR / "timeline.log"

_timeline_seq = 0
_open_phases: dict = {}


def record_start(phase: str):
    global _timeline_seq
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        _timeline_seq += 1
        now = datetime.now(timezone.utc)
        _open_phases[phase] = (_timeline_seq, now)

        entry = {
            "timeline_seq": _timeline_seq,
            "phase": phase,
            "state": "START",
            "timestamp": now.isoformat(),
            "duration_ms": None,
        }

        if not is_enabled():
            return
        buffered_append(TIMELINE_LOG, entry)
    except Exception:
        pass


def record_end(phase: str):
    global _timeline_seq
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        _timeline_seq += 1
        now = datetime.now(timezone.utc)

        duration_ms = None
        if phase in _open_phases:
            _, start_time = _open_phases.pop(phase)
            duration_ms = round((now - start_time).total_seconds() * 1000, 2)

        entry = {
            "timeline_seq": _timeline_seq,
            "phase": phase,
            "state": "END",
            "timestamp": now.isoformat(),
            "duration_ms": duration_ms,
        }

        if not is_enabled():
            return
        buffered_append(TIMELINE_LOG, entry)
    except Exception:
        pass
