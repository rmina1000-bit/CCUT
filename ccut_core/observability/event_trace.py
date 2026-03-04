import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .runtime_switch import is_enabled
from .trace_buffer import buffered_append


TRACE_DIR = Path("storage/observability")
TRACE_LOG = TRACE_DIR / "event_trace.log"

_trace_counter = 0


def _get_resource_state() -> dict:
    state = {"cpu": None, "mem_mb": None, "gpu_mem_mb": None}
    try:
        import psutil
        state["cpu"] = psutil.cpu_percent(interval=None)
        state["mem_mb"] = round(
            psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1
        )
    except Exception:
        pass
    return state


def log_event(event_type: str, engine_seq: int = None, metadata: dict = None):
    global _trace_counter
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        _trace_counter += 1

        entry = {
            "trace_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "engine_seq": engine_seq,
            "trace_seq": _trace_counter,
            "resource_state": _get_resource_state(),
            "metadata": metadata or {},
        }

        if not is_enabled():
            return
        buffered_append(TRACE_LOG, entry)
    except Exception:
        pass
