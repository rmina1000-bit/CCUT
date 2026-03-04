from pathlib import Path
from collections import defaultdict
from .trace_chain import append_with_chain


_BUFFER: dict = defaultdict(list)
_BUFFER_LIMIT: int = 50


def buffered_append(log_path: Path, payload: dict):
    try:
        _BUFFER[log_path].append(payload)
        if len(_BUFFER[log_path]) >= _BUFFER_LIMIT:
            flush(log_path)
    except Exception:
        pass


def flush(log_path: Path):
    try:
        items = _BUFFER.pop(log_path, [])
        for payload in items:
            append_with_chain(log_path, payload)
        if items:
            from datetime import datetime, timezone
            from .trace_chain import _last_hash
            from .live_metrics import update_last_flush
            ts = datetime.now(timezone.utc).isoformat()
            last_hash = _last_hash(log_path)
            update_last_flush(ts, last_hash)
    except Exception:
        pass


def flush_all():
    try:
        for log_path in list(_BUFFER.keys()):
            flush(log_path)
    except Exception:
        pass
