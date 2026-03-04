from pathlib import Path


_LAST_FLUSH_TS = None
_LAST_TRACE_HASH = None
_LAST_DECISION_COUNT = 0

_LOG_NAMES = ["event_trace", "timeline", "snapshot", "render_trace"]
_TRACE_DIR = Path("storage/observability")
_QUEUE_DIR = Path("storage/render_queue")


def update_last_flush(ts: str, last_hash: str):
    global _LAST_FLUSH_TS, _LAST_TRACE_HASH
    _LAST_FLUSH_TS = ts
    _LAST_TRACE_HASH = last_hash


def update_decision_count(n: int):
    global _LAST_DECISION_COUNT
    _LAST_DECISION_COUNT = n


def get_live_metrics() -> dict:
    from .runtime_switch import is_enabled
    from .trace_buffer import _BUFFER

    buffer_sizes = {}
    try:
        for name in _LOG_NAMES:
            path = _TRACE_DIR / f"{name}.log"
            buffer_sizes[name] = len(_BUFFER.get(path, []))
    except Exception:
        buffer_sizes = {name: 0 for name in _LOG_NAMES}

    render_queue_depth = 0
    try:
        if _QUEUE_DIR.exists():
            render_queue_depth = len(list(_QUEUE_DIR.glob("req_v*.json")))
    except Exception:
        pass

    return {
        "observability_enabled": is_enabled(),
        "buffer_sizes": buffer_sizes,
        "last_flush_timestamp": _LAST_FLUSH_TS,
        "last_trace_hash": _LAST_TRACE_HASH,
        "render_queue_depth": render_queue_depth,
        "decision_count": _LAST_DECISION_COUNT,
    }
